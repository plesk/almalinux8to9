# Copyright 1999 - 2026. WebPros International GmbH. All rights reserved.
import os
import typing
import shutil
import re
from functools import partial

from pleskdistup.common import action, files, leapp_configs, log, motd, packages, plesk, rpm, systemd, util
from .common import get_adapted_repository

BASE_REPO_PATHS = ["/etc/yum.repos.d/base.repo", "/etc/yum.repos.d/almalinux-base.repo"]


class PostEnableRepos(action.ActiveAction):
    repos: typing.List[str]

    def __init__(self, repos: typing.List[str]) -> None:
        self.name = f"post enable repos: '{repos}'"
        self.repos = repos

    def _prepare_action(self) -> action.ActionResult:
        return action.ActionResult()

    def _post_action(self) -> action.ActionResult:
        for r in self.repos:
            util.logged_check_call(["/usr/bin/dnf", "config-manager", "--set-enabled", r])
        return action.ActionResult()

    def _revert_action(self) -> action.ActionResult:
        return action.ActionResult()


class RemovingPleskConflictPackages(action.ActiveAction):
    conflict_pkgs: typing.List[str]

    def __init__(self) -> None:
        self.name = "remove plesk conflict packages"
        self.conflict_pkgs = [
            "GeoIP",
        ]

    def _prepare_action(self) -> action.ActionResult:
        packages.remove_packages(rpm.filter_installed_packages(self.conflict_pkgs))
        return action.ActionResult()

    def _post_action(self) -> action.ActionResult:
        return action.ActionResult()

    def _revert_action(self) -> action.ActionResult:
        packages.install_packages(self.conflict_pkgs)
        return action.ActionResult()

    def estimate_prepare_time(self) -> int:
        return 2

    def estimate_revert_time(self) -> int:
        return 10


class RemovePleskOutdatedPackages(action.ActiveAction):
    outdated_pkgs: typing.List[str]

    def __init__(self) -> None:
        self.name = "remove plesk outdated packages"
        self.outdated_pkgs = [
            "psa-fileserver",
        ]

    def _prepare_action(self) -> action.ActionResult:
        packages.remove_packages(rpm.filter_installed_packages(self.outdated_pkgs))
        return action.ActionResult()

    def _post_action(self) -> action.ActionResult:
        return action.ActionResult()

    def _revert_action(self) -> action.ActionResult:
        # This packages are outdated so they not provided by modern Plesk repositories
        # So we can't reinstall them on revert, and seems like there is no need to do that anyway
        return action.ActionResult()

    def estimate_prepare_time(self) -> int:
        return 2


class ReinstallPhpmyadminPleskComponents(action.ActiveAction):
    def __init__(self) -> None:
        self.name = "re-installing plesk components"

    def _prepare_action(self) -> action.ActionResult:
        components_pkgs = [
            "psa-phpmyadmin",
        ]

        packages.remove_packages(rpm.filter_installed_packages(components_pkgs))
        return action.ActionResult()

    def _post_action(self) -> action.ActionResult:
        # We should reinstall psa-phpmyadmin over plesk installer to make sure every trigger
        # will be called. It's because triggers that creates phpmyadmin configuration files
        # expect plesk on board. Hence when we install the package in scope of temporary OS
        # the file can't be created.
        phpmyadmin_package_name: str = "psa-phpmyadmin"
        if packages.is_package_installed(phpmyadmin_package_name):
            packages.remove_packages([phpmyadmin_package_name])

        util.logged_check_call(["/usr/sbin/plesk", "installer", "update"])

        return action.ActionResult()

    def _revert_action(self) -> action.ActionResult:
        util.logged_check_call(["/usr/sbin/plesk", "installer", "update"])
        systemd.restart_services(["sw-cp-server"])
        return action.ActionResult()

    def estimate_prepare_time(self) -> int:
        return 10

    def estimate_post_time(self) -> int:
        return 60

    def estimate_revert_time(self) -> int:
        return 3 * 60


