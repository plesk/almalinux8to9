# Copyright 1999 - 2026. WebPros International GmbH. All rights reserved.

import argparse
import os
import typing

from pleskdistup import actions as common_actions
from pleskdistup.common import action, dist, feedback, files, packages, systemd, util, version
from pleskdistup.phase import Phase
from pleskdistup.messages import REBOOT_WARN_MESSAGE
from pleskdistup.upgrader import DistUpgrader, DistUpgraderFactory, PathType

import almalinux8to9.config
from almalinux8to9 import actions as custom_actions


class AlmaLinux8to9Upgrader(DistUpgrader):
    _distro_from = dist.AlmaLinux("8")
    _distro_to = dist.AlmaLinux("9")

    _pre_reboot_delay = 45

    _elevate_almalinux_rpm_url: str = "https://repo.almalinux.org/elevate/elevate-release-latest-el8.noarch.rpm"
    _leapp_vendors_postgres_repo: str = '/etc/leapp/files/vendors.d/postgresql.repo'
    _sha1_only_php_packages: typing.List[str] = ["plesk-php56", "plesk-php70", "plesk-php74", "plesk-php80"]


    def __init__(self):
        super().__init__()

        self.fix_deprecated_if_scripts = False
        self.upgrade_postgres_allowed = False
        self.remove_unknown_perl_modules = False
        self.disable_spamassasin_plugins = False
        self.amavis_upgrade_allowed = False
        self.leapp_ovl_size = 4096
        self.allow_raid_devices = False
        self.rm_sha1_plesk_packages = False
        self.remove_leapp_logs = False
        self.allow_old_script_version = False

    def __repr__(self) -> str:
        attrs = ", ".join(f"{k}={getattr(self, k)!r}" for k in (
            "_distro_from", "_distro_to",
        ))
        return f"{self.__class__.__name__}({attrs})"

    def __str__(self) -> str:
        return f"{self.__class__.__name__}"

    @classmethod
    def supports(
        cls,
        from_system: typing.Optional[dist.Distro] = None,
        to_system: typing.Optional[dist.Distro] = None
    ) -> bool:
        return (
            (from_system is None or cls._distro_from == from_system)
            and (to_system is None or cls._distro_to == to_system)
        )

    @property
    def upgrader_name(self) -> str:
        return "Plesk::AlmaLinux8to9Upgrader"

    @property
    def upgrader_version(self) -> str:
        if almalinux8to9.config.version:
            return almalinux8to9.config.version + "-" + almalinux8to9.config.revision[:8]
        return almalinux8to9.config.revision

    @property
    def issues_url(self) -> str:
        return "https://github.com/plesk/almalinux8to9/issues"

    def prepare_feedback(
        self,
        feed: feedback.Feedback,
    ) -> feedback.Feedback:

        feed.collect_actions += [
            feedback.collect_installed_packages_yum,
            feedback.collect_plesk_version,
            feedback.collect_kernel_modules,
        ]

        feed.attached_files += [
            "/etc/fstab",
            "/etc/grub2.cfg",
            "/etc/leapp/files/repomap.csv",
            "/etc/leapp/files/pes-events.json",
            "/etc/leapp/files/leapp_upgrade_repositories.repo",
            "/etc/named.conf",
            "/var/named/chroot/etc/named.conf",
            "/var/named/chroot/etc/named-user-options.conf",
            "/var/log/leapp/leapp-report.txt",
            "/var/log/leapp/leapp-preupgrade.log",
            "/var/log/leapp/leapp-upgrade.log",
        ]

        for grub_directory in ("/etc/grub.d", "/boot/grub", "/boot/grub2"):
            feed.attached_files += files.find_files_case_insensitive(grub_directory, ["*"])

        for repofile in files.find_files_case_insensitive("/etc/yum.repos.d", ["*.repo*"]):
            feed.attached_files.append(repofile)

        for gpgfile in files.find_files_case_insensitive("/etc/leapp/files/vendors.d/rpm-gpg", ["*"]):
            feed.attached_files.append(gpgfile)

        for gpgfile in files.find_files_case_insensitive("/etc/leapp/repos.d/system_upgrade/common/files/rpm-gpg", ["*"], recursive=True):
            feed.attached_files.append(gpgfile)

        return feed

    def construct_actions(
        self,
        upgrader_bin_path: PathType,
        options: typing.Any,
        phase: Phase
    ) -> typing.Dict[str, typing.List[action.ActiveAction]]:
        new_os = str(self._distro_to)

        actions_map: typing.Dict[str, typing.List[action.ActiveAction]] = {
            "Status informing": [
                common_actions.HandleConversionStatus(options.status_flag_path, options.completion_flag_path),
                common_actions.AddFinishSshLoginMessage(new_os),  # Executed at the finish phase only
                common_actions.AddInProgressSshLoginMessage(new_os),
            ],
            "Leapp installation": [
                common_actions.RemoveLeappReposDisablement(),
                common_actions.LeappInstallation(
                    self._elevate_almalinux_rpm_url,
                    [
                        "leapp-0.20.0-1.el8_10",
                        "leapp-data-almalinux-0.10-9.el8.20250729",
                        "leapp-deps-0.20.0-1.el8_10",
                        "leapp-upgrade-el8toel9-0.23.0-1.el8.elevate.1.1",
                        "leapp-upgrade-el8toel9-deps-0.23.0-1.el8.elevate.1.1",
                        "python3-leapp-0.20.0-1.el8_10",
                    ],
                    remove_logs_on_finish=self.remove_leapp_logs
                ),
            ],
            "Prepare finishing systemd service": [
                common_actions.AddUpgradeSystemdService(
                    os.path.abspath(upgrader_bin_path),
                    options,
                    service_name = common_actions.DEFAULT_RESUME_SERVICE_NAME,
                    remove_service_in_post = False, # will be removed before reboot
                ),
            ],
            "Prepare configurations": [
                common_actions.RevertChangesInGrub(),
                custom_actions.RemoveOldPostgresRepoDefs(self._leapp_vendors_postgres_repo),
                custom_actions.PrepareLeappConfigurationBackup(),
                custom_actions.RemoveOldMigratorThirdparty(),
                custom_actions.FetchKernelCareGPGKey(),
                custom_actions.FetchPleskGPGKey(),
                custom_actions.FetchImunifyGPGKey(),
                custom_actions.PleskMainRepoTemporary(),
                custom_actions.LeappReposConfiguration(),
                custom_actions.LeappChoicesConfiguration(),
                custom_actions.AdoptKolabRepositories(),
                custom_actions.AdoptAtomicRepositories(),
                custom_actions.FixupImunify(),
                common_actions.UpdatePlesk(),
                custom_actions.PostgresReinstallModernPackage(),
                common_actions.FixNamedConfig(),
                common_actions.DisablePleskSshBanner(),
                common_actions.SetMinDovecotDhParamSize(dhparam_size=2048),
                common_actions.RestoreDovecotConfiguration(options.state_dir),
                common_actions.RestoreRoundcubeConfiguration(options.state_dir),
                common_actions.RecreateAwstatsConfigurationFiles(),
                common_actions.UninstallTuxcareEls(),
                common_actions.UninstallExtension("tuxcare-php"),
                common_actions.PreserveMariadbConfig(),
                common_actions.SubstituteSshPermitRootLoginConfigured(),
                custom_actions.UseSystemResolveForLeappContainer(),
            ],
            "Handle plesk related services": [
                common_actions.DisablePleskRelatedServicesDuringUpgrade(),
                common_actions.DisableServiceDuringUpgrade("mailman.service"),
                common_actions.HandlePleskFirewallService(),
            ],
            "Handle packages and services": [
                common_actions.RemovePleskComponents(
                    ["webalizer"], options.state_dir, "rm webalizer component",
                ),
                custom_actions.FixOsVendorPhpFpmConfiguration(),
                common_actions.RebundleRubyApplications(),
                custom_actions.ReinstallPhpmyadminPleskComponents(),
                custom_actions.ReinstallRoundcubePleskComponents(),
                custom_actions.ReinstallConflictPackages(options.state_dir),
                custom_actions.ReinstallPerlCpanModules(options.state_dir),
                common_actions.DisableSuspiciousKernelModules(),
                common_actions.HandleUpdatedSpamassassinConfig(),
                common_actions.DisableSelinuxDuringUpgrade(),
                custom_actions.RestoreMissingNginx(),
                common_actions.ReinstallAmavisAntivirus(),
                custom_actions.HandleInternetxRepository(),
            ],
            "First plesk start": [
                common_actions.StartPleskBasicServices(),
            ],
            "Remove conflicting packages": [
                custom_actions.RemovingPleskConflictPackages(),
                custom_actions.RemovePleskOutdatedPackages(),
            ],
            "Update databases": [
                custom_actions.UpdateModernMariadb(),
                custom_actions.AddMysqlConnector(),
            ],
            "Repositories handling": [
                custom_actions.SetRPMCryptoPolicy(self._sha1_only_php_packages, "LEGACY"),
                custom_actions.AdoptRepositories(),
                custom_actions.PostEnableRepos(["crb"]),
                custom_actions.DisablePesEventsRemovePackages(["libidn"]),
            ],
            "Do convert": [
                custom_actions.DisableBaseRepoUpdatesRepository(),
                custom_actions.RemovePleskBaseRepository(),
                custom_actions.DoAlmaLinux8to9Convert(),
            ],
            "Resume": [
                common_actions.RestoreInProgressSshLoginMessage(new_os),
            ],
            "Pause before reboot": [
            ],
            "Reboot": [
                common_actions.Reboot(
                    prepare_next_phase=Phase.FINISH,
                    post_reboot=action.RebootType.AFTER_LAST_STAGE,
                    name="reboot and perform finishing actions",
                    do_before_post_reboot=lambda: \
                        systemd.remove_systemd_service(common_actions.DEFAULT_RESUME_SERVICE_NAME)
                )
            ]
        }

        if self.fix_deprecated_if_scripts:
            actions_map = util.merge_dicts_of_lists(actions_map, {
                "Prepare configurations": [
                    custom_actions.FixDeprecatedIFScripts(),
                ]
            })

        if self.rm_sha1_plesk_packages:
            actions_map = util.merge_dicts_of_lists(actions_map, {
                "Handle packages and services": [
                    custom_actions.RemovePleskSHA1Packages(),
                ]
            })

        if not options.no_reboot:
            actions_map = util.merge_dicts_of_lists(actions_map, {
                "Pause before reboot": [
                    common_actions.PreRebootPause(
                        REBOOT_WARN_MESSAGE.format(delay=self._pre_reboot_delay, util_name="almalinux8to9"),
                        self._pre_reboot_delay
                    ),
                ]
            })

        if self.upgrade_postgres_allowed:
            actions_map = util.merge_dicts_of_lists(actions_map, {
                "Prepare configurations": [
                    custom_actions.PostgresDatabasesUpdate(),
                ]
            })

        return actions_map

    def get_check_actions(
        self,
        options: typing.Any,
        phase: Phase
    ) -> typing.List[action.CheckAction]:
        if phase is Phase.FINISH:
            return [custom_actions.AssertDistroIsAlmaLinux9()]

        FIRST_SUPPORTED_BY_ALMA_8_PHP_VERSION = "5.6"
        ALMALINUX9_AMAVIS_REQUIRED_RAM = int(1.5 * 1024 * 1024 * 1024)
        # From our experience it's better to have at least 5GB as the required minimum space to store packages,
        # however when more space is required we should check exactly what was requested.
        # Leapp_ovl_size in Mbs so we have to multiply
        REQUIRED_MINUMUM_SPACE_FOR_OVERLAY = max(5 * 1024 * 1024 * 1024, self.leapp_ovl_size * 1024 * 1024)

        checks = [
            common_actions.AssertPleskVersionIsAvailable(),
            common_actions.AssertPleskInstallerNotInProgress(),
            common_actions.AssertAvailableSpaceForLocation("/var/lib", REQUIRED_MINUMUM_SPACE_FOR_OVERLAY),
            common_actions.AssertAvailableSpaceForLocation("/boot", 100 * 1024 * 1024),  # 100M required minimum space to store bootloader
            common_actions.AssertMinPhpVersionInstalled(FIRST_SUPPORTED_BY_ALMA_8_PHP_VERSION),
            common_actions.AssertMinPhpVersionUsedByWebsites(FIRST_SUPPORTED_BY_ALMA_8_PHP_VERSION),
            common_actions.AssertMinPhpVersionUsedByCron(FIRST_SUPPORTED_BY_ALMA_8_PHP_VERSION),
            common_actions.AssertOsVendorPhpUsedByWebsites(FIRST_SUPPORTED_BY_ALMA_8_PHP_VERSION),
            common_actions.AssertGrub2Installed(),
            custom_actions.AssertNoMoreThenOneKernelNamedNIC(),
            custom_actions.AssertRedHatKernelInstalled(),
            custom_actions.AssertLastInstalledKernelInUse(),
            common_actions.AssertLocalRepositoryNotPresent(file_list = [
                    file for file in files.find_files_case_insensitive("/etc/yum.repos.d", "*.repo")
                    if os.path.basename(file) != "AlmaLinux-Media.repo"
                 ]),
            common_actions.AssertIPRepositoryNotPresent(),
            custom_actions.CheckNMUnreachableDevices(),
            # custom_actions.AssertCentosEOLedRepositoriesNotPresent(),
            common_actions.AssertNoRepositoryDuplicates(),
            common_actions.AssertPackageIsNotInstalled("plesk-php71",
                                                       "PHP-7.1 is not supported"),
            common_actions.AssertPackageIsNotInstalled("plesk-php72",
                                                       "PHP-7.2 is not supported"),
            common_actions.AssertPackageIsNotInstalled("plesk-php73",
                                                       "PHP-7.3 is not supported"),
            common_actions.AssertPackageIsNotInstalled("psa-qmail",
                                                       "QMail is not supported on AlmaLinux 9 - consider switching to Postfix before conversion"),
            custom_actions.AssertStatsToolNotUsed('webalizer'),
            custom_actions.AssertMariadbRepoAvailable(),
            common_actions.AssertMariadbRepoEnabled(
                custom_actions.MARIADB_VERSION_ON_ALMA,
                custom_actions.KNOWN_MARIADB_REPO_FILES,
            ),
            custom_actions.AssertModernPostgresRepositoryFilePresent(),
            common_actions.AssertNotInContainer(),
            custom_actions.AssertPackagesUpToDate(),
            custom_actions.AssertNoOutdatedLetsEncryptExtRepository(),
            custom_actions.AssertPleskRepositoriesNotNoneLink(),
            common_actions.AssertNoAbsoluteLinksInRoot(),
            # custom_actions.AssertMinGovernorMariadbVersion(custom_actions.FIRST_SUPPORTED_GOVERNOR_MARIADB_VERSION),
            # custom_actions.AssertGovernorMysqlNotInstalled(custom_actions.FIRST_SUPPORTED_GOVERNOR_MARIADB_VERSION),
            custom_actions.CheckSourcePointsToArchiveURL(),
            common_actions.AssertNoMoreThenOneKernelDevelInstalled(),
            common_actions.AssertEnoughRamForAmavis(ALMALINUX9_AMAVIS_REQUIRED_RAM, self.amavis_upgrade_allowed),
            common_actions.AssertSshPermitRootLoginConfigured(skip_known_substitudes=True),
            common_actions.AssertFstabOrderingIsFine(),
            common_actions.AssertFstabHasDirectRaidDevices(self.allow_raid_devices),
            common_actions.AssertFstabHasNoDuplicates(),
            # custom_actions.AssertCentosSignedKernelInstalled(),
            common_actions.AssertPackageAvailable(
                "dnf",
                name="asserting dnf package available",
                recommendation="""The dnf package is required for Leapp to function properly.
\tHint: You can install it using the AlmaLinux-8 BaseOS repository with the following base URL:
\t\t'baseurl=https://repo.almalinux.org/almalinux/8/BaseOS/x86_64/os/'"""
            ),
        ]

        if not self.fix_deprecated_if_scripts:
            checks.append(custom_actions.CheckDeprecatedIFScripts())
        if not self.upgrade_postgres_allowed:
            checks.append(custom_actions.AssertOutdatedPostgresNotInstalled())
        else:
            checks.append(custom_actions.AssertPostgresLocaleMatchesSystemOne())
        if not self.remove_unknown_perl_modules:
            checks.append(custom_actions.AssertThereIsNoUnknownPerlCpanModules())
        if not self.disable_spamassasin_plugins:
            checks.append(common_actions.AssertSpamassassinAdditionalPluginsDisabled())
        if not self.allow_old_script_version and almalinux8to9.config.version:
            checks.append(common_actions.AssertScriptVersionUpToDate("https://github.com/plesk/almalinux8to9", "almalinux8to9", version.DistupgradeToolVersion(almalinux8to9.config.version)))
        if not any(packages.is_package_installed(name) for name in self._sha1_only_php_packages):
            checks.append(
                custom_actions.AssertNoOldRPMSignatures(not self.rm_sha1_plesk_packages))

        return checks

    def parse_args(self, args: typing.Sequence[str]) -> None:
        DESC_MESSAGE = f"""Use this upgrader to convert {self._distro_from} server with Plesk to {self._distro_to}.
The process consists of the following general stages:

- Preparation (about 20 minutes) - The Leapp utility is installed and configured.
   The OS is prepared for the conversion. The Leapp utility is then called to
   create a temporary OS distribution.
- Conversion (about 20 minutes) - The conversion takes place. During this stage,
   you cannot connect to the server via SSH.
- Finalization (about 5 minutes) - The server is returned to normal operation.

To see the detailed plan, run the utility with the --show-plan option.

For assistance, submit an issue here {self.issues_url}
and attach the feedback archive generated with --prepare-feedback or at least
the log file.
"""
        parser = argparse.ArgumentParser(
            usage=argparse.SUPPRESS,
            description=DESC_MESSAGE,
            formatter_class=argparse.RawDescriptionHelpFormatter,
            add_help=False,
        )
        parser.add_argument(
            "-h", "--help", action="help", default=argparse.SUPPRESS,
            help=argparse.SUPPRESS
        )
        parser.add_argument(
            "--fix-deprecated-if-scripts", action="store_true", dest="fix_deprecated_if_scripts", default=False,
            help="Fix deprecated custom network scripts. Custom network scripts in /sbin/if*-local are deprecated and may not work properly on AlmaLinux 9. By enabling this option, the utility will create wrapper scripts that will call the original scripts if they exist and are executable."
        )
        parser.add_argument(
            "--upgrade-postgres", action="store_true", dest="upgrade_postgres_allowed", default=False,
            help="Upgrade all hosted PostgreSQL databases. To avoid data loss, create backups of all "
                 "hosted PostgreSQL databases before calling this option."
        )
        parser.add_argument(
            "--remove-unknown-perl-modules", action="store_true",
            dest="remove_unknown_perl_modules", default=False,
            help="Allow to remove unknown perl modules installed from CPAN. In this case all modules installed "
                 "by CPAN will be removed. Note that it could lead to some issues with perl scripts"
        )
        parser.add_argument(
            "--disable-spamassasin-plugins", action="store_true",
            dest="disable_spamassasin_plugins", default=False,
            help="Disable additional plugins in spamassasin configuration during the conversion."
        )
        parser.add_argument("--leapp-ovl-size", type=int, dest="leapp_ovl_size", default=4096,
                            help="Specify the overlay size for leapp in megabytes.")
        parser.add_argument("--amavis-upgrade-allowed", action="store_true", dest="amavis_upgrade_allowed", default=False,
                            help="Allow to upgrade amavis antivirus even if there is not enough RAM available.")
        parser.add_argument("--allow-raid-devices", action="store_true", dest="allow_raid_devices", default=False,
                            help="Allow to have direct RAID devices in /etc/fstab. This could lead to unbootable system after the conversion so use the option on your own risk.")
        parser.add_argument("--keep-leapp-logs", action="store_false", dest="remove_leapp_logs",
                            help="Don't remove leapp logs after the conversion. By default, the logs are removed after the conversion.")
        parser.add_argument("--allow-old-script-version", action="store_true", dest="allow_old_script_version", default=False,
                            help="Allow to run the script with an old version. By default, the script checks for a new version on GitHub and does not allow to run with an old one.")
        parser.add_argument(
            "--rm-sha1-plesk-packages", action="store_true",
            help="remove SHA1 signed old Plesk packages before conversion."
        )
        parser.set_defaults(remove_leapp_logs=False)
        options = parser.parse_args(args)

        self.upgrade_postgres_allowed = options.upgrade_postgres_allowed
        self.remove_unknown_perl_modules = options.remove_unknown_perl_modules
        self.disable_spamassasin_plugins = options.disable_spamassasin_plugins
        self.amavis_upgrade_allowed = options.amavis_upgrade_allowed
        self.leapp_ovl_size = options.leapp_ovl_size
        self.allow_raid_devices = options.allow_raid_devices
        self.rm_sha1_plesk_packages = options.rm_sha1_plesk_packages
        self.remove_leapp_logs = options.remove_leapp_logs
        self.allow_old_script_version = options.allow_old_script_version
        self.fix_deprecated_if_scripts = options.fix_deprecated_if_scripts


class AlmaLinux8to9Factory(DistUpgraderFactory):
    def __init__(self):
        super().__init__()

    def __repr__(self) -> str:
        return f"{self.__class__.__name__}(upgrader_name={self.upgrader_name})"

    def __str__(self) -> str:
        return f"{self.__class__.__name__} (creates {self.upgrader_name})"

    def supports(
        self,
        from_system: typing.Optional[dist.Distro] = None,
        to_system: typing.Optional[dist.Distro] = None
    ) -> bool:
        return AlmaLinux8to9Upgrader.supports(from_system, to_system)

    @property
    def upgrader_name(self) -> str:
        return "Plesk::AlmaLinux8to9Upgrader"

    def create_upgrader(self, *args, **kwargs) -> DistUpgrader:
        return AlmaLinux8to9Upgrader(*args, **kwargs)
