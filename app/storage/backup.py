"""SQLite backup / restore for the local investment DB.

Usage:
  python -m app.storage.backup                 # backup to data/backups/invest-<timestamp>.db
  python -m app.storage.backup backup /tmp/b.db
  python -m app.storage.backup restore /tmp/b.db

Uses sqlite3's online backup API — safe while the app is running (no torn files).
Restore refuses non-SQLite files and never deletes the source backup.
"""
import shutil
import sqlite3
import sys
from datetime import datetime
from pathlib import Path
from typing import Optional

from app.config import settings

SQLITE_MAGIC = b"SQLite format 3\x00"


def _db_path() -> Path:
    url = settings.DATABASE_URL
    if not url.startswith("sqlite:///"):
        raise RuntimeError(f"backup only supports sqlite URLs, got: {url}")
    return Path(url[len("sqlite:///"):])


def backup(dest: Optional[str] = None) -> Path:
    """Copy the live DB to dest (default: data/backups/invest-<ts>.db)."""
    src_path = _db_path()
    if not src_path.exists():
        raise FileNotFoundError(f"database not found: {src_path}")

    if dest:
        out = Path(dest)
    else:
        out = settings.DATA_DIR / "backups" / f"invest-{datetime.now().strftime('%Y%m%d-%H%M%S')}.db"
    out.parent.mkdir(parents=True, exist_ok=True)

    src = sqlite3.connect(str(src_path))
    dst = sqlite3.connect(str(out))
    try:
        src.backup(dst)
    finally:
        dst.close()
        src.close()
    return out


def restore(src: str) -> Path:
    """Restore from a backup file into the configured DATABASE_URL path."""
    in_path = Path(src)
    if not in_path.exists():
        raise FileNotFoundError(f"backup not found: {in_path}")
    with open(in_path, "rb") as f:
        header = f.read(16)
    if header != SQLITE_MAGIC:
        raise RuntimeError(f"not a SQLite file: {in_path}")

    target = _db_path()
    target.parent.mkdir(parents=True, exist_ok=True)

    src_conn = sqlite3.connect(str(in_path))
    dst_conn = sqlite3.connect(str(target))
    try:
        src_conn.backup(dst_conn)  # overwrite target from backup
    finally:
        dst_conn.close()
        src_conn.close()
    return target


def main(argv=None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    cmd = argv[0] if argv else "backup"
    try:
        if cmd == "backup":
            out = backup(argv[1] if len(argv) > 1 else None)
            print(f"backup written: {out}")
            return 0
        if cmd == "restore":
            if len(argv) < 2:
                print("usage: python -m app.storage.backup restore <path>", file=sys.stderr)
                return 2
            target = restore(argv[1])
            print(f"restored {argv[1]} -> {target}")
            return 0
        print(__doc__, file=sys.stderr)
        return 2
    except Exception as e:
        print(f"error: {type(e).__name__}: {e}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
