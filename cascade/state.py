"""
State machine for Cascade agent workers.
Writes atomic state files so any external tool can observe agent progress.
"""

import json, time, os
from enum import Enum
from pathlib import Path
from datetime import datetime

STATE_FILE = Path(".agent/worker-state.json")


class Status(Enum):
    IDLE       = "idle"
    READY      = "ready"
    PROCESSING = "processing"
    ESCALATING = "escalating"
    COMPLETE   = "complete"
    ERROR      = "error"


class WorkerState:
    def __init__(self):
        self.status    = Status.IDLE
        self.task      = ""
        self.backend   = ""
        self.iteration = 0
        self.started   = time.time()
        self._emit()

    def transition(self, status: Status, **meta):
        self.status = status
        for k, v in meta.items():
            setattr(self, k, v)
        self._emit()

    def _emit(self):
        STATE_FILE.parent.mkdir(exist_ok=True)
        data = {
            "status":     self.status.value,
            "task":       self.task,
            "backend":    self.backend,
            "iteration":  self.iteration,
            "elapsed_s":  round(time.time() - self.started, 1),
            "updated_at": datetime.now().isoformat(),
        }
        # Atomic write: temp file → rename
        tmp = STATE_FILE.with_suffix(".tmp")
        tmp.write_text(json.dumps(data, indent=2))
        tmp.rename(STATE_FILE)
