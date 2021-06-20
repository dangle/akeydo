"""A plug-in for managing memory allocation.

Classes:
    Manager: The core plug-in to be instantiated by the service.
"""

from __future__ import annotations

import logging
import subprocess


class Manager:
    def __init__(self, settings: Settings, *_) -> None:
        """Initialize the plug-in.

        Args:
            settings: Global settings for hotkeys and plug-in options.
        """
        self._settings: Settings = settings

    def vm_prepare(self, _: str, config: VirtualMachineConfig) -> None:
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
        if not config.hugepages_1g and not config.hugepages_2m:
            return
        pre_meminfo = self._get_meminfo()
        hugepagesz = 1048576
        hugepages = config.hugepages_2m if hugepagesz == 2048 else config.hugepages_1g
        free_hugepages = pre_meminfo["HugePages_Free"]
        if free_hugepages >= hugepages:
            return True
        logging.info(
            "Allocating %d new hugepages of size %dkB",
            hugepages,
            hugepagesz,
        )
        total_hugepages = pre_meminfo["HugePages_Total"]
        self._compact()
        with open(
            f"/sys/kernel/mm/hugepages/hugepages-{hugepagesz}kB/nr_hugepages",
            "w",
        ) as file:
            file.write(f"{total_hugepages + hugepages}")
        # post_meminfo = self._get_meminfo()
        # post_free_hugepages = post_meminfo["HugePages_Free"]
        # if post_free_hugepages >= hugepages:
        #     return True
        # logging.error("Unable to allocate sufficient hugepages")
        # logging.debug(
        #     "Expected at least %d free hugepages, but found %d",
        #     hugepages,
        #     post_free_hugepages,
        # )

    def vm_release(self, _: str, config: VirtualMachineConfig) -> None:
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
        if not config.hugepages_1g and not config.hugepages_2m:
            return
        pre_meminfo = self._get_meminfo()
        hugepagesz = 1048576  # TODO: FIX HACK
        hugepages = config.hugepages_2m if hugepagesz == 2048 else config.hugepages_1g
        logging.info(
            "Deallocating %d hugepages of size %dkB",
            hugepages,
            hugepagesz,
        )
        total_hugepages = pre_meminfo["HugePages_Total"]
        with open(
            f"/sys/kernel/mm/hugepages/hugepages-{hugepagesz}kB/nr_hugepages",
            "w",
        ) as file:
            file.write(f"{total_hugepages - hugepages}")

    def _get_meminfo(self):
        with open("/proc/meminfo") as file:
            raw_meminfo = file.readlines()
        meminfo = {
            data[0]: int(data[1])
            for line in raw_meminfo
            if (data := line.replace(":", "").split())
        }
        # TODO: FIX HACK
        with open("/sys/kernel/mm/hugepages/hugepages-1048576kB/nr_hugepages") as file:
            val = file.readlines()
            meminfo["HugePages_Total"] = int(val[0])
        logging.debug("Memory info: %r", meminfo)
        return meminfo

    def _compact(self):
        subprocess.run(["sync"], capture_output=True)
        with open("/proc/sys/vm/drop_caches", "w") as file:
            file.write("3")
        with open("/proc/sys/vm/compact_memory", "w") as file:
            file.write("1")
