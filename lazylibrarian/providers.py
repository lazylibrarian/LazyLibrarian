import time, threading, urllib, urllib2, re

from xml.etree import ElementTree

import lazylibrarian

from lazylibrarian import logger, SimpleCache

def UsenetCrawler(book=None, searchType=None):


    results = []
    
    #print book.keys()
    
    results = NewzNabPlus(book, lazylibrarian.USENETCRAWLER_HOST, lazylibrarian.USENETCRAWLER_API, searchType)
    return results
    
def OLDUsenetCrawler(book=None):


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

#deprecated once update searchmag.py
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

#
#Purpose of this function is to read the config file, and loop through all active NewsNab+
#sites and return the compiled results list from all sites back to the caller
def IterateOverNewzNabSites(book=None, searchType=None):

    resultslist = []
    
    if (lazylibrarian.NEWZNAB):
        logger.debug('[IterateOverNewzNabSites] - NewzNab1')
        resultslist += NewzNabPlus(book, lazylibrarian.NEWZNAB_HOST, 
                                    lazylibrarian.NEWZNAB_API,
                                    searchType)

    if (lazylibrarian.NEWZNAB2):
        logger.debug('[IterateOverNewzNabSites] - NewzNab2')
        resultslist += NewzNabPlus(book, lazylibrarian.NEWZNAB_HOST2, 
                                    lazylibrarian.NEWZNAB_API2,
                                    searchType)
                                    
    if (lazylibrarian.USENETCRAWLER):
        logger.debug('[IterateOverNewzNabSites] - USenetCrawler')
        resultslist += NewzNabPlus(book, lazylibrarian.USENETCRAWLER_HOST,
                                    lazylibrarian.USENETCRAWLER_API,
                                    searchType)
    return resultslist

#
#Generic NewzNabplus query function
#takes in host+key+type and returns the result set regardless of who
#based on site running NewzNab+
#ref http://usenetreviewz.com/nzb-sites/
def NewzNabPlus(book=None, host=None, api_key=None, searchType=None):


    #logger.info('[NewzNabPlus] Searching term [%s] for author [%s] and title [%s] on host [%s] for a [%s] item' % (book['searchterm'], book['authorName'], book['bookName'], host, searchType))
    logger.info('[NewzNabPlus] searchType [%s] with Host [%s] using api [%s] for item [%s]'%(searchType, host, api_key,str(book)))
    
    
    results = []  
    params = ReturnSearchTypeStructure(api_key, book, searchType)

    if not str(host)[:4] == "http":
        host = 'http://' + host

    URL = host + '/api?' + urllib.urlencode(params)

    try :
        request = urllib2.Request(URL)
        request.add_header('User-Agent', 'lazylibrary/0.0 +https://github.com/herman-rogers/LazyLibrarian-1')
        opener = urllib2.build_opener(SimpleCache.CacheHandler(".ProviderCache"), SimpleCache.ThrottlingProcessor(5))
        resp = opener.open(request)

        try:
            data = ElementTree.parse(resp)
        except (urllib2.URLError, IOError, EOFError), e:
            logger.warn('Error fetching data from %s: %s' % (host, e))
            data = None

    except Exception, e:
        logger.error("Error 403 openning url")
        data = None

    if data:
        # to debug because of api
        logger.debug(u'Parsing results from <a href="%s">%s</a>' % (URL, host))
        rootxml = data.getroot()
        resultxml = rootxml.getiterator('item')
        nzbcount = 0
        for nzb in resultxml:
            try:
                nzbcount = nzbcount+1
                
                results.append(ReturnResultsFieldsBySearchType(book, nzb, searchType, host))
            except IndexError:
                logger.debug('No results')
        if nzbcount:
            logger.debug('Found %s nzb for: %s' % (nzbcount, book['searchterm']))
        else:
            logger.info(u'Newznab returned 0 results for: ' + book['searchterm'] + '. Adding book to queue.')
    return results
    
def ReturnSearchTypeStructure(api_key, book, searchType):
  
    params = None
    
    if searchType == "book":
        params = {
            "t": "book",
            "apikey": api_key,
            "title": book['bookName'],
            "author": book['authorName'],         
            "cat": 7020,                #7020=ebook
        }
    elif searchType == "mag":
        params = {
            "t": "search",
            "apikey": api_key,
            "cat": "7000,7010,7020",    #7000=Other,7010=Misc,7020 Ebook
            "q": book['searchterm'],
            "extended": 1,
        }
    else:
                params = {
            "t": "search",
            "apikey": api_key,
            #"cat": 7020,
            "q": book['searchterm'],
            "extended": 1,
        }        
        
    logger.debug('NewzNabPlus] - Search parameters set to '+str(params))

    return params


