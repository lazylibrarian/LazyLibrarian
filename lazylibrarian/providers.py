#  This file is part of Lazylibrarian.
#
#  Lazylibrarian is free software':'you can redistribute it and/or modify
#  it under the terms of the GNU General Public License as published by
#  the Free Software Foundation, either version 3 of the License, or
#  (at your option) any later version.
#
#  Lazylibrarian is distributed in the hope that it will be useful,
#  but WITHOUT ANY WARRANTY; without even the implied warranty of
#  MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
#  GNU General Public License for more details.
#
#  You should have received a copy of the GNU General Public License
#  along with Lazylibrarian.  If not, see <http://www.gnu.org/licenses/>.

import urllib
from xml.etree import ElementTree

import lazylibrarian
import lib.feedparser as feedparser
from lazylibrarian import logger
from lazylibrarian.cache import fetchURL
from lazylibrarian.formatter import age, today, plural, cleanName, unaccented
from lazylibrarian.torrentparser import KAT, TPB, ZOO, TDL, GEN, EXTRA, LIME


def get_searchterm(book, searchType):
    authorname = cleanName(book['authorName'])
    bookname = cleanName(book['bookName'])
    if searchType == "book" or searchType == "shortbook":
        while authorname[1] in '. ':  # strip any leading initials
            authorname = authorname[2:].strip()  # and leading whitespace
        # middle initials can't have a dot
        authorname = authorname.replace('. ', ' ')
        if bookname == authorname and book['bookSub']:
            # books like "Spike Milligan: Man of Letters"
            # where we split the title/subtitle on ':'
            bookname = cleanName(book['bookSub'])
        if bookname.startswith(authorname) and len(bookname) > len(authorname):
            # books like "Spike Milligan In his own words"
            # where we don't want to look for "Spike Milligan Spike Milligan In his own words"
            bookname = bookname[len(authorname) + 1:]
        bookname = bookname.strip()

        if searchType == "book":
            return authorname, bookname

        if searchType == "shortbook" and '(' in bookname:
            bookname = bookname.split('(')[0].strip()
            return authorname, bookname

    # any other searchType
    return authorname, bookname


def get_capabilities(provider):
    """
    query provider for caps if none loaded yet, or if config entry is too old and not set manually.
    """
    match = False
    if len(provider['UPDATED']) == 10:  # any stored values?
        match = True
        if (age(provider['UPDATED']) > lazylibrarian.CACHE_AGE) and not provider['MANUAL']:
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

        source_xml, success = fetchURL(URL)
        if success:
            data = ElementTree.fromstring(source_xml)
        else:
            logger.debug(u"Error getting xml from %s, %s" % (URL, source_xml))
            data = ''
        if len(data):
            logger.debug(u"Parsing xml for capabilities of %s" % URL)

            #
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
            #
            #
            #  set some defaults
            #
            provider['GENERALSEARCH'] = 'search'
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
                        bookcat = cat.attrib['id']  # keep main bookcat for later
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
                            if search:
                                if 'available' in search.attrib:
                                    if search.attrib['available'] == 'yes':
                                        provider['BOOKSEARCH'] = 'book'
                                    else:
                                        provider['BOOKSEARCH'] = ''
                        subcats = cat.getiterator('subcat')
                        for subcat in subcats:
                            if 'ebook' in subcat.attrib['name'].lower():
                                provider['BOOKCAT'] = "%s,%s" % (provider['BOOKCAT'], subcat.attrib['id'])
                            if 'magazines' in subcat.attrib['name'].lower() or 'mags' in subcat.attrib['name'].lower():
                                if provider['MAGCAT']:
                                    provider['MAGCAT'] = "%s,%s" % (provider['MAGCAT'], subcat.attrib['id'])
                                else:
                                    provider['MAGCAT'] = subcat.attrib['id']
                        # if no specific magazine subcategory, use books
                        if not provider['MAGCAT']:
                            provider['MAGCAT'] = bookcat
            logger.debug("Categories: Books %s : Mags %s" % (provider['BOOKCAT'], provider['MAGCAT']))
            provider['UPDATED'] = today()
            lazylibrarian.config_write()
        else:
            logger.warn(u"Unable to get capabilities for %s: No data returned" % URL)
    return provider


