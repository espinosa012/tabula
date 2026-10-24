#!/usr/bin/env python3
"""Entry point to run Tabula."""
import sys
import os
import uvicorn

# Ensure the root directory is on sys.path
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8000))
    host = os.environ.get("HOST", "127.0.0.1")
    reload = os.environ.get("RELOAD", "false").lower() in ("true", "1", "yes")

    print(f"Starting Tabula at http://{host}:{port} ...")
    uvicorn.run("backend.app.main:app", host=host, port=port, reload=reload)
