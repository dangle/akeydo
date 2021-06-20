import subprocess

from .base import BaseDriver


class Driver(BaseDriver):
    _MODULES = ("amdgpu",)

    def load(self):
        for module in self._MODULES:
            subprocess.call(["modprobe", module])
        self._read_xconfig()

    def unload(self):
        for module in reversed(self._MODULES):
            subprocess.call(["rmmod", module])
