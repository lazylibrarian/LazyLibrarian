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


import os
import re
import unicodedata
from base64 import b16encode, b32decode, b64encode
from hashlib import sha1

try:
    import requests
except ImportError:
    import lib.requests as requests

import lazylibrarian
from lazylibrarian import logger, database, nzbget, sabnzbd, classes, utorrent, transmission, qbittorrent, \
    deluge, rtorrent, synology
from lazylibrarian.cache import fetchURL
from lazylibrarian.common import setperm, USER_AGENT, proxyList, mymakedirs
from lazylibrarian.formatter import cleanName, unaccented_str, getList, makeUnicode
from lazylibrarian.postprocess import delete_task
from lib.deluge_client import DelugeRPCClient
from .magnet2torrent import magnet2torrent
from lib.bencode import encode, decode
from lib.six import text_type


def NZBDownloadMethod(bookid=None, nzbtitle=None, nzburl=None, library='eBook'):
    myDB = database.DBConnection()
    Source = ''
    downloadID = ''
    if lazylibrarian.CONFIG['NZB_DOWNLOADER_SABNZBD'] and lazylibrarian.CONFIG['SAB_HOST']:
        Source = "SABNZBD"
        downloadID = sabnzbd.SABnzbd(nzbtitle, nzburl, False)  # returns nzb_ids or False

    if lazylibrarian.CONFIG['NZB_DOWNLOADER_NZBGET'] and lazylibrarian.CONFIG['NZBGET_HOST']:
        Source = "NZBGET"
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
                    if isinstance(nzbfile, text_type):
                        nzbfile = nzbfile.encode('iso-8859-1')
                    f.write(nzbfile)
                logger.debug('NZB file saved to: ' + nzbpath)
                setperm(nzbpath)
                downloadID = nzbname

            except Exception as e:
                logger.error('%s not writable, NZB not saved. %s: %s' % (nzbpath, type(e).__name__, str(e)))
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
        logger.error('Failed to download nzb @ <a href="%s">%s</a>' % (nzburl, Source))
        myDB.action('UPDATE wanted SET status="Failed" WHERE NZBurl=?', (nzburl,))
        return False


def DirectDownloadMethod(bookid=None, tor_title=None, tor_url=None, bookname=None, library='eBook'):
    myDB = database.DBConnection()
    downloadID = False
    Source = "DIRECT"

    logger.debug("Starting Direct Download for [%s]" % bookname)
    proxies = proxyList()
    headers = {'Accept-encoding': 'gzip', 'User-Agent': USER_AGENT}
    try:
        r = requests.get(tor_url, headers=headers, timeout=90, proxies=proxies)
    except requests.exceptions.Timeout:
        logger.warn('Timeout fetching file from url: %s' % tor_url)
        return False
    except Exception as e:
        if hasattr(e, 'reason'):
            logger.warn('%s fetching file from url: %s, %s' % (type(e).__name__, tor_url, e.reason))
        else:
            logger.warn('%s fetching file from url: %s, %s' % (type(e).__name__, tor_url, str(e)))
        return False

    if not str(r.status_code).startswith('2'):
        logger.debug("Got a %s response for %s" % (r.status_code, tor_url))
    elif len(r.content) < 1000:
        logger.debug("Only got %s bytes for %s/%s, rejecting" % (len(r.content), tor_title, bookname))
    else:
        bookname = '.'.join(bookname.rsplit(' ', 1))  # last word is the extension
        logger.debug("File download got %s bytes for %s/%s" % (len(r.content), tor_title, bookname))
        destdir = os.path.join(lazylibrarian.DIRECTORY('Download'), tor_title)
        if not os.path.isdir(destdir):
            _ = mymakedirs(destdir)

        destfile = os.path.join(destdir, bookname)
        try:
            with open(destfile, 'wb') as bookfile:
                bookfile.write(r.content)
            setperm(destfile)
            downloadID = True
        except Exception as e:
            logger.error("%s writing book to %s, %s" % (type(e).__name__, destfile, e))

    if downloadID:
        logger.debug('File %s has been downloaded from %s' % (tor_title, tor_url))
        if library == 'eBook':
            myDB.action('UPDATE books SET status="Snatched" WHERE BookID=?', (bookid,))
        elif library == 'AudioBook':
            myDB.action('UPDATE books SET audiostatus="Snatched" WHERE BookID=?', (bookid,))
        myDB.action('UPDATE wanted SET status="Snatched", Source=?, DownloadID=? WHERE NZBurl=?',
                    (Source, downloadID, tor_url))
        return True
    else:
        logger.error('Failed to download file @ <a href="%s">%s</a>' % (tor_url, tor_url))
        myDB.action('UPDATE wanted SET status="Failed" WHERE NZBurl=?', (tor_url,))
        return False


