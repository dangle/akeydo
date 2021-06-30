"""Plug-in for handling passing through of the boot video card.

Classes:
    Manager: The core plug-in for managing GPU passthrough.
    Settings: All settings for the plug-in that will be added to the global
        settings object.
"""


from .manager import Manager
from .settings import Settings

__all__ = (
    "Manager",
    "Settings",
)
