# Copyright 1999 - 2026. WebPros International GmbH. All rights reserved.

import os
import shutil
import typing
from functools import partial

from pleskdistup.common import action, leapp_configs, files, rpm, util
from .common import get_adapted_repository


class PrepareLeappConfigurationBackup(action.ActiveAction):
    leapp_configs: typing.List[str]

    def __init__(self) -> None:
        self.name = "prepare leapp configuration backup"
        self.leapp_configs = ["/etc/leapp/files/leapp_upgrade_repositories.repo",
                              "/etc/leapp/files/repomap.csv",
                              "/etc/leapp/files/repomap.json",
                              "/etc/leapp/files/pes-events.json"]

    def _prepare_action(self) -> action.ActionResult:
        for file in self.leapp_configs:
            if os.path.exists(file):
                files.backup_file(file)

        return action.ActionResult()

    def _post_action(self) -> action.ActionResult:
        for file in self.leapp_configs:
            if os.path.exists(file):
                files.remove_backup(file)

        return action.ActionResult()

    def _revert_action(self) -> action.ActionResult:
        for file in self.leapp_configs:
            if os.path.exists(file):
                files.restore_file_from_backup(file)

        return action.ActionResult()


class PleskMainRepoTemporary(action.ActiveAction):

    def __init__(self) -> None:
        self.name = "temporarily create Plesk main repository"
        self.repo_filepath = "/etc/yum.repos.d/plesk-convert_tmp.repo"

    def _create_temporary_plesk_repo(self, repofiles: typing.List[str],
                                     repo_filepath: str) -> str:
        with open(repo_filepath, 'w') as repo_file:
            repo_file.write("# Automatically generated (temporary) by Plesk distribution upgrade script\n")
            for file in repofiles:
                if not os.path.exists(file):
                    continue

                for repo in rpm.extract_repodata(file):
                    if repo.enabled == "0":
                        continue
                    if repo.id is None or repo.name is None or repo.url is None \
                            or not repo.id.startswith("PLESK_18_0") \
                            or "extras" not in repo.id:
                        continue

                    dist_repo = rpm.Repository(
                        "alma8-" + repo.id.replace("-extras", ""),
                        name= "Alma XX " + repo.name.replace("extras", ""),
                        url=repo.url.replace("extras", "dist"),
                        metalink=None,
                        mirrorlist=None,
                        enabled="1\n",
                        gpgcheck="1\n",
                    )
                    repo_file.write(repr(dist_repo))
                    return dist_repo.id
        return ''

    def _prepare_action(self) -> action.ActionResult:
        repofiles = files.find_files_case_insensitive("/etc/yum.repos.d", ["plesk*.repo"])
        self._create_temporary_plesk_repo(repofiles, self.repo_filepath)
        # We need this update since plesk installer will not upgrade "same-version" packages
        # so these packages might be stuck at old DSA/SHA1 signed
        util.logged_check_call(["/usr/bin/dnf", "-y", "update", "--disablerepo=elevate"])
        return action.ActionResult()

    def _post_action(self) -> action.ActionResult:
        if os.path.exists(self.repo_filepath):
            os.unlink(self.repo_filepath)
        return action.ActionResult()

    def _revert_action(self) -> action.ActionResult:
        if os.path.exists(self.repo_filepath):
            os.unlink(self.repo_filepath)
        return action.ActionResult()

    def estimate_prepare_time(self) -> int:
        return 10


class LeappReposConfiguration(action.ActiveAction):

    def __init__(self) -> None:
        self.name = "map plesk repositories for leapp"

    def _prepare_action(self) -> action.ActionResult:
        repofiles = files.find_files_case_insensitive("/etc/yum.repos.d", ["plesk*.repo", "epel.repo"])

        leapp_configs.add_repositories_mapping_json(repofiles, ignore=[
            "PLESK_17_PHP52", "PLESK_17_PHP53", "PLESK_17_PHP54", "PLESK_17_PHP55"],
                                               do_adapt_repository=partial(get_adapted_repository, keep_id=False),
                                               mapjson_path=leapp_configs.LEAPP_MAP_JSON_PATH,
                                               distro="almalinux",
                                               source_major_version="8",
                                               target_major_version="9")
        return action.ActionResult()

    def _post_action(self) -> action.ActionResult:
        # Since only leap related files should be changed, there is nothing to do after on finishing stage
        return action.ActionResult()

    def _revert_action(self) -> action.ActionResult:
        return action.ActionResult()


class LeappChoicesConfiguration(action.ActiveAction):
    answer_file_path: str

    def __init__(self) -> None:
        self.name = "configure leapp user choices"
        self.answer_file_path = "/var/log/leapp/answerfile.userchoices"

    def _prepare_action(self) -> action.ActionResult:
        try:
            with open(self.answer_file_path, 'w') as userchoice:
                userchoice.write("[remove_pam_pkcs11_module_check]\nconfirm = True\n")
                userchoice.write("[check_vdo]\nconfirm = True\n")
        except FileNotFoundError:
            raise RuntimeError("Unable to create the leapp user answer file '{}'. Likely the script does not have "
                               "sufficient permissions to write in this directory. Please run the script as root "
                               "and use `setenforce 0` to disable selinux".format(self.answer_file_path))

        return action.ActionResult()

    def _post_action(self) -> action.ActionResult:
        if os.path.exists(self.answer_file_path):
            os.unlink(self.answer_file_path)
        return action.ActionResult()

    def _revert_action(self) -> action.ActionResult:
        return action.ActionResult()


class UseSystemResolveForLeappContainer(action.ActiveAction):
    path_to_src: str

    def __init__(self) -> None:
        self.name = "configure leapp container to use host's /etc/resolv.conf"
        self.path_to_resolve = "/etc/resolv.conf"
        self.path_to_src = "/etc/leapp/files/resolv.conf"

    def is_required(self) -> bool:
        return os.path.exists(self.path_to_resolve)

    def _prepare_action(self) -> action.ActionResult:
        shutil.copy(self.path_to_resolve, self.path_to_src)
        return action.ActionResult()

    def _post_action(self) -> action.ActionResult:
        return action.ActionResult()

    def _revert_action(self) -> action.ActionResult:
        return action.ActionResult()
