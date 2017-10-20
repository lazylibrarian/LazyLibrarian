# Author: Marvin Pinto <me@marvinp.ca>
# Author: Dennis Lutter <lad1337@gmail.com>
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
import lib.requests as requests

import lazylibrarian
from lazylibrarian import logger
from lazylibrarian.common import notifyStrings, NOTIFY_SNATCH, NOTIFY_DOWNLOAD, proxyList
from lazylibrarian.formatter import getList, check_int

# from lazylibrarian.exceptions import ex

# API_URL = "https://boxcar.io/devices/providers/MH0S7xOFSwVLNvNhTpiC/notifications"
# changed to boxcar2
API_URL = 'https://new.boxcar.io/api/notifications'


class BoxcarNotifier:
    def __init__(self):
        pass

    def _sendBoxcar(self, msg, title, token, subscribe=False):
        """
        Sends a boxcar notification to the address provided

        msg: The message to send (unicode)
        title: The title of the message
        email: The email address to send the message to (or to subscribe with)
        subscribe: If true then instead of sending a message this function will send
        a subscription notification (optional, default is False)

        returns: True if the message succeeded, False otherwise
        """
        logger.debug('Boxcar notification: %s' % msg)
        logger.debug('Title: %s' % title)
        logger.debug('Token: %s' % token)
        logger.debug('Subscribe: %s' % subscribe)

        # build up the URL and parameters
        msg = msg.strip().encode(lazylibrarian.SYS_ENCODING)
        title = title.encode(lazylibrarian.SYS_ENCODING)
        curUrl = API_URL

        # if this is a subscription notification then act accordingly
        if subscribe:
            data = {'email': token}
            curUrl += "/subscribe"

        # for normal requests we need all these parameters
        else:
            data = {
                'user_credentials': token,
                'notification[title]': title,
                'notification[long_message]': msg,
                'notification[sound]': "done"
            }
        proxies = proxyList()
        # send the request to boxcar
        try:
            timeout = check_int(lazylibrarian.CONFIG['HTTP_TIMEOUT'], 30)
            r = requests.get(curUrl, params=data, timeout=timeout, proxies=proxies)
            status = str(r.status_code)
            if status.startswith('2'):
                logger.debug("BOXCAR: Notification successful.")
                return True

            # HTTP status 404 if the provided email address isn't a Boxcar user.
            if status == '404':
                logger.warn("BOXCAR: Username is wrong/not a boxcar email. Boxcar will send an email to it")
            # For HTTP status code 401's, it is because you are passing in either an
            # invalid token, or the user has not added your service.
            elif status == '401':
                # If the user has already added your service, we'll return an HTTP status code of 401.
                if subscribe:
                    logger.error("BOXCAR: Already subscribed to service")
                # HTTP status 401 if the user doesn't have the service added
                else:
                    subscribeNote = self._sendBoxcar(msg, title, token, True)
                    if subscribeNote:
                        logger.debug("BOXCAR: Subscription sent.")
                        return True
                    else:
                        logger.error("BOXCAR: Subscription could not be sent.")
            # If you receive an HTTP status code of 400, it is because you failed to send the proper parameters
            elif status == '400':
                logger.error("BOXCAR: Wrong data send to boxcar.")
            else:
                logger.error("BOXCAR: Got error code %s" % status)
            return False

        except Exception as e:
            # if we get an error back that doesn't have an error code then who knows what's really happening
            # URLError doesn't return a code, just a reason. HTTPError gives a code
            if not hasattr(e, 'code'):
                logger.error("BOXCAR: Boxcar notification failed: %s" % str(e))
            else:
                logger.error("BOXCAR: Boxcar notification failed. Error code: %s" % str(e.code))
            return False

    def _notify(self, title, message, username=None, force=False):
        """
        Sends a boxcar notification based on the provided info or SB config

        title: The title of the notification to send
        message: The message string to send
        username: The username to send the notification to (optional, defaults to the username in the config)
        force: If True then the notification will be sent even if Boxcar is disabled in the config
        """

        # suppress notifications if the notifier is disabled but the notify options are checked
        if not lazylibrarian.CONFIG['USE_BOXCAR'] and not force:
            return False

        # if no username was given then use the one from the config
        if not username:
            username = lazylibrarian.CONFIG['BOXCAR_TOKEN']

        return self._sendBoxcar(message, title, username)

    #
    # Public functions
    #

    def notify_snatch(self, title):
        if lazylibrarian.CONFIG['BOXCAR_NOTIFY_ONSNATCH']:
            self._notify(notifyStrings[NOTIFY_SNATCH], title)

    def notify_download(self, title):
        if lazylibrarian.CONFIG['BOXCAR_NOTIFY_ONDOWNLOAD']:
            self._notify(notifyStrings[NOTIFY_DOWNLOAD], title)

    def test_notify(self, title="Test"):
        return self._notify("This is a test notification from LazyLibrarian", title, force=True)

    def update_library(self, showName=None):
        pass


notifier = BoxcarNotifier
