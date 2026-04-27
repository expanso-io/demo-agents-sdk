"""Shared pytest fixtures.

Sets fake API keys before any classifier script is imported, since each
script's `client = OpenAI()` (etc.) constructor runs at import time and reads
the env. We also expose `scripts/` on sys.path so tests can import the three
classifier modules directly.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

ROOT = Path(__file__).parent.parent
SCRIPTS_DIR = ROOT / "scripts"

# Set fake keys before any test (or test collection) imports a classifier.
os.environ.setdefault("OPENAI_API_KEY", "test-openai")
os.environ.setdefault("ANTHROPIC_API_KEY", "test-anthropic")
os.environ.setdefault("GEMINI_API_KEY", "test-gemini")

# Make scripts/ importable.
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))
