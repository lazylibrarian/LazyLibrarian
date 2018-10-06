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


import json
import mimetypes
import os
import platform
import random
import string
import time

# noinspection PyUnresolvedReferences
from lib.six.moves import http_cookiejar
# noinspection PyUnresolvedReferences
from lib.six.moves.urllib_error import URLError
# noinspection PyUnresolvedReferences
from lib.six.moves.urllib_parse import urlencode
# noinspection PyUnresolvedReferences
from lib.six.moves.urllib_request import HTTPCookieProcessor, build_opener, Request

import lazylibrarian
from lazylibrarian import logger
from lazylibrarian.common import USER_AGENT
from lazylibrarian.formatter import check_int, getList, makeBytestr, makeUnicode


class qbittorrentclient(object):
    # TOKEN_REGEX = "<div id='token' style='display:none;'>([^<>]+)</div>"
    # UTSetting = namedtuple("UTSetting", ["name", "int", "str", "access"])

    def __init__(self):

        host = lazylibrarian.CONFIG['QBITTORRENT_HOST']
        port = check_int(lazylibrarian.CONFIG['QBITTORRENT_PORT'], 0)
        if not host or not port:
            logger.error('Invalid Qbittorrent host or port, check your config')

        if not host.startswith("http://") and not host.startswith("https://"):
            host = 'http://' + host

        if host.endswith('/'):
            host = host[:-1]

        if host.endswith('/gui'):
            host = host[:-4]

        host = "%s:%s" % (host, port)
        self.base_url = host
        self.username = lazylibrarian.CONFIG['QBITTORRENT_USER']
        self.password = lazylibrarian.CONFIG['QBITTORRENT_PASS']
        self.cookiejar = http_cookiejar.CookieJar()
        self.opener = self._make_opener()
        self._get_sid(self.base_url, self.username, self.password)
        self.api = self._api_version()

    def _make_opener(self):
        # create opener with cookie handler to carry QBitTorrent SID cookie
        cookie_handler = HTTPCookieProcessor(self.cookiejar)
        handlers = [cookie_handler]
        return build_opener(*handlers)

    def _api_version(self):
        # noinspection PyBroadException
        try:
            version = int(self._command('version/api'))
        except Exception as err:
            logger.warn('Error getting api version. qBittorrent %s: %s' % (type(err).__name__, str(err)))
            version = 1
        return version

    def _get_sid(self, base_url, username, password):
        # login so we can capture SID cookie
        login_data = makeBytestr(urlencode({'username': username, 'password': password}))
        try:
            _ = self.opener.open(base_url + '/login', login_data)
        except Exception as err:
            logger.error('Error getting SID. qBittorrent %s: %s' % (type(err).__name__, str(err)))
            logger.warn('Unable to log in to %s/login' % base_url)
            return
        for cookie in self.cookiejar:
            logger.debug('login cookie: ' + cookie.name + ', value: ' + cookie.value)
        return

    def _command(self, command, args=None, content_type=None, files=None):
        logger.debug('QBittorrent WebAPI Command: %s' % command)
        url = self.base_url + '/' + command
        data = None
        headers = dict()

        if files or content_type == 'multipart/form-data':
            data, headers = encode_multipart(args, files, '-------------------------acebdf13572468')
        else:
            if args:
                data = makeBytestr(urlencode(args))
            if content_type:
                headers['Content-Type'] = content_type

        request = Request(url, data, headers)

        if lazylibrarian.CONFIG['PROXY_HOST']:
            for item in getList(lazylibrarian.CONFIG['PROXY_TYPE']):
                request.set_proxy(lazylibrarian.CONFIG['PROXY_HOST'], item)
        request.add_header('User-Agent', USER_AGENT)

        try:
            response = self.opener.open(request)
            try:
                contentType = response.headers['content-type']
            except KeyError:
                contentType = ''

            resp = response.read()
            # some commands return json
            if contentType == 'application/json':
                if resp:
                    return json.loads(resp)
                return ''
            else:
                # some commands return plain text
                resp = makeUnicode(resp)
                logger.debug("QBitTorrent returned %s" % resp)
                if command == 'version/api':
                    return resp
                # some just return Ok. or Fails.
                if resp and resp != 'Ok.':
                    return False
            # some commands return nothing but response code (always 200)
            return True
        except URLError as err:
            logger.debug('Failed URL: %s' % url)
            logger.debug('QBitTorrent webUI raised the following error: %s' % err.reason)
            return False

    def _get_list(self, **args):
        # type: (dict) -> list
        return self._command('query/torrents', args)

    def _get_settings(self):
        value = self._command('query/preferences')
        logger.debug('get_settings() returned %d items' % len(value))
        return value

    def get_savepath(self, hashid):
        logger.debug('qb.get_savepath(%s)' % hashid)
        hashid = hashid.lower()
        torrentList = self._get_list()
        for torrent in list(torrentList):
            if torrent['hash'] and torrent['hash'].lower() == hashid:
                return torrent['save_path']
        return None

    def start(self, hashid):
        logger.debug('qb.start(%s)' % hashid)
        args = {'hash': hashid}
        return self._command('command/resume', args, 'application/x-www-form-urlencoded')

    def pause(self, hashid):
        logger.debug('qb.pause(%s)' % hashid)
        args = {'hash': hashid}
        return self._command('command/pause', args, 'application/x-www-form-urlencoded')

    def getfiles(self, hashid):
        logger.debug('qb.getfiles(%s)' % hashid)
        return self._command('query/propertiesFiles/' + hashid)

    def getprops(self, hashid):
        logger.debug('qb.getprops(%s)' % hashid)
        return self._command('query/propertiesGeneral/' + hashid)

    def setprio(self, hashid, priority):
        logger.debug('qb.setprio(%s,%d)' % (hashid, priority))
        args = {'hash': hashid, 'priority': priority}
        return self._command('command/setFilePrio', args, 'application/x-www-form-urlencoded')

    def remove(self, hashid, remove_data=False):
        logger.debug('qb.remove(%s,%s)' % (hashid, remove_data))
        args = {'hashes': hashid}
        if remove_data:
            command = 'command/deletePerm'
        else:
            command = 'command/delete'
        return self._command(command, args, 'application/x-www-form-urlencoded')


