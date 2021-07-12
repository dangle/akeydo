#!/usr/bin/bash

UPPER_MONITOR=dev:/dev/i2c-4
LOWER_MONITOR=dev:/dev/i2c-6
RIGHT_MONITOR=dev:/dev/i2c-7

INPUT_REGISTER=0x60

HDMI1=0x11
HDMI2=0x12
DP=0x0F
USBC=0x1B

VM=($(virsh list --inactive --name))

for vm in ${VM[@]}; do
  virsh start "${vm}"
done

HOST="$(virsh domifaddr "${VM[1]}" | awk '/192.168./{print substr($4, 1, length($4)-3)}')"

function change_input() {
  local monitor=${1}
  local new_input=${2}
  ssh ${HOST} bash <<EOF
raw_current_input=\$(ddccontrol -r ${INPUT_REGISTER} ${monitor} | awk -F '/' '/+/{ print \$2 }')
current_input=\$((\$raw_current_input - 0x0F00))

if (( \${current_input} != ${new_input} )); then
  ddccontrol -r ${INPUT_REGISTER} -w ${new_input} ${monitor}
fi
EOF
}

dbus-monitor --system "type='signal',sender='dev.akeydo'" 2>/dev/null |
  while read line; do
    case "${line}" in
    *"string \"${VM[0]}\""*)
      change_input ${LOWER_MONITOR} ${HDMI1}
      ;;
    *"string \"${VM[1]}\""*)
      change_input ${LOWER_MONITOR} ${DP}
      change_input ${UPPER_MONITOR} ${DP}
      ;;
    *"string \"${VM[2]}\""*)
      change_input ${UPPER_MONITOR} ${HDMI2}
      ;;
    esac
  done
