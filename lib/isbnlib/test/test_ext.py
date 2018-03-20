# -*- coding: utf-8 -*-
# flake8: noqa
# pylint: skip-file

from nose.tools import assert_equals, assert_raises
from .._ext import mask, editions, isbn_from_words, doi, desc, cover

# nose tests


def test_mask():
    """Test 'mask' command."""
    assert_equals(mask('5852700010'), '5-85270-001-0')
    assert_equals(mask('0330284983'), '0-330-28498-3')
    assert_equals(mask('3796519008'), '3-7965-1900-8')
    assert_equals(mask('4198301271'), '4-19-830127-1')
    assert_equals(mask('2226052577'), '2-226-05257-7')
    assert_equals(mask('6053840572'), '605-384-057-2')
    assert_equals(mask('7301102992'), '7-301-10299-2')
    assert_equals(mask('8085983443'), '80-85983-44-3')
    assert_equals(mask('9056911872'), '90-5691-187-2')
    assert_equals(mask('9500404427'), '950-04-0442-7')
    assert_equals(mask('9800101942'), '980-01-0194-2')
    assert_equals(mask('9813018399'), '981-3018-39-9')
    assert_equals(mask('9786001191251'), '978-600-119-125-1')
    assert_equals(mask('9780321534965'), '978-0-321-53496-5')
    assert_equals(mask('9781590593561'), '978-1-59059-356-1')
    assert_equals(mask('9789993075899'), '978-99930-75-89-9')
    assert_equals(mask('0-330284983'), '0-330-28498-3')
    assert_equals(mask('9791090636071'), '979-10-90636-07-1')
    assert_equals(
        mask('9786131796364'), '978-613-1-79636-4')  # <-- prefix with 1 rule
    assert_equals(mask('isbn 979-10-90636-07-1'), '979-10-90636-07-1')
    assert_raises(Exception, mask, '')
    assert_raises(Exception, mask, '9786')
    assert_raises(Exception, mask, '0000000000000')


def test_isbn_from_words():
    """Test 'isbn_from_words' command."""
    assert_equals(len(isbn_from_words('old men and sea')), 13)


def test_doi():
    """Test 'doi' command."""
    assert_equals(doi('9780195132861'), '10.978.019/5132861')
    assert_equals(doi('9780321534965'), '10.978.0321/534965')
    assert_equals(doi('9791090636071'), '10.979.1090636/071')


def test_desc():
    """Test 'desc' command."""
    assert_equals(len(desc('9780156001311')) > 10, True)
    assert_equals(desc('9780000000000'), None)


def test_cover():
    """Test 'cover' command."""
    assert_equals(len(repr(cover('9780156001311'))) > 50, True)
    assert_equals(cover('9780000000000'), None)  # <-- invalid ISBN
    assert_equals(len(repr(cover('9781408835029'))) > 50, True)
    assert_equals(
        len(repr(cover('9789727576807'))) < 50,
        True)  # <-- no image of any size
