import time, threading, urllib, urllib2, re

from xml.etree import ElementTree

import lazylibrarian

from lazylibrarian import logger, SimpleCache

def UsenetCrawler(book=None):


    HOST = lazylibrarian.USENETCRAWLER_HOST
    results = []
    
    print book.keys()
    
    logger.info('UsenetCrawler: Searching term [%s] for author [%s] and title [%s]' % (book['searchterm'], book['authorName'], book['bookName']))
    
    params = {
        "apikey": lazylibrarian.USENETCRAWLER_API,

        "t": "book",
        "title": book['bookName'],
        "author": book['authorName']
        }
	
	#sample request
	#http://www.usenet-crawler.com/api?apikey=7xxxxxxxxxxxxxyyyyyyyyyyyyyyzzz4&t=book&author=Daniel

    logger.debug("%s" % params)
	
    if not str(HOST)[:4] == "http":
        HOST = 'http://' + HOST
	
    URL = HOST + '/api?' + urllib.urlencode(params)
	
    logger.debug('UsenetCrawler: searching on [%s] ' % URL)
    
    data = None    
    try:
        data = ElementTree.parse(urllib2.urlopen(URL, timeout=30))
    except (urllib2.URLError, IOError, EOFError), e:
        logger.Error('Error fetching data from %s: %s' % (HOST, e))
        data = None

    if data:
        # to debug because of api
        logger.debug(u'Parsing results from <a href="%s">%s</a>' % (URL, HOST))
        rootxml = data.getroot()
        resultxml = rootxml.getiterator('item')
        nzbcount = 0
        for nzb in resultxml:
            try:
                nzbcount = nzbcount+1
                results.append({
                    'bookid': book['bookid'],
                    'nzbprov': "UsenetCrawler",
                    'nzbtitle': nzb[0].text,
                    'nzburl': nzb[2].text,
                    'nzbdate': nzb[4].text,
                    'nzbsize': nzb[10].attrib.get('size')
                    })
                    
                logger.debug('NZB Details BookID: [%s] NZBUrl [%s] NZBDate [%s] NZBSize [%s]' % (book['bookid'],nzb[2].text,nzb[4].text,nzb[10].attrib.get('size')))
              
            except IndexError:
                logger.info('No results')
        if nzbcount:
            logger.info('Found %s nzb for: %s' % (nzbcount, book['searchterm']))
        else:
            logger.info('UsenetCrawler returned 0 results for: ' + book['searchterm'])
                
    return results

def NewzNab(book=None, newznabNumber=None):

    if (newznabNumber == "1"):
        HOST = lazylibrarian.NEWZNAB_HOST
        logger.info('Searching for %s.' % book['searchterm'] + " at: " + lazylibrarian.NEWZNAB_HOST)
    if (newznabNumber == "2"):
        HOST = lazylibrarian.NEWZNAB_HOST2
        logger.info('Searching for %s.' % book['searchterm'] + " at: " + lazylibrarian.NEWZNAB_HOST2)

    results = []

    if lazylibrarian.EBOOK_TYPE == None:
        params = {
            "t": "book",
            "apikey": lazylibrarian.NEWZNAB_API,
            #"cat": 7020,
            "author": book['searchterm']
        }
    else:
        params = {
            "t": "search",
            "apikey": lazylibrarian.NEWZNAB_API,
            "cat": 7020,
            "q": book['searchterm'],
            "extended": 1,
        }

    if not str(HOST)[:4] == "http":
        HOST = 'http://' + HOST

    URL = HOST + '/api?' + urllib.urlencode(params)

    try :
        request = urllib2.Request(URL)
        request.add_header('User-Agent', 'lazylibrary/0.0 +https://github.com/herman-rogers/LazyLibrarian-1')
        opener = urllib2.build_opener(SimpleCache.CacheHandler(".ProviderCache"), SimpleCache.ThrottlingProcessor(5))
        resp = opener.open(request)

        try:
            data = ElementTree.parse(resp)
        except (urllib2.URLError, IOError, EOFError), e:
            logger.warn('Error fetching data from %s: %s' % (lazylibrarian.NEWZNAB_HOST, e))
            data = None

    except Exception, e:
        logger.error("Error 403 openning url")
        data = None

    if data:
        # to debug because of api
        logger.debug(u'Parsing results from <a href="%s">%s</a>' % (URL, lazylibrarian.NEWZNAB_HOST))
        rootxml = data.getroot()
        resultxml = rootxml.getiterator('item')
        nzbcount = 0
        for nzb in resultxml:
            try:
                nzbcount = nzbcount+1
                results.append({
                    'bookid': book['bookid'],
                    'nzbprov': "NewzNab",
                    'nzbtitle': nzb[0].text,
                    'nzburl': nzb[2].text,
                    'nzbdate': nzb[4].text,
                    'nzbsize': nzb[7].attrib.get('length')
                    })
            except IndexError:
                logger.debug('No results')
        if nzbcount:
            logger.debug('Found %s nzb for: %s' % (nzbcount, book['searchterm']))
        else:
            logger.info(u'Newznab returned 0 results for: ' + book['searchterm'] + '. Adding book to queue.')
    return results
