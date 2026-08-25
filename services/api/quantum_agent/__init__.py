"""Quantum Agent backend primitives.

The package intentionally exposes database infrastructure without importing an
application object.  This keeps migrations, ingestion workers, and API workers
free to configure their own process lifecycle.
"""

from quantum_agent.config import Settings, get_settings

__all__ = ["Settings", "get_settings"]
