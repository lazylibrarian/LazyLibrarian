# Author: Marvin Pinto <me@marvinp.ca>
# Author: Dennis Lutter <lad1337@gmail.com>
# URL: http://code.google.com/p/lazylibrarian/
#
# This file is part of LazyLibrarian.
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

import base64
import urllib
import urllib2
import time
import lazylibrarian

from httplib import HTTPSConnection, HTTPException
from urllib import urlencode
from lazylibrarian import logger
from lazylibrarian.common import notifyStrings, NOTIFY_SNATCH, NOTIFY_DOWNLOAD


class PushbulletNotifier:

    def _sendPushbullet(self, message=None, event=None, pushbullet_token=None, pushbullet_deviceid=None, 
                        notificationType=None, method=None, force=False):

        if not lazylibrarian.USE_PUSHBULLET and not force:
            return False

        if pushbullet_token == None:
            pushbullet_token = lazylibrarian.PUSHBULLET_TOKEN
        if pushbullet_deviceid == None:
            pushbullet_deviceid = lazylibrarian.PUSHBULLET_DEVICEID
        method = 'POST'
        if method == 'POST':
            uri = '/api/pushes'
        else:
            uri = '/api/devices'

        logger.debug("Pushbullet event: " + str(event))
        logger.debug("Pushbullet message: " + str(message))
        logger.debug("Pushbullet api: " + str(pushbullet_token))
        logger.debug("Pushbullet devices: " + str(pushbullet_deviceid))
        logger.debug("Pushbullet notification type: " + str(notificationType))

        http_handler = HTTPSConnection('api.pushbullet.com')

        authString = base64.encodestring('%s:' % (pushbullet_token)).replace('\n', '')

        if notificationType == None:
            testMessage = True
            try:
                logger.debug("Testing Pushbullet authentication and retrieving the device list.")
                http_handler.request(method, uri, None, headers={'Authorization': 'Basic %s:' % authString})
            except (SSLError, HTTPException):
                logger.error("Pushbullet notification failed.")
                return False
        else:
            testMessage = False
            try:
                data = {
                        'title': event.encode('utf-8'),
                        'body': message.encode('utf-8'),
                        'device_iden': pushbullet_deviceid,
                        'type': notificationType}
                http_handler.request(method, uri, body=urlencode(data),
                             headers={'Authorization': 'Basic %s' % authString})
                pass
            except (SSLError, HTTPException):
                return False

        response = http_handler.getresponse()
        request_body = response.read()
        request_status = response.status
        logger.debug("Pushbullet Response: %s" % request_status)
        logger.debug("Pushbullet Reason: %s" % response.reason)
        if request_status == 200:
            if testMessage:
                return request_body
            else:
                logger.debug("Pushbullet notifications sent.")
                return True
        elif request_status == 410:
            logger.error("Pushbullet auth failed: %s" % response.reason)
            return False
        else:
            logger.error("Pushbullet notification failed.")
            return False

    def _notify(self, message=None, event=None, pushbullet_token=None, pushbullet_deviceid=None, 
                notificationType=None, method=None, force=False):
        """
        Sends a pushbullet notification based on the provided info or LL config

        title: The title of the notification to send
        message: The message string to send
        username: The username to send the notification to (optional, defaults to the username in the config)
        force: If True then the notification will be sent even if pushbullet is disabled in the config
        """

        # suppress notifications if the notifier is disabled but the notify options are checked
        if not lazylibrarian.USE_PUSHBULLET and not force:
            return False

        logger.debug("Pushbullet: Sending notification for " + str(message))

        self._sendPushbullet(message,event,pushbullet_token,pushbullet_deviceid,notificationType,method)
        return True

##############################################################################
# Public functions
##############################################################################

    def notify_snatch(self, title):
        if lazylibrarian.PUSHBULLET_NOTIFY_ONSNATCH:
            self._notify(message=title, event=notifyStrings[NOTIFY_SNATCH], notificationType='note', method='POST')

    def notify_download(self, title):
        if lazylibrarian.PUSHBULLET_NOTIFY_ONDOWNLOAD:
            self._notify( message=title, event=notifyStrings[NOTIFY_DOWNLOAD], notificationType='note', method='POST')

    def test_notify(self, token, title="Test"):
        return self._sendPushbullet("This is a test notification from LazyLibrarian", title, token)

    def update_library(self, showName=None):
        pass

notifier = PushbulletNotifier
