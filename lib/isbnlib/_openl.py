# -*- coding: utf-8 -*-
"""Query the openlibrary.org service for metadata."""

import logging
import re

from .dev import stdmeta
from .dev._bouth23 import u
from .dev._exceptions import NoDataForSelectorError, RecordMappingError
from .dev.webquery import query as wquery

UA = 'isbnlib (gzip)'
SERVICE_URL = 'http://openlibrary.org/api/books?bibkeys='\
    'ISBN:{isbn}&format=json&jscmd=data'
LOGGER = logging.getLogger(__name__)


def _mapper(isbn, records):
    """Map canonical <- records."""
    # canonical:
    # -> ISBN-13, Title, Authors, Publisher, Year, Language
    try:
        # mapping: canonical <- records
        canonical = {}
        canonical['ISBN-13'] = u(isbn)
        canonical['Title'] = records.get('title', u('')).replace(' :', ':')
        canonical['Authors'] = [
            a['name'] for a in records.get('authors', ({
                'name': u(''),
            }, ))
        ]
        canonical['Publisher'] = records.get('publishers', [
            {
                'name': u(''),
            },
        ])[0]['name']
        canonical['Year'] = u('')
        strdate = records.get('publish_date', u(''))
        if strdate:  # pragma: no cover
            match = re.search(r'\d{4}', strdate)
            if match:
                canonical['Year'] = match.group(0)
    except:  # pragma: no cover
        LOGGER.debug("RecordMappingError for %s with data %s", isbn, records)
        raise RecordMappingError(isbn)
    # call stdmeta for extra cleanning and validation
    return stdmeta(canonical)


def _records(isbn, data):
    """Classify (canonically) the parsed data."""
    try:
        # put the selected data in records
        records = data['ISBN:%s' % isbn]
    except:  # pragma: no cover
        LOGGER.debug('NoDataForSelectorError for %s', isbn)
        raise NoDataForSelectorError(isbn)

    # map canonical <- records
    return _mapper(isbn, records)


def query(isbn):
    """Query the openlibrary.org service for metadata."""
    data = wquery(SERVICE_URL.format(isbn=isbn), user_agent=UA)
    return _records(isbn, data)
