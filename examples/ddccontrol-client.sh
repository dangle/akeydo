function monitor_listener() {
  dbus-monitor --system "type='signal',sender='vfio.kvm'" 2>/dev/null |
    while read x; do
      case "$x" in
      *'string "host"'*)
        ddccontrol -r 0x60 -w 15 dev:/dev/i2c-9
        ;;
      *'string "guest"'*)
        ddccontrol -r 0x60 -w 17 dev:/dev/i2c-9
        ;;
      esac
    done
}

monitor_listener &
