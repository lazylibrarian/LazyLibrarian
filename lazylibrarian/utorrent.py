#  This file is part of LazyLibrarin.
#
#  LazyLibrarian is free software: you can redistribute it and/or modify
#  it under the terms of the GNU General Public License as published by
#  the Free Software Foundation, either version 3 of the License, or
#  (at your option) any later version.
#
#  LazyLibrarian is distributed in the hope that it will be useful,
#  but WITHOUT ANY WARRANTY; without even the implied warranty of
#  MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
#  GNU General Public License for more details.
#
#  You should have received a copy of the GNU General Public License
#  along with LazyLibrarian.  If not, see <http://www.gnu.org/licenses/>.

import cookielib
import json
import re
import urllib
import urllib2
import urlparse

import lazylibrarian
from lazylibrarian import logger
from lazylibrarian.common import USER_AGENT
from lazylibrarian.formatter import check_int


class utorrentclient(object):
    TOKEN_REGEX = "<div id='token' style='display:none;'>([^<>]+)</div>"

    # noinspection PyUnusedLocal,PyUnusedLocal,PyUnusedLocal
    def __init__(self, base_url='',  # lazylibrarian.CONFIG['UTORRENT_HOST'],
                 username='',  # lazylibrarian.CONFIG['UTORRENT_USER'],
                 password='',):  # lazylibrarian.CONFIG['UTORRENT_PASS']):

        host = lazylibrarian.CONFIG['UTORRENT_HOST']
        port = check_int(lazylibrarian.CONFIG['UTORRENT_PORT'], 0)
        if not host or not port:
            logger.error('Invalid Utorrent host or port, check your config')

        if not host.startswith('http'):
            host = 'http://' + host

        if host.endswith('/'):
            host = host[:-1]

        if host.endswith('/gui'):
            host = host[:-4]

        host = "%s:%s" % (host, port)
        self.base_url = host
        self.username = lazylibrarian.CONFIG['UTORRENT_USER']
        self.password = lazylibrarian.CONFIG['UTORRENT_PASS']
        self.opener = self._make_opener('uTorrent', self.base_url, self.username, self.password)
        self.token = self._get_token()
        # TODO refresh token, when necessary

    @staticmethod
    def _make_opener(realm, base_url, username, password):
        """uTorrent API need HTTP Basic Auth and cookie support for token verify."""
        auth = urllib2.HTTPBasicAuthHandler()
        auth.add_password(realm=realm, uri=base_url, user=username, passwd=password)
        opener = urllib2.build_opener(auth)
        urllib2.install_opener(opener)

        cookie_jar = cookielib.CookieJar()
        cookie_handler = urllib2.HTTPCookieProcessor(cookie_jar)

        handlers = [auth, cookie_handler]
        opener = urllib2.build_opener(*handlers)
        return opener

    def _get_token(self):
        url = urlparse.urljoin(self.base_url, 'gui/token.html')
        try:
            response = self.opener.open(url)
        except Exception as err:
            logger.debug('URL: %s' % url)
            logger.debug('Error getting Token. uTorrent responded with: %s' % str(err))
            return None
        match = re.search(utorrentclient.TOKEN_REGEX, response.read())
        return match.group(1)

    def list(self, **kwargs):
        params = [('list', '1')]
        params += kwargs.items()
        return self._action(params)

    def add_url(self, url):
        # can recieve magnet or normal .torrent link
        params = [('action', 'add-url'), ('s', url)]
        return self._action(params)

    def start(self, *hashes):
        params = [('action', 'start'), ]
        for hashid in hashes:
            params.append(('hash', hashid))
        return self._action(params)

    def stop(self, *hashes):
        params = [('action', 'stop'), ]
        for hashid in hashes:
            params.append(('hash', hashid))
        return self._action(params)

    def pause(self, *hashes):
        params = [('action', 'pause'), ]
        for hashid in hashes:
            params.append(('hash', hashid))
        return self._action(params)

    def forcestart(self, *hashes):
        params = [('action', 'forcestart'), ]
        for hashid in hashes:
            params.append(('hash', hashid))
        return self._action(params)

    def getfiles(self, hashid):
        params = [('action', 'getfiles'), ('hash', hashid)]
        return self._action(params)

    def getprops(self, hashid):
        params = [('action', 'getprops'), ('hash', hashid)]
        return self._action(params)

    def removedata(self, hashid):
        params = [('action', 'removedata'), ('hash', hashid)]
        return self._action(params)

    def remove(self, hashid):
        params = [('action', 'remove'), ('hash', hashid)]
        return self._action(params)

    def setprops(self, hashid, s, v):
        params = [('action', 'setprops'), ('hash', hashid), ("s", s), ("v", v)]
        return self._action(params)

    def setprio(self, hashid, priority, *files):
        params = [('action', 'setprio'), ('hash', hashid), ('p', str(priority))]
        for file_index in files:
            params.append(('f', str(file_index)))

        return self._action(params)

    def _action(self, params, body=None, content_type=None):
        url = self.base_url + '/gui/' + '?token=' + self.token + '&' + urllib.urlencode(params)
        request = urllib2.Request(url)
        if lazylibrarian.CONFIG['PROXY_HOST']:
            proxy_type = lazylibrarian.CONFIG['PROXY_TYPE']
            proxy_type = proxy_type.lower() + ':'
            if url.lower().startswith(proxy_type):
                request.set_proxy(lazylibrarian.CONFIG['PROXY_HOST'], lazylibrarian.CONFIG['PROXY_TYPE'])
        request.add_header('User-Agent', USER_AGENT)

        if body:
            request.add_data(body)
            request.add_header('Content-length', len(body))
        if content_type:
            request.add_header('Content-type', content_type)

        try:
            response = self.opener.open(request)
            return response.code, json.loads(response.read())
        except urllib2.HTTPError as err:
            logger.debug('URL: %s' % url)
            logger.debug('uTorrent webUI raised the following error: ' + str(err))


