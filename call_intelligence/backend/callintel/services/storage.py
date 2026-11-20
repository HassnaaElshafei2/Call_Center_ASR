"""Recordings on disk (a mounted volume in Docker). Paths are always inside storage_dir."""
import os
import re
from pathlib import Path

from ..config import settings

AUDIO_EXT = {".wav", ".mp3", ".m4a", ".ogg", ".flac", ".opus", ".webm", ".aac", ".wma", ".amr"}


def root() -> Path:
    p = Path(settings().storage_dir).resolve()
    p.mkdir(parents=True, exist_ok=True)
    return p


def safe_name(name: str) -> str:
    base = os.path.basename(name or "recording")
    return re.sub(r"[^\w.\-]+", "_", base)[:150] or "recording"


def path_for(enterprise: str, call_id: str, filename: str) -> Path:
    d = root() / enterprise / call_id[:2]
    d.mkdir(parents=True, exist_ok=True)
    return d / f"{call_id}_{safe_name(filename)}"


def resolve(stored: str) -> Path | None:
    """A stored path back to a file, refusing anything outside the storage root."""
    if not stored:
        return None
    p = (root() / stored).resolve()
    return p if str(p).startswith(str(root())) and p.is_file() else None


def relative(p: Path) -> str:
    return str(p.resolve().relative_to(root()))
