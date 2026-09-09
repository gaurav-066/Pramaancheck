# Vercel Serverless Entry Point for PramaanCheck
# Vercel detects 'app' from this file and runs it as a Python ASGI serverless function.

import sys
from pathlib import Path

# Add project root to path so 'backend.*' imports resolve correctly
sys.path.insert(0, str(Path(__file__).parent.parent))

from backend.main import app  # noqa: F401 — Vercel uses 'app' as the ASGI handler
