# Copyright 1999 - 2026. WebPros International GmbH. All rights reserved.
import os
import shutil
import subprocess
import typing

from pleskdistup.common import action, dns, files, leapp_configs, log, motd, rpm, util


def _do_id_replacement(id: typing.Optional[str]) -> typing.Optional[str]:
    if id is not None:
        id = id.replace("alma8-", "")
    return leapp_configs.do_replacement(id, [
        lambda to_change: "alma9-" + to_change if not to_change.startswith("alma9-") else to_change,
    ])


def _do_name_replacement(name: typing.Optional[str]) -> typing.Optional[str]:
    return leapp_configs.do_replacement(name, [
        lambda to_change: "Alma " + to_change if not to_change.startswith("Alma ") else to_change,
        lambda to_change: to_change.replace("Enterprise Linux 8",  "Enterprise Linux 9"),
        lambda to_change: to_change.replace("EPEL-8", "EPEL-9"),
        lambda to_change: to_change.replace("$releasever", "9"),
    ])


def _fixup_old_php_urls(to_change: str) -> str:
    supported_old_versions = ["7.1", "7.2", "7.3"]
    for version in supported_old_versions:
        if "PHP_" + version in to_change:
            return to_change.replace("rpm-CentOS-8", "rpm-CentOS-9")
    return to_change


def _fix_rackspace_repository(to_change: str) -> str:
    if "mirror.rackspace.com" in to_change:
        return to_change.replace("rhel8-amd64", "rhel9-amd64")
    return to_change


def _fix_mariadb_repository(to_change: str) -> str:
    # Mariadb official repository doesn't support short url for centos 8 since 10.11
    # Since there are short URL for rhel8 short for all versions, we could use it instead
    if "yum.mariadb.org" in to_change:
        return to_change.replace("rhel8", "rhel9")
    return to_change


def _fix_rackspace_epel_repository(to_change: str) -> str:
    # The Rackspace EPEL repository for version 8 has a slightly different path, including 'Everything' in it
    # Additionally, some repositories use '7Server' instead of 7.
    # Therefore, we need to handle these cases specifically.
    if "iad.mirror.rackspace.com/epel/8/" in to_change:
        return to_change.replace("8", "9/Everything")
    if "iad.mirror.rackspace.com/epel/8Server" in to_change:
        return to_change.replace("8Server", "9/Everything")
    if "iad.mirror.rackspace.com/epel/8/Everything" in to_change:
        return to_change.replace("8/Everything", "9/Everything")
    return to_change


def _do_url_replacement(url: typing.Optional[str]) -> typing.Optional[str]:
    return leapp_configs.do_replacement(url, [
        _fixup_old_php_urls,
        _fix_rackspace_repository,
        _fix_mariadb_repository,
        _fix_rackspace_epel_repository,
        lambda to_change: to_change.replace("archives.fedoraproject.org/pub/archive/epel/8", "dl.fedoraproject.org/pub/epel/9/Everything"),
        lambda to_change: to_change.replace("rpm-RedHat-el8", "rpm-RedHat-el9"),
        lambda to_change: to_change.replace("rpm-CentOS-8", "rpm-RedHat-el9"),
        lambda to_change: to_change.replace("rpm-CentOS-8", "rpm-RedHat-el9"),
        lambda to_change: to_change.replace("AlmaLinux-8", "AlmaLinux-9"),
        lambda to_change: to_change.replace("cloudlinux/8", "cloudlinux/9"),
        lambda to_change: to_change.replace("almalinux/8", "almalinux/9"),
        lambda to_change: to_change.replace("epel-8", "epel-9"),
        lambda to_change: to_change.replace("epel/8", "epel/9"),
        lambda to_change: to_change.replace("epel-debug-8", "epel-debug-9"),
        lambda to_change: to_change.replace("epel-source-8", "epel-source-9"),
        lambda to_change: to_change.replace("centos8", "centos9"),
        lambda to_change: to_change.replace("almalinux8", "almalinux9"),
        lambda to_change: to_change.replace("centos/8", "centos/9"),
        lambda to_change: to_change.replace("rhel/8", "rhel/9"),
        lambda to_change: to_change.replace("rhel8", "rhel9"),
        lambda to_change: to_change.replace("CentOS_8", "CentOS_9"),
        lambda to_change: to_change.replace("AlmaLinux_8", "AlmaLinux_9"),
        lambda to_change: to_change.replace("rhel-$releasever", "rhel-9"),
        lambda to_change: to_change.replace("$releasever", "9"),
        lambda to_change: to_change.replace("mirror.pp.plesk.tech/cloudlinux/8/os/", "mirror.pp.plesk.tech/cloudlinux/9/cloudlinux-x86_64-server-9/"),
        lambda to_change: to_change.replace("mirror.pp.plesk.tech/almalinux/8/os/", "mirror.pp.plesk.tech/almalinux/9/almalinux-x86_64-server-9/"),
        lambda to_change: to_change.replace("autoinstall.plesk.com/PMM_0.1.10", "autoinstall.plesk.com/PMM_0.1.11"),
        lambda to_change: to_change.replace("autoinstall.plesk.com/PMM0", "autoinstall.plesk.com/PMM_0.1.11"),
    ])


