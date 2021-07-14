from ....system import system


class Driver:
    _HOST_CGROUPS = (
        "init.scope",
        "user.slice",
        "system.slice",
    )

    def __init__(self, cores: int, path: str) -> None:
        self._all_cpus = set(range(self.cores))
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
        host_cpus = self._all_cpus - self._vm_cpus
        config = ",".join(host_cpus)
        for cgroup in self._HOST_CGROUPS:
            system.write(f"{self._path}/{cgroup}/cpuset.cpus", config)
