# Copyright 1999 - 2026. WebPros International GmbH. All rights reserved.

import typing
from functools import partial

from pleskdistup import actions as common_actions
from pleskdistup.common import action, files, leapp_configs, packages, systemd, util
from .common import get_adapted_repository


class FixupImunify(action.ActiveAction):
    def __init__(self):
        self.name = "fixing up imunify360"

    def _find_imunify_repo_files(self) -> typing.List[str]:
        return files.find_files_case_insensitive("/etc/yum.repos.d", ["imunify*.repo"])

    def _is_required(self) -> bool:
        return len(self._find_imunify_repo_files()) > 0

    def _prepare_action(self) -> action.ActionResult:
        repofiles = self._find_imunify_repo_files()

        leapp_configs.add_repositories_mapping_json(repofiles,
                                               do_adapt_repository=partial(get_adapted_repository, keep_id=False),
                                               mapjson_path=leapp_configs.LEAPP_MAP_JSON_PATH,
                                               distro="almalinux",
                                               source_major_version="8",
                                               target_major_version="9")

        # For some reason leapp replaces the libssh2 package on installation. It's fine in most cases,
        # but imunify packages require libssh2. So we should use PRESENT action to keep it.
        leapp_configs.set_package_action("libssh2", leapp_configs.LeappActionType.PRESENT)
        return action.ActionResult()

    def _post_action(self) -> action.ActionResult:
        return action.ActionResult()

    def _revert_action(self) -> action.ActionResult:
        return action.ActionResult()


class AdoptKolabRepositories(action.ActiveAction):
    def __init__(self):
        self.name = "adopting kolab repositories"

    def _find_kolab_repo_files(self) -> typing.List[str]:
        return files.find_files_case_insensitive("/etc/yum.repos.d", ["kolab*.repo"])

    def _is_required(self) -> bool:
        return len(self._find_kolab_repo_files()) > 0

    def _prepare_action(self) -> action.ActionResult:
        repofiles = self._find_kolab_repo_files()

        leapp_configs.add_repositories_mapping_json(
            repofiles,
            ignore=[
                "kolab-16-source",
                "kolab-16-testing-source",
                "kolab-16-testing-candidate-source",
            ],
            do_adapt_repository=partial(get_adapted_repository, keep_id=False),
            mapjson_path=leapp_configs.LEAPP_MAP_JSON_PATH,
            distro="almalinux",
            source_major_version="8",
            target_major_version="9",
        )
        return action.ActionResult()

    def _post_action(self) -> action.ActionResult:
        for file in self._find_kolab_repo_files():
            leapp_configs.adopt_repositories(file,
                                            do_adapt_repository=partial(get_adapted_repository, keep_id=False))

        util.logged_check_call(["/usr/bin/dnf", "-y", "update"])
        return action.ActionResult()

    def _revert_action(self) -> action.ActionResult:
        return action.ActionResult()

    def estimate_prepare_time(self) -> int:
        return 30

    def estimate_post_time(self) -> int:
        return 2 * 60


class FetchKernelCareGPGKey(common_actions.FetchGPGKeyForLeapp):
    def __init__(self):
        self.name = "fetching KernelCare GPG key"
        self.target_repository_files_regex = ["kernelcare*.repo"]
        super().__init__()


class FetchPleskGPGKey(common_actions.FetchGPGKeyForLeapp):
    def __init__(self):
        self.name = "fetching Plesk GPG key"
        self.target_repository_files_regex = ["plesk*.repo"]
        super().__init__()


class FetchImunifyGPGKey(common_actions.FetchGPGKeyForLeapp):
    def __init__(self):
        self.name = "fetching Imunify360 GPG key"
        self.target_repository_files_regex = ["imunify*.repo"]
        super().__init__()


class AdoptSOGo(action.ActiveAction):
    def __init__(self):
        self.name = "adopting SOGo extension"
        self.sogo_config = "/etc/sogo/sogo.conf"
        self.sogo_repo_file = "/etc/yum.repos.d/plesk-ext-sogo.repo"

    def _is_required(self) -> bool:
        return packages.is_package_installed("sogo")

    def _prepare_action(self) -> action.ActionResult:
        files.backup_file(self.sogo_config)
        return action.ActionResult()

    def fix_permissions(self) -> None:
        target_dirs = ["/run/sogo", "/var/lib/sogo/", "/var/log/sogo/", "/var/spool/sogo/", "/etc/sogo/"]
        for target_dir in target_dirs:
            files.change_directory_ownership(target_dir, "sogo", "sogo", recursive=True)
        files.change_file_ownership(self.sogo_config, "sogo", "sogo")

    def _post_action(self) -> action.ActionResult:
        # This temporarily replaces systemctl with a no-op stub, allowing
        # post-install scripts to run without disrupting the conversion service
        # by calling the systemd daemon-reload operation.
        with systemd.systemctl_stub():
            packages.install_packages(["sogo", "sogo-tool"])

        files.restore_file_from_backup(self.sogo_config)
        self.fix_permissions()

        systemd.enable_services(["sogod"])
        return action.ActionResult()

    def _revert_action(self) -> action.ActionResult:
        files.restore_file_from_backup(self.sogo_config)
        return action.ActionResult()

    def estimate_post_time(self) -> int:
        return 1 * 60
