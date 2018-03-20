# -*- coding: utf-8 -*-
"""Query the worldcat.org xID service for related ISBNs."""

import logging
from ast import literal_eval

from .dev._exceptions import DataWrongShapeError, NoDataForSelectorError
from .dev.webquery import query as wquery

LOGGER = logging.getLogger(__name__)
UA = 'isbnlib (gzip)'
SERVICE_URL = 'http://xisbn.worldcat.org/webservices/xid/isbn/{isbn}?'\
              'method=getEditions&format=python'


def _editions(isbn, data):
    """Return the records from the parsed response."""
    # check status
    try:
        status = data['stat']
        if status != 'ok':
            raise  # pragma: no cover
    except:  # pragma: no cover
        LOGGER.debug('DataWrongShapeError for %s with status %s', isbn, status)
        raise DataWrongShapeError("status: '%s' for isbn %s" % (status, isbn))
    # put the selected data in records
    try:
        recs = [ib['isbn'][0] for ib in data['list']]
    except:  # pragma: no cover
        LOGGER.debug('NoDataForSelectorError for %s', isbn)
        raise NoDataForSelectorError(isbn)
    return recs


def query(isbn):
    """Query the worldcat.org service for related ISBNs."""
    data = wquery(
        SERVICE_URL.format(isbn=isbn), user_agent=UA, parser=literal_eval)
    return _editions(isbn, data)
