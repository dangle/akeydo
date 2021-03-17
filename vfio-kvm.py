#!/usr/bin/env python3
"""
A service that reads libvirtd events from a hook and manages device creation and
deletion, replication, CPU pinning, and hugepages allocation.

Classes:
    DbusTypes: An enumeration of types used by dbus_next.
    VmOptions: A dataclass containing options for virtual machines configured at
        launch and not in the XML configuration of the virtual machine.
    VmConfig: A class containing the relevant parsed sections of a virtual
        machine's XML configuration during the virtual machine's start.
    VfioKvmService: The service that manages hardware alterations and
        replications as well as signaling when a new virtual machine has focus.
    ReplicatedDevice: Manages a real system device and creates virtual devices
        that can receive input only when a specific virtual machine (or the
        host) has focus.

Type Aliases:
    Hotkey: A structure describing a sequence of Linux-defined values
        representing key presses used to trigger an action.

Functions:
    main: Called when this script is run as an executable. It creates the
        services and handles exceptions in the event loop.
"""


from typing import (
    FrozenSet,
    List,
    Optional,
    Set,
    Tuple,
    Union,
)
import asyncio
import dataclasses
import functools
import logging
import os
import signal
import stat
import xml.etree.ElementTree as xml

import dbus_next as dbus
import evdev
import yaml


Hotkey = FrozenSet[int]


class DbusTypes:
    """An enumeration to represent the strings used by dbus_next."""

    Boolean = "b"
    String = "s"


@dataclasses.dataclass
class VmOptions:
    """A dataclass to hold data virtual machine-specific options."""

    hotkey: Hotkey = dataclasses.field(default_factory=frozenset)


class VmConfig:
    """A representation of virtual-machine XML configuration values."""

    def __init__(self, xml_config: str):
        """XXX"""
        root = xml.fromstring(xml_config)
        hugepages = root.find(".//memoryBacking/hugepages") is not None
        memory = int(root.findtext(".//memory"))
        mem_in_mb = memory // 1024
        self.hugepages1G: int = mem_in_mb // 1024 if hugepages else 0
        self.hugepages2M: int = mem_in_mb % self.hugepages1G if hugepages else 0
        self.cpu: List[int] = (
            int(e.get("cpuset")) for e in root.findall(".//cputune/vcpupin")
        )
        self.devices: Set[str] = {
            e.get("evdev")
            for e in root.findall(".//devices/input[@type='passthrough']/source")
        } | {
            param[6:]
            for e in root.findall(
                ".//qemu:commandline/qemu:arg",
                {"qemu": "http://libvirt.org/schemas/domain/qemu/1.0"},
            )
            if "evdev=" in e.get("value")
            for param in e.get("value").split(",")
            if param.startswith("evdev=")
        }


