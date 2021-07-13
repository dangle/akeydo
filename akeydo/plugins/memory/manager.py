"""A plug-in for managing memory allocation.

Classes:
    Manager: The core plug-in to be instantiated by the service.
"""

from __future__ import annotations

import subprocess

from . import hugepages


class Manager:
    def __init__(self, settings: Settings, *_) -> None:
        """Initialize the plug-in.

        Args:
            settings: Global settings for hotkeys and plug-in options.
        """
        self._settings: Settings = settings

    async def vm_prepare(self, _: str, config: VirtualMachineConfig) -> None:
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
        if config.hugepages:
            self._sync()
            self._drop_caches()
            self._compact_memory()
            self._allocate(config.memory)

    async def vm_release(self, _: str, config: VirtualMachineConfig) -> None:
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
        if config.hugepages:
            self._deallocate(config.memory)

    def _allocate(self, memory: int) -> None:
        driver = self._get_hugepages_driver(memory)
        if not driver.allocate(memory):
            raise RuntimeError("Unable to allocate free pages")

    def _deallocate(self, memory: int) -> None:
        driver = self._get_hugepages_driver(memory)
        driver.deallocate(memory)

    def _get_hugepages_driver(self, memory: int) -> hugepages.HugePages:
        mem_in_kb = memory // 1024 + memory // 1024 % 2
        if mem_in_kb >= hugepages.HugePageSize.HUGEPAGES_1G:
            return hugepages.HugePages()
        return hugepages.HugePages(hugepages.HugePageSize.HUGEPAGES_2M)

    def _sync(self):
        subprocess.run(["sync"], capture_output=True)

    def _drop_caches(self):
        with open("/proc/sys/vm/drop_caches", "w") as file:
            file.write("3")

    def _compact_memory(self):
        with open("/proc/sys/vm/compact_memory", "w") as file:
            file.write("1")
