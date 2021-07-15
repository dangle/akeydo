from __future__ import annotations

import logging

from ....system import system


class Driver:
    _HOST_CGROUPS = (
        "init.scope",
        "user.slice",
        "system.slice",
    )

    def __init__(self, cores: int, path: str) -> None:
        self._all_cpus = frozenset(range(cores))
        self._vm_cpus = set()
        self._path = path
        system.write(f"{self._path}/cgroup.subtree_control", "+cpuset")

    def shield_cpu(self, *cpu):
        self._vm_cpus.update(cpu)
        self._set_host_cpus()

    def unshield_cpu(self, *cpu):
        self._vm_cpus.difference_update(cpu)
        self._set_host_cpus()

    def _set_host_cpus(self) -> str:
        host_cpus = (self._all_cpus - self._vm_cpus) | {0}
        logging.debug(
            "All CPUs: %r\nVM CPUs: %r\nHOST CPUs: %s",
            self._all_cpus,
            self._vm_cpus,
            host_cpus,
        )
        config = ",".join(host_cpus)
        for cgroup in self._HOST_CGROUPS:
            logging.debug(
                'Writing "%s" to %s', config, f"{self._path}/{cgroup}/cpuset.cpus"
            )
            system.write(f"{self._path}/{cgroup}/cpuset.cpus", config)
