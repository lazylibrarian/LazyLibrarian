# -*- coding: utf-8 -*-
# flake8: noqa
# pylint: skip-file
"""
nose tests
"""

from .. import _gwords as words
from nose.tools import assert_equals


def test_words():
    """Test 'isbn_from_words' function."""
    assert_equals(len(words.goos('the old man and the sea')), 13)
    assert_equals(len(words.goos('Camões Lusíadas')), 13)
    # assert_equals(words.goos('-ISBN -isbn') in ('9781364200329', None), True)
