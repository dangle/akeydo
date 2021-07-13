from __future__ import annotations

import asyncio
import logging


class HugePageSize:
    HUGEPAGES_2M = 2048
    HUGEPAGES_1G = 1048576


class HugePages:
    _WAIT_FOR_ALLOCATION = 30

    def __init__(self, size=HugePageSize.HUGEPAGES_1G) -> None:
        self._size = size

    @property
    def allocated(self) -> int:
        with open(f"{self._base_path}/nr_hugepages") as file:
            return int(file.readlines()[0])

    @property
    def free(self) -> int:
        with open(f"{self._base_path}/free_hugepages") as file:
            return int(file.readlines()[0])

    async def allocate(self, bytes_: int) -> None:
        pages = self._get_pages(bytes_)
        self._assert_memory(pages)
        logging.info(
            "Allocating %d new hugepages of size %dkB",
            pages,
            self._size,
        )
        allocated = self.allocated
        with open(f"{self._base_path}/nr_hugepages", "w") as file:
            file.write(f"{allocated + pages}")
        await self._wait_for_allocation(allocated, pages)

    def deallocate(self, bytes_: int) -> None:
        allocated = self.allocated
        pages = self._get_pages(bytes_)
        logging.info(
            "Deallocating %d hugepages of size %dkB",
            pages,
            self._size,
        )
        with open(f"{self._base_path}/nr_hugepages", "w") as file:
            file.write(f"{max(0, allocated - pages)}")

    @property
    def _base_path(self) -> str:
        return f"/sys/kernel/mm/hugepages/hugepages-{self._size}kB"

    def _get_meminfo(self):
        with open("/proc/meminfo") as file:
            raw_meminfo = file.readlines()
        meminfo = {
            data[0]: int(data[1])
            for line in raw_meminfo
            if (data := line.replace(":", "").split())
        }
        logging.debug("Memory info: %r", meminfo)
        return meminfo

    def _get_pages(self, bytes_: int) -> int:
        mem_in_kb = bytes_ // 1024 + bytes_ // 1024 % 2
        return mem_in_kb // self._size + mem_in_kb // 1024 % 2

    def _assert_memory(self, pages: int) -> None:
        meminfo = self._get_meminfo()
        required_memory = pages * self._size
        if required_memory > meminfo["MemFree"]:
            if required_memory <= meminfo["MemAvailable"]:
                logging.warn(
                    "MemFree is insufficient to allocate %d hugepages of size %dkB."
                    " MemAvailable may not contain sufficient contiguous blocks.",
                    pages,
                    self._size,
                )
            else:
                raise IOError(
                    f"Insufficient available memory to allocate {pages} hugepages of size {self._size}kB"
                )

    async def _wait_for_allocation(self, allocated, pages):
        if self.allocated < allocated + pages:
            for _ in range(self._WAIT_FOR_ALLOCATION):
                asyncio.sleep(1)
                if self.allocated >= allocated + pages:
                    return
            raise IOError(
                f"Failed to allocate {pages} hugepages of size {self._size}kB "
                f"after {self._WAIT_FOR_ALLOCATION}s"
            )
