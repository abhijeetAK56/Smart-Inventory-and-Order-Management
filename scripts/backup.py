"""
backup.py - make a full backup of the main database with mysqldump.

    python scripts/backup.py

Creates backups/stockflow_YYYYMMDD_HHMM.sql

Options used:
    --single-transaction   consistent snapshot without locking the app (InnoDB)
    --routines --triggers  include the stored procedures and triggers (easy to forget!)
    --events               include scheduled events (none yet, but complete)
"""
import os
import shutil
import subprocess
import sys
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from dotenv import load_dotenv  # noqa: E402

load_dotenv(ROOT / ".env")
BACKUP_DIR = ROOT / "backups"


def find_tool(name):
    """Find mysqldump / mysql: first in MYSQL_BIN from .env, then on the PATH."""
    folder = os.getenv("MYSQL_BIN", "").strip()
    if folder:
        for candidate in (Path(folder) / name, Path(folder) / f"{name}.exe"):
            if candidate.exists():
                return str(candidate)
    found = shutil.which(name)
    if found is None:
        sys.exit(f"Could not find '{name}'. Put its folder in MYSQL_BIN in your .env file.")
    return found


def login_args():
    """Connection options for the MySQL command line tools."""
    return [
        f"--host={os.getenv('DB_HOST', 'localhost')}",
        f"--port={os.getenv('DB_PORT', '3306')}",
        f"--user={os.getenv('ROOT_USER', 'root')}",
        f"--password={os.getenv('ROOT_PASSWORD', '')}",
    ]


def make_backup(db_name=None):
    db_name = db_name or os.getenv("DB_NAME", "stockflow")
    BACKUP_DIR.mkdir(exist_ok=True)
    out_file = BACKUP_DIR / f"{db_name}_{datetime.now():%Y%m%d_%H%M%S}.sql"
    command = [find_tool("mysqldump"), *login_args(),
               "--single-transaction", "--routines", "--triggers", "--events",
               "--set-gtid-purged=OFF", f"--result-file={out_file}", db_name]
    subprocess.run(command, check=True)
    size_kb = out_file.stat().st_size / 1024
    print(f"Backup saved: {out_file}  ({size_kb:.0f} KB)")
    return out_file


if __name__ == "__main__":
    make_backup()
