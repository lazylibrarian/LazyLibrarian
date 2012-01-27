import time, threading, urllib, urllib2, os, re

from xml.etree import ElementTree
from xml.etree.ElementTree import Element, SubElement

import lazylibrarian

from lazylibrarian import logger, database, formatter, providers, sabnzbd

def searchbook(bookid=None):

    myDB = database.DBConnection()

    if bookid:
        searchbooks = myDB.select('SELECT AuthorName, BookName from books WHERE BookID=? AND Status="Wanted"', [bookid])
    else:
        searchbooks = myDB.select('SELECT AuthorName, Bookname from books WHERE Status="Wanted"')

    for searchbook in searchbooks:
        author = searchbook[0]
        book = searchbook[1]

        dic = {'...':'', ' & ':' ', ' = ': ' ', '?':'', '$':'s', ' + ':' ', '"':'', ',':'', '*':''}

        author = formatter.latinToAscii(formatter.replace_all(author, dic))
        book = formatter.latinToAscii(formatter.replace_all(book, dic))

        searchterm = author + ' ' + book
        searchterm = re.sub('[\.\-\/]', ' ', searchterm).encode('utf-8')

        resultlist = []

        if lazylibrarian.NEWZNAB:
            logger.info('Searching NZB at provider %s ...' % lazylibrarian.NEWZNAB_HOST)
            resultlist = providers.NewzNab(searchterm, resultlist)

# FUTURE-CODE
        if lazylibrarian.NEWZBIN:
            logger.info('Searching NZB at provider %s ...' % lazylibrarian.NEWZBIN)
            resultlist = providers.Newzbin(searchterm, resultlist)

        if lazylibrarian.NZBMATRIX:
            logger.info('Searching NZB at provider %s ...' % lazylibrarian.NZBMATRIX)
            resultlist = providers.NZBMatrix(searchterm, resultlist)


        if lazylibrarian.NZBSORG:
            logger.info('Searching NZB at provider %s ...' % lazylibrarian.NZBSORG)
            resultlist = providers.NZBsorg(searchterm, resultlist)

        if resultlist is None:
            logger.info("Search didn't have results. Adding book %s - %s to queue." % (author, book))

        else:
            nzbcount = 0
            for nzb in resultlist:
                # write checks here later
                    title = nzb['title']
                    nzburl = nzb['nzburl']
                    prvurl = nzb['prvurl']
                    pubdate = nzb['pubdate']
                    size = nzb['size']

                    download = sabnzbd.SABnzbd(title, nzburl)
                    if download is True:
                        break
                    else:
                        continue