class ReinstallRoundcubePleskComponents(action.ActiveAction):
    def __init__(self):
        self.name = "re-installing roundcube plesk components"

    def is_required(self) -> bool:
        return plesk.is_component_installed("roundcube")

    def _prepare_action(self) -> action.ActionResult:
        packages.remove_packages(rpm.filter_installed_packages(["plesk-roundcube"]))
        return action.ActionResult()

    def _post_action(self) -> action.ActionResult:
        util.logged_check_call(["/usr/sbin/plesk", "installer", "add", "--components", "roundcube"])
        return action.ActionResult()

    def _revert_action(self) -> action.ActionResult:
        util.logged_check_call(["/usr/sbin/plesk", "installer", "add", "--components", "roundcube"])
        systemd.restart_services(["sw-cp-server"])
        return action.ActionResult()

    def estimate_prepare_time(self):
        return 10

    def estimate_post_time(self):
        return 60

    def estimate_revert_time(self):
        return 3 * 60


class ReinstallConflictPackages(action.ActiveAction):
    removed_packages_file: str
    conflict_pkgs_map: typing.Dict[str, str]

    def __init__(self, temp_directory: str):
        self.name = "re-installing common conflict packages"
        self.removed_packages_file = temp_directory + "/almalinux8to9_removed_packages.txt"
        self.conflict_pkgs_map = {
            "python36-argcomplete": "python3-argcomplete",
            "python36-cffi": "python3-cffi",
            "python36-chardet": "python3-chardet",
            "python36-colorama": "python3-colorama",
            "python36-cryptography": "python3-cryptography",
            "python36-pycurl": "python3-pycurl",
            "python36-dateutil": "python3-dateutil",
            "python36-dbus": "python3-dbus",
            "python36-decorator": "python3-decorator",
            "python36-gobject-base": "python3-gobject-base",
            "python36-idna": "python3-idna",
            "python36-jinja2": "python3-jinja2",
            "python36-jsonschema": "python3-jsonschema",
            "python36-jwt": "python3-jwt",
            "python36-lxml": "python3-lxml",
            "python36-markupsafe": "python3-markupsafe",
            "python36-pyOpenSSL": "python3-pyOpenSSL",
            "python36-ply": "python3-ply",
            "python36-prettytable": "python3-prettytable",
            "python36-pycparser": "python3-pycparser",
            "python36-pyparsing": "python3-pyparsing",
            "python36-pyserial": "python3-pyserial",
            "python36-pytz": "python3-pytz",
            "python36-requests": "python3-requests",
            "python36-six": "python3-six",
            "python36-urllib3": "python3-urllib3",
            "libpcap": "libpcap",
            "libwebp7": "libwebp",
            "libzip5": "libzip",
            "libytnef": "ytnef",
            "imunify360-webshield-bundle": "imunify360-webshield-bundle",
        }

    def _is_required(self) -> bool:
        return len(rpm.filter_installed_packages(list(self.conflict_pkgs_map.keys()))) > 0

    def _prepare_action(self) -> action.ActionResult:
        packages_to_remove = rpm.filter_installed_packages(list(self.conflict_pkgs_map.keys()))

        rpm.remove_packages(packages_to_remove)

        with open(self.removed_packages_file, "a") as f:
            f.write("\n".join(packages_to_remove) + "\n")

        return action.ActionResult()

    def _post_action(self) -> action.ActionResult:
        if not os.path.exists(self.removed_packages_file):
            log.warn("File with removed packages list does not exist. While the action itself was not skipped. Skip reinstalling packages.")
            return action.ActionResult()

        if os.path.getsize(self.removed_packages_file) > 0:
            with open(self.removed_packages_file, "r") as f:
                packages_to_install = [self.conflict_pkgs_map[pkg] for pkg in set(f.read().splitlines())]
                rpm.install_packages(packages_to_install)

        os.unlink(self.removed_packages_file)
        return action.ActionResult()

    def _revert_action(self) -> action.ActionResult:
        if not os.path.exists(self.removed_packages_file):
            log.warn("File with removed packages list does not exist. While the action itself was not skipped. Skip reinstalling packages.")
            return action.ActionResult()

        if os.path.getsize(self.removed_packages_file) > 0:
            with open(self.removed_packages_file, "r") as f:
                packages_to_install = list(set(f.read().splitlines()))
                rpm.install_packages(packages_to_install)

        os.unlink(self.removed_packages_file)
        return action.ActionResult()

    def estimate_prepare_time(self) -> int:
        return 10

    @property
    def _removed_packages_num(self) -> int:
        if os.path.exists(self.removed_packages_file):
            with open(self.removed_packages_file, "r") as f:
                return len(f.read().splitlines())
        return 0

    def estimate_post_time(self) -> int:
        return 60 + 10 * self._removed_packages_num

    def estimate_revert_time(self) -> int:
        return 60 + 10 * self._removed_packages_num


