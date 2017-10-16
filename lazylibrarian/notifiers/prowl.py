from httplib import HTTPSConnection
from urllib import urlencode

import lazylibrarian
from lazylibrarian import logger
from lazylibrarian.common import notifyStrings, NOTIFY_SNATCH, NOTIFY_DOWNLOAD


class Prowl_Notifier:
    def __init__(self):
        pass

    @staticmethod
    def _sendProwl(prowl_api=None, prowl_priority=None, event=None, message=None, force=False):

        title = "LazyLibrarian"

        # suppress notifications if the notifier is disabled but the notify options are checked
        if not lazylibrarian.CONFIG['USE_PROWL'] and not force:
            return False

        if prowl_api is None:
            prowl_api = lazylibrarian.CONFIG['PROWL_APIKEY']

        if prowl_priority is None:
            prowl_priority = lazylibrarian.CONFIG['PROWL_PRIORITY']

        message = message.encode(lazylibrarian.SYS_ENCODING)

        logger.debug(u"Prowl: title: " + title)
        logger.debug(u"Prowl: event: " + event)
        logger.debug(u"Prowl: message: " + message)

        data = {'event': event,
                'description': message,
                'application': title,
                'apikey': prowl_api,
                'priority': prowl_priority
                }

        try:
            http_handler = HTTPSConnection("api.prowlapp.com")

            http_handler.request("POST",
                                 "/publicapi/add",
                                 headers={'Content-type': "application/x-www-form-urlencoded"},
                                 body=urlencode(data))

            response = http_handler.getresponse()
            request_status = response.status

            if request_status == 200:
                logger.info('Prowl notifications sent.')
                return True
            elif request_status == 401:
                logger.info('Prowl auth failed: %s' % response.reason)
                return False
            else:
                logger.info('Prowl notification failed.')
                return False

        except Exception as e:
            logger.warn('Error sending to Prowl: %s' % e)
            return False
        #
        # Public functions
        #

    def notify_snatch(self, title):
        if lazylibrarian.CONFIG['PROWL_ONSNATCH']:
            self._sendProwl(prowl_api=None, prowl_priority=None, event=notifyStrings[NOTIFY_SNATCH], message=title)

    def notify_download(self, title):
        if lazylibrarian.CONFIG['PROWL_ONDOWNLOAD']:
            self._sendProwl(prowl_api=None, prowl_priority=None, event=notifyStrings[NOTIFY_DOWNLOAD], message=title)

    # noinspection PyUnusedLocal
    def test_notify(self, title="Test"):
        return self._sendProwl(prowl_api=None, prowl_priority=None, event="Test",
                               message="Testing Prowl settings from LazyLibrarian", force=True)

    def update_library(self, showName=None):
        pass


notifier = Prowl_Notifier
