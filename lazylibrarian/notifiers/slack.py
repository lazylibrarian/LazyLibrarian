# This file is part of LazyLibrarian.
#
# LazyLibrarian is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# LazyLibrarian is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
#  GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with LazyLibrarian.  If not, see <http://www.gnu.org/licenses/>.
try:
    import requests
except ImportError:
    import lib.requests as requests

import lazylibrarian
from lazylibrarian import logger
from lazylibrarian.common import notifyStrings, NOTIFY_SNATCH, NOTIFY_DOWNLOAD
from lazylibrarian.formatter import unaccented


class SlackNotifier:

    def __init__(self):
        pass

    @staticmethod
    def _sendSlack(message=None, event=None, slack_token=None,
                   method=None, force=False):
        if not lazylibrarian.CONFIG['USE_SLACK'] and not force:
            return False

        url = lazylibrarian.CONFIG['SLACK_URL']
        if not url.startswith("http"):
            url = 'https://' + url
        if not url.endswith("/"):
            url = url + '/'

        if slack_token is None:
            slack_token = lazylibrarian.CONFIG['SLACK_TOKEN']
        if method is None:
            method = 'POST'
        if event == "Test":
            logger.debug("Testing Slack notification")
        else:
            logger.debug("Slack message: %s: %s" % (event, message))

        if slack_token.startswith(url):
            url = slack_token
        else:
            url = url + slack_token
        headers = {"Content-Type": "application/json"}

        postdata = '{"username": "LazyLibrarian", '
        postdata += '"attachments": [{"text": "%s", "thumb_url": ' % message
        postdata += '"https://github.com/DobyTang/LazyLibrarian/raw/master/data/images/ll.png"}], '
        postdata += '"text":"%s"}' % event
        r = requests.request(method,
                             url,
                             data=postdata,
                             headers=headers
                             )
        if r.text.startswith('<!DOCTYPE html>'):
            logger.debug("Slack returned html errorpage")
            return "Invalid or missing Webhook"
        logger.debug("Slack returned [%s]" % r.text)
        return r.text

    def _notify(self, message=None, event=None, slack_token=None, method=None, force=False):
        """
        Sends a slack incoming-webhook notification based on the provided info or LL config

        message: The message string to send
        force: If True then the notification will be sent even if slack is disabled in the config
        """
        try:
            message = unaccented(message)
        except Exception as e:
            logger.warn("Slack: could not convert message: %s" % e)
        # suppress notifications if the notifier is disabled but the notify options are checked
        if not lazylibrarian.CONFIG['USE_SLACK'] and not force:
            return False

        return self._sendSlack(message, event, slack_token, method, force)

#
# Public functions
#

    def notify_snatch(self, title):
        if lazylibrarian.CONFIG['SLACK_NOTIFY_ONSNATCH']:
            self._notify(message=title, event=notifyStrings[NOTIFY_SNATCH])

    def notify_download(self, title):
        if lazylibrarian.CONFIG['SLACK_NOTIFY_ONDOWNLOAD']:
            self._notify(message=title, event=notifyStrings[NOTIFY_DOWNLOAD])

    def test_notify(self, title="Test"):
        return self._notify(message="This is a test notification from LazyLibrarian",
                            event=title, force=True)


notifier = SlackNotifier
