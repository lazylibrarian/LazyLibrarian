import time, threading, urllib, urllib2, os, re

from xml.etree import ElementTree
from xml.etree.ElementTree import Element, SubElement

import lazylibrarian

from lazylibrarian import logger, database, formatter, providers, sabnzbd

def searchbook(books=None):

    # rename this thread
    threading.currentThread().name = "SEARCHBOOKS"
    myDB = database.DBConnection()
    searchlist = []

    if books is None:
        logger.debug('Searching for all books with status WANTED')
        searchbooks = myDB.select('SELECT BookID, AuthorName, Bookname from books WHERE Status="Wanted"')
    else:
        searchbooks = []
        for book in books:
            logger.debug('Looking for BookID %s ' % book['bookid'])
            searchbook = myDB.select('SELECT BookID, AuthorName, BookName from books WHERE BookID=? AND Status="Wanted"', [book['bookid']])
            for terms in searchbook:
                searchbooks.append(terms)

    for searchbook in searchbooks:
        bookid = searchbook[0]
        author = searchbook[1]
        book = searchbook[2]
        
        

        #dic = {'...':'', ' & ':' ', ' = ': ' ', '?':'', '$':'s', ' + ':' ', '"':'', ',':'', '*':''}

        #author = formatter.latinToAscii(formatter.replace_all(author, dic))
        #book = formatter.latinToAscii(formatter.replace_all(book, dic))
        
        author = MakeSearchTermWebSafe(author)
        book   = MakeSearchTermWebSafe(book)
        searchterm = author + ' ' + book
        searchlist.append({"bookid": bookid, "searchterm": searchterm, "author": author, "title":book })

    if not lazylibrarian.SAB_HOST and not lazylibrarian.BLACKHOLE:
        logger.info('No downloadmethod is set, use SABnzbd or blackhole')

    if not lazylibrarian.NEWZNAB and lazylibrarian.NZBMATRIX and lazylibrarian.UsenetCrawler :
        logger.info('No providers are set.')


    for book in searchlist:
        resultlist = []
        if lazylibrarian.NEWZNAB and not resultlist:
            logger.info('Searching NZB\'s at provider %s ...' % lazylibrarian.NEWZNAB_HOST)
            resultlist = providers.NewzNab(book)

        if lazylibrarian.NZBMATRIX and not resultlist:
            logger.info('Searching NZB at provider NZBMatrix ...')
            resultlist = providers.NZBMatrix(book)
            
        if lazylibrarian.USENETCRAWLER and not resultlist:
            logger.info('Searching NZB\'s at provider UsenetCrawler ...')
            resultlist = providers.UsenetCrawler(book)

        if not resultlist:
            logger.info("Search didn't have results. Adding book %s to queue." % book['searchterm'])

        else:
            for nzb in resultlist:
                bookid = nzb['bookid']
                nzbtitle = nzb['nzbtitle']
                nzburl = nzb['nzburl']
                nzbprov = nzb['nzbprov']

                controlValueDict = {"NZBurl": nzburl}
                newValueDict = {
                    "NZBprov": nzbprov,
                    "BookID": bookid,
                    "NZBdate": formatter.today(),
                    "NZBtitle": nzbtitle,
                    "Status": "Skipped"
                    }
                myDB.upsert("wanted", newValueDict, controlValueDict)

                snatchedbooks = myDB.action('SELECT * from books WHERE BookID=? and Status="Snatched"', [bookid]).fetchone()
                if not snatchedbooks:
                    snatch = DownloadMethod(bookid, nzbprov, nzbtitle, nzburl)
                time.sleep(1)

def DownloadMethod(bookid=None, nzbprov=None, nzbtitle=None, nzburl=None):

    myDB = database.DBConnection()

    if lazylibrarian.SAB_HOST and not lazylibrarian.BLACKHOLE:
        download = sabnzbd.SABnzbd(nzbtitle, nzburl)

    elif lazylibrarian.BLACKHOLE:

        try:
            nzbfile = urllib2.urlopen(nzburl, timeout=30).read()

        except urllib2.URLError, e:
            logger.warn('Error fetching nzb from url: ' + nzburl + ' %s' % e)

        nzbname = str.replace(nzbtitle, ' ', '_') + '.nzb'
        nzbpath = os.path.join(lazylibrarian.BLACKHOLEDIR, nzbname)

        try:
            f = open(nzbpath, 'w')
            f.write(nzbfile)
            f.close()
            logger.info('NZB file saved to: ' + nzbpath)
            download = True
        except Exception, e:
            logger.error('%s not writable, NZB not saved. Error: %s' % (nzbpath, e))
            download = False

    else:
        logger.error('No downloadmethod is enabled, check config.')
        return False

    if download:
        logger.info(u'Downloaded nzbfile @ <a href="%s">%s</a>' % (nzburl, lazylibrarian.NEWZNAB_HOST))
        myDB.action('UPDATE books SET status = "Snatched" WHERE BookID=?', [bookid])
        myDB.action('UPDATE wanted SET status = "Snatched" WHERE NZBurl=?', [nzburl])
    else:
        logger.error(u'Failed to download nzb @ <a href="%s">%s</a>' % (nzburl, lazylibrarian.NEWZNAB_HOST))
        myDB.action('UPDATE wanted SET status = "Failed" WHERE NZBurl=?', [nzburl])



def MakeSearchTermWebSafe(insearchterm=None):

        dic = {'...':'', ' & ':' ', ' = ': ' ', '?':'', '$':'s', ' + ':' ', '"':'', ',':'', '*':''}

        searchterm = formatter.latinToAscii(formatter.replace_all(insearchterm, dic))

        searchterm = re.sub('[\.\-\/]', ' ', searchterm).encode('utf-8')
        
        logger.debug("Converting Search Term [%s] to Web Safe Search Term [%s]" % (insearchterm, searchterm))
        
        return searchterm
 

