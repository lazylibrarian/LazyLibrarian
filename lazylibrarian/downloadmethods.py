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

import gzip
import os
import re
import socket
import unicodedata
import urllib2
from StringIO import StringIO
from base64 import b16encode, b32decode
from hashlib import sha1

import lazylibrarian
from lazylibrarian import logger, database, nzbget, sabnzbd, classes, utorrent, transmission, qbittorrent, \
    deluge, rtorrent, synology, bencode
from lazylibrarian.cache import fetchURL
from lazylibrarian.common import setperm, USER_AGENT
from lazylibrarian.formatter import cleanName, unaccented_str
from lib.deluge_client import DelugeRPCClient
from magnet2torrent import magnet2torrent


def NZBDownloadMethod(bookid=None, nzbtitle=None, nzburl=None, library='eBook'):
    myDB = database.DBConnection()
    Source = ''
    downloadID = ''
    if lazylibrarian.CONFIG['NZB_DOWNLOADER_SABNZBD'] and lazylibrarian.CONFIG['SAB_HOST']:
        Source = "SABNZBD"
        downloadID = sabnzbd.SABnzbd(nzbtitle, nzburl, False)  # returns nzb_ids or False

    if lazylibrarian.CONFIG['NZB_DOWNLOADER_NZBGET'] and lazylibrarian.CONFIG['NZBGET_HOST']:
        Source = "NZBGET"
        # headers = {'User-Agent': USER_AGENT}
        # data = request.request_content(url=nzburl, headers=headers)
        data, success = fetchURL(nzburl)
        if not success:
            logger.debug('Failed to read nzb data for nzbget: %s' % data)
            downloadID = ''
        else:
            nzb = classes.NZBDataSearchResult()
            nzb.extraInfo.append(data)
            nzb.name = nzbtitle
            nzb.url = nzburl
            downloadID = nzbget.sendNZB(nzb)

    if lazylibrarian.CONFIG['NZB_DOWNLOADER_SYNOLOGY'] and lazylibrarian.CONFIG['USE_SYNOLOGY'] and \
            lazylibrarian.CONFIG['SYNOLOGY_HOST']:
        Source = "SYNOLOGY_NZB"
        downloadID = synology.addTorrent(nzburl)  # returns nzb_ids or False

    if lazylibrarian.CONFIG['NZB_DOWNLOADER_BLACKHOLE']:
        Source = "BLACKHOLE"
        nzbfile, success = fetchURL(nzburl)
        if not success:
            logger.warn('Error fetching nzb from url [%s]: %s' % (nzburl, nzbfile))
            nzbfile = ''

        if nzbfile:
            nzbname = str(nzbtitle) + '.nzb'
            nzbpath = os.path.join(lazylibrarian.CONFIG['NZB_BLACKHOLEDIR'], nzbname)
            try:
                with open(nzbpath, 'wb') as f:
                    f.write(nzbfile)
                logger.debug('NZB file saved to: ' + nzbpath)
                setperm(nzbpath)
                downloadID = nzbname

            except Exception as e:
                logger.error('%s not writable, NZB not saved. Error: %s' % (nzbpath, str(e)))
                downloadID = ''

    if not Source:
        logger.warn('No NZB download method is enabled, check config.')
        return False

    if downloadID:
        logger.debug('Nzbfile has been downloaded from ' + str(nzburl))
        if library == 'eBook':
            myDB.action('UPDATE books SET status="Snatched" WHERE BookID=?', (bookid,))
        elif library == 'AudioBook':
            myDB.action('UPDATE books SET audiostatus = "Snatched" WHERE BookID=?', (bookid,))
        myDB.action('UPDATE wanted SET status="Snatched", Source=?, DownloadID=? WHERE NZBurl=?',
                    (Source, downloadID, nzburl))
        return True
    else:
        logger.error(u'Failed to download nzb @ <a href="%s">%s</a>' % (nzburl, Source))
        myDB.action('UPDATE wanted SET status="Failed" WHERE NZBurl=?', (nzburl,))
        return False


