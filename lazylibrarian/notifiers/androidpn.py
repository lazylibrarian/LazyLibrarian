# Author: Marvin Pinto <me@marvinp.ca>
# Author: Dennis Lutter <lad1337@gmail.com>
# Author: Aaron Bieber <deftly@gmail.com>
# URL: http://code.google.com/p/lazylibrarian/
#
# This file is part of Sick Beard.
#
# Sick Beard is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# Sick Beard is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
#  GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with Sick Beard.  If not, see <http://www.gnu.org/licenses/>.
try:
    import requests
except ImportError:
    import lib.requests as requests

import lazylibrarian
from lazylibrarian import logger
from lazylibrarian.common import notifyStrings, NOTIFY_SNATCH, NOTIFY_DOWNLOAD, proxyList
from lazylibrarian.formatter import check_int


class AndroidPNNotifier:
    def __init__(self):
        pass

    def _sendAndroidPN(self, title, msg, url, username, broadcast):

        # build up the URL and parameters
        msg = msg.strip()
        msg = msg.encode(lazylibrarian.SYS_ENCODING)

        data = {
            'action': "send",
            'broadcast': broadcast,
            'uri': "",
            'title': title,
            'username': username,
            'message': msg,
        }
        proxies = proxyList()
        # send the request
        try:
            timeout = check_int(lazylibrarian.CONFIG['HTTP_TIMEOUT'], 30)
            r = requests.get(url, params=data, timeout=timeout, proxies=proxies)
            status = str(r.status_code)
            if status.startswith('2'):
                logger.debug("ANDROIDPN: Notification successful.")
                return True

            # HTTP status 404 if the provided email address isn't a AndroidPN user.
            if status == '404':
                logger.warn("ANDROIDPN: Username is wrong/not a AndroidPN email. AndroidPN will send an email to it")
            # For HTTP status code 401's, it is because you are passing in either an
            # invalid token, or the user has not added your service.
            elif status == '401':
                subscribeNote = self._sendAndroidPN(title, msg, url, username, broadcast)
                if subscribeNote:
                    logger.debug("ANDROIDPN: Subscription sent")
                    return True
                else:
                    logger.error("ANDROIDPN: Subscription could not be sent")

            # If you receive an HTTP status code of 400, it is because you failed to send the proper parameters
            elif status == '400':
                logger.error(u"ANDROIDPN: Wrong data sent to AndroidPN")
            else:
                logger.error(u"ANDROIDPN: Got error code %s" % status)
            return False

        except Exception as e:
            # URLError only returns a reason, not a code. HTTPError gives a code
            # FIXME: Python 2.5 hack, it wrongly reports 201 as an error
            if hasattr(e, 'code') and e.code == 201:
                logger.debug(u"ANDROIDPN: Notification successful.")
                return True

            # if we get an error back that doesn't have an error code then who knows what's really happening
            if not hasattr(e, 'code'):
                logger.error(u"ANDROIDPN: Notification failed.")
            else:
                # noinspection PyUnresolvedReferences
                logger.error(u"ANDROIDPN: Notification failed. Error code: " + str(e.code))
            return False

    def _notify(self, title, message, url=None, username=None, broadcast=None, force=False):
        """
        Sends a pushover notification based on the provided info or SB config
        """

        # suppress notifications if the notifier is disabled but the notify options are checked
        if not lazylibrarian.CONFIG['USE_ANDROIDPN'] and not force:
            return False

        # fill in omitted parameters
        if not username:
            username = lazylibrarian.CONFIG['ANDROIDPN_USERNAME']
        if not url:
            url = lazylibrarian.CONFIG['ANDROIDPN_URL']
        if not broadcast:
            broadcast = lazylibrarian.CONFIG['ANDROIDPN_BROADCAST']
            if broadcast:
                broadcast = 'Y'
            else:
                broadcast = 'N'

        logger.debug('ANDROIDPN: Sending notice: title="%s", message="%s", username=%s, url=%s, broadcast=%s' %
                     (title, message, username, url, broadcast))

        if not username or not url:
            return False

        return self._sendAndroidPN(title, message, url, username, broadcast)

    #
    # Public functions
    #

    def notify_snatch(self, ep_name):
        if lazylibrarian.CONFIG['ANDROIDPN_NOTIFY_ONSNATCH']:
            self._notify(notifyStrings[NOTIFY_SNATCH], ep_name)

    def notify_download(self, ep_name):
        if lazylibrarian.CONFIG['ANDROIDPN_NOTIFY_ONDOWNLOAD']:
            self._notify(notifyStrings[NOTIFY_DOWNLOAD], ep_name)

    def test_notify(self):
        return self._notify("Test", "This is a test notification from LazyLibrarian", force=True)

    def update_library(self, ep_obj=None):
        pass


notifier = AndroidPNNotifier
