# -*- coding: utf-8 -*-
"""Get the Language/Country of an ISBN."""

import logging

from ._core import EAN13
from ._data.data4info import d, identifiers
from ._exceptions import NotValidISBNError

LOGGER = logging.getLogger(__name__)


def infogroup(isbn):
    """Get the Language/Country of this ISBN."""
    # if isbn is not a valid ISBN this def can give a wrong result!
    # => clean and validate
    isbn = EAN13(isbn)
    if not isbn:
        LOGGER.critical('%s is not a valid ISBN', isbn)
        raise NotValidISBNError(isbn)
    # put isbn in the form 978-...
    prefix = isbn[0:3] + '-'
    isbn = prefix + isbn[3:]
    dtxt = d
    idents = identifiers
    ixi, ixf = 4, 5
    for ident in idents:
        iid = prefix + isbn[ixi:ixf]
        ixf += 1
        # stop if identifier is found
        if iid in ident:
            return dtxt[iid]
