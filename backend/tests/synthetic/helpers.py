"""Wspólne dane testów nakładki syntetycznej."""

from pathlib import Path

import psycopg

from app.synthetic.importer import DOCUMENTS_PATH, import_synthetic_snapshot
from app.techqa.chunking import ChunkerConfig
from app.techqa.importer import import_snapshot
from tests.techqa.helpers import build_snapshot

# Odpowiednik dokumentu kotwicy TechQA (swg21648497) w mini-migawce testowej.
ANCHOR_DOC_ID = "swg21648497"
ANCHOR_RAW = (
    "Title: IBM Insufficient ulimit Value Causes Native OutOfMemory - United States"
    "\n\nText:\nDIAGNOSING THE PROBLEM\n\n"
    "WebSphere Application Server Support recommends setting the ulimit -u or "
    "nproc to a value of 131072 when running on Linux.\n"
)
SYNTHETIC_DOC_ID = "SYN-KB-0007"


def import_both(conn: psycopg.Connection, tmp_path: Path) -> None:
    """Mini-migawka TechQA z kotwicą oraz migawka `synthetic@v1`."""
    data_dir, manifest = build_snapshot(
        tmp_path,
        extra_entries={f"corpus/{ANCHOR_DOC_ID}.txt": ANCHOR_RAW.encode("utf-8")},
    )
    import_snapshot(conn, data_dir, manifest, ChunkerConfig())
    import_synthetic_snapshot(conn, DOCUMENTS_PATH, ChunkerConfig())
