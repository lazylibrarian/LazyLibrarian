# -*- coding: utf-8 -*-
"""Registry for metadata services, formatters and cache."""

from pkg_resources import iter_entry_points

from . import _goob as goob
from . import _merge as merge
from . import _openl as openl
from . import _wcat as wcat
from ._imcache import IMCache
from .dev._fmt import _fmtbib

# SERVICES

services = {
    'default': merge.query,
    'merge': merge.query,
    'wcat': wcat.query,
    'goob': goob.query,
    'openl': openl.query,
}


def setdefaultservice(name):  # pragma: no cover
    """Set the default service."""
    global services
    services['default'] = services[name]


def add_service(name, query):  # pragma: no cover
    """Add a new service to services."""
    global services
    services[name] = query


# FORMATTERS

bibformatters = {
    'default': lambda x: _fmtbib('labels', x),
    'labels': lambda x: _fmtbib('labels', x),
    'bibtex': lambda x: _fmtbib('bibtex', x),
    'csl': lambda x: _fmtbib('csl', x),
    'json': lambda x: _fmtbib('json', x),
    'opf': lambda x: _fmtbib('opf', x),
    'endnote': lambda x: _fmtbib('endnote', x),
    'refworks': lambda x: _fmtbib('refworks', x),
    'msword': lambda x: _fmtbib('msword', x),
}  # pragma: no cover


def setdefaultbibformatter(name):  # pragma: no cover
    """Set the default formatter."""
    global bibformatters
    bibformatters['default'] = bibformatters[name]


def add_bibformatter(name, formatter):  # pragma: no cover
    """Add a new formatter to formatters."""
    global bibformatters
    bibformatters[name] = formatter


def load_plugins():  # pragma: no cover
    """Load plugins with groups: isbnlib.metadata & isbnlib.formatters."""
    # get metadata plugins from entry_points
    try:
        for entry in iter_entry_points(group='isbnlib.metadata'):
            add_service(entry.name, entry.load())
    except:
        pass
    # get formatters from entry_points
    try:
        for entry in iter_entry_points(group='isbnlib.formatters'):
            add_bibformatter(entry.name, entry.load())
    except:
        pass


# load plugins on import
load_plugins()

# CACHE
metadata_cache = IMCache()  # should be an instance


def set_cache(cache):  # pragma: no cover
    """Set cache for metadata."""
    global metadata_cache
    metadata_cache = cache


custom_cache = None  # should be an instance


def set_custom_cache(cache):  # pragma: no cover
    """Set a 'spare' cache."""
    global custom_cache
    custom_cache = cache
