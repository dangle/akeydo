import subprocess

from .base import BaseDriver


class Driver(BaseDriver):
    _MODULES = ("amdgpu",)

    def load(self) -> None:
        for module in self._MODULES:
            subprocess.call(["modprobe", module])
        self._read_xconfig()

    def unload(self) -> None:
        for module in reversed(self._MODULES):
            subprocess.call(["rmmod", module])
