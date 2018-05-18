import os
import lazylibrarian
from lazylibrarian import logger
from lazylibrarian.common import notifyStrings, NOTIFY_SNATCH, NOTIFY_DOWNLOAD
from lib.six import PY2
# noinspection PyUnresolvedReferences
from lib.six.moves.urllib_parse import urlencode
# noinspection PyUnresolvedReferences
from lib.six.moves.http_client import HTTPSConnection

import lib.gntp.notifier as gntp_notifier


class Growl_Notifier:
    def __init__(self):
        pass

    @staticmethod
    def _sendGrowl(growl_host=None, growl_password=None, event=None, message=None, force=False):

        title = "LazyLibrarian"

        # suppress notifications if the notifier is disabled but the notify options are checked
        if not lazylibrarian.CONFIG['USE_GROWL'] and not force:
            return False

        if growl_host is None:
            growl_host = lazylibrarian.CONFIG['GROWL_HOST']

        if growl_password is None:
            growl_password = lazylibrarian.CONFIG['GROWL_PASSWORD']

        if PY2:
            message = message.encode(lazylibrarian.SYS_ENCODING)

        logger.debug(u"Growl: title: " + title)
        logger.debug(u"Growl: event: " + event)
        logger.debug(u"Growl: message: " + message)

        # Split host and port
        if growl_host and ':' in growl_host:
            host, port = growl_host.split(':', 1)
            port = int(port)
        else:
            host, port = 'localhost', 23053

        # If password is empty, assume none
        if growl_password == "":
            growl_password = None

        try:
            # Register notification
            growl = gntp_notifier.GrowlNotifier(
                applicationName='LazyLibrarian',
                notifications=['New Event'],
                defaultNotifications=['New Event'],
                hostname=host,
                port=port,
                password=growl_password
            )
        except Exception as e:
            logger.error(e)
            return False

        try:
            growl.register()
        except gntp_notifier.errors.NetworkError:
            logger.warn(u'Growl notification failed: network error')
            return False

        except gntp_notifier.errors.AuthError:
            logger.warn(u'Growl notification failed: authentication error')
            return False

        # Send it, including an image if available
        image_file = os.path.join(lazylibrarian.PROG_DIR, "data/images/ll.png")
        if os.path.exists(image_file):
            with open(image_file, 'rb') as f:
                image = f.read()
        else:
            image = None

        try:
            growl.notify(
                noteType='New Event',
                title=event,
                description=message,
                icon=image
            )
        except gntp_notifier.errors.NetworkError:
            logger.warn(u'Growl notification failed: network error')
            return False

        logger.info(u"Growl notification sent.")
        return True

        #
        # Public functions
        #

    def notify_snatch(self, title):
        if lazylibrarian.CONFIG['GROWL_ONSNATCH']:
            self._sendGrowl(growl_host=None, growl_password=None, event=notifyStrings[NOTIFY_SNATCH], message=title)

    def notify_download(self, title):
        if lazylibrarian.CONFIG['GROWL_ONDOWNLOAD']:
            self._sendGrowl(growl_host=None, growl_password=None, event=notifyStrings[NOTIFY_DOWNLOAD], message=title)

    # noinspection PyUnusedLocal
    def test_notify(self, title="Test"):
        return self._sendGrowl(growl_host=None, growl_password=None, event="Test",
                               message="Testing Growl settings from LazyLibrarian", force=True)

notifier = Growl_Notifier
