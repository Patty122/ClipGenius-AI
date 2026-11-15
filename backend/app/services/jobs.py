"""Background job execution. One worker (CPU-only student machines); inline mode for deterministic tests."""
from concurrent.futures import ThreadPoolExecutor
from ..config import get_settings
from ..utils.logger import get_logger

log = get_logger("jobs")
_pool = ThreadPoolExecutor(max_workers=1, thread_name_prefix="clipgenius-job")


def submit(fn, *args, **kwargs):
    if get_settings().sync_jobs:
        try:
            fn(*args, **kwargs)
        except Exception:
            log.exception("job failed (inline)")
        return None

    def wrapped():
        try:
            fn(*args, **kwargs)
        except Exception:
            log.exception("job failed")
    return _pool.submit(wrapped)
