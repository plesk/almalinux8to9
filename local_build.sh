#!/bin/bash
# Sample script to build almalinux8to9 using prebuilt buck

# download the prebuilt buck pex latest version
# wget https://jitpack.io/com/github/facebook/buck/2022.05.05.01/buck-2022.05.05.01.pex -O /root/buck-2022.05.05.01.pex

# make a local build of almalinux8to9 via prebuilt buck pex
# assuming the almalinux8to9 is cloned in /root/almalinux8to9
cd /root/almalinux8to9 || exit
/root/buck-2022.05.05.01.pex build :almalinux8to9
