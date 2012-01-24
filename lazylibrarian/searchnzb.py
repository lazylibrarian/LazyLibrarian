import time, threading, urllib, urllib2, os, re

from xml.etree import ElementTree
from xml.etree.ElementTree import Element, SubElement

import lazylibrarian

from lazylibrarian import logger, database, formatter


def searchbook(bookid=None):

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
            logger.info('Searching NZB at provider %s ...' % lazylibrarian.NEWZNAB)
            Newznab(searchterm)

def Newznab(searchterm=None):

    HOST = lazylibrarian.NEWZNAB_HOST

    params = {
        "t": "search",
        "apikey": lazylibrarian.NEWZNAB_API,
        "cat": 7020,
        "q": searchterm
        }

    if not str(HOST)[:4] == "http":
        HOST = 'http://' + HOST

    URL = HOST + '/api?' + urllib.urlencode(params)

    # to debug because of api
    logger.debug(u'Parsing results from <a href="%s">%s</a>' % (URL, lazylibrarian.NEWZNAB_HOST))

    try:
        sourcexml = ElementTree.parse(urllib2.urlopen(URL, timeout=20))
        url_error = False
    except urllib2.URLError, e:
        logger.warn('Error fetching data from %s: %s' % (lazylibrarian.NEWZNAB_HOST, e))
        url_error = True

    if not url_error:
        rootxml = sourcexml.getroot()
        resultxml = rootxml.iter('item')

        if not len(rootxml):
            nzblist = []
        else:
            nzblist = []

            for item in resultxml:
                if item is None:
                    logger.info('No nzbs found with : %s' % searchterm)
                else:
                    nzblist.append({
                        'title': item[0].text,
                        'guid': item[1].text,
                        'link': item[2].text,
                        'comments': item[3].text,
                        'pubdate': item[4].text,
                        'category': item[5].text,
                        'description': item[6].text,
                        'filesize': item[7].attrib.get('length')
                        })





