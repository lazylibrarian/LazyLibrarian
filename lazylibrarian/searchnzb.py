import time, threading, urllib, urllib2, os, re

from xml.etree import ElementTree
from xml.etree.ElementTree import Element, SubElement

import lazylibrarian

from lazylibrarian import logger, database, formatter
from lazylibrarian.providers import NZBProviders
from lazylibrarian.downloaders import DownloadInstruct

def searchbook(bookid=None, nzblist=None):

    with threading.Lock():
        myDB = database.DBConnection()

        searchbooks = myDB.select('SELECT AuthorName, BookName from books WHERE BookID=?', [bookid])

        for searchbook in searchbooks:

            author = searchbook[0]
            book = searchbook[1]

            dic = {
                '...':'',
                ' & ':' ',
                 ' = ': ' ',
                 '?':'',
                 '$':'s',
                 ' + ':' ',
                 '"':'',
                 ',':'',
                 '*':''
                 }

            author = formatter.latinToAscii(formatter.replace_all(author, dic))
            book = formatter.latinToAscii(formatter.replace_all(book, dic))

            searchterm = author + ' ' + book
            searchterm = re.sub('[\.\-\/]', ' ', searchterm).encode('utf-8')

            logger.info('Searching for: %s - %s ' % (author, book))

            if lazylibrarian.NEWZNAB:
                logger.info('Searching NZB at provider %s ...' % lazylibrarian.NEWZNAB_HOST)
                NP = NZBProviders()
                nzbresult = NP.NewzNab(bookid, searchterm)

    ## FUTURE-CODE
    #        if not nzblist:
    #            if lazylibrarian.NEWZBIN:
    #                logger.info('Searching NZB at provider %s ...' % lazylibrarian.NEWZBIN)
    #                Newzbin(searchterm)

    #        if not nzblist:
    #            if lazylibrarian.NZBMATRIX:
    #                logger.info('Searching NZB at provider %s ...' % lazylibrarian.NZBMATRIX)
    #                Newzbin(searchterm)

    #        if not nzblist:
    #            if lazylibrarian.NZBSORG:
    #                logger.info('Searching NZB at provider %s ...' % lazylibrarian.NZBSORG)

            if not nzbresult:
                logger.info("Search didn't have results. Adding book %s - %s to queue." % (author, book))

            else:
                logger.info("Adding results to database ...")

                myDB = database.DBConnection()

                # update bookstable
                controlValueDict = {"BookID": bookid}
                newValueDict = {"Status":"Pending"}
                myDB.upsert("books", newValueDict, controlValueDict)

                nzbcount = 0
                for nzb in nzbresult['nzbs']:
                    # update wantedtable
                    nzbcount = nzbcount+1
                    controlValueDict = {"BookID": bookid}
                    newValueDict = {
                        "AuthorName": author,
                        "BookName": book,
                        "JobName": nzb['jobname'],
                        "ProvLink": nzb['provlink'],
                        "NZBLink": nzb['nzblink'],
                        "PubDate": nzb['pubdate'],
                        "FileSize": nzb['filesize'],
                        "Status": "Pending"
                        }

                    myDB.upsert("wanted", newValueDict, controlValueDict)

                logger.info('Found %s nzbfiles. Preparing nzb for download' % nzbcount)
                DI = DownloadInstruct()
                DI.DownloadMethod(bookid)








