"""Settings used for configuring the service to use D-BUS.

Classes:
    DbusSettings: Reads the D-BUS settings from a given dictionary.
"""

from ..dataclass import dataclass

__all__ = ("DbusSettings",)


@dataclass
class DbusSettings:
    """Settings for configuring the service to use D-BUS.

    Settings:
        bus_name: The D-BUS bus name to request from the D-BUS service. This
            should have the form `org.service"
        object_path:  The D-BUS object path to populate on the requested bus.
            This should have the form `/org/service/path
    """

    bus_name: str = "dev.akeydo"
    object_path: str = "/dev/akeydo"
