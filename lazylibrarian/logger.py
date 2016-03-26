import os
import threading
import logging

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
        l = logging.getLogger('lazylibrarian')
        l.removeHandler(self.filehandler)
        l.removeHandler(self.consolehandler) 
    
    def initLogger(self, loglevel=1):

        l = logging.getLogger('lazylibrarian')
        l.setLevel(logging.DEBUG)

        self.filename = os.path.join(lazylibrarian.LOGDIR, self.filename)

        filehandler = handlers.RotatingFileHandler(
            self.filename,
            maxBytes=lazylibrarian.LOGSIZE,
            backupCount=lazylibrarian.LOGFILES)

        filehandler.setLevel(logging.DEBUG)

        fileformatter = logging.Formatter('%(asctime)s - %(levelname)-7s :: %(message)s', '%d-%b-%Y %H:%M:%S')

        filehandler.setFormatter(fileformatter)
        l.addHandler(filehandler)
        self.filehandler = filehandler
        
        if loglevel:
            consolehandler = logging.StreamHandler()
            if loglevel == 1:
                consolehandler.setLevel(logging.INFO)
            if loglevel == 2:
                consolehandler.setLevel(logging.DEBUG)
            consoleformatter = logging.Formatter('%(asctime)s - %(levelname)s :: %(message)s', '%d-%b-%Y %H:%M:%S')
            consolehandler.setFormatter(consoleformatter)
            l.addHandler(consolehandler)
            self.consolehandler = consolehandler

    def log(self, message, level):

        logger = logging.getLogger('lazylibrarian')

        threadname = threading.currentThread().getName()

        # Ensure messages are utf-8 as some author names contain accents and the web page doesnt like them
        message = formatter.safe_unicode(message).encode('utf-8')

        if level != 'DEBUG' or lazylibrarian.LOGFULL is True:
            # Limit the size of the "in-memory" log, as gets slow if too long
            lazylibrarian.LOGLIST.insert(0, (formatter.now(), level, message))
            if len(lazylibrarian.LOGLIST) > lazylibrarian.LOGLIMIT:
                del lazylibrarian.LOGLIST[-1]

        message = threadname + ' : ' + message

        if level == 'DEBUG':
            logger.debug(message)
        elif level == 'INFO':
            logger.info(message)
        elif level == 'WARNING':
            logger.warn(message)
        else:
            logger.error(message)

lazylibrarian_log = RotatingLogger('lazylibrarian.log')


def debug(message):
    lazylibrarian_log.log(message, level='DEBUG')


def info(message):
    lazylibrarian_log.log(message, level='INFO')


def warn(message):
    lazylibrarian_log.log(message, level='WARNING')


def error(message):
    lazylibrarian_log.log(message, level='ERROR')
