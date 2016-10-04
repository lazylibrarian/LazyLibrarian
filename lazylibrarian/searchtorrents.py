import urllib2
import socket
import os
import re
from base64 import b16encode, b32decode
from lib.bencode import bencode as bencode, bdecode
from hashlib import sha1
from magnet2torrent import magnet2torrent
import threading
import lazylibrarian
import unicodedata

from lazylibrarian import logger, database, utorrent, transmission, qbittorrent, deluge, rtorrent
from lib.deluge_client import DelugeRPCClient
from lib.fuzzywuzzy import fuzz

from lazylibrarian.common import scheduleJob, USER_AGENT
from lazylibrarian.cache import fetchURL
from lazylibrarian.formatter import plural, unaccented_str, replace_all, getList, check_int, now, cleanName
from lazylibrarian.providers import IterateOverTorrentSites
from lazylibrarian.notifiers import notify_snatch

# new to support torrents
from StringIO import StringIO
import gzip


def cron_search_tor_book():
    threading.currentThread().name = "CRON-SEARCHTOR"
    search_tor_book()


def search_tor_book(books=None, reset=False):
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
            tor_count = tor_count + 1

    logger.info("TORSearch for Wanted items complete, found %s book%s" % (tor_count, plural(tor_count)))

    if reset:
        scheduleJob(action='Restart', target='search_tor_book')


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

        already_failed = myDB.match('SELECT * from wanted WHERE NZBurl="%s" and Status="Failed"' %
                                    tor_url)
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
        if tor_size_temp is None:
            tor_size_temp = 1000
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
                snatch = DirectDownloadMethod(newValueDict["BookID"], newValueDict["NZBprov"],
                                              newValueDict["NZBtitle"], controlValueDict["NZBurl"], nzb_Title)
            else:
                snatch = TORDownloadMethod(newValueDict["BookID"], newValueDict["NZBprov"],
                                           newValueDict["NZBtitle"], controlValueDict["NZBurl"])
            if snatch:
                logger.info('Downloading %s from %s' % (newValueDict["NZBtitle"], newValueDict["NZBprov"]))
                notify_snatch("%s from %s at %s" %
                              (newValueDict["NZBtitle"], newValueDict["NZBprov"], now()))
                scheduleJob(action='Start', target='processDir')
                return True + True  # we found it
    else:
        logger.debug("No torrent's found for [%s] using searchtype %s" % (book["searchterm"], searchtype))
    return False


def DirectDownloadMethod(bookid=None, tor_prov=None, tor_title=None, tor_url=None, bookname=None):
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
        destdir = os.path.join(lazylibrarian.DOWNLOAD_DIR, tor_title)
        try:
            os.makedirs(destdir)
        except OSError as e:
            if 'File exists' not in e.strerror:  # directory already exists is ok
                logger.debug("Error creating directory %s, %s" % (destdir, e.strerror))

        destfile = os.path.join(destdir, bookname)
        try:
            with open(destfile, 'wb') as bookfile:
                bookfile.write(fdata)
            downloadID = True
        except Exception as e:
            logger.debug("Error writing book to %s, %s" % (destfile, str(e)))

    except (socket.timeout) as e:
        logger.warn('Timeout fetching file from url: %s' % tor_url)
        return False
    except (urllib2.URLError) as e:
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


