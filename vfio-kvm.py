#!/usr/bin/env python3

import asyncio
import datetime
import functools
import logging
import os
import signal
import sys
import time

import dbus_next as dbus
import evdev
import yaml


class ReplicatedDevice:
    def __init__(self, source: str, manager) -> None:
        self._name = os.path.basename(source)
        self._source = evdev.InputDevice(source)
        self._manager = manager
        self._task = None
        self._host = None
        self._guest = None

    def _get_device_path(self, target) -> str:
        return os.path.join(
            os.sep,
            "dev",
            "input",
            "by-id",
            f"{target}-{self._name}",
        )

    @functools.cached_property
    def _host_path(self) -> str:
        return self._get_device_path("host")

    @functools.cached_property
    def _guest_path(self) -> str:
        return self._get_device_path("guest")

    @property
    def _target(self) -> evdev.device.InputDevice:
        return getattr(self, f"_{self._manager.target}")

    def _link(self) -> None:
        logging.info(f"Creating host device %s", self._host_path)
        os.symlink(self._host.device, self._host_path)
        logging.info(f"Creating guest device %s", self._guest_path)
        os.symlink(self._guest.device, self._guest_path)

    def _unlink(self) -> None:
        if os.path.islink(self._host_path):
            logging.info(f"Removing host device %s", self._host_path)
            os.unlink(self._host_path)
        if os.path.islink(self._guest_path):
            logging.info(f"Removing guest device %s", self._guest_path)
            os.unlink(self._guest_path)

    def _init_device(self):
        self._host = evdev.UInput.from_device(self._source)
        self._guest = evdev.UInput.from_device(self._source)
        self._unlink()
        self._link()
        try:
            self._source.grab()
        except IOError as e:
            logging.exception(f"Unable to grab device %s", self._source.path)
            asyncio.get_event_loop().stop()
            sys.exit(1)
        logging.info(f"Listening to device %s", self._source.path)

    def _cleanup_device(self):
        self._source.ungrab()
        self._unlink()
        self._host.close()
        self._guest.close()
        logging.info(f"No longer listening to device %s", self._source.path)

    @property
    def is_grabbed(self):
        try:
            self._guest.device.grab()
        except IOError:
            return True
        self._guest.device.ungrab()
        return False

    def grab(self):
        for value in (1, 0):
            for key in self._manager.qemu_hotkey:
                self._guest.write(evdev.ecodes.EV_KEY, key, value)
        self._guest.syn()

    async def _replicate(self) -> None:
        self._init_device()
        try:
            is_toggle = False
            async for event in self._source.async_read_loop():
                self._target.write_event(event)
                if event.type == evdev.ecodes.EV_KEY:
                    if (
                        event.value == 1
                        and frozenset(self._source.active_keys())
                        == self._manager.hotkey
                    ):
                        is_toggle = True
                    elif is_toggle and not self._source.active_keys():
                        self._target.syn()  # Flush queued write events
                        time.sleep(0.1)  # Wait for events to flush
                        is_toggle = False
                        self._manager.toggle()
        except asyncio.CancelledError:
            self._cleanup_device()

    def start(self) -> None:
        self._task = asyncio.create_task(self._replicate())

    def stop(self) -> None:
        self._task.cancel()


