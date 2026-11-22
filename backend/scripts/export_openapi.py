"""Zapisuje specyfikację OpenAPI do backend/openapi.json (deterministycznie)."""

import json
import sys
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BACKEND_DIR))

from app.main import app  # noqa: E402

OUTPUT = BACKEND_DIR / "openapi.json"


def main() -> None:
    text = json.dumps(app.openapi(), indent=2, sort_keys=True, ensure_ascii=False)
    with OUTPUT.open("w", encoding="utf-8", newline="\n") as f:
        f.write(text + "\n")


if __name__ == "__main__":
    main()
