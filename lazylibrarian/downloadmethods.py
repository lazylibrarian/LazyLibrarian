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

try:
    import magic
except (ImportError, TypeError):
    try:
        import lib.magic as magic
    except (ImportError, TypeError):
        magic = None

import lazylibrarian
from lazylibrarian import logger, database, nzbget, sabnzbd, classes, utorrent, transmission, qbittorrent, \
    deluge, rtorrent, synology
from lazylibrarian.cache import fetchURL
from lazylibrarian.common import setperm, USER_AGENT, proxyList, mymakedirs
from lazylibrarian.formatter import cleanName, unaccented_str, getList, makeUnicode
from lazylibrarian.postprocess import delete_task
from lib.deluge_client import DelugeRPCClient
from .magnet2torrent import magnet2torrent
from lib.bencode import bencode, bdecode
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
        logger.error('Failed to send nzb to @ <a href="%s">%s</a>' % (nzburl, Source))
        dlresult = "Failed to send nzb to %s" % Source
        myDB.action('UPDATE wanted SET status="Failed",DLResult=? WHERE NZBurl=?', (dlresult, nzburl))
        return False


def DirectDownloadMethod(bookid=None, dl_title=None, dl_url=None, library='eBook'):
    myDB = database.DBConnection()
    downloadID = False
    Source = "DIRECT"

    logger.debug("Starting Direct Download for [%s]" % dl_title)
    proxies = proxyList()
    headers = {'Accept-encoding': 'gzip', 'User-Agent': USER_AGENT}
    try:
        r = requests.get(dl_url, headers=headers, timeout=90, proxies=proxies)
    except requests.exceptions.Timeout:
        logger.warn('Timeout fetching file from url: %s' % dl_url)
        return False
    except Exception as e:
        if hasattr(e, 'reason'):
            logger.warn('%s fetching file from url: %s, %s' % (type(e).__name__, dl_url, e.reason))
        else:
            logger.warn('%s fetching file from url: %s, %s' % (type(e).__name__, dl_url, str(e)))
        return False

    if not str(r.status_code).startswith('2'):
        logger.debug("Got a %s response for %s" % (r.status_code, dl_url))
    elif len(r.content) < 1000:
        logger.debug("Only got %s bytes for %s, rejecting" % (len(r.content), dl_title))
    else:
        extn = ''
        basename = ''
        if ' ' in dl_title:
            basename, extn = dl_title.rsplit(' ', 1)  # last word is often the extension - but not always...
        if extn and extn in getList(lazylibrarian.CONFIG['EBOOK_TYPE']):
            dl_title = '.'.join(dl_title.rsplit(' ', 1))
        elif magic:
            mtype = magic.from_buffer(r.content)
            if 'EPUB' in mtype:
                extn = 'epub'
            elif 'Mobipocket' in mtype:  # also true for azw and azw3, does it matter?
                extn = 'mobi'
            elif 'PDF' in mtype:
                extn = 'pdf'
            else:
                logger.debug("magic reports %s" % mtype)
            basename = dl_title
        else:
            logger.warn("Don't know the filetype for %s" % dl_title)
            basename = dl_title

        logger.debug("File download got %s bytes for %s" % (len(r.content), dl_title))
        destdir = os.path.join(lazylibrarian.DIRECTORY('Download'), basename)
        # destdir = os.path.join(lazylibrarian.DIRECTORY('Download'), '%s LL.(%s)' % (basename, bookid))
        if not os.path.isdir(destdir):
            _ = mymakedirs(destdir)

        try:
            hashid = dl_url.split("md5=")[1].split("&")[0]
        except IndexError:
            hashid = sha1(bencode(dl_url)).hexdigest()

        destfile = os.path.join(destdir, basename + '.' + extn)
        try:
            with open(destfile, 'wb') as bookfile:
                bookfile.write(r.content)
            setperm(destfile)
            downloadID = hashid
        except Exception as e:
            logger.error("%s writing book to %s, %s" % (type(e).__name__, destfile, e))

    if downloadID:
        logger.debug('File %s has been downloaded from %s' % (dl_title, dl_url))
        if library == 'eBook':
            myDB.action('UPDATE books SET status="Snatched" WHERE BookID=?', (bookid,))
        elif library == 'AudioBook':
            myDB.action('UPDATE books SET audiostatus="Snatched" WHERE BookID=?', (bookid,))
        myDB.action('UPDATE wanted SET status="Snatched", Source=?, DownloadID=? WHERE NZBurl=?',
                    (Source, downloadID, dl_url))
        return True
    else:
        logger.error('Failed to download file @ <a href="%s">%s</a>' % (dl_url, dl_url))
        dlresult = "Failed to download file from %s" % Source
        myDB.action('UPDATE wanted SET status="Failed",DLResult=? WHERE NZBurl=?', (dlresult, dl_url))
        return False


