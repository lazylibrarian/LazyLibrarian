import urllib
import urllib2
import socket

from xml.etree import ElementTree

import lazylibrarian
from lazylibrarian import logger, formatter, database
import lazylibrarian.common as common

# new libraries to support torrents
import lib.feedparser as feedparser
import urlparse


def url_fix(s, charset='utf-8'):
    if isinstance(s, unicode):
        s = s.encode(charset, 'ignore')
    scheme, netloc, path, qs, anchor = urlparse.urlsplit(s)
    path = urllib.quote(path, '/%')
    qs = urllib.quote_plus(qs, ':&=')
    return urlparse.urlunsplit((scheme, netloc, path, qs, anchor))


def KAT(book=None):

    provider = "KAT"
    host = lazylibrarian.KAT_HOST
    if not str(host)[:4] == "http":
        host = 'http://' + host

    providerurl = url_fix(host + "/usearch/" + book['searchterm'])
    minimumseeders = int(lazylibrarian.NUMBEROFSEEDERS) - 1

    params = {
        "category": "books",
        "field": "seeders",
        "sorder": "desc",
        "rss": "1"
    }
    searchURL = providerurl + "/?%s" % urllib.urlencode(params)

    try:
        data = urllib2.urlopen(searchURL, timeout=90)
    except (urllib2.HTTPError, urllib2.URLError, socket.timeout) as e:
        # seems KAT returns 404 if no results, not really an error
        if not e.code == 404:
            logger.debug(searchURL)
            logger.debug('Error fetching data from %s: %s' % (provider, e))
        else:
            logger.debug(u"No results found from %s for %s" % (provider, book['searchterm']))
        data = False

    results = []

    if data:

        logger.debug(u'Parsing results from <a href="%s">KAT</a>' % searchURL)

        d = feedparser.parse(data)

        if not len(d.entries):
            logger.debug(u"No results found from %s for %s" % (provider, book['searchterm']))
            pass

        else:
            logger.debug(u"Found %i results from %s for %s, checking seeders" % (len(d.entries),
                         provider, book['searchterm']))
            for item in d.entries:
                try:
                    # rightformat = True
                    title = item['title']

                    seeders = item['torrent_seeds']
                    url = item['links'][1]['href']
                    size = int(item['links'][1]['length'])

                    if minimumseeders < int(seeders):
                        results.append({
                            'bookid': book['bookid'],
                            'tor_prov': "KAT",
                            'tor_title': title,
                            'tor_url': url,
                            'tor_size': str(size),
                        })

                        logger.debug('Found %s. Size: %s' % (title, size))
                    else:
                        if int(seeders) == 0:
                            logger.debug('Found %s but no seeders' % title)
                        elif int(seeders) == 1:
                            logger.debug('Found %s but only one seeder' % title)
                        else:
                            logger.debug('Found %s but only %s seeders' % (title, int(seeders)))

                except Exception as e:
                    logger.error(u"An unknown error occurred in the KAT parser: %s" % e)

    logger.debug(u"Found %i results from %s for %s" % (len(results), provider, book['searchterm']))
    return results

