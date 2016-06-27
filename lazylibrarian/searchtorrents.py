import threading
import urllib2
import socket
import os
import re
from base64 import b16encode, b32decode
from lib.bencode import bencode as bencode, bdecode
from hashlib import sha1

import lazylibrarian

from lazylibrarian import logger, database, formatter, providers, notifiers, utorrent, transmission, qbittorrent, deluge

from lib.deluge_client import DelugeRPCClient

from lib.fuzzywuzzy import fuzz

import unicodedata

import lazylibrarian.common as common
# new to support torrents
from StringIO import StringIO
import gzip


def search_tor_book(books=None, reset=False):
    if not lazylibrarian.USE_TOR():
        logger.warn('No Torrent providers set, check config')
        return
    # rename this thread
    threading.currentThread().name = "SEARCHTORBOOKS"
    myDB = database.DBConnection()
    searchlist = []

    if books is None:
        # We are performing a backlog search
        searchbooks = myDB.select('SELECT BookID, AuthorName, Bookname, BookAdded from books WHERE Status="Wanted" order by BookAdded desc')
    else:
        # The user has added a new book
        searchbooks = []
        for book in books:
            searchbook = myDB.select('SELECT BookID, AuthorName, BookName from books WHERE BookID="%s" \
                                     AND Status="Wanted"' % book['bookid'])
            for terms in searchbook:
                searchbooks.append(terms)

    if len(searchbooks) == 0:
        logger.debug("TOR search requested for no books or invalid BookID")
        return
    elif len(searchbooks) == 1:
        logger.info('TOR Searching for one book')
    else:
        logger.info('TOR Searching for %i books' % len(searchbooks))

    for searchbook in searchbooks:
        bookid = searchbook['BookID']
        author = searchbook['AuthorName']
        book = searchbook['BookName']

        dic = {'...': '', '.': ' ', ' & ': ' ', ' = ': ' ', '?': '', '$': 's', ' + ': ' ', '"': '',
               ',': '', '*': '', ':': '', ';': ''}
        dicSearchFormatting = {'.': ' +', ' + ': ' '}

        author = formatter.latinToAscii(formatter.replace_all(author, dic))
        book = formatter.latinToAscii(formatter.replace_all(book, dic))

        # TRY SEARCH TERM just using author name and book type
        author = formatter.latinToAscii(formatter.replace_all(author, dicSearchFormatting))
        searchterm = author + ' ' + book  # + ' ' + lazylibrarian.EBOOK_TYPE
        searchterm = re.sub('[\.\-\/]', ' ', searchterm).encode('utf-8')
        searchterm = re.sub(r'\(.*?\)', '', searchterm).encode('utf-8')
        searchterm = re.sub(r"\s\s+", " ", searchterm)  # strip any double white space
        searchlist.append({"bookid": bookid, "bookName": searchbook[2], "authorName": searchbook[1],
                           "searchterm": searchterm.strip()})

    tor_count = 0
    for book in searchlist:

        resultlist, nproviders = providers.IterateOverTorrentSites(book, 'book')
        if not nproviders:
            logger.warn('No torrent providers are set, check config')
            return  # No point in continuing

        found = processResultList(resultlist, book, "book")

        # if you can't find the book, try author/title without any "(extended details, series etc)"
        if not found and '(' in book['bookName']:
            resultlist, nproviders = providers.IterateOverTorrentSites(book, 'shortbook')
            found = processResultList(resultlist, book, "shortbook")

        # if you can't find the book under "books", you might find under general search
        if not found:
            resultlist, nproviders = providers.IterateOverTorrentSites(book, 'general')
            found = processResultList(resultlist, book, "general")

        # if you still can't find the book, try with author only
        if not found:
            resultlist, nproviders = providers.IterateOverTorrentSites(book, 'author')
            found = processResultList(resultlist, book, "author")

        if not found:
            logger.debug("Searches returned no results. Adding book %s to queue." % book['searchterm'])
        else:
            tor_count = tor_count + 1

    plural = "s"
    if tor_count == 1:
        plural = ""
    logger.info("TORSearch for Wanted items complete, found %s book%s" % (tor_count, plural))

    if reset:
        common.schedule_job(action='Restart', target='search_tor_book')


