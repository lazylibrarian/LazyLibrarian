# -*- coding: utf-8 -*-
"""Query the Google Books (JSON API v1) service for metadata."""

import logging

from .dev import stdmeta
from .dev._bouth23 import u
from .dev._exceptions import (ISBNNotConsistentError, NoDataForSelectorError,
                              RecordMappingError)
from .dev.webquery import query as wquery

UA = 'isbnlib (gzip)'
SERVICE_URL = 'https://www.googleapis.com/books/v1/volumes?q=isbn:{isbn}'\
    '&fields=items/volumeInfo(title,authors,publisher,publishedDate,language,'\
    'industryIdentifiers)&maxResults=1'
LOGGER = logging.getLogger(__name__)


def _mapper(isbn, records):
    """Mapp: canonical <- records."""
    # canonical: ISBN-13, Title, Authors, Publisher, Year, Language
    try:
        canonical = {}
        canonical['ISBN-13'] = u(isbn)
        canonical['Title'] = records.get('title', u('')).replace(' :', ':')
        canonical['Authors'] = records.get('authors', [u('')])
        canonical['Publisher'] = records.get('publisher', u(''))
        if 'publishedDate' in records \
           and len(records['publishedDate']) >= 4:
            canonical['Year'] = records['publishedDate'][0:4]
        else:  # pragma: no cover
            canonical['Year'] = u('')
        canonical['Language'] = records.get('language', u(''))
    except:  # pragma: no cover
        LOGGER.debug("RecordMappingError for %s with data %s", isbn, records)
        raise RecordMappingError(isbn)
    # call stdmeta for extra cleanning and validation
    return stdmeta(canonical)


def _records(isbn, data):
    """Classify (canonically) the parsed data."""
    # put the selected data in records
    try:
        recs = data['items'][0]['volumeInfo']
    except:  # pragma: no cover
        LOGGER.debug('NoDataForSelectorError for %s', isbn)
        raise NoDataForSelectorError(isbn)
    # consistency check (isbn request = isbn response)
    if recs:
        ids = recs.get('industryIdentifiers', '')
        if u('ISBN_13') in repr(ids) and \
           isbn not in repr(ids):  # pragma: no cover
            LOGGER.debug('ISBNNotConsistentError for %s (%s)', isbn, repr(ids))
            raise ISBNNotConsistentError("{0} not in {1}".format(
                isbn, repr(ids)))
    # map canonical <- records
    return _mapper(isbn, recs)


def query(isbn):
    """Query the Google Books (JSON API v1) service for metadata."""
    data = wquery(SERVICE_URL.format(isbn=isbn), user_agent=UA)
    return _records(isbn, data)
