import random
import logging
import threading
from locust import HttpUser, task, between, events

from config import (
    TEST_USER_PREFIX, TEST_USER_PASSWORD,
    MISTRAL_MAX_CONCURRENT, MISTRAL_MAX_PER_MINUTE,
    ENABLE_ML_TRAINING, MAX_ML_TRAINING_RUNS,
    CACHE_HIT_DATASET_ID, CACHE_HIT_MODEL_TYPE,
    CACHE_MISS_DATASET_ID, CACHE_MISS_MODEL_TYPE,
    CACHE_MISS_TARGET_COLUMN, SSE_TIMEOUT_SECONDS,
)
from helpers import (
    ChatThrottle, register_user, login_user, auth_headers,
    create_session, delete_session, send_chat_and_read_sse,
)
from metrics import metrics

logger = logging.getLogger('load_test')

# Global rate limiter shared across all users
chat_throttle = ChatThrottle(MISTRAL_MAX_CONCURRENT, MISTRAL_MAX_PER_MINUTE)

# Global counter for ML training runs (to enforce cap)
_ml_training_count = 0
_ml_training_lock = threading.Lock()

# User numbering
_user_counter = 0
_user_counter_lock = threading.Lock()


def _next_user_number() -> int:
    global _user_counter
    with _user_counter_lock:
        _user_counter += 1
        return _user_counter


def _can_do_ml_training() -> bool:
    """Check if we're still under the ML training cap."""
    global _ml_training_count
    with _ml_training_lock:
        if _ml_training_count >= MAX_ML_TRAINING_RUNS:
            return False
        _ml_training_count += 1
        return True


LIGHTWEIGHT_PROMPTS = [
    'What can you do?',
    'What tools do you have? List them briefly.',
    'Explain what this application can do in 2-3 sentences.',
    'What types of machine learning tasks can you help with?',
    'What datasets are available? Just give me a brief overview.',
    'Hi! Give me a quick summary of your capabilities.',
]


class LightweightUser(HttpUser):
    """Simulates 98% of users making lightweight requests.
    These hit Mistral for chat but with short prompts/responses.
    """
    weight = 98
    wait_time = between(1, 3)  # Fast pacing to stress the LLM router
    
    def on_start(self):
        num = _next_user_number()
        self.username = f'{TEST_USER_PREFIX}{num}'
        self.email = f'{self.username}@loadtest.dev'
        self.password = TEST_USER_PASSWORD
        self.token = None
        
        # Register (or reuse existing)
        success, was_new = register_user(self.client, self.username, self.email, self.password)
        if was_new:
            metrics.increment('users_created')
            metrics.increment('mongo_writes')
        else:
            metrics.increment('users_reused')
        
        # Login
        if success:
            self.token = login_user(self.client, self.email, self.password)
            if self.token:
                metrics.increment('logins_success')
                metrics.increment('mongo_reads')
            else:
                metrics.increment('logins_failed')
    
    @task(1)
    def ask_general_question(self):
        """Send a lightweight chat prompt."""
        if not self.token:
            return
        
        if not chat_throttle.acquire(timeout=30):
            logger.debug('Chat throttle timeout, skipping')
            return
        
        session_id = None
        try:
            session_id = create_session(self.client, self.token)
            if not session_id:
                return
            metrics.increment('sessions_created')
            metrics.increment('mongo_writes')
            
            prompt = random.choice(LIGHTWEIGHT_PROMPTS)
            metrics.increment('chat_requests')
            
            full_text, events_list, terminal, duration = send_chat_and_read_sse(
                self.client, self.token, session_id, prompt,
                timeout=SSE_TIMEOUT_SECONDS,
                request_name=f'/api/chat [lightweight]'
            )
            
            if terminal == 'turn_complete':
                metrics.increment('chat_successes')
            elif terminal == 'timeout':
                metrics.increment('sse_timeouts')
                metrics.increment('chat_failures')
            elif terminal == 'error' or terminal == 'exception':
                metrics.increment('chat_failures')
            else:
                metrics.increment('chat_successes')  # Stream ended normally
        finally:
            chat_throttle.release()
            if session_id:
                delete_session(self.client, self.token, session_id)
                metrics.increment('sessions_deleted')


