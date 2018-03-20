# -*- coding: utf-8 -*-
# flake8: noqa
# pylint: skip-file

from .._infogroup import infogroup
from .._ext import info
from nose.tools import assert_equals, assert_raises


# nose tests
def test_infogroup():
    """Test 'infogroup' language/country function."""
    assert_equals(infogroup('9789727576807'), 'Portugal')
    assert_equals(infogroup('978-972-757-680-7'), 'Portugal')
    assert_equals(infogroup('7500117019'), "China, People's Republic")
    assert_equals(infogroup('7-5001-1701-9'), "China, People's Republic")
    assert_equals(infogroup('9524712946'), 'Finland')
    assert_equals(infogroup('0330284983'), 'English language')
    assert_equals(infogroup('3796519008'), 'German language')
    assert_raises(Exception, infogroup, '92xxxxxxxxxxx')
    assert_raises(Exception, infogroup, '')
    assert_equals(infogroup('9791090636071'), 'France')
    assert_equals(infogroup('9786131796364'), 'Mauritius')
    assert_equals(infogroup('9789992158104'), 'Qatar')


def test_ext_info():
    """Test 'info' language/country function."""
    assert_equals(info('9524712946'), 'Finland')
    assert_raises(Exception, info, '')
