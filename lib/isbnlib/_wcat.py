# -*- coding: utf-8 -*-
"""Query the worldcat.org xID service for metadata."""

import logging

from .dev import stdmeta
from .dev._bouth23 import u
from .dev._exceptions import (DataWrongShapeError, ISBNNotConsistentError,
                              NoDataForSelectorError, RecordMappingError)
from .dev.webquery import query as wquery

UA = 'isbnlib (gzip)'
SERVICE_URL = 'http://xisbn.worldcat.org/webservices/xid/isbn/{isbn}?'\
    'method=getMetadata&format=json&fl=title,author,year,publisher,lang'
LOGGER = logging.getLogger(__name__)


def _mapper(isbn, records):
    """Map: canonical <- records."""
    # canonical: ISBN-13, Title, Authors, Publisher, Year, Language
    try:
        canonical = {}
        canonical['ISBN-13'] = u(isbn)
        canonical['Title'] = records.get('title', u('')).replace(' :', ':')
        buf = records.get('author', u(''))
        canonical['Authors'] = [x.strip('. ') for x in buf.split(';')]
        canonical['Publisher'] = records.get('publisher', u(''))
        canonical['Year'] = records.get('year', u(''))
        canonical['Language'] = records.get('lang', u(''))
    except:  # pragma: no cover
        LOGGER.debug("RecordMappingError for %s with data %s", isbn, records)
        raise RecordMappingError(isbn)
    # call stdmeta for extra cleanning and validation
    return stdmeta(canonical)


def _records(isbn, data):
    """Classify (canonically) the parsed data."""
    # check status
    try:
        status = data['stat']
        if status != 'ok':
            raise
    except:
        LOGGER.debug('DataWrongShapeError for %s with status %s', isbn, status)
        raise DataWrongShapeError("status: '%s' for isbn %s" % (status, isbn))
    # put the selected data in records
    try:
        recs = data['list'][0]
    except:  # pragma: no cover
        LOGGER.debug('NoDataForSelectorError for %s', isbn)
        raise NoDataForSelectorError(isbn)
    # consistency check (isbn request = isbn response)
    if recs:
        ids = recs.get('isbn', '')
        if isbn not in repr(ids):  # pragma: no cover
            LOGGER.debug('ISBNNotConsistentError for %s (%s)', isbn, repr(ids))
            raise ISBNNotConsistentError("%s not in %s" % (isbn, repr(ids)))
    # map canonical <- records
    return _mapper(isbn, recs)


def query(isbn):
    """Query the worldcat.org service for metadata."""
    data = wquery(SERVICE_URL.format(isbn=isbn), user_agent=UA)
    return _records(isbn, data)
