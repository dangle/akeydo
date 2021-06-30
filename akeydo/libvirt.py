"""Classes and utilities for parsing and using libvirt domain XML.

Classes:
    VirtualMachineConfig: A python representation of a libvirt domain XML
        configuration file containing only the attributes necessary for
        configuring the service.
"""

from __future__ import annotations

import functools
import itertools
import logging
import xml.etree.ElementTree as xml

from . import hotkey

__all__ = (
    "Device",
    "VirtualMachineConfig",
)


Device = tuple[int, int, int, int]


class VirtualMachineConfig:
    """A representation of virtual-machine XML configuration values."""

    _NAMESPACE = "akeydo"
    _NAMESPACE_URI = "https://dev.akeydo/xmlns/libvirt/domain/1.0"

    _UNITS = {
        "b": 1,
        "bytes": 1,
        "KB": 10 ** 3,
        "k": 2 ** 10,
        "KiB": 2 ** 10,
        "MB": 10 ** 6,
        "M": 2 ** 20,
        "MiB": 2 ** 20,
        "GB": 10 ** 9,
        "G": 2 ** 30,
        "GiB": 2 ** 30,
        "TB": 10 ** 12,
        "T": 2 ** 40,
        "TiB": 2 ** 40,
    }

    def __init__(self, xml_config: str) -> None:
        """Parse libvirt XML configuration.

        Parses an XML configuration for a virtual machine passed to the service
        via a libvirt hook. The relevant values are stored on this object for
        later reference.

        Args:
            xml_config: The XML configuration for a virtual machine that was
                passed to the service through a VM hook.
        """
        root: xml.Element = xml.fromstring(xml_config)
        self.name: str = root.findtext(".//name")
        self.hugepages: bool = root.find(".//memoryBacking/hugepages") is not None
        self.memory: int = self._parse_memory(root)
        self.pinned_cpus: set[int] = self._parse_cpusets(root)
        self.pci_devices: set[Device] = self._parse_pci_devices(root)
        self.devices: set[str] = self._parse_devices(root, self.name)
        self.hotkey: Optional[hotkey.Hotkey] = self._parse_hotkey(root)

    @functools.cached_property
    def cpuset(self) -> int:
        """An integer mask representing the pinned CPUs for this VM."""
        mask = 0
        for cpu in self.pinned_cpus:
            mask |= 1 << cpu
        return mask

    def _parse_memory(self, root) -> int:
        """Parse memory from memory elements.

        Args:
            root: The root element of the libvirt domain XML.

        Returns: The number of bytes required by the virtual machine.
        """
        element = root.find(".//memory")
        unit = element.get("unit", "b")
        mem = int(element.text or "0")
        return mem * self._UNITS[unit]

    def _parse_pci_devices(self, root: xml.Element) -> set[Device]:
        """Parse PCI devices from hostdev elements.

        Args:
            root: The root element of the libvirt domain XML.

        Returns: A set of 4-tuples containing the integer represetations of the
            domain, bus, slot, and function of each device.
        """
        return frozenset(
            (
                int(e.get("domain", "0"), base=16),
                int(e.get("bus", "0"), base=16),
                int(e.get("slot", "0"), base=16),
                int(e.get("function", "0"), base=16),
            )
            for e in root.findall(".//devices/hostdev[@type='pci']/source/address")
        )

    def _parse_cpusets(self, root: xml.Element) -> set[int]:
        """Parse cpusets from vcpupin elements.

        Args:
            root: The root element of the libvirt domain XML.

        Returns: A set containing all of the CPUs that are pinned.
        """
        return frozenset(
            itertools.chain.from_iterable(
                self._parse_cpuset(cpuset)
                for element in root.findall(".//cputune/vcpupin")
                for cpuset in (element.get("cpuset") or "").split(",")
            )
        )

    @staticmethod
    def _parse_cpuset(cpuset: str) -> Iterable[int]:
        """Parse a cpuset into an iterable.

        Args:
            cpuset: An (optionally) hyphenated string representing a range of
                CPUs in a CPU set, or a single integer.

        Returns: An iterable containing all integers in the given range
            specified by the string representation of the cpuset.
        """
        try:
            if "-" in cpuset:
                lower, upper = (int(cpu) for cpu in cpuset.split("-"))
                if upper < lower:
                    upper, lower = lower, upper
                return range(lower, upper + 1)
            return (int(cpuset),)
        except ValueError:
            logging.warning("Unable to parse cpuset %s", cpuset)
            return ()

    def _parse_devices(self, root: xml.Element, name: str) -> set[str]:
        """Parse devices to be generated for this VM.

        Args:
            root: The root element of the libvirt domain XML.
            name: The name of the virtual machine that will be stripped from the
                parsed devices in order to get the base devices.

        Returns: A set of all devices that will be toggled between the host and
            the active virtual machines.
        """
        return self._parse_passthrough_inputs(root, name) | self._parse_qemu_arg_evdev(
            root, name
        )

    @staticmethod
    def _parse_passthrough_inputs(root: xml.Element, name: str) -> set[str]:
        """Parse devices to be generated for this VM from libvirt devices.

        Args:
            root: The root element of the libvirt domain XML.
            name: The name of the virtual machine that will be stripped from the
                parsed devices in order to get the base devices.

        Returns: A set of devices that will be toggled between the host and the
            active virtual machines that are configured as libvirt passthrough
            devices.
        """
        return {
            dev
            for e in root.findall(".//devices/input[@type='passthrough']/source")
            if (dev := e.get("evdev", "")).startswith(f"/dev/input/by-id/{name}-")
        }

    @staticmethod
    def _parse_qemu_arg_evdev(root: xml.Element, name: str) -> set[str]:
        """Parse devices to be generated for this VM from QEMU args.

        This method is no longer recommended as it is adds complexity and risk
        to passing through devices; however, this is still commonly used and, as
        such, must be supported.

        Args:
            root: The root element of the libvirt domain XML.
            name: The name of the virtual machine that will be stripped from the
                parsed devices in order to get the base devices.

        Returns: A set of devices that will be toggled between the host and the
            active virtual machines that are configured as QEMU args.
        """
        return {
            param[6:]
            for e in root.findall(
                ".//qemu:commandline/qemu:arg",
                {"qemu": "http://libvirt.org/schemas/domain/qemu/1.0"},
            )
            if "evdev=" in (val := e.get("value", ""))
            for param in val.split(",")
            if param.startswith(f"evdev=/dev/input/by-id/{name}-")
        }

    def _parse_hotkey(self, root: xml.Element) -> Optional[hotkey.Hotkey]:
        """Parse a Hotkey from the VM metadata to toggle directly to this VM.

        The expected structure uses the `akeydo` namespace and should look like
        the following:

        ```xml
        <akeydo:settings>
            <akeydo:hotkey>
                <akeydo:key value="KEY_LEFTCTRL" />
                <akeydo:key value="KEY_LEFTALT" />
                <akeydo:key value="KEY_KP1" />
            </akeydo:hotkey>
        </akeydo:settings>
        ```

        Args:
            root: The root element of the libvirt domain XML.

        Returns: An optional hotkey
        """
        return hotkey.parse_hotkeys(
            e.get("value")
            for e in root.findall(
                ".//metadata/"
                f"{self._NAMESPACE}:settings/"
                f"{self._NAMESPACE}:hotkey/"
                f"{self._NAMESPACE}:key",
                {self._NAMESPACE: self._NAMESPACE_URI},
            )
        )