CHANGED_REPOS_MSG_FMT = """During the conversion, some of customized .repo files were updated. You can find the old
files with the .rpmsave extension. Below is a list of the changed files:
\t{changed_files}
"""


class AdoptRepositories(action.ActiveAction):
    def __init__(self) -> None:
        self.name = "adopting repositories"

    def _prepare_action(self) -> action.ActionResult:
        return action.ActionResult()

    def _use_rpmnew_repositories(self) -> None:
        # The problem is about changed repofiles, that leapp is trying to install from packages.
        # For example, when epel.repo file was changed, dnf will save the new one as epel.repo.rpmnew.
        # I beleive there could be other files with the same problem, so let's iterate every .rpmnew file in /etc/yum.repos.d
        fixed_list = []
        for file in files.find_files_case_insensitive("/etc/yum.repos.d", ["*.rpmnew"]):
            original_file = file[:-len(".rpmnew")]
            if os.path.exists(original_file):
                shutil.move(original_file, original_file + ".rpmsave")
                fixed_list.append(original_file)

            shutil.move(file, original_file)

        if len(fixed_list) > 0:
            motd.add_finish_ssh_login_message(CHANGED_REPOS_MSG_FMT.format(changed_files="\n\t".join(fixed_list)))

    def _adopt_plesk_repositories(self) -> None:
        for file in files.find_files_case_insensitive("/etc/yum.repos.d", ["plesk*.repo"]):
            rpm.remove_repositories(file, [
                lambda repo: repo.id in ["PLESK_17_PHP52", "PLESK_17_PHP53",
                                         "PLESK_17_PHP54", "PLESK_17_PHP55"],
            ])
            leapp_configs.adopt_repositories(file,
                                             do_adapt_repository=partial(get_adapted_repository, keep_id=False))

    def _adopt_base_repository(self) -> None:
        for path in BASE_REPO_PATHS:
            if os.path.exists(path):
                leapp_configs.adopt_repositories(path,
                                                do_adapt_repository=partial(get_adapted_repository, keep_id=False))

    def _post_action(self) -> action.ActionResult:
        self._use_rpmnew_repositories()
        self._adopt_plesk_repositories()
        self._adopt_base_repository()
        util.logged_check_call(["/usr/bin/dnf", "clean", "all"])
        util.logged_check_call(["/usr/bin/dnf", "-y", "update", "--disablerepo=elevate"])
        return action.ActionResult()

    def _revert_action(self) -> action.ActionResult:
        return action.ActionResult()

    def estimate_post_time(self) -> int:
        return 2 * 60


class RemovePleskBaseRepository(action.ActiveAction):
    # In some cases we have plesk specific base repository, which will not be
    # fixed by the leapp converter. So we have to remove it manually.
    base_repo_paths: typing.List[str] = BASE_REPO_PATHS

    def __init__(self) -> None:
        self.name = "removing base repository"

    def _is_required(self) -> bool:
        return any(os.path.exists(path) for path in self.base_repo_paths)

    def _prepare_action(self) -> action.ActionResult:
        return action.ActionResult()

    def _is_plesk_base(self, repo_file: str) -> bool:
        for repo in rpm.extract_repodata(repo_file):
            if repo.url and "psabr.aws.plesk.tech/share/mirror/almalinux/8" in repo.url:
                log.info(f"Plesk base repo found in {repo_file!r} by repository {repo.id!r}")
                return True
        return False

    def _post_action(self) -> action.ActionResult:
        for path in self.base_repo_paths:
            if os.path.exists(path) and self._is_plesk_base(path):
                files.backup_file(path)
                os.unlink(path)
        return action.ActionResult()

    def _revert_action(self) -> action.ActionResult:
        return action.ActionResult()


class AssertPleskRepositoriesNotNoneLink(action.CheckAction):
    def __init__(self):
        self.name = "checking if plesk repositories does not have a 'none' link"
        self.description = """There are plesk repositories with link set to 'none'. To proceed with the conversion, remove following repositories:
\t- {}
"""

    def _do_check(self) -> bool:
        none_link_repos = []
        for file in files.find_files_case_insensitive("/etc/yum.repos.d", ["plesk*.repo"]):
            for repo in rpm.extract_repodata(file):
                if rpm.repository_has_none_link(repo):
                    none_link_repos.append(f"{repo.id!r} from repofile {file!r}")

        if len(none_link_repos) == 0:
            return True

        self.description = self.description.format("\n\t- ".join(none_link_repos))
        return False


