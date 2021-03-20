#!/usr/bin/env bash

# Replace these values with the values for your monitor.
MONITOR="0x60"
DP1="15"
HDMI1="17"
HDMI2="18"

# Replace these with your virtual machine names.
VM1="vm1"
VM2="vm2"

# This function loops forever listening for a D-BUS signal from the service
# indicating changes to the active target.
function monitor_listener() {
  dbus-monitor --system "type='signal',sender='vfio.kvm'" 2>/dev/null |
    while read x; do
      case "$x" in
      *'string "host device"'*)
        # The host device is identified by the string "host device" to
        # distinguish it from virtual machines.
        ddccontrol -r ${MONITOR} -w ${DP1} dev:/dev/i2c-9
        ;;
      *"string \"${VM1}\""*)
        # Each virtual machine is a separate case block. If you have more or
        # less virtual machines, you can add or remove case blocks as necessary.
        ddccontrol -r ${MONITOR}-w ${HDMI1} dev:/dev/i2c-9
        ;;
      *"string \"${VM2}\""*)
        # Anything can go in these blocks; it doesn't have to be a monitor input
        # change.
        ddccontrol -r ${MONITOR} -w ${HDMI2} dev:/dev/i2c-9
        ;;
      esac
    done
}

# Spawn the listener off in the background and disown it from the terminal.
monitor_listener &
disown
