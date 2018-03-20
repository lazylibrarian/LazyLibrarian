# -*- coding: utf-8 -*-
# flake8: noqa
# pylint: skip-file
"""
nose tests
"""

from ..dev._helpers import last_first, cutoff_tokens, parse_placeholders, fake_isbn
from nose.tools import assert_equals


def test_last_first():
    """Test the parsing of author's name into (Surname, First Name)."""
    assert_equals(last_first("Surname, First Name"),
                  {"last": "Surname",
                   "first": "First Name"})
    assert_equals(last_first("First Name Surname"),
                  {"last": "Surname",
                   "first": "First Name"})
    assert_equals(last_first("Surname1, First1 and Sur2, First2"),
                  {"last": "Surname1",
                   "first": "First1 and Sur2, First2"})


def test_cutoff_tokens():
    """Test the 'cutoff_tokens' function."""
    assert_equals(cutoff_tokens(['1', '23', '456'], 3), ['1', '23'])


def test_parse_placeholders():
    """Test the parsing of placeholders."""
    assert_equals(parse_placeholders('{isbn}_akaj_{name}'), ['{isbn}', '{name}'
                                                             ])


def test_fake_isbn():
    """Test the 'fake_isbn' function."""
    assert_equals(fake_isbn(' Hello?? Wer,  ! ksDf:  asdf. ; '),
                  '1111006407537')
    assert_equals(fake_isbn(' Hello?? Wer,  ! ksDf:  asdf. ; ',
                            author=''),
                  '1108449680873')
    assert_equals(fake_isbn(' Hello?? Wer,  ! ksDf:  asdf. ; ',
                            author=' '),
                  '1108449680873')
    assert_equals(fake_isbn(' Hello?? Wer,  ! ksDf:  asdf. ; ',
                            author='',
                            publisher=''),
                  '1181593982422')
    assert_equals(fake_isbn(' Hello?? Wer,  ! ksDf:  asdf. ; ',
                            author='a',
                            publisher='K'),
                  '1895031085488')
    assert_equals(fake_isbn(' Hello?? Wer,  ! ksDf:  asdf. ; ',
                            author='A',
                            publisher='k'),
                  '1895031085488')
