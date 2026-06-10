# Copyright 1999 - 2026. WebPros International GmbH. All rights reserved.

import subprocess
import typing
import os
from functools import partial

from pleskdistup.common import action, leapp_configs, files, log, mariadb, rpm, util
from pleskdistup.actions.packages import RemovePackages
from .common import get_adapted_repository


MARIADB_VERSION_ON_ALMA = mariadb.MariaDBVersion("10.3.39")
KNOWN_MARIADB_REPO_FILES = [
    "mariadb.repo",
    "mariadb10.repo",
    "cl-mysql.repo"
]
MARIADB_PACKAGES = [
    "MariaDB-client",
    "MariaDB-client-compat",
    "MariaDB-compat",
    "MariaDB-common",
    "MariaDB-server",
    "MariaDB-server-compat",
    "MariaDB-shared"
]


def _find_mariadb_repo_files() -> typing.List[str]:
    return files.find_files_case_insensitive("/etc/yum.repos.d", KNOWN_MARIADB_REPO_FILES)


def _is_governor_mariadb_installed() -> bool:
    if not mariadb.is_mariadb_installed() and not mariadb.is_mysql_installed():
        return False

    repofiles = _find_mariadb_repo_files()
    for repofile in repofiles:
        for repo in rpm.extract_repodata(repofile):
            if repo.url and "repo.almalinux.com" in repo.url and ("cl-mariadb" in repo.url or "cl-mysql" in repo.url):
                return True

    return False


class AssertMariadbRepoAvailable(action.CheckAction):
    def __init__(self) -> None:
        self.name = "check mariadb repo available"
        self.description = """
The MariaDB repository with id '{}' from the file '{}' is not accessible.
\tThis issue may be caused by the deprecation of the currently installed MariaDB version or the disabling
\tof the MariaDB repository by the provider. To resolve this, update MariaDB to any version from the official
\trepository 'rpm.mariadb.org', or use the official archive repository for your current MariaDB version at 'archive.mariadb.org'.
"""

    def _do_check(self) -> bool:
        if not mariadb.is_mariadb_installed() or not mariadb.get_installed_mariadb_version() > MARIADB_VERSION_ON_ALMA:
            return True

        repofiles = _find_mariadb_repo_files()
        if len(repofiles) == 0:
            return True

        for repofile in repofiles:
            for repo in rpm.extract_repodata(repofile):
                if not repo.url or ".mariadb.org" not in repo.url:
                    continue

                # Since repository will be deprecated for any distro at once it looks fine to check only for 8 on x86_64
                repo_baseurl = repo.url.replace("$releasever", "8").replace("$basearch", "x86_64")
                result = subprocess.run(["curl", "-s", "-o", "/dev/null", "-f", repo_baseurl])
                if result.returncode != 0:
                    self.description = self.description.format(repo.id, repofile)
                    return False

        return True


def _remove_mariadb_packages() -> None:
    rpm.remove_packages(rpm.filter_installed_packages(MARIADB_PACKAGES))


class UpdateModernMariadb(RemovePackages):
    def __init__(self) -> None:
        super().__init__(MARIADB_PACKAGES,
                         "/usr/local/psa/var/almalinux8to9/dist-upgrader-mmariadb.list",
                         "update modern mariadb")

    def _is_required(self) -> bool:
        return (
            mariadb.is_mariadb_installed()
            and mariadb.get_installed_mariadb_version() > MARIADB_VERSION_ON_ALMA
            and not _is_governor_mariadb_installed()
        )

    def _prepare_action(self) -> action.ActionResult:
        repofiles = _find_mariadb_repo_files()
        if len(repofiles) == 0:
            raise Exception("Mariadb installed from unknown repository. Please check the '{}' file is present".format("/etc/yum.repos.d/mariadb.repo"))

        log.debug("Add MariaDB repository files '{}' mapping into leapp vendor directory".format(repofiles[0]))
        for repofile in repofiles:
            leapp_configs.create_leapp_vendor_repository_adoption(
                repofile,
                do_adapt_repository=partial(get_adapted_repository, keep_id=False),
                distro="almalinux", source_major_version="8", target_major_version="9",
            )

        log.debug("Set repository mapping in the leapp configuration file")
        leapp_configs.set_package_repository("mariadb", "mariadb-main")

        return super()._prepare_action()

    def _post_action(self) -> action.ActionResult:
        repofiles = _find_mariadb_repo_files()
        if len(repofiles) == 0:
            return action.ActionResult()

        for repofile in repofiles:
            leapp_configs.adopt_repositories(
                repofile,
                do_adapt_repository=partial(get_adapted_repository, keep_id=True))

        repo = [repo for repo in rpm.extract_repodata(repofiles[0])][0]

        packages = ["MariaDB-client", "MariaDB-server"]
        rpm.install_packages(packages, repository=repo.id, simulate=True)
        _remove_mariadb_packages()
        rpm.install_packages(packages, repository=repo.id)

        return super()._post_action()

    def estimate_prepare_time(self) -> int:
        return 30

    def estimate_post_time(self) -> int:
        return 60


class UpdateMariadbDatabase(RemovePackages):
    def __init__(self) -> None:
        super().__init__(MARIADB_PACKAGES,
                         "/usr/local/psa/var/almalinux8to9/dist-upgrader-smariadb.list",
                         "updating mariadb databases")

    def _is_required(self) -> bool:
        return (
            mariadb.is_mariadb_installed()
            and not mariadb.get_installed_mariadb_version() > MARIADB_VERSION_ON_ALMA
            and not _is_governor_mariadb_installed()
        )

    def _post_action(self) -> action.ActionResult:
        # Leapp does not remove non-standard MariaDB-client package. But since we have updated
        # mariadb to 10.3.35 old client is not relevant anymore. So we have to switch to new client.
        # On the other hand, we want to be sure AlmaLinux mariadb-server installed as well
        for repofile in _find_mariadb_repo_files():
            files.backup_file(repofile)
            os.unlink(repofile)

        packages = ["mariadb", "mariadb-server"]
        rpm.install_packages(packages, simulate=True)
        _remove_mariadb_packages()
        rpm.install_packages(packages)

        # We should be sure mariadb is started, otherwise restore wouldn't work
        util.logged_check_call(["/usr/bin/systemctl", "start", "mariadb"])

        # it could be missing due to implicit/automatic conversion support
        if os.path.isfile("/usr/bin/mysql_upgrade"):
            with open('/etc/psa/.psa.shadow', 'r') as shadowfile:
                shadowdata = shadowfile.readline().rstrip()
                util.logged_check_call(["/usr/bin/mysql_upgrade", "-uadmin", "-p" + shadowdata])
        # Also find a way to drop cookies, because it will ruin your day
        # We have to delete it once again, because leapp going to install it in scope of conversion process,
        # but without right configs
        return super()._post_action()

    def estimate_post_time(self) -> int:
        return 2 * 60


class AddMysqlConnector(action.ActiveAction):
    def __init__(self) -> None:
        self.name = "install mysql connector"

    def _is_required(self) -> bool:
        return mariadb.is_mysql_installed()

    def _prepare_action(self) -> action.ActionResult:
        return action.ActionResult()

    def _post_action(self) -> action.ActionResult:
        subprocess.check_call(["/usr/bin/dnf", "install", "-y", "mariadb-connector-c"])
        return action.ActionResult()

    def _revert_action(self) -> action.ActionResult:
        return action.ActionResult()

