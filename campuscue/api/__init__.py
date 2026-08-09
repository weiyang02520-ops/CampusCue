"""HTTP layer for the CampusCue task board."""

from campuscue.api.events import hub
from campuscue.api.routes import router

__all__ = ["hub", "router"]
