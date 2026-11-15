import re
import shutil
import uuid
from pathlib import Path

_SAFE = re.compile(r"[^A-Za-z0-9._-]+")

def safe_filename(name: str, default: str = "upload") -> str:
    """Strip directories and unsafe characters; never returns an empty / dot-only name."""
    base = Path(name.replace("\\", "/")).name
    base = _SAFE.sub("_", base).strip("._") or default
    return base[:120]

def new_id(prefix: str = "") -> str:
    return prefix + uuid.uuid4().hex[:12]

def ensure_within(base: Path, candidate: Path) -> Path:
    """Resolve `candidate` and make sure it stays inside `base` (path-traversal guard)."""
    base_r, cand_r = base.resolve(), candidate.resolve()
    if base_r != cand_r and base_r not in cand_r.parents:
        raise ValueError("Path escapes allowed directory")
    return cand_r

def rmtree_quiet(p: Path) -> None:
    shutil.rmtree(p, ignore_errors=True)
