# Copyright 1999 - 2026. WebPros International GmbH. All rights reserved.
import glob
import os
import re
import shutil
import stat
import subprocess
import typing

from pleskdistup.common import action, log, motd, plesk, util

PSA_CONF = "/etc/psa/psa.conf"
SSHD_CONFIG = "/etc/ssh/sshd_config"
UPDATE_CHROOT_SCRIPT_URL = "https://raw.githubusercontent.com/plesk/kb-scripts/master/update-chroot/update-chroot.sh"

# Same set of programs the update-chroot.sh script (--install/--rebuild) puts into the template:
# https://raw.githubusercontent.com/plesk/kb-scripts/master/update-chroot/update-chroot.sh
CHROOT_PROGRAMS = [
    "bash", "cat", "chmod", "cp", "curl", "du", "false", "grep", "groups", "gunzip",
    "gzip", "head", "id", "less", "ln", "ls", "mkdir", "more", "mv", "pwd", "rm", "rmdir",
    "scp", "tail", "tar", "touch", "true", "unzip", "vi", "wget", "zip", "sh",
]

# name, mode, major, minor
CHROOT_DEVICES = [
    ("urandom", 0o444, 1, 9),
    ("random", 0o444, 1, 8),
    ("null", 0o666, 1, 3),
]

BINARY_FILETYPES = (
    "application/octet-stream",
    "application/x-executable",
    "application/x-sharedlib",
    "application/x-pie-executable",
)


def read_psa_conf_value(key: str, psa_conf: str = PSA_CONF) -> typing.Optional[str]:
    with open(psa_conf, "r") as f:
        for line in f:
            parts = line.split(None, 1)
            if len(parts) == 2 and parts[0] == key:
                return parts[1].strip()
    return None


def parse_ldd_output(output: str) -> typing.List[str]:
    """Returns absolute paths of the libraries (and the loader) listed by ldd."""
    libs: typing.List[str] = []
    for line in output.splitlines():
        line = line.strip()
        if "=>" in line:
            line = line.split("=>", 1)[1].strip()
        if not line.startswith("/"):
            # linux-vdso, 'not found' and similar entries have no real file
            continue
        libs.append(line.split()[0])
    return libs


def parse_sftp_server(sshd_config_content: str) -> typing.Optional[str]:
    for line in sshd_config_content.splitlines():
        m = re.match(r"^Subsystem\s+sftp\s+(\S+)", line)
        if m:
            return m.group(1)
    return None


def serialize_domains(domains: typing.List[typing.Tuple[str, str]]) -> str:
    return "\n".join(f"{name}\t{login}" for name, login in domains)


def deserialize_domains(content: str) -> typing.List[typing.Tuple[str, str]]:
    result = []
    for line in content.splitlines():
        parts = line.split("\t")
        if len(parts) == 2 and parts[0] and parts[1]:
            result.append((parts[0], parts[1]))
    return result


def _remove_path(path: str) -> None:
    if os.path.islink(path) or os.path.isfile(path):
        os.unlink(path)
    elif os.path.isdir(path):
        shutil.rmtree(path)


