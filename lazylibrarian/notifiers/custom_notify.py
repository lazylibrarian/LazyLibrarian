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

from subprocess import Popen, PIPE

import lazylibrarian
from lazylibrarian import logger, database
from lazylibrarian.common import notifyStrings, NOTIFY_SNATCH, NOTIFY_DOWNLOAD
from lazylibrarian.formatter import makeUnicode


class CustomNotifier:
    def __init__(self):
        pass

    @staticmethod
    def _notify(message, event, force=False):

        # suppress notifications if the notifier is disabled but the notify options are checked
        if not lazylibrarian.CONFIG['USE_CUSTOM'] and not force:
            return False

        logger.debug('Custom Event: %s' % event)
        logger.debug('Custom Message: %s' % message)
        myDB = database.DBConnection()
        if event == "Test":
            # grab the first entry in the book table and wanted table
            book = myDB.match('SELECT * from books')
            wanted = myDB.match('SELECT * from wanted')
        else:
            # message is a bookid followed by type (eBook/AudioBook)
            # or a magazine title followed by it's NZBUrl
            words = message.split()
            ident = words[-1]
            bookid = " ".join(words[:-1])
            book = myDB.match('SELECT * from books where BookID=?', (bookid,))
            if not book:
                book = myDB.match('SELECT * from magazines where Title=?', (bookid,))

            if event == 'Added to Library':
                wanted_status = 'Processed'
            else:
                wanted_status = 'Snatched'

            if ident in ['eBook', 'AudioBook']:
                wanted = myDB.match('SELECT * from wanted where BookID=? AND AuxInfo=? AND Status=?',
                                    (bookid, ident, wanted_status))
            else:
                wanted = myDB.match('SELECT * from wanted where BookID=? AND NZBUrl=? AND Status=?',
                                    (bookid, ident, wanted_status))

        if book:
            dictionary = dict(list(zip(list(book.keys()), book)))
        else:
            dictionary = {}

        dictionary['Event'] = event

        if wanted:
            wanted_dictionary = dict(list(zip(list(wanted.keys()), wanted)))
            for item in wanted_dictionary:
                if item in ['Status', 'BookID']:  # rename to avoid clash
                    dictionary['Wanted_' + item] = wanted_dictionary[item]
                else:
                    dictionary[item] = wanted_dictionary[item]
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

                try:
                    p = Popen(params, stdout=PIPE, stderr=PIPE)
                    res, err = p.communicate()
                    rc = p.returncode
                    res = makeUnicode(res)
                    err = makeUnicode(err)
                    if rc:
                        logger.error("Custom notifier returned %s: res[%s] err[%s]" % (rc, res, err))
                        return False
                    logger.debug(res)
                    return True
                except Exception as e:
                    logger.warn('Error sending command: %s' % e)
                    return False
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
        if lazylibrarian.CONFIG['CUSTOM_NOTIFY_ONSNATCH']:
            self._notify(message=title, event=notifyStrings[NOTIFY_SNATCH])

    def notify_download(self, title):
        if lazylibrarian.CONFIG['CUSTOM_NOTIFY_ONDOWNLOAD']:
            self._notify(message=title, event=notifyStrings[NOTIFY_DOWNLOAD])

    def test_notify(self, title="Test"):
        return self._notify(message=title, event="Test", force=True)

notifier = CustomNotifier
