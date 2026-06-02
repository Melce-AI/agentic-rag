import os
import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

# Disable OTel tracing in tests — Phoenix is not running and the BatchSpanProcessor
# background thread causes I/O-on-closed-stream noise during process teardown.
os.environ.setdefault("OTEL_ENABLED", "false")
