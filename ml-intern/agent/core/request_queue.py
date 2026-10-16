import asyncio
import logging
import time
from typing import Dict
from contextlib import asynccontextmanager

logger = logging.getLogger(__name__)

class RequestQueue:
    def __init__(self, concurrency_limit: int = 50, requests_per_minute: int = 500):
        self.semaphores: Dict[str, asyncio.Semaphore] = {}
        self.concurrency_limit = concurrency_limit
        self.requests_per_minute = requests_per_minute
        
        # Sliding window for rate limiting: provider -> list of timestamps
        self.request_timestamps: Dict[str, list[float]] = {}
        self.lock = asyncio.Lock()
        
    async def acquire(self, provider: str):
        """Acquire a slot to make a request to the provider."""
        async with self.lock:
            if provider not in self.semaphores:
                self.semaphores[provider] = asyncio.Semaphore(self.concurrency_limit)
            if provider not in self.request_timestamps:
                self.request_timestamps[provider] = []
                
        # 1. Respect concurrency limit
        await self.semaphores[provider].acquire()
        
        # 2. Respect rate limit
        while True:
            now = time.time()
            async with self.lock:
                # Remove timestamps older than 60 seconds
                self.request_timestamps[provider] = [t for t in self.request_timestamps[provider] if now - t < 60]
                
                if len(self.request_timestamps[provider]) < self.requests_per_minute:
                    # We can proceed
                    self.request_timestamps[provider].append(now)
                    break
            
            # Rate limit exceeded, wait a bit
            await asyncio.sleep(1)
        
    def release(self, provider: str):
        """Release the slot for the provider."""
        if provider in self.semaphores:
            self.semaphores[provider].release()

    @asynccontextmanager
    async def session(self, provider: str):
        await self.acquire(provider)
        try:
            yield
        finally:
            self.release(provider)

# Global request queue
request_queue = RequestQueue()
