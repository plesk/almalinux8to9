# Copyright 1999 - 2026. WebPros International GmbH. All rights reserved.

import os

from pleskdistup import actions as common_actions
from pleskdistup.common import util


class PostStartProftpd(common_actions.StopStartServices):
    def __init__(self) -> None:
        super().__init__(["proftpd.socket"], disable_on_prep=False)

    def _is_required(self) -> bool:
        try:
            out = util.logged_check_call(["/usr/sbin/chkconfig", "ftp_psa", "--list"])
            for line in out.splitlines():
                parts = line.split()
                if len(parts) > 1 and parts[0] == "ftp_psa":
                    if parts[1] == "on":
                        return True
                    return False
        except Exception:
            pass
        return os.path.isfile("/etc/xinetd.d/ftp_psa")

