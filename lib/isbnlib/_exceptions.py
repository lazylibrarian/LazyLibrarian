# -*- coding: utf-8 -*-
"""Exceptions for isbnlib."""

import sys


def quiet_errors(exc_type, exc_value, traceback):
    """An error format suitable for end user scripts.

       Usage: enter the following lines in your script
              from isbnlib import quiet_errors
              sys.excepthook = quiet_errors
    """
    sys.stderr.write('Error: %s\n' % exc_value)  # pragma: no cover


class ISBNLibException(Exception):
    """Base class for isbnlib exceptions.

    This exception should not be raised directly,
    only subclasses of this exception should be used!
    """

    def __str__(self):
        return getattr(self, 'message', '')  # pragma: no cover


class NotRecognizedServiceError(ISBNLibException):
    """Exception raised when the service is not in config.py."""

    def __init__(self, service):
        self.message = "(%s) is not a recognized service" % service


class NotValidISBNError(ISBNLibException):
    """Exception raised when the ISBN is not valid."""

    def __init__(self, isbnlike):
        self.message = "(%s) is not a valid ISBN" % isbnlike


class PluginNotLoadedError(ISBNLibException):  # pragma: no cover
    """Exception raised when the plugin's loader doesn't load the plugin.

    TODO: Delete this in version 4?
    """

    def __init__(self, path):
        self.message = "plugin (%s) wasn't loaded" % path
