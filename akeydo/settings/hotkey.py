"""Settings for hotkeys.

Classes:
    HotkeySettings: A dataclass containing settings for hotkeys as well as the
        configuration for the default hotkeys, virtual machine-specific hotkeys,
        and hotkeys used to send arbitrary D-BUS signals.
"""

from __future__ import annotations

import collections
import dataclasses

from ..hotkey import (
    Hotkey,
    parse_hotkeys,
)
from ..dataclass import dataclass

__all__ = ("HotkeySettings",)


@dataclass
class HotkeySettings:
    """Settings for configuring hotkeys used by the service.

    Settings:
        delay: The delay to sleep after a hotkey triggers a change to the
            current target in milliseconds. This is to ensure that the hotkey
            release is sent to the current target and not the new target. The
            default value is 100ms.
        qemu: The hotkey used to grab devices in QEMU. This defaults to
            KEY_LEFTCTRL and KEY_RIGHTCTRL.
        toggle: The hotkey used to toggle between virtual machines. If left
            unspecified, it uses the QEMU hotkey.
        host: The hotkey used to switch the target to the host machine.
        release: The hotkey used to release devices to the host machine without
            changing the currently active target.
        virtual_machines: A mapping of virtual machine names to hotkeys that can
            be used to switch the target to the virtual machine with the
            matching name.
        signals: A mapping of strings to hotkeys. When a hotkey is triggered,
            a custom signal is emitted by the service with the given string.
    """

    delay: float = 100
    qemu: Hotkey = Hotkey((29, 97))
    toggle: Optional[Hotkey] = None
    host: Optional[Hotkey] = None
    release: Optional[Hotkey] = None
    virtual_machines: dict[str, Hotkey] = dataclasses.field(default_factory=dict)
    signals: dict[str, Hotkey] = dataclasses.field(default_factory=dict)

    @classmethod
    def from_dict(cls, source) -> None:
        """Recursively parse a dictionary to convert strings into Hotkeys.

        Args:
            source: The initial dictionary containing nested hotkey
                configurations.

        Returns: An instance of HotkeySettings.
        """
        instance = cls(
            **{
                k: {ki: parse_hotkeys(vi) for ki, vi in v.items()}
                if isinstance(v, dict)
                else parse_hotkeys(v)
                if isinstance(v, collections.abc.Iterable)
                else v
                for k, v in source.items()
                if k in cls.__dataclass_fields__.keys()
            }
        )
        instance.toggle = instance.toggle or instance.qemu
        return instance
