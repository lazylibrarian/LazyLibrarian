#  This file is part of Lazylibrarian.
#  Lazylibrarian is free software':'you can redistribute it and/or modify
#  it under the terms of the GNU General Public License as published by
#  the Free Software Foundation, either version 3 of the License, or
#  (at your option) any later version.
#  Lazylibrarian is distributed in the hope that it will be useful,
#  but WITHOUT ANY WARRANTY; without even the implied warranty of
#  MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
#  GNU General Public License for more details.
#  You should have received a copy of the GNU General Public License
#  along with Lazylibrarian.  If not, see <http://www.gnu.org/licenses/>.


import socket
from time import sleep

import lazylibrarian
from lazylibrarian import logger
# noinspection PyUnresolvedReferences
from lib.six.moves import xmlrpc_client


def getServer():
    host = lazylibrarian.CONFIG['RTORRENT_HOST']
    if not host:
        logger.error("rtorrent error: No host found, check your config")
        return False

    if not host.startswith("http://") and not host.startswith("https://"):
        host = 'http://' + host
    if host.endswith('/'):
        host = host[:-1]

    if lazylibrarian.CONFIG['RTORRENT_USER']:
        user = lazylibrarian.CONFIG['RTORRENT_USER']
        password = lazylibrarian.CONFIG['RTORRENT_PASS']
        parts = host.split('://')
        host = parts[0] + '://' + user + ':' + password + '@' + parts[1]

    try:
        socket.setdefaulttimeout(20)  # so we don't freeze if server is not there
        server = xmlrpc_client.ServerProxy(host)
        result = server.system.client_version()
        socket.setdefaulttimeout(None)  # reset timeout
        logger.debug("rTorrent client version = %s" % result)
    except Exception as e:
        socket.setdefaulttimeout(None)  # reset timeout if failed
        logger.error("xmlrpc_client error: %s" % repr(e))
        return False
    if result:
        return server
    else:
        logger.warn('No response from rTorrent server')
        return False


def addTorrent(tor_url, hashID, data=None):
    server = getServer()
    if server is False:
        return False, 'rTorrent unable to connect to server'
    try:
        if data:
            logger.debug('Sending rTorrent content [%s...]' % str(data)[:40])
            _ = server.load_raw(xmlrpc_client.Binary(data))
        else:
            logger.debug('Sending rTorrent url [%s...]' % str(tor_url)[:40])
            _ = server.load(tor_url)  # response isn't anything useful, always 0
        # need a short pause while rtorrent loads it
        RETRIES = 5
        while RETRIES:
            mainview = server.download_list("", "main")
            for tor in mainview:
                if tor.upper() == hashID.upper():
                    break
            sleep(1)
            RETRIES -= 1

        label = lazylibrarian.CONFIG['RTORRENT_LABEL']
        if label:
            server.d.set_custom1(hashID, label)

        directory = lazylibrarian.CONFIG['RTORRENT_DIR']
        if directory:
            server.d.set_directory(hashID, directory)

        server.d.start(hashID)

    except Exception as e:
        res = "rTorrent Error: %s: %s" % (type(e).__name__, str(e))
        logger.error(res)
        return False, res

    # wait a while for download to start, that's when rtorrent fills in the name
    name = getName(hashID)
    if name:
        directory = server.d.get_directory(hashID)
        label = server.d.get_custom1(hashID)
        if label:
            logger.debug('rTorrent downloading %s to %s with label %s' % (name, directory, label))
        else:
            logger.debug('rTorrent downloading %s to %s' % (name, directory))
        return hashID, ''
    return False, 'rTorrent hashid not found'


def getProgress(hashID):
    server = getServer()
    if server is False:
        return 0, 'error'
    mainview = server.download_list("", "main")
    for tor in mainview:
        if tor.upper() == hashID.upper():
            if server.d.complete(tor):
                return 100, 'finished'
            return int((server.d.bytes_done(tor) * 100) / server.d.size_bytes(tor)), 'OK'
    return -1, ''


def getFiles(hashID):
    server = getServer()
    if server is False:
        return []

    mainview = server.download_list("", "main")
    for tor in mainview:
        if tor.upper() == hashID.upper():
            size_files = server.d.size_files(tor)
            cnt = 0
            files = []
            while cnt < size_files:
                target = "%s:f%d" % (tor, cnt)
                path = server.f.path(target)
                size = server.f.size_bytes(target)
                files.append({"path": path, "size": size})
                cnt += 1
            return files
    return []


def getName(hashID):
    server = getServer()
    if server is False:
        return False

    mainview = server.download_list("", "main")
    for tor in mainview:
        if tor.upper() == hashID.upper():
            RETRIES = 5
            name = ''
            while RETRIES:
                name = server.d.get_name(tor)
                if tor.upper() not in name:
                    break
                sleep(5)
                RETRIES -= 1
            return name
    return False  # not found


# noinspection PyUnusedLocal
def removeTorrent(hashID, remove_data=False):
    server = getServer()
    if server is False:
        return False

    mainview = server.download_list("", "main")
    for tor in mainview:
        if tor.upper() == hashID.upper():
            return server.d.erase(tor)
    return False  # not found


def checkLink():
    server = getServer()
    if server is False:
        return "rTorrent login FAILED\nCheck debug log"
    return "rTorrent login successful"
