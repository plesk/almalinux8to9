# Copyright 1999 - 2026. WebPros International GmbH. All rights reserved.

import os

from pleskdistup import actions as common_actions


class PostStartProftpd(common_actions.StopStartServices):
    def __init__(self) -> None:
        super().__init__(["proftpd.socket"], disable_on_prep=False)

    def _is_required(self) -> bool:
        return os.path.isfile("/etc/xinetd.d/ftp_psa")

