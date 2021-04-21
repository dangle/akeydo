#!/bin/bash

VM=${1}

dbus-send \
    --system \
    --print-reply \
    --type="method_call" \
    --dest=dev.akeydo \
    /dev/akeydo \
    dev.akeydo.Release \
    string:"${VM}" \
    string:"end" \
    string:"-" \
    string:"$(virsh dumpxml ${VM})"
