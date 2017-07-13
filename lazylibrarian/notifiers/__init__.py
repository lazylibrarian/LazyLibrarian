# Author: Nic Wolfe <nic@wolfeden.ca>
# URL: http://code.google.com/p/sickbeard/
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

import androidpn
import boxcar
import custom_notify
import email_notify
import nma
import prowl
import pushbullet
import pushover
import slack
import tweet
from lazylibrarian import logger

# online
twitter_notifier = tweet.TwitterNotifier()
boxcar_notifier = boxcar.BoxcarNotifier()
pushbullet_notifier = pushbullet.PushbulletNotifier()
pushover_notifier = pushover.PushoverNotifier()
androidpn_notifier = androidpn.AndroidPNNotifier()
prowl_notifier = prowl.Prowl_Notifier()
nma_notifier = nma.NMA_Notifier()
slack_notifier = slack.SlackNotifier()
email_notifier = email_notify.EmailNotifier()
#
custom_notifier = custom_notify.CustomNotifier()

notifiers = [
    twitter_notifier,
    boxcar_notifier,
    pushbullet_notifier,
    pushover_notifier,
    androidpn_notifier,
    prowl_notifier,
    nma_notifier,
    slack_notifier,
    email_notifier
]


def custom_notify_download(bookid):
    try:
        custom_notifier.notify_download(bookid)
    except Exception as e:
        logger.warn('Custom notify download failed: %s' % str(e))


def custom_notify_snatch(bookid):
    try:
        custom_notifier.notify_snatch(bookid)
    except Exception as e:
        logger.warn('Custom notify snatch failed: %s' % str(e))


def notify_download(title, bookid=None):
    try:
        for n in notifiers:
            if 'EmailNotifier' in str(n):
                n.notify_download(title, bookid=bookid)
            else:
                n.notify_download(title)
    except Exception as e:
        logger.warn('Notify download failed: %s' % str(e))


def notify_snatch(title):
    try:
        for n in notifiers:
            n.notify_snatch(title)
    except Exception as e:
        logger.warn('Notify snatch failed: %s' % str(e))