def TORDownloadMethod(bookid=None, tor_prov=None, tor_title=None, tor_url=None):
    myDB = database.DBConnection()
    downloadID = False
    full_url = tor_url  # keep the url as stored in "wanted" table
    if (lazylibrarian.TOR_DOWNLOADER_DELUGE or
        lazylibrarian.TOR_DOWNLOADER_UTORRENT or
        lazylibrarian.TOR_DOWNLOADER_RTORRENT or
        lazylibrarian.TOR_DOWNLOADER_QBITTORRENT or
        lazylibrarian.TOR_DOWNLOADER_BLACKHOLE or
            lazylibrarian.TOR_DOWNLOADER_TRANSMISSION):

        if tor_url and tor_url.startswith('magnet'):
            torrent = tor_url  # allow magnet link to write to blackhole and hash to utorrent/rtorrent
        else:
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

            # PAB removed this, KAT serves us html instead of torrent if this header is sent
            # if tor_prov == 'KAT':
            #    host = lazylibrarian.KAT_HOST
            #    if not str(host)[:4] == "http":
            #        host = 'http://' + host
            #    request.add_header('Referer', host)

            try:
                response = urllib2.urlopen(request, timeout=90)
                if response.info().get('Content-Encoding') == 'gzip':
                    buf = StringIO(response.read())
                    f = gzip.GzipFile(fileobj=buf)
                    torrent = f.read()
                else:
                    torrent = response.read()

            except (socket.timeout) as e:
                logger.warn('Timeout fetching torrent from url: %s' % tor_url)
                return False
            except (urllib2.URLError) as e:
                logger.warn('Error fetching torrent from url: %s, %s' % (tor_url, e.reason))
                return False

        if lazylibrarian.TOR_DOWNLOADER_BLACKHOLE:
            Source = "BLACKHOLE"
            tor_title = cleanName(tor_title)
            logger.debug("Sending %s to blackhole" % tor_title)
            tor_name = str.replace(str(tor_title), ' ', '_')
            if tor_url and tor_url.startswith('magnet'):
                if lazylibrarian.TOR_CONVERT_MAGNET:
                    hashid = CalcTorrentHash(tor_url)
                    tor_name = 'meta-' + hashid + '.torrent'
                    tor_path = os.path.join(lazylibrarian.TORRENT_DIR, tor_name)
                    result = magnet2torrent(tor_url, tor_path)
                    if result is not False:
                        logger.debug('Magnet file saved as: %s' % tor_path)
                        downloadID = True
                else:
                    tor_name = tor_name + '.magnet'
                    tor_path = os.path.join(lazylibrarian.TORRENT_DIR, tor_name)
                    with open(tor_path, 'wb') as torrent_file:
                        torrent_file.write(torrent)
                    logger.debug('Magnet file saved: %s' % tor_path)
                    downloadID = True
            else:
                tor_name = tor_name + '.torrent'
                tor_path = os.path.join(lazylibrarian.TORRENT_DIR, tor_name)
                with open(tor_path, 'wb') as torrent_file:
                    torrent_file.write(torrent)
                logger.debug('Torrent file saved: %s' % tor_title)
                downloadID = True

        if (lazylibrarian.TOR_DOWNLOADER_UTORRENT and lazylibrarian.UTORRENT_HOST):
            logger.debug("Sending %s to Utorrent" % tor_title)
            Source = "UTORRENT"
            hashid = CalcTorrentHash(torrent)
            downloadID = utorrent.addTorrent(tor_url, hashid)

        if (lazylibrarian.TOR_DOWNLOADER_RTORRENT and lazylibrarian.RTORRENT_HOST):
            logger.debug("Sending %s to rTorrent" % tor_title)
            Source = "RTORRENT"
            hashid = CalcTorrentHash(torrent)
            downloadID = rtorrent.addTorrent(tor_url, hashid)

        if (lazylibrarian.TOR_DOWNLOADER_QBITTORRENT and lazylibrarian.QBITTORRENT_HOST):
            logger.debug("Sending %s to qbittorrent" % tor_title)
            Source = "QBITTORRENT"
            downloadID = qbittorrent.addTorrent(tor_url)

        if (lazylibrarian.TOR_DOWNLOADER_TRANSMISSION and lazylibrarian.TRANSMISSION_HOST):
            logger.debug("Sending %s to Transmission" % tor_title)
            Source = "TRANSMISSION"
            downloadID = transmission.addTorrent(tor_url)  # returns torrent_id or False

        if (lazylibrarian.TOR_DOWNLOADER_DELUGE and lazylibrarian.DELUGE_HOST):
            logger.debug("Sending %s to Deluge" % tor_title)
            if not lazylibrarian.DELUGE_USER:
                # no username, talk to the webui
                Source = "DELUGEWEBUI"
                downloadID = deluge.addTorrent(tor_url)
            else:
                # have username, talk to the daemon
                Source = "DELUGERPC"
                client = DelugeRPCClient(lazylibrarian.DELUGE_HOST,
                                         int(lazylibrarian.DELUGE_PORT),
                                         lazylibrarian.DELUGE_USER,
                                         lazylibrarian.DELUGE_PASS)
                client.connect()
                args = {"name": tor_title}
                downloadID = client.call('core.add_torrent_url', tor_url, args)
                logger.debug('Deluge torrent_id: %s' % downloadID)
                if downloadID and lazylibrarian.DELUGE_LABEL:
                    labelled = client.call('label.set_torrent', downloadID, lazylibrarian.DELUGE_LABEL)
                    logger.debug('Deluge label returned: %s' % labelled)
    else:
        logger.warn('No torrent download method is enabled, check config.')
        return False

    if downloadID:
        myDB.action('UPDATE books SET status = "Snatched" WHERE BookID="%s"' % bookid)
        myDB.action('UPDATE wanted SET status = "Snatched", Source = "%s", DownloadID = "%s" WHERE NZBurl="%s"' %
                    (Source, downloadID, full_url))
        return True
    else:
        logger.error(u'Failed to download torrent @ <a href="%s">%s</a>' % (full_url, tor_url))
        myDB.action('UPDATE wanted SET status = "Failed" WHERE NZBurl="%s"' % full_url)
        return False


def CalcTorrentHash(torrent):

    if torrent and torrent.startswith('magnet'):
        hashid = re.findall('urn:btih:([\w]{32,40})', torrent)[0]
        if len(hashid) == 32:
            hashid = b16encode(b32decode(hashid)).lower()
    else:
        info = bdecode(torrent)["info"]
        hashid = sha1(bencode(info)).hexdigest()
    logger.debug('Torrent Hash: ' + hashid)
    return hashid
