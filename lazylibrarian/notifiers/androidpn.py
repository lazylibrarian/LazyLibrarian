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

import urllib
import urllib2

import lazylibrarian
from lazylibrarian import logger
from lazylibrarian.common import notifyStrings, NOTIFY_SNATCH, NOTIFY_DOWNLOAD


class AndroidPNNotifier:

    def _sendAndroidPN(self, title, msg, url, username, broadcast):

        # build up the URL and parameters
        msg = msg.strip()

        data = urllib.urlencode({
            'action': "send",
            'broadcast': broadcast,
            'uri': "",
            'title': title,
            'username': username,
            'message': msg.encode('utf-8'),
        })

        # send the request to pushover
        try:
            req = urllib2.Request(url)
            handle = urllib2.urlopen(req, data)
            handle.close()

        except (urllib2.URLError, urllib2.HTTPError) as e:
            # URLError only returns a reason, not a code. HTTPError gives a code
            # FIXME: Python 2.5 hack, it wrongly reports 201 as an error
            if hasattr(e, 'code') and e.code == 201:
                logger.debug(u"ANDROIDPN: Notification successful.")
                return True

            # if we get an error back that doesn't have an error code then who knows what's really happening
            if not hasattr(e, 'code'):
                logger.error(u"ANDROIDPN: Notification failed.")
                return False
            else:
                logger.error(u"ANDROIDPN: Notification failed. Error code: " + str(e.code))

            # HTTP status 404 if the provided email address isn't a AndroidPN user.
            if e.code == 404:
                logger.warn(
                    u"ANDROIDPN: Username is wrong/not a AndroidPN email. AndroidPN will send an email to it")
                return False

            # For HTTP status code 401's, it is because you are passing in either an
            # invalid token, or the user has not added your service.
            elif e.code == 401:

                # HTTP status 401 if the user doesn't have the service added
                subscribeNote = self._sendAndroidPN(title, msg, url, username, broadcast)
                if subscribeNote:
                    logger.debug(u"ANDROIDPN: Subscription sent")
                    return True
                else:
                    logger.error(u"ANDROIDPN: Subscription could not be sent")
                    return False

            # If you receive an HTTP status code of 400, it is because you failed to send the proper parameters
            elif e.code == 400:
                logger.error(u"ANDROIDPN: Wrong data sent to AndroidPN")
                return False

        logger.debug(u"ANDROIDPN: Notification successful.")
        return True

    def _notify(self, title, message, url=None, username=None, broadcast=None, force=False):
        """
        Sends a pushover notification based on the provided info or SB config
        """

        # suppress notifications if the notifier is disabled but the notify options are checked
        if not lazylibrarian.USE_ANDROIDPN and not force:
            return False

        # fill in omitted parameters
        if not username:
            username = lazylibrarian.ANDROIDPN_USERNAME
        if not url:
            url = lazylibrarian.ANDROIDPN_URL
        if not broadcast:
            broadcast = lazylibrarian.ANDROIDPN_BROADCAST
            if broadcast:
                broadcast = 'Y'
            else:
                broadcast = 'N'

        logger.debug(u"ANDROIDPN: Sending notice with details: title=\"%s\", message=\"%s\", username=%s, url=%s, broadcast=%s" %
                     (title, message, username, url, broadcast))

        return self._sendAndroidPN(title, message, url, username, broadcast)

#
# Public functions
#

    def notify_snatch(self, ep_name):
        if lazylibrarian.ANDROIDPN_NOTIFY_ONSNATCH:
            self._notify(notifyStrings[NOTIFY_SNATCH], ep_name)

    def notify_download(self, ep_name):
        if lazylibrarian.ANDROIDPN_NOTIFY_ONDOWNLOAD:
            self._notify(notifyStrings[NOTIFY_DOWNLOAD], ep_name)

    def test_notify(self, url, username, broadcast):
        return self._notify("Test", "This is a test notification from Sick Beard", url, username, broadcast, force=True)

    def update_library(self, ep_obj=None):
        pass

notifier = AndroidPNNotifier
