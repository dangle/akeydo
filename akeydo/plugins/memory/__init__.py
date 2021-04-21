"""Plug-in for managing memory allocation.

Classes:
    Manager: The core plug-in for managing memory.
    Settings: All settings for the plug-in that will be added to the global
        settings object.
"""

from .manager import Manager
from .settings import Settings

__all__ = (
    "Manager",
    "Settings",
)