def checkLink():
    """ Check we can talk to utorrent"""
    try:
        client = utorrentclient()
        if client.token:
            # we would also like to check lazylibrarian.utorrent_label
            # but uTorrent only sends us a list of labels that have active torrents
            # so we can't tell if our label is known, or does it get created anyway?
            if lazylibrarian.CONFIG['UTORRENT_LABEL']:
                return "uTorrent login successful, label not checked"
            return "uTorrent login successful"
        return "uTorrent login FAILED\nCheck debug log"
    except Exception as err:
        return "uTorrent login FAILED: %s" % str(err)


def labelTorrent(hashid):
    label = lazylibrarian.CONFIG['UTORRENT_LABEL']
    uTorrentClient = utorrentclient()
    settinglabel = True
    while settinglabel:
        torrentList = uTorrentClient.list()
        for torrent in torrentList[1].get('torrents'):
            if torrent[0].lower() == hashid:
                uTorrentClient.setprops(hashid, 'label', label)
                return True


def dirTorrent(hashid):
    uTorrentClient = utorrentclient()
    torrentList = uTorrentClient.list()
    for torrent in torrentList[1].get('torrents'):
        if torrent[0].lower() == hashid:
            return torrent[26]
    return False


def nameTorrent(hashid):
    uTorrentClient = utorrentclient()
    torrentList = uTorrentClient.list()
    for torrent in torrentList[1].get('torrents'):
        if torrent[0].lower() == hashid:
            return torrent[2]
    return False


def removeTorrent(hashid, remove_data=False):
    uTorrentClient = utorrentclient()
    torrentList = uTorrentClient.list()
    for torrent in torrentList[1].get('torrents'):
        if torrent[0].lower() == hashid:
            if remove_data:
                uTorrentClient.removedata(hashid)
            else:
                uTorrentClient.remove(hashid)
            return True
    return False


def addTorrent(link, hashid):
    uTorrentClient = utorrentclient()
    uTorrentClient.add_url(link)
    labelTorrent(hashid)
    if dirTorrent(hashid):
        return hashid
    return False
