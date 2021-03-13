#!/bin/bash

VM=${1:-"win10"}

dbus-send \
    --system \
    --print-reply \
    --type="method_call" \
    --dest=vfio.kvm \
    /vfio/kvm \
    vfio.kvm.Prepare \
    string:"${VM}" \
    string:"begin" \
    string:"-" \
    string:"$(virsh dumpxml ${VM})"