def DirectDownloadMethod(bookid=None, tor_title=None, tor_url=None, bookname=None, library='eBook'):
    myDB = database.DBConnection()
    downloadID = False
    Source = "DIRECT"
    full_url = tor_url  # keep the url as stored in "wanted" table
    logger.debug("Starting Direct Download for [%s]" % bookname)
    request = urllib2.Request(ur'%s' % tor_url)
    if lazylibrarian.CONFIG['PROXY_HOST']:
        request.set_proxy(lazylibrarian.CONFIG['PROXY_HOST'], lazylibrarian.CONFIG['PROXY_TYPE'])
    request.add_header('Accept-encoding', 'gzip')
    request.add_header('User-Agent', USER_AGENT)

    try:
        response = urllib2.urlopen(request, timeout=90)
        if response.info().get('Content-Encoding') == 'gzip':
            buf = StringIO(response.read())
            f = gzip.GzipFile(fileobj=buf)
            fdata = f.read()
        else:
            try:
                fdata = response.read()
            except Exception as e:
                logger.warn('Error reading response from url: %s, %s' % (tor_url, str(e)))
                return False

        bookname = '.'.join(bookname.rsplit(' ', 1))  # last word is the extension
        logger.debug("File download got %s bytes for %s/%s" % (len(fdata), tor_title, bookname))
        destdir = os.path.join(lazylibrarian.DIRECTORY('Download'), tor_title)
        try:
            os.makedirs(destdir)
            setperm(destdir)
        except OSError as e:
            if not os.path.isdir(destdir):
                logger.debug("Error creating directory %s, %s" % (destdir, e.strerror))

        destfile = os.path.join(destdir, bookname)
        try:
            with open(destfile, 'wb') as bookfile:
                bookfile.write(fdata)
            setperm(destfile)
            downloadID = True
        except Exception as e:
            logger.debug("Error writing book to %s, %s" % (destfile, str(e)))

    except socket.timeout:
        logger.warn('Timeout fetching file from url: %s' % tor_url)
        return False
    except urllib2.URLError as e:
        logger.warn('Error fetching file from url: %s, %s' % (tor_url, e.reason))
        return False

    if downloadID:
        logger.debug(u'File %s has been downloaded from %s' % (tor_title, tor_url))
        if library == 'eBook':
            myDB.action('UPDATE books SET status="Snatched" WHERE BookID=?', (bookid,))
        elif library == 'AudioBook':
            myDB.action('UPDATE books SET audiostatus="Snatched" WHERE BookID=?', (bookid,))
        myDB.action('UPDATE wanted SET status="Snatched", Source=?, DownloadID=? WHERE NZBurl=?',
                    (Source, downloadID, full_url))
        return True
    else:
        logger.error(u'Failed to download file @ <a href="%s">%s</a>' % (full_url, tor_url))
        myDB.action('UPDATE wanted SET status="Failed" WHERE NZBurl=?', (full_url,))
        return False


