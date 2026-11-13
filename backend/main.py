"""Deprecated entry point kept so `uvicorn backend.main:app` still works; use `python -m godseye api`."""
from godseye.api.app import app  # noqa: F401