def processResultList(resultlist, book, searchtype):
    myDB = database.DBConnection()
    dictrepl = {'...': '', '.': ' ', ' & ': ' ', ' = ': ' ', '?': '', '$': 's', ' + ': ' ', '"': '',
                ',': ' ', '*': '', '(': '', ')': '', '[': '', ']': '', '#': '', '0': '', '1': '', '2': '',
                '3': '', '4': '', '5': '', '6': '', '7': '', '8': '', '9': '', '\'': '', ':': '', '!': '',
                '-': ' ', '\s\s': ' '}
                # ' the ': ' ', ' a ': ' ', ' and ': ' ', ' to ': ' ', ' of ': ' ',
                # ' for ': ' ', ' my ': ' ', ' in ': ' ', ' at ': ' ', ' with ': ' '}

    dic = {'...': '', '.': ' ', ' & ': ' ', ' = ': ' ', '?': '', '$': 's', ' + ': ' ', '"': '',
           ',': '', '*': '', ':': '', ';': ''}

    match_ratio = int(lazylibrarian.MATCH_RATIO)
    reject_list = formatter.getList(lazylibrarian.REJECT_WORDS)
    author = formatter.latinToAscii(formatter.replace_all(book['authorName'], dic))
    title = formatter.latinToAscii(formatter.replace_all(book['bookName'], dic))

    matches = []
    for tor in resultlist:
        torTitle = formatter.latinToAscii(formatter.replace_all(str(tor['tor_title']), dictrepl)).strip()
        torTitle = re.sub(r"\s\s+", " ", torTitle)  # remove extra whitespace

        torAuthor_match = fuzz.token_set_ratio(author, torTitle)
        torBook_match = fuzz.token_set_ratio(title, torTitle)
        logger.debug(u"TOR author/book Match: %s/%s for %s" % (torAuthor_match, torBook_match, torTitle))

        rejected = False

        for word in reject_list:
            if word in torTitle.lower() and not word in author.lower() and not word in title.lower():
                rejected = True
                logger.debug("Rejecting %s, contains %s" % (torTitle, word))
                break

        tor_size_temp = tor['tor_size']  # Need to cater for when this is NONE (Issue 35)
        if tor_size_temp is None:
            tor_size_temp = 1000
        tor_size = round(float(tor_size_temp) / 1048576, 2)

        maxsize = formatter.check_int(lazylibrarian.REJECT_MAXSIZE, 0)
        if maxsize and tor_size > maxsize:
            rejected = True
            logger.debug("Rejecting %s, too large" % torTitle)

        if (torAuthor_match >= match_ratio and torBook_match >= match_ratio and not rejected):
            #logger.debug(u'Found Torrent: %s using %s search' % (tor['tor_title'], searchtype))
            bookid = book['bookid']
            tor_Title = (author + ' - ' + title + ' LL.(' + book['bookid'] + ')').strip()
            tor_url = tor['tor_url']
            tor_prov = tor['tor_prov']

            controlValueDict = {"NZBurl": tor_url}
            newValueDict = {
                "NZBprov": tor_prov,
                "BookID": bookid,
                "NZBdate": formatter.now(),  # when we asked for it
                "NZBsize": tor_size,
                "NZBtitle": tor_Title,
                "NZBmode": "torrent",
                "Status": "Skipped"
            }

            score = (torBook_match + torAuthor_match)/2  # as a percentage
            # lose a point for each extra word in the title so we get the closest match
            words = len(formatter.getList(torTitle))
            words -= len(formatter.getList(author))
            words -= len(formatter.getList(title))
            score -= abs(words)
            matches.append([score, torTitle, newValueDict, controlValueDict])

    if matches:
        highest = max(matches, key=lambda x: x[0])
        score = highest[0]
        nzb_Title = highest[1]
        newValueDict = highest[2]
        controlValueDict = highest[3]
        logger.info(u'Best match TOR (%s%%): %s using %s search' %
            (score, nzb_Title, searchtype))

        myDB.upsert("wanted", newValueDict, controlValueDict)

        snatchedbooks = myDB.action('SELECT * from books WHERE BookID="%s" and Status="Snatched"' %
                                    newValueDict["BookID"]).fetchone()
        if not snatchedbooks:
            snatch = TORDownloadMethod(newValueDict["BookID"], newValueDict["NZBprov"],
                                           newValueDict["NZBtitle"], controlValueDict["NZBurl"])
            if snatch:
                notifiers.notify_snatch(newValueDict["NZBtitle"] + ' at ' + formatter.now())
                common.schedule_job(action='Start', target='processDir')
                return True

    logger.debug("No torrent's found for " + (book["authorName"] + ' ' +
                 book['bookName']).strip() + " using searchtype " + searchtype)
    return False