def get_capabilities(provider):
    """
    query provider for caps if none loaded yet, or if config entry is too old and not set manually. 
    """                
    match = False
    if len(provider['UPDATED']) == 10: # any stored values?
        match = True
        if (formatter.age(provider['UPDATED']) > lazylibrarian.CACHE_AGE) and not provider['MANUAL']:
            logger.debug('Stored capabilities for %s are too old' % provider['HOST'])
            match = False

    if match:
        logger.debug('Using stored capabilities for %s' % provider['HOST'])
    else:
        host = provider['HOST']
        if not str(host)[:4] == "http":
            host = 'http://' + host
        URL = host + '/api?t=caps&apikey=' + provider['API']
        logger.debug('Requesting capabilities for %s' % URL)
        
        request = urllib2.Request(URL)
        if lazylibrarian.PROXY_HOST:
            request.set_proxy(lazylibrarian.PROXY_HOST, lazylibrarian.PROXY_TYPE)
        request.add_header('User-Agent', common.USER_AGENT)
        resp = ""
        try:
            resp = urllib2.urlopen(request, timeout=30)  # don't get stuck
        except (urllib2.HTTPError, urllib2.URLError, socket.timeout) as e:
            logger.debug("Error getting capabilities: %s" % e)
            resp = ""
        if resp:
            if str(resp.getcode()).startswith("2"):  # (200 OK etc)
                logger.debug(u"Got capabilities for %s" % request.get_full_url())
                try:
                    source_xml = resp.read()  # .decode('utf-8')
                    data = ElementTree.fromstring(source_xml)
                except:
                    logger.debug(u"Error getting xml from %s" % URL)
                    data = None
                if len(data):
                    logger.debug(u"Parsing xml for capabilities of %s" % URL)
                    
                    ############################################################################# 
                    # book search isn't mentioned in the caps xml returned by
                    # nzbplanet,jackett,oznzb,usenet-crawler, so we can't use it as a test
                    # but the newznab+ ones usually support t=book and categories in 7000 range
                    # whereas nZEDb ones don't support t=book and use categories in 8000 range
                    # also some providers give searchtype but no supportedparams, so we still
                    # can't tell what queries will be accepted
                    # also category names can be lowercase or Mixed, magazine subcat name isn't
                    # consistent, and subcat can be just subcat or category/subcat subcat > lang
                    # eg "Magazines" "Mags" or "Books/Magazines" "Mags > French" 
                    # Load all languages for now as we don't know which the user might want
                    #############################################################################
                    #
                    #  set some defaults
                    #
                    provider['GENERALSEARCH'] = ''
                    provider['EXTENDED'] = '1'
                    provider['BOOKCAT'] = ''
                    provider['MAGCAT'] = ''
                    provider['BOOKSEARCH'] = ''
                    provider['MAGSEARCH'] = ''
                    #
                    search = data.find('searching/search')
                    if search is not None:
                        if 'available' in search.attrib:
                            if search.attrib['available'] == 'yes': 
                                provider['GENERALSEARCH'] = 'search'    
                    categories = data.getiterator('category')
                    for cat in categories:
                        if 'name' in cat.attrib:
                            if cat.attrib['name'].lower() == 'books':
                                bookcat = cat.attrib['id'] # keep main bookcat for later
                                provider['BOOKCAT'] = bookcat
                                provider['MAGCAT'] = ''
                                if provider['BOOKCAT'] == '7000':
                                    # looks like newznab+, should support book-search
                                    provider['BOOKSEARCH'] = 'book'
                                    # but check in case
                                    search = data.find('searching/book-search')
                                    if search is not None:
                                        if 'available' in search.attrib:
                                            if search.attrib['available'] == 'yes': 
                                                provider['BOOKSEARCH'] = 'book'    
                                            else:
                                                provider['BOOKSEARCH'] = ''
                                else:
                                    # looks like nZEDb, probably no book-search
                                    provider['BOOKSEARCH'] = ''
                                    # but check in case
                                    search = data.find('searching/book-search')
                                    if search is not None:
                                        if 'available' in search.attrib:
                                            if search.attrib['available'] == 'yes': 
                                                provider['BOOKSEARCH'] = 'book'    
                                            else:
                                                provider['BOOKSEARCH'] = ''
                                subcats = cat.getiterator('subcat')
                                for subcat in subcats:
                                    if 'ebook' in subcat.attrib['name'].lower():
                                        provider['BOOKCAT'] = "%s,%s" % (provider['BOOKCAT'],subcat.attrib['id'])
                                    if  'magazines' in subcat.attrib['name'].lower() or 'mags' in subcat.attrib['name'].lower():
                                        if provider['MAGCAT']:
                                            provider['MAGCAT'] = "%s,%s" % (provider['MAGCAT'],subcat.attrib['id'])
                                        else:
                                            provider['MAGCAT'] = subcat.attrib['id']
                                # if no specific magazine subcategory, use books
                                if not provider['MAGCAT']:
                                    provider['MAGCAT'] = bookcat
                    logger.debug("Categories: Books %s : Mags %s" % (provider['BOOKCAT'], provider['MAGCAT']))
                    provider['UPDATED'] = formatter.today()
                else:
                    logger.warn(u"Unable to get capabilities for %s: No data returned" % URL)
            else:
                logger.warn(u"Unable to get capabilities for %s: Got %s" % (URL, resp.getcode()))
    return provider

