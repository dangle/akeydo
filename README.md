# vfio-kvm

A systemd service that send a D-Bus signal when a QEMU `evdev` hotkey is pressed.

This service reads a list of devices to grab and creates new devices with the same id but prefixed with _host-_ and _guest-_. `evdev` events are captured and forwarded to the currently selected device.

## Installation

### Arch Linux

```shell
yay -Sy vfio-kvm-git
```

### Manual Installation

```shell
cp config/dbus/vfio-kvm.xml /etc/dbus-1/system.d/
cp vfio-kvm.py /usr/bin/vfio-kvm
chmod +x /usr/bin/vfio-kvm
cp config/systemd/vfio-kvm.service /etc/systemd/system
systemctl enable vfio-kvm.service
```

Create the file `/etc/vfio-kvm.yaml` with the devices to switch as shown below. Optionally, configure the hotkey that you will use. The default hotkey is `KEY_LEFTCTRL` and `KEY_RIGHTCTRL`.

## Using the Service

Follow the [instructions on the Arch Wiki](https://wiki.archlinux.org/index.php/PCI_passthrough_via_OVMF#Passing_keyboard/mouse_via_Evdev) for setting up keyboard and mouse passthrough for evdev, but prepend `guest-` to each device that you pass through.

Once setup, run `systemctl start vfio-kvm.service` and then start your VM.

## Sample Configuration

```
/etc/vfio-kvm.yaml
```

```yaml
hotkey:
  - KEY_LEFTCTRL
  - KEY_RIGHTCTRL

delay: 5

devices:
  - /dev/input/by-id/usb-kbd
  - /dev/input/by-id/usb-mouse
```

## Switching Monitors on Hotkey

This service sends a D-Bus signal that can be monitored in order to run custom commands when the QEMU hotkey is pressed. To monitor the signal from a shell script use `dbus-monitor`.

```shell
dbus-monitor --system "type='signal',sender='vfio.kvm'"
```

To see a [complete example](examples/ddccontrol-client.sh) that triggers `ddccontrol`, look in the [examples](examples/) folder.

## Troubleshooting

- The VM isn't getting input, even though `journalctl` says `GUEST selected`
  - Verify that passing in the device without this service works.
  - Check that the VM is configured to use the `guest-<device-name>` instead of the raw device.
  - Make sure the QEMU ACL specifies the `guest-<device>` device instead of the raw device.
- The VM won't start when configured to use the `guest` devices
  - The `vfio-kvm.service` must be started in order for the guest devices to exist; verify that the service has started successfully before the VM loads.
