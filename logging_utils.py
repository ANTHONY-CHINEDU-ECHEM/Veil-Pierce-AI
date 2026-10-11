"""Small logging and timing helpers shared by every stage of the pipeline."""

from __future__ import annotations

import logging
import time
from contextlib import contextmanager

_FORMAT = "%(asctime)s %(levelname)s %(name)s %(message)s"


def get_logger(name: str = "veilpierce") -> logging.Logger:
    """Return a configured logger. Handlers are attached only once."""
    logger = logging.getLogger(name)
    root = logging.getLogger("veilpierce")
    if not root.handlers:
        handler = logging.StreamHandler()
        handler.setFormatter(logging.Formatter(_FORMAT, datefmt="%H:%M:%S"))
        root.addHandler(handler)
        root.setLevel(logging.INFO)
        root.propagate = False
    return logger


class StageTimer:
    """Collects wall clock seconds per named stage so runs can be audited."""

    def __init__(self) -> None:
        self.seconds: dict[str, float] = {}

    @contextmanager
    def stage(self, name: str):
        log = get_logger()
        start = time.perf_counter()
        log.info("stage start: %s", name)
        try:
            yield
        finally:
            elapsed = time.perf_counter() - start
            self.seconds[name] = round(self.seconds.get(name, 0.0) + elapsed, 3)
            log.info("stage done: %s (%.1f s)", name, elapsed)

    def total(self) -> float:
        return round(sum(self.seconds.values()), 3)
