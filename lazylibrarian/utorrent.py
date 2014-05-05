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
#coding=utf8
import urllib
import urllib2
import urlparse
import cookielib
import json
import re
import os
import time
import lib.bencode
import base64
import lazylibrarian


from lazylibrarian import logger, request

class utorrentclient(object):
    TOKEN_REGEX = "<div id='token' style='display:none;'>([^<>]+)</div>"

    def __init__(self, base_url = '', # lazylibrarian.UTORRENT_HOST, 
                       username = '', #lazylibrarian.UTORRENT_USER,
                       password = '',): #lazylibrarian.UTORRENT_PASS):
                       
        host = lazylibrarian.UTORRENT_HOST
        if not host.startswith('http'):
            host = 'http://' + host

        if host.endswith('/'):
            host = host[:-1]

        if host.endswith('/gui'):
            host = host[:-4]

        self.base_url = host
        self.username = lazylibrarian.UTORRENT_USER
        self.password = lazylibrarian.UTORRENT_PASS
        self.opener = self._make_opener('uTorrent', base_url, username, password)
        self.token = self._get_token()
        #TODO refresh token, when necessary

    def _make_opener(self, realm, base_url, username, password):
        """uTorrent API need HTTP Basic Auth and cookie support for token verify."""

        auth_handler = urllib2.HTTPBasicAuthHandler()
        auth_handler.add_password(realm=realm,uri=base_url,user=username,passwd=password)
        opener = urllib2.build_opener(auth_handler)
        urllib2.install_opener(opener)

        cookie_jar = cookielib.CookieJar()
        cookie_handler = urllib2.HTTPCookieProcessor(cookie_jar)

        handlers = [auth_handler, cookie_handler]
        opener = urllib2.build_opener(*handlers)
        return opener

    def _get_token(self):
        auth = (self.username, self.password) if self.username and self.password else None
        response = request.request_response(self.base_url + '/gui/token.html')
        match = re.search(UTorrentClient.TOKEN_REGEX, response.read())
        return match.group(1)

    def list(self, **kwargs):
        params = [('list', '1')]
        params += kwargs.items()
        return self._action(params)

    def add_url(self, url):
        #can recieve magnet or normal .torrent link
        params = [('action', 'add-url'), ('s', url)]
        return self._action(params)

    def start(self, *hashes):
        params = [('action', 'start'), ]
        for hash in hashes:
            params.append(('hash', hash))
        return self._action(params)

    def stop(self, *hashes):
        params = [('action', 'stop'), ]
        for hash in hashes:
            params.append(('hash', hash))
        return self._action(params)

    def pause(self, *hashes):
        params = [('action', 'pause'), ]
        for hash in hashes:
            params.append(('hash', hash))
        return self._action(params)

    def forcestart(self, *hashes):
        params = [('action', 'forcestart'), ]
        for hash in hashes:
            params.append(('hash', hash))
        return self._action(params)

    def getfiles(self, hash):
        params = [('action', 'getfiles'), ('hash', hash)]
        return self._action(params)

    def getprops(self, hash):
        params = [('action', 'getprops'), ('hash', hash)]
        return self._action(params)

    def setprops(self, hash, **kvpairs):
        params = [('action', 'setprops'), ('hash', hash)]
        for k, v in kvpairs.iteritems():
            params.append(("s", k))
            params.append(("v", v))

        return self._action(params)

    def setprio(self, hash, priority, *files):
        params = [('action', 'setprio'), ('hash', hash), ('p', str(priority))]
        for file_index in files:
            params.append(('f', str(file_index)))

        return self._action(params)

    def _action(self, params, body=None, content_type=None):
        url = self.base_url + '/gui/' + '?token=' + self.token + '&' + urllib.urlencode(params)
        request = urllib2.Request(url)

        if body:
            request.add_data(body)
            request.add_header('Content-length', len(body))
        if content_type:
            request.add_header('Content-type', content_type)

        try:
            response = self.opener.open(request)
            return response.code, json.loads(response.read())
        except urllib2.HTTPError, e:
            raise

def addTorrent(link):
    label = lazylibrarian.UTORRENT_LABEL
    token = ''
    if link.startswith('magnet'):
        hash = re.findall('urn:btih:([\w]{32,40})', link)[0]
        if len(tor_hash) == 32:
            hash = b16encode(b32decode(tor_hash)).lower()
    #else:
    #    info = bdecode(link.content)["info"]
    #    hash = sha1(bencode(info)).hexdigest()
    
    uTorrentClient = utorrentclient()
    uTorrentClient.add_url(link)
    #utorrentclient.setprops(hash,'label',label) #labels our torrent with label
    return True