# Copyright 1999 - 2025. WebPros International GmbH. All rights reserved.
# vim:ft=python:

import os.path

with allow_unsafe_import():
    import subprocess


def get_full_base_path():
    path = get_base_path()
    cell = get_cell_name()
    if cell:
        path = os.path.join(cell, path)
    return path


def get_git_revision(path=None):
    if not path:
        path = get_full_base_path()
    return subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=path, universal_newlines=True).strip()


def get_git_revision_description(dirty=True, path=None):
    cmd = ['git', 'describe', '--match', 'v[0-9]*']
    if dirty is True:
        cmd.append('--dirty')
    if not path:
        path = get_full_base_path()
    try:
        return subprocess.check_output(cmd, cwd=path, universal_newlines=True).strip()
    except Exception:
        return get_git_revision(path=path)
