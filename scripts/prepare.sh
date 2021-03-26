#!/bin/bash

VM=${1}

dbus-send \
    --system \
    --print-reply \
    --type="method_call" \
    --dest=dev.akeydo \
    /dev/akeydo \
    dev.akeydo.Prepare \
    string:"${VM}" \
    string:"begin" \
    string:"-" \
    string:"$(virsh dumpxml ${VM})"
