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
import threading
import traceback
import unicodedata
import urllib2
from StringIO import StringIO
from base64 import b16encode, b32decode
from hashlib import sha1
#from HTMLParser import HTMLParser

import lazylibrarian
from lazylibrarian import logger, database, utorrent, transmission, qbittorrent, deluge, rtorrent, synology, bencode
from lazylibrarian.common import scheduleJob, USER_AGENT, setperm
from lazylibrarian.formatter import plural, unaccented_str, replace_all, getList, check_int, now, cleanName
from lazylibrarian.notifiers import notify_snatch
from lazylibrarian.providers import IterateOverTorrentSites
from lib.deluge_client import DelugeRPCClient
from lib.fuzzywuzzy import fuzz
from magnet2torrent import magnet2torrent


def cron_search_tor_book():
    threading.currentThread().name = "CRON-SEARCHTOR"
    search_tor_book()


def search_tor_book(books=None, reset=False):
    try:
        threadname = threading.currentThread().name
        if "Thread-" in threadname:
            threading.currentThread().name = "SEARCHTOR"

        if not lazylibrarian.USE_TOR():
            logger.warn('No Torrent providers set, check config')
            return

        myDB = database.DBConnection()
        searchlist = []

        if books is None:
            # We are performing a backlog search
            searchbooks = myDB.select(
                'SELECT BookID, AuthorName, Bookname, BookSub, BookAdded from books WHERE Status="Wanted" order by BookAdded desc')
        else:
            # The user has added a new book
            searchbooks = []
            for book in books:
                searchbook = myDB.select('SELECT BookID, AuthorName, BookName, BookSub from books WHERE BookID="%s" \
                                         AND Status="Wanted"' % book['bookid'])
                for terms in searchbook:
                    searchbooks.append(terms)

        if len(searchbooks) == 0:
            return

        logger.info('TOR Searching for %i book%s' % (len(searchbooks), plural(len(searchbooks))))

        for searchbook in searchbooks:
            # searchterm is only used for display purposes
            searchterm = searchbook['AuthorName'] + ' ' + searchbook['BookName']
            if searchbook['BookSub']:
                searchterm = searchterm + ': ' + searchbook['BookSub']

            searchlist.append(
                {"bookid": searchbook['BookID'],
                 "bookName": searchbook['BookName'],
                 "bookSub": searchbook['BookSub'],
                 "authorName": searchbook['AuthorName'],
                 "searchterm": searchterm})

        tor_count = 0
        for book in searchlist:

            resultlist, nproviders = IterateOverTorrentSites(book, 'book')
            if not nproviders:
                logger.warn('No torrent providers are set, check config')
                return  # No point in continuing

            found = processResultList(resultlist, book, "book")

            # if you can't find the book, try author/title without any "(extended details, series etc)"
            if not found and '(' in book['bookName']:
                resultlist, nproviders = IterateOverTorrentSites(book, 'shortbook')
                found = processResultList(resultlist, book, "shortbook")

            # general search is the same as booksearch for torrents
            # if not found:
            #    resultlist, nproviders = IterateOverTorrentSites(book, 'general')
            #    found = processResultList(resultlist, book, "general")

            if not found:
                logger.debug("Searches for %s returned no results." % book['searchterm'])
            if found > True:
                tor_count += 1

        logger.info("TORSearch for Wanted items complete, found %s book%s" % (tor_count, plural(tor_count)))

        if reset:
            scheduleJob(action='Restart', target='search_tor_book')

    except Exception:
        logger.error('Unhandled exception in search_tor_book: %s' % traceback.format_exc())


