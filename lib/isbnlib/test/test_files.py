# -*- coding: utf-8 -*-
# flake8: noqa
# pylint: skip-file
""" nose tests

"""

import locale
import os
from ..dev._files import File, cwdfiles
from nose.tools import assert_equals, assert_raises

WINDOWS = os.name == 'nt'
ENCODING = locale.getpreferredencoding()
if ENCODING == 'UTF-8':
    TESTFILE = './ç-deleteme.pdf' if WINDOWS else '/tmp/海明威-deleteme.pdf'
    NEW_BASENAME = 'ç-deleteme-PLEASE.pdf' if WINDOWS else '海明威-deleteme-PLEASE.pdf'
else:
    print("Your default locale encoding (%s) doesn't allow unicode filenames!"
          % ENCODING)
    TESTFILE = './deleteme.pdf'
    NEW_BASENAME = 'deleteme-PLEASE.pdf'


def setup_module():
    with open(TESTFILE, 'w') as f:
        f.write('ooo')
    os.chdir(os.path.dirname(TESTFILE))


def teardown_module():
    os.remove(os.path.join(os.path.dirname(TESTFILE), NEW_BASENAME))


def test_isfile():
    """Test if a path is a file."""
    f = File(TESTFILE)
    assert f.isfile(TESTFILE) == True


def test_exists():
    """Test if a path is a file or a directory."""
    f = File(TESTFILE)
    assert f.exists(TESTFILE) == True


def test_validate():
    """Test if a string is a valid filename for 'ren' command."""
    f = File(TESTFILE)
    assert f.validate('basename.pdf') == True
    assert f.validate('as/basename.pdf') == False
    assert f.validate('.basename.pdf') == True
    assert f.validate('.basename') == False
    assert f.validate('') == False


def test_mkwinsafe():
    """Test if a string is a valid basename in Windows."""
    f = File(TESTFILE)
    assert f.mkwinsafe('Açtr: ') == 'Açtr'
    assert f.mkwinsafe('as/tiõ') == 'astiõ'
    assert f.mkwinsafe('file ""name?') == 'file name'
    assert f.mkwinsafe('file ""name?', space='_') == 'file_name'
    assert f.mkwinsafe('file   name ') == 'file name'


def test_baserename():
    """Test the rename of a basename."""
    f = File(TESTFILE)
    assert f.baserename(NEW_BASENAME) == True
    assert f.baserename(NEW_BASENAME) == True


def test_cwdfiles():
    """Test the renaming of files in cwd."""
    assert (NEW_BASENAME in cwdfiles()) == True
    assert (NEW_BASENAME in cwdfiles('*.pdf')) == True
    assert (NEW_BASENAME in cwdfiles('*.txt')) == False
