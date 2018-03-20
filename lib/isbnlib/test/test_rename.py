# -*- coding: utf-8 -*-
# flake8: noqa
# pylint: skip-file

import locale
import os
from nose.tools import assert_equals, assert_raises
from .._ext import ren
from ..dev._bouth23 import b2u3, u
from ..dev.helpers import File, cwdfiles
"""
nose tests
"""

WINDOWS = os.name == 'nt'
ENCODING = locale.getpreferredencoding()
if ENCODING != 'UTF-8':
    print("Your default locale encoding (%s) doesn't allow unicode filenames!"
          % ENCODING)
    print("=> Some tests could fail.")

TESTFILE_1 = './ç-deleteme.pdf' if WINDOWS else '/tmp/ç-deleteme.pdf'
TESTFILE_2 = './ç-deleteme-PLEASE.pdf' if WINDOWS else '/tmp/ç-deleteme-PLEASE.pdf'

F1 = '9780321534965.pdf'
F2 = '9781597499644.pdf'
F3 = '9781852330729.pdf'
F4 = '9787500117018.pdf'
F5 = '9789727576807.pdf'

F6 = 'Campos2011_Emergências obstétricas_9789727576807.pdf'
F7 = 'Knuth2008_The Art Of Computer Programming_9780321534965.pdf'
F8 = 'Man2001_Genetic Algorithms Concepts And Designs_9781852330729.pdf'
F9 = "O'Connor2012_Violent Python A Cookbook for Hackers, Forensic Analysts, Penetra_9781597499644.pdf"
F10 = '海明威2007_Lao ren yu hai_9787500117018.pdf'

F11 = 'myfile.pdf'

FISBN = [F1, F2, F3, F4, F5]
FFT = [F6, F7, F8, F9, F10]
FILES = FISBN + FFT + [F11]


def create_files(files):
    os.chdir(os.path.dirname(TESTFILE_1))
    for fn in files:
        try:
            with open(fn, 'w') as f:
                f.write(b2u3('ooo') + b2u3(fn))
        except UnicodeEncodeError:
            print("Your default locale (%s) doesn't allow non-ascii filenames!"
                  % locale.CODESET)


def delete_files(fnpatt):
    os.chdir(os.path.dirname(TESTFILE_1))
    for fn in cwdfiles(fnpatt):
        os.remove(fn)


def setup_module():
    # create_files([u(TESTFILE_1), u(TESTFILE_2)])
    os.chdir(os.path.dirname(TESTFILE_1))
    #create_files(FISBN + [F11])
    create_files([F1])


def teardown_module():
    delete_files("*.pdf")


def test_ren():
    """Test 'high level' ren function."""
    ren(F1)
    assert_equals('Knuth2008_The Art Of Computer Programming_9780321534965.pdf'
                  in cwdfiles("*.pdf"), True)
    # create_files([F5])
    # ren(F5)
    # assert_equals('Campos2011_Emergências obstétricas_9789727576807.pdf' in cwdfiles("*.pdf"), True)
