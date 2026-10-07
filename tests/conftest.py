import os
import tempfile

os.environ.setdefault("AUTH_REQUIRED", "false")
os.environ.setdefault("THAMUN_SECRET", "test-secret-not-for-production-0123456789")
os.environ.setdefault("THAMUN_DB_PATH", os.path.join(tempfile.mkdtemp(prefix="thamun-test-"), "test.db"))
os.environ.setdefault("RATE_LIMIT_PER_MINUTE", "100000")
os.environ.setdefault("AUTH_LIMIT_PER_MINUTE", "100000")
os.environ.pop("DATABASE_URL", None)
