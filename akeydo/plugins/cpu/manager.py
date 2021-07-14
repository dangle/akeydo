"""A plug-in for managing CPU shielding and frequency governors.

Classes:
    Manager: The core plug-in to be instantiated by the service.
"""

from __future__ import annotations

import functools
import importlib
import logging
import traceback

from ...system import system


class Manager:
    def __init__(self, settings: Settings, *_) -> None:
        """Initialize the plug-in.

        Args:
            settings: Global settings for hotkeys and plug-in options.
        """
        self._settings: Settings = settings
        self._shielded_vms: int = 0

    async def vm_prepare(self, _: str, config: VirtualMachineConfig) -> None:
        """Restrict kernel processes to pinned CPUs."""
        if not config.pinned_cpus:
            return
        logging.info(
            "Pinning CPUs: %s", ", ".join(str(c) for c in sorted(config.pinned_cpus))
        )
        self._driver.shield_cpu(*config.pinned_cpus)
        if not self._shielded_vms:
            system.set("/proc/sys/vm/stat_interval", 120)
            system.set("/proc/sys/kernel/watchdog", 0)
            system.set("/sys/bus/workqueue/devices/writeback/numa", 1)
        self._shielded_vms += 1

    async def vm_release(self, _: str, config: VirtualMachineConfig) -> None:
        """Remove process restrictions to CPUs used by the the virtual machine."""
        if not config.pinned_cpus:
            return
        logging.info(
            "Unpinning CPUs: %s", ", ".join(str(c) for c in sorted(config.pinned_cpus))
        )
        self._driver.unshield_cpu(*config.pinned_cpus)
        self._shielded_vms -= 1
        if not self._shielded_vms:
            system.reset("/proc/sys/vm/stat_interval")
            system.reset("/proc/sys/kernel/watchdog")
            system.reset("/sys/bus/workqueue/devices/writeback/numa")

    @functools.cache
    def _get_cgroups_mount(self):
        with open("/proc/mounts") as file:
            for line in file.readlines():
                if line.startswith("cgroup"):
                    mount_options = line.split()
                    return mount_options[0], mount_options[1]

    @functools.cached_property
    def _cpu_cores(self):
        with open("/proc/cpuinfo") as file:
            for line in file.readlines():
                if line.startswith("cpu cores"):
                    return int(line.split(":")[1].strip())

    @functools.cached_property
    def _driver(self):
        version, path = self._get_cgroups_mount()
        logging.debug('Attempting to import cgroup driver shim "%s"', version)
        try:
            module = importlib.import_module(
                f".drivers.{version}", __name__.rsplit(".", 1)[0]
            )
            return module.Driver(self._cpu_cores, path)
        except ImportError:
            logging.error("cgroups are not mounted")
            logging.debug(traceback.format_exc())
            raise RuntimeError("cgroups are not mounted")
