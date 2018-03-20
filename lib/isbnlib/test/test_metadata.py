# -*- coding: utf-8 -*-
# flake8: noqa
# pylint: skip-file
"""nose tests for metadata."""

from random import randrange
from .._metadata import query
from .._ext import meta
from nose.tools import assert_equals, assert_raises


def test_query():
    """Test the query of metadata with 'low level' queries."""
    # test query from metadata
    assert_raises(Exception, query, '9781849692341', 'goog')
    assert_raises(Exception, query, '9781849692343', 'goob')
    assert_raises(Exception, query, '9781849692341', 'wcat')
    assert_equals(len(repr(query('9780321534965', 'wcat'))) > 100, True)
    assert_equals(len(repr(query('9780321534965'))) > 100, True)
    assert_equals(len(repr(query('9780321534965', 'merge'))) > 100, True)
    assert_equals(len(repr(query('9780321534965', 'goob'))) > 100, True)
    assert_equals(len(repr(query('9789934015960'))) > 100, True)
    assert_equals(len(repr(query(u'9781118241257'))) > 100, True)
    assert_raises(Exception, query, '9780000000', 'wcat', None)
    assert_raises(Exception, query, randrange(0, 1000000), 'wcat')


def test_ext_meta():
    """Test the query of metadata with 'high level' meta function."""
    # test meta from core
    assert_equals(len(repr(meta('9780321534965', 'wcat'))) > 100, True)
    assert_equals(len(repr(meta('9780321534965', 'merge'))) > 100, True)
    assert_equals(len(repr(meta('9780321534965'))) > 100, True)
    assert_raises(Exception, meta, '9780000000', 'wcat', None)
    assert_raises(Exception, meta, randrange(0, 1000000), 'wcat')
    assert_raises(Exception, meta, '9781849692343', 'goob', None)
