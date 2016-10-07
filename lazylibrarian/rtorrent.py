#!/usr/bin/python

import os
from time import sleep
import lazylibrarian
from lazylibrarian import logger
from magnet2torrent import magnet2torrent
import lib.xmlrpclib as xmlrpclib
import socket


def getServer():
    host = lazylibrarian.RTORRENT_HOST
    if not host:
        logger.debug("rtorrent error: No host found")
        return False
    if not host.startswith('http'):
        host = 'http://' + host
    if host.endswith('/'):
        host = host[:-1]

    if lazylibrarian.RTORRENT_USER:
        user = lazylibrarian.RTORRENT_USER
        password = lazylibrarian.RTORRENT_PASS
        parts = host.split('://')
        host = parts[0] + '://' + user + ':' + password + '@' + parts[1]
    try:
        server = xmlrpclib.ServerProxy(host)
    except Exception as e:
        logger.debug("xmlrpclib error: %s" % str(e))
        return False
    return server


def addTorrent(tor_url, hashID):

    server = getServer()
    if server is False:
        return False

    socket.setdefaulttimeout(10)  # set a timeout

    directory = lazylibrarian.RTORRENT_DIR

    if tor_url.startswith('magnet') and directory:
        # can't send magnets to rtorrent with a directory - not working correctly
        # convert magnet to torrent instead
        tor_name = 'meta-' + hashID + '.torrent'
        tor_file = os.path.join(lazylibrarian.TORRENT_DIR, tor_name)
        torrent = magnet2torrent(tor_url, tor_file)
        if torrent is False:
            return False
        tor_url = torrent
    try:
        response = server.load(tor_url)  # response isn't anything useful, always 0
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

        label = lazylibrarian.RTORRENT_LABEL
        if label:
            server.d.set_custom1(hashID, label)

        if directory:
            server.d.set_directory(hashID, directory)

        mainview = server.download_list("", "main")
    except Exception as e:
        logger.error("rTorrent Error: %s" % str(e))
        socket.setdefaulttimeout(None)  # reset timeout if failed
        return False

    socket.setdefaulttimeout(None)  # reset timeout

    # For each torrent in the main view
    for tor in mainview:
        if tor.upper() == hashID.upper():  # we are there
            name = server.d.get_name(tor)
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
            return server.d.get_name(tor)
    return False  # not found


def checkLink():
    msg = ""
    server = getServer()
    if server is not False:
        try:
            socket.setdefaulttimeout(5)  # set the timeout to 5 seconds
            result = server.system.listMethods()
            msg = "rTorrent login successful"
        except Exception as e:
            logger.debug("rTorrent connection: %s" % str(e))
    socket.setdefaulttimeout(None)  # set the default back
    if msg == "":
        msg = "rTorrent login FAILED\nCheck debug log"
    return msg
