from __future__ import annotations

import json
from pathlib import Path
from threading import RLock
from typing import Any


class JsonStore:
    def __init__(self, path: Path, default_factory):
        self.path = path
        self.default_factory = default_factory
        self._lock = RLock()
        self.path.parent.mkdir(parents=True, exist_ok=True)
        if not self.path.exists():
            self.write(self.default_factory())

    def read(self) -> Any:
        with self._lock:
            if not self.path.exists():
                return self.default_factory()
            with self.path.open("r", encoding="utf-8") as handle:
                return json.load(handle)

    def write(self, payload: Any) -> None:
        with self._lock:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            with self.path.open("w", encoding="utf-8") as handle:
                json.dump(payload, handle, ensure_ascii=False, indent=2)

    def update(self, mutator):
        with self._lock:
            payload = self.read()
            next_payload = mutator(payload)
            self.write(next_payload)
            return next_payload
