import json
import time
import threading
import logging
from collections import deque

logger = logging.getLogger('load_test')
logging.basicConfig(level=logging.INFO, format='%(asctime)s [%(levelname)s] %(message)s')

class ChatThrottle:
    """Thread-safe rate limiter for chat requests.
    Enforces both concurrency limit (semaphore) and sliding-window rate limit.
    """
    def __init__(self, max_concurrent: int, max_per_minute: int):
        self.semaphore = threading.Semaphore(max_concurrent)
        self.max_per_minute = max_per_minute
        self.timestamps = deque()
        self.lock = threading.Lock()
    
    def acquire(self, timeout: float = 60.0) -> bool:
        """Acquire both semaphore and rate limit slot. Returns True if acquired."""
        if not self.semaphore.acquire(timeout=timeout):
            return False
        # Wait until we're under the rate limit
        deadline = time.time() + timeout
        while time.time() < deadline:
            with self.lock:
                now = time.time()
                # Purge timestamps older than 60s
                while self.timestamps and self.timestamps[0] < now - 60:
                    self.timestamps.popleft()
                if len(self.timestamps) < self.max_per_minute:
                    self.timestamps.append(now)
                    return True
            time.sleep(0.5)  # Wait and retry
        # Timed out on rate limit, release semaphore
        self.semaphore.release()
        return False
    
    def release(self):
        self.semaphore.release()


def register_user(client, username: str, email: str, password: str) -> tuple[bool, bool]:
    """Register a user. Returns (success, was_new).
    If user already exists (400), returns (True, False).
    """
    with client.post(
        '/auth/register',
        json={'username': username, 'email': email, 'password': password},
        name='/auth/register',
        catch_response=True
    ) as resp:
        if resp.status_code == 200:
            resp.success()
            return True, True
        elif resp.status_code == 400:
            # User already exists — that's fine
            resp.success()  # Don't count as failure
            return True, False
        else:
            resp.failure(f'Registration failed: {resp.status_code}')
            return False, False


def login_user(client, email: str, password: str) -> str | None:
    """Login and return JWT token, or None on failure."""
    with client.post(
        '/auth/login',
        json={'email': email, 'password': password},
        name='/auth/login',
        catch_response=True
    ) as resp:
        if resp.status_code == 200:
            data = resp.json()
            token = data.get('access_token')
            resp.success()
            return token
        else:
            resp.failure(f'Login failed: {resp.status_code}')
            return None


def auth_headers(token: str) -> dict:
    return {'Authorization': f'Bearer {token}'}


def create_session(client, token: str) -> str | None:
    """Create a new agent session, return session_id."""
    with client.post(
        '/api/session',
        json={},
        headers=auth_headers(token),
        name='/api/session [create]',
        catch_response=True
    ) as resp:
        if resp.status_code == 200:
            data = resp.json()
            resp.success()
            return data.get('session_id')
        else:
            resp.failure(f'Create session failed: {resp.status_code} {resp.text[:200]}')
            return None


def delete_session(client, token: str, session_id: str) -> bool:
    """Delete an agent session."""
    with client.delete(
        f'/api/session/{session_id}',
        headers=auth_headers(token),
        name='/api/session [delete]',
        catch_response=True
    ) as resp:
        if resp.status_code in (200, 404):  # 404 is fine if already deleted
            resp.success()
            return True
        else:
            resp.failure(f'Delete session failed: {resp.status_code}')
            return False


def send_chat_and_read_sse(
    client,
    token: str,
    session_id: str,
    text: str,
    timeout: int = 300,
    request_name: str = '/api/chat [SSE]'
) -> tuple[str, list[dict], str | None, float]:
    """Send a chat message and read the SSE stream until a terminal event.
    
    Returns: (full_text, events, terminal_event_type, duration_seconds)
    """
    terminal_events = {'turn_complete', 'approval_required', 'error', 'interrupted', 'shutdown'}
    full_text = ''
    events = []
    terminal_event = None
    start_time = time.time()
    
    try:
        with client.post(
            f'/api/chat/{session_id}',
            json={'text': text},
            headers={**auth_headers(token), 'Accept': 'text/event-stream'},
            name=request_name,
            stream=True,
            catch_response=True,
            timeout=timeout
        ) as resp:
            if resp.status_code != 200:
                resp.failure(f'Chat SSE failed: {resp.status_code} {resp.text[:200]}')
                return '', [], None, time.time() - start_time
            
            # Read SSE stream line by line
            data_buffer = ''
            for line in resp.iter_lines():
                if time.time() - start_time > timeout:
                    resp.failure('SSE timeout')
                    return full_text, events, 'timeout', time.time() - start_time
                
                if not line:
                    continue
                    
                line_str = line if isinstance(line, str) else line.decode('utf-8', errors='replace')
                
                # Skip SSE comments (keepalives)
                if line_str.startswith(':'):
                    continue
                
                if line_str.startswith('data: '):
                    data_str = line_str[6:]
                    try:
                        event_data = json.loads(data_str)
                        events.append(event_data)
                        
                        event_type = event_data.get('event_type', '')
                        data = event_data.get('data', {})
                        
                        # Accumulate text from assistant chunks
                        if event_type == 'assistant_chunk':
                            chunk_text = data.get('content', '') or data.get('text', '')
                            full_text += chunk_text
                        elif event_type == 'tool_output':
                            tool_text = data.get('output', '') or data.get('content', '')
                            full_text += f'\\n[TOOL OUTPUT]: {tool_text}'
                        
                        # Check for terminal event
                        if event_type in terminal_events:
                            terminal_event = event_type
                            if event_type == 'turn_complete':
                                resp.success()
                            elif event_type == 'error':
                                error_text = data.get("error") or data.get("message", "unknown")
                                resp.failure(f'Agent error: {error_text[:200]}')
                            else:
                                resp.success()
                            break
                    except json.JSONDecodeError:
                        continue
            
            if terminal_event is None:
                resp.success()  # Stream ended without terminal event
                
    except Exception as e:
        error_msg = str(e)
        if '429' in error_msg:
            logger.warning(f'Mistral 429 rate limit hit: {error_msg[:200]}')
        return full_text, events, 'exception', time.time() - start_time
    
    duration = time.time() - start_time
    return full_text, events, terminal_event, duration