def processResultList(resultlist, book, searchtype):
    myDB = database.DBConnection()
    dictrepl = {'...': '', '.': ' ', ' & ': ' ', ' = ': ' ', '?': '', '$': 's', ' + ': ' ', '"': '',
                ',': ' ', '*': '', '(': '', ')': '', '[': '', ']': '', '#': '', '0': '', '1': '', '2': '',
                '3': '', '4': '', '5': '', '6': '', '7': '', '8': '', '9': '', '\'': '', ':': '', '!': '',
                '-': ' ', '\s\s': ' '}

    dic = {'...': '', '.': ' ', ' & ': ' ', ' = ': ' ', '?': '', '$': 's', ' + ': ' ', '"': '',
           ',': '', '*': '', ':': '', ';': ''}

    match_ratio = int(lazylibrarian.MATCH_RATIO)
    reject_list = getList(lazylibrarian.REJECT_WORDS)
    author = unaccented_str(replace_all(book['authorName'], dic))
    title = unaccented_str(replace_all(book['bookName'], dic))

    matches = []
    for tor in resultlist:
        torTitle = unaccented_str(tor['tor_title'])
        torTitle = replace_all(torTitle, dictrepl).strip()
        torTitle = re.sub(r"\s\s+", " ", torTitle)  # remove extra whitespace

        torAuthor_match = fuzz.token_set_ratio(author, torTitle)
        torBook_match = fuzz.token_set_ratio(title, torTitle)
        logger.debug(u"TOR author/book Match: %s/%s for %s" % (torAuthor_match, torBook_match, torTitle))
        tor_url = tor['tor_url']

        rejected = False

        already_failed = myDB.match('SELECT * from wanted WHERE NZBurl="%s" and Status="Failed"' % tor_url)
        if already_failed:
            logger.debug("Rejecting %s, blacklisted at %s" % (torTitle, already_failed['NZBprov']))
            rejected = True

        if not rejected:
            for word in reject_list:
                if word in torTitle.lower() and word not in author.lower() and word not in title.lower():
                    rejected = True
                    logger.debug("Rejecting %s, contains %s" % (torTitle, word))
                    break

        tor_size_temp = tor['tor_size']  # Need to cater for when this is NONE (Issue 35)
        tor_size_temp = check_int(tor_size_temp, 1000)
        tor_size = round(float(tor_size_temp) / 1048576, 2)

        maxsize = check_int(lazylibrarian.REJECT_MAXSIZE, 0)
        if not rejected:
            if maxsize and tor_size > maxsize:
                rejected = True
                logger.debug("Rejecting %s, too large" % torTitle)

        if not rejected:
            bookid = book['bookid']
            tor_Title = (author + ' - ' + title + ' LL.(' + book['bookid'] + ')').strip()

            controlValueDict = {"NZBurl": tor_url}
            newValueDict = {
                "NZBprov": tor['tor_prov'],
                "BookID": bookid,
                "NZBdate": now(),  # when we asked for it
                "NZBsize": tor_size,
                "NZBtitle": tor_Title,
                "NZBmode": "torrent",
                "Status": "Skipped"
            }

            score = (torBook_match + torAuthor_match) / 2  # as a percentage
            # lose a point for each extra word in the title so we get the closest match
            words = len(getList(torTitle))
            words -= len(getList(author))
            words -= len(getList(title))
            score -= abs(words)
            matches.append([score, torTitle, newValueDict, controlValueDict])

    if matches:
        highest = max(matches, key=lambda x: x[0])
        score = highest[0]
        nzb_Title = highest[1]
        newValueDict = highest[2]
        controlValueDict = highest[3]

        if score < match_ratio:
            logger.info(u'Nearest TOR match (%s%%): %s using %s search for %s %s' %
                        (score, nzb_Title, searchtype, author, title))
            return False

        logger.info(u'Best TOR match (%s%%): %s using %s search' %
                    (score, nzb_Title, searchtype))

        snatchedbooks = myDB.match('SELECT * from books WHERE BookID="%s" and Status="Snatched"' %
                                   newValueDict["BookID"])
        if snatchedbooks:
            logger.debug('%s already marked snatched' % nzb_Title)
            return True  # someone else found it, not us
        else:
            myDB.upsert("wanted", newValueDict, controlValueDict)
            if newValueDict["NZBprov"] == 'libgen':
                # for libgen we use direct download links
                snatch = DirectDownloadMethod(newValueDict["BookID"], newValueDict["NZBtitle"], controlValueDict["NZBurl"], nzb_Title)
            else:
                snatch = TORDownloadMethod(newValueDict["BookID"], newValueDict["NZBtitle"], controlValueDict["NZBurl"])
            if snatch:
                logger.info('Downloading %s from %s' % (newValueDict["NZBtitle"], newValueDict["NZBprov"]))
                notify_snatch("%s from %s at %s" %
                              (newValueDict["NZBtitle"], newValueDict["NZBprov"], now()))
                scheduleJob(action='Start', target='processDir')
                return True + True  # we found it
    else:
        logger.debug("No torrent's found for [%s] using searchtype %s" % (book["searchterm"], searchtype))
    return False


