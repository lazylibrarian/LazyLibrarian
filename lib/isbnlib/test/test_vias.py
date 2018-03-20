# -*- coding: utf-8 -*-
# flake8: noqa
# pylint: skip-file
"""
nose tests
"""

import os

from .. import _merge as merge
from nose.tools import assert_equals

WINDOWS = os.name == 'nt'


def test_vias_parallel():
    """Test 'vias' parallel operation."""
    if WINDOWS:
        # appveyor doesn't allow!
        return
    assert_equals(len(repr(merge.query('9783319020983', 'parallel'))) > 100,
                  True)

def test_vias_multi():
    """Test 'vias' multi operation."""
    if WINDOWS:
        # appveyor doesn't allow!
        return
    assert_equals(len(repr(merge.query('9783319020983', 'multi'))) > 100, True)

def test_vias_serial():
    """Test 'vias' serial operation."""
    if WINDOWS:
        # appveyor doesn't allow!
        return
    assert_equals(len(repr(merge.query('9783319020983', 'serial'))) > 100,
                  True)

def test_vias_cache_cleanning():
    """Test 'vias' cache cleanning for serial."""
    # test if the secondary cache (cache in vias) does clears... sequentially
    assert_equals(len(repr(merge.query('9781680450260', 'serial'))) < 20, True)  # NO METADATA
    assert_equals(len(repr(merge.query('9780521581783', 'serial'))) > 100,
                  True)
    assert_equals(len(repr(merge.query('9781680450260', 'serial'))) < 20, True)  # NO METADATA
