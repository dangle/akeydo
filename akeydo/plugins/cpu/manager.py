"""A plug-in for managing CPU shielding and frequency governors.

Classes:
    Manager: The core plug-in to be instantiated by the service.
"""

from __future__ import annotations

import logging


class Manager:
    def __init__(self, settings: Settings, *_) -> None:
        """Initialize the plug-in.

        Args:
            settings: Global settings for hotkeys and plug-in options.
        """
        self._settings: Settings = settings

    async def vm_prepare(self, vm_name: str, config: VirtualMachineConfig) -> None:
        """Restrict kernel processes to pinned CPUs.

        If the "manage_cpu" option is enabled, it will set cpusets to restrict
        the kernel from adding processes to the pinned CPUs.

        Arg:
            cpu: A tuple of integers of CPUs to restrict. These should match up
                to pinned CPUs from the virtual machine XML configuration.
        """
        if not self._settings.cpu.manage or not config.pinned_cpus:
            return
        logging.info(
            "Pinning CPUs: %s", ", ".join(str(c) for c in sorted(config.pinned_cpus))
        )

    async def vm_release(self, vm_name: str, config: VirtualMachineConfig) -> None:
        """Remove process restrictions to CPUs used by the the virtual machine.

        If the "manage_cpu" option is enabled, it will set cpusets to allow
        the kernel to add processes to the CPUs that were pinned by the virtual
        machine.

        Arg:
            cpu: A tuple of integers of CPUs to allow. These should match up
                to pinned CPUs from the virtual machine XML configuration.
        """
        if not self._settings.cpu.manage or not config.pinned_cpus:
            return
        logging.info(
            "Unpinning CPUs: %s", ", ".join(str(c) for c in sorted(config.pinned_cpus))
        )
