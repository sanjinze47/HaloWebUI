from __future__ import annotations

import contextlib
import os
import time
from pathlib import Path
from typing import BinaryIO, Iterator


def _lock_file(file: BinaryIO) -> None:
    file.seek(0)
    if os.name == "nt":
        import msvcrt

        while True:
            try:
                msvcrt.locking(file.fileno(), msvcrt.LK_NBLCK, 1)
                break
            except OSError as exc:
                if exc.errno not in {11, 13, 36} and getattr(
                    exc, "winerror", None
                ) not in {33, 36}:
                    raise
                time.sleep(0.05)
    else:
        import fcntl

        fcntl.flock(file.fileno(), fcntl.LOCK_EX)


def _unlock_file(file: BinaryIO) -> None:
    file.seek(0)
    if os.name == "nt":
        import msvcrt

        msvcrt.locking(file.fileno(), msvcrt.LK_UNLCK, 1)
    else:
        import fcntl

        fcntl.flock(file.fileno(), fcntl.LOCK_UN)


@contextlib.contextmanager
def exclusive_file_lock(path: Path) -> Iterator[None]:
    """Hold a process-wide file lock without deleting the lock file."""

    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a+b") as lock_file:
        if lock_file.seek(0, os.SEEK_END) == 0:
            lock_file.write(b"\0")
            lock_file.flush()
        _lock_file(lock_file)
        try:
            yield
        finally:
            _unlock_file(lock_file)
