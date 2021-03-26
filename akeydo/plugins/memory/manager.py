"""A plug-in for managing memory allocation.

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

    def vm_prepare(self, vm_name: str, config: VirtualMachineConfig) -> None:
        """Allocate memory for hugepages.

        If the "manage_hugepages" option is enabled and the virtual machine XML
        specifies "<hugepages/>" it will try to free up sufficient memory and
        dynamically allocate enough hugepages for the virtual machine.

        Args:
            gb_pages: The number of 1GB hugepages to allocate. This should be
                calculated by dividing the memory requested for the virtual
                machine into 1GB chunks.
            mb_pages: The number of 2MB hugepages to allocate. This should be
                calculated by taking the remainder of the memory requested for
                the virtual machine after dividing it into 1GB chunks and then
                dividing that into 2MB chunks.
        """
        if not self._settings.memory.manage or (
            not config.hugepages_1g and not config.hugepages_2m
        ):
            return
        logging.info(
            "Allocating %d 1G hugepages or %d 2M hugepages",
            config.hugepages_1g,
            config.hugepages_2m,
        )

    def vm_release(self, vm_name: str, config: VirtualMachineConfig) -> None:
        """Deallocate memory used for hugepages by the virtual machine.

        If the "manage_hugepages" option is enabled and the virtual machine XML
        specifies "<hugepages/>" it will try to free any hugepages used by the
        virtual machine.

        Args:
            gb_pages: The number of 1GB hugepages to deallocate. This should be
                calculated by dividing the memory requested for the virtual
                machine into 1GB chunks.
            mb_pages: The number of 2MB hugepages to deallocate. This should be
                calculated by taking the remainder of the memory requested for
                the virtual machine after dividing it into 1GB chunks and then
                dividing that into 2MB chunks.
        """
        if not self._settings.memory.manage or (
            not config.hugepages_1g and not config.hugepages_2m
        ):
            return
        logging.info(
            "Deallocating %d 1G hugepages or %d 2M hugepages",
            config.hugepages_1g,
            config.hugepages_2m,
        )