def IterateOverNewzNabSites(book=None, searchType=None):
    """
    Purpose of this function is to read the config file, and loop through all active NewsNab+
    sites and return the compiled results list from all sites back to the caller
    We get called with book[] and searchType of "book", "mag", "general" etc
    """

    resultslist = []
    providers = 0
    myDB = database.DBConnection()
    
    for provider in lazylibrarian.NEWZNAB_PROV:
        if (provider['ENABLED']):
            provider = get_capabilities(provider)
            providers += 1
            logger.debug('[IterateOverNewzNabSites] - %s' % provider['HOST'])
            resultslist += NewzNabPlus(book, provider, searchType, "nzb")

    for provider in lazylibrarian.TORZNAB_PROV:
        if (provider['ENABLED']):
            provider = get_capabilities(provider)
            providers += 1
            logger.debug('[IterateOverTorzNabSites] - %s' % provider['HOST'])
            resultslist += NewzNabPlus(book, provider,
                                       searchType, "torznab")

    return resultslist, providers


def IterateOverTorrentSites(book=None, searchType=None):

    resultslist = []
    providers = 0
    if (lazylibrarian.KAT):
        providers += 1
        logger.debug('[IterateOverTorrentSites] - KAT')
        resultslist += KAT(book)

    return resultslist, providers


def IterateOverRSSSites(book=None, searchType=None):

    resultslist = []
    providers = 0
    for provider in lazylibrarian.RSS_PROV:
        if (provider['ENABLED']):
            providers += 1
            logger.debug('[IterateOverRSSSites] - %s' % provider['HOST'])
            resultslist += RSS(provider['HOST'], provider['NAME'])
    return resultslist, providers

#
# Generic RSS query function, just return all the results from all the RSS feeds in a list
#


def RSS(host=None, feednr=None):

    results = []

    if not str(host)[:4] == "http":
        host = 'http://' + host

    URL = host

    try:
        request = urllib2.Request(URL)
        if lazylibrarian.PROXY_HOST:
            request.set_proxy(lazylibrarian.PROXY_HOST, lazylibrarian.PROXY_TYPE)
        request.add_header('User-Agent', common.USER_AGENT)
        resp = urllib2.urlopen(request, timeout=90)
        try:
            data = feedparser.parse(resp)
        except (urllib2.URLError, socket.timeout, IOError, EOFError) as e:
            logger.error('Error fetching data from %s: %s' % (host, e))
            data = None

    except Exception as e:
        logger.error("Error opening url: %s" % e)
        data = None

    if data:
        # to debug because of api
        logger.debug(u'Parsing results from %s' % (URL))
        provider = data['feed']['link']
        logger.debug("RSS %s returned %i results" % (provider, len(data.entries)))
        for post in data.entries:
            title = None
            magnet = None
            size = None
            torrent = None
            nzb = None

            if 'title' in post:
                title = post.title
            if 'links' in post:
                for f in post.links:
                    if 'x-bittorrent' in f['type']:
                        size = f['length']
                        torrent = f['href']
                        break
                    if 'x-nzb' in f['type']:
                        size = f['length']
                        torrent = f['href']
                        break
            if 'torrent_magneturi' in post:
                magnet = post.torrent_magneturi

            if torrent:
                url = torrent
            if magnet:  # prefer magnet over torrent
                url = magnet
            if nzb:
                url = nzb

            if not size:
                size = 1000
            if title and url:
                results.append({
                    'tor_prov': provider,
                    'tor_title': title,
                    'tor_url': url,
                    'tor_size': str(size),
                    'tor_feed': feednr
                })

    else:
        logger.debug('No data returned from %s' % host)
    return results

#
# Generic NewzNabplus query function
# takes in host+key+type and returns the result set regardless of who
# based on site running NewzNab+
# ref http://usenetreviewz.com/nzb-sites/


