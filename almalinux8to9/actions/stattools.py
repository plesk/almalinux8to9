# Copyright 1999 - 2026. WebPros International GmbH. All rights reserved.

import typing

from pleskdistup.common import action, plesk


class AssertStatsToolNotUsed(action.CheckAction):
    toolname: str

    def __init__(self, toolname: str) -> None:
        self.name = f"checking if {toolname} is utilized in domains"
        self.description = f'''You have domains using {toolname}, please switch to another statistics collector supported by target OS:
\t{{}}'''
        self.toolname = toolname

    def _get_domains_with_stat_tool(self, toolname: str) -> typing.List[str]:
        lines = plesk.get_from_plesk_database(
            f'SELECT d.name FROM domains d JOIN hosting h ON d.id = h.dom_id WHERE h.webstat = "{toolname}";',
        )
        if lines is None:
            return []
        return lines

    def _do_check(self) -> bool:
        doms = self._get_domains_with_stat_tool(self.toolname)
        if len(doms) == 0:
            return True
        self.description = self.description.format(", ".join(doms))
        return False


