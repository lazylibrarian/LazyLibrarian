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

import lazylibrarian
import subprocess
from lazylibrarian import logger, database
from lazylibrarian.common import notifyStrings, NOTIFY_SNATCH, NOTIFY_DOWNLOAD


class CustomNotifier:
    @staticmethod
    def _notify(message, event, force=False):

        # suppress notifications if the notifier is disabled but the notify options are checked
        if not lazylibrarian.CONFIG['USE_CUSTOM'] and not force:
            return False

        subject = event
        text = message

        logger.debug('Custom Event: %s' % event)
        logger.debug('Custom Message: %s' % message)
        myDB = database.DBConnection()
        if subject == "Test":
            # grab the first entry in the book table
            data = myDB.match('SELECT * from books')
        else:
            # message is a bookid or a magazineid
            data = myDB.match('SELECT * from books where BookID="%s"' % message)
            if not data:
                data = myDB.match('SELECT * from magazines where BookID="%s"' % message)
        dictionary = dict(zip(data.keys(), data))

        try:
            # call the custom notifier script here, passing dictionary deconstructed as strings
            if lazylibrarian.CONFIG['CUSTOM_SCRIPT']:
                params = [lazylibrarian.CONFIG['CUSTOM_SCRIPT']]
                for item in dictionary:
                    params.append(item)
                    if hasattr(dictionary[item], 'encode'):
                        params.append(dictionary[item].encode('utf-8'))
                    else:
                        params.append(str(dictionary[item]))

                res = subprocess.check_output(params, stderr=subprocess.STDOUT)
                if len(res):
                    return res
                return True
            else:
                logger.warn('Error sending custom notification: Check config')
                return False

        except Exception as e:
            logger.warn('Error sending custom notification: %s' % e)
            return False

        #
        # Public functions
        #

    def notify_snatch(self, title):
        if lazylibrarian.CONFIG['EMAIL_NOTIFY_ONSNATCH']:
            self._notify(message=title, event=notifyStrings[NOTIFY_SNATCH])

    def notify_download(self, title):
        if lazylibrarian.CONFIG['EMAIL_NOTIFY_ONDOWNLOAD']:
            self._notify(message=title, event=notifyStrings[NOTIFY_DOWNLOAD])

    def test_notify(self, title="Test"):
        return self._notify(message=title, event="Test", force=True)


notifier = CustomNotifier
