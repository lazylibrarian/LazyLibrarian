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
import lazylibrarian.common as common

from httplib import HTTPSConnection, HTTPException
from urllib import urlencode
from lazylibrarian import logger
from lazylibrarian.common import notifyStrings, NOTIFY_SNATCH, NOTIFY_DOWNLOAD


class PushoverNotifier:

    def _sendPushover(self, message=None, event=None, pushover_apitoken=None, pushover_keys=None,
                      pushover_device=None, notificationType=None, method=None, force=False):

        if not lazylibrarian.USE_PUSHOVER and not force:
            return False

        if pushover_apitoken == None:
            pushover_apitoken = lazylibrarian.PUSHOVER_APITOKEN
        if pushover_keys == None:
            pushover_keys = lazylibrarian.PUSHOVER_KEYS
        if pushover_device == None:
            pushover_device = lazylibrarian.PUSHOVER_DEVICE
        if method == None:
            method = 'POST'
        if notificationType == None:
            testMessage = True
            uri = "/1/users/validate.json"
            logger.debug("Testing Pushover authentication and retrieving the device list.")
        else:
            testMessage = False
            uri = "/1/messages.json"
            logger.debug("Pushover event: " + str(event))
            logger.debug("Pushover message: " + str(message))
            logger.debug("Pushover api: " + str())
            logger.debug("Pushover keys: " + str(pushover_keys))
            logger.debug("Pushover device: " + str(pushover_device))
            logger.debug("Pushover notification type: " + str(notificationType))

        http_handler = HTTPSConnection('api.pushover.net')
        
        try:
            data = {'token': pushover_apitoken,
                    'user': pushover_keys,
                    'title': event.encode('utf-8'),
                    'message': message.encode("utf-8"),
                    'device': pushover_device,
                    'priority': lazylibrarian.PUSHOVER_PRIORITY}
            http_handler.request("POST",
                                 uri,
                                 headers={'Content-type': "application/x-www-form-urlencoded"},
                                 body=urlencode(data))
            pass
        except Exception, e:
            logger.error(str(e))
            return False

        response = http_handler.getresponse()
        request_body = response.read()
        request_status = response.status
        logger.debug("Pushover Response: %s" % request_status)
        logger.debug("Pushover Reason: %s" % response.reason)
        if request_status == 200:
            if testMessage:
                logger.debug(request_body)
                if 'devices' in request_body:
                    return "Devices: %s" % request_body.split('[')[1].split(']')[0]
                else:
                    return request_body  
            else:
                return True
        elif request_status >= 400 and request_status < 500:
            logger.error("Pushover request failed: %s" % response.reason)
            return False
        else:
            logger.error("Pushover notification failed: %s" % request_status)
            return False

    def _notify(self, message=None, event=None, pushover_apitoken=None, pushover_keys=None,
                pushover_device=None, notificationType=None, method=None, force=False):
        """
        Sends a pushover notification based on the provided info or LL config

        title: The title of the notification to send
        message: The message string to send
        username: The username to send the notification to (optional, defaults to the username in the config)
        force: If True then the notification will be sent even if pushover is disabled in the config
        """
        try:
            message = common.remove_accents(message)
        except Exception, e:
            logger.warn("Pushover: could not convert  message: %s" % e)
        # suppress notifications if the notifier is disabled but the notify options are checked
        if not lazylibrarian.USE_PUSHOVER and not force:
            return False

        logger.debug("Pushover: Sending notification " + str(message))

        return self._sendPushover(message, event, pushover_apitoken, pushover_keys, pushover_device, notificationType, method)

#
# Public functions
#

    def notify_snatch(self, title):
        if lazylibrarian.PUSHOVER_ONSNATCH:
            self._notify(message=title, event=notifyStrings[NOTIFY_SNATCH], notificationType='note')

    def notify_download(self, title):
        if lazylibrarian.PUSHOVER_ONDOWNLOAD:
            self._notify(message=title, event=notifyStrings[NOTIFY_DOWNLOAD], notificationType='note')

    def test_notify(self, title="Test"):
        return self._notify(message="This is a test notification from LazyLibrarian", event=title, notificationType=None)

    def update_library(self, showName=None):
        pass

notifier = PushoverNotifier
