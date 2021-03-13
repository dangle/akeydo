#!/bin/bash

VM=${1:-"win10"}

dbus-send \
    --system \
    --print-reply \
    --type="method_call" \
    --dest=vfio.kvm \
    /vfio/kvm \
    vfio.kvm.Release \
    string:"${VM}" \
    string:"end" \
    string:"-" \
    string:"$(virsh dumpxml ${VM})"
