#!/usr/bin/python

import os
from time import sleep
import lazylibrarian
from lazylibrarian import logger
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


def addTorrent(torrent, hashID, directory=None):

    server = getServer()
    if server is False:
        return False
    logger.debug('rTorrent adding %s' % torrent)
    socket.setdefaulttimeout(10)  # set a timeout
    try:
        response = server.load(torrent)  # response isn't anything useful, always 0
        # need a short pause while rtorrent grabs the metadata
        sleep(5)
        label = lazylibrarian.RTORRENT_LABEL
        if label:
            server.d.set_custom1(hashID, label)
        if directory:
            server.d.set_directory(hashID, directory)
        server.d.start(hashID)
        # read mainview to see if we are there, as response tells us nothing
        mainview = server.download_list("", "main")
    except Exception as e:
        logger.error("rTorrent Error: %s" % str(e))
        socket.setdefaulttimeout(None)  # reset timeout if failed
        return False

    socket.setdefaulttimeout(None)  # reset timeout

    # For each torrent in the main view
    for torrent in mainview:
        if torrent == hashID.upper():  # we are there
            name = server.d.get_name(torrent)
            directory = server.d.get_directory(torrent)
            label = server.d.get_custom1(torrent)
            if label:
                logger.debug('rtorrent downloading %s to %s with label %s' % (name, directory, label))
            else:
                logger.debug('rtorrent downloading %s to %s' % (name, directory))
            return hashID
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
