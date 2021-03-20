#!/usr/bin/env bash

while :; do
  dbus-send \
    --system \
    --type="method_call" \
    --dest=vfio.kvm \
    /vfio/kvm \
    vfio.kvm.Toggle
  sleep 60
done
