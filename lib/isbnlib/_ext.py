# -*- coding: utf-8 -*-
"""Extra methods."""

import re

from ._core import EAN13
from ._cover import cover as gcover
from ._desc import goo_desc
from ._editions import editions as eds
from ._gwords import goos
from ._infogroup import infogroup
from ._metadata import query
from ._msk import msk
from .dev._bouth23 import b2u3, u
from .dev.helpers import File, cutoff_tokens, last_first


def mask(isbn, separator='-'):
    """`Mask` a canonical ISBN."""
    return msk(isbn, separator)


def meta(isbn, service='default', cache='default'):
    """Get metadata from worldcat.org ('wcat'), Google Books ('goob') , ..."""
    service = service if service else 'default'
    return query(isbn, service, cache) if isbn else None


def info(isbn):
    """Get language or country assigned to this ISBN."""
    return infogroup(isbn)


def editions(isbn, service='merge'):
    """Return the list of ISBNs of editions related with this ISBN.

    'service' can have the values:
    'any', 'merge' (default), 'wcat', 'openl' and 'thingl'
    """
    return eds(isbn, service)


def isbn_from_words(words):
    """Return the most probable ISBN from a list of words."""
    return goos(words)


def doi(isbn):
    """Return a DOI's ISBN-A from a ISBN-13."""
    return "10.%s.%s%s/%s%s" % \
           tuple(msk(EAN13(isbn), '-').split('-'))


def ren(fp):
    """Rename a file using metadata from an ISBN in his filename."""
    cfp = File(fp)
    isbn = EAN13(cfp.name)
    if not isbn:  # pragma: no cover
        return None
    data = meta(isbn)
    author = data.get('Authors', u('UNKNOWN'))
    if author != u('UNKNOWN'):  # pragma: no cover
        author = last_first(author[0])['last']
    year = data.get('Year', u('UNKNOWN'))
    maxlen = 98 - (20 + len(author) + len(year))
    title = data.get('Title', u('UNKNOWN'))
    if title != u('UNKNOWN'):
        regex1 = re.compile(r'[.,_!?/\\]')
        regex2 = re.compile(r'\s\s+')
        title = regex1.sub(' ', title)
        title = regex2.sub(' ', title)
        title = title.strip()
    if title == u('UNKNOWN') or not title:  # pragma: no cover
        return None
    if ' ' in title:  # pragma: no cover
        tokens = title.split(' ')
        stitle = cutoff_tokens(tokens, maxlen)
        title = ' '.join(stitle)
    isbn13 = data.get('ISBN-13', u('UNKNOWN'))
    new_name = "%s%s_%s_%s" % (author, year, title, isbn13)
    return cfp.baserename(b2u3(new_name + cfp.ext))


def cover(isbn):
    """Get the img urls of the cover of the ISBN."""
    isbn = EAN13(isbn)
    return gcover(isbn) if isbn else None


def desc(isbn):
    """Return a descripion of the ISBN."""
    isbn = EAN13(isbn)
    return goo_desc(isbn) if isbn else None
