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


_BOLD = "\033[1m"
_HOST = "\033[1;33m"
_GUEST = "\033[1;32m"
_RAW = "\033[1;36m"
_CLEAR = "\033[0m"


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
        logging.info(f"Creating host device {_HOST}%s{_CLEAR}", self._host_path)
        os.symlink(self._host.device, self._host_path)
        logging.info(f"Creating guest device {_GUEST}%s{_CLEAR}", self._guest_path)
        os.symlink(self._guest.device, self._guest_path)

    def _unlink(self) -> None:
        if os.path.islink(self._host_path):
            logging.info(f"Removing host device {_GUEST}%s{_CLEAR}", self._host_path)
            os.unlink(self._host_path)
        if os.path.islink(self._guest_path):
            logging.info(f"Removing guest device {_GUEST}%s{_CLEAR}", self._guest_path)
            os.unlink(self._guest_path)

    def _init_device(self):
        self._host = evdev.UInput.from_device(self._source)
        self._guest = evdev.UInput.from_device(self._source)
        self._unlink()
        self._link()
        try:
            self._source.grab()
        except IOError as e:
            logging.exception(
                f"Unable to grab device {_RAW}%s{_CLEAR}", self._source.path
            )
            asyncio.get_event_loop().stop()
            sys.exit(1)
        logging.info(f"Listening to device {_RAW}%s{_CLEAR}", self._source.path)

    def _cleanup_device(self):
        self._source.ungrab()
        self._unlink()
        self._host.close()
        self._guest.close()
        logging.info(
            f"No longer listening to device {_RAW}%s{_CLEAR}", self._source.path
        )

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
                        time.sleep(0.01)  # 10ms delay to let key-up events process
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

    _BUS_NAME = "vfio.kvm"
    _OBJ_PATH = "/vfio/kvm"

    async def __new__(cls, *args, **kwargs) -> dbus.service.ServiceInterface:
        instance = super().__new__(cls)
        await instance.__init__(*args, **kwargs)
        return instance

    async def __init__(self, config=None, bus=None, path=None) -> None:
        super().__init__(bus or self._BUS_NAME)
        with open(config or self._DEFAULT_CONFIG_PATH) as fp:
            data = yaml.safe_load(fp)
        self._target = self._HOST
        self._last_change = None
        self._delay = datetime.timedelta(seconds=data.get("delay", 0))
        self._configure_hotkey(data.get("hotkey"))
        await self._configure_dbus(bus or self._BUS_NAME, path or self._OBJ_PATH)
        self._configure_devices(data.get("devices"))

    def _configure_hotkey(self, keys):
        self._hotkey = (
            evdev.ecodes.ecodes[key]
            for key in keys or ("KEY_LEFTCTRL", "KEY_RIGHTCTRL")
        )

    def _configure_devices(self, devices):
        self.target = self._HOST
        self._devices = [ReplicatedDevice(device, self) for device in devices or ()]

    async def _configure_dbus(self, bus, path):
        _bus = await dbus.aio.MessageBus(
            bus_type=dbus.constants.BusType.SYSTEM
        ).connect()
        _bus.export(path, self)
        await _bus.request_name(bus)

    @property
    def _target_display(self) -> str:
        return f"{_HOST if self.target == self._HOST else _GUEST}{self._target.upper()}{_CLEAR}"

    @functools.cached_property
    def hotkey(self) -> frozenset:
        return frozenset(self._hotkey)

    @dbus.service.method("Toggle")
    def toggle(self) -> "s":
        self.target = self._HOST if self.target == self._GUEST else self._GUEST
        return self.target

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
            self._last_change = now
            self._target = val
            logging.info("%s selected", self._target_display)
            self.emit_properties_changed({"Target": self._target})


async def main() -> None:
    logging.basicConfig(
        level=os.environ.get("LOGLEVEL", "INFO").upper(),
        format=f"{_BOLD}[%(levelname)s]{_CLEAR} %(message)s",
    )
    manager = await VfioKvmService()

    def signal_handler() -> None:
        manager.stop()
        asyncio.get_event_loop().stop()

    for s in (signal.SIGINT, signal.SIGQUIT, signal.SIGTERM):
        asyncio.get_event_loop().add_signal_handler(s, signal_handler)

    manager.start()


if __name__ == "__main__":
    asyncio.get_event_loop().create_task(main())
    asyncio.get_event_loop().run_forever()
