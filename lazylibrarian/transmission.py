#  This file is part of LazyLibrarian.
#  LazyLibrarian is free software: you can redistribute it and/or modify
#  it under the terms of the GNU General Public License as published by
#  the Free Software Foundation, either version 3 of the License, or
#  (at your option) any later version.
#  LazyLibrarian is distributed in the hope that it will be useful,
#  but WITHOUT ANY WARRANTY; without even the implied warranty of
#  MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
#  GNU General Public License for more details.
#  You should have received a copy of the GNU General Public License
#  along with LazyLibrarian.  If not, see <http://www.gnu.org/licenses/>.


import json
import time

try:
    import requests
except ImportError:
    import lib.requests as requests

import lazylibrarian
from lazylibrarian import logger
from lazylibrarian.formatter import check_int
from lazylibrarian.common import proxyList
from lib.six.moves.urllib_parse import urlparse, urlunparse

# This is just a simple script to send torrents to transmission. The
# intention is to turn this into a class where we can check the state
# of the download, set the download dir, etc.
# TODO: Store the session id so we don't need to make 2 calls
#       Store torrent id so we can check up on it


def addTorrent(link, directory=None):
    method = 'torrent-add'
    if directory is None:
        directory = lazylibrarian.DIRECTORY('Download')
    arguments = {'filename': link, 'download-dir': directory}

    response = torrentAction(method, arguments)  # type: dict

    if not response:
        return False

    if response['result'] == 'success':
        if 'torrent-added' in response['arguments']:
            retid = response['arguments']['torrent-added']['id']
        elif 'torrent-duplicate' in response['arguments']:
            retid = response['arguments']['torrent-duplicate']['id']
        else:
            retid = False

        logger.debug("Torrent sent to Transmission successfully")
        return retid

    else:
        logger.debug('Transmission returned status %s' % response['result'])
        return False


def getTorrentFolder(torrentid):  # uses hashid
    method = 'torrent-get'
    arguments = {'ids': [torrentid], 'fields': ['name', 'percentDone']}
    retries = 3
    while retries:
        response = torrentAction(method, arguments)  # type: dict
        if response and len(response['arguments']['torrents']):
            percentdone = response['arguments']['torrents'][0]['percentDone']
            if percentdone:
                return response['arguments']['torrents'][0]['name']
        else:
            logger.debug('getTorrentFolder: No response from transmission')
            return ''

        retries -= 1
        if retries:
            time.sleep(5)

    return ''


def getTorrentFolderbyID(torrentid):  # uses transmission id
    method = 'torrent-get'
    arguments = {'fields': ['name', 'percentDone', 'id']}
    retries = 3
    while retries:
        response = torrentAction(method, arguments)  # type: dict
        if response and len(response['arguments']['torrents']):
            tor = 0
            while tor < len(response['arguments']['torrents']):
                percentdone = response['arguments']['torrents'][tor]['percentDone']
                if percentdone:
                    torid = response['arguments']['torrents'][tor]['id']
                    if str(torid) == str(torrentid):
                        return response['arguments']['torrents'][tor]['name']
                tor += 1
        else:
            logger.debug('getTorrentFolder: No response from transmission')
            return ''

        retries -= 1
        if retries:
            time.sleep(5)

    return ''


def setSeedRatio(torrentid, ratio):
    method = 'torrent-set'
    if ratio != 0:
        arguments = {'seedRatioLimit': ratio, 'seedRatioMode': 1, 'ids': [torrentid]}
    else:
        arguments = {'seedRatioMode': 2, 'ids': [torrentid]}

    response = torrentAction(method, arguments)  # type: dict
    if not response:
        return False


def removeTorrent(torrentid, remove_data=False):

    method = 'torrent-get'
    arguments = {'ids': [torrentid], 'fields': ['isFinished', 'name']}

    response = torrentAction(method, arguments)  # type: dict
    if not response:
        return False

    try:
        finished = response['arguments']['torrents'][0]['isFinished']
        name = response['arguments']['torrents'][0]['name']

        if finished:
            logger.debug('%s has finished seeding, removing torrent and data' % name)
            method = 'torrent-remove'
            if remove_data:
                arguments = {'delete-local-data': True, 'ids': [torrentid]}
            else:
                arguments = {'ids': [torrentid]}
            _ = torrentAction(method, arguments)
            return True
        else:
            logger.debug('%s has not finished seeding yet, torrent will not be removed, \
                        will try again on next run' % name)
    except Exception as e:
        logger.debug('Unable to remove torrent %s, %s %s' % (torrentid, type(e).__name__, str(e)))
        return False

    return False


def checkLink():

    method = 'session-stats'
    arguments = {}

    response = torrentAction(method, arguments)  # type: dict
    if response:
        if response['result'] == 'success':
            # does transmission handle labels?
            return "Transmission login successful"
    return "Transmission login FAILED\nCheck debug log"


def torrentAction(method, arguments):

    host = lazylibrarian.CONFIG['TRANSMISSION_HOST']
    port = check_int(lazylibrarian.CONFIG['TRANSMISSION_PORT'], 0)

    if not host or not port:
        logger.error('Invalid transmission host or port, check your config')
        return False

    username = lazylibrarian.CONFIG['TRANSMISSION_USER']
    password = lazylibrarian.CONFIG['TRANSMISSION_PASS']

    if not host.startswith("http://") and not host.startswith("https://"):
        host = 'http://' + host

    if host.endswith('/'):
        host = host[:-1]

    # Fix the URL. We assume that the user does not point to the RPC endpoint,
    # so add it if it is missing.
    parts = list(urlparse(host))

    if parts[0] not in ("http", "https"):
        parts[0] = "http"

    if ':' not in parts[1]:
        parts[1] += ":%s" % port

    if not parts[2].endswith("/rpc"):
        parts[2] += "/transmission/rpc"

    host = urlunparse(parts)

    # Retrieve session id
    auth = (username, password) if username and password else None
    proxies = proxyList()
    timeout = check_int(lazylibrarian.CONFIG['HTTP_TIMEOUT'], 30)
    response = requests.get(host, auth=auth, proxies=proxies, timeout=timeout)

    if response is None:
        logger.error("Error getting Transmission session ID")
        return

    # Parse response
    session_id = ''
    if response.status_code == 401:
        if auth:
            logger.error("Username and/or password not accepted by "
                         "Transmission")
        else:
            logger.error("Transmission authorization required")
        return
    elif response.status_code == 409:
        session_id = response.headers['x-transmission-session-id']

    if not session_id:
        logger.error("Expected a Session ID from Transmission")
        return

    # Prepare next request
    headers = {'x-transmission-session-id': session_id}
    data = {'method': method, 'arguments': arguments}
    proxies = proxyList()
    timeout = check_int(lazylibrarian.CONFIG['HTTP_TIMEOUT'], 30)
    try:
        response = requests.post(host, data=json.dumps(data), headers=headers, proxies=proxies,
                                 auth=auth, timeout=timeout)
        response = response.json()
    except Exception as e:
        logger.debug('Transmission %s: %s' % (type(e).__name__, str(e)))
        response = ''

    if not response:
        logger.error("Error sending torrent to Transmission")
        return

    return response
