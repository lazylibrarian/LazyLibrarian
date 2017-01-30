#  This file is part of Lazylibrarian.
#
#  Lazylibrarian is free software':'you can redistribute it and/or modify
#  it under the terms of the GNU General Public License as published by
#  the Free Software Foundation, either version 3 of the License, or
#  (at your option) any later version.
#
#  Lazylibrarian is distributed in the hope that it will be useful,
#  but WITHOUT ANY WARRANTY; without even the implied warranty of
#  MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
#  GNU General Public License for more details.
#
#  You should have received a copy of the GNU General Public License
#  along with Lazylibrarian.  If not, see <http://www.gnu.org/licenses/>.

import json
import socket
import ssl
import urllib
import urllib2

import lazylibrarian
from lazylibrarian import logger


def checkLink():
    # connection test, check host/port
    auth = SABnzbd(nzburl='auth')
    if not auth:
        return "Unable to talk to SABnzbd, check HOST/PORT"
    # check apikey is valid
    cats = SABnzbd(nzburl='get_cats')
    if not cats:
        return "Unable to talk to SABnzbd, check APIKEY"
    # check category exists
    if lazylibrarian.SAB_CAT:
        if not cats.has_key('categories') or not len(cats['categories']):
            return "SABnzbd seems to have no categories set"
        if lazylibrarian.SAB_CAT not in cats['categories']:
            return "SABnzbd: Unknown category [%s]\nValid categories:\n%s" % (
                    lazylibrarian.SAB_CAT, str(cats['categories']))
    return "SABnzbd connection successful"


def SABnzbd(title=None, nzburl=None, remove_data=False):

    if nzburl == 'delete' and title == 'unknown':
        logger.debug('Delete function unavailable in this version of sabnzbd, no nzo_ids')
        return False

    hostname = lazylibrarian.SAB_HOST
    if hostname.endswith('/'):
        hostname = hostname[:-1]
    if not hostname.startswith("http"):
        hostname = 'http://' + hostname

    HOST = "%s:%i" % (hostname, lazylibrarian.SAB_PORT)

    if lazylibrarian.SAB_SUBDIR:
        HOST = HOST + "/" + lazylibrarian.SAB_SUBDIR

    params = {}
    if nzburl == 'auth' or nzburl == 'get_cats':
        # connection test, check auth mode or get_cats
        params['mode'] = nzburl
        params['output'] = 'json'
        if lazylibrarian.SAB_API:
            params['apikey'] = lazylibrarian.SAB_API
        title = 'Test ' + nzburl
    elif nzburl == 'delete':
        # only deletes tasks if still in the queue, ie NOT completed tasks
        params['mode'] = 'queue'
        params['output'] = 'json'
        params['name'] = nzburl
        params['value'] = title
        if lazylibrarian.SAB_USER:
            params['ma_username'] = lazylibrarian.SAB_USER
        if lazylibrarian.SAB_PASS:
            params['ma_password'] = lazylibrarian.SAB_PASS
        if lazylibrarian.SAB_API:
            params['apikey'] = lazylibrarian.SAB_API
        if remove_data:
            params['del_files'] = 1
        title = 'Delete ' + title
    else:
        params['mode'] = 'addurl'
        params['output'] = 'json'
        if nzburl:
            params['name'] = nzburl
        if title:
            params['nzbname'] = title
        if lazylibrarian.SAB_USER:
            params['ma_username'] = lazylibrarian.SAB_USER
        if lazylibrarian.SAB_PASS:
            params['ma_password'] = lazylibrarian.SAB_PASS
        if lazylibrarian.SAB_API:
            params['apikey'] = lazylibrarian.SAB_API
        if lazylibrarian.SAB_CAT:
            params['cat'] = lazylibrarian.SAB_CAT
        if lazylibrarian.USENET_RETENTION:
            params["maxage"] = lazylibrarian.USENET_RETENTION

# FUTURE-CODE
#    if lazylibrarian.SAB_PRIO:
#        params["priority"] = lazylibrarian.SAB_PRIO
#    if lazylibrarian.SAB_PP:
#        params["script"] = lazylibrarian.SAB_SCRIPT

    URL = HOST + "/api?" + urllib.urlencode(params)

    # to debug because of api
    logger.debug(u'Request url for <a href="%s">SABnzbd</a>' % URL)

    try:
        request = urllib2.urlopen(URL, timeout=30)
    except socket.error as e:
        logger.error(u"Timeout connecting to SAB with URL: %s : %s" % (URL, str(e)))
        return False
    except (EOFError, IOError, urllib2.URLError) as e:
        if hasattr(e, 'reason'):
            errmsg = e.reason
        elif hasattr(e, 'strerror'):
            errmsg = e.strerror
        else:
            errmsg = str(e)

        logger.error(u"Unable to connect to SAB with URL: %s, %s" % (URL, errmsg))
        return False

    except (urllib2.HTTPError, ssl.SSLError) as e:
        logger.error(u"Invalid SAB host, check your config. Current host: %s : %s" % (HOST, str(e)))
        return False

    result = json.loads(request.read())

    if not result:
        logger.error("SABnzbd didn't return any json")
        return False

    logger.debug("Result text from SAB: " + str(result))
    if title and (title.startswith('Test') or title.startswith('Delete')):
        return result
    elif result['status'] is True:
        logger.info(title + " sent to SAB successfully.")
        # sab versions earlier than 0.8.0 don't return nzo_ids
        if 'nzo_ids' in result:
            if result['nzo_ids']:  # check its not empty
                return result['nzo_ids'][0]
        return 'unknown'
    elif result['status'] is False:
        logger.error("SAB returned Error: %s" % result['error'])
        return False
    else:
        logger.error("Unknown error: " + str(result))
        return False
