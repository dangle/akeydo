"""Settings for the devices plug-in.

Classes:
    Settings: The settings object to be appended to the global settings under
        the `devices` attribute.
"""

from typing import (
    FrozenSet,
)
import dataclasses

from ...dataclass import dataclass


@dataclass
class Settings:
    """Settings for the devices plug-in.

    Settings:
        enabled: Whether or not the service should instantiate this plug-in. The
            devices plug-in contains important functionality to the
            service and is enabled by default.
        by_id: A set of physical devices that should always be active and
            listening for hotkeys even if no virtual machine is currently using
            them.
        wait_duration: The number of seconds to wait until a device is ready
            before throwing an error.
    """

    enabled: bool = True
    by_id: FrozenSet[str] = dataclasses.field(default_factory=frozenset)
    wait_duration: int = 10