def IterateOverNewzNabSites(book=None, searchType=None):
    """
    Purpose of this function is to read the config file, and loop through all active NewsNab+
    sites and return the compiled results list from all sites back to the caller
    We get called with book[] and searchType of "book", "mag", "general" etc
    """

    resultslist = []
    providers = 0

    for provider in lazylibrarian.NEWZNAB_PROV:
        if provider['ENABLED']:
            provider = get_capabilities(provider)
            providers += 1
            logger.debug('[IterateOverNewzNabSites] - %s' % provider['HOST'])
            resultslist += NewzNabPlus(book, provider, searchType, "nzb")

    for provider in lazylibrarian.TORZNAB_PROV:
        if provider['ENABLED']:
            provider = get_capabilities(provider)
            providers += 1
            logger.debug('[IterateOverTorzNabSites] - %s' % provider['HOST'])
            resultslist += NewzNabPlus(book, provider,
                                       searchType, "torznab")
    return resultslist, providers


def IterateOverTorrentSites(book=None, searchType=None):

    resultslist = []
    providers = 0
    if searchType != 'mag':
        authorname, bookname = get_searchterm(book, searchType)
        book['searchterm'] = authorname + ' ' + bookname

    if lazylibrarian.KAT:
        providers += 1
        logger.debug('[IterateOverTorrentSites] - %s' % lazylibrarian.KAT_HOST)
        resultslist += KAT(book)
    if lazylibrarian.TPB:
        providers += 1
        logger.debug('[IterateOverTorrentSites] - %s' % lazylibrarian.TPB_HOST)
        resultslist += TPB(book)
    if lazylibrarian.ZOO:
        providers += 1
        logger.debug('[IterateOverTorrentSites] - %s' % lazylibrarian.ZOO_HOST)
        resultslist += ZOO(book)
    if lazylibrarian.EXTRA:
        providers += 1
        logger.debug('[IterateOverTorrentSites] - %s' % lazylibrarian.EXTRA_HOST)
        resultslist += EXTRA(book)
    if lazylibrarian.TDL:
        providers += 1
        logger.debug('[IterateOverTorrentSites] - %s' % lazylibrarian.TDL_HOST)
        resultslist += TDL(book)
    if lazylibrarian.GEN:
        providers += 1
        logger.debug('[IterateOverTorrentSites] - %s' % lazylibrarian.GEN_HOST)
        resultslist += GEN(book)
    if lazylibrarian.LIME:
        providers += 1
        logger.debug('[IterateOverTorrentSites] - %s' % lazylibrarian.LIME_HOST)
        resultslist += LIME(book)

    return resultslist, providers


def IterateOverRSSSites():

    resultslist = []
    providers = 0
    for provider in lazylibrarian.RSS_PROV:
        if provider['ENABLED']:
            providers += 1
            logger.debug('[IterateOverRSSSites] - %s' % provider['HOST'])
            resultslist += RSS(provider['HOST'], provider['NAME'])
    return resultslist, providers


