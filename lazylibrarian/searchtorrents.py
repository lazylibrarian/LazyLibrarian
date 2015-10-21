import time, threading, urllib, urllib2, os, re, sys
from base64 import b16encode, b32decode
from lib.bencode import bencode as bencode, bdecode
from hashlib import sha1
from xml.etree import ElementTree
from xml.etree.ElementTree import Element, SubElement

import lazylibrarian

from lazylibrarian import logger, database, formatter, providers, SimpleCache, notifiers, searchmag, utorrent, transmission

from lib.deluge_client import DelugeRPCClient

import lib.fuzzywuzzy as fuzzywuzzy
from lib.fuzzywuzzy import fuzz, process

#from lazylibrarian.common import USER_AGENT

import lazylibrarian.common as common
#new to support torrents
from StringIO import StringIO
import gzip

def search_tor_book(books=None, mags=None):
    if not(lazylibrarian.USE_TOR):
        return
    # rename this thread
    threading.currentThread().name = "SEARCHTORBOOKS"
    myDB = database.DBConnection()
    searchlist = []
    searchlist1 = []

    if books is None:
        # We are performing a backlog search
        searchbooks = myDB.select('SELECT BookID, AuthorName, Bookname from books WHERE Status="Wanted"')

        # Clear cache
        if os.path.exists(".ProviderCache"):
            for f in os.listdir(".ProviderCache"):
                os.unlink("%s/%s" % (".ProviderCache", f))

        # Clearing throttling timeouts
        t = SimpleCache.ThrottlingProcessor()
        t.lastRequestTime.clear()
    else:
        # The user has added a new book
        searchbooks = []
        if books != False:
            for book in books:
                searchbook = myDB.select('SELECT BookID, AuthorName, BookName from books WHERE BookID=? AND Status="Wanted"', [book['bookid']])
                for terms in searchbook:
                    searchbooks.append(terms)

    for searchbook in searchbooks:
        bookid = searchbook[0]
        author = searchbook[1]
        book = searchbook[2]

        dic = {'...':'', '.':' ', ' & ':' ', ' = ': ' ', '?':'', '$':'s', ' + ':' ', '"':'', ',':'', '*':'', ':':'', ';':''}
        dicSearchFormatting = {'.':' +', ' + ':' '}

        author = formatter.latinToAscii(formatter.replace_all(author, dic))
        book = formatter.latinToAscii(formatter.replace_all(book, dic))

        # TRY SEARCH TERM just using author name and book type
        author = formatter.latinToAscii(formatter.replace_all(author, dicSearchFormatting))
        searchterm = author + ' ' + book # + ' ' + lazylibrarian.EBOOK_TYPE 
        searchterm = re.sub('[\.\-\/]', ' ', searchterm).encode('utf-8')
        searchterm = re.sub(r'\(.*?\)', '', searchterm).encode('utf-8')
        searchterm = re.sub(r"\s\s+" , " ", searchterm) # strip any double white space
        searchlist.append({"bookid": bookid, "bookName":searchbook[2], "authorName":searchbook[1], "searchterm": searchterm.strip()})
    
    if not lazylibrarian.KAT:
        logger.info('No download method is set, use SABnzbd or blackhole')


    counter = 0
    for book in searchlist: 
        #print book.keys()
        resultlist = providers.IterateOverTorrentSites(book,'book')

        #if you can't find teh book specifically, you might find under general search
        if not resultlist:
            logger.info("Searching for type book failed to find any books...moving to general search")
            resultlist = providers.IterateOverTorrentSites(book,'general')

        if not resultlist:
            logger.debug("Adding book %s to queue." % book['searchterm'])

        else:
            dictrepl = {'...':'', '.':' ', ' & ':' ', ' = ': ' ', '?':'', '$':'s', ' + ':' ', '"':'', ',':'', '*':'', '(':'', ')':'', '[':'', ']':'', '#':'', '0':'', '1':'', '2':'', '3':'', '4':'', '5':'', '6':'', '7':'', '8':'' , '9':'', '\'':'', ':':'', '!':'', '-':'', '\s\s':' ', ' the ':' ', ' a ':' ', ' and ':' ', ' to ':' ', ' of ':' ', ' for ':' ', ' my ':' ', ' in ':' ', ' at ':' ', ' with ':' ' }
            logger.debug(u'searchterm %s' % book['searchterm'])
            addedCounter = 0

            for tor in resultlist:
                tor_Title = formatter.latinToAscii(formatter.replace_all(str(tor['tor_title']).lower(), dictrepl)).strip()
                tor_Title = re.sub(r"\s\s+" , " ", tor_Title) #remove extra whitespace
                logger.debug(u'torName %s' % tor_Title)          

                match_ratio = int(lazylibrarian.MATCH_RATIO)
                tor_Title_match = fuzz.token_sort_ratio(book['searchterm'].lower(), tor_Title)
                logger.debug("Torrent Title Match %: " + str(tor_Title_match))
                
                if (tor_Title_match > match_ratio):
                    logger.info(u'Found Torrent: %s' % tor['tor_title'])
                    addedCounter = addedCounter + 1
                    bookid = book['bookid']
                    tor_Title = (book["authorName"] + ' - ' + book['bookName'] + ' LL.(' + book['bookid'] + ')').strip()
                    tor_url = tor['tor_url']
                    tor_prov = tor['tor_prov']
                    
                    tor_size_temp = tor['tor_size']  #Need to cater for when this is NONE (Issue 35)
                    if tor_size_temp is None:
                        tor_size_temp = 1000
                    tor_size = str(round(float(tor_size_temp) / 1048576,2))+' MB'
                    
                    controlValueDict = {"NZBurl": tor_url}
                    newValueDict = {
                        "NZBprov": tor_prov,
                        "BookID": bookid,
                        "NZBsize": tor_size,
                        "NZBtitle": tor_Title,
                        "Status": "Skipped"
                    }
                    myDB.upsert("wanted", newValueDict, controlValueDict)

                    snatchedbooks = myDB.action('SELECT * from books WHERE BookID=? and Status="Snatched"', [bookid]).fetchone()
                    if not snatchedbooks:
                        snatch = DownloadMethod(bookid, tor_prov, tor_Title, tor_url)
                        notifiers.notify_snatch(tor_Title+' at '+formatter.now()) 
                    break;
            if addedCounter == 0:
                logger.info("No torrent's found for " + (book["authorName"] + ' ' + book['bookName']).strip() + ". Adding book to queue.")
        counter = counter + 1

   # if not books or books==False:
   #     snatched = searchmag.searchmagazines(mags)
   #     for items in snatched:
   #         snatch = DownloadMethod(items['bookid'], items['tor_prov'], items['tor_title'], items['tor_url'])
   #         notifiers.notify_snatch(items['tor_title']+' at '+formatter.now()) 
    logger.info("Search for Wanted items complete")


