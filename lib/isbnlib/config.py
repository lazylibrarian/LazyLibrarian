# -*- coding: utf-8 -*-
"""Config file for isbnlib."""

# --> Import only external modules! <--

# Timeouts
URLOPEN_TIMEOUT = 10  # seconds
THREADS_TIMEOUT = 12  # seconds


# URLOPEN_TIMEOUT is used by webservice
def seturlopentimeout(seconds):
    """Set the value of URLOPEN_TIMEOUT (in seconds)."""
    global URLOPEN_TIMEOUT
    URLOPEN_TIMEOUT = seconds


# THREADS_TIMEOUT is a parameter used downstream by Thread calls (see vias.py)
def setthreadstimeout(seconds):  # pragma: no cover
    """Set the value of THREADS_TIMEOUT (in seconds)."""
    global THREADS_TIMEOUT
    THREADS_TIMEOUT = seconds


# API keys
apikeys = {}


def add_apikey(service, apikey):  # pragma: no cover
    """Add API keys."""
    apikeys[service] = apikey


# Generic Options
options = {'VIAS_MERGE': 'parallel'}


def set_option(option, value):  # pragma: no cover
    """Set the value for option."""
    options[option] = value
