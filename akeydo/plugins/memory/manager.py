"""A plug-in for managing memory allocation.

Classes:
    Manager: The core plug-in to be instantiated by the service.
"""

from __future__ import annotations

import subprocess

from . import hugepages


class Manager:
    _TH_MADVISE = "madvise"
    _TH_NEVER = "never"

    def __init__(self, settings: Settings, *_) -> None:
        """Initialize the plug-in.

        Args:
            settings: Global settings for hotkeys and plug-in options.
        """
        self._settings: Settings = settings
        self._vms_with_hugepages = 0
        self._transparent_hugepages = self._TH_MADVISE

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
            await self._allocate(config.memory)
            if not self._vms_with_hugepages:
                self._disable_transparent_hugepages()
            self._vms_with_hugepages += 1

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
            self._vms_with_hugepages -= 1
            if not self._vms_with_hugepages:
                self._reset_transparent_hugepages()

    async def _allocate(self, memory: int) -> None:
        driver = self._get_hugepages_driver(memory)
        await driver.allocate(memory)

    def _deallocate(self, memory: int) -> None:
        driver = self._get_hugepages_driver(memory)
        driver.deallocate(memory)

    def _get_hugepages_driver(self, memory: int) -> hugepages.HugePages:
        mem_in_kb = memory // 1024 + memory // 1024 % 2
        if mem_in_kb >= hugepages.HugePageSize.HUGEPAGES_1G:
            return hugepages.HugePages()
        return hugepages.HugePages(
            hugepages.HugePageSize.HUGEPAGES_2M, self._settings.memory.wait_duration
        )

    def _sync(self) -> None:
        subprocess.run(["sync"], capture_output=True)

    def _drop_caches(self) -> None:
        with open("/proc/sys/vm/drop_caches", "w") as file:
            file.write("3")

    def _compact_memory(self) -> None:
        with open("/proc/sys/vm/compact_memory", "w") as file:
            file.write("1")

    def _disable_transparent_hugepages(self):
        self._transparent_hugepages = self._get_current_transparent_hugepages()
        with open("/sys/kernel/mm/transparent_hugepage/enabled", "w") as file:
            file.write(self._TH_NEVER)

    def _reset_transparent_hugepages(self):
        if self._transparent_hugepages != self._TH_NEVER:
            with open("/sys/kernel/mm/transparent_hugepage/enabled", "w") as file:
                file.write(self._transparent_hugepages)

    def _get_current_transparent_hugepages(self):
        with open("/sys/kernel/mm/transparent_hugepage/enabled") as file:
            status = file.readlines()[0]
        for s in status.split():
            if s.startswith("["):
                return s.replace("[", "").replace("]", "")
        return self._TH_MADVISE
