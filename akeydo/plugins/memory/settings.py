"""Settings for the memory plug-in.

Classes:
    Settings: The settings object to be appended to the global settings under
        the `memory` attribute.
"""

from ...dataclass import dataclass


@dataclass
class Settings:
    """Settings for the memory plug-in.

    Settings:
        enabled: Whether or not the service should instantiate this plug-in.
    """

    enabled: bool = False
