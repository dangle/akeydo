"""Utilities for managing dataclasses.

Decorators:
    dataclass: Converts a decorated class into a dataclass and adds a
        `from_dict` method that can be used to pass only the keys that match the
        dataclass attributes to the constructor of the dataclass.
"""

from __future__ import annotations

import dataclasses
import typing

__all__ = ("dataclass",)


T = typing.TypeVar("T")


@classmethod
def from_dict(cls: type[T], source: dict[str, Any]) -> T:
    """A method to be attached to a dataclass that instantiates from a dict.

    Args:
        source: A dictionary containing keys and values that will be used to
            initialize the dataclass. Any keys that are not valid attributes of
            the dataclass are ignored. Hyphens in keys are first converted into
            underscores.

    Returns: An instance of the dataclass.
    """
    return cls(
        **{
            attr: v
            for k, v in source.items()
            if (attr := k.replace("-", "_")) in cls.__dataclass_fields__.keys()
        }
    )


def dataclass(cls: type[T]) -> type[T]:
    """Converts a class into a dataclass and adds the `from_dict` method."""
    inner = dataclasses.dataclass(cls)
    if not hasattr(inner, "from_dict"):
        inner.from_dict = from_dict
    return inner
