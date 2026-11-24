"""Nonblocking POSIX locks for a planning output directory."""

from contextlib import contextmanager
import fcntl
import os
from pathlib import Path


@contextmanager
def output_lock(output):
    output = Path(output)
    output.parent.mkdir(parents=True, exist_ok=True)
    path = output.parent / (".event-coordination-" + output.name + ".lock")
    fd = os.open(path, os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW, 0o600)
    try:
        try:
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as exc:
            raise ValueError("Another planning operation is active for this output directory") from exc
        yield
    finally:
        os.close(fd)
