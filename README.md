# vfio-kvm

A systemd service that sends a D-Bus signal when the QEMU `evdev` hotkey is
triggered.

When using a virtual machine with `evdev` passthrough QEMU allows the devices to
be switched between the host and the virtual machine by pressing the left and
right control keys at the same time. This service detects that press and sends a
D-BUS signal allowing the computer to trigger and actions the user may want,
including changing the input of one or more monitors.

When a virtual machine is started, the service reads the XML configuration for
the virtual machine and scans for any passthrough input devices that start with
the name of the virtual machine and creates them.

The service reads events from the source device and forwards them to the newly
created device. When the QEMU hotkey is pressed the events will be forwarded to
the next virtual machine or the host, allowing control to be cycled between any
number of virtual machines.

## Installation

### Arch Linux

```shell
yay -Sy vfio-kvm
systemctl enable vfio-kvm.service
systemctl start vfio-kvm.service
```

### Manual Installation

```shell
cp config/libvirt/qemu /etc/libvirt/hooks/
cp config/dbus/vfio-kvm.xml /etc/dbus-1/system.d/
cp vfio-kvm.py /usr/bin/vfio-kvm
chmod +x /usr/bin/vfio-kvm
cp config/systemd/vfio-kvm.service /usr/lib/systemd/system/
systemctl enable vfio-kvm.service
systemctl start vfio-kvm.service
```

## Using the Service

For each device to toggle between the host and virtual machine(s) add the
following XML segment to the libvirt XML for the virtual machine.

```xml
...
<devices>
  ...
  <input type="passthrough" bus="virtio">
    <source evdev="/dev/input/by-id/<VM NAME>-<DEVICE NAME>"/>
  </input>
  ...
</devices>
...
```

For example, to passthrough the device `keyboard1` to the virtual machine named
`vm1` add the following XML segment to the `<devices>` section of the virtual
machine configuration:

```xml
<input type="passthrough" bus="virtio">
  <source evdev="/dev/input/by-id/vm1-keyboard1"/>
</input>
```

The service will grab `/dev/input/by-id/keyboard1` and forward events from it to
the device specified in the `evdev` attribute of the `<source>` tag.

## Switching Monitors on Hotkey

This service sends a D-Bus signal that can be monitored in order to run custom
commands when the QEMU hotkey is pressed. To monitor the signal from a shell
script use the program `dbus-monitor`.

```shell
dbus-monitor --system "type='signal',sender='vfio.kvm'"
```

To see a [complete example](examples/ddccontrol-client.sh) that triggers
[ddccontrol](https://github.com/ddccontrol/ddccontrol), look in the [examples](examples/) folder.

## Troubleshooting

- The VM won't start when configured to use the `guest` devices
  - The `vfio-kvm.service` must be started in order for the guest devices to
    exist; verify that the service has started successfully before the VM loads.