def ReturnResultsFieldsBySearchType(book=None, nzbdetails=None, searchType=None, host=None):
    #searchType has multiple query params for t=, which return different results sets. 
    #books have a dedicated check, so will use that.
    #mags don't so will have more generic search term.
    #http://newznab.readthedocs.org/en/latest/misc/api/#predefined-categories
    ### results when searching for t=book
    #    <item>
    #       <title>David Gemmell - Troy 03 - Fall of Kings</title>
    #       <guid isPermaLink="true">
    #           http://www.usenet-crawler.com/details/091c8c0e18ca34201899b91add52e8c0
    #       </guid>
    #       <link>
    #           http://www.usenet-crawler.com/getnzb/091c8c0e18ca34201899b91add52e8c0.nzb&i=155518&r=78c0509bc6bb91742ae0a0b6231e75e4
    #       </link>
    #       <comments>
    #           http://www.usenet-crawler.com/details/091c8c0e18ca34201899b91add52e8c0#comments
    #       </comments>
    #       <pubDate>Fri, 11 Jan 2013 16:49:34 +0100</pubDate>
    #       <category>Books > Ebook</category>
    #       <description>David Gemmell - Troy 03 - Fall of Kings</description>
    #       <enclosure url="http://www.usenet-crawler.com/getnzb/091c8c0e18ca34201899b91add52e8c0.nzb&i=155518&r=78c0509bc6bb91742ae0a0b6231e75e4" length="4909563" type="application/x-nzb"/>
    #       <newznab:attr name="category" value="7000"/>
    #       <newznab:attr name="category" value="7020"/>
    #       <newznab:attr name="size" value="4909563"/>
    #       <newznab:attr name="guid" value="091c8c0e18ca34201899b91add52e8c0"/>
    #       </item>
    ###
    ###t=search results
    #<item>
    #   <title>David Gemmell - [Troy 03] - Fall of Kings</title>
    #   <guid isPermaLink="true">
    #       http://www.usenet-crawler.com/details/5d7394b2386683d079d8bd8f16652b18
    #   </guid>
    #   <link>
    #       http://www.usenet-crawler.com/getnzb/5d7394b2386683d079d8bd8f16652b18.nzb&i=155518&r=78c0509bc6bb91742ae0a0b6231e75e4
    #   </link>
    #   <comments>
    #       http://www.usenet-crawler.com/details/5d7394b2386683d079d8bd8f16652b18#comments
    #   </comments>
    #   <pubDate>Mon, 27 May 2013 02:12:09 +0200</pubDate>
    #   <category>Books > Ebook</category>
    #   <description>David Gemmell - [Troy 03] - Fall of Kings</description>
    #   <enclosure url="http://www.usenet-crawler.com/getnzb/5d7394b2386683d079d8bd8f16652b18.nzb&i=155518&r=78c0509bc6bb91742ae0a0b6231e75e4" length="4909563" type="application/x-nzb"/>
    #   <newznab:attr name="category" value="7000"/>
    #   <newznab:attr name="category" value="7020"/>
    #   <newznab:attr name="size" value="4909563"/>
    #   <newznab:attr name="guid" value="5d7394b2386683d079d8bd8f16652b18"/>
    #   <newznab:attr name="files" value="2"/>
    #   <newznab:attr name="poster" value="nerdsproject@gmail.com (N.E.R.Ds)"/>
    #   <newznab:attr name="grabs" value="0"/>
    #   <newznab:attr name="comments" value="0"/>
    #   <newznab:attr name="password" value="0"/>
    #   <newznab:attr name="usenetdate" value="Fri, 11 Mar 2011 13:45:15 +0100"/>
    #   <newznab:attr name="group" value="alt.binaries.e-book.flood"/>
    #</item>    
    
    resultFields=None

    
    if searchType == "book":
        resultFields= {
                    'bookid': book['bookid'],
                    'nzbprov': host,
                    'nzbtitle': nzbdetails[0].text,
                    'nzburl': nzbdetails[2].text,
                    'nzbdate': nzbdetails[4].text,
                    'nzbsize': nzbdetails[10].attrib.get('size')
                    }
    elif searchType == "mag":
        resultFields = {
                    'bookid': book['bookid'],
                    'nzbprov': host,
                    'nzbtitle': nzbdetails[0].text,
                    'nzburl': nzbdetails[2].text,
                    'nzbdate': nzbdetails[4].text,
                    'nzbsize': nzbdetails[7].attrib.get('length')
                    }
    else:
        resultFields = {
                    'bookid': book['bookid'],
                    'nzbprov': host,
                    'nzbtitle': nzbdetails[0].text,
                    'nzburl': nzbdetails[2].text,
                    'nzbdate': nzbdetails[4].text,
                    'nzbsize': nzbdetails[7].attrib.get('length')
                    }
    
    logger.debug('[NewzNabPlus] - result fields from NZB are ' + str(resultFields))
    return resultFields
