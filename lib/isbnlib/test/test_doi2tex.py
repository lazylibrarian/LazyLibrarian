# -*- coding: utf-8 -*-
# flake8: noqa
# pylint: skip-file
"""
nose tests
"""

from .. import doi2tex
from nose.tools import assert_equals


def test_doi2tex():
    """Test the doi2tex service."""
    assert_equals(len(repr(doi2tex('10.2139/ssrn.2411669'))) > 50, True)