def TORDownloadMethod(bookid=None, tor_title=None, tor_url=None, library='eBook'):
    myDB = database.DBConnection()
    downloadID = False
    Source = ''
    full_url = tor_url  # keep the url as stored in "wanted" table
    if tor_url and tor_url.startswith('magnet'):
        torrent = tor_url  # allow magnet link to write to blackhole and hash to utorrent/rtorrent
    else:
        # h = HTMLParser()
        # tor_url = h.unescape(tor_url)
        # HTMLParser is probably overkill, we only seem to get &amp;
        #
        tor_url = tor_url.replace('&amp;', '&')

        if '&file=' in tor_url:
            # torznab results need to be re-encoded
            # had a problem with torznab utf-8 encoded strings not matching
            # our utf-8 strings because of long/short form differences
            url, value = tor_url.split('&file=', 1)
            if isinstance(value, str):
                value = value.decode('utf-8')  # make unicode
            value = unicodedata.normalize('NFC', value)  # normalize to short form
            value = value.encode('unicode-escape')  # then escape the result
            value = value.replace(' ', '%20')  # and encode any spaces
            tor_url = url + '&file=' + value

        # strip url back to the .torrent as some sites add parameters
        if not tor_url.endswith('.torrent'):
            if '.torrent' in tor_url:
                tor_url = tor_url.split('.torrent')[0] + '.torrent'

        request = urllib2.Request(ur'%s' % tor_url)
        if lazylibrarian.CONFIG['PROXY_HOST']:
            request.set_proxy(lazylibrarian.CONFIG['PROXY_HOST'], lazylibrarian.CONFIG['PROXY_TYPE'])
        request.add_header('Accept-encoding', 'gzip')
        request.add_header('User-Agent', USER_AGENT)

        try:
            response = urllib2.urlopen(request, timeout=90)
            if response.info().get('Content-Encoding') == 'gzip':
                buf = StringIO(response.read())
                f = gzip.GzipFile(fileobj=buf)
                torrent = f.read()
            else:
                torrent = response.read()

        except socket.timeout:
            logger.warn('Timeout fetching torrent from url: %s' % tor_url)
            return False
        except urllib2.URLError as e:
            logger.warn('Error fetching torrent from url: %s, %s' % (tor_url, e.reason))
            return False
        except ValueError as e:
            logger.warn('Error, invalid url: [%s] %s' % (full_url, str(e)))
            return False

    if lazylibrarian.CONFIG['TOR_DOWNLOADER_BLACKHOLE']:
        Source = "BLACKHOLE"
        logger.debug("Sending %s to blackhole" % tor_title)
        tor_name = cleanName(tor_title).replace(' ', '_')
        if tor_url and tor_url.startswith('magnet'):
            if lazylibrarian.CONFIG['TOR_CONVERT_MAGNET']:
                hashid = CalcTorrentHash(tor_url)
                tor_name = 'meta-' + hashid + '.torrent'
                tor_path = os.path.join(lazylibrarian.CONFIG['TORRENT_DIR'], tor_name)
                result = magnet2torrent(tor_url, tor_path)
                if result is not False:
                    logger.debug('Magnet file saved as: %s' % tor_path)
                    downloadID = Source
            else:
                tor_name += '.magnet'
                tor_path = os.path.join(lazylibrarian.CONFIG['TORRENT_DIR'], tor_name)
                try:
                    with open(tor_path, 'wb') as torrent_file:
                        torrent_file.write(torrent)
                    logger.debug('Magnet file saved: %s' % tor_path)
                    setperm(tor_path)
                    downloadID = Source
                except Exception as e:
                    logger.debug("Failed to write magnet to file %s, %s" % (tor_path, str(e)))
                    return False
        else:
            tor_name += '.torrent'
            tor_path = os.path.join(lazylibrarian.CONFIG['TORRENT_DIR'], tor_name)
            msg = ''
            try:
                msg = 'Opening '
                with open(tor_path, 'wb') as torrent_file:
                    msg += 'Writing '
                    torrent_file.write(torrent)
                msg += 'SettingPerm '
                setperm(tor_path)
                msg += 'Saved'
                logger.debug('Torrent file saved: %s' % tor_name)
                downloadID = Source
            except Exception as e:
                logger.debug("Failed to write torrent to file: %s" % (str(e)))
                logger.debug("Progress: %s" % msg)
                logger.debug("Filename [%s]" % (repr(tor_path)))
                #logger.debug("Failed to write torrent to file %s, %s" % (repr(tor_path), str(e)))
                return False

    if lazylibrarian.CONFIG['TOR_DOWNLOADER_UTORRENT'] and lazylibrarian.CONFIG['UTORRENT_HOST']:
        logger.debug("Sending %s to Utorrent" % tor_title)
        Source = "UTORRENT"
        hashid = CalcTorrentHash(torrent)
        downloadID = utorrent.addTorrent(tor_url, hashid)  # returns hash or False
        if downloadID:
            tor_title = utorrent.nameTorrent(downloadID)

    if lazylibrarian.CONFIG['TOR_DOWNLOADER_RTORRENT'] and lazylibrarian.CONFIG['RTORRENT_HOST']:
        logger.debug("Sending %s to rTorrent" % tor_title)
        Source = "RTORRENT"
        hashid = CalcTorrentHash(torrent)
        downloadID = rtorrent.addTorrent(tor_url, hashid)  # returns hash or False
        if downloadID:
            tor_title = rtorrent.getName(downloadID)

    if lazylibrarian.CONFIG['TOR_DOWNLOADER_QBITTORRENT'] and lazylibrarian.CONFIG['QBITTORRENT_HOST']:
        logger.debug("Sending %s to qbittorrent" % tor_title)
        Source = "QBITTORRENT"
        hashid = CalcTorrentHash(torrent)
        status = qbittorrent.addTorrent(tor_url)  # returns hash or False
        if status:
            downloadID = hashid
            tor_title = qbittorrent.getName(hashid)

    if lazylibrarian.CONFIG['TOR_DOWNLOADER_TRANSMISSION'] and lazylibrarian.CONFIG['TRANSMISSION_HOST']:
        logger.debug("Sending %s to Transmission" % tor_title)
        Source = "TRANSMISSION"
        downloadID = transmission.addTorrent(tor_url)  # returns id or False
        if downloadID:
            # transmission returns it's own int, but we store hashid instead
            downloadID = CalcTorrentHash(torrent)
            tor_title = transmission.getTorrentFolder(downloadID)

    if lazylibrarian.CONFIG['TOR_DOWNLOADER_SYNOLOGY'] and lazylibrarian.CONFIG['USE_SYNOLOGY'] and \
            lazylibrarian.CONFIG['SYNOLOGY_HOST']:
        logger.debug("Sending %s to Synology" % tor_title)
        Source = "SYNOLOGY_TOR"
        downloadID = synology.addTorrent(tor_url)  # returns id or False
        if downloadID:
            tor_title = synology.getName(downloadID)

    if lazylibrarian.CONFIG['TOR_DOWNLOADER_DELUGE'] and lazylibrarian.CONFIG['DELUGE_HOST']:
        logger.debug("Sending %s to Deluge" % tor_title)
        if not lazylibrarian.CONFIG['DELUGE_USER']:
            # no username, talk to the webui
            Source = "DELUGEWEBUI"
            downloadID = deluge.addTorrent(tor_url)  # returns hash or False
            if downloadID:
                tor_title = deluge.getTorrentFolder(downloadID)
        else:
            # have username, talk to the daemon
            Source = "DELUGERPC"
            client = DelugeRPCClient(lazylibrarian.CONFIG['DELUGE_HOST'],
                                     int(lazylibrarian.CONFIG['DELUGE_PORT']),
                                     lazylibrarian.CONFIG['DELUGE_USER'],
                                     lazylibrarian.CONFIG['DELUGE_PASS'])
            try:
                client.connect()
                args = {"name": tor_title}
                if tor_url.startswith('magnet'):
                    downloadID = client.call('core.add_torrent_magnet', tor_url, args)
                else:
                    downloadID = client.call('core.add_torrent_url', tor_url, args)
                if downloadID:
                    if lazylibrarian.CONFIG['DELUGE_LABEL']:
                        _ = client.call('label.set_torrent', downloadID, lazylibrarian.CONFIG['DELUGE_LABEL'])
                    result = client.call('core.get_torrent_status', downloadID, {})
                    # for item in result:
                    #    logger.debug ('Deluge RPC result %s: %s' % (item, result[item]))
                    if 'name' in result:
                        tor_title = result['name']

            except Exception as e:
                logger.debug('DelugeRPC failed %s' % str(e))
                return False

    if not Source:
        logger.warn('No torrent download method is enabled, check config.')
        return False

    if downloadID:
        if library == 'eBook':
            myDB.action('UPDATE books SET status="Snatched" WHERE BookID=?', (bookid,))
        elif library == 'AudioBook':
            myDB.action('UPDATE books SET audiostatus="Snatched" WHERE BookID=?', (bookid,))
        myDB.action('UPDATE wanted SET status="Snatched", Source=?, DownloadID=? WHERE NZBurl=?',
                    (Source, downloadID, full_url))
        if tor_title:
            if downloadID.upper() in tor_title.upper():
                logger.warn('%s: name contains hash, probably unresolved magnet' % Source)
            else:
                tor_title = unaccented_str(tor_title)
                logger.debug('%s setting torrent name to [%s]' % (Source, tor_title))
                myDB.action('UPDATE wanted SET NZBtitle=? WHERE NZBurl=?', (tor_title, full_url))
        return True
    else:
        logger.error(u'Failed to download torrent from %s, %s' % (Source, tor_url))
        myDB.action('UPDATE wanted SET status="Failed" WHERE NZBurl=?', (full_url,))
        return False


def CalcTorrentHash(torrent):
    if torrent and torrent.startswith('magnet'):
        hashid = re.findall('urn:btih:([\w]{32,40})', torrent)[0]
        if len(hashid) == 32:
            hashid = b16encode(b32decode(hashid)).lower()
    else:
        info = bencode.decode(torrent)["info"]
        hashid = sha1(bencode.encode(info)).hexdigest()
    logger.debug('Torrent Hash: ' + hashid)
    return hashid
