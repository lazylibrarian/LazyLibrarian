# -*- coding: utf-8 -*-
# flake8: noqa
# pylint: skip-file

from nose.tools import assert_equals
from .._core import (check_digit10, check_digit13, _check_structure10,
                     _check_structure13, is_isbn10, is_isbn13, to_isbn10,
                     to_isbn13, canonical, clean, notisbn, get_isbnlike,
                     get_canonical_isbn, EAN13)
from .data4tests import ISBNs

# nose tests


def test_check_digit10():
    """Test check digit algo for ISBN-10."""
    assert_equals(check_digit10('082649752'), '7')
    assert_equals(check_digit10('585270001'), '0')
    assert_equals(check_digit10('08264975X'), None)
    assert_equals(check_digit10('08264975'), None)


def test_check_digit13():
    """Test check digit algo for ISBN-13."""
    assert_equals(check_digit13('978082649752'), '9')
    assert_equals(check_digit13('97808264975'), None)
    assert_equals(check_digit13('97808264975X'), None)


def test__check_structure10():
    """Test structure detection for ISBN-10."""
    assert_equals(_check_structure10('0826497527'), True)
    assert_equals(_check_structure10('0826497X27'), True)  # isbnlike!
    assert_equals(_check_structure10('0826497XI7'), False)


def test__check_structure13():
    """Test structure detection for ISBN-13."""
    assert_equals(_check_structure13('9780826497529'), True)
    assert_equals(_check_structure13('978082649752X'), False)


def test_is_isbn10():
    """Test detection and validation for ISBN-10."""
    assert_equals(is_isbn10('0826497527'), True)
    assert_equals(is_isbn10('isbn 0-8264-9752-7'), True)
    assert_equals(is_isbn10('0826497520'), False)
    assert_equals(is_isbn10('954430603X'), True)


def test_is_isbn13():
    """Test detection and validation for ISBN-13."""
    assert_equals(is_isbn13('9780826497529'), True)
    assert_equals(is_isbn13('9791090636071'), True)
    assert_equals(is_isbn13('isbn 979-10-90636-07-1'), True)
    assert_equals(is_isbn13('9780826497520'), False)
    assert_equals(is_isbn13('9700000000000'), False)
    assert_equals(is_isbn13('9000000000000'), False)
    assert_equals(is_isbn13('9710000000000'), False)


def test_to_isbn10():
    """Test transformation of ISBN to ISBN-10."""
    assert_equals(to_isbn10('9780826497529'), '0826497527')
    assert_equals(to_isbn10('0826497527'), '0826497527')
    assert_equals(to_isbn10('9780826497520'), None)  # ISBN13 not valid
    assert_equals(to_isbn10('9790826497529'), None)
    assert_equals(to_isbn10('97808264975X3'), None)
    assert_equals(to_isbn10('978-826497'), None)  # (bug #14)
    assert_equals(to_isbn10('isbn 0-8264-9752-7'), '0826497527')
    assert_equals(to_isbn10('isbn 979-10-90636-07-1'), None)
    assert_equals(to_isbn10('isbn 978-0-8264-9752-9'), '0826497527')
    assert_equals(to_isbn10('asdadv isbn 978-0-8264-9752-9'), '0826497527')


def test_to_isbn13():
    """Test transformation of ISBN to ISBN-13."""
    assert_equals(to_isbn13('0826497527'), '9780826497529')
    assert_equals(to_isbn13('9780826497529'), '9780826497529')
    assert_equals(to_isbn13('0826497520'), None)  # ISBN10 not valid
    assert_equals(to_isbn13('08X6497527'), None)
    assert_equals(to_isbn13('91-43-01019-9'), '9789143010190')  # (bug #14)
    assert_equals(to_isbn13('isbn 91-43-01019-9'), '9789143010190')
    assert_equals(
        to_isbn13('asd isbn 979-10-90636-07-1 blabla'), '9791090636071')