def NewzNabPlus(book=None, provider=None, searchType=None, searchMode=None):

    host = provider['HOST']
    api_key = provider['API']
    logger.debug('[NewzNabPlus] searchType [%s] with Host [%s] mode [%s] using api [%s] for item [%s]' % (
                 searchType, host, searchMode, api_key, str(book)))

    results = []
    data = None

    params = ReturnSearchTypeStructure(provider, api_key, book, searchType, searchMode)

    if not str(host)[:4] == "http":
        host = 'http://' + host

    if params:
        URL = host + '/api?' + urllib.urlencode(params)

        try:
            request = urllib2.Request(URL)
            if lazylibrarian.PROXY_HOST:
                request.set_proxy(lazylibrarian.PROXY_HOST, lazylibrarian.PROXY_TYPE)
            request.add_header('User-Agent', common.USER_AGENT)
            resp = urllib2.urlopen(request, timeout=90)
            try:
                data = ElementTree.parse(resp)
            except (urllib2.URLError, socket.timeout, IOError, EOFError) as e:
                logger.error('Error fetching data from %s: %s' % (host, e))
                data = None
    
        except Exception as e:
            logger.error("Error 403 opening url %s, %s" % (URL, e))
            data = None
    
        if data:
            # to debug because of api
            logger.debug(u'Parsing results from <a href="%s">%s</a>' % (URL, host))
            rootxml = data.getroot()
    
            if rootxml.tag == 'error':
                errormsg = rootxml.get('description', default='unknown error')
                logger.error(u"%s - %s" % (host, errormsg))
            else:
                resultxml = rootxml.getiterator('item')
                nzbcount = 0
                for nzb in resultxml:
                    try:
                        nzbcount = nzbcount + 1
                        results.append(ReturnResultsFieldsBySearchType(book, nzb, searchType, host, searchMode))
                    except IndexError:
                        logger.debug('No results from %s for %s' % (host, book['searchterm']))
                logger.debug(u'Found %s nzb at %s for: %s' % (nzbcount, host, book['searchterm']))
        else:
            logger.debug('No data returned from %s for %s' % (host, book['searchterm']))
    return results


def ReturnSearchTypeStructure(provider, api_key, book, searchType, searchMode):

    params = None
    if searchType == "book":
        authorname = book['authorName']
        while authorname[1] in '. ':  # strip any leading initials
            authorname = authorname[2:].strip()  # and leading whitespace
        # middle initials can't have a dot
        authorname = authorname.replace('. ', ' ')
        authorname = common.removeDisallowedFilenameChars(authorname)
        bookname = common.removeDisallowedFilenameChars(book['bookName'])
        if provider['BOOKSEARCH'] and provider['BOOKCAT']:  # if specific booksearch, use it
            params = {
                "t": provider['BOOKSEARCH'],
                "apikey": api_key,
                "title": bookname,
                "author": authorname,
                "cat": provider['BOOKCAT']
            }
        elif provider['GENERALSEARCH'] and provider['BOOKCAT']: # if not, try general search
            params = {
                "t": provider['GENERALSEARCH'],
                "apikey": api_key,
                "q": authorname + ' ' + bookname,
                "cat": provider['BOOKCAT']
            }    
    elif searchType == "shortbook":
        authorname = book['authorName']
        while authorname[1] in '. ':  # strip any leading initials
            authorname = authorname[2:].strip()  # and leading whitespace
        # middle initials can't have a dot
        authorname = authorname.replace('. ', ' ')
        authorname = common.removeDisallowedFilenameChars(authorname)
        bookname = common.removeDisallowedFilenameChars(book['bookName'].split('(')[0]).strip()
        if provider['BOOKSEARCH'] and provider['BOOKCAT']:  # if specific booksearch, use it
            params = {
                "t": provider['BOOKSEARCH'],
                "apikey": api_key,
                "title": bookname,
                "author": authorname,
                "cat": provider['BOOKCAT']
            }
        elif provider['GENERALSEARCH'] and provider['BOOKCAT']:
            params = {
                "t": provider['GENERALSEARCH'],
                "apikey": api_key,
                "q": authorname + ' ' + bookname,
                "cat": provider['BOOKCAT']
            }            
    elif searchType == "author":
        authorname = book['authorName']
        while authorname[1] in '. ':  # strip any leading initials
            authorname = authorname[2:].strip()  # and leading whitespace
        # middle initials can't have a dot
        authorname = authorname.replace('. ', ' ')
        authorname = common.removeDisallowedFilenameChars(authorname)
        if provider['GENERALSEARCH']:
            params = {
                "t": provider['GENERALSEARCH'],
                "apikey": api_key,
                "q": authorname,
                "extended": provider['EXTENDED'],
            }
    elif searchType == "mag":
        if provider['MAGSEARCH'] and provider['MAGCAT']:  # if specific magsearch, use it
            params = {
                "t": provider['MAGSEARCH'],
                "apikey": api_key,
                "cat": provider['MAGCAT'],
                "q": book['searchterm'],
                "extended": provider['EXTENDED'],
            }
        elif provider['GENERALSEARCH'] and provider['MAGCAT']:
            params = {
               "t": provider['GENERALSEARCH'],
               "apikey": api_key,
               "cat": provider['MAGCAT'],
               "q": book['searchterm'],
               "extended": provider['EXTENDED'],
           }
    else:
        if provider['GENERALSEARCH']:
            params = {
                "t": provider['GENERALSEARCH'],
                "apikey": api_key,
                # this is a general search
                "q": book['searchterm'],
                "extended": provider['EXTENDED'],
            }
    if params:
        logger.debug('[NewzNabPlus] - %s Search parameters set to %s' % (searchMode, str(params)))
    else:
        logger.debug('[NewzNabPlus] - %s No matching search parameters' % searchMode)
            
    return params


