"""进程内滑动窗口限流，用于保护 AI 问答接口（防止无鉴权时额度被刷）。"""
import time
from collections import defaultdict, deque
from threading import Lock


class SlidingWindowLimiter:
    def __init__(self, max_requests, window_seconds):
        self.max_requests = max_requests
        self.window_seconds = window_seconds
        self._hits = defaultdict(deque)
        self._lock = Lock()

    def allow(self, key):
        now = time.monotonic()
        with self._lock:
            dq = self._hits[key]
            while dq and now - dq[0] > self.window_seconds:
                dq.popleft()
            if len(dq) >= self.max_requests:
                return False
            dq.append(now)
            return True