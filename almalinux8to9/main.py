#!/usr/bin/python3
# Copyright 1999 - 2026. WebPros International GmbH. All rights reserved.

import sys

import pleskdistup.main
import pleskdistup.registry

import almalinux8to9.upgrader

if __name__ == "__main__":
    pleskdistup.registry.register_upgrader(almalinux8to9.upgrader.AlmaLinux8to9Factory())
    sys.exit(pleskdistup.main.main())