def RSS(host=None, feednr=None):
    """
    Generic RSS query function, just return all the results from all the RSS feeds in a list
    """
    results = []

    if not str(host)[:4] == "http":
        host = 'http://' + host

    URL = host

    result, success = fetchURL(URL)
    if success:
        data = feedparser.parse(result)
    else:
        logger.error('Error fetching data from %s: %s' % (host, result))
        data = None

    if data:
        # to debug because of api
        logger.debug(u'Parsing results from %s' % URL)
        provider = data['feed']['link']
        logger.debug("RSS %s returned %i result%s" % (provider, len(data.entries), plural(len(data.entries))))
        for post in data.entries:
            title = None
            magnet = None
            size = None
            torrent = None
            nzb = None
            url = None
            tortype = 'torrent'

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
                        nzb = f['href']
                        break

            if 'torrent_magneturi' in post:
                magnet = post.torrent_magneturi

            if torrent:
                url = torrent
                tortype = 'torrent'

            if magnet:
                if not url or (url and lazylibrarian.PREFER_MAGNET):
                    url = magnet
                    tortype = 'magnet'

            if nzb:     # prefer nzb over torrent/magnet
                url = nzb
                tortype = 'nzb'

            if not url:
                if 'link' in post:
                    url = post.link

            tor_date = 'Fri, 01 Jan 1970 00:00:00 +0100'
            if 'newznab_attr' in post:
                if post.newznab_attr['name'] == 'usenetdate':
                    tor_date = post.newznab_attr['value']

            if not size:
                size = 1000
            if title and url:
                results.append({
                    'tor_prov': provider,
                    'tor_title': title,
                    'tor_url': url,
                    'tor_size': str(size),
                    'tor_date': tor_date,
                    'tor_feed': feednr,
                    'tor_type': tortype
                })

    else:
        logger.debug('No data returned from %s' % host)
    return results


def NewzNabPlus(book=None, provider=None, searchType=None, searchMode=None):
    """
    Generic NewzNabplus query function
    takes in host+key+type and returns the result set regardless of who
    based on site running NewzNab+
    ref http://usenetreviewz.com/nzb-sites/
    """

    host = provider['HOST']
    api_key = provider['API']
    logger.debug('[NewzNabPlus] searchType [%s] with Host [%s] mode [%s] using api [%s] for item [%s]' % (
                 searchType, host, searchMode, api_key, str(book)))

    results = []

    params = ReturnSearchTypeStructure(provider, api_key, book, searchType, searchMode)

    if params:
        if not str(host)[:4] == "http":
            host = 'http://' + host
        URL = host + '/api?' + urllib.urlencode(params)

        rootxml = None
        logger.debug("[NewzNabPlus] URL = %s" % URL)
        result, success = fetchURL(URL)
        if success:
            try:
                rootxml = ElementTree.fromstring(result)
            except Exception as e:
                logger.error('Error parsing data from %s: %s' % (host, str(e)))
                rootxml = None
        else:
            if not result or result == "''":
                result = "Got an empty response"
            logger.error('Error reading data from %s: %s' % (host, result))

        if rootxml is not None:
            # to debug because of api
            logger.debug(u'Parsing results from <a href="%s">%s</a>' % (URL, host))

            if rootxml.tag == 'error':
                errormsg = rootxml.get('description', default='unknown error')
                logger.error(u"%s - %s" % (host, errormsg))
                if provider['BOOKSEARCH']:  # maybe the host doesn't support it
                    errorlist = ['no such function', 'unknown parameter', 'unknown function', 'incorrect parameter']
                    match = False
                    for item in errorlist:
                        if item in errormsg.lower() and provider['BOOKSEARCH'].lower() in errormsg.lower():
                            match = True
                    if match:
                        count = 0
                        while count < len(lazylibrarian.NEWZNAB_PROV):
                            if lazylibrarian.NEWZNAB_PROV[count]['HOST'] == provider['HOST']:
                                if str(provider['MANUAL']) == 'False':
                                    logger.error(
                                        "Disabled booksearch=%s for %s" %
                                        (provider['BOOKSEARCH'], provider['HOST']))
                                    lazylibrarian.NEWZNAB_PROV[count]['BOOKSEARCH'] = ""
                                    lazylibrarian.config_write()
                                else:
                                    logger.error(
                                        "Unable to disable booksearch for %s [MANUAL=%s]" %
                                        (provider['HOST'], provider['MANUAL']))
                            count += 1
            else:
                resultxml = rootxml.getiterator('item')
                nzbcount = 0
                for nzb in resultxml:
                    try:
                        nzbcount += 1
                        results.append(ReturnResultsFieldsBySearchType(book, nzb, host, searchMode))
                    except IndexError:
                        logger.debug('No results from %s for %s' % (host, book['searchterm']))
                logger.debug(u'Found %s nzb at %s for: %s' % (nzbcount, host, book['searchterm']))
        else:
            logger.debug('No data returned from %s for %s' % (host, book['searchterm']))
    return results