class HeavyMLUser(HttpUser):
    """Simulates 1-2 users performing ML operations.
    Much slower pacing to avoid overwhelming Mistral and ML compute.
    """
    weight = 2
    wait_time = between(30, 60)
    
    def on_start(self):
        num = _next_user_number()
        self.username = f'{TEST_USER_PREFIX}ml_{num}'
        self.email = f'{self.username}@loadtest.dev'
        self.password = TEST_USER_PASSWORD
        self.token = None
        
        success, was_new = register_user(self.client, self.username, self.email, self.password)
        if was_new:
            metrics.increment('users_created')
            metrics.increment('mongo_writes')
        else:
            metrics.increment('users_reused')
        
        if success:
            self.token = login_user(self.client, self.email, self.password)
            if self.token:
                metrics.increment('logins_success')
            else:
                metrics.increment('logins_failed')
    
    @task(3)
    def report_existing_models(self):
        """Ask the agent to list existing models — tests cache-hit path.
        This uses list_local_models (MongoDB read) without training.
        """
        if not self.token:
            return
        
        if not chat_throttle.acquire(timeout=60):
            logger.debug('Chat throttle timeout for ML user, skipping')
            return
        
        session_id = None
        try:
            session_id = create_session(self.client, self.token)
            if not session_id:
                return
            metrics.increment('sessions_created')
            
            prompt = (
                'Use the list_local_models tool to show me all trained models '
                'and their accuracy/F1 metrics. Do not train anything new, '
                'just report what already exists.'
            )
            metrics.increment('chat_requests')
            metrics.increment('existing_model_lookups')
            metrics.increment('mongo_reads')
            
            full_text, events_list, terminal, duration = send_chat_and_read_sse(
                self.client, self.token, session_id, prompt,
                timeout=SSE_TIMEOUT_SECONDS,
                request_name='/api/chat [list models]'
            )
            
            if terminal == 'turn_complete':
                metrics.increment('chat_successes')
                metrics.increment('cache_hits')
                # Verify metrics appear in response
                text_lower = full_text.lower()
                if 'accuracy' in text_lower or 'f1' in text_lower or 'rmse' in text_lower:
                    logger.info(f'✅ Model list returned metrics successfully ({duration:.1f}s)')
                else:
                    logger.warning(f'⚠️ Model list response may not contain metrics')
            else:
                metrics.increment('chat_failures')
                if terminal == 'timeout':
                    metrics.increment('sse_timeouts')
        finally:
            chat_throttle.release()
            if session_id:
                delete_session(self.client, self.token, session_id)
                metrics.increment('sessions_deleted')
    
    @task(1)
    def train_model(self):
        """Ask the agent to train a model — tests cache-miss path.
        Guarded by MAX_ML_TRAINING_RUNS to limit MongoDB writes.
        """
        if not self.token:
            return
        
        if not ENABLE_ML_TRAINING:
            logger.info('ML training disabled via config, skipping')
            return
        
        if not _can_do_ml_training():
            logger.info(f'ML training cap ({MAX_ML_TRAINING_RUNS}) reached, skipping')
            return
        
        if not chat_throttle.acquire(timeout=120):
            logger.debug('Chat throttle timeout for ML training, skipping')
            return
        
        session_id = None
        try:
            session_id = create_session(self.client, self.token)
            if not session_id:
                return
            metrics.increment('sessions_created')
            metrics.increment('ml_training_started')
            metrics.increment('cache_misses')
            
            prompt = (
                f"Train a {CACHE_MISS_MODEL_TYPE} model on the Iris Species dataset "
                f"(dataset_id: {CACHE_MISS_DATASET_ID}). "
                f"The target column is '{CACHE_MISS_TARGET_COLUMN}'. "
                f"Use the train_local_model tool directly."
            )
            metrics.increment('chat_requests')
            
            full_text, events_list, terminal, duration = send_chat_and_read_sse(
                self.client, self.token, session_id, prompt,
                timeout=SSE_TIMEOUT_SECONDS,
                request_name='/api/chat [train model]'
            )
            
            if terminal == 'turn_complete':
                metrics.increment('chat_successes')
                metrics.increment('ml_training_completed')
                text_lower = full_text.lower()
                if 'cache hit' in text_lower:
                    metrics.increment('cache_hits')
                    logger.info(f'✅ Training cache HIT ({duration:.1f}s)')
                elif 'accuracy' in text_lower or 'f1' in text_lower or 'successfully trained' in text_lower:
                    metrics.increment('new_models_created')
                    metrics.increment('mongo_writes', 2)  # model doc + GridFS
                    logger.info(f'✅ Model trained successfully ({duration:.1f}s)')
                else:
                    logger.warning(f'⚠️ Training response unclear: {full_text[:200]}')
            else:
                metrics.increment('chat_failures')
                metrics.increment('ml_training_failed')
                if terminal == 'timeout':
                    metrics.increment('sse_timeouts')
                logger.error(f'❌ Model training failed: terminal={terminal} ({duration:.1f}s)')
        finally:
            chat_throttle.release()
            if session_id:
                delete_session(self.client, self.token, session_id)
                metrics.increment('sessions_deleted')