class VfioKvmService(dbus.service.ServiceInterface):
    _HOST = "host"
    _GUEST = "guest"

    _DEFAULT_CONFIG_PATH = "/etc/vfio-kvm.yaml"
    _DEFAULT_QEMU_HOTKEY = ("KEY_LEFTCTRL", "KEY_RIGHTCTRL")
    _DEFAULT_HOTKEY = _DEFAULT_QEMU_HOTKEY

    _BUS_NAME = "vfio.kvm"
    _OBJ_PATH = "/vfio/kvm"

    async def __new__(cls, *args, **kwargs) -> dbus.service.ServiceInterface:
        instance = super().__new__(cls)
        await instance.__init__(*args, **kwargs)
        return instance

    async def __init__(self, config=None, bus=None, path=None) -> None:
        super().__init__(bus or self._BUS_NAME)
        config = config or self._DEFAULT_CONFIG_PATH
        if not os.path.isfile(config):
            logging.error('Configuration file "%s" not found', config)
            sys.exit(6)
        with open(config) as fp:
            data = yaml.safe_load(fp)
        self._target = self._HOST
        self._last_change = None
        self._delay = datetime.timedelta(seconds=data.get("delay", 0))
        self._configure_hotkey(data.get("hotkey"))
        self._configure_qemu_hotkey(data.get("qemu_hotkey"))
        await self._configure_dbus(bus or self._BUS_NAME, path or self._OBJ_PATH)
        self._configure_devices(data.get("devices"))

    def _configure_hotkey(self, keys):
        self._hotkey = (
            evdev.ecodes.ecodes[key] for key in keys or self._DEFAULT_HOTKEY
        )

    def _configure_qemu_hotkey(self, keys):
        self._qemu_hotkey = (
            evdev.ecodes.ecodes[key] for key in keys or self._DEFAULT_QEMU_HOTKEY
        )

    def _configure_devices(self, devices):
        if not devices:
            logging.error("No devices configured")
            sys.exit(6)
        self.target = self._HOST
        self._devices = [ReplicatedDevice(device, self) for device in devices or ()]

    async def _configure_dbus(self, bus, path):
        _bus = await dbus.aio.MessageBus(
            bus_type=dbus.constants.BusType.SYSTEM
        ).connect()
        _bus.export(path, self)
        logging.debug("Requesting bus name %s", _bus.unique_name)
        await _bus.request_name(bus)
        logging.debug("Bus name %s granted", _bus.unique_name)

    @property
    def _target_display(self) -> str:
        return self._target.upper()

    def _grab_all(self):
        for device in self._devices:
            device.grab()

    @functools.cached_property
    def hotkey(self) -> frozenset:
        return frozenset(self._hotkey)

    @functools.cached_property
    def qemu_hotkey(self) -> frozenset:
        return frozenset(self._qemu_hotkey)

    @dbus.service.method("Toggle")
    def toggle(self) -> "s":
        self.target = self._HOST if self.target == self._GUEST else self._GUEST
        return self.target

    @dbus.service.method("Prepare")
    def prepare(self, vm_name: "s", sub_op: "s", extra_op: "s", xml_config: "s") -> "b":
        print(xml_config)
        return True

    @dbus.service.method("Start")
    def start(self):
        for device in self._devices:
            device.start()

    @dbus.service.method("Stop")
    def stop(self):
        for device in self._devices:
            device.stop()

    @dbus.service.dbus_property(name="Target")
    def target(self) -> "s":
        return self._target

    @target.setter
    def target(self, val: "s"):
        now = datetime.datetime.now()
        if self._target != val and (
            not self._last_change or now >= self._last_change + self._delay
        ):
            if val == self._GUEST and not all(d.is_grabbed for d in self._devices):
                self._grab_all()
            self._last_change = now
            self._target = val
            logging.info("%s selected", self._target_display)
            self.emit_properties_changed({"Target": self._target})


async def main() -> None:
    logging.basicConfig(
        level=os.environ.get("LOGLEVEL", "INFO").upper(),
        format="[%(levelname)s] %(message)s",
    )
    manager = await VfioKvmService()

    def signal_handler() -> None:
        manager.stop()
        asyncio.get_event_loop().stop()

    for s in (signal.SIGINT, signal.SIGQUIT, signal.SIGTERM):
        asyncio.get_event_loop().add_signal_handler(s, signal_handler)

    manager.start()


if __name__ == "__main__":
    task = asyncio.get_event_loop().create_task(main())
    try:
        asyncio.get_event_loop().run_forever()
    except SystemExit:
        task.exception()
        raise
