"""Settings for the CPU plug-in.

Classes:
    Settings: The settings object to be appended to the global settings under
        the `cpu` attribute.
"""

from ...dataclass import dataclass


@dataclass
class Settings:
    """Settings for the CPU plug-in.

    Settings:
        enabled: Whether or not the service should instantiate this plug-in.
    """

    enabled: bool = False
