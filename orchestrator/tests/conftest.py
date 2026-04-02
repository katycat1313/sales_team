"""
conftest.py — pytest configuration for orchestrator tests.

Patches the tools package's browser import that tries to mkdir /app/sessions,
which doesn't exist in the CI / local test environment.
"""

import sys
import os
from unittest.mock import MagicMock, patch

# ── Pre-import patching ───────────────────────────────────────────────────────
# The tools/__init__.py does `from .browser import browser_tool` which triggers
# SESSION_DIR.mkdir(parents=True, exist_ok=True) at module level.
# We need to intercept this before any test module imports happen.

# Provide a fake browser module so `tools/__init__.py` can import safely.
_fake_browser = MagicMock()
_fake_browser.browser_tool = MagicMock()
sys.modules.setdefault("tools.browser", _fake_browser)

# Also stub playwright so browser.py doesn't fail on import if it IS loaded.
sys.modules.setdefault("playwright", MagicMock())
sys.modules.setdefault("playwright.async_api", MagicMock())

# Ensure the orchestrator directory is on sys.path.
_orchestrator_dir = os.path.join(os.path.dirname(__file__), "..")
if _orchestrator_dir not in sys.path:
    sys.path.insert(0, _orchestrator_dir)
