# -*- coding: utf-8 -*-
"""Use Google to get an ISBN from words from title and author's name."""

import logging
import sys

from ._core import get_canonical_isbn, get_isbnlike
from .dev import webservice

if sys.version > '3':
    from urllib.parse import quote

LOGGER = logging.getLogger(__name__)


def goos(words):
    """Use Google to get an ISBN from words from title and author's name."""
    service_url = "http://www.google.com/search?q=ISBN+"
    if sys.version > '3':
        search_url = service_url + quote(words.replace(' ', '+'))
    else:
        search_url = service_url + words.replace(' ', '+')

    user_agent = 'w3m/0.5.3'

    content = webservice.query(
        search_url,
        user_agent=user_agent,
        appheaders={
            'Content-Type': 'text/plain; charset="UTF-8"',
            'Content-Transfer-Encoding': 'Quoted-Printable',
        })
    isbns = get_isbnlike(content)

    for item in isbns:
        isbn = get_canonical_isbn(item, output='isbn13')
        if isbn:
            break
    if not isbns or not isbn:  # pragma: no cover
        LOGGER.debug('No ISBN found for %s', words)
        return None
    return isbn
