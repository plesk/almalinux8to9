# Copyright 1999 - 2026. WebPros International GmbH. All rights reserved.

import os

from pleskdistup.common import action, files, packages


class PostUpgradeFirewalldConfiguration(action.ActiveAction):
    config_file: str = "/etc/firewalld/firewalld.conf"

    def __init__(self) -> None:
        self.name = "upgrade Firewalld configuration"

    def _check_AllowZoneDrifting(self) -> bool:
        with open(self.config_file, "r") as f:
            for line in f.readlines():
                if line.strip().lower().startswith("allowzonedrifting"):
                    return True
        return False

    def _rm_AllowZoneDrifting(self) -> None:
        lines = []
        with open(self.config_file, "r") as f:
            lines = f.readlines()
        # Filter out AllowZoneDrifting lines (any value)
        new_lines = [
            line for line in lines
            if not line.strip().lower().startswith("allowzonedrifting")
        ]
        with open(self.config_file, "w") as f:
            f.writelines(new_lines)

    def is_required(self) -> bool:
        return ((len(packages.get_installed_packages_list("firewalld")) != 0) and
                os.path.isfile(self.config_file) and
                self._check_AllowZoneDrifting())

    def _prepare_action(self) -> action.ActionResult:
        return action.ActionResult()

    def _post_action(self) -> action.ActionResult:
        files.backup_file(self.config_file)
        self._rm_AllowZoneDrifting()
        return action.ActionResult()

    def _revert_action(self) -> action.ActionResult:
        return action.ActionResult()

    def estimate_post_time(self) -> int:
        return 1