class RemoveOldMigratorThirdparty(action.ActiveAction):
    def __init__(self) -> None:
        self.name = "removing old migrator thirdparty packages"

    def _find_migrator_repo_files(self) -> typing.List[str]:
        return files.find_files_case_insensitive("/etc/yum.repos.d", ["plesk*migrator*.repo"])

    def _is_required(self) -> bool:
        for file in self._find_migrator_repo_files():
            for repo in rpm.extract_repodata(file):
                if repo.url and "PMM_0.1.10/thirdparty-rpm" in repo.url:
                    return True

        return False

    def _prepare_action(self) -> action.ActionResult:
        for file in self._find_migrator_repo_files():
            files.backup_file(file)

            rpm.remove_repositories(file, [
                lambda repo: (repo.url is not None and "PMM_0.1.10/thirdparty-rpm" in repo.url),
            ])
        return action.ActionResult()

    def _post_action(self) -> action.ActionResult:
        for file in self._find_migrator_repo_files():
            files.remove_backup(file)
        return action.ActionResult()

    def _revert_action(self) -> action.ActionResult:
        for file in self._find_migrator_repo_files():
            files.restore_file_from_backup(file)
        return action.ActionResult()


class RestoreMissingNginx(action.ActiveAction):
    def __init__(self) -> None:
        self.name = "restore nginx if it was removed during the conversion"

    def _is_required(self) -> bool:
        # nginx related to plesk could be removed by user. So we need to make sure
        # it is installed before we start the conversion
        return packages.is_package_installed("sw-nginx")

    def _prepare_action(self) -> action.ActionResult:
        return action.ActionResult()

    def _post_action(self) -> action.ActionResult:
        if not packages.is_package_installed("sw-nginx"):
            util.logged_check_call(["/usr/sbin/plesk", "installer", "add", "--components", "nginx"])
        return action.ActionResult()

    def _revert_action(self) -> action.ActionResult:
        return action.ActionResult()

    def estimate_post_time(self) -> int:
        return 3 * 60


class AssertNoOutdatedLetsEncryptExtRepository(action.CheckAction):
    OUTDATED_LETSENCRYPT_REPO_PATHS = ["/etc/yum.repos.d/plesk-letsencrypt.repo", "/etc/yum.repos.d/plesk-ext-letsencrypt.repo"]

    def __init__(self) -> None:
        self.name = "checking if outdated repository for letsencrypt extension is used"
        self.description = """There is outdated repository for letsencrypt extension used.
\tTo resolve the problem perform following actions:
\t1. make sure the letsencrypt extension is up to date from Plesk web interface
\t2. rpm -qe plesk-letsencrypt-pre plesk-py27-pip plesk-py27-setuptools plesk-py27-virtualenv plesk-wheel-cffi plesk-wheel-cryptography plesk-wheel-psutil
\t3. rm {repo_paths}
"""

    def _do_check(self) -> bool:
        for path in self.OUTDATED_LETSENCRYPT_REPO_PATHS:
            if os.path.exists(path):
                self.description = self.description.format(repo_paths=path)
                return False
        return True


class AdoptAtomicRepositories(action.ActiveAction):
    atomic_repository_path: str = "/etc/yum.repos.d/tortix-common.repo"

    def __init__(self) -> None:
        self.name = "adopting atomic repositories"

    def _is_required(self) -> bool:
        return os.path.exists(self.atomic_repository_path)

    def _prepare_action(self) -> action.ActionResult:
        leapp_configs.add_repositories_mapping_json([self.atomic_repository_path],
                                               do_adapt_repository=partial(get_adapted_repository, keep_id=False),
                                               mapjson_path=leapp_configs.LEAPP_MAP_JSON_PATH,
                                               distro="almalinux",
                                               source_major_version="8",
                                               target_major_version="9")
        return action.ActionResult()

    def _post_action(self) -> action.ActionResult:
        # We don't need to adopt repositories here because repositories uses $releasever-$basearch
        return action.ActionResult()

    def _revert_action(self) -> action.ActionResult:
        return action.ActionResult()


