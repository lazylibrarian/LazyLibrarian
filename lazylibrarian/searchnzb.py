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
            for nzb in resultlist:
                nzbtitle = nzb['nzbtitle']
                nzburl = nzb['nzburl']
                nzbprov = nzb['nzbprov']

                #save nzb's to database for later use
                snatchbooks = myDB.select('SELECT * from wanted WHERE BookID=? and Status="Snatched"', [bookid])
                if snatchbooks:
                    "Book with BookID %s allready snatched, skipped this NZB."
                    controlValueDict = {"BookID": bookid}
                    newValueDict = {
                        "NZBprov": nzbprov,
                        "NZBdate": formatter.today(),
                        "NZBurl": nzburl,
                        "NZBtitle": nzbtitle,
                        "Status": "Skipped"
                        }
                    myDB.upsert("wanted", newValueDict, controlValueDict)

                else:
                    snatch = DownloadMethod(bookid, nzbprov, nzbtitle, nzburl)


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

    if download:
        myDB.action('UPDATE books SET status = "Snatched" WHERE BookID=?', [bookid])

        controlValueDict = {"BookID": bookid}
        newValueDict = {
            "NZBprov": nzbprov,
            "NZBdate": formatter.now(),
            "NZBurl": nzburl,
            "NZBtitle": nzbtitle,
            "Status": "Snatched"
            }

        myDB.upsert("wanted", newValueDict, controlValueDict)

    else:
        controlValueDict = {"BookID": bookid}
        newValueDict = {
            "NZBprov": nzbprov,
            "NZBdate": formatter.now(),
            "NZBurl": nzburl,
            "NZBtitle": nzbtitle,
            "Status": "Failed"
            }

        myDB.upsert("wanted", newValueDict, controlValueDict)

    return download






