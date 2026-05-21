# Copyright 1999- 2025. WebPros International GmbH. All rights reserved.
# vim:ft=python:

include_defs('//product.defs.py')


python_binary(
    name = 'almalinux8to9.pex',
    platform = 'py3',
    build_args = ['--python-shebang', '/usr/bin/env python3'],
    main_module = 'almalinux8to9.main',
    deps = [
        'dist-upgrader//pleskdistup:lib',
        '//almalinux8to9:lib',
    ],
)

genrule(
    name = 'almalinux8to9',
    srcs = [':almalinux8to9.pex'],
    out = 'almalinux8to9',
    cmd = 'cp $(location :almalinux8to9.pex) $OUT && chmod +x $OUT',
)
