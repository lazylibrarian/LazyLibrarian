#  This file is part of Lazylibrarian.
#
#  Lazylibrarian is free software':'you can redistribute it and/or modify
#  it under the terms of the GNU General Public License as published by
#  the Free Software Foundation, either version 3 of the License, or
#  (at your option) any later version.
#
#  Lazylibrarian is distributed in the hope that it will be useful,
#  but WITHOUT ANY WARRANTY; without even the implied warranty of
#  MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
#  GNU General Public License for more details.
#
#  You should have received a copy of the GNU General Public License
#  along with Lazylibrarian.  If not, see <http://www.gnu.org/licenses/>.

import logging
import os
import threading
import inspect
from logging import handlers

import lazylibrarian
from lazylibrarian import formatter


# Simple rotating log handler that uses RotatingFileHandler
class RotatingLogger(object):

    def __init__(self, filename):

        self.filename = filename
        self.filehandler = None
        self.consolehandler = None

    def stopLogger(self):
        lg = logging.getLogger('lazylibrarian')
        lg.removeHandler(self.filehandler)
        lg.removeHandler(self.consolehandler)

    def initLogger(self, loglevel=1):

        lg = logging.getLogger('lazylibrarian')
        lg.setLevel(logging.DEBUG)

        self.filename = os.path.join(lazylibrarian.CONFIG['LOGDIR'], self.filename)

        filehandler = handlers.RotatingFileHandler(
            self.filename,
            maxBytes=lazylibrarian.CONFIG['LOGSIZE'],
            backupCount=lazylibrarian.CONFIG['LOGFILES'])

        filehandler.setLevel(logging.DEBUG)

        fileformatter = logging.Formatter('%(asctime)s - %(levelname)-7s :: %(message)s', '%d-%b-%Y %H:%M:%S')

        filehandler.setFormatter(fileformatter)
        lg.addHandler(filehandler)
        self.filehandler = filehandler

        if loglevel:
            consolehandler = logging.StreamHandler()
            if loglevel == 1:
                consolehandler.setLevel(logging.INFO)
            if loglevel >= 2:
                consolehandler.setLevel(logging.DEBUG)
            consoleformatter = logging.Formatter('%(asctime)s - %(levelname)s :: %(message)s', '%d-%b-%Y %H:%M:%S')
            consolehandler.setFormatter(consoleformatter)
            lg.addHandler(consolehandler)
            self.consolehandler = consolehandler

    @staticmethod
    def log(message, level):

        logger = logging.getLogger('lazylibrarian')

        threadname = threading.currentThread().getName()

        # Get the frame data of the method that made the original logger call
        if len(inspect.stack()) > 2:
            frame = inspect.getframeinfo(inspect.stack()[2][0])
            program = os.path.basename(frame.filename)
            method = frame.function
            lineno = frame.lineno
        else:
            program = ""
            method = ""
            lineno = ""

        # Ensure messages are correctly encoded as some author names contain accents and the web page doesnt like them
        message = formatter.safe_unicode(message)
        message = message.encode(lazylibrarian.SYS_ENCODING)
        if level != 'DEBUG' or lazylibrarian.LOGLEVEL >= 2:
            # Limit the size of the "in-memory" log, as gets slow if too long
            lazylibrarian.LOGLIST.insert(0, (formatter.now(), level, threadname, program, method, lineno, message))
            if len(lazylibrarian.LOGLIST) > lazylibrarian.CONFIG['LOGLIMIT']:
                del lazylibrarian.LOGLIST[-1]

        message = "%s : %s:%s:%s : %s" % (threadname, program, method, lineno, message)

        if level == 'DEBUG':
            logger.debug(message)
        elif level == 'INFO':
            logger.info(message)
        elif level == 'WARNING':
            logger.warning(message)
        else:
            logger.error(message)


lazylibrarian_log = RotatingLogger('lazylibrarian.log')


def debug(message):
    if lazylibrarian.LOGLEVEL > 1:
        lazylibrarian_log.log(message, level='DEBUG')


def info(message):
    if lazylibrarian.LOGLEVEL > 0:
        lazylibrarian_log.log(message, level='INFO')


def warn(message):
    lazylibrarian_log.log(message, level='WARNING')


def error(message):
    lazylibrarian_log.log(message, level='ERROR')
