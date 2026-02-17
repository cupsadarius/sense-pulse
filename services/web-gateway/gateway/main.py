"""Uvicorn entry point for the Sense Pulse web gateway."""

from gateway.app import create_app

app = create_app()
