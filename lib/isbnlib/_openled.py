# -*- coding: utf-8 -*-
"""Query the Open Library for related ISBNs."""

import logging

from . import get_canonical_isbn, get_isbnlike
from .dev._bouth23 import u
from .dev.webquery import query as wquery

LOGGER = logging.getLogger(__name__)
UA = 'isbnlib (gzip)'
SERVICE_URL = 'http://openlibrary.org/query.json?type=/type/edition&'\
              '{selectors}'
CODES = 'isbn_13={isbn}&books='
ISBNS = '{code}&isbn_13='


def query(isbn):
    """Query the Open Library for related ISBNs."""
    try:
        data = wquery(
            SERVICE_URL.format(selectors=CODES.format(isbn=isbn)),
            user_agent=UA)
        codes = [rec['key'] for rec in data]
        isbnlikes = [isbn]
        for code in codes:
            txt = wquery(
                SERVICE_URL.format(selectors=ISBNS.format(code=code)),
                user_agent=UA,
                parser=None)
            isbnlikes.extend(get_isbnlike(txt))
        isbns = [get_canonical_isbn(isbnlike) for isbnlike in isbnlikes]
        isbns = sorted(list(set([u(n) for n in isbns if n])))  # qa: py26
    except Exception:  # pragma: no cover, qa: FIXME
        LOGGER.debug('No data from Open Library for isbn %s', isbn)
    return isbns