def DirectDownloadMethod(bookid=None, tor_title=None, tor_url=None, bookname=None):
    myDB = database.DBConnection()
    downloadID = False
    Source = "DIRECT"
    full_url = tor_url  # keep the url as stored in "wanted" table

    request = urllib2.Request(ur'%s' % tor_url)
    if lazylibrarian.PROXY_HOST:
        request.set_proxy(lazylibrarian.PROXY_HOST, lazylibrarian.PROXY_TYPE)
    request.add_header('Accept-encoding', 'gzip')
    request.add_header('User-Agent', USER_AGENT)

    try:
        response = urllib2.urlopen(request, timeout=90)
        if response.info().get('Content-Encoding') == 'gzip':
            buf = StringIO(response.read())
            f = gzip.GzipFile(fileobj=buf)
            fdata = f.read()
        else:
            fdata = response.read()
        bookname = '.'.join(bookname.rsplit(' ', 1))  # last word is the extension
        logger.debug("File download got %s bytes for %s/%s" % (len(fdata), tor_title, bookname))
        destdir = os.path.join(lazylibrarian.DIRECTORY('Download'), tor_title)
        try:
            os.makedirs(destdir)
            setperm(destdir)
        except OSError as e:
            if e.errno is not 17:  # directory already exists is ok. Using errno because of different languages
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
        myDB.action('UPDATE books SET status = "Snatched" WHERE BookID="%s"' % bookid)
        myDB.action('UPDATE wanted SET status = "Snatched", Source = "%s", DownloadID = "%s" WHERE NZBurl="%s"' %
                    (Source, downloadID, full_url))
        return True
    else:
        logger.error(u'Failed to download file @ <a href="%s">%s</a>' % (full_url, tor_url))
        myDB.action('UPDATE wanted SET status = "Failed" WHERE NZBurl="%s"' % full_url)
        return False


