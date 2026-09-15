# Copyright 2025. WebPros International GmbH. All rights reserved.
# vim:ft=python:

include_defs('//buck.defs.py')


# Function is necessary, because Buck won't allow
# get_git_revision_description() to be called at the top level of an
# included file due to get_base_path() call inside (so, you can't just
# do REVISION = get_git_revision_description())
def get_product_revision():
    return get_git_revision_description(dirty=False)


def get_product_version():
    rev = get_product_revision()
    return rev.lstrip('v').split('-', 1)[0] if rev.startswith('v') else ''
