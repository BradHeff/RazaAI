from __future__ import annotations

import signal
import threading
from contextlib import contextmanager


class ToolDeadlineExceeded(BaseException):
    """Raised by the execution authority when a model/tool call exceeds its deadline."""


@contextmanager
def tool_deadline(seconds):
    """Enforce a wall-clock deadline on the normal POSIX main-thread tool path."""
    seconds = max(1, int(seconds or 1))
    supported = (
        hasattr(signal, "SIGALRM")
        and hasattr(signal, "setitimer")
        and threading.current_thread() is threading.main_thread()
    )
    if not supported:
        yield False
        return

    previous_handler = signal.getsignal(signal.SIGALRM)
    previous_timer = signal.getitimer(signal.ITIMER_REAL)

    def _expire(signum, frame):  # noqa: ARG001
        raise ToolDeadlineExceeded()

    signal.signal(signal.SIGALRM, _expire)
    signal.setitimer(signal.ITIMER_REAL, float(seconds))
    try:
        yield True
    finally:
        signal.setitimer(signal.ITIMER_REAL, 0.0)
        signal.signal(signal.SIGALRM, previous_handler)
        if previous_timer[0] > 0:
            signal.setitimer(signal.ITIMER_REAL, previous_timer[0], previous_timer[1])
