"""A plug-in for managing input devices and hotkeys.

Classes:
    Manager: The core plug-in to be instantiated by the service.
"""

from __future__ import annotations

import asyncio
import os

from .input import ReplicatedDevice


class Manager:
    """A plug-in for managing devices and hotkeys.

    This service supports to pieces of functionality:

    1. Replicating source devices across the host and multiple virtual machines
       and sending events to only the currently active target.
    2. Reading hotkeys from devices that are used to send D-BUS signals.
    """

    def __init__(self, settings: Settings, service: AkeydoService) -> None:
        """Initialize the plug-in.

        Args:
            settings: Global settings for hotkeys and plug-in options.
            service: The service that initialized this plug-in.
        """
        self._settings: Settings = settings
        self._service: AkeydoService = service
        self._devices: dict[str, ReplicatedDevice] = {}

    async def vm_prepare(self, vm_name: str, config: VirtualMachineConfig) -> None:
        """Create devices requested in the virtual machine's XML configuration.

        While parsing the XML configuration for the virtual machine all input
        devices starting with "/dev/input/by-id/{vm_name}-" are extracted from
        passthrough input tags and qemu:arg tags and passed to this function.

        For each device passed to this function, vm_name is removed from the
        device to get the true source device. For each source device, a
        ReplicatedDevice is created to divert input events from either the host
        or running guests.

        If a ReplicatedDevice already exists for the source device, the virtual
        machine will be added as an additional target for device.

        Args:
            vm_name: The name of the new virtual machine. This is used to
                determine the true source device from the requested guest source
                device given.
            devices: A tuple of strings representing devices that the virtual
                machine would like to have created. They are of the form:
                    /dev/input/by-id/{vm_name}-{device-ID}
                The vm_name is removed to give a source device of the form:
                    /dev/input/by-id/{device-ID}
            host_hotkey: A hotkey that the device should monitor to switch the
                target back to the host device.
            guest_hotkey: A hotkey that the device should monitor to switch the
                target to this specific virtual machine.
        """
        for guest_source in config.devices:
            source = os.path.join(
                os.sep,
                "dev",
                "input",
                "by-id",
                os.path.basename(guest_source)[len(vm_name) + 1 :],
            )
            if source not in self._devices:
                i = 0
                while 1:
                    try:
                        self._devices[source] = ReplicatedDevice(
                            source,
                            self._service,
                            self._settings,
                            self._settings.hotkeys.host,
                        )
                        break
                    except IOError:
                        if i >= self._settings.devices.wait_duration:
                            raise
                        await asyncio.sleep(1)
                        i += 1
            device = self._devices[source]
            device.add(
                vm_name,
                config.hotkey or self._settings.hotkeys.virtual_machines.get(vm_name),
            )

    async def vm_release(self, vm_name: str, config: VirtualMachineConfig) -> None:
        """Destroy devices created for use with the virtual machine.

        While parsing the XML configuration for the virtual machine all input
        devices starting with "/dev/input/by-id/{vm_name}-" are extracted from
        passthrough input tags and qemu:arg tags and passed to this function.

        All devices used by the virtual machine and given the prefix
        "{vm_name}-" will be destroyed.

        If this is the last virtual machine managed by this service, the source
        device will be freed and the ReplicatedDevice will be deleted.

        Args:
            vm_name: The name of the virtual machine. This is used to determine
                the true source device from the requested guest source device
                given.
            devices: A tuple of strings representing devices that the virtual
                machine had created that should be destroyed. They are of the
                form:
                    /dev/input/by-id/{vm_name}-{device-ID}
                The vm_name is removed to give a source device of the form:
                    /dev/input/by-id/{device-ID}
            guest_hotkey: A hotkey that the device uses to monitor to switch the
                target to this specific virtual machine. This is necessary to
                remove it from the hotkeys monitored by the device.
        """
        for guest_source in config.devices:
            source = os.path.join(
                os.sep,
                "dev",
                "input",
                "by-id",
                os.path.basename(guest_source)[len(vm_name) + 1 :],
            )
            device = self._devices[source]
            device.remove(
                vm_name,
                config.hotkey or self._settings.hotkeys.virtual_machines.get(vm_name),
            )
            if not self._service.vm_count:
                del self._devices[source]
                del device

    async def stop(self) -> None:
        """Stop all devices in preparation for shutting down the service."""
        for device in self._devices.values():
            device.stop()

    async def target_changed(self, _: Optional[str]) -> None:
        """Ensure all devices are grabbed after the target changes."""
        for device in self._devices.values():
            device.grab()