def test_clean():
    """Test the cleanning of ISBN-like strings."""
    assert_equals(clean(' 978.0826.497529'), '9780826497529')
    assert_equals(clean('ISBN: 9791090636071'), 'ISBN 9791090636071')
    assert_equals(clean('978,0826497520'), '9780826497520')


def test_notisbn():
    """Test the impossibility of extracting valid ISBN from ISBN-like strings."""
    assert_equals(notisbn('0826497527'), False)
    assert_equals(notisbn('0826497520'), True)
    assert_equals(notisbn('9780826497529', level='strict'), False)
    assert_equals(notisbn('9426497529', level='strict'), True)
    assert_equals(notisbn('978082649752', level='strict'), True)
    assert_equals(notisbn('978082649752', level='loose'), True)
    assert_equals(notisbn('9780826400001', level='loose'), False)
    assert_equals(notisbn('9780826400001', level='strict'), True)
    assert_equals(notisbn('9780826400001', level='badlevel'), None)
    assert_equals(notisbn('978 9426497529'), True)
    assert_equals(notisbn('9789426497529'), True)
    assert_equals(notisbn('979 10 9063607 1'), False)
    assert_equals(notisbn('9780826497520'), True)


def test_get_isbnlike():
    """Test the extraction of ISBN-like strings."""
    assert_equals(len(get_isbnlike(ISBNs)), 79)
    assert_equals(len(get_isbnlike(ISBNs, 'normal')), 79)
    assert_equals(len(get_isbnlike(ISBNs, 'strict')), 69)
    assert_equals(len(get_isbnlike(ISBNs, 'loose')), 81)
    assert_equals(get_isbnlike(ISBNs, 'e'), None)


def test_get_canonical_isbn():
    """Test the extraction of canonical ISBN from ISBN-like string."""
    assert_equals(
        get_canonical_isbn(
            '0826497527', output='bouth'), '0826497527')
    assert_equals(get_canonical_isbn('0826497527'), '0826497527')
    assert_equals(
        get_canonical_isbn(
            '0826497527', output='isbn10'), '0826497527')
    assert_equals(
        get_canonical_isbn(
            '0826497527', output='isbn13'), '9780826497529')
    assert_equals(
        get_canonical_isbn(
            'ISBN 0826497527', output='isbn13'),
        '9780826497529')
    assert_equals(
        get_canonical_isbn(
            'ISBN 0826497527', output='NOOPTION'), None)
    assert_equals(get_canonical_isbn('0826497520'), None)
    assert_equals(get_canonical_isbn('9780826497529'), '9780826497529')
    assert_equals(get_canonical_isbn('9780826497520'), None)
    assert_equals(get_canonical_isbn('OSX 9780826497529.pdf'), '9780826497529')


def test_canonical():
    """Test the extraction of 'only numbers and X' from ISBN-like string."""
    assert_equals(canonical('ISBN 9789720404427'), '9789720404427')
    assert_equals(canonical('ISBN-9780826497529'), '9780826497529')
    assert_equals(canonical('ISBN9780826497529'), '9780826497529')
    assert_equals(canonical('isbn9780826497529'), '9780826497529')
    assert_equals(canonical('isbn 0826497527'), '0826497527')
    assert_equals(canonical('954430603x'), '954430603X')


def test_EAN13():
    """Test the extraction and validation of EAN13 from ISBN-like string."""
    assert_equals(EAN13('ISBN 9789720404427'), None)
    assert_equals(EAN13('ISBN 9789720404428'), '9789720404428')
    assert_equals(EAN13('ISBN-9780826497529'), '9780826497529')
    assert_equals(EAN13('ISBN9780826497529'), '9780826497529')
    assert_equals(EAN13('isbn9780826497529'), '9780826497529')
    assert_equals(EAN13('isbn 0826497527'), '9780826497529')
    assert_equals(EAN13('9700000000000'), None)
    assert_equals(EAN13('9000000000000'), None)
    assert_equals(EAN13('9710000000000'), None)
