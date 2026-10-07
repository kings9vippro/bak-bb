# safety_controller.py
"""Defensive rate-limit/circuit-breaker controller.

Purpose: keep owned integrations within conservative limits and stop on
platform-side enforcement. It does NOT spoof fingerprints, rotate identities,
or attempt to bypass anti-abuse systems.
"""
from __future__ import annotations
import time, threading
from dataclasses import dataclass

@dataclass
class GuardState:
    failures: int = 0
    blocked_until: float = 0.0
    sent: int = 0
    last_send: float = 0.0

class SafetyController:
    def __init__(self, min_interval=5.0, max_per_hour=120, cooldown=60.0):
        self.min_interval = float(min_interval)
        self.max_per_hour = int(max_per_hour)
        self.cooldown = float(cooldown)
        self._lock = threading.Lock()
        self._state = {}
        self._events = {}

    def _get(self, key):
        return self._state.setdefault(key, GuardState())

    def allow(self, key):
        now = time.time()
        with self._lock:
            st = self._get(key)
            if now < st.blocked_until:
                return False, st.blocked_until - now
            events = [t for t in self._events.setdefault(key, []) if now - t < 3600]
            self._events[key] = events
            if len(events) >= self.max_per_hour:
                st.blocked_until = now + self.cooldown
                return False, self.cooldown
            wait = max(0.0, self.min_interval - (now - st.last_send))
            if wait:
                return False, wait
            st.last_send = now
            events.append(now)
            st.sent += 1
            return True, 0.0

    def report(self, key, status=None, error=None):
        now = time.time()
        status = int(status or 0)
        with self._lock:
            st = self._get(key)
            if status in (401, 403, 429) or isinstance(error, TimeoutError):
                st.failures += 1
                # Exponential cooldown, capped at 15 minutes.
                st.blocked_until = max(
                    st.blocked_until,
                    now + min(900.0, self.cooldown * (2 ** min(st.failures, 4)))
                )
            elif 200 <= status < 400:
                st.failures = max(0, st.failures - 1)


    def reset(self):
        with self._lock:
            self._state.clear()
            self._events.clear()

    def snapshot(self):
        with self._lock:
            now = time.time()
            return {
                k: {
                    "sent_last_hour": len([t for t in self._events.get(k, []) if now-t < 3600]),
                    "failures": v.failures,
                    "cooldown": max(0.0, v.blocked_until-now),
                    "last_send": v.last_send,
                }
                for k, v in self._state.items()
            }
