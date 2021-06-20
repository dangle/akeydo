"""Utilities for sharing a physical device across the host and multiple VMs.

Classes:
    ReplicatedDevice: Manages a real system device and creates virtual devices
        that can receive input only when a specific virtual machine (or the
        host) has focus.
"""

from __future__ import annotations

from typing import (
    Dict,
    Optional,
    Union,
    cast,
)
import asyncio
import functools
import logging
import os
import stat
import threading

import evdev

from ...hotkey import Hotkey
from ...task import create_task, handle_exception

__all__ = ("ReplicatedDevice",)


class ReplicatedDevice:
    """A device manager for redirecting device events.

    This takes a real source device and creates virtual devices for every
    virtual machine that requests the source device. Events from the source
    device are captured, monitored for configured hotkeys, and events are
    forwarded to the currently active target.
    """

    HOST = None

    def __init__(
        self,
        source: str,
        manager: AkeydoService,
        settings: Settings,
        host_hotkey: Optional[Hotkey] = None,
    ) -> None:
        """Initialize a new device to be monitored and replicated.

        Args:
            source: The path to the source device that all virtual devices will
                replicate.
            manager: The service managing all of the ReplicatedDevices. This is
                used in order to read the current target.
            settings: Global settings for hotkeys and plug-in options.
            host_hotkey: An optional hotkey that will cause an immediate switch
                to the host device.
        """
        if not os.path.exists(source) or not stat.S_ISCHR(os.stat(source).st_mode):
            raise IOError(f"No such device: {source}")
        self._settings: Settings = settings
        self._source_path: str = source
        self._source: Optional[evdev.InputDevice] = None
        self._manager: AkeydoService = manager
        self._targets: Dict[Union[bool, None, str], evdev.InputDevice] = {}
        self._hotkeys: Dict[Hotkey, Optional[str]] = {}
        self._grab_task: Optional[asyncio.Task] = None
        self._replicate_task: Optional[asyncio.Task] = None
        if host_hotkey:
            self._hotkeys[host_hotkey] = self.HOST

    @functools.cached_property
    def _name(self):
        """Return the base name of the device."""
        return os.path.basename(self._source_path)

    def _get_device_path(self, target: str) -> str:
        """Get the device path of the virtual device for the target.

        Args:
            target: The name of the target virtual machine or "host" for the the
                device created for the host.

        Returns: The path to the virtual device on the file system.
        """
        return os.path.join(
            os.sep,
            "dev",
            "input",
            "by-id",
            f"{target}-{self._name}",
        )

    def _create_device(
        self, target: str, *, key: Union[bool, None, str] = False
    ) -> None:
        """Create a new UInput device from the source device.

        Args:
            target: The name of the target to be used as a prefix for the newly
                created device. For virtual machines this should be the name of
                the virtual machine. For the host device it should be "host".
            key: The key used to store the device in the target map. For virtual
                machines, this should be the name of the virtual machine. For
                the host device it should be None.
                The default value of the key is False. If the key is False, it
                will use the name of the virtual machine. This acts as a
                sentinel so that None can be used as a key for the host.
        """
        path = self._get_device_path(target)
        logging.info("Creating %s device %s", target, path)
        device = evdev.UInput.from_device(self._source)
        self._targets[key if key is not False else target] = device
        try:
            if os.path.islink(path):
                logging.debug("Removing existing symlink %s", path)
                os.unlink(path)
        except IOError:
            pass
        os.symlink(device.device, path)

    def _destroy_device(
        self, target: str, *, key: Union[bool, None, str] = False
    ) -> None:
        """Destroy the device created for the target.

        Args:
            target: The name of the target used as a prefix for the newly
                device. For virtual machines this should be the name of the
                virtual machine. For the host device it should be "host".
            key: The key used to store the device in the target map. For virtual
                machines, this should be the name of the virtual machine. For
                the host device it should be None.
                The default value of the key is False. If the key is False, it
                will use the name of the virtual machine. This acts as a
                sentinel so that None can be used as a key for the host.
        """
        index = key if key is not False else target
        if index not in self._targets:
            return
        path = self._get_device_path(target)
        logging.info("Destroying %s device %s", target, path)
        try:
            if os.path.islink(path):
                logging.debug("Removing symlink %s", path)
                os.unlink(path)
        except IOError:
            pass
        try:
            self._targets.pop(index).close()
        except IOError:
            pass

    async def _grab_source(self) -> None:
        """Grab the source device if it is ungrabbed.

        This task grabs the source device if it is ungrabbed and attempts to
        re-grab it every ten seconds in case the device was disconnected.
        """
        try:
            while 1:
                try:
                    if self._source:
                        self._source.grab()
                        logging.debug("Grabbed source device %s", self._source.path)
                except IOError:
                    pass
                await asyncio.sleep(10)
        except asyncio.CancelledError:
            self._grab_task = None

    @property
    def _target(self) -> Optional[evdev.device.InputDevice]:
        """Get the device for the currently active target."""
        target = self._targets.get(self._manager.target)
        logging.trace(
            "Current target for device %s is %s", self._name, self._manager.target
        )
        return target

    @functools.cached_property
    def _delay(self) -> float:
        """The delay to wait between switching targets in seconds."""
        return self._settings.hotkeys.delay / 1000.0

    async def _replicate(self) -> None:
        """Listen to the source for hotkeys and pass events to the target.

        This listens for three types of events:

        1. Release events. If the release hotkey is detected, the "released"
           value for the manager is toggled.
        2. Toggle events. If the toggle hotkey is detected, the "toggle" method
           on the manager is called.
        3. VM hotkey events. If a key combination in the hotkeys map is
           detected then the target on the manager will be set to the value
           associated with the hotkey.

        All other events are forwarded to the current target if the device has
        a mapping for the current target.
        """
        try:
            if not self._source:
                return

            source = self._source

            is_release = False

            async def handle_release(
                event: evdev.InputEvent, active_keys: Hotkey
            ) -> None:
                """Detect the release hotkey and trigger a device release.

                Args:
                    event: The current device input.
                    active_keys: The set of currently pressed keys.
                """
                nonlocal is_release
                if event.value == 1 and active_keys == self._settings.hotkeys.release:
                    is_release = True
                elif self._target and is_release and not source.active_keys():
                    self._target.syn()
                    await asyncio.sleep(self._delay)
                    is_release = False
                    self._manager.released = not self._manager.released

            is_toggle = False

            async def handle_toggle(
                event: evdev.InputEvent, active_keys: Hotkey
            ) -> None:
                """Detect the toggle hotkey and toggle the currently active target.

                Args:
                    event: The current device input.
                    active_keys: The set of currently pressed keys.
                """
                nonlocal is_toggle
                if event.value == 1 and active_keys == self._settings.hotkeys.toggle:
                    is_toggle = True
                elif self._target and is_toggle and not source.active_keys():
                    self._target.syn()
                    await asyncio.sleep(self._delay)
                    is_toggle = False
                    self._manager.toggle()

            hotkey_triggered: Optional[Hotkey] = None

            async def handle_hotkeys(
                event: evdev.InputEvent, active_keys: Hotkey
            ) -> None:
                """Detect VM hotkeys and toggle to specific virtual machines.

                Args:
                    event: The current device input.
                    active_keys: The set of currently pressed keys.
                """
                nonlocal hotkey_triggered
                if event.value == 1 and active_keys in self._hotkeys:
                    hotkey_triggered = active_keys
                elif self._target and hotkey_triggered and not source.active_keys():
                    self._target.syn()
                    await asyncio.sleep(self._delay)
                    self._manager.target = self._hotkeys[hotkey_triggered]
                    hotkey_triggered = None

            async for event in source.async_read_loop():
                if self._target:
                    self._target.write_event(event)
                    if event.type == evdev.ecodes.EV_KEY:
                        active_keys = frozenset(source.active_keys())
                        await asyncio.gather(
                            *(
                                f(event, active_keys)
                                for f in (handle_release, handle_toggle, handle_hotkeys)
                            )
                        )
        except asyncio.CancelledError:
            self._replicate_task = None

    def grab(self) -> None:
        """Send the QEMU hotkey to a VM to force it to grab devices."""
        if not self._manager.target or not self._target:
            return
        try:
            self._target.device.grab()
            self._target.device.ungrab()
        except IOError:
            return
        logging.debug("Grabbing device %s", self._get_device_path(self._manager.target))
        for value in (1, 0):
            for key in self._settings.hotkeys.qemu or ():
                self._target.write(evdev.ecodes.EV_KEY, key, value)
        self._target.syn()

    def start(self) -> None:
        """Create source devices and tasks for grabbing and replicating.

        If the source is not currently being monitored by this device it will
        grab the device and create a "host" device to forward events to by
        default.

        If no grab task is currently running it will create a new grab task for
        device.

        If no replicate task is currently running it will create a new replicate
        task for the device.

        These tasks are started in a separate thread to minimize potential
        processing lag.
        """
        if not self._source:
            self._source = evdev.InputDevice(self._source_path)
            self._create_device("host", key=self.HOST)

        def create_tasks():
            """Create the new tasks in a separate event loop."""
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            self._grab_task = create_task(
                self._grab_source(), name=f"Grab: {self._name}"
            )
            self._replicate_task = create_task(
                self._replicate(), name=f"Replicate: {self._name}"
            )
            try:
                task = asyncio.gather(self._grab_task, self._replicate_task)
                task.add_done_callback(handle_exception)
                loop.run_until_complete(task)
            except asyncio.CancelledError:
                pass
            finally:
                loop.close()

        if not self._grab_task and not self._replicate_task:
            threading.Thread(target=create_tasks).start()

    def stop(self) -> None:
        """Stop replicating and toggling this device to virtual machines.

        Cancels the replicate and grab tasks and destroys all devices created
        for virtual machines and ungrabs and closes the source device.
        """

        def destroy():
            if self._replicate_task:
                self._replicate_task.cancel()
            if self._grab_task:
                self._grab_task.cancel()
            for target in frozenset(self._targets.keys()):
                self._destroy_device(
                    cast(str, target) if target else "host", key=target
                )
            if self._source:
                try:
                    self._source.ungrab()
                    logging.info("Ungrabbed device %s", self._source.path)
                    self._source.close()
                except IOError:
                    pass
                finally:
                    self._source = None

        if self._grab_task:
            self._grab_task.get_loop().call_soon_threadsafe(destroy)

    def add(self, vm_name: str, hotkey: Optional[Hotkey] = None) -> None:
        """Add a new virtual device for the virtual machine.

        Args:
            vm_name: The name of the new virtual machine to be monitored. This
                is used as a prefix for all newly created virtual devices.
            hotkey: An optional hotkey combination that will be monitored and,
                if detected, will cause a switch directly to this virtual
                machine.
        """
        if hotkey:
            self._hotkeys[hotkey] = vm_name
            logging.debug("Adding hotkey %s to VM %s", hotkey, vm_name)
        self.start()
        self._create_device(vm_name)

    def remove(self, vm_name: str, hotkey: Optional[Hotkey] = None) -> None:
        """Remove the virtual device created for the virtual machine.

        Args:
            vm_name: The name of the virtual machine that is no longer to be
                monitored. The virtual device created with this name as a prefix
                will be destroyed.
            hotkey: An optional hotkey combination. If given, any matching
                hotkey will be removed from the list of monitored hotkeys.
        """
        self._destroy_device(vm_name)
        if hotkey:
            self._hotkeys.pop(hotkey, None)
        if len(self._targets) == 1:
            self.stop()
