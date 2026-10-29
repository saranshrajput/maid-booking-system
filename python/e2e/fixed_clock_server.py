"""Test server whose clock never moves: python e2e/fixed_clock_server.py 2030-01-08T10:07:30 8766"""
import os
import sys
from datetime import datetime
from pathlib import Path

import uvicorn

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from maidbooking.api import create_app  # noqa: E402

now, port = datetime.fromisoformat(sys.argv[1]), int(sys.argv[2])
uvicorn.run(create_app(clock=lambda: now, database_url=os.getenv("DATABASE_URL")), port=port, log_level="warning")
