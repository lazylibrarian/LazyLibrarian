# -*- coding: utf-8 -*-
"""Query the ThingISBN api (Library Thing) for related ISBNs."""

import logging
from xml.dom.minidom import parseString

from ._core import EAN13
from .dev.webquery import query as wquery

LOGGER = logging.getLogger(__name__)
UA = 'isbnlib (gzip)'
SERVICE_URL = 'http://www.librarything.com/api/thingISBN/{isbn}'


def _get_text(topnode):
    """Get the text values in the child nodes."""
    text = ""
    for node in topnode.childNodes:
        if node.nodeType == node.TEXT_NODE:
            text = text + node.data
    return text


def parser_thinged(xml):
    """Parse the response from the ThingISBN service."""
    dom = parseString(xml)
    nodes = dom.getElementsByTagName("idlist")[0].getElementsByTagName("isbn")
    return [EAN13(_get_text(isbn)) for isbn in nodes]


def query(isbn):
    """Query the ThingISBN service for related ISBNs."""
    data = wquery(
        SERVICE_URL.format(isbn=isbn), user_agent=UA, parser=parser_thinged)
    if not data:  # pragma: no cover
        LOGGER.debug('No data from ThingISBN for isbn %s', isbn)
    return data