from locust import events
import os
from datetime import datetime

OMNIROUTE_LOG_PATH = os.environ.get("OMNIROUTE_LOG_PATH", "/tmp/omniroute.log")


@events.test_start.add_listener
def on_test_start(environment, **kwargs):
    # 1. Clear the OmniRoute log file so we only count metrics for the current run!
    if os.path.exists(OMNIROUTE_LOG_PATH):
        try:
            open(OMNIROUTE_LOG_PATH, 'w').close()
        except:
            pass
            
    # 2. Automatically clear zombie sessions from MongoDB to prevent 200/200 capacity errors!
    try:
        import subprocess
        subprocess.run(["python3", "/tmp/clean_sessions.py"], capture_output=True)
        print("🧹 Cleaned up any zombie sessions from previous interrupted runs!")
    except Exception as e:
        print("Could not clean zombie sessions:", e)

@events.test_stop.add_listener
def on_test_stop(environment, **kwargs):
    print("\n" + "="*60)
    print("🎯 GENERATING UNIFIED LOAD TEST REPORT...")
    print("="*60)

    total_requests = 0
    total_failures = 0
    chat_requests = 0
    chat_failures = 0
    chat_latency = 0
    
    start_time = environment.stats.start_time
    last_req_time = environment.stats.last_request_timestamp
    duration_secs = int(last_req_time - start_time) if (start_time and last_req_time) else 0
    duration_mins = round(duration_secs / 60, 2)
    
    # Try different properties for user_count and spawn_rate
    user_count = getattr(environment.runner, 'target_user_count', None) or getattr(environment.parsed_options, 'num_users', 'Unknown')
    spawn_rate = getattr(environment.runner, 'target_spawn_rate', None) or getattr(environment.parsed_options, 'spawn_rate', 'Unknown')

    for key, stats in environment.stats.entries.items():
        total_requests += stats.num_requests
        total_failures += stats.num_failures
        name = getattr(stats, "name", str(key)).lower()
        if "chat" in name:
            chat_requests += stats.num_requests
            chat_failures += stats.num_failures
            chat_latency = stats.avg_response_time
            
    omni_successes = 0
    omni_timeouts = 0
    providers = set()
    
    if os.path.exists(OMNIROUTE_LOG_PATH):
        with open(OMNIROUTE_LOG_PATH, 'r', encoding='utf-8', errors='ignore') as f:
            for line in f:
                if 'succeeded' in line and '[sse] Model' in line:
                    omni_successes += 1
                    try:
                        parts = line.split('Model ')[1].split(' succeeded')[0]
                        providers.add(parts.split('/')[0])
                    except:
                        pass
                if 'timeout' in line.lower() or 'error' in line.lower() or 'RATE-LIMIT' in line:
                    omni_timeouts += 1
    
    report_path = f"load_test_report_{datetime.now().strftime('%Y%m%d_%H%M%S')}.md"
    
    report = f"""# 🚀 ML Intern + OmniRoute Load Test Summary
*Generated on {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}*

## ⚙️ Test Parameters
- **Users Simulated:** {user_count}
- **Spawn Rate:** {spawn_rate} users/sec
- **Test Duration:** {duration_secs} seconds ({duration_mins} mins)

## 📊 Client Metrics (Locust)
- **Total Requests Handled:** {total_requests}
- **Total Failures:** {total_failures}
- **LLM Chat Requests Completed:** {chat_requests}
- **LLM Chat Requests Failed:** {chat_failures}
- **Average Chat Latency:** {round(chat_latency)} ms

## 🤖 Gateway Metrics (OmniRoute)
*Parsed from `{OMNIROUTE_LOG_PATH}`*
- **Successful Upstream Hits:** {omni_successes}
- **Gateway Intercepts / Retries:** {omni_timeouts}
- **Providers Engaged:** {', '.join(providers) if providers else 'None detected'}

## 💡 Performance Insight
**Note on 0 Chat Requests:** If Locust reports 0 completed chat requests but OmniRoute shows upstream hits, it means you stopped the test *before* the upstream LLMs finished streaming their responses back to Locust. Locust only logs requests that have completely finished!
"""
    with open(report_path, "w") as f:
        f.write(report)
        
    print(f"✅ Report successfully generated: {os.path.abspath(report_path)}")
    print("="*60 + "\n")
