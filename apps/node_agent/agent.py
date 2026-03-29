"""Thin launcher for the Nexora node agent."""
from __future__ import annotations

from .api import app, main  # noqa: F401  # app re-exported for gunicorn/uvicorn entrypoint

if __name__ == "__main__":
    main()