def ReturnResultsFieldsBySearchType(book=None, nzbdetails=None, searchType=None, host=None, searchMode=None):
    # searchType has multiple query params for t=, which return different results sets.
    # books have a dedicated check, so will use that.
    # mags don't so will have more generic search term.
    # http://newznab.readthedocs.org/en/latest/misc/api/#predefined-categories
    # results when searching for t=book
    #    <item>
    #       <title>David Gemmell - Troy 03 - Fall of Kings</title>
    #       <guid isPermaLink="true">
    #           https://www.usenet-crawler.com/details/091c8c0e18ca34201899b91add52e8c0
    #       </guid>
    #       <link>
    #           https://www.usenet-crawler.com/getnzb/091c8c0e18ca34201899b91add52e8c0.nzb&i=155518&r=78c0509bc6bb91742ae0a0b6231e75e4
    #       </link>
    #       <comments>
    # https://www.usenet-crawler.com/details/091c8c0e18ca34201899b91add52e8c0#comments
    #       </comments>
    #       <pubDate>Fri, 11 Jan 2013 16:49:34 +0100</pubDate>
    #       <category>Books > Ebook</category>
    #       <description>David Gemmell - Troy 03 - Fall of Kings</description>
    #       <enclosure url="https://www.usenet-crawler.com/getnzb/091c8c0e18ca34201899b91add52e8c0.nzb&i=155518&r=78c0509bc6bb91742ae0a0b6231e75e4" length="4909563" type="application/x-nzb"/>
    #       <newznab:attr name="category" value="7000"/>
    #       <newznab:attr name="category" value="7020"/>
    #       <newznab:attr name="size" value="4909563"/>
    #       <newznab:attr name="guid" value="091c8c0e18ca34201899b91add52e8c0"/>
    #       </item>
    #
    # t=search results
    # <item>
    #   <title>David Gemmell - [Troy 03] - Fall of Kings</title>
    #   <guid isPermaLink="true">
    #       https://www.usenet-crawler.com/details/5d7394b2386683d079d8bd8f16652b18
    #   </guid>
    #   <link>
    #       https://www.usenet-crawler.com/getnzb/5d7394b2386683d079d8bd8f16652b18.nzb&i=155518&r=78c0509bc6bb91742ae0a0b6231e75e4
    #   </link>
    #   <comments>
    # https://www.usenet-crawler.com/details/5d7394b2386683d079d8bd8f16652b18#comments
    #   </comments>
    #   <pubDate>Mon, 27 May 2013 02:12:09 +0200</pubDate>
    #   <category>Books > Ebook</category>
    #   <description>David Gemmell - [Troy 03] - Fall of Kings</description>
    #   <enclosure url="https://www.usenet-crawler.com/getnzb/5d7394b2386683d079d8bd8f16652b18.nzb&i=155518&r=78c0509bc6bb91742ae0a0b6231e75e4" length="4909563" type="application/x-nzb"/>
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
    # </item>
    # -------------------------------TORZNAB RETURN DATA-- book ----------------------------------------------------------------------
    # <item>
    #  <title>Tom Holt - Blonde Bombshell (Dystop; SFX; Humour) ePUB+MOBI</title>
    #  <guid>https://getstrike.net/torrents/1FDBE6466738EED3C7FD915E1376BA0A63088D4D</guid>
    #  <comments>https://getstrike.net/torrents/1FDBE6466738EED3C7FD915E1376BA0A63088D4D</comments>
    #  <pubDate>Sun, 27 Sep 2015 23:10:56 +0200</pubDate>
    #  <size>24628</size>
    #  <description>Tom Holt - Blonde Bombshell (Dystop; SFX; Humour) ePUB+MOBI</description>
    #  <link>http://192.168.2.2:9117/dl/strike/pkl4u83iz41up73m4zsigqsd4zyie50r/aHR0cHM6Ly9nZXRzdHJpa2UubmV0L3RvcnJlbnRzL2FwaS9kb3dubG9hZC8xRkRCRTY0NjY3MzhFRUQzQzdGRDkxNUUxMzc2QkEwQTYzMDg4RDRELnRvcnJlbnQ1/t.torrent</link>
    #  <category>8000</category>
    #  <enclosure url="http://192.168.2.2:9117/dl/strike/pkl4u83iz41up73m4zsigqsd4zyie50r/aHR0cHM6Ly9nZXRzdHJpa2UubmV0L3RvcnJlbnRzL2FwaS9kb3dubG9hZC8xRkRCRTY0NjY3MzhFRUQzQzdGRDkxNUUxMzc2QkEwQTYzMDg4RDRELnRvcnJlbnQ1/t.torrent" length="24628" type="application/x-bittorrent" />
    #  <torznab:attr name="magneturl" value="magnet:?xt=urn:btih:1FDBE6466738EED3C7FD915E1376BA0A63088D4D&amp;dn=Tom+Holt+-+Blonde+Bombshell+(Dystop%3B+SFX%3B+Humour)+ePUB%2BMOBI&amp;tr=udp://open.demonii.com:1337&amp;tr=udp://tracker.coppersurfer.tk:6969&amp;tr=udp://tracker.leechers-paradise.org:6969&amp;tr=udp://exodus.desync.com:6969" />
    #  <torznab:attr name="seeders" value="1" />
    #  <torznab:attr name="peers" value="2" />
    #  <torznab:attr name="infohash" value="1FDBE6466738EED3C7FD915E1376BA0A63088D4D" />
    #  <torznab:attr name="minimumratio" value="1" />
    #  <torznab:attr name="minimumseedtime" value="172800" />
    # </item>
    # ---------------------------------------- magazine ----------------------------------------
    # <item>
    #  <title>Linux Format Issue 116 - KDE Issue</title>
    #  <guid>https://getstrike.net/torrents/f3fc8df4fdd850132072a435a7d112d6c9d77d16</guid>
    #  <comments>https://getstrike.net/torrents/f3fc8df4fdd850132072a435a7d112d6c9d77d16</comments>
    #  <pubDate>Wed, 04 Mar 2009 01:57:20 +0100</pubDate>
    #  <size>1309195</size>
    #  <description>Linux Format Issue 116 - KDE Issue</description>
    #  <link>http://192.168.2.2:9117/dl/strike/pkl4u83iz41up73m4zsigqsd4zyie50r/aHR0cHM6Ly9nZXRzdHJpa2UubmV0L3RvcnJlbnRzL2FwaS9kb3dubG9hZC9mM2ZjOGRmNGZkZDg1MDEzMjA3MmE0MzVhN2QxMTJkNmM5ZDc3ZDE2LnRvcnJlbnQ1/t.torrent</link>
    #  <enclosure url="http://192.168.2.2:9117/dl/strike/pkl4u83iz41up73m4zsigqsd4zyie50r/aHR0cHM6Ly9nZXRzdHJpa2UubmV0L3RvcnJlbnRzL2FwaS9kb3dubG9hZC9mM2ZjOGRmNGZkZDg1MDEzMjA3MmE0MzVhN2QxMTJkNmM5ZDc3ZDE2LnRvcnJlbnQ1/t.torrent" length="1309195" type="application/x-bittorrent" />
    # <torznab:attr name="magneturl" value="magnet:?xt=urn:btih:f3fc8df4fdd850132072a435a7d112d6c9d77d16&amp;dn=Linux+Format+Issue+116+-+KDE+Issue&amp;tr=udp://open.demonii.com:1337&amp;tr=udp://tracker.coppersurfer.tk:6969&amp;tr=udp://tracker.leechers-paradise.org:6969&amp;tr=udp://exodus.desync.com:6969" />
    # <torznab:attr name="seeders" value="2" />
    # <torznab:attr name="peers" value="3" />
    # <torznab:attr name="infohash" value="f3fc8df4fdd850132072a435a7d112d6c9d77d16" />
    # <torznab:attr name="minimumratio" value="1" />
    # <torznab:attr name="minimumseedtime" value="172800" />
    # </item>

    resultFields = None

    nzbtitle = nzbdetails[0].text  # title is currently the same field for all searchtypes
    # nzbtitle = common.removeDisallowedFilenameChars(nzbtitle)

    if searchMode == "torznab":  # For torznab results, either 8 or 9 contain a magnet link
        if nzbdetails[8].attrib.get('name') == 'magneturl':
            nzburl = nzbdetails[8].attrib.get('value')
        elif nzbdetails[9].attrib.get('name') == 'magneturl':
            nzburl = nzbdetails[9].attrib.get('value')
        else:
            nzburl = nzbdetails[6].text

        if searchType == "book":
            resultFields = {
                'bookid': book['bookid'],
                'nzbprov': host,
                'nzbtitle': nzbtitle,
                'nzburl': nzburl,
                'nzbdate': nzbdetails[3].text,
                'nzbsize': nzbdetails[4].text,
                'nzbmode': searchMode
            }
        elif searchType == "mag":
            resultFields = {
                'bookid': book['bookid'],
                'nzbprov': host,
                'nzbtitle': nzbtitle,
                'nzburl': nzburl,
                'nzbdate': nzbdetails[3].text,
                'nzbsize': nzbdetails[4].text,
                'nzbmode': searchMode
            }
        else:
            resultFields = {
                'bookid': book['bookid'],
                'nzbprov': host,
                'nzbtitle': nzbtitle,
                'nzburl': nzburl,
                'nzbdate': nzbdetails[3].text,
                'nzbsize': nzbdetails[4].text,
                'nzbmode': searchMode
            }
    else:
        if searchType == "book":
            # for nzb books, 9 or 10 contain size
            if nzbdetails[10].attrib.get('name') == 'size':
                nzbsize = nzbdetails[10].attrib.get('value')
            elif nzbdetails[9].attrib.get('name') == 'size':
                nzbsize = nzbdetails[9].attrib.get('value')
            else:
                nzbsize = 0
            resultFields = {
                'bookid': book['bookid'],
                'nzbprov': host,
                'nzbtitle': nzbtitle,
                'nzburl': nzbdetails[2].text,
                'nzbdate': nzbdetails[4].text,
                'nzbsize': nzbsize,
                'nzbmode': searchMode
            }
        elif searchType == "mag":
            resultFields = {
                'bookid': book['bookid'],
                'nzbprov': host,
                'nzbtitle': nzbtitle,
                'nzburl': nzbdetails[2].text,
                'nzbdate': nzbdetails[4].text,
                'nzbsize': nzbdetails[7].attrib.get('length'),
                'nzbmode': searchMode
            }
        else:
            resultFields = {
                'bookid': book['bookid'],
                'nzbprov': host,
                'nzbtitle': nzbtitle,
                'nzburl': nzbdetails[2].text,
                'nzbdate': nzbdetails[4].text,
                'nzbsize': nzbdetails[7].attrib.get('length'),
                'nzbmode': searchMode
            }

    logger.debug('[NewzNabPlus] - result fields from NZB are ' + str(resultFields))
    return resultFields