class CheckSourcePointsToArchiveURL(action.CheckAction):
    AUTOINSTALLERRC_PATH = os.path.expanduser('~/.autoinstallerrc')

    def __init__(self):
        self.name = "checking if SOURCE points to old archive"
        self.description = f"""Old archive doesn't serve up-to-date Plesk.
\tEdit {self.AUTOINSTALLERRC_PATH} and change SOURCE - i.e. https://autoinstall.plesk.com
""".format(self)

    def _do_check(self) -> bool:
        if not os.path.exists(self.AUTOINSTALLERRC_PATH):
            return True
        p = re.compile(r'^\s*SOURCE\s*=\s*https?://autoinstall-archives.plesk.com')
        with open(self.AUTOINSTALLERRC_PATH) as f:
            for line in f:
                if p.search(line):
                    return False
        return True


class HandleInternetxRepository(action.ActiveAction):
    KNOWN_INTERNETX_REPO_FILES = ["internetx.repo"]

    def __init__(self):
        self.name = "handling InternetX repository"

    def is_required(self) -> bool:
        return len(files.find_files_case_insensitive("/etc/yum.repos.d", self.KNOWN_INTERNETX_REPO_FILES)) > 0

    def _prepare_action(self) -> action.ActionResult:
        for file in files.find_files_case_insensitive("/etc/yum.repos.d", self.KNOWN_INTERNETX_REPO_FILES):
            files.backup_file(file)
            leapp_configs.add_repositories_mapping_json([file],
                                                   do_adapt_repository=partial(get_adapted_repository, keep_id=False),
                                                   mapjson_path=leapp_configs.LEAPP_MAP_JSON_PATH,
                                                   distro="almalinux",
                                                   source_major_version="8",
                                                   target_major_version="9")
        return action.ActionResult()

    def _post_action(self) -> action.ActionResult:
        for file in files.find_files_case_insensitive("/etc/yum.repos.d", self.KNOWN_INTERNETX_REPO_FILES):
            files.remove_backup(file)
            leapp_configs.adopt_repositories(file,
                                            do_adapt_repository=partial(get_adapted_repository, keep_id=False))
        return action.ActionResult()

    def _revert_action(self) -> action.ActionResult:
        for file in files.find_files_case_insensitive("/etc/yum.repos.d", self.KNOWN_INTERNETX_REPO_FILES):
            files.restore_file_from_backup(file)
        return action.ActionResult()


class DisableBaseRepoUpdatesRepository(action.ActiveAction):
    base_repo_paths: list = BASE_REPO_PATHS

    def __init__(self) -> None:
        self.name = "disabling updates repository"

    def _prepare_action(self) -> action.ActionResult:
        return action.ActionResult()

    def _post_action(self) -> action.ActionResult:
        for path in self.base_repo_paths:
            if os.path.exists(path):
                rpm.remove_repositories(path, [
                    lambda repo: repo.url is not None and "mirror.pp.plesk.tech/almalinux/8/updates" in repo.url,
                ])
        return action.ActionResult()

    def _revert_action(self) -> action.ActionResult:
        return action.ActionResult()


class SetRPMCryptoPolicy(action.ActiveAction):
    policy: str
    due_to_packages: typing.List[str]

    def __init__(self,
                 all_possible_packages: typing.List[str],
                 policy: str) -> None:
        self.policy = policy
        self.due_to_packages = packages.filter_installed_packages(all_possible_packages)

        self.name = f'set RPM crypto policy to "{self.policy}" due to installed packages: {", ".join(self.due_to_packages)}'
        self.description = f'''We need to switch to {self.policy} crypto policy due to following legacy packages'
conversion support. These packages will prevent the conversion if policy is not set to old mode.
Consider removing them using plesk installer if they are not utilized by plesk or your domains.
\t {", ".join(self.due_to_packages)}
'''

    def is_required(self) -> bool:
        return bool(self.due_to_packages)

    def _prepare_action(self) -> action.ActionResult:
        util.logged_check_call(
            ["/usr/bin/update-crypto-policies", "--set", f"{self.policy}"]
        )
        return action.ActionResult()

    def _post_action(self) -> action.ActionResult:
        util.logged_check_call(
            ["/usr/bin/update-crypto-policies", "--set", "DEFAULT"]
        )
        return action.ActionResult()

    def _revert_action(self) -> action.ActionResult:
        util.logged_check_call(
            ["/usr/bin/update-crypto-policies", "--set", "DEFAULT"]
        )
        return action.ActionResult()