def TORDownloadMethod(bookid=None, tor_title=None, tor_url=None):
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
            url = tor_url.split('&file=')[0]
            value = tor_url.split('&file=')[1]
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
        if lazylibrarian.PROXY_HOST:
            request.set_proxy(lazylibrarian.PROXY_HOST, lazylibrarian.PROXY_TYPE)
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

    if lazylibrarian.TOR_DOWNLOADER_BLACKHOLE:
        Source = "BLACKHOLE"
        logger.debug("Sending %s to blackhole" % tor_title)
        tor_name = cleanName(tor_title).replace(' ', '_')
        if tor_url and tor_url.startswith('magnet'):
            if lazylibrarian.TOR_CONVERT_MAGNET:
                hashid = CalcTorrentHash(tor_url)
                tor_name = 'meta-' + hashid + '.torrent'
                tor_path = os.path.join(lazylibrarian.TORRENT_DIR, tor_name)
                result = magnet2torrent(tor_url, tor_path)
                if result is not False:
                    logger.debug('Magnet file saved as: %s' % tor_path)
                    downloadID = Source
            else:
                tor_name += '.magnet'
                tor_path = os.path.join(lazylibrarian.TORRENT_DIR, tor_name)
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
            tor_path = os.path.join(lazylibrarian.TORRENT_DIR, tor_name)
            try:
                with open(tor_path, 'wb') as torrent_file:
                    torrent_file.write(torrent)
                setperm(tor_path)
                logger.debug('Torrent file saved: %s' % tor_name)
                downloadID = Source
            except Exception as e:
                logger.debug("Failed to write torrent to file %s, %s" % (tor_path, str(e)))
                return False

    if lazylibrarian.TOR_DOWNLOADER_UTORRENT and lazylibrarian.UTORRENT_HOST:
        logger.debug("Sending %s to Utorrent" % tor_title)
        Source = "UTORRENT"
        hashid = CalcTorrentHash(torrent)
        downloadID = utorrent.addTorrent(tor_url, hashid)  # returns hash or False
        if downloadID:
            tor_title = utorrent.nameTorrent(downloadID)

    if lazylibrarian.TOR_DOWNLOADER_RTORRENT and lazylibrarian.RTORRENT_HOST:
        logger.debug("Sending %s to rTorrent" % tor_title)
        Source = "RTORRENT"
        hashid = CalcTorrentHash(torrent)
        downloadID = rtorrent.addTorrent(tor_url, hashid)  # returns hash or False
        if downloadID:
            tor_title = rtorrent.getName(downloadID)

    if lazylibrarian.TOR_DOWNLOADER_QBITTORRENT and lazylibrarian.QBITTORRENT_HOST:
        logger.debug("Sending %s to qbittorrent" % tor_title)
        Source = "QBITTORRENT"
        hashid = CalcTorrentHash(torrent)
        status = qbittorrent.addTorrent(tor_url)  # returns hash or False
        if status:
            downloadID = hashid
            tor_title = qbittorrent.getName(hashid)

    if lazylibrarian.TOR_DOWNLOADER_TRANSMISSION and lazylibrarian.TRANSMISSION_HOST:
        logger.debug("Sending %s to Transmission" % tor_title)
        Source = "TRANSMISSION"
        downloadID = transmission.addTorrent(tor_url)  # returns id or False
        if downloadID:
            # transmission returns it's own int, but we store hashid instead
            downloadID = CalcTorrentHash(torrent)
            tor_title = transmission.getTorrentFolder(downloadID)

    if lazylibrarian.TOR_DOWNLOADER_SYNOLOGY and lazylibrarian.USE_SYNOLOGY and lazylibrarian.SYNOLOGY_HOST:
        logger.debug("Sending %s to Synology" % tor_title)
        Source = "SYNOLOGY_TOR"
        downloadID = synology.addTorrent(tor_url)  # returns id or False
        if downloadID:
            tor_title = synology.getName(downloadID)

    if lazylibrarian.TOR_DOWNLOADER_DELUGE and lazylibrarian.DELUGE_HOST:
        logger.debug("Sending %s to Deluge" % tor_title)
        if not lazylibrarian.DELUGE_USER:
            # no username, talk to the webui
            Source = "DELUGEWEBUI"
            downloadID = deluge.addTorrent(tor_url)  # returns hash or False
            if downloadID:
                tor_title = deluge.getTorrentFolder(downloadID)
        else:
            # have username, talk to the daemon
            Source = "DELUGERPC"
            client = DelugeRPCClient(lazylibrarian.DELUGE_HOST,
                                     int(lazylibrarian.DELUGE_PORT),
                                     lazylibrarian.DELUGE_USER,
                                     lazylibrarian.DELUGE_PASS)
            try:
                client.connect()
                args = {"name": tor_title}
                if tor_url.startswith('magnet'):
                    downloadID = client.call('core.add_torrent_magnet', tor_url, args)
                else:
                    downloadID = client.call('core.add_torrent_url', tor_url, args)
                if downloadID:
                    if lazylibrarian.DELUGE_LABEL:
                        result = client.call('label.set_torrent', downloadID, lazylibrarian.DELUGE_LABEL)
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
        myDB.action('UPDATE books SET status = "Snatched" WHERE BookID="%s"' % bookid)
        myDB.action('UPDATE wanted SET status = "Snatched", Source = "%s", DownloadID = "%s" WHERE NZBurl="%s"' %
                    (Source, downloadID, full_url))
        if tor_title:
            if downloadID.upper() in tor_title.upper():
                logger.warn('%s: name contains hash, probably unresolved magnet' % Source)
            else:
                tor_title = unaccented_str(tor_title)
                logger.debug('%s setting torrent name to [%s]' % (Source, tor_title))
                myDB.action('UPDATE wanted SET NZBtitle = "%s" WHERE NZBurl="%s"' % (tor_title, full_url))
        return True
    else:
        logger.error(u'Failed to download torrent from %s, %s' % (Source, tor_url))
        myDB.action('UPDATE wanted SET status = "Failed" WHERE NZBurl="%s"' % full_url)
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
