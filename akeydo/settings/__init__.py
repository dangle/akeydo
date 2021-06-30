"""Utilities for managing the service configuration.

Classes:
    Settings: An object that parses a YAML configuration file and attaches all
        plug-in settings to itself.
"""

from __future__ import annotations

import logging
import pathlib

import yaml

from .dbus import DbusSettings
from .hotkey import HotkeySettings
from .. import plugins

__all__ = ("Settings",)


class Settings:
    """A class for parsing and storing configuration options for the service."""

    def __init__(self, config: pathlib.Path) -> None:
        """Parse a YAML configuration file to configure this service.

        Additionally, it loops over each plug-in and initializes the settings
        for that plug-in using the dictionary value from the given configuration
        with the same name as the plug-in.

        Args:
            config: A Path to a configuration file that contains settings for
                the service including hotkeys used for mapping keys to virtual
                machines.
        """
        data = {}
        if config.is_file():
            with open(config.resolve()) as config_file:
                data = yaml.safe_load(config_file) or {}
        self.dbus = DbusSettings.from_dict(data.get("dbus") or {})
        self.hotkeys = HotkeySettings.from_dict(data.get("hotkeys") or {})
        self.enabled_plugins = {}
        for plugin in plugins.installed_plugins:
            try:
                logging.debug('Loading plug-in "%s"', plugin.name)
                module = plugin.load()
                logging.debug('Reading settings for plug-in "%s"', plugin.name)
                settings = module.Settings.from_dict(data.get(plugin.name) or {})
                setattr(self, plugin.name, settings)
                if getattr(settings, "enabled", False):
                    logging.info('Enabling plug-in "%s"', plugin.name)
                    self.enabled_plugins[plugin.name] = module.Manager
            except Exception:
                logging.exception(
                    'An error occurred while attempting to load plug-in "%s"',
                    plugin.name,
                )
