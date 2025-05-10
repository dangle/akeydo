from __future__ import annotations

import importlib
import logging
import os
import subprocess
import traceback

from .drivers.base import BaseDriver


_PCI_GPU_CLASS = 30000


class Manager:
    _VFIO_MODULES: ClassVar[tuple[str, ...]] = (
        "vfio_pci",
        "vfio",
        "vfio_iommu_type1",
        "vfio_virqfd",
    )

    def __init__(self, settings: Settings, service: AkeydoService) -> None:
        """Initialize the plug-in.

        Args:
            settings: Global settings for hotkeys and plug-in options.
            service: The service that initialized this plug-in.
        """
        self._settings: Settings = settings
        self._service: AkeydoService = service

    async def vm_prepare(self, vm_name: str, config: VirtualMachineConfig) -> None:
        for device in config.pci_devices:
            if self._is_boot_gpu(device):
                driver = self._get_driver(device)
                self._stop_display_manager()
                driver.unbind_vtcons()
                driver.unbind_framebuffer()
                self._nodedev_detach(self._get_node_devices(device, config))
                driver.unload()
                self._load_vfio(device)
            else:
                logging.debug("Setting %s as host", vm_name)
                self._service.set_host(vm_name)
                return

    async def vm_release(self, _: str, config: VirtualMachineConfig) -> None:
        for device in config.pci_devices:
            if self._is_boot_gpu(device):
                self._nodedev_reattach(self._get_node_devices(device, config))
                driver = self._get_driver(device)
                driver.load()
                driver.bind_vtcons()
                driver.bind_framebuffer()
                self._start_display_manager()
                self._service.set_host()
                return

    def _get_uevent(self, device):
        device_name = f"{device[0]:04x}:{device[1]:02x}:{device[2]:02x}.{device[3]:01x}"
        path = f"/sys/bus/pci/devices/{device_name}/uevent"
        with open(path) as file:
            return {
                data[0].strip(): data[1].strip()
                for line in file.readlines()
                if (data := line.split("="))
            }

    def _load_vfio(self, device):
        logging.debug("Loading vfio-pci")
        for module in self._VFIO_MODULES:
            subprocess.call(["modprobe", module])

    def _unload_vfio(self, device):
        for module in reversed(self._VFIO_MODULES):
            subprocess.call(["rmmod", module])

    def _get_driver(self, device):
        uevent = self._get_uevent(device)
        if 'DRIVER' not in uevent:
            return BaseDriver()
        try:
            logging.debug('Attempting to import driver shim "%s"', uevent.get("DRIVER", "Unknown"))
            module = importlib.import_module(
                f".drivers.{uevent.get('DRIVER', "")}", __name__.rsplit(".", 1)[0]
            )
            return module.Driver()
        except:
            logging.warning("Unable to find drivers for passthrough video card")
            logging.debug(traceback.format_exc())
            return BaseDriver()

    def _is_gpu(self, device):
        is_gpu = self._get_uevent(device).get("PCI_CLASS") == _PCI_GPU_CLASS
        logging.debug("Device %r is GPU: %r", device, is_gpu)
        return is_gpu

    def _is_boot_gpu(self, device) -> bool:
        device_name = f"{device[0]:04x}:{device[1]:02x}:{device[2]:02x}.{device[3]:01x}"
        path = f"/sys/bus/pci/devices/{device_name}/boot_vga"
        if os.path.isfile(path):
            with open(path) as file:
                is_boot_gpu = bool(int(file.read(1)))
                is_boot_gpu_format = "" if is_boot_gpu else " not"
                logging.debug(f"Device %s is{is_boot_gpu_format} boot GPU", device_name)
                return is_boot_gpu
        return False

    def _get_node_devices(self, device, config: VirtualMachineConfig):
        all_devices = subprocess.run(
            ["virsh", "nodedev-list"], capture_output=True, text=True
        ).stdout.split()
        prefix = f"pci_{device[0]:04x}_{device[1]:02x}_{device[2]:02x}_"
        devices = [
            d
            for d in all_devices
            if d.startswith(prefix)
            and tuple(int(component, base=16) for component in d.split("_")[1:])
            in config.pci_devices
        ]
        logging.debug(f"Matching virsh devices: {devices}")
        return devices

    def _nodedev_detach(self, node_devices):
        logging.debug("Detaching nodedev devices")
        for device in node_devices:
            logging.debug("Detaching device %r", device)
            subprocess.call(["virsh", "nodedev-detach", device])

    def _nodedev_reattach(self, node_devices):
        logging.debug("Reattaching nodedev devices")
        for device in reversed(node_devices):
            logging.debug("Reattaching device %s", device)
            subprocess.call(["virsh", "nodedev-reattach", device])

    def _stop_display_manager(self):
        logging.debug("Stopping the display manager")
        try:
            subprocess.call(["systemctl", "stop", "display-manager"])
            subprocess.call(["killall", "gdm-x-session"])
            subprocess.call(["killall", "gdm-wayland-session"])
        except FileNotFoundError:
            logging.debug("Not able to call systemctl")

    def _start_display_manager(self):
        logging.debug("Starting the display manager")
        try:
            subprocess.call(["systemctl", "start", "display-manager"])
        except FileNotFoundError:
            logging.debug("Not able to call systemctl")