def _do_gpgkey_replacement(gpgkey: typing.Optional[str]) -> typing.Optional[str]:
    return leapp_configs.do_replacement(gpgkey, [
        lambda to_change: to_change.replace("EPEL-8", "EPEL-9"),
    ])


def _do_common_replacement(line: typing.Optional[str]) -> typing.Optional[str]:
    return leapp_configs.do_replacement(line, [
        lambda to_change: to_change.replace("EPEL-8", "EPEL-9"),
    ])


def get_adapted_repository(
        repository: rpm.Repository,
        keep_id: bool = False
) -> rpm.Repository:
    id = _do_id_replacement(repository.id) if not keep_id else repository.id
    name = _do_name_replacement(repository.name)

    if id is None or name is None:
        raise ValueError(f"Repository {repository.id!r} with name {name!r} has no next id or next name")

    if repository.url is None and repository.metalink is None and repository.mirrorlist is None:
        raise ValueError(f"Repository {repository.id!r} has no next baseurl, metalink and mirrorlist")

    gpgkey_replacement = [_do_gpgkey_replacement(gpgkey) for gpgkey in repository.gpgkeys] if repository.gpgkeys else []

    return rpm.Repository(
        id,
        name=name,
        url=_do_url_replacement(repository.url) if repository.url else None,
        metalink=_do_url_replacement(repository.metalink) if repository.metalink else None,
        mirrorlist=_do_url_replacement(repository.mirrorlist) if repository.mirrorlist else None,
        enabled=repository.enabled,
        gpgcheck=repository.gpgcheck,
        gpgkeys=[gpgkey for gpgkey in gpgkey_replacement if gpgkey is not None] if gpgkey_replacement else None,
        additional=[sline for sline in (_do_common_replacement(line) for line in repository.additional) if sline is not None]
    )


class DisablePesEventsRemovePackages(action.ActiveAction):
    _list_of_packages_to_remove: typing.List[str]
    _repo: typing.Optional[str]

    def __init__(self, list_of_packages_to_remove: typing.List[str], repo: typing.Optional[str] = None):
        self.name = "disable PES events and remove related packages"
        self._list_of_packages_to_remove = list_of_packages_to_remove
        self._repo = repo

    def _prepare_action(self) -> action.ActionResult:
        if os.path.exists(leapp_configs.LEAPP_PKGS_CONF_PATH):
            files.backup_file(leapp_configs.LEAPP_PKGS_CONF_PATH)
        else:
            return action.ActionResult()

        for package in self._list_of_packages_to_remove:
            leapp_configs.rm_package_from_pes_events(package, self._repo)
        return action.ActionResult()

    def _post_action(self) -> action.ActionResult:
        files.restore_file_from_backup(leapp_configs.LEAPP_PKGS_CONF_PATH)
        return action.ActionResult()

    def _revert_action(self) -> action.ActionResult:
        files.restore_file_from_backup(leapp_configs.LEAPP_PKGS_CONF_PATH)
        return action.ActionResult()

