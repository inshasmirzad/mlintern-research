import threading
import time
import logging
from locust import events

logger = logging.getLogger('load_test')

class LoadTestMetrics:
    """Thread-safe custom metrics collector for the load test."""
    
    def __init__(self):
        self._lock = threading.Lock()
        self.start_time = time.time()
        
        # Auth
        self.users_created = 0
        self.users_reused = 0
        self.logins_success = 0
        self.logins_failed = 0
        
        # Sessions
        self.sessions_created = 0
        self.sessions_deleted = 0
        
        # Chat / SSE
        self.chat_requests = 0
        self.chat_successes = 0
        self.chat_failures = 0
        self.sse_timeouts = 0
        
        # Mistral / LLM
        self.mistral_429s = 0
        self.mistral_retries = 0
        
        # ML Operations
        self.model_list_requests = 0
        self.dataset_list_requests = 0
        self.existing_model_lookups = 0
        
        # Cache
        self.cache_hits = 0
        self.cache_misses = 0
        
        # Training
        self.ml_training_started = 0
        self.ml_training_completed = 0
        self.ml_training_failed = 0
        self.new_models_created = 0
        
        # MongoDB estimates
        self.mongo_reads = 0
        self.mongo_writes = 0
    
    def increment(self, counter_name: str, amount: int = 1):
        with self._lock:
            current = getattr(self, counter_name, 0)
            setattr(self, counter_name, current + amount)
    
    def get(self, counter_name: str) -> int:
        with self._lock:
            return getattr(self, counter_name, 0)
    
    def print_summary(self):
        elapsed = time.time() - self.start_time
        print('\n' + '='*70)
        print('           LOAD TEST SUMMARY REPORT')
        print('='*70)
        print(f'  Duration:              {elapsed:.1f}s')
        print(f'  Peak Concurrent Users: (see Locust stats)')
        print()
        print('  --- Authentication ---')
        print(f'  Users Created:         {self.users_created}')
        print(f'  Users Reused:          {self.users_reused}')
        print(f'  Logins Success:        {self.logins_success}')
        print(f'  Logins Failed:         {self.logins_failed}')
        print()
        print('  --- Sessions ---')
        print(f'  Sessions Created:      {self.sessions_created}')
        print(f'  Sessions Deleted:      {self.sessions_deleted}')
        print()
        print('  --- Chat / SSE ---')
        print(f'  Chat Requests:         {self.chat_requests}')
        print(f'  Chat Successes:        {self.chat_successes}')
        print(f'  Chat Failures:         {self.chat_failures}')
        print(f'  SSE Timeouts:          {self.sse_timeouts}')
        print()
        print('  --- LLM / Mistral ---')
        print(f'  Mistral 429s:          {self.mistral_429s}')
        print(f'  Mistral Retries:       {self.mistral_retries}')
        print()
        print('  --- ML Operations ---')
        print(f'  Model List Requests:   {self.model_list_requests}')
        print(f'  Dataset List Requests: {self.dataset_list_requests}')
        print(f'  Existing Model Lookups:{self.existing_model_lookups}')
        print()
        print('  --- Cache (Model Training) ---')
        print(f'  Cache Hits:            {self.cache_hits}')
        print(f'  Cache Misses:          {self.cache_misses}')
        print()
        print('  --- Training ---')
        print(f'  Training Started:      {self.ml_training_started}')
        print(f'  Training Completed:    {self.ml_training_completed}')
        print(f'  Training Failed:       {self.ml_training_failed}')
        print(f'  New Models Created:    {self.new_models_created}')
        print()
        print('  --- MongoDB (Estimated) ---')
        print(f'  Reads:                 {self.mongo_reads}')
        print(f'  Writes:                {self.mongo_writes}')
        print('='*70 + '\n')


# Global singleton
metrics = LoadTestMetrics()


@events.quitting.add_listener
def on_quitting(environment, **kwargs):
    metrics.print_summary()


@events.request.add_listener
def on_request(request_type, name, response_time, response_length, response, exception, **kwargs):
    if response and hasattr(response, 'status_code'):
        if response.status_code == 429:
            metrics.increment('mistral_429s')
