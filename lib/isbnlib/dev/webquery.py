# -*- coding: utf-8 -*-
"""Base class to query a webservice and parse the result to py objects."""

import json
import logging
from time import sleep, time as timestamp

from . import webservice
from ._exceptions import DataNotFoundAtServiceError, ServiceIsDownError

UA = 'isbnlib (gzip)'
OUT_OF_SERVICE = 'Temporarily out of service'
BOOK_NOT_FOUND = 'No results match your search'
LOGGER = logging.getLogger(__name__)
THROTTLING = 1


class WEBQuery(object):
    """Base class to query a webservice and parse the result to py objects."""

    T = {'id': timestamp()}  # noqa

    def __init__(self, service_url, ua=UA):
        """Initialize & call webservice."""
        srv = service_url[8:20]
        last = WEBQuery.T[srv] if srv in WEBQuery.T else 0.0
        wait = 0 if timestamp() - last > THROTTLING else THROTTLING
        sleep(wait)
        self.url = service_url
        self.data = webservice.query(service_url, ua)
        WEBQuery.T[srv] = timestamp()

    def check_data(self, data_checker=None):  # pragma: no cover
        """Check the data & handle errors."""
        if data_checker:
            return data_checker(self.data)
        if self.data == '{}':
            LOGGER.warning('DataNotFoundAtServiceError for %s', self.url)
            raise DataNotFoundAtServiceError(self.url)
        if BOOK_NOT_FOUND in self.data:
            LOGGER.warning('DataNotFoundAtServiceError for %s', self.url)
            raise DataNotFoundAtServiceError(self.url)
        if OUT_OF_SERVICE in self.data:
            LOGGER.critical('ServiceIsDownError for %s', self.url)
            raise ServiceIsDownError(self.url)
        return True

    def parse_data(self, parser=json.loads):
        """Parse the data (default JSON -> PY)."""
        if parser is None:  # pragma: no cover
            return self.data
        return parser(self.data)  # <-- data is now unicode


def query(url, user_agent=UA, data_checker=None, parser=json.loads):
    """Put call and return the data from the web service."""
    wq = WEBQuery(url, user_agent)
    return wq.parse_data(parser) \
        if wq.check_data(data_checker) else None
