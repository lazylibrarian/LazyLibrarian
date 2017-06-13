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
from lazylibrarian import logger
from lazylibrarian.common import notifyStrings, NOTIFY_SNATCH, NOTIFY_DOWNLOAD
from lazylibrarian.formatter import check_int
import cherrypy
from httplib import HTTPSConnection
from urllib import urlencode

class ProwlNotifier:
    def __init__(self):
        pass

    @staticmethod
    def _notify(message, event, force=False):

        # suppress notifications if the notifier is disabled but the notify options are checked
        if not lazylibrarian.CONFIG['USE_PROWL'] and not force:
            return False

        http_handler = HTTPSConnection("api.prowlapp.com")
        
        data = {    'event'       : event,
                    'description' : message.encode("utf-8"),
                    'application' : 'LazyLibrarian',
                    'apikey'      : lazylibrarian.CONFIG['PROWL_APIKEY'],
                    'priority'    : lazylibrarian.CONFIG['PROWL_PRIORITY']
        }
        logger.debug('Prowl notification: %s' % event)
        logger.debug('Prowl text: %s' % description)

        try:
            http_handler.request("POST",
                                "/publicapi/add",
                                headers = {'Content-type': "application/x-www-form-urlencoded"},
                                body = urlencode(data))
        response = http_handler.getresponse()
        request_status = response.status
        
        if request_status == 200:
                logger.info(module + ' Prowl notifications sent.')
                return True
        elif request_status == 401:
                logger.info(module + ' Prowl auth failed: %s' % response.reason)
                return False
        else:
                logger.info(module + ' Prowl notification failed.')
                return False

        except Exception as e:
            logger.warn('Error sending to Prowl: %s' % e)
            return False

            #
            # Public functions
            #

    def notify_snatch(self, title):
        if lazylibrarian.CONFIG['PROWL_NOTIFY_ONSNATCH']:
            self._notify(message=title, event=notifyStrings[NOTIFY_SNATCH])

    def notify_download(self, title):
        if lazylibrarian.CONFIG['PROWL_NOTIFY_ONDOWNLOAD']:
            self._notify(message=title, event=notifyStrings[NOTIFY_DOWNLOAD])

    def test_notify(self, title='Test'):
        message = "This is a test notification from LazyLibrarian"
        return self._notify(message=message, event=title, force=True)


notifier = ProwlNotifier