class VfioKvmService(dbus.service.ServiceInterface):
    """XXX"""

    _DEFAULT_CONFIG_PATH = "/etc/vfio-kvm.yaml"
    _DEFAULT_QEMU_HOTKEY = ("KEY_LEFTCTRL", "KEY_RIGHTCTRL")
    _DEFAULT_HOTKEY = _DEFAULT_QEMU_HOTKEY

    _BUS_NAME = "vfio.kvm"
    _OBJ_PATH = "/vfio/kvm"

    async def __new__(cls, *args, **kwargs) -> dbus.service.ServiceInterface:
        """A workaround for async __init__ functions."""
        instance = super().__new__(cls)
        await instance.__init__(*args, **kwargs)
        return instance

    async def __init__(
        self, config: str = None, bus: str = None, path: str = None
    ) -> None:
        """Creates a new DBUS service for managing virtual machines.

        Args:
            config: XXX
            bus: XXX
            path: XXX
        """
        super().__init__(bus or self._BUS_NAME)
        self._released = False
        self._vm_options = {}
        self._devices = {}
        self._targets = [None]
        self._target = None
        self._manage_cpu = False
        self._manage_hugepages = False
        self._parse_config(config=config or self._DEFAULT_CONFIG_PATH)
        await self._configure_dbus(bus or self._BUS_NAME, path or self._OBJ_PATH)
        logging.info("Listening for libvirtd events")

    def _parse_config(self, config: str) -> None:
        """XXX

        Args:
            config: XXX
        """
        config = config or self._DEFAULT_CONFIG_PATH
        if not os.path.isfile(config):
            return
        with open(config) as fp:
            data = yaml.safe_load(fp) or {}
        if "host" in data:
            self._vm_options[None] = VmOptions(
                self._parse_hotkeys(data["host"].get("hotkey"))
            )
        self._vm_options.update(
            {
                key: VmOptions(self._parse_hotkeys(value.get("hotkey")))
                for key, value in data.get("vm", {}).items()
            }
        )
        self._manage_cpu = data.get("manage_cpu", False)
        self._manage_hugepages = data.get("manage_hugepages", False)
        self._release_hotkey = self._parse_hotkeys(data.get("release_hotkey", []))
        self._hotkey = self._parse_hotkeys(data.get("hotkey", self._DEFAULT_HOTKEY))
        self._qemu_hotkey = self._parse_hotkeys(
            data.get("qemu_hotkey", self._DEFAULT_QEMU_HOTKEY)
        )

    def _parse_hotkeys(self, hotkey: List[str]) -> Hotkey:
        """XXX

        Args:
            hotkey: XXX

        Returns: XXX
        """
        try:
            return frozenset(evdev.ecodes.ecodes[key] for key in hotkey)
        except:
            logging.warning(
                "Unable to match all keys in hotkey %s to integers. "
                "Hotkey will be unavailable.",
                hotkey,
            )
            return frozenset()

    async def _configure_dbus(self, bus: str, path: str) -> None:
        """XXX

        Args:
            bus: XXX
            path: XXX
        """
        _bus = await dbus.aio.MessageBus(
            bus_type=dbus.constants.BusType.SYSTEM
        ).connect()
        _bus.export(path, self)
        logging.debug("Requesting bus name %s", _bus.unique_name)
        await asyncio.wait_for(_bus.request_name(bus), timeout=30)
        logging.debug("Bus name %s granted", _bus.unique_name)

    @functools.cached_property
    def hotkey(self) -> Hotkey:
        return frozenset(self._hotkey)

    @functools.cached_property
    def qemu_hotkey(self) -> Hotkey:
        return frozenset(self._qemu_hotkey)

    @functools.cached_property
    def release_hotkey(self) -> Hotkey:
        return frozenset(self._release_hotkey)

    @property
    def released(self):
        return self._released

    @released.setter
    def released(self, value: bool) -> bool:
        logging.debug(f"Released state set to {value}")
        self._released = value
        return self._released

    def stop(self) -> None:
        for device in self._devices.values():
            device.stop()

    @dbus.service.dbus_property(name="Target")
    def target(self) -> DbusTypes.String:
        return self._target

    @target.setter
    def target(self, val: DbusTypes.String):
        display = val or "host device"
        if val == self._target:
            logging.debug("%s selected but %s is already active", display, display)
            return
        logging.info("%s selected", display)
        self._released = False
        self._target = val
        for device in self._devices.values():
            device.grab()
        self.emit_properties_changed({"Target": display})

    @dbus.service.method("Toggle")
    def toggle(self) -> DbusTypes.String:
        self.target = self._targets[
            (self._targets.index(self._target) + 1) % len(self._targets)
        ]
        return self.target

    @dbus.service.method("Prepare")
    def prepare(
        self,
        vm_name: DbusTypes.String,
        sub_op: DbusTypes.String,
        extra_op: DbusTypes.String,
        xml_config: DbusTypes.String,
    ) -> DbusTypes.Boolean:
        logging.info("VM %s preparing to start", vm_name)
        logging.debug("libvirtd: %s %s %s\n%s", vm_name, sub_op, extra_op, xml_config)
        config = VmConfig(xml_config)
        self._targets.append(vm_name)
        self._pin_cpus(config.cpu)
        self._allocate_hugepages(config.hugepages1G, config.hugepages2M)
        self._create_devices(
            vm_name,
            config.devices,
            self._vm_options.get(None, VmOptions()).hotkey,
            self._vm_options.get(vm_name, VmOptions()).hotkey,
        )
        return True

    def _pin_cpus(self, cpu: Tuple[int]) -> None:
        if not self._manage_cpu or not cpu:
            return
        logging.info("Pinning CPUs: %s", ", ".join(str(c) for c in sorted(cpu)))

    def _allocate_hugepages(self, gb_pages: int, mb_pages: int) -> None:
        if not self._manage_hugepages or (not gb_pages and not mb_pages):
            return
        logging.info(
            "Allocating %d 1G hugepages and %d 2M hugepages", gb_pages, mb_pages
        )

    def _create_devices(
        self,
        vm_name: str,
        devices: Tuple[str],
        host_hotkey: Hotkey = None,
        guest_hotkey: Hotkey = None,
    ) -> None:
        for guest_source in devices:
            source = os.path.join(
                os.sep,
                "dev",
                "input",
                "by-id",
                os.path.basename(guest_source)[len(vm_name) + 1 :],
            )
            if source not in self._devices:
                self._devices[source] = ReplicatedDevice(source, self, host_hotkey)
            device = self._devices.get(source)
            device.add(vm_name, guest_hotkey)

    @dbus.service.method("Release")
    def release(
        self,
        vm_name: DbusTypes.String,
        sub_op: DbusTypes.String,
        extra_op: DbusTypes.String,
        xml_config: DbusTypes.String,
    ) -> DbusTypes.Boolean:
        if vm_name not in self._targets:
            logging.debug("Attempted to release devices for unmanaged VM %s", vm_name)
            return False
        logging.info("VM %s shutting down", vm_name)
        logging.debug("libvirtd: %s %s %s\n%s", vm_name, sub_op, extra_op, xml_config)
        config = VmConfig(xml_config)
        self._targets.remove(vm_name)
        if self._target == vm_name:
            self.target = None
        self._destroy_devices(vm_name, config.devices)
        self._deallocate_hugepages(config.hugepages1G, config.hugepages2M)
        self._unpin_cpus(config.cpu)
        return True

    def _unpin_cpus(self, cpu: Tuple[int]) -> None:
        if not self._manage_cpu or not cpu:
            return
        logging.info("Unpinning CPUs: %s", ", ".join(str(c) for c in sorted(cpu)))

    def _deallocate_hugepages(self, gb_pages: int, mb_pages: int) -> None:
        if not self._manage_hugepages or (not gb_pages and not mb_pages):
            return
        logging.info(
            "Deallocating %d 1G hugepages and %d 2M hugepages", gb_pages, mb_pages
        )

    def _destroy_devices(
        self, vm_name: str, devices: Tuple[str], guest_hotkey: Hotkey = None
    ) -> None:
        is_last_vm = len(self._targets) == 1
        for guest_source in devices:
            source = os.path.join(
                os.sep,
                "dev",
                "input",
                "by-id",
                os.path.basename(guest_source)[len(vm_name) + 1 :],
            )
            device = self._devices[source]
            device.remove(vm_name, guest_hotkey)
            if is_last_vm:
                del self._devices[source]
                del device


