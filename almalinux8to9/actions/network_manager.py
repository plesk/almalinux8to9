# Copyright 1999 - 2026. WebPros International GmbH. All rights reserved.

# https://access.redhat.com/solutions/6900331
# Migrating custom network scripts to NetworkManager dispatcher scripts
#  Solution Verified - Updated June 13 2024 at 9:30 PM

import glob
import os
import shutil

from pleskdistup.common import action, util

NM_SCRIPTS_DIR = "/opt/network-scripts"
IF_SBIN_SCRIPTS_PATTERN = "/sbin/if*-local"
NM_IF_SCRIPTS_PATTERN = "/opt/network-scripts/if*-local"

NM_IFLOCAL_SCRIPT_PATH = "/etc/NetworkManager/dispatcher.d/20-if-local"
NM_IFLOCAL_SCRIPT = """#!/bin/bash

test -n "$DEVICE_IFACE" || exit 0

run() {{
    if [ -x "/sbin/$1" ]; then
        "/sbin/$1" "$DEVICE_IFACE"
        return $?
    fi

    test -x "{0}/$1" || return 0
    "{0}/$1" "$DEVICE_IFACE"
    return $?
}}

case "$2" in
    "up")
        run ifup-local
        ;;
    "pre-up")
        run ifup-pre-local
        ;;
    "down")
        run ifdown-local
        ;;
    "pre-down")
        run ifdown-pre-local
        ;;
esac
""".format(NM_SCRIPTS_DIR)


class CheckDeprecatedIFScripts(action.CheckAction):
    def __init__(self) -> None:
        self.name = "check for deprecated custom network scripts"
        self.description = """There are deprecated custom network scripts: {}.
Either pass `--fix-deprecated-if-scripts` argument in order to fix it by https://access.redhat.com/solutions/6900331 or manually address&remove these.
"""

    def _do_check(self) -> bool:
        scripts = glob.glob(IF_SBIN_SCRIPTS_PATTERN)
        if len(scripts) == 0:
            return True
        self.description = self.description.format(", ".join(scripts))
        return False


class FixDeprecatedIFScripts(action.ActiveAction):
    def __init__(self) -> None:
        self.name = "fix custom network scripts"

    def is_required(self) -> bool:
        return bool(glob.glob(IF_SBIN_SCRIPTS_PATTERN))

    def _prepare_action(self) -> action.ActionResult:
        os.makedirs(NM_SCRIPTS_DIR, exist_ok=True)
        with open(NM_IFLOCAL_SCRIPT_PATH, "w") as f:
            f.write(NM_IFLOCAL_SCRIPT)
        os.chmod(NM_IFLOCAL_SCRIPT_PATH, 0o755)
        util.logged_check_call(["/usr/sbin/restorecon", NM_IFLOCAL_SCRIPT_PATH])
        for file_path in glob.glob(IF_SBIN_SCRIPTS_PATTERN):
            shutil.move(file_path, NM_SCRIPTS_DIR)
        return action.ActionResult()

    def _post_action(self) -> action.ActionResult:
        return action.ActionResult()

    def _revert_action(self) -> action.ActionResult:
        for file_path in glob.glob(NM_IF_SCRIPTS_PATTERN):
            shutil.move(file_path, "/sbin/")
        if not os.listdir(NM_SCRIPTS_DIR):
            os.rmdir(NM_SCRIPTS_DIR)
        return action.ActionResult()

    def estimate_post_time(self) -> int:
        return 1