def ReturnSearchTypeStructure(provider, api_key, book, searchType, searchMode):

    params = None
    if searchType == "book":
        authorname, bookname = get_searchterm(book, searchType)
        if provider['BOOKSEARCH'] and provider['BOOKCAT']:  # if specific booksearch, use it
            params = {
                "t": provider['BOOKSEARCH'],
                "apikey": api_key,
                "title": bookname,
                "author": authorname,
                "cat": provider['BOOKCAT']
            }
        elif provider['GENERALSEARCH'] and provider['BOOKCAT']:  # if not, try general search
            params = {
                "t": provider['GENERALSEARCH'],
                "apikey": api_key,
                "q": authorname + ' ' + bookname,
                "cat": provider['BOOKCAT']
            }
    elif searchType == "shortbook":
        authorname, bookname = get_searchterm(book, searchType)
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
    elif searchType == "mag":
        if provider['MAGSEARCH'] and provider['MAGCAT']:  # if specific magsearch, use it
            params = {
                "t": provider['MAGSEARCH'],
                "apikey": api_key,
                "cat": provider['MAGCAT'],
                "q": unaccented(book['searchterm']),
                "extended": provider['EXTENDED'],
            }
        elif provider['GENERALSEARCH'] and provider['MAGCAT']:
            params = {
                "t": provider['GENERALSEARCH'],
                "apikey": api_key,
                "cat": provider['MAGCAT'],
                "q": unaccented(book['searchterm']),
                "extended": provider['EXTENDED'],
            }
    else:
        if provider['GENERALSEARCH']:
            params = {
                "t": provider['GENERALSEARCH'],
                "apikey": api_key,
                # this is a general search
                "q": unaccented(book['searchterm']),
                "extended": provider['EXTENDED'],
            }
    if params:
        logger.debug('[NewzNabPlus] - %s Search parameters set to %s' % (searchMode, str(params)))
    else:
        logger.debug('[NewzNabPlus] - %s No matching search parameters' % searchMode)

    return params


def ReturnResultsFieldsBySearchType(book=None, nzbdetails=None, host=None, searchMode=None):
    """
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
    # -------------------------------TORZNAB RETURN DATA-- book ---------------------------------------------
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
    """

    nzbtitle = ''
    nzbdate = ''
    nzburl = ''
    nzbsize = 0

    n = 0
    while n < len(nzbdetails):
        tag = str(nzbdetails[n].tag).lower()

        if tag == 'title':
            nzbtitle = nzbdetails[n].text
        elif tag == 'size':
            nzbsize = nzbdetails[n].text
        elif tag == 'pubdate':
            nzbdate = nzbdetails[n].text
        elif tag == 'link':
            if not nzburl or (nzburl and not lazylibrarian.PREFER_MAGNET):
                nzburl = nzbdetails[n].text
        elif nzbdetails[n].attrib.get('name') == 'magneturl':
            nzburl = nzbdetails[n].attrib.get('value')
        elif nzbdetails[n].attrib.get('name') == 'size':
            nzbsize = nzbdetails[n].attrib.get('value')
        n += 1

    resultFields = {
        'bookid': book['bookid'],
        'nzbprov': host,
        'nzbtitle': nzbtitle,
        'nzburl': nzburl,
        'nzbdate': nzbdate,
        'nzbsize': nzbsize,
        'nzbmode': searchMode
        }

    logger.debug('[NewzNabPlus] - result fields from NZB are ' + str(resultFields))
    return resultFields
