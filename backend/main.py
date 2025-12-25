import logging
import sys
from pathlib import Path

import uvicorn

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

LOG = logging.getLogger("fbc-uploader")


def main() -> None:
    import os

    uvicorn.run("backend.app.main:app", host="0.0.0.0", port=8000, reload=bool(os.getenv("FBC_DEV_MODE", "0") == "1"))


if __name__ == "__main__":
    main()