def TORDownloadMethod(bookid=None, tor_prov=None, tor_title=None, tor_url=None):
    myDB = database.DBConnection()
    download = False
    full_url = tor_url  # keep the url as stored in "wanted" table
    if (lazylibrarian.TOR_DOWNLOADER_DELUGE or
        lazylibrarian.TOR_DOWNLOADER_UTORRENT or
        lazylibrarian.TOR_DOWNLOADER_QBITTORRENT or
        lazylibrarian.TOR_DOWNLOADER_BLACKHOLE or
        lazylibrarian.TOR_DOWNLOADER_TRANSMISSION):

        if tor_url.startswith('magnet'):
            torrent = tor_url  # allow magnet link to write to blackhole and hash to utorrent
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
            request.add_header('User-Agent', common.USER_AGENT)

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

            except (urllib2.URLError, socket.timeout) as e:
                logger.warn('Error fetching torrent from url: %s, %s' % (tor_url, e))
                return False

        if lazylibrarian.TOR_DOWNLOADER_BLACKHOLE:
            tor_title = common.removeDisallowedFilenameChars(tor_title)
            logger.debug("Sending %s to blackhole" % tor_title)
            tor_name = str.replace(str(tor_title), ' ', '_')
            if tor_url.startswith('magnet'):
                tor_name = tor_name + '.magnet'
            else:
                tor_name = tor_name + '.torrent'
            tor_path = os.path.join(lazylibrarian.TORRENT_DIR, tor_name)
            with open(tor_path, 'wb') as torrent_file:
                torrent_file.write(torrent)
            logger.debug('Torrent file saved: %s' % tor_title)
            download = True

        if  (lazylibrarian.TOR_DOWNLOADER_UTORRENT and lazylibrarian.UTORRENT_HOST):
            logger.debug("Sending %s to Utorrent" % tor_title)
            hash = CalcTorrentHash(torrent)
            download = utorrent.addTorrent(tor_url, hash)

        if  (lazylibrarian.TOR_DOWNLOADER_QBITTORRENT and lazylibrarian.QBITTORRENT_HOST):
            logger.debug("Sending %s to qbittorrent" % tor_title)
            download = qbittorrent.addTorrent(tor_url)

        if  (lazylibrarian.TOR_DOWNLOADER_TRANSMISSION and lazylibrarian.TRANSMISSION_HOST):
            logger.debug("Sending %s to Transmission" % tor_title)
            download = transmission.addTorrent(tor_url)

        if  (lazylibrarian.TOR_DOWNLOADER_DELUGE and lazylibrarian.DELUGE_HOST):
            logger.debug("Sending %s to Deluge" % tor_title)
            if not lazylibrarian.DELUGE_USER:
                # no username, talk to the webui
                download = deluge.addTorrent(tor_url)
            else:
                # have username, talk to the daemon
                client = DelugeRPCClient(lazylibrarian.DELUGE_HOST,
                                     int(lazylibrarian.DELUGE_PORT),
                                     lazylibrarian.DELUGE_USER,
                                     lazylibrarian.DELUGE_PASS)
                client.connect()
                args = {"name": tor_title}
                download = client.call('core.add_torrent_url', tor_url, args)
                logger.debug('Deluge torrent_id: %s' % download)
                if download and lazylibrarian.DELUGE_LABEL:
                    labelled = client.call('label.set_torrent', download, lazylibrarian.DELUGE_LABEL)
                    logger.debug('Deluge label returned: %s' % labelled)
    else:
        logger.warn('No torrent download method is enabled, check config.')
        return False

    if download:
        logger.debug(u'Torrent id %s has been downloaded from %s' % (download, tor_url))
        myDB.action('UPDATE books SET status = "Snatched" WHERE BookID="%s"' % bookid)
        myDB.action('UPDATE wanted SET status = "Snatched" WHERE NZBurl="%s"' % full_url)
        return True
    else:
        logger.error(u'Failed to download torrent @ <a href="%s">%s</a>' % (full_url, tor_url))
        myDB.action('UPDATE wanted SET status = "Failed" WHERE NZBurl="%s"' % full_url)
        return False


def CalcTorrentHash(torrent):

    if torrent.startswith('magnet'):
        hash = re.findall('urn:btih:([\w]{32,40})', torrent)[0]
        if len(hash) == 32:
            hash = b16encode(b32decode(hash)).lower()
    else:
        info = bdecode(torrent)["info"]
        hash = sha1(bencode(info)).hexdigest()
    logger.debug('Torrent Hash: ' + hash)
    return hash
