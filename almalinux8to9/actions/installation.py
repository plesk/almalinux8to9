# Copyright 1999 - 2026. WebPros International GmbH. All rights reserved.
import os
import shutil
import typing

from pleskdistup.common import action, files, rpm, util

LEAPP_ALMALINUX_RPM_URL = "https://repo.almalinux.org/elevate/elevate-release-latest-el8.noarch.rpm"
LEAPP_VENDORS_POSTGRES_REPO: str = '/etc/leapp/files/vendors.d/postgresql.repo'


class LeappInstallation(action.ActiveAction):
    pkgs_to_install: typing.List[str]
    elevate_release_rpm_url: str
    remove_logs_on_finish: bool

    def __init__(self, elevate_release_rpm_url: str, pkgs_to_install: typing.List[str], remove_logs_on_finish: bool = False):
        self.name = "installing leapp"
        self.pkgs_to_install = pkgs_to_install
        self.elevate_release_rpm_url = elevate_release_rpm_url
        self.remove_logs_on_finish = remove_logs_on_finish

    def _prepare_action(self) -> action.ActionResult:
        # it also removes previous converter leftovers: leapp-repository-deps-el[8,9], leapp-deps-el[8,9]
        util.logged_check_call(["/usr/bin/dnf", "erase", "-y", "leapp-*"])

        if not rpm.is_package_installed("elevate-release"):
            util.logged_check_call(["/usr/bin/yum", "install", "-y", self.elevate_release_rpm_url])

        util.logged_check_call(["/usr/bin/yum-config-manager", "--enable", "elevate"])

        util.logged_check_call(["/usr/bin/yum", "install", "-y"] + self.pkgs_to_install)
        # We want to prevent the leapp packages from being updated accidentally to
        # the latest version (for example by using 'yum update -y'). Therefore, we
        # should disable the 'elevate' repository. Additionally, this will prevent
        # the pre-checker from detecting leapp as outdated and prevent re-evaluation
        # on the next restart.
        util.logged_check_call(["/usr/bin/yum-config-manager", "--disable", "elevate"])
        return action.ActionResult()

    def remove_all(self, include_logs: bool = True) -> None:
        rpm.remove_packages(
            rpm.filter_installed_packages(
                self.pkgs_to_install + ["elevate-release", "leapp-upgrade-el8toel9"]
            )
        )
        util.logged_check_call(["/usr/bin/dnf", "erase", "-y", "leapp-*"])

        leapp_related_files = [
            "/root/tmp_leapp_py3/leapp",
        ]
        for file in leapp_related_files:
            if os.path.exists(file):
                os.unlink(file)

        leapp_related_directories = [
            "/etc/leapp",
            "/var/lib/leapp",
            "/usr/lib/python2.7/site-packages/leapp",
        ]
        if include_logs:
            leapp_related_directories.append("/var/log/leapp")
        for directory in leapp_related_directories:
            if os.path.exists(directory):
                shutil.rmtree(directory)

    def _post_action(self) -> action.ActionResult:
        self.remove_all(include_logs=self.remove_logs_on_finish)
        return action.ActionResult()

    def _revert_action(self) -> action.ActionResult:
        self.remove_all(include_logs=False)
        return action.ActionResult()

    def estimate_prepare_time(self) -> int:
        return 40


class RemoveLeappReposDisablement(action.ActiveAction):
    def __init__(self):
        self.name = "remove leapp installation yum.conf inhibitors"

    def is_required(self) -> bool:
        return bool(rpm.yum_conf_get_exclude_list())

    def _prepare_action(self) -> action.ActionResult:
        files.backup_file(rpm.YUM_CONF_PATH)
        rpm.yum_conf_rm_leapp_disablement()
        return action.ActionResult()

    def _post_action(self) -> action.ActionResult:
        # We need to get rid of leapp repo entries in 'exclude=' in order
        # to enable leapp packages installations in the next OS conversion.
        # These are possibly added during leapp upgrade step to prevent
        # unnecessary leapp upgrades
        files.backup_file(rpm.YUM_CONF_PATH)
        rpm.yum_conf_rm_leapp_disablement()
        return action.ActionResult()

    def _revert_action(self) -> action.ActionResult:
        files.restore_file_from_backup(rpm.YUM_CONF_PATH)
        return action.ActionResult()

    def estimate_prepare_time(self) -> int:
        return 1