def TORDownloadMethod(bookid=None, tor_title=None, tor_url=None, library='eBook'):
    myDB = database.DBConnection()
    downloadID = False
    Source = ''
    full_url = tor_url  # keep the url as stored in "wanted" table
    if tor_url and tor_url.startswith('magnet:?'):
        torrent = tor_url  # allow magnet link to write to blackhole and hash to utorrent/rtorrent
    elif 'magnet:?' in tor_url:
        # discard any other parameters and just use the magnet link
        torrent = 'magnet:?' + tor_url.split('magnet:?')[1]
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
            value = makeUnicode(value)  # ensure unicode
            value = unicodedata.normalize('NFC', value)  # normalize to short form
            value = value.encode('unicode-escape')  # then escape the result
            value = makeUnicode(value)  # ensure unicode
            value = value.replace(' ', '%20')  # and encode any spaces
            tor_url = url + '&file=' + value

        # strip url back to the .torrent as some sites add extra parameters
        if not tor_url.endswith('.torrent'):
            if '.torrent' in tor_url:
                tor_url = tor_url.split('.torrent')[0] + '.torrent'

        headers = {'Accept-encoding': 'gzip', 'User-Agent': USER_AGENT}
        proxies = proxyList()
        try:
            r = requests.get(tor_url, headers=headers, timeout=90, proxies=proxies)
            torrent = r.content
        except requests.exceptions.Timeout:
            logger.warn('Timeout fetching file from url: %s' % tor_url)
            return False
        except Exception as e:
            # some jackett providers redirect internally using http 301 to a magnet link
            # which requests can't handle, so throws an exception
            if "magnet:?" in str(e):
                torrent = 'magnet:?' + str(e).split('magnet:?')[1]. strip("'")
            else:
                if hasattr(e, 'reason'):
                    logger.warn('%s fetching file from url: %s, %s' % (type(e).__name__, tor_url, e.reason))
                else:
                    logger.warn('%s fetching file from url: %s, %s' % (type(e).__name__, tor_url, str(e)))
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
                msg = ''
                try:
                    msg = 'Opening '
                    with open(tor_path, 'wb') as torrent_file:
                        msg += 'Writing '
                        if isinstance(torrent, text_type):
                            torrent = torrent.encode('iso-8859-1')
                        torrent_file.write(torrent)
                    msg += 'SettingPerm '
                    setperm(tor_path)
                    msg += 'Saved '
                    logger.debug('Magnet file saved: %s' % tor_path)
                    downloadID = Source
                except Exception as e:
                    logger.warn("Failed to write magnet to file: %s %s" % (type(e).__name__, str(e)))
                    logger.debug("Progress: %s" % msg)
                    logger.debug("Filename [%s]" % (repr(tor_path)))
                    return False
        else:
            tor_name += '.torrent'
            tor_path = os.path.join(lazylibrarian.CONFIG['TORRENT_DIR'], tor_name)
            msg = ''
            try:
                msg = 'Opening '
                with open(tor_path, 'wb') as torrent_file:
                    msg += 'Writing '
                    if isinstance(torrent, text_type):
                        torrent = torrent.encode('iso-8859-1')
                    torrent_file.write(torrent)
                msg += 'SettingPerm '
                setperm(tor_path)
                msg += 'Saved '
                logger.debug('Torrent file saved: %s' % tor_name)
                downloadID = Source
            except Exception as e:
                logger.warn("Failed to write torrent to file: %s %s" % (type(e).__name__, str(e)))
                logger.debug("Progress: %s" % msg)
                logger.debug("Filename [%s]" % (repr(tor_path)))
                return False

    hashid = CalcTorrentHash(torrent)
    if lazylibrarian.CONFIG['TOR_DOWNLOADER_UTORRENT'] and lazylibrarian.CONFIG['UTORRENT_HOST']:
        logger.debug("Sending %s to Utorrent" % tor_title)
        Source = "UTORRENT"
        downloadID = utorrent.addTorrent(tor_url, hashid)  # returns hash or False
        if downloadID:
            tor_title = utorrent.nameTorrent(downloadID)

    if lazylibrarian.CONFIG['TOR_DOWNLOADER_RTORRENT'] and lazylibrarian.CONFIG['RTORRENT_HOST']:
        logger.debug("Sending %s to rTorrent" % tor_title)
        Source = "RTORRENT"
        downloadID = rtorrent.addTorrent(tor_url, hashid)  # returns hash or False
        if downloadID:
            tor_title = rtorrent.getName(downloadID)

    if lazylibrarian.CONFIG['TOR_DOWNLOADER_QBITTORRENT'] and lazylibrarian.CONFIG['QBITTORRENT_HOST']:
        logger.debug("Sending %s to qbittorrent" % tor_title)
        Source = "QBITTORRENT"
        if torrent.startswith(b'magnet'):
            status = qbittorrent.addTorrent(torrent, hashid)
        else:
            status = qbittorrent.addTorrent(tor_url, hashid)  # returns True or False
        if status:
            downloadID = hashid
            tor_title = qbittorrent.getName(hashid)

    if lazylibrarian.CONFIG['TOR_DOWNLOADER_TRANSMISSION'] and lazylibrarian.CONFIG['TRANSMISSION_HOST']:
        logger.debug("Sending %s to Transmission" % tor_title)
        if lazylibrarian.LOGLEVEL > 2:
            logger.debug("TORRENT %s [%s] [%s]" % (len(torrent), torrent[:20], torrent[-20:]))
        Source = "TRANSMISSION"
        if torrent.startswith(b'magnet'):
            downloadID = transmission.addTorrent(torrent)  # returns id or False
        elif torrent:
            downloadID = transmission.addTorrent(None, metainfo=b64encode(torrent))
        else:
            downloadID = transmission.addTorrent(tor_url)  # returns id or False
        if downloadID:
            # transmission returns it's own int, but we store hashid instead
            downloadID = hashid
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
            if torrent.startswith(b'magnet'):
                downloadID = deluge.addTorrent(torrent)
            elif torrent:
                downloadID = deluge.addTorrent(tor_title, data=b64encode(torrent))
            else:
                downloadID = deluge.addTorrent(tor_url)  # can be link or magnet, returns hash or False
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
                elif torrent.startswith(b'magnet'):
                    downloadID = client.call('core.add_torrent_magnet', torrent, args)
                elif torrent:
                    downloadID = client.call('core.add_torrent_file', tor_title, b64encode(torrent), args)
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
                logger.error('DelugeRPC failed %s %s' % (type(e).__name__, str(e)))
                return False

    if not Source:
        logger.warn('No torrent download method is enabled, check config.')
        return False

    if downloadID:
        if tor_title:
            if downloadID.upper() in tor_title.upper():
                logger.warn('%s: name contains hash, probably unresolved magnet' % Source)
            else:
                tor_title = unaccented_str(tor_title)
                # need to check against reject words list again as the name may have changed
                # library = magazine eBook AudioBook to determine which reject list
                # but we can't easily do the per-magazine rejects
                if library == 'magazine':
                    reject_list = getList(lazylibrarian.CONFIG['REJECT_MAGS'])
                elif library == 'eBook':
                    reject_list = getList(lazylibrarian.CONFIG['REJECT_WORDS'])
                elif library == 'AudioBook':
                    reject_list = getList(lazylibrarian.CONFIG['REJECT_AUDIO'])
                else:
                    logger.debug("Invalid library [%s] in TORDownloadMethod" % library)
                    reject_list = []

                rejected = False
                lower_title = tor_title.lower()
                for word in reject_list:
                    if word in lower_title:
                        rejected = True
                        logger.debug("Rejecting torrent name %s, contains %s" % (tor_title, word))
                        break
                if rejected:
                    myDB.action('UPDATE wanted SET status="Failed" WHERE NZBurl=?', (full_url,))
                    delete_task(Source, downloadID, True)
                    return False
                else:
                    logger.debug('%s setting torrent name to [%s]' % (Source, tor_title))
                    myDB.action('UPDATE wanted SET NZBtitle=? WHERE NZBurl=?', (tor_title, full_url))

        if library == 'eBook':
            myDB.action('UPDATE books SET status="Snatched" WHERE BookID=?', (bookid,))
        elif library == 'AudioBook':
            myDB.action('UPDATE books SET audiostatus="Snatched" WHERE BookID=?', (bookid,))
        myDB.action('UPDATE wanted SET status="Snatched", Source=?, DownloadID=? WHERE NZBurl=?',
                    (Source, downloadID, full_url))
        return True

    logger.error('Failed to download torrent from %s, %s' % (Source, tor_url))
    myDB.action('UPDATE wanted SET status="Failed" WHERE NZBurl=?', (full_url,))
    return False


def CalcTorrentHash(torrent):
    # torrent could be a unicode magnet link or a bytes object torrent file contents
    if makeUnicode(torrent[:6]) == 'magnet':
        # torrent = makeUnicode(torrent)
        hashid = re.findall('urn:btih:([\w]{32,40})', torrent)[0]
        if len(hashid) == 32:
            hashid = b16encode(b32decode(hashid)).lower()
    else:
        # noinspection PyTypeChecker
        info = dict(decode(torrent))["info"]  # python3 decode returns OrderedDict
        hashid = sha1(encode(info)).hexdigest()
    logger.debug('Torrent Hash: ' + hashid)
    return hashid
