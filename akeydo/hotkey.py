"""Definition and utility functions for managing hotkey combinations.

Types:
    Hotkey:
        An iterable that represents a hotkey combination with each value
        representing the keys as defined by the operating system.

Functions:
    parse_hotkeys: Takes an optional iterable containing string values
        representing keys and if possible returns a Hotkey.
"""

from __future__ import annotations

import logging

import evdev

__all__ = (
    "Hotkey",
    "parse_hotkeys",
)


Hotkey = frozenset[int]


def parse_hotkeys(hotkey: Optional[Iterable[str]]) -> Optional[Hotkey]:
    """Convert a list of strings representing keys to a set of int codes.

    Args:
        hotkey: An iterable containing strings of the format KEY_XXX defined
            by the Linux kernel that can be converted to the integers
            returned by keyboard presses.
            If None, the hotkey will be assumed to be an empty list and None
            will be returned.

    Returns: A frozenset containing the integers represented by the strings
        in the initial iterable. If any of the strings is unable to be
        converted into an integer a warning will be logged and None will be
        returned instead of a frozenset.
    """
    try:
        return frozenset(evdev.ecodes.ecodes[key] for key in hotkey or ()) or None
    except KeyError:
        logging.warning(
            "Unable to match all keys in hotkey %s to integers. "
            "Hotkey will be unavailable.",
            hotkey,
        )
        return None
