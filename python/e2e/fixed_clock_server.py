"""Test server with a controllable clock.

    python e2e/fixed_clock_server.py 2030-01-08T10:07:30 8766                 # the clock never moves
    python e2e/fixed_clock_server.py 2030-01-08T10:00:00 8766 /tmp/clock.txt  # the clock is whatever the file says
"""
import os
import sys
from datetime import datetime
from pathlib import Path

import uvicorn

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from maidbooking.api import create_app  # noqa: E402

start, port = datetime.fromisoformat(sys.argv[1]), int(sys.argv[2])
clock_file = Path(sys.argv[3]) if len(sys.argv) > 3 else None


def clock() -> datetime:
    if clock_file and clock_file.exists() and clock_file.read_text().strip():
        return datetime.fromisoformat(clock_file.read_text().strip())
    return start


uvicorn.run(create_app(clock=clock, database_url=os.getenv("DATABASE_URL"), sweep_seconds=1), port=port, log_level="warning")
