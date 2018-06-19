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

import time

try:
    import requests
except ImportError:
    import lib.requests as requests

import lazylibrarian
from lazylibrarian import logger
from lazylibrarian.formatter import check_int
from lazylibrarian.common import proxyList
# noinspection PyUnresolvedReferences
from lib.six.moves.urllib_parse import urlparse, urlunparse

# This is just a simple script to send torrents to transmission. The
# intention is to turn this into a class where we can check the state
# of the download, set the download dir, etc.
#
session_id = None
host_url = None


def addTorrent(link, directory=None, metainfo=None):
    method = 'torrent-add'
    if metainfo:
        arguments = {'metainfo': metainfo}
    else:
        arguments = {'filename': link}
    if not directory:
        directory = lazylibrarian.CONFIG['TRANSMISSION_DIR']
    if directory:
        arguments['download-dir'] = directory

    logger.debug('addTorrent args(%s)' % arguments)
    response, res = torrentAction(method, arguments)  # type: dict

    if not response:
        return False, res

    if response['result'] == 'success':
        if 'torrent-added' in response['arguments']:
            retid = response['arguments']['torrent-added']['id']
        elif 'torrent-duplicate' in response['arguments']:
            retid = response['arguments']['torrent-duplicate']['id']
        else:
            retid = False
        if retid:
            logger.debug("Torrent sent to Transmission successfully")
            return retid, ''

    res = 'Transmission returned status %s' % response['result']
    logger.debug(res)
    return False, res


def getTorrentFolder(torrentid):  # uses hashid
    method = 'torrent-get'
    arguments = {'ids': [torrentid], 'fields': ['name', 'percentDone']}
    retries = 3
    while retries:
        response, _ = torrentAction(method, arguments)  # type: dict
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
        response, _ = torrentAction(method, arguments)  # type: dict
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


def getTorrentFiles(torrentid):  # uses hashid
    method = 'torrent-get'
    arguments = {'ids': [torrentid], 'fields': ['id', 'files']}
    retries = 3
    while retries:
        response, _ = torrentAction(method, arguments)  # type: dict
        if response:
            if len(response['arguments']['torrents'][0]['files']):
                return response['arguments']['torrents'][0]['files']
        else:
            logger.debug('getTorrentFiles: No response from transmission')
            return ''

        retries -= 1
        if retries:
            time.sleep(5)

    return ''


def getTorrentProgress(torrentid):  # uses hashid
    method = 'torrent-get'
    arguments = {'ids': [torrentid], 'fields': ['id', 'percentDone', 'errorString']}
    retries = 3
    while retries:
        response, _ = torrentAction(method, arguments)  # type: dict
        if response:
            try:
                if len(response['arguments']['torrents'][0]):
                    err = response['arguments']['torrents'][0]['errorString']
                    res = response['arguments']['torrents'][0]['percentDone']
                    try:
                        res = int(float(res) * 100)
                        return res, err
                    except ValueError:
                        continue
            except IndexError:
                msg = '%s not found at transmission' % torrentid
                logger.debug(msg)
                return -1, msg
        else:
            msg = 'No response from transmission'
            logger.debug(msg)
            return 0, msg

        retries -= 1
        if retries:
            time.sleep(1)

    msg = '%s not found at transmission' % torrentid
    logger.debug(msg)
    return -1, msg


def setSeedRatio(torrentid, ratio):
    method = 'torrent-set'
    if ratio != 0:
        arguments = {'seedRatioLimit': ratio, 'seedRatioMode': 1, 'ids': [torrentid]}
    else:
        arguments = {'seedRatioMode': 2, 'ids': [torrentid]}

    response, _ = torrentAction(method, arguments)  # type: dict
    if not response:
        return False


def removeTorrent(torrentid, remove_data=False):

    method = 'torrent-get'
    arguments = {'ids': [torrentid], 'fields': ['isFinished', 'name']}

    response, _ = torrentAction(method, arguments)  # type: dict
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
            _, _ = torrentAction(method, arguments)
            return True
        else:
            logger.debug('%s has not finished seeding yet, torrent will not be removed' % name)
    except IndexError:
        # no torrents, already removed?
        return True
    except Exception as e:
        logger.warn('Unable to remove torrent %s, %s %s' % (torrentid, type(e).__name__, str(e)))
        return False

    return False


def checkLink():
    global session_id
    method = 'session-stats'
    arguments = {}
    session_id = None
    response, _ = torrentAction(method, arguments)  # type: dict
    if response:
        if response['result'] == 'success':
            # does transmission handle labels?
            return "Transmission login successful"
    return "Transmission login FAILED\nCheck debug log"


def torrentAction(method, arguments):
    global session_id, host_url

    username = lazylibrarian.CONFIG['TRANSMISSION_USER']
    password = lazylibrarian.CONFIG['TRANSMISSION_PASS']

    if host_url:
        if lazylibrarian.LOGLEVEL & lazylibrarian.log_dlcomms:
            logger.debug("Using existing host %s" % host_url)
    else:
        host = lazylibrarian.CONFIG['TRANSMISSION_HOST']
        port = check_int(lazylibrarian.CONFIG['TRANSMISSION_PORT'], 0)

        if not host or not port:
            res = 'Invalid transmission host or port, check your config'
            logger.error(res)
            return False, res

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

        host_url = urlunparse(parts)

    auth = (username, password) if username and password else None
    proxies = proxyList()
    timeout = check_int(lazylibrarian.CONFIG['HTTP_TIMEOUT'], 30)
    # Retrieve session id
    if session_id:
        if lazylibrarian.LOGLEVEL & lazylibrarian.log_dlcomms:
            logger.debug('Using existing session_id %s' % session_id)
    else:
        response = requests.get(host_url, auth=auth, proxies=proxies, timeout=timeout)
        if response is None:
            res = "Error getting Transmission session ID"
            logger.error(res)
            return False, res

        # Parse response
        if response.status_code == 401:
            if auth:
                res = "Username and/or password not accepted by Transmission"
            else:
                res = "Transmission authorization required"
            logger.error(res)
            return False, res
        elif response.status_code == 409:
            session_id = response.headers['x-transmission-session-id']

        if not session_id:
            res = "Expected a Session ID from Transmission, got %s" % response.status_code
            logger.error(res)
            return False, res

    # Prepare next request
    headers = {'x-transmission-session-id': session_id}
    data = {'method': method, 'arguments': arguments}
    try:
        response = requests.post(host_url, json=data, headers=headers, proxies=proxies,
                                 auth=auth, timeout=timeout)
        if response.status_code == 409:
            session_id = response.headers['x-transmission-session-id']
            logger.debug("Retrying with new session_id %s" % session_id)
            headers = {'x-transmission-session-id': session_id}
            response = requests.post(host_url, json=data, headers=headers, proxies=proxies,
                                     auth=auth, timeout=timeout)
        if not str(response.status_code).startswith('2'):
            res = "Expected a response from Transmission, got %s" % response.status_code
            logger.error(res)
            return False, res
        try:
            res = response.json()
        except ValueError:
            res = "Expected json, Transmission returned %s" % response.text
            logger.error(res)
            return False, res
        return res, ''

    except Exception as e:
        res = 'Transmission %s: %s' % (type(e).__name__, str(e))
        logger.error(res)
        return False, res
