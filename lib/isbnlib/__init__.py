# -*- coding: utf-8 -*-
# flake8: noqa
# isort:skip_file
"""Library to validate, clean, transform and get metadata of ISBN strings (for devs)."""

# Define isbnlib API and set lib environment

import logging as _logging

from ._exceptions import (quiet_errors, ISBNLibException,
                          NotRecognizedServiceError, NotValidISBNError,
                          PluginNotLoadedError)

# configuration
from . import config  # <-- first import

# main modules
from ._core import (is_isbn10, is_isbn13, to_isbn10, to_isbn13, check_digit10,
                    check_digit13, clean, canonical, notisbn, get_isbnlike,
                    get_canonical_isbn, GTIN13, EAN13, RE_ISBN10, RE_ISBN13,
                    RE_LOOSE, RE_NORMAL, RE_STRICT)
from ._ext import (cover, desc, mask, meta, info, editions, isbn_from_words,
                   doi, ren)
from ._goom import query as goom
from ._doitotex import doi2tex

# Ranges Database date
from ._data.data4mask import RDDATE

# config _logging for lib
_nh = _logging.NullHandler()
_logging.getLogger('isbnlib').addHandler(_nh)

# alias
ISBN13 = EAN13
ean13 = EAN13

# dunders

__all__ = ('is_isbn10', 'is_isbn13', 'clean', 'check_digit10', 'check_digit13',
           'mask', 'info', 'meta', 'to_isbn10', 'to_isbn13', 'get_isbnlike',
           'notisbn', 'ean13', 'EAN13', 'cover', 'desc', 'canonical',
           'get_canonical_isbn', 'editions', 'isbn_from_words', 'quiet_errors',
           'config', '__version__', '__support__', 'doi', 'ren', 'ISBN13',
           'GTIN13', 'ISBNLibException', 'NotRecognizedServiceError',
           'NotValidISBNError', 'PluginNotLoadedError', 'goom', 'doi2tex',
           'RDDATE')

__version__ = '3.8.4'  # <-- literal IDs
__support__ = 'py27, py34, py35, py36, pypy, pypy3'  # <-- literal IDs