class ChrootTemplateBuilder:
    """Python port of the template building flow ('install_chroot_base') of
    https://raw.githubusercontent.com/plesk/kb-scripts/master/update-chroot/update-chroot.sh
    Ported from script version 1.6. When the script gets a new version, diff it against
    1.6 and update this class and RebuildChrootTemplates accordingly.

    Methods are named after the script functions they port (with a leading underscore), except:
    _copy_file/_copy_tree/_in_root (replace the COPY variable and path concatenation) and
    _install_chroot_programs (loop over the programs). '_create_node' is called directly for
    each of CHROOT_DEVICES instead of going through 'add_device'.

    Deviations from the script:
      - Debian/Ubuntu/CloudLinux specific branches are dropped, the tool is AlmaLinux only.
      - '--locales' (locale_init) is not ported, it is not a part of the script's '--rebuild'.
      - The template is built aside (<root>.new) and swapped in only on success,
        the script removes the old template first.
      - Programs found in the old template's bin/ are reinstalled by name. In the script's
        full_rebuild the glob is expanded after the old template is removed, so only
        the default programs are reinstalled there.
    """

    def __init__(self, root: str) -> None:
        self.root = root

    def _in_root(self, path: str) -> str:
        return os.path.join(self.root, path.lstrip("/"))

    @staticmethod
    def _copy_file(src: str, dst: str) -> None:
        # Equivalent of `cp -p -L -u`: follow symlinks, keep attributes, skip up-to-date files
        if os.path.isdir(dst):
            dst = os.path.join(dst, os.path.basename(src))
        if os.path.exists(dst) and os.stat(dst).st_mtime >= os.stat(src).st_mtime:
            return
        shutil.copy2(src, dst)

    def _copy_tree(self, src: str, dst_dir: str) -> None:
        # Equivalent of `cp -r -p -L -u src dst_dir`
        target = os.path.join(dst_dir, os.path.basename(src.rstrip("/")))
        for dirpath, _dirnames, filenames in os.walk(src, followlinks=True):
            rel = os.path.relpath(dirpath, src)
            dst = target if rel == "." else os.path.join(target, rel)
            os.makedirs(dst, exist_ok=True)
            for name in filenames:
                path = os.path.join(dirpath, name)
                if os.path.exists(path):  # skip dangling symlinks
                    self._copy_file(path, dst)

    def _install_chroot_skeleton(self) -> None:
        os.makedirs(self.root, mode=0o755)
        for d in ["dev", "etc", "lib", "usr", "usr/bin", "var", "usr/lib", "sbin"]:
            os.mkdir(self._in_root(d), 0o755)
        # Some OS's have /bin present as a symlink to /usr/bin
        if os.path.islink("/bin") and os.path.isdir("/bin"):
            os.symlink("usr/bin", self._in_root("bin"))
        else:
            os.mkdir(self._in_root("bin"), 0o755)
        for d in ["/lib64", "/usr/libexec", "/libexec"]:
            if os.path.isdir(d):
                os.mkdir(self._in_root(d), 0o755)
        for d in ["tmp", "var/tmp"]:
            os.mkdir(self._in_root(d))
            os.chmod(self._in_root(d), 0o1777)

    def _install_ld(self) -> None:
        for libdir in ["/lib", "/lib64"]:
            if not os.path.isdir(libdir):
                continue
            files = glob.glob(f"{libdir}/ld-linux*") + glob.glob(f"{libdir}/libnss_*.so.2")
            for f in files:
                self._copy_file(f, self._in_root(libdir))

    def _create_node(self, device: str, mode: int, dev_major: int, dev_minor: int) -> None:
        path = self._in_root(f"dev/{device}")
        if os.path.exists(path):
            log.warn(f"Device {device} already exists in template, skipping.")
            return
        os.mknod(path, stat.S_IFCHR | mode, os.makedev(dev_major, dev_minor))
        os.chmod(path, mode)  # mknod is subject to umask

    def _termcap_init(self) -> None:
        for src, dst in [("/etc/termcap", "/etc"), ("/etc/terminfo", "/etc"), ("/lib/terminfo", "/lib")]:
            if os.path.isdir(src):
                self._copy_tree(src, self._in_root(dst))
        if os.path.isdir("/usr/share/terminfo"):
            os.makedirs(self._in_root("/usr/share"), exist_ok=True)
            self._copy_tree("/usr/share/terminfo", self._in_root("/usr/share"))
        if os.path.isfile("/etc/inputrc"):
            self._copy_file("/etc/inputrc", self._in_root("/etc"))

    def _install_libs(self, program_path: str) -> None:
        proc = subprocess.run(
            ["ldd", program_path],
            stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, universal_newlines=True,
        )
        for lib in parse_ldd_output(proc.stdout):
            dst_dir = self._in_root(os.path.dirname(lib))
            os.makedirs(dst_dir, exist_ok=True)
            if not os.path.isfile(self._in_root(lib)):
                self._copy_file(lib, self._in_root(lib))

    @staticmethod
    def _get_path(program: str) -> typing.Optional[str]:
        if os.path.exists(program):
            return program
        path = shutil.which(program)
        if path is None:
            log.warn(f"Could not find {program}.")
        return path

    def _ldconfig_init(self) -> None:
        for f in glob.glob("/etc/ld.so.conf*"):
            if os.path.isdir(f):
                self._copy_tree(f, self._in_root("/etc"))
            else:
                self._copy_file(f, self._in_root("/etc"))
        self._install_chroot_program("ldconfig")

    def _install_chroot_program(self, program: str) -> None:
        path = self._get_path(program)
        if path is None:
            return
        proc = subprocess.run(
            ["file", "-Lib", path],
            stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, universal_newlines=True,
        )
        if proc.stdout.startswith(BINARY_FILETYPES):
            self._install_libs(path)
        else:
            log.warn(f"{path} is not a binary executable (filetype {proc.stdout.strip()}). Shared libraries will not be copied.")

        binary_dir = os.path.dirname(path)
        os.makedirs(self._in_root(binary_dir), exist_ok=True)
        self._copy_file(path, self._in_root(binary_dir))

        ldpath = self._get_path("ldconfig")
        if ldpath is not None:
            if not os.path.isfile(self._in_root(ldpath)):
                self._ldconfig_init()
            # Some applications might have lib-depends in unusual directories
            if os.path.isfile(self._in_root("/bin/sh")):
                util.logged_check_call(["chroot", self.root, "/bin/sh", "-c", "ldconfig"])

    def _install_chroot_programs(self, programs: typing.List[str]) -> None:
        for program in programs:
            self._install_chroot_program(program)

    def install_chroot_base(self, extra_programs: typing.List[str]) -> None:
        self._install_chroot_skeleton()
        os.chown(self.root, 0, 0)
        self._install_ld()
        for device, mode, dev_major, dev_minor in CHROOT_DEVICES:
            self._create_node(device, mode, dev_major, dev_minor)
        self._install_chroot_programs(CHROOT_PROGRAMS)

        # Get correct SFTP path and install it
        sftp_server = None
        if os.path.exists(SSHD_CONFIG):
            with open(SSHD_CONFIG, "r") as f:
                sftp_server = parse_sftp_server(f.read())
        if sftp_server:
            self._install_chroot_programs([sftp_server])
        else:
            log.warn(f"Could not find sftp-server path in {SSHD_CONFIG}, SFTP will not be added to chroot template")

        if os.path.exists("/etc/resolv.conf"):
            self._copy_file("/etc/resolv.conf", self._in_root("/etc"))
        self._termcap_init()
        for name in ("passwd", "group"):
            open(self._in_root(f"etc/{name}"), "a").close()

        # Reinstall programs added to the template by the administrator
        self._install_chroot_programs([p for p in extra_programs if p not in CHROOT_PROGRAMS])


