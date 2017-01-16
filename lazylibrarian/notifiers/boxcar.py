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

import urllib
import urllib2

import lazylibrarian
from lazylibrarian import logger
from lazylibrarian.common import notifyStrings, NOTIFY_SNATCH, NOTIFY_DOWNLOAD

# from lazylibrarian.exceptions import ex

# API_URL = "https://boxcar.io/devices/providers/MH0S7xOFSwVLNvNhTpiC/notifications"
# changed to boxcar2
API_URL = 'https://new.boxcar.io/api/notifications'


class BoxcarNotifier:
    def _sendBoxcar(self, msg, title, token, subscribe=False):
        """
        Sends a boxcar notification to the address provided

        msg: The message to send (unicode)
        title: The title of the message
        email: The email address to send the message to (or to subscribe with)
        subscribe: If true then instead of sending a message this function will send a subscription notification (optional, default is False)

        returns: True if the message succeeded, False otherwise
        """
        logger.debug('Boxcar notification: %s' % msg)
        logger.debug('Title: %s' % title)
        logger.debug('Token: %s' % token)
        logger.debug('Subscribe: %s' % subscribe)

        # build up the URL and parameters
        msg = msg.strip()
        curUrl = API_URL

        # if this is a subscription notification then act accordingly
        if subscribe:
            data = urllib.urlencode({'email': token})
            curUrl += "/subscribe"

        # for normal requests we need all these parameters
        else:
            # data = urllib.urlencode({
            #    'email': email,
            #    'notification[from_screen_name]': title,
            #    'notification[message]': msg.encode('utf-8'),
            #    'notification[from_remote_service_id]': int(time.time())
            #    })
            data = urllib.urlencode({
                'user_credentials': token,
                'notification[title]': title.encode('utf-8'),
                'notification[long_message]': msg.encode('utf-8'),
                'notification[sound]': "done"
            })

        # send the request to boxcar
        try:
            # TODO: Use our getURL from helper?
            req = urllib2.Request(curUrl)
            handle = urllib2.urlopen(req, data)
            handle.close()

        except (urllib2.URLError, urllib2.HTTPError) as e:
            # if we get an error back that doesn't have an error code then who knows what's really happening
            # URLError doesn't return a code, just a reason. HTTPError gives a code
            if not hasattr(e, 'code'):
                logger.error(u"BOXCAR: Boxcar notification failed." + str(e))
                return False
            else:
                logger.error(u"BOXCAR: Boxcar notification failed. Error code: " + str(e.code))

            # HTTP status 404 if the provided email address isn't a Boxcar user.
            if e.code == 404:
                logger.warn(
                    u"BOXCAR: Username is wrong/not a boxcar email. Boxcar will send an email to it")
                return False

            # For HTTP status code 401's, it is because you are passing in either an
            # invalid token, or the user has not added your service.
            elif e.code == 401:
                # If the user has already added your service, we'll return an HTTP status code of 401.
                if subscribe:
                    logger.error(u"BOXCAR: Already subscribed to service")
                    # i dont know if this is true or false ... its neither but i also dont
                    # know how we got here in the first place
                    return False

                # HTTP status 401 if the user doesn't have the service added
                else:
                    subscribeNote = self._sendBoxcar(msg, title, token, True)
                    if subscribeNote:
                        logger.debug(u"BOXCAR: Subscription sent.")
                        return True
                    else:
                        logger.error(u"BOXCAR: Subscription could not be sent.")
                        return False

            # If you receive an HTTP status code of 400, it is because you failed to send the proper parameters
            elif e.code == 400:
                logger.error(u"BOXCAR: Wrong data send to boxcar.")
                return False

        logger.debug(u"BOXCAR: Boxcar notification successful.")
        return True

    def _notify(self, title, message, username=None, force=False):
        """
        Sends a boxcar notification based on the provided info or SB config

        title: The title of the notification to send
        message: The message string to send
        username: The username to send the notification to (optional, defaults to the username in the config)
        force: If True then the notification will be sent even if Boxcar is disabled in the config
        """

        # suppress notifications if the notifier is disabled but the notify options are checked
        if not lazylibrarian.USE_BOXCAR and not force:
            return False

        # if no username was given then use the one from the config
        if not username:
            username = lazylibrarian.BOXCAR_TOKEN

        logger.debug(u"BOXCAR: Sending notification for " + message)

        return self._sendBoxcar(message, title, username)

    #
    # Public functions
    #

    def notify_snatch(self, title):
        if lazylibrarian.BOXCAR_NOTIFY_ONSNATCH:
            self._notify(notifyStrings[NOTIFY_SNATCH], title)

    def notify_download(self, title):
        if lazylibrarian.BOXCAR_NOTIFY_ONDOWNLOAD:
            self._notify(notifyStrings[NOTIFY_DOWNLOAD], title)

    def test_notify(self, title="Test"):
        return self._notify("This is a test notification from LazyLibrarian", title, force=True)

    def update_library(self, showName=None):
        pass


notifier = BoxcarNotifier
