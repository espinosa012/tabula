import os

# FastAPI's TestClient sends "Host: testserver"; allow it through LocalRequestGuard.
os.environ.setdefault("ALLOWED_HOSTS", "testserver")