def getProgress(hashid):
    logger.debug('getProgress(%s)' % hashid)
    hashid = hashid.lower()
    qbclient = qbittorrentclient()
    if not len(qbclient.cookiejar):
        logger.debug("Failed to login to qBittorrent")
        return False
    # noinspection PyProtectedMember
    torrentList = qbclient._get_list()
    if torrentList:
        for torrent in torrentList:
            if torrent['hash'].lower() == hashid:
                if 'state' in torrent:
                    state = torrent['state']
                else:
                    state = ''
                if 'progress' in torrent:
                    try:
                        progress = int(100 * float(torrent['progress']))
                    except ValueError:
                        progress = 0
                else:
                    progress = 0
                return progress, state
    return -1, ''


def removeTorrent(hashid, remove_data=False):
    logger.debug('removeTorrent(%s,%s)' % (hashid, remove_data))
    hashid = hashid.lower()
    qbclient = qbittorrentclient()
    if not len(qbclient.cookiejar):
        logger.debug("Failed to login to qBittorrent")
        return False
    # noinspection PyProtectedMember
    torrentList = qbclient._get_list()
    if torrentList:
        for torrent in torrentList:
            if torrent['hash'].lower() == hashid:
                remove = True
                if torrent['state'] == 'uploading' or torrent['state'] == 'stalledUP':
                    if not lazylibrarian.CONFIG['SEED_WAIT']:
                        logger.debug('%s is seeding, removing torrent and data anyway' % torrent['name'])
                    else:
                        logger.info('%s has not finished seeding yet, torrent will not be removed' % torrent['name'])
                        remove = False
                if remove:
                    if remove_data:
                        logger.info('%s removing torrent and data' % torrent['name'])
                    else:
                        logger.info('%s removing torrent' % torrent['name'])
                    qbclient.remove(hashid, remove_data)
                    return True
    return False


def checkLink():
    """ Check we can talk to qbittorrent"""
    try:
        qbclient = qbittorrentclient()
        if len(qbclient.cookiejar):
            # qbittorrent creates a new label if needed
            # can't see how to get a list of known labels to check against
            return "qBittorrent login successful, api: %s" % qbclient.api
        return "qBittorrent login FAILED\nCheck debug log"
    except Exception as err:
        return "qBittorrent login FAILED: %s %s" % (type(err).__name__, str(err))


def addTorrent(link, hashid):
    logger.debug('addTorrent(%s)' % link)
    args = {}
    hashid = hashid.lower()
    qbclient = qbittorrentclient()
    if not len(qbclient.cookiejar):
        res = "Failed to login to qBittorrent"
        logger.debug(res)
        return False, res
    dl_dir = lazylibrarian.CONFIG['QBITTORRENT_DIR']
    if dl_dir:
        args['savepath'] = dl_dir

    if lazylibrarian.CONFIG['QBITTORRENT_LABEL']:
        if 6 < qbclient.api < 10:
            args['label'] = lazylibrarian.CONFIG['QBITTORRENT_LABEL']
        elif qbclient.api >= 10:
            args['category'] = lazylibrarian.CONFIG['QBITTORRENT_LABEL']
    logger.debug('addTorrent args(%s)' % args)
    args['urls'] = link

    # noinspection PyProtectedMember
    if qbclient._command('command/download', args, 'multipart/form-data'):
        return True, ''
    # sometimes returns "Fails." when it hasn't failed, so look if hashid was added correctly
    logger.debug("qBittorrent: addTorrent thinks it failed")
    time.sleep(2)
    # noinspection PyProtectedMember
    torrents = qbclient._get_list()
    if hashid in str(torrents).lower():
        logger.debug("qBittorrent: hashid found in torrent list, assume success")
        return True, ''
    res = "qBittorrent: hashid not found in torrent list, addTorrent failed"
    logger.debug(res)
    return False, res


