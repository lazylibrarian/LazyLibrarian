import threading
import urllib2
import os
import shutil
import re
from base64 import b16encode, b32decode
from lib.bencode import bencode as bencode, bdecode
from hashlib import sha1

import lazylibrarian

from lazylibrarian import logger, database, formatter, providers, notifiers, utorrent, transmission

from lib.deluge_client import DelugeRPCClient

from lib.fuzzywuzzy import fuzz

import unicodedata

import lazylibrarian.common as common
# new to support torrents
from StringIO import StringIO
import gzip


def search_tor_book(books=None, mags=None):
    if not(lazylibrarian.USE_TOR):
        logger.warn('Torrent search is disabled')
        return
    # rename this thread
    threading.currentThread().name = "SEARCHTORBOOKS"
    myDB = database.DBConnection()
    searchlist = []

    if books is None:
        # We are performing a backlog search
        searchbooks = myDB.select('SELECT BookID, AuthorName, Bookname from books WHERE Status="Wanted"')
    else:
        # The user has added a new book
        searchbooks = []
        if books is not False:
            for book in books:
                searchbook = myDB.select('SELECT BookID, AuthorName, BookName from books WHERE BookID="%s" \
                                         AND Status="Wanted"' % book['bookid'])
                for terms in searchbook:
                    searchbooks.append(terms)

    if len(searchbooks) == 1:
        logger.info('TOR Searching for one book')
    else:
        logger.info('TOR Searching for %i books' % len(searchbooks))

    for searchbook in searchbooks:
        bookid = searchbook[0]
        author = searchbook[1]
        book = searchbook[2]

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

    counter = 0
    for book in searchlist:
        resultlist, nproviders = providers.IterateOverTorrentSites(book, 'book')
        if not nproviders:
            logger.warn('No torrent providers are set, check config for TORRENT providers')
            return

        # if you can't find teh book specifically, you might find under general search
        if not resultlist:
            logger.debug("Searching for type book failed to find any books...moving to general search")
            resultlist, nproviders = providers.IterateOverTorrentSites(book, 'general')

        if not resultlist:
            logger.debug("Adding book %s to queue." % book['searchterm'])

        else:
            dictrepl = {'...': '', '.': ' ', ' & ': ' ', ' = ': ' ', '?': '', '$': 's', ' + ': ' ', '"': '',
                        ',': '', '*': '', '(': '', ')': '', '[': '', ']': '', '#': '', '0': '', '1': '', '2': '',
                        '3': '', '4': '', '5': '', '6': '', '7': '', '8': '', '9': '', '\'': '', ':': '', '!': '',
                        '-': '', '\s\s': ' ', ' the ': ' ', ' a ': ' ', ' and ': ' ', ' to ': ' ', ' of ': ' ',
                        ' for ': ' ', ' my ': ' ', ' in ': ' ', ' at ': ' ', ' with ': ' '}
            logger.debug(u'searchterm %s' % book['searchterm'])
            addedCounter = 0

            for tor in resultlist:
                tor_Title = formatter.latinToAscii(formatter.replace_all(str(tor['tor_title']), dictrepl)).strip()
                tor_Title = re.sub(r"\s\s+", " ", tor_Title)  # remove extra whitespace
                logger.debug(u'torName %s' % tor_Title)

                match_ratio = int(lazylibrarian.MATCH_RATIO)
                tor_Title_match = fuzz.token_sort_ratio(book['searchterm'], tor_Title)
                logger.debug("Torrent Title Match %: " + str(tor_Title_match))

                if (tor_Title_match > match_ratio):
                    logger.debug(u'Found Torrent: %s' % tor['tor_title'])
                    addedCounter = addedCounter + 1
                    bookid = book['bookid']
                    tor_Title = (book["authorName"] + ' - ' + book['bookName'] +
                                 ' LL.(' + book['bookid'] + ')').strip()
                    tor_url = tor['tor_url']
                    tor_prov = tor['tor_prov']

                    tor_size_temp = tor['tor_size']  # Need to cater for when this is NONE (Issue 35)
                    if tor_size_temp is None:
                        tor_size_temp = 1000
                    tor_size = str(round(float(tor_size_temp) / 1048576, 2)) + ' MB'

                    controlValueDict = {"NZBurl": tor_url}
                    newValueDict = {
                        "NZBprov": tor_prov,
                        "BookID": bookid,
                        "NZBsize": tor_size,
                        "NZBtitle": tor_Title,
                        "NZBmode": "torrent",
                        "Status": "Skipped"
                    }
                    myDB.upsert("wanted", newValueDict, controlValueDict)

                    snatchedbooks = myDB.action('SELECT * from books WHERE BookID="%s" and Status="Snatched"' %
                                                bookid).fetchone()
                    if not snatchedbooks:
                        TORDownloadMethod(bookid, tor_prov, tor_Title, tor_url)
                        notifiers.notify_snatch(formatter.latinToAscii(tor_Title) + ' at ' + formatter.now())
                        postprocess.schedule_processor(action='Start')
                    break
            if addedCounter == 0:
                logger.debug("No torrent's found for " + (book["authorName"] + ' ' +
                             book['bookName']).strip() + ". Adding book to queue.")
        counter = counter + 1
    logger.info("TORSearch for Wanted items complete")


