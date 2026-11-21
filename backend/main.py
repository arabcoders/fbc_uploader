import argparse
import logging
import os
import sys
from collections.abc import Sequence
from pathlib import Path

import uvicorn

ROOT: Path = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

LOG: logging.Logger = logging.getLogger("fbc-uploader")


def main(argv: Sequence[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description="Start FBC Uploader", allow_abbrev=False)
    parser.add_argument(
        "--no-auto-migration",
        action="store_true",
        help="Prevent automatic upgrades of initialized databases; new databases are still initialized",
    )
    if parser.parse_args(argv).no_auto_migration:
        # Uvicorn's reload subprocess imports the app separately.
        os.environ["FBC_NO_AUTO_MIGRATION"] = "1"

    uvicorn.run(
        "backend.app.main:app",
        host="0.0.0.0",
        port=8000,
        reload=bool(os.getenv("FBC_DEV_MODE", "0") == "1"),
        proxy_headers=False,
        server_header=False,
    )


if __name__ == "__main__":
    main()