def addFile(data, hashid, title):
    logger.debug('addFile(data)')
    hashid = hashid.lower()
    qbclient = qbittorrentclient()
    if not len(qbclient.cookiejar):
        res = "Failed to login to qBittorrent"
        logger.debug(res)
        return False, res
    files = {'torrents': {'filename': title, 'content': data}}
    # noinspection PyProtectedMember
    if qbclient._command('command/upload', files=files):
        return True, ''
    # sometimes returns "Fails." when it hasn't failed, so look if hashid was added correctly
    logger.debug("qBittorrent: addFile thinks it failed")
    time.sleep(2)
    # noinspection PyProtectedMember
    torrents = qbclient._get_list()
    if hashid in str(torrents).lower():
        logger.debug("qBittorrent: hashid found in torrent list, assume success")
        return True, ''
    res = "qBittorrent: hashid not found in torrent list, addFile failed"
    logger.debug(res)
    return False, res


def getName(hashid):
    logger.debug('getName(%s)' % hashid)
    hashid = hashid.lower()
    qbclient = qbittorrentclient()
    if not len(qbclient.cookiejar):
        logger.debug("Failed to login to qBittorrent")
        return ''
    RETRIES = 5
    torrents = []
    while RETRIES:
        # noinspection PyProtectedMember
        torrents = qbclient._get_list()
        if torrents:
            if hashid in str(torrents).lower():
                break
        time.sleep(2)
        RETRIES -= 1

    for tor in torrents:
        if tor['hash'].lower() == hashid:
            return tor['name']
    return ''


def getFiles(hashid):
    logger.debug('getFiles(%s)' % hashid)
    hashid = hashid.lower()
    qbclient = qbittorrentclient()
    if not len(qbclient.cookiejar):
        logger.debug("Failed to login to qBittorrent")
        return ''
    RETRIES = 5

    while RETRIES:
        # noinspection PyProtectedMember
        files = qbclient.getfiles(hashid)
        if files:
            return files
        time.sleep(2)
        RETRIES -= 1
    return ''


def getFolder(hashid):
    logger.debug('getFolder(%s)' % hashid)
    hashid = hashid.lower()
    qbclient = qbittorrentclient()
    if not len(qbclient.cookiejar):
        logger.debug("Failed to login to qBittorrent")
        return None

    # Get Active Directory from settings
    # noinspection PyProtectedMember
    settings = qbclient._get_settings()
    # noinspection PyTypeChecker
    active_dir = settings['temp_path']
    # completed_dir = settings['save_path']

    if not active_dir:
        logger.error(
            'Could not get "Keep incomplete torrents in:" directory from QBitTorrent settings, please ensure it is set')
        return None

    # Get Torrent Folder Name
    torrent_folder = qbclient.get_savepath(hashid)

    # If there's no folder yet then it's probably a magnet, try until folder is populated
    if torrent_folder == active_dir or not torrent_folder:
        tries = 1
        while (torrent_folder == active_dir or torrent_folder is None) and tries <= 10:
            tries += 1
            time.sleep(6)
            torrent_folder = qbclient.get_savepath(hashid)

    if torrent_folder == active_dir or not torrent_folder:
        torrent_folder = qbclient.get_savepath(hashid)
        return torrent_folder
    else:
        if 'windows' not in platform.system().lower():
            torrent_folder = torrent_folder.replace('\\', '/')
        return os.path.basename(os.path.normpath(torrent_folder))


_BOUNDARY_CHARS = string.digits + string.ascii_letters


def encode_multipart(fields, files, boundary=None):
    """Encode dict of form fields and dict of files as multipart/form-data.
    Return tuple of (body_string, headers_dict). Each value in files is a dict
    with required keys 'filename' and 'content', and optional 'mimetype' (if
    not specified, tries to guess mime type or uses 'application/octet-stream').
    """

    def escape_quote(s):
        s = makeUnicode(s)
        return s.replace('"', '\\"')

    if boundary is None:
        boundary = ''.join(random.choice(_BOUNDARY_CHARS) for _ in range(30))
    lines = []

    if fields:
        fields = dict((makeBytestr(k), makeBytestr(v)) for k, v in fields.items())
        for name, value in list(fields.items()):
            lines.extend((
                '--{0}'.format(boundary),
                'Content-Disposition: form-data; name="{0}"'.format(escape_quote(name)),
                '',
                makeUnicode(value),
            ))

    if files:
        for name, value in list(files.items()):
            filename = value['filename']
            if 'mimetype' in value:
                mimetype = value['mimetype']
            else:
                mimetype = mimetypes.guess_type(filename)[0] or 'application/octet-stream'
            lines.extend((
                '--{0}'.format(boundary),
                'Content-Disposition: form-data; name="{0}"; filename="{1}"'.format(
                    escape_quote(name), escape_quote(filename)),
                'Content-Type: {0}'.format(mimetype),
                '',
                value['content'],
            ))

    lines.extend((
        '--{0}--'.format(boundary),
        '',
    ))
    body = makeBytestr('\r\n'.join(lines))

    headers = {
        'Content-Type': 'multipart/form-data; boundary={0}'.format(boundary),
        'Content-Length': str(len(body)),
    }

    return body, headers
