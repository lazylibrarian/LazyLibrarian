# -*- coding: utf-8 -*-
"""Return a small description of the book."""

import logging
from json import loads
from textwrap import fill

from .dev.webservice import query as wsquery

LOGGER = logging.getLogger(__name__)

UA = "isbnlib (gzip)"
SERVICE_URL = "https://www.googleapis.com/books/v1/volumes?q=isbn:{isbn}"\
              "&fields=items/volumeInfo(description)"\
              "&maxResults=1"


def goo_desc(isbn):
    """Get description from Google Books api."""
    from .registry import metadata_cache  # <-- dynamic
    cache = metadata_cache
    if cache is not None:  # pragma: no cover
        key = 'desc-go-' + isbn
        try:
            if cache[key]:
                return cache[key]
            else:
                raise KeyError  # <-- IMPORTANT: caches don't return error!
        except KeyError:
            pass
    url = SERVICE_URL.format(isbn=isbn)
    content = wsquery(url, user_agent=UA)
    try:
        content = loads(content)
        content = content['items'][0]['volumeInfo']['description']
        # TODO don't format content here!
        content = fill(content, width=75) if content else None
        if content and cache is not None:  # pragma: no cover
            cache[key] = content
        return content
    except:  # pragma: no cover
        LOGGER.debug('No description for %s', isbn)
