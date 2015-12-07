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
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with Sick Beard.  If not, see <http://www.gnu.org/licenses/>.

#import os.path
#import operator
import platform
import re

USER_AGENT = 'LazyLibrarian' + ' (' + platform.system() + ' ' + platform.release() + ')'

# Notification Types
NOTIFY_SNATCH = 1
NOTIFY_DOWNLOAD = 2

notifyStrings = {}
notifyStrings[NOTIFY_SNATCH] = "Started Download"
notifyStrings[NOTIFY_DOWNLOAD] = "Download Finished"

import lazylibrarian
import unicodedata
import string

def remove_accents(str_or_unicode):
    try:
        nfkd_form = unicodedata.normalize('NFKD', str_or_unicode)
    except TypeError:
        nfkd_form = unicodedata.normalize('NFKD', str_or_unicode.decode(lazylibrarian.SYS_ENCODING, 'replace'))
    return u''.join([c for c in nfkd_form if not unicodedata.combining(c)])
    # returns unicode


def removeDisallowedFilenameChars(filename):
    validFilenameChars = u"-_.() %s%s" % (string.ascii_letters, string.digits)
    try:
        cleanedFilename = unicodedata.normalize('NFKD', filename).encode('ASCII', 'ignore')
    except TypeError:
        cleanedFilename = unicodedata.normalize('NFKD', filename.decode('utf-8')).encode('ASCII', 'ignore')
    #return u''.join(c for c in cleanedFilename if c in validFilenameChars) <<-- does not work on python3, complains c is int
    # if you coerce c to str it fails to match, returns empty string.   re.sub works on python2 and 3 
    return u''+re.sub(validFilenameChars,"", str(cleanedFilename))
    # returns unicode

