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


import os
import socket
import xmlrpclib
from time import sleep

import lazylibrarian
from lazylibrarian import logger
from magnet2torrent import magnet2torrent


def getServer():
    host = lazylibrarian.CONFIG['RTORRENT_HOST']
    if not host:
        logger.debug("rtorrent error: No host found")
        return False
    if not host.startswith('http'):
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
        server = xmlrpclib.ServerProxy(host)
        result = server.system.client_version()
        socket.setdefaulttimeout(None)  # reset timeout
        logger.debug("rTorrent client version = %s" % result)
    except Exception as e:
        socket.setdefaulttimeout(None)  # reset timeout if failed
        logger.debug("xmlrpclib error: %s" % repr(e))
        return False
    if result:
        return server
    else:
        logger.warn('No response from rTorrent server')
        return False


def addTorrent(tor_url, hashID):
    server = getServer()
    if server is False:
        return False

    directory = lazylibrarian.CONFIG['RTORRENT_DIR']

    if tor_url.startswith('magnet') and directory:
        # can't send magnets to rtorrent with a directory - not working correctly
        # convert magnet to torrent instead
        tor_name = 'meta-' + hashID + '.torrent'
        tor_file = os.path.join(lazylibrarian.CONFIG['TORRENT_DIR'], tor_name)
        torrent = magnet2torrent(tor_url, tor_file)
        if torrent is False:
            return False
        tor_url = torrent

    # socket.setdefaulttimeout(10)  # shouldn't need timeout again as we already talked to server

    try:
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

        server.d.start(hashID)

        label = lazylibrarian.CONFIG['RTORRENT_LABEL']
        if label:
            server.d.set_custom1(hashID, label)

        if directory:
            server.d.set_directory(hashID, directory)

        mainview = server.download_list("", "main")
        # socket.setdefaulttimeout(None)  # reset timeout

    except Exception as e:
        # socket.setdefaulttimeout(None)  # reset timeout if failed
        logger.error("rTorrent Error: %s" % str(e))
        return False

    # For each torrent in the main view
    for tor in mainview:
        if tor.upper() == hashID.upper():  # this is us
            # wait a while for download to start, that's when rtorrent fills in the name
            RETRIES = 5
            name = ''
            while RETRIES:
                name = server.d.get_name(tor)
                if tor.upper() not in name:
                    break
                sleep(5)
                RETRIES -= 1

            directory = server.d.get_directory(tor)
            label = server.d.get_custom1(tor)
            if label:
                logger.debug('rtorrent downloading %s to %s with label %s' % (name, directory, label))
            else:
                logger.debug('rtorrent downloading %s to %s' % (name, directory))
            return hashID
    return False  # not found


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
