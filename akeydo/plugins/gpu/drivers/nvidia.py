import os
import subprocess

from .base import BaseDriver


class Driver(BaseDriver):
    _MODULES = (
        "nvidia",
        "nvidia_modeset",
        "nvidia_drm",
        "nvidia_uvm",
    )

    def load(self) -> None:
        for module in self._MODULES:
            subprocess.call(["modprobe", module])
        self._read_xconfig()

    def unload(self) -> None:
        for module in reversed(self._MODULES):
            subprocess.call(["rmmod", module])

    def _read_xconfig(self) -> None:
        if os.path.isfile("/usr/bin/nvidia-xconfig"):
            subprocess.run(
                ["/usr/bin/nvidia-xconfig", "--query-gpu-info"],
                capture_output=True,
            )
