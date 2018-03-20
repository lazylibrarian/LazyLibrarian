# -*- coding: utf-8 -*-
# flake8: noqa
# pylint: skip-file
"""
nose tests
"""

from nose.tools import assert_equals
from ..dev._bouth23 import u
from ..dev._fmt import _fmtbib

canonical = {
    'ISBN-13': u('9780123456789'),
    'Title': u('A book about nothing'),
    'Publisher': u('No Paper Press'),
    'Year': u('2000'),
    'Language': u('en'),
    'Authors': [u('John Smith'), u('José Silva')]
}


def test_fmtbib():
    """Test the formating into several bibliographic formats."""
    assert_equals(len(_fmtbib("bibtex", canonical)), 182)
    assert_equals(len(_fmtbib("labels", canonical)), 158)
    assert_equals(len(_fmtbib("endnote", canonical)), 103)
    assert_equals(len(_fmtbib("msword", canonical)), 485)
    assert_equals(len(_fmtbib("json", canonical)), 229)
    assert_equals(len(_fmtbib("csl", canonical)), 253)
    assert_equals(len(_fmtbib("refworks", canonical)), 130)
    assert_equals(len(_fmtbib("opf", canonical)), 861)
