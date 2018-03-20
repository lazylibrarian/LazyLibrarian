# -*- coding: utf-8 -*-
"""Helper module to work with files."""

import fnmatch
import logging
import os
import re
from stat import S_IRGRP, S_IROTH, S_IRUSR, S_IWGRP, S_IWOTH, S_IWUSR

from ._exceptions import FileNotFoundError

MAXLEN = 120
ILEGAL = r'<>:"/\|?*'
LOGGER = logging.getLogger(__name__)
MODE666 = S_IRUSR | S_IWUSR | S_IRGRP | S_IWGRP | S_IROTH | S_IWOTH


class File(object):
    """Easy manipulation of files in the SAME directory."""

    def __init__(self, fp):
        """Set and validate the basic properties."""
        if not self.isfile(fp):
            raise FileNotFoundError(fp)
        self.path = os.path.dirname(fp) or os.getcwd()
        self.basename = os.path.basename(fp)
        self.name, self.ext = os.path.splitext(self.basename)
        self.writable = os.access(fp, os.W_OK)

    def siblings(self):
        """Collect files and directories in the same directory."""
        return [f for f in os.listdir(self.path) if f != self.basename]

    @staticmethod
    def isfile(path):
        """Check if a given path is a file."""
        return os.path.isfile(path)

    @staticmethod
    def exists(path):
        """Check if a given path is a file or a directory."""
        return os.path.exists(path)

    @staticmethod
    def mkwinsafe(name, space=' '):
        """Delete most common characters not allowed in Windows filenames."""
        space = space if space not in ILEGAL else ' '
        name = ''.join(c for c in name if c not in ILEGAL)\
               .replace(' ', space).strip()
        name = re.sub(r'\s\s+', ' ', name) if space == ' ' else name
        return name[:MAXLEN]

    @staticmethod
    def validate(basename):
        """Check for a proper basename."""
        if basename != os.path.basename(basename):
            LOGGER.critical("This (%s) is not a basename!", basename)
            return False
        name, ext = os.path.splitext(basename)
        if not name:
            LOGGER.critical("Not a valid name (lenght 0)!")
            return False
        if not ext:
            LOGGER.critical("Not a valid extension (lenght 0)!")
            return False
        return True

    def baserename(self, new_basename):
        """Rename the file to a 'safe' basename."""
        if not self.validate(new_basename):
            return False
        name, ext = os.path.splitext(new_basename)
        name = self.mkwinsafe(name)
        new_basename = name + ext
        if new_basename == self.basename:
            return True
        if new_basename not in self.siblings():
            try:
                os.rename(self.basename, new_basename)
            except OSError as err:
                LOGGER.critical("%s", err)
                return False
            self.basename = new_basename
            self.name = name
            self.ext = ext
        else:
            LOGGER.info("The file (%s) already exist in the directory!",
                        new_basename)
        return True

    @staticmethod
    def uxchmod(fp, mode=MODE666):
        """Change the mode of the file (default is 0666)."""
        return os.chmod(fp, mode)


def cwdfiles(pattern='*'):
    """List the files in current directory that match a given pattern."""
    return fnmatch.filter(os.listdir('.'), pattern)
