# Copyright 1999 - 2026. WebPros International GmbH. All rights reserved.

import os
import subprocess
import typing

from pleskdistup.common import action, dist, log, rpm, version


class AssertDistroIsAlmaLinux9(action.CheckAction):
    def __init__(self) -> None:
        self.name = "checking if distro is AlmaLinux 9"
        self.description = "You are running a distribution other than AlmaLinux 9. The finalization stage can only be started on AlmaLinux 9."

    def _do_check(self) -> bool:
        return dist.get_distro() == dist.AlmaLinux("9")


class AssertNoMoreThenOneKernelNamedNIC(action.CheckAction):
    def __init__(self) -> None:
        self.name = "checking if there is more than one NIC interface using ketnel-name"
        self.description = """The system has one or more network interface cards (NICs) using kernel-names (ethX).
\tLeapp cannot guarantee the interface names' stability during the conversion.
\tGive those NICs persistent names (enpXsY) to proceed with the conversion.
\tInterfaces: {}
"""

    def _do_check(self) -> bool:
        # We can't use this method to get interfaces names, so just skip the check
        if not os.path.exists("/sys/class/net"):
            return True

        interfaces = os.listdir('/sys/class/net')
        suspicious_interfaces = [interface for interface in interfaces if interface.startswith("eth") and interface[3:].isdigit()]
        if len(suspicious_interfaces) > 1:
            self.description = self.description.format(", ".join(suspicious_interfaces))
            return False

        return True


# ToDo. Implement for deb-based and move to common part. Might be useful for distupgrade/other converters
class AssertLastInstalledKernelInUse(action.CheckAction):
    def __init__(self) -> None:
        self.name = "checking if the last installed kernel is in use"
        self.description = """The last installed kernel is not in use.
\tThe kernel version in use is '{}'. The last installed kernel version is '{}'.
\tReboot the system to use the last installed kernel.
"""

    def _get_kernel_version_in_use(self) -> version.KernelVersion:
        curr_kernel = subprocess.check_output(["/usr/bin/uname", "-r"], universal_newlines=True).strip()
        log.debug("Current kernel version is '{}'".format(curr_kernel))
        return version.KernelVersion(curr_kernel)

    def _get_last_installed_kernel_version(self) -> version.KernelVersion:
        versions = subprocess.check_output(
            [
                "/usr/bin/rpm", "-q", "-a", "kernel", "kernel-plus", "kernel-rt-core"
            ], universal_newlines=True
        ).splitlines()

        log.debug("Installed kernel versions: {}".format(', '.join(versions)))
        return max([version.KernelVersion(ver) for ver in versions])

    def _do_check(self) -> bool:
        last_installed_kernel_version = self._get_last_installed_kernel_version()
        used_kernel_version = self._get_kernel_version_in_use()

        if used_kernel_version != last_installed_kernel_version:
            self.description = self.description.format(str(used_kernel_version), str(last_installed_kernel_version))
            return False

        return True


class AssertRedHatKernelInstalled(action.CheckAction):
    def __init__(self) -> None:
        self.name = "checking if the Red Hat kernel is installed"
        self.description = """No Red Hat signed kernel is installed.
\tTo proceed with the conversion, install a kernel by running:
\t- 'yum install kernel kernel-tools kernel-tools-libs'
\tAfter installing the kernel fix the grub configuration by calling:
\t- `grub2-set-default 'AlmaLinux (newly_installed_kernel_version) 8 (Core)'`
\t- `grub2-mkconfig -o /boot/grub2/grub.cfg`
\t- `reboot`
"""

    def _do_check(self) -> bool:
        redhat_kernel_packages = subprocess.check_output(
            [
                "/usr/bin/rpm", "-q", "-a", "kernel", "kernel-rt"
            ], universal_newlines=True
        ).splitlines()
        return len(redhat_kernel_packages) > 0


class AssertPackagesUpToDate(action.CheckAction):
    def __init__(self):
        self.name = "checking if all packages are up to date"
        self.description = "There are packages which are not up to date. Call `yum update -y && reboot` to update the packages.\n"

    def _do_check(self) -> bool:
        subprocess.check_call(["/usr/bin/yum", "clean", "all"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        checker = subprocess.run(["/usr/bin/yum", "check-update"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        return checker.returncode == 0


class AssertNoOldRPMSignatures(action.CheckAction):
    _fail_for_plesk_packages: bool

    def __init__(self, fail_for_plesk_packages: bool = True):
        self._fail_for_plesk_packages = fail_for_plesk_packages
        self.name = "checking if all RPMs have modern SHA256 signing"
        self.description = "There are packages which are signed with old methods.\n\t"

    @classmethod
    def _could_be_leftover_package(cls, pkg_name: str, include_php: bool = False) -> bool:
        return ((pkg_name.startswith('plesk-php') if include_php else False) or
                (pkg_name.startswith('plesk-') and not pkg_name.startswith('plesk-php')) or
                pkg_name.startswith('sw-') or
                (pkg_name.startswith('pp') and pkg_name.endswith('-bootstrapper')))

    def _do_check(self) -> bool:
        packs = rpm.get_packages_with_sign_method('DSA/SHA1')
        if not packs:
            return True

        plesk_packs = []
        other_packs = []
        for name, ver in packs:
            if self._could_be_leftover_package(name):
                plesk_packs.append((name, ver))
            else:
                other_packs.append((name, ver))

        if self._fail_for_plesk_packages and plesk_packs:
            self.description += "- Found Plesk packages: autoremove those by passing '--rm-sha1-plesk-packages'\n\t"
        if not other_packs and not self._fail_for_plesk_packages:
            return True
        if other_packs:
            self.description += "- Consider remove/reinstall:\n\t\t{}".format(
                ' '.join([f"{name}-{ver}" for name, ver in other_packs]))
        return False

