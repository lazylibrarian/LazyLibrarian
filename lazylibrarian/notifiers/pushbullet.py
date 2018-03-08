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

import lazylibrarian

from lazylibrarian import logger
from lazylibrarian.common import notifyStrings, NOTIFY_SNATCH, NOTIFY_DOWNLOAD
from lazylibrarian.formatter import unaccented
from .pushbullet2 import PushBullet


class PushbulletNotifier:

    def __init__(self):
        pass

    @staticmethod
    def _sendPushbullet(message=None, event=None, pushbullet_token=None, pushbullet_deviceid=None, force=False):

        if not lazylibrarian.CONFIG['USE_PUSHBULLET'] and not force:
            return False

        if pushbullet_token is None:
            pushbullet_token = lazylibrarian.CONFIG['PUSHBULLET_TOKEN']
        if pushbullet_deviceid is None:
            if lazylibrarian.CONFIG['PUSHBULLET_DEVICEID']:
                pushbullet_deviceid = lazylibrarian.CONFIG['PUSHBULLET_DEVICEID']

        logger.debug("Pushbullet event: " + str(event))
        logger.debug("Pushbullet message: " + str(message))
        logger.debug("Pushbullet api: " + str(pushbullet_token))
        logger.debug("Pushbullet devices: " + str(pushbullet_deviceid))

        pb = PushBullet(str(pushbullet_token))

        if event == 'DeviceList':  # special case, return device list
            devices = pb.getDevices()
            ret = ""
            for device in devices:
                logger.info("Pushbullet: %s [%s]" % (device["nickname"], device["iden"]))
                ret += "\nPushbullet: %s [%s]" % (device["nickname"], device["iden"])
            _ = pb.pushNote(pushbullet_deviceid, str(event), str(message))
            return ret
        else:
            push = pb.pushNote(pushbullet_deviceid, str(event), str(message))
            return push

    def _notify(self, message=None, event=None, pushbullet_token=None, pushbullet_deviceid=None, force=False):
        """
        Sends a pushbullet notification based on the provided info or LL config

        title: The title of the notification to send
        message: The message string to send
        username: The username to send the notification to (optional, defaults to the username in the config)
        force: If True then the notification will be sent even if pushbullet is disabled in the config
        """
        try:
            message = unaccented(message)
        except Exception as e:
            logger.warn("Pushbullet: could not convert  message: %s" % e)

        # suppress notifications if the notifier is disabled but the notify options are checked
        if not lazylibrarian.CONFIG['USE_PUSHBULLET'] and not force:
            return False
        logger.debug("Pushbullet: Sending notification " + str(message))

        return self._sendPushbullet(message, event, pushbullet_token, pushbullet_deviceid, force=force)

#
# Public functions
#

    def notify_snatch(self, title):
        if lazylibrarian.CONFIG['PUSHBULLET_NOTIFY_ONSNATCH']:
            self._notify(message=title, event=notifyStrings[NOTIFY_SNATCH])

    def notify_download(self, title):
        if lazylibrarian.CONFIG['PUSHBULLET_NOTIFY_ONDOWNLOAD']:
            self._notify(message=title, event=notifyStrings[NOTIFY_DOWNLOAD])

    def test_notify(self, title="Test"):
        res = self._notify("This test notification asks for the device list", event='DeviceList', force=True)
        if res:
            _ = self._notify("This is a test notification from LazyLibrarian", event=title, force=True)
        return res

    def update_library(self, showName=None):
        pass


notifier = PushbulletNotifier
