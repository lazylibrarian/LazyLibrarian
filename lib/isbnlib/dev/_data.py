# -*- coding: utf-8 -*-
"""Handle metadata objects."""

import logging

from ._bouth23 import type3str, u
from ._exceptions import NotValidMetadataError
from ._helpers import normalize_space, titlecase

# For now you cannot add custom fields!
FIELDS = ('ISBN-13', 'Title', 'Authors', 'Publisher', 'Year', 'Language')
LOGGER = logging.getLogger(__name__)


class Metadata(object):
    """Class for metadata objects."""

    def __init__(self, record=None):
        """Initialize attributes."""
        self._content = None
        self._set_empty()
        if record:
            self._content.update((k, v) for k, v in list(record.items()))
            if not self._validate():
                self._set_empty()
                LOGGER.debug(record)
                raise NotValidMetadataError()
            self.clean()

    @staticmethod
    def fields():  # pragma: no cover
        """Return a list of value's fields."""
        return list(FIELDS)

    def clean(self, broom=normalize_space, exclude=()):
        """Clean fields of value."""
        self._content.update((k, broom(v))
                             for k, v in list(self._content.items())
                             if k != 'Authors' and k not in exclude)
        if 'Authors' not in exclude:
            self._content['Authors'] = [
                broom(i) for i in self._content['Authors']
            ]
        self._content['Title'] = self._content['Title'].strip(',.:;-_ ')
        if self._content['Language'].lower() in ('en', 'eng', 'english'):
            self._content['Title'] = titlecase(self._content['Title'])

    @property
    def value(self):
        """Get value."""
        return self._content

    @value.setter
    def value(self, record):  # pragma: no cover
        """Set value."""
        self._content.update((k, v) for k, v in list(record.items()))
        if not self._validate():
            self._set_empty()
            LOGGER.debug(record)
            raise NotValidMetadataError()
        self.clean()

    @value.deleter
    def value(self):  # pragma: no cover
        """Delete value."""
        self._set_empty()

    def merge(self,
              record,
              overwrite=(),
              overrule=lambda x: x == u('') or x == [u('')]):
        """Merge the record with value."""
        # by default do nothing
        self._content.update(
            (k, v) for k, v in list(record.items())
            if k in overwrite and not overrule(v) or self._content[k] == u(''))
        if not self._validate():  # pragma: no cover
            self._set_empty()
            LOGGER.debug(record)
            raise NotValidMetadataError()
        self.clean()

    def _validate(self):
        """Validate value."""
        # 'minimal' check
        for k in self._content:
            if not isinstance(self._content[k], type3str()) and k != 'Authors':
                return False
        if not isinstance(self._content['Authors'], list):
            return False
        return True

    def _set_empty(self):
        """Set an empty value record."""
        self._content = dict.fromkeys(list(FIELDS), u(''))
        self._content['Authors'] = [u('')]


def stdmeta(records):
    """Function API to the class."""
    data = Metadata(records)
    return data.value