def TORDownloadMethod(bookid=None, tor_prov=None, tor_title=None, tor_url=None):
    myDB = database.DBConnection()
    download = False
    full_url = tor_url  # keep the url as stored in "wanted" table
    if (lazylibrarian.USE_TOR) and (lazylibrarian.TOR_DOWNLOADER_DELUGE or
                                    lazylibrarian.TOR_DOWNLOADER_UTORRENT or
                                    lazylibrarian.TOR_DOWNLOADER_BLACKHOLE or
                                    lazylibrarian.TOR_DOWNLOADER_TRANSMISSION):

        if tor_url.startswith('magnet'):
            torrent = tor_url  # allow magnet link to write to blackhole and hash to utorrent
        else:
            if '&file=' in tor_url:  # torznab results need to be re-encoded
                url = tor_url.split('&file=')[0]
                value = tor_url.split('&file=')[1]
                if isinstance(value, str):
                    value = value.decode('utf-8')  # make unicode
                value = unicodedata.normalize('NFC', value)  # normalize to short form
                value = value.encode('unicode-escape')  # then escape the result
                value = value.replace(' ', '%20')  # and encode any spaces
                tor_url = url + '&file=' + value

            # strip url back to the .torrent as some sites add parameters
            if '?' in tor_url:
                tor_url = tor_url.split('?')[0]

            request = urllib2.Request(ur'%s' % tor_url)
            if lazylibrarian.PROXY_HOST:
                request.set_proxy(lazylibrarian.PROXY_HOST, lazylibrarian.PROXY_TYPE)
            request.add_header('Accept-encoding', 'gzip')
            request.add_header('User-Agent', common.USER_AGENT)

            # PAB removed this, KAT serves us html instead of torrent if this header is sent
            #if tor_prov == 'KAT':
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

            except urllib2.URLError as e:
                logger.warn('Error fetching torrent from url: ' + tor_url + ' %s' % e.reason)
                return

        if (lazylibrarian.TOR_DOWNLOADER_BLACKHOLE):
            logger.debug('Torrent blackhole')
            tor_title = common.removeDisallowedFilenameChars(tor_title)
            tor_name = str.replace(str(tor_title), ' ', '_')
            if tor_url.startswith('magnet'):
                tor_name = tor_name + '.magnet'
            else:
                tor_name = tor_name + '.torrent'
            tor_path = os.path.join(lazylibrarian.TORRENT_DIR, tor_name)
            torrent_file = open(tor_path, 'wb')
            torrent_file.write(torrent)
            torrent_file.close()
            logger.debug('Torrent file saved: %s' % tor_title)
            download = True

        if (lazylibrarian.TOR_DOWNLOADER_UTORRENT):
            logger.debug('Utorrent')
            hash = CalcTorrentHash(torrent)
            download = utorrent.addTorrent(tor_url, hash)

        if (lazylibrarian.TOR_DOWNLOADER_TRANSMISSION):
            logger.debug('Transmission')
            download = transmission.addTorrent(tor_url)

        if (lazylibrarian.TOR_DOWNLOADER_DELUGE):
            client = DelugeRPCClient(lazylibrarian.DELUGE_HOST,
                                     int(lazylibrarian.DELUGE_PORT),
                                     lazylibrarian.DELUGE_USER,
                                     lazylibrarian.DELUGE_PASS)
            if lazylibrarian.DELUGE_USER and lazylibrarian.DELUGE_PASS:
                client.connect()
                download = client.call('core.add_torrent_url', tor_url, {"name": tor_title})
                logger.debug('Deluge return value: %s' % download)
            else:
                logger.warn('Need user & pass for deluge, check config.')
    else:
        logger.warn('No torrent download method is enabled, check config.')
        return False

    if download:
        logger.debug(u'Torrent file has been downloaded from %s' % tor_url)
        myDB.action('UPDATE books SET status = "Snatched" WHERE BookID="%s"' % bookid)
        myDB.action('UPDATE wanted SET status = "Snatched" WHERE NZBurl="%s"' % full_url)
    else:
        logger.error(u'Failed to download torrent @ <a href="%s">%s</a>' % (full_url, tor_url))
        myDB.action('UPDATE wanted SET status = "Failed" WHERE NZBurl="%s"' % full_url)


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
