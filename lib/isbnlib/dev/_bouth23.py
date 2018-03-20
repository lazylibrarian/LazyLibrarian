# -*- coding: utf-8 -*-
# flake8:noqa
# pylint: skip-file
"""Help code to run in py2 and py3."""

import sys

if sys.version < '3':

    def s(x):
        return x

    def b(x):
        return x

    def u(x):
        try:
            return unicode(x, "utf-8")
        except TypeError:
            return x

    def b2u3(x):
        return x.encode("utf-8")

    def type3str():
        return type(u'')

    def bstream(x):
        from StringIO import StringIO
        return StringIO(x)
else:

    def s(x):
        return x.decode("utf-8", 'ignore')

    def b(x):
        return x.encode("utf-8")

    def u(x):
        return x

    def b2u3(x):
        return x

    def type3str():
        return type('')

    def bstream(x):
        from io import BytesIO
        return BytesIO(x)
