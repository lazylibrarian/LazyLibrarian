import lazylibrarian
import lib.requests as requests

from lazylibrarian import logger
from lazylibrarian.common import notifyStrings, NOTIFY_SNATCH, NOTIFY_DOWNLOAD


class Telegram_Notifier:
    def __init__(self):
        pass

    @staticmethod
    def _notify(telegram_token=None, telegram_userid=None, event=None, message=None, force=False):

        # suppress notifications if the notifier is disabled but the notify options are checked
        if not lazylibrarian.CONFIG['USE_TELEGRAM'] and not force:
            return False

        TELEGRAM_API = "https://api.telegram.org/bot%s/%s"

        if telegram_token is None:
            telegram_token = lazylibrarian.CONFIG['TELEGRAM_TOKEN']

        if telegram_userid is None:
            telegram_userid = lazylibrarian.CONFIG['TELEGRAM_USERID']

        logger.debug(u"Telegram: event: " + event)
        logger.debug(u"Telegram: message: " + message)

        # Construct message
        payload = {'chat_id': telegram_userid, 'text': event + ': ' + message}

        # Send message to user using Telegram's Bot API
        try:
            url = TELEGRAM_API % (telegram_token, "sendMessage")
            logger.debug(url)
            logger.debug(payload)
            response = requests.request('POST', url, data=payload)
        except Exception, e:
            logger.warn(u'Telegram notify failed: ' + str(e))
            return False

        if response.status_code == 200:
            return True
        else:
            logger.warn('Could not send notification to TelegramBot (token=%s). Response: [%s]' %
                        (telegram_token, response.text))
            return False
            #
            # Public functions
            #

    def notify_snatch(self, title):
        if lazylibrarian.CONFIG['TELEGRAM_ONSNATCH']:
            self._notify(telegram_token=None, telegram_userid=None, event=notifyStrings[NOTIFY_SNATCH], message=title)

    def notify_download(self, title):
        if lazylibrarian.CONFIG['TELEGRAM_ONDOWNLOAD']:
            self._notify(telegram_token=None, telegram_userid=None, event=notifyStrings[NOTIFY_DOWNLOAD], message=title)

    # noinspection PyUnusedLocal
    def test_notify(self, title="Test"):
        return self._notify(telegram_token=None, telegram_userid=None, event="Test",
                            message="Testing Telegram settings from LazyLibrarian", force=True)


notifier = Telegram_Notifier