class RebuildChrootTemplates(action.ActiveAction):
    """After the conversion, binaries and libraries inside Plesk chroot template and inside
    the chrooted domains are no longer compatible with the new OS (SFTP login fails).
    Rebuild the template and re-apply it to domains with chrooted shell, like
    '--rebuild' of https://raw.githubusercontent.com/plesk/kb-scripts/master/update-chroot/update-chroot.sh does.

    Domains are collected at the prepare stage and stored in a file, so Plesk database
    is not required at the post stage."""

    def __init__(self, store_dir: str) -> None:
        self.name = "rebuild chroot templates"
        self._domains_file = os.path.join(store_dir, "almalinux8to9_chrooted_domains.txt")

    def _read_psa_conf_value(self, var_name: str) -> str:
        val = read_psa_conf_value(var_name)
        if not val:
            raise RuntimeError(f"Could not extract {var_name} from {PSA_CONF}")
        return val

    def _load_saved_domains(self) -> typing.List[typing.Tuple[str, str]]:
        with open(self._domains_file, "r") as f:
            return deserialize_domains(f.read())

    def _is_required(self) -> bool:
        try:
            return os.path.isdir(
                os.path.join(self._read_psa_conf_value("HTTPD_VHOSTS_D"), "chroot")
            )
        except (OSError, RuntimeError):
            return False

    def _prepare_action(self) -> action.ActionResult:
        product_root = self._read_psa_conf_value("PRODUCT_ROOT_D")
        rows = plesk.get_from_plesk_database(
            "SELECT d.name, s.login FROM domains d, hosting h, sys_users s "
            "WHERE d.id = h.dom_id AND h.sys_user_id = s.id "
            f"AND s.shell = '{product_root}/bin/chrootsh' AND d.webspace_id = 0"
        )
        if rows is None:
            log.warn("Plesk database is not ready, the list of chrooted domains is not collected")
            return action.ActionResult()
        domains = [(r.split("\t")[0], r.split("\t")[1]) for r in rows if len(r.split("\t")) == 2]
        with open(self._domains_file, "w") as f:
            f.write(serialize_domains(domains))
        log.info(f"Found {len(domains)} domains with chrooted shell")
        return action.ActionResult()

    def _chrootmng(self, product_root: str, vhosts: str, template: str, domain: str, login: typing.Optional[str]) -> None:
        cmd = [f"{product_root}/admin/sbin/chrootmng", "--remove" if login is None else "--create",
               f"--source={template}", f"--target={vhosts}/{domain}"]
        if login is not None:
            cmd.append(f"--setup-user={login}")
        util.logged_check_call(cmd)

    def _post_action(self) -> action.ActionResult:
        if not os.path.exists(self._domains_file):
            msg = ("The list of domains with chrooted shell was not saved before the conversion, "
                   f"so chroot templates were not rebuilt. Please run '--rebuild' of {UPDATE_CHROOT_SCRIPT_URL} manually.\n")
            log.warn(msg)
            motd.add_finish_ssh_login_message(msg)
            return action.ActionResult()

        product_root = self._read_psa_conf_value("PRODUCT_ROOT_D")
        vhosts = self._read_psa_conf_value("HTTPD_VHOSTS_D")
        template = os.path.join(vhosts, "chroot")

        # Programs added to the template by the administrator, reinstalled from the new OS
        old_bin = os.path.join(template, "bin")
        extra_programs = sorted(os.listdir(old_bin)) if os.path.isdir(old_bin) else []

        # Build the new template aside, so nothing is destroyed if the build fails
        new_template = template + ".new"
        old_template = template + ".old"
        for p in (new_template, old_template):
            _remove_path(p)
        try:
            ChrootTemplateBuilder(new_template).install_chroot_base(extra_programs)
        except Exception as ex:
            _remove_path(new_template)
            msg = f"Failed to rebuild chroot template: {ex}. The old template is kept, please run '--rebuild' of {UPDATE_CHROOT_SCRIPT_URL} manually.\n"
            log.err(msg)
            motd.add_finish_ssh_login_message(msg)
            return action.ActionResult()

        domains = self._load_saved_domains()
        failed: typing.List[str] = []
        for domain, _ in domains:
            try:
                self._chrootmng(product_root, vhosts, template, domain, None)
                for d in ("bin", "lib", "lib64", "dev", "usr"):
                    _remove_path(os.path.join(vhosts, domain, d))
            except Exception as ex:
                log.warn(f"Failed to remove chroot of {domain}: {ex}")

        os.rename(template, old_template)
        os.rename(new_template, template)
        _remove_path(old_template)

        for domain, login in domains:
            try:
                log.info(f"Applying chroot template to {domain}")
                self._chrootmng(product_root, vhosts, template, domain, login)
            except Exception as ex:
                log.warn(f"Failed to apply chroot template to {domain}: {ex}")
                failed.append(domain)

        if failed:
            msg = ("Failed to re-apply chroot template to the domains: " + ", ".join(failed)
                   + f". Please run '--apply' of {UPDATE_CHROOT_SCRIPT_URL} for them manually.\n")
            motd.add_finish_ssh_login_message(msg)
        os.unlink(self._domains_file)
        return action.ActionResult()

    def _revert_action(self) -> action.ActionResult:
        if os.path.exists(self._domains_file):
            os.unlink(self._domains_file)
        return action.ActionResult()

    def estimate_post_time(self) -> int:
        if not os.path.exists(self._domains_file):
            return 0
        return 30 + 2 * len(self._load_saved_domains())