def DownloadMethod(bookid=None, tor_prov=None, tor_title=None, tor_url=None):

    myDB = database.DBConnection()
    download = False
    if (lazylibrarian.USE_TOR) and (lazylibrarian.TOR_DOWNLOADER_DELUGE or  lazylibrarian.TOR_DOWNLOADER_UTORRENT
                                    or lazylibrarian.TOR_DOWNLOADER_BLACKHOLE or lazylibrarian.TOR_DOWNLOADER_TRANSMISSION):
        request = urllib2.Request(tor_url)
	if lazylibrarian.PROXY_HOST:
		request.set_proxy(lazylibrarian.PROXY_HOST, lazylibrarian.PROXY_TYPE)
        request.add_header('Accept-encoding', 'gzip')
	request.add_header('User-Agent', common.USER_AGENT)
    
        if tor_prov == 'KAT':
            request.add_header('Referer', 'http://kat.cr/')
        
        response = urllib2.urlopen(request)
        if response.info().get('Content-Encoding') == 'gzip':
            buf = StringIO(response.read())
            f = gzip.GzipFile(fileobj=buf)
            torrent = f.read()
        else:
            torrent = response.read()

        if (lazylibrarian.TOR_DOWNLOADER_BLACKHOLE):
            logger.info('Torrent blackhole')
            tor_title = common.removeDisallowedFilenameChars(tor_title)
            tor_name = str.replace(str(tor_title), ' ', '_') + '.torrent'
            tor_path = os.path.join(lazylibrarian.TORRENT_DIR, tor_name)

            torrent_file = open(tor_path , 'wb')
            torrent_file.write(torrent)
            torrent_file.close()
            logger.info('Torrent file saved: %s' % tor_title)
            download = True

        if (lazylibrarian.TOR_DOWNLOADER_UTORRENT):            
            logger.info('Utorrent')
            hash = CalcTorrentHash(torrent)
            download = utorrent.addTorrent(tor_url, hash)

        if (lazylibrarian.TOR_DOWNLOADER_TRANSMISSION):
            logger.info('Transmission')
            download = transmission.addTorrent(tor_url)

        if (lazylibrarian.TOR_DOWNLOADER_DELUGE):
            client = DelugeRPCClient(lazylibrarian.DELUGE_HOST,
                    int(lazylibrarian.DELUGE_PORT),
                    lazylibrarian.DELUGE_USER,
                    lazylibrarian.DELUGE_PASS)
            client.connect()
            download = client.call('add_torrent_url',tor_url, {"name": tor_title})
            logger.info('Deluge return value: %s' % download)

    else:
        logger.error('No torrent download method is enabled, check config.')
        return False

    if download:
        logger.debug('Torrent file has been downloaded from ' + str(tor_url))
        myDB.action('UPDATE books SET status = "Snatched" WHERE BookID=?', [bookid])
        myDB.action('UPDATE wanted SET status = "Snatched" WHERE NZBurl=?', [tor_url])
    else:
        logger.error(u'Failed to download torrent @ <a href="%s">%s</a>' % (tor_url, tor_url))
        myDB.action('UPDATE wanted SET status = "Failed" WHERE NZBurl=?', [tor_url])

        
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


def MakeSearchTermWebSafe(insearchterm=None):

        dic = {'...':'', ' & ':' ', ' = ': ' ', '?':'', '$':'s', ' + ':' ', '"':'', ',':'', '*':''}

        searchterm = formatter.latinToAscii(formatter.replace_all(insearchterm, dic))

        searchterm = re.sub('[\.\-\/]', ' ', searchterm).encode('utf-8')
        
        logger.debug("Converting Search Term [%s] to Web Safe Search Term [%s]" % (insearchterm, searchterm))
        
        return searchterm
