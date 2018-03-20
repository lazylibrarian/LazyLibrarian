# -*- coding: utf-8 -*-
"""Get image links of the book's cover."""

import logging

from .dev.webquery import query as wquery

LOGGER = logging.getLogger(__name__)

UA = "isbnlib (gzip)"
SERVICE_URL = 'https://www.googleapis.com/books/v1/volumes?q=isbn+{isbn}'\
              '&fields=items/volumeInfo(imageLinks)&maxResults=1'


def cover(isbn):
    """Main entry point for cover."""
    from .registry import metadata_cache  # <-- dynamic
    # check the cache first
    cache = metadata_cache
    if cache:  # pragma: no cover
        key = 'img-url-go-' + isbn
        try:  # pragma: no cover
            if cache[key]:
                return cache[key]
            else:
                raise KeyError  # <-- IMPORTANT: caches don't return error!
        except KeyError:  # pragma: no cover
            pass
    # request to the web service
    data = wquery(SERVICE_URL.format(isbn=isbn), user_agent=UA)
    try:
        lnks = data['items'][0]['volumeInfo']['imageLinks']
        # put in cache
        if cache and lnks:  # pragma: no cover
            cache[key] = lnks
        return lnks
    except (KeyError, IndexError):  # pragma: no cover
        LOGGER.debug('No cover img data for %s', isbn)
    return None
