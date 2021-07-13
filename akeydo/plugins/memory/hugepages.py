from __future__ import annotations

import asyncio
import logging


class HugePageSize:
    HUGEPAGES_2M = 2048
    HUGEPAGES_1G = 1048576


class HugePages:
    def __init__(self, size=HugePageSize.HUGEPAGES_1G, use_available=False) -> None:
        self._size = size
        self._use_available = use_available

    @property
    def allocated(self) -> int:
        with open(f"{self._base_path}/nr_hugepages") as file:
            return int(file.readlines()[0])

    @property
    def free(self) -> int:
        with open(f"{self._base_path}/free_hugepages") as file:
            return int(file.readlines()[0])

    async def allocate(self, bytes_: int) -> None:
        meminfo = self._get_meminfo()
        free_memory = meminfo["MemAvailable" if self._use_available else "MemFree"]
        pages = self._get_pages(bytes_)
        if pages * self._size > free_memory:
            logging.debug(
                "Insufficient free memory to allocate %d hugepages of size %dkB",
                pages,
                self._size,
            )
            raise IOError(
                f"Insufficient free memory to allocate {pages} hugepages of size {self._size}kB"
            )
        logging.info(
            "Allocating %d new hugepages of size %dkB",
            pages,
            self._size,
        )
        allocated = self.allocated
        with open(f"{self._base_path}/nr_hugepages", "w") as file:
            file.write(f"{allocated + pages}")
        for _ in range(30):
            if self.allocated >= allocated + pages:
                return
            asyncio.sleep(1)
        raise IOError(f"Failed to allocate {pages} hugepages of size {self._size}kB")

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