class ReplicatedDevice:
    """XXX"""

    def __init__(
        self,
        source: str,
        manager: VfioKvmService,
        host_hotkey: Optional[Hotkey] = None,
    ) -> None:
        if not os.path.exists(source) or not stat.S_ISCHR(os.stat(source).st_mode):
            raise IOError("No such device: %s", source)
        self._name = os.path.basename(source)
        self._source_path = source
        self._source = None
        self._manager = manager
        self._targets = {}
        self._hotkeys = {}
        self._grab_task = None
        self._replicate_task = None
        if host_hotkey:
            self._hotkeys[host_hotkey] = None

    def _get_device_path(self, target: str) -> str:
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
        path = self._get_device_path(target)
        logging.info(f"Creating {target} device %s", path)
        device = evdev.UInput.from_device(self._source)
        self._targets[key if key is not False else target] = device
        if os.path.islink(path):
            logging.debug(f"Removing existing symlink %s", path)
            os.unlink(path)
        os.symlink(device.device, path)

    def _destroy_device(
        self, target: str, *, key: Union[bool, None, str] = False
    ) -> None:
        index = key if key is not False else target
        if index not in self._targets:
            return
        path = self._get_device_path(target)
        logging.info(f"Destroying {target} device %s", path)
        if os.path.islink(path):
            logging.debug(f"Removing symlink %s", path)
            os.unlink(path)
        self._targets.pop(index).close()

    async def _grab_source(self) -> None:
        while 1:
            try:
                self._source.grab()
                logging.debug("Grabbed source device %s", self._source.path)
            except IOError:
                pass
            except asyncio.CancelledError:
                return
            await asyncio.sleep(5)

    @property
    def _target(self) -> evdev.device.InputDevice:
        return self._targets.get(
            None if self._manager.released else self._manager.target
        )

    async def _replicate(self) -> None:
        is_release = False
        is_toggle = False
        hotkey_triggered = None

        async def handle_release(active_keys: Hotkey) -> None:
            nonlocal is_release
            if event.value == 1 and active_keys == self._manager.release_hotkey:
                is_release = True
            elif is_release and not self._source.active_keys():
                self._target.syn()
                await asyncio.sleep(0.1)
                is_release = False
                self._manager.released = not self._manager.released

        async def handle_toggle(active_keys: Hotkey) -> None:
            nonlocal is_toggle
            if event.value == 1 and active_keys == self._manager.hotkey:
                is_toggle = True
            elif is_toggle and not self._source.active_keys():
                self._target.syn()
                await asyncio.sleep(0.1)
                is_toggle = False
                self._manager.toggle()

        async def handle_hotkeys(active_keys: Hotkey) -> None:
            nonlocal hotkey_triggered
            if event.value == 1 and active_keys in self._hotkeys:
                hotkey_triggered = active_keys
            elif hotkey_triggered and not self._source.active_keys():
                self._target.syn()
                await asyncio.sleep(0.1)
                self._manager.target = self._hotkeys[hotkey_triggered]
                hotkey_triggered = None

        async for event in self._source.async_read_loop():
            self._target.write_event(event)
            if event.type == evdev.ecodes.EV_KEY:
                active_keys = frozenset(self._source.active_keys())
                await handle_release(active_keys)
                await handle_toggle(active_keys)
                await handle_hotkeys(active_keys)

    def grab(self) -> None:
        if not self._manager.target:
            return
        try:
            self._target.device.grab()
            self._target.device.ungrab()
        except IOError:
            return
        logging.debug("Grabbing device %s", self._get_device_path(self._manager.target))
        for value in (1, 0):
            for key in self._manager.qemu_hotkey:
                self._target.write(evdev.ecodes.EV_KEY, key, value)
        self._target.syn()

    def start(self) -> None:
        if not self._source:
            self._source = evdev.InputDevice(self._source_path)
            self._create_device("host", key=None)
        if not self._grab_task:
            self._grab_task = asyncio.create_task(
                self._grab_source(), name=f"Grab: {self._name}"
            )
            self._grab_task.add_done_callback(handle_exception)
        if not self._replicate_task:
            self._replicate_task = asyncio.create_task(
                self._replicate(), name=f"Replicate: {self._name}"
            )
            self._replicate_task.add_done_callback(handle_exception)

    def stop(self) -> None:
        self._replicate_task.cancel()
        self._grab_task.cancel()
        for target in frozenset(self._targets.keys()):
            self._destroy_device(target if target else "host", key=target)
        try:
            self._source.ungrab()
            logging.info(f"Ungrabbed device %s", self._source.path)
            self._source.close()
            self._source = None
        except IOError:
            pass

    def add(self, vm_name: str, hotkey: Optional[Hotkey] = None) -> None:
        if hotkey:
            self._hotkeys[hotkey] = vm_name
            logging.debug("Adding hotkey %s to VM %s", hotkey, vm_name)
        self.start()
        self._create_device(vm_name)

    def remove(self, vm_name: str, hotkey: Optional[Hotkey] = None) -> None:
        self._destroy_device(vm_name)
        self._hotkeys.pop(hotkey, None)
        if len(self._targets) == 1:
            self.stop()


def handle_exception(task: asyncio.Task) -> None:
    try:
        task.result()
    except asyncio.CancelledError:
        pass
    except:
        logging.exception("Exception raised by task %s", task.get_name())
        asyncio.get_event_loop().stop()


async def main() -> None:
    """Configure logging and error handling and start the service."""
    logging.basicConfig(
        level=os.environ.get("LOGLEVEL", "INFO").upper(),
        format="[%(levelname)s] %(message)s",
    )
    manager = await VfioKvmService()

    def signal_handler() -> None:
        """Stop the service and cleanup devices on receiving a signal."""
        manager.stop()
        asyncio.get_event_loop().stop()

    loop = asyncio.get_event_loop()

    for s in (signal.SIGINT, signal.SIGQUIT, signal.SIGTERM):
        loop.add_signal_handler(s, signal_handler)


if __name__ == "__main__":
    loop = asyncio.get_event_loop()
    loop.create_task(main())
    loop.run_forever()
