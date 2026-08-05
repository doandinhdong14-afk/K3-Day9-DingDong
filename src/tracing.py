"""Run tracing to `logging/trace.jsonl` (truncated at the start of every run).

One JSON object per line. The spec asks for the trace of the latest real run of
all 50 cases, not an append-only history, so `Tracer` opens the file in "w" mode
once and every writer appends through a lock.
"""

from __future__ import annotations

import json
import os
import threading
import time
from typing import Any, Dict, Optional


class Tracer:
    def __init__(self, path: str, run_id: str) -> None:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        self.path = path
        self.run_id = run_id
        self._lock = threading.Lock()
        self._handle = open(path, "w", encoding="utf-8")
        self._seq = 0

    def emit(
        self,
        event: str,
        case_id: Optional[str] = None,
        agent: Optional[str] = None,
        **payload: Any,
    ) -> None:
        head: Dict[str, Any] = {
            "run_id": self.run_id,
            "ts": time.strftime("%Y-%m-%dT%H:%M:%S"),
            "event": event,
        }
        if case_id:
            head["case_id"] = case_id
        if agent:
            head["agent"] = agent
        head.update(payload)
        with self._lock:
            self._seq += 1
            record = {"seq": self._seq, **head}
            self._handle.write(json.dumps(record, ensure_ascii=False, default=str) + "\n")
            self._handle.flush()

    def close(self) -> None:
        with self._lock:
            self._handle.close()

    @property
    def event_count(self) -> int:
        return self._seq
