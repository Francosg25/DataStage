"""Bounded, process-local report reuse with one calculation per concurrent key."""
from collections import OrderedDict
from concurrent.futures import Future
from copy import deepcopy
import json
from threading import Lock


class ReportCache:
    def __init__(self, max_entries=12, max_bytes=32 * 1024 * 1024):
        self.max_entries = max_entries
        self.max_bytes = max_bytes
        self._entries = OrderedDict()
        self._pending = {}
        self._bytes = 0
        self._lock = Lock()

    def get_or_compute(self, key, build):
        with self._lock:
            cached = self._entries.get(key)
            if cached is not None:
                self._entries.move_to_end(key)
                report = cached[0]
                pending, owner = None, False
            else:
                report = None
                pending = self._pending.get(key)
                owner = pending is None
                if owner:
                    pending = self._pending[key] = Future()
        if report is not None:
            return deepcopy(report)
        if not owner:
            return deepcopy(pending.result())
        try:
            report = build()
            size = len(json.dumps(report, ensure_ascii=False).encode('utf-8'))
        except BaseException as exc:
            with self._lock:
                self._pending.pop(key)
                pending.set_exception(exc)
            raise
        with self._lock:
            if self.max_entries > 0 and size <= self.max_bytes:
                self._entries[key] = (report, size)
                self._bytes += size
                while len(self._entries) > self.max_entries or self._bytes > self.max_bytes:
                    _, (_, removed_bytes) = self._entries.popitem(last=False)
                    self._bytes -= removed_bytes
            self._pending.pop(key)
            pending.set_result(report)
        return deepcopy(report)