def TORDownloadMethod(bookid=None, tor_title=None, tor_url=None, library='eBook'):
    myDB = database.DBConnection()
    downloadID = False
    Source = ''
    torrent = ''

    full_url = tor_url  # keep the url as stored in "wanted" table
    if 'magnet:?' in tor_url:
        # discard any other parameters and just use the magnet link
        tor_url = 'magnet:?' + tor_url.split('magnet:?')[1]
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
        if not tor_url.endswith('.torrent') and '.torrent' in tor_url:
            tor_url = tor_url.split('.torrent')[0] + '.torrent'

        headers = {'Accept-encoding': 'gzip', 'User-Agent': USER_AGENT}
        proxies = proxyList()

        try:
            logger.debug("Fetching %s" % tor_url)
            r = requests.get(tor_url, headers=headers, timeout=90, proxies=proxies)
            if str(r.status_code).startswith('2'):
                torrent = r.content
                if not len(torrent):
                    logger.warn("Got empty response for %s, rejecting" % tor_url)
                    return False
                elif len(torrent) < 100:
                    logger.warn("Only got %s bytes for %s, rejecting" % (len(torrent), tor_url))
                    return False
                else:
                    logger.debug("Got %s bytes for %s" % (len(torrent), tor_url))
            else:
                logger.warn("Got a %s response for %s, rejecting" % (r.status_code, tor_url))
                return False

        except requests.exceptions.Timeout:
            logger.warn('Timeout fetching file from url: %s' % tor_url)
            return False
        except Exception as e:
            # some jackett providers redirect internally using http 301 to a magnet link
            # which requests can't handle, so throws an exception
            logger.debug("Requests exception: %s" % str(e))
            if "magnet:?" in str(e):
                tor_url = 'magnet:?' + str(e).split('magnet:?')[1]. strip("'")
                logger.debug("Redirecting to %s" % tor_url)
            else:
                if hasattr(e, 'reason'):
                    logger.warn('%s fetching file from url: %s, %s' % (type(e).__name__, tor_url, e.reason))
                else:
                    logger.warn('%s fetching file from url: %s, %s' % (type(e).__name__, tor_url, str(e)))
                return False

    if not torrent and not tor_url.startswith('magnet:?'):
        logger.warn("No magnet or data, cannot continue")
        return False

    if lazylibrarian.CONFIG['TOR_DOWNLOADER_BLACKHOLE']:
        Source = "BLACKHOLE"
        logger.debug("Sending %s to blackhole" % tor_title)
        tor_name = cleanName(tor_title).replace(' ', '_')
        if tor_url and tor_url.startswith('magnet'):
            if lazylibrarian.CONFIG['TOR_CONVERT_MAGNET']:
                hashid = calculate_torrent_hash(tor_url)
                if not hashid:
                    hashid = tor_name
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

    hashid = calculate_torrent_hash(tor_url, torrent)
    if not hashid:
        logger.error("Unable to calculate torrent hash from url/data")
        logger.debug("url: %s" % tor_url)

        logger.debug("data: %s" % makeUnicode(str(torrent[:50])))
        return False

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
        Source = "QBITTORRENT"
        if torrent:
            logger.debug("Sending %s data to qbittorrent" % tor_title)
            status = qbittorrent.addTorrent(torrent, hashid)
        else:
            logger.debug("Sending %s url to qbittorrent" % tor_title)
            status = qbittorrent.addTorrent(tor_url, hashid)  # returns True or False
        if status:
            downloadID = hashid
            tor_title = qbittorrent.getName(hashid)

    if lazylibrarian.CONFIG['TOR_DOWNLOADER_TRANSMISSION'] and lazylibrarian.CONFIG['TRANSMISSION_HOST']:
        Source = "TRANSMISSION"
        if torrent:
            logger.debug("Sending %s data to Transmission" % tor_title)
            # transmission needs b64encoded metainfo to be unicode, not bytes
            downloadID = transmission.addTorrent(None, metainfo=makeUnicode(b64encode(torrent)))
        else:
            logger.debug("Sending %s url to Transmission" % tor_title)
            downloadID = transmission.addTorrent(tor_url)  # returns id or False
        if downloadID:
            # transmission returns it's own int, but we store hashid instead
            downloadID = hashid
            tor_title = transmission.getTorrentFolder(downloadID)

    if lazylibrarian.CONFIG['TOR_DOWNLOADER_SYNOLOGY'] and lazylibrarian.CONFIG['USE_SYNOLOGY'] and \
            lazylibrarian.CONFIG['SYNOLOGY_HOST']:
        logger.debug("Sending %s url to Synology" % tor_title)
        Source = "SYNOLOGY_TOR"
        downloadID = synology.addTorrent(tor_url)  # returns id or False
        if downloadID:
            tor_title = synology.getName(downloadID)

    if lazylibrarian.CONFIG['TOR_DOWNLOADER_DELUGE'] and lazylibrarian.CONFIG['DELUGE_HOST']:
        if not lazylibrarian.CONFIG['DELUGE_USER']:
            # no username, talk to the webui
            Source = "DELUGEWEBUI"
            if torrent:
                logger.debug("Sending %s data to Deluge" % tor_title)
                downloadID = deluge.addTorrent(tor_title, data=b64encode(torrent))
            else:
                logger.debug("Sending %s url to Deluge" % tor_title)
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
                    logger.debug("Sending %s magnet to DelugeRPC" % tor_title)
                    downloadID = client.call('core.add_torrent_magnet', tor_url, args)
                elif torrent:
                    logger.debug("Sending %s data to DelugeRPC" % tor_title)
                    downloadID = client.call('core.add_torrent_file', tor_title, b64encode(torrent), args)
                else:
                    logger.debug("Sending %s url to DelugeRPC" % tor_title)
                    downloadID = client.call('core.add_torrent_url', tor_url, args)
                if downloadID:
                    if lazylibrarian.CONFIG['DELUGE_LABEL']:
                        _ = client.call('label.set_torrent', downloadID, lazylibrarian.CONFIG['DELUGE_LABEL'].lower())
                    result = client.call('core.get_torrent_status', downloadID, {})
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
                        rejected = "Rejecting torrent name %s, contains %s" % (tor_title, word)
                        logger.debug(rejected)
                        break
                if rejected:
                    myDB.action('UPDATE wanted SET status="Failed",DLResult=? WHERE NZBurl=?',
                                (rejected, full_url))
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

    logger.error('Failed to send torrent to %s, %s' % (Source, tor_url))
    dlresult = "Failed to send torrent to %s" % Source
    myDB.action('UPDATE wanted SET status="Failed",DLResult=? WHERE NZBurl=?', (dlresult, full_url))
    return False


def calculate_torrent_hash(link, data=None):
    """
    Calculate the torrent hash from a magnet link or data. Returns empty string
    when it cannot create a torrent hash given the input data.
    """

    if link.startswith("magnet:"):
        torrent_hash = re.findall("urn:btih:([\w]{32,40})", link)[0]
        if len(torrent_hash) == 32:
            torrent_hash = b16encode(b32decode(torrent_hash)).lower()
    elif data:
        # noinspection PyUnresolvedReferences
        info = bdecode(data)["info"]
        torrent_hash = sha1(bencode(info)).hexdigest()
    else:
        logger.error("Cannot calculate torrent hash without magnet link or data")
        return ''

    logger.debug('Torrent Hash: ' + torrent_hash)
    return torrent_hash
