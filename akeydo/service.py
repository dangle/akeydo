"""
A service that reads libvirtd events from a hook and manages VM resources.

Classes:
    AkeydoService: The service that manages hardware alterations and
        replications as well as signaling when a new virtual machine has focus.
"""

from __future__ import annotations

import asyncio
import functools
import logging
import threading

import dbus_next as dbus

from .libvirt import VirtualMachineConfig
from .settings import Settings
from .task import create_task

__all__ = ("AkeydoService",)


class AkeydoService(dbus.service.ServiceInterface):
    """A D-BUS service that creates and manages virtual devices for libvirt VMs.

    D-Bus Methods:

        Toggle (string):
            This method cycles the currently active target to the next available
            machine.

            Returns: The newly activated target.

        Prepare (boolean):
            Accepts the information for a libvirt QEMU hook including the
            virtual machine name, the sub-operation, extra-operation and the XML
            configuration for the virtual machine. It then pins CPUs, allocates
            memory, and creates devices to use to send input to the virtual
            machine.

            Returns:
                A boolean value to indicate if it was successful or not. On a
                failure, the virtual machine will not be started.

        Release (boolean):
            Accepts the information for a libvirt QEMU hook including the
            virtual machine name, the sub-operation, extra-operation and the XML
            configuration for the virtual machine. If any resources were
            allocated for the virtual machine they will be freed up. Any devices
            created will be destroyed.

            Returns:
                A boolean value to indicate if it was successful or not. If it
                fails, there may be allocated resources that are not cleaned up.

    D-BUS Properties:

        Target (string):
            This property is emitted for any listeners whenever the target is
            changed. This allows listeners to act on changes to the focused
            target and take actions such as changing a monitor input.

    When the service is created, it reads settings from a given configuration
    file (default: /etc/vfio-kvm.yaml) if it exists. This file is used to read
    hotkeys for direct access to specific virtual machines, the host, or to
    change the QEMU hotkey and D-BUS bus name and object path. It can also set
    a hotkey to release the devices to the host without emitting a target change
    or altering the position in the virtual machine cycle.
    """

    HOST = None  # None used as a target represents the true host device.

    def __init__(self, settings: Settings, *plugins) -> None:
        """Create a new D-BUS service for managing virtual machines.

        Args:
            settings: Global settings for hotkeys and plug-in options.
            plugins: An iterable containing plug-in managers that should be
                initialized.
        """
        self._settings = settings
        self._released = False
        self._current_host = self.HOST
        self._plugins = tuple(plugin(settings, self) for plugin in plugins)
        self._targets: list[Optional[str]] = [self.HOST]
        self._target: Optional[str] = self.HOST
        self._bus: Optional[dbus.aio.MessageBus] = None
        self._lock = threading.Lock()
        super().__init__(settings.dbus.bus_name)

    async def start(self) -> None:
        """Start the service and initialize the D-BUS message bus.

        Requesting a bus name that the running user does not have access to will
        cause the program to hang indefinitely because dbus_next does not yield
        control or timeout.
        """
        self._bus = await dbus.aio.MessageBus(
            bus_type=dbus.constants.BusType.SYSTEM
        ).connect()
        self._bus.export(self._settings.dbus.object_path, self)
        logging.debug("Requesting bus name %s", self._bus.unique_name)
        await asyncio.wait_for(
            self._bus.request_name(self._settings.dbus.bus_name), timeout=30
        )
        logging.debug("Bus name %s granted", self._bus.unique_name)
        logging.info("Listening for libvirtd events")
        for plugin in self._plugins:
            self._call_plugin_func(plugin, "start")

    def stop(self) -> None:
        """Stop all devices running on the service and disconnect from D-BUS."""
        try:
            for plugin in reversed(self._plugins):
                self._call_plugin_func(plugin, "stop")
        finally:
            self._bus.disconnect()

    @property
    def vm_count(self) -> int:
        """Return the number of managed virtual machines."""
        return len(self._targets) - 1

    @property
    def released(self):
        """Return the device released state."""
        return self._released

    @released.setter
    def released(self, value: bool) -> bool:
        """Set the device released state to the given value.

        Returns: The new device released state.
        """
        if self._released == value:
            logging.debug(
                "Attempted to set the release state to %s but it already was %s",
                value,
                self._released,
            )
            return
        logging.debug("Released state set to %s", value)
        with self._lock:
            self._released = value
            for plugin in reversed(self._plugins):
                if hasattr(plugin, "target_release"):
                    plugin.target_release(self._released)
            return self._released

    @dbus.service.dbus_property(name="Target")
    def target(self) -> s:
        """Return the current target.

        This is a D-BUS property that can be queried for the currently active
        target as a string.
        """
        current_target = self._target or self._current_host
        logging.trace("Current target is %s", current_target)
        logging.trace("Current host is %s", self._current_host)
        logging.trace("Releasted state is %s", self.released)
        return current_target if not self.released else self._current_host

    @target.setter
    def target(self, val: s) -> str:
        """Set the target to a specific virtual machine.

        This is a D-BUS property that can be used to change the currently active
        target. When the target is changed, any released devices are grabbed and
        a property change is emitted via D-BUS.

        If the target is set to the already active target, no change will be
        emitted and released devices will remain released.

        If the python value None is given the host device will be selected.

        Args:
            val: The new value to set as the currently active target.
        """
        logging.debug("Setting target to %s", val)
        val = val or self._current_host
        logging.debug("Using value %s for target", val)
        display = val or "host device"
        if val == self._target:
            logging.debug("%s selected but %s is already active", display, display)
            return self.target
        logging.info("%s selected", display)
        with self._lock:
            self._released = False
            self._target = val
            for plugin in self._plugins:
                self._call_plugin_func(plugin, "target_changed", val)
            self.emit_properties_changed({"Target": display})
        return self.target

    @dbus.service.method("Toggle")
    def toggle(self) -> s:
        """Cycle the active target to the next virtual machine.

        This is a D-BUS method that can be called to cycle the currently active
        virtual machine.

        Returns: The new active target.
        """
        self.target = self._targets[
            (self._targets.index(self._target) + 1) % len(self._targets)
        ]
        return self.target

    @dbus.service.method("Prepare")
    def vm_prepare(self, vm_name: s, sub_op: s, extra_op: s, xml_config: s) -> b:
        """Create devices to prepare for a new virtual machine.

        The service extracts information about requested passthrough devices,
        hugepages memory requests, and CPU tuning.

        The service creates new devices by removing "{vm_name}-" from the device
        and creating replicas of the base device to be used by the host and
        guest.

        If the "manage_cpu" option is enabled, it will set cpusets to restrict
        the kernel from adding processes to the pinned CPUs.

        If the "manage_hugepages" option is enabled and the virtual machine XML
        specifies "<hugepages/>" it will try to free up sufficient memory and
        dynamically allocate enough hugepages for the virtual machine.

        Args:
            vm_name: The name of the new virtual machine.
            sub_op: The libvirt sub-operation. Always "begin".
            extra_op: The libvirt extra-operation. Always "-".
            xml_config: The libvirt XML definition of the new virtual machine
                that is about to be started.

        Returns: True if all plug-ins return successfully, or False if a plug-in
            raised an exception.
        """
        try:
            if vm_name in self._targets:
                logging.info("VM %s is already managed", vm_name)
                return False
            logging.info("VM %s preparing to start", vm_name)
            logging.debug(
                "libvirtd: %s %s %s\n%s", vm_name, sub_op, extra_op, xml_config
            )
            config = VirtualMachineConfig(xml_config)
            self._targets.append(vm_name)
            for plugin in self._plugins:
                self._call_plugin_func(plugin, "vm_prepare", vm_name, config)
            return True
        except Exception:
            logging.exception(
                "An exception occurred while preparing a virtual machine."
            )
            return False

    @dbus.service.method("Release")
    def vm_release(self, vm_name: s, sub_op: s, extra_op: s, xml_config: s) -> b:
        """Clean up any resources used by the stopped virtual machine.

        This is a D-BUS method that destroys any virtual devices created for the
        virtual machine. If this is the last virtual machine managed by the
        service, the source device will be released.

        If the "manage_cpu" option is enabled, it will set cpusets to remove CPU
        restrictions from any pinned CPUs the virtual machine was using.

        If the "manage_hugepages" option is enabled and the virtual machine XML
        specifies "<hugepages/>" any hugepages allocated for the virtual machine
        will be freed. If this is the last virtual machine managed by the
        service, hugepages and relevant features will be disabled.

        Args:
            vm_name: The name of the virtual machine that just shutdown.
            sub_op: The libvirt sub-operation. Always "end".
            extra_op: The libvirt extra-operation. Always "-".
            xml_config: The libvirt XML definition of the virtual machine
                that just shutdown.

        Returns: True if all plug-ins return successfully, or False if a plug-in
            raised an exception.
        """
        if vm_name not in self._targets:
            logging.debug("Attempted to release unmanaged VM %s", vm_name)
            return False
        logging.info("VM %s shutting down", vm_name)
        logging.debug("libvirtd: %s %s %s\n%s", vm_name, sub_op, extra_op, xml_config)
        config = VirtualMachineConfig(xml_config)
        self._targets.remove(vm_name)
        if vm_name == self._current_host:
            self.set_host()
        if self._target == vm_name:
            self.target = self._current_host
        for plugin in reversed(self._plugins):
            try:
                self._call_plugin_func(plugin, "vm_release", vm_name, config)
            except Exception:
                logging.exception(
                    "An error occurred while calling %s.%s.vm_release",
                    plugin.__class__.__module__,
                    plugin.__class__.__name__,
                )
        return True

    def set_host(self, vm_name: str = None) -> None:
        """Replace the host target with the given virtual machine.

        Removes the true host target from the list of targets and anything that
        would go to the host will now go to this virtual machine. This is useful
        for GPU passthrough when the true host no longer accepts input and the
        virtual machine receives all input and handles the output.

        Args:
            vm_name: The name of the virtual machine that will replace the host.
                If the value is None, the true host is added back into the list
                of targets.
        """
        logging.debug("Setting host to: %s", vm_name)
        if self.target == self._current_host:
            logging.debug(
                "Currently targeting the host; changing target to %s", vm_name
            )
            self.target = vm_name
        self._current_host = vm_name
        if vm_name == self.HOST:
            self._targets.insert(0, None)
        elif None in self._targets:
            self._targets.remove(None)

    def _call_plugin_func(self, plugin: object, func_name: str, *args: Any) -> None:
        """Call the given function asyncronously on the plugin if it exists.

        Args:
            plugin: The plugin manager that will be used to call the function.
            func_name: The name of the function to call on the plugin.
            args: The arguments to pass to the function.
        """
        if func := getattr(plugin, func_name, None):

            @functools.wraps(func)
            async def trace() -> None:
                logging.debug(
                    "Entering %s.%s.%s",
                    plugin.__class__.__module__,
                    plugin.__class__.__name__,
                    func_name,
                )
                try:
                    await func(*args)
                finally:
                    logging.debug(
                        "Exiting %s.%s.%s",
                        plugin.__class__.__module__,
                        plugin.__class__.__name__,
                        func_name,
                    )

            create_task(trace(), name=f"{plugin.__class__.__name__}.{func_name}")
        else:
            logging.debug(
                "Plug-in %s.%s does not support %s",
                plugin.__class__.__module__,
                plugin.__class__.__name__,
                func_name,
            )
