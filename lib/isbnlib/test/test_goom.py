# -*- coding: utf-8 -*-
# flake8: noqa
# pylint: skip-file
"""
nose tests
"""

from .. import _goom as goom
from nose.tools import assert_equals


def test_goom():
    """Test the Google's Multiple Books service."""
    assert_equals(len(repr(goom.query('the old man and the sea'))) > 1000,
                  True)
