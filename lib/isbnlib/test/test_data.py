# -*- coding: utf-8 -*-
# flake8: noqa
# pylint: skip-file
""" nose tests

"""

from nose.tools import assert_equals, assert_raises
from ..dev import Metadata, stdmeta
from ..dev._bouth23 import u


def test_stdmeta():
    """Test the transformation of raw records into standard metadata."""
    # test stdmeta from data
    r = {
        'ISBN-13': u('9780123456789 '),
        'Title': u('Bla. Bla /Title .'),
        'Publisher': u(''),
        'Year': u('2000'),
        'Language': u('en'),
        'Authors': [u('author1. mba'), u('author2   ')]
    }
    R = {
        'ISBN-13': u('9780123456789'),
        'Title': u('Bla. Bla /Title'),
        'Publisher': u(''),
        'Year': u('2000'),
        'Language': u('en'),
        'Authors': [u('author1. mba'), u('author2')]
    }
    A = {
        'ISBN-13': u('9780123456789 '),
        'Title': b'Bla. Bla /Title .',
        'Publisher': u(''),
        'Year': b'2000',
        'Language': u('en'),
        'Authors': [u('author1. mba'), u('author2   ')]
    }
    B = {
        'ISBN-13': u('9780123456789'),
        'Title': u('Bla. Bla /Title .'),
        'Publisher': u(''),
        'Year': u('2000'),
        'Language': u('en'),
        'Authors': u('author1')
    }
    assert_equals(stdmeta(r), R)
    assert_equals(stdmeta(R), R)
    assert_raises(Exception, stdmeta, A)
    assert_raises(Exception, stdmeta, B)


def test_metaclass():
    """Test the creation of a Metadata class from raw records."""
    R = {
        'ISBN-13': u('9780123456789'),
        'Title': u('Bla. Bla /Title'),
        'Publisher': u(''),
        'Year': u('2000'),
        'Language': u('en'),
        'Authors': [u('author1. mba'), u('author2')]
    }
    dt = Metadata(R)
    assert_equals(dt.value, R)
