import urllib
import urllib2
import socket
import lazylibrarian
from lazylibrarian import logger
from lazylibrarian.common import USER_AGENT
from lazylibrarian.formatter import plural
from lazylibrarian.cache import fetchURL
import lib.feedparser as feedparser
import urlparse


def findrows(lines, startrow, endrow):
    """ given an array of lines from a webpage, find the data table
        and return an array of start_line,end_line for each row in the table
        using startrow and endrow to identify start and end of each row
    """
    finish = len(lines)
    current = 0
    rows = []
    row = []

    # pick all the table rows out of the results page
    while current < finish:
        line = lines[current]
        if startrow in line:
            row.append(current)
            current += 1
            line = lines[current]
        if endrow in line:
            row.append(current)
            if len(row) == 2:
                rows.append(row)
            row = []
        current += 1
    return rows


def url_fix(s, charset='utf-8'):
    if isinstance(s, unicode):
        s = s.encode(charset, 'ignore')
    scheme, netloc, path, qs, anchor = urlparse.urlsplit(s)
    path = urllib.quote(path, '/%')
    qs = urllib.quote_plus(qs, ':&=')
    return urlparse.urlunsplit((scheme, netloc, path, qs, anchor))


def TPB(book=None):

    provider = "TPB"
    host = lazylibrarian.TPB_HOST
    if not str(host)[:4] == "http":
        host = 'http://' + host

    providerurl = url_fix(host + "/s/?q=" + book['searchterm'])

    params = {
        "category": "601",
        "page": "0",
        "orderby": "99"
    }
    searchURL = providerurl + "&%s" % urllib.urlencode(params)

    result, success = fetchURL(searchURL)
    if not success:
        # seems KAT returns 404 if no results, not really an error
        if '404' in result:
            logger.debug(u"No results found from %s for %s" % (provider, book['searchterm']))
            result = False
        else:
            logger.debug(searchURL)
            logger.debug('Error fetching data from %s: %s' % (provider, result))
        result = False

    results = []

    if result:
        logger.debug(u'Parsing results from <a href="%s">%s</a>' % (searchURL, provider))
        lines = result.split('\n')
        rows = findrows(lines, '<tr>', '</tr>')
        if len(rows) > 0:
            logger.debug(u"Found %i result%s from %s for %s, checking seeders" % (len(rows),
                         plural(len(rows)), provider, book['searchterm']))
            minimumseeders = int(lazylibrarian.NUMBEROFSEEDERS) - 1
            try:
                rownum = 0
                while rownum < len(rows):
                    cur = rows[rownum][0]
                    fin = rows[rownum][1]

                    while cur < fin:
                        line = lines[cur]
                        if 'class="detLink"' in line:
                            try:
                                magnet = line.split('href="')[1].split('"')[0]
                            except IndexError:
                                magnet = None
                            try:
                                title = line.split('</a>')[0].split('>')[-1]
                            except IndexError:
                                title = None
                        elif 'class="detDesc"' in line:
                            # try:
                            #    age = line.split('class="detDesc"')[1].split('Uploaded ')[1].split(',')[0].decode('ascii','ignore')
                                    #   age = str(age[:5]+'-'+age[5:])
                            # except IndexError:
                            #    age = None
                            try:
                                size = line.split('class="detDesc"')[1].split(
                                    'Size ')[1].split('iB')[0].decode('ascii', 'ignore')
                                try:
                                    mult = 1
                                    if 'K' in size:
                                        size = size.split('K')[0]
                                        mult = 1024
                                    if 'M' in size:
                                        size = size.split('M')[0]
                                        mult = 1024 * 1024
                                    size = int(float(size) * mult)
                                except ValueError:
                                    size = 0
                            except IndexError:
                                size = 0
                        cur += 1

                    try:
                        seeders = lines[fin - 2].split('</td>')[0].split('>')[1]
                    except IndexError:
                        seeders = 0
                    # try:
                    #    leechers = lines[fin-1].split('</td>')[0].split('>')[1]
                    # except IndexError:
                    #    leechers = 0
                    if magnet and minimumseeders < seeders:
                        # no point in asking for magnet link if not enough seeders
                        magurl = '%s/%s' % (host, magnet)
                        result, success = fetchURL(magurl)
                        if not success:
                            logger.debug('Error fetching url %s, %s' % (magurl, result))
                        else:
                            links = result.split('\n')

                            magnet = None
                            for link in links:
                                if 'href="magnet' in link:
                                    try:
                                        magnet = 'magnet' + link.split('href="magnet')[1].split('"')[0]
                                        break
                                    except IndexError:
                                        magnet = None

                    if minimumseeders < seeders:
                        if not magnet or not title:
                            logger.debug('No magnet or title found')
                        else:
                            results.append({
                                'bookid': book['bookid'],
                                'tor_prov': provider,
                                'tor_title': title,
                                'tor_url': magnet,
                                'tor_size': str(size),
                            })
                            logger.debug('Found %s. Size: %s' % (title, size))
                    else:
                        logger.debug('Found %s but %s seeder%s' % (title, seeders, plural(seeders)))
                    rownum += 1

            except Exception as e:
                logger.error(u"An unknown error occurred in the %s parser: %s" % (provider, str(e)))

    logger.debug(
        u"Found %i result%s from %s for %s" %
        (len(results), plural(len(results)), provider, book['searchterm']))
    return results


def KAT(book=None):

    provider = "KAT"
    host = lazylibrarian.KAT_HOST
    if not str(host)[:4] == "http":
        host = 'http://' + host

    providerurl = url_fix(host + "/usearch/" + book['searchterm'])

    params = {
        "category": "books",
        "field": "seeders",
        "sorder": "desc"
    }
    searchURL = providerurl + "/?%s" % urllib.urlencode(params)

    result, success = fetchURL(searchURL)
    if not success:
        # seems KAT returns 404 if no results, not really an error
        if '404' in result:
            logger.debug(u"No results found from %s for %s" % (provider, book['searchterm']))
            result = False
        else:
            logger.debug(searchURL)
            logger.debug('Error fetching data from %s: %s' % (provider, result))
        result = False

    results = []

    if result:
        logger.debug(u'Parsing results from <a href="%s">%s</a>' % (searchURL, provider))
        lines = result.split('\n')
        rows = findrows(lines, '<tr ', '</tr>')
        # first row is the column headers
        if len(rows) > 1:
            logger.debug(u"Found %i result%s from %s for %s, checking seeders" % (len(rows) - 1,
                         plural(len(rows) - 1), provider, book['searchterm']))
            minimumseeders = int(lazylibrarian.NUMBEROFSEEDERS) - 1
            try:
                rownum = 1
                while rownum < len(rows):
                    cur = rows[rownum][0]
                    fin = rows[rownum][1]

                    while cur < fin:
                        line = lines[cur]
                        if 'title="Torrent magnet link"' in line:
                            try:
                                magnet = line.split('href="')[1].split('"')[0]
                            except IndexError:
                                magnet = None
                        elif 'title="Download torrent file"' in line:
                            try:
                                torrent = line.split('href="')[1].split('?')[0]
                                title = line.split('?title=')[1].split(']')[1].split('"')[0]
                            except IndexError:
                                torrent = None
                                title = None
                        cur += 1
                    try:
                        size = lines[fin - 4].split('</td>')[0].split('>')[1].split('&')[0].strip()
                        try:
                            size = int(float(size) * 1024)
                        except ValueError:
                            size = 0
                    except IndexError:
                        size = 0
                    # try:
                    #        age = lines[fin-3].split('</td>')[0].split('>')[1].replace('&nbsp;','-').strip()
                    # except IndexError:
                    #    age = 0
                    try:
                        seeders = lines[fin - 2].split('</td>')[0].split('>')[1]
                    except IndexError:
                        seeders = 0
                    # try:
                    #    leechers = lines[fin-1].split('</td>')[0].split('>')[1]
                    # except IndexError:
                    #    leechers = 0

                    url = magnet  # prefer magnet over torrent
                    if not url:
                        url = torrent

                    if not url or not title:
                        logger.debug('No url or title found')
                    elif minimumseeders < seeders:
                        results.append({
                            'bookid': book['bookid'],
                            'tor_prov': provider,
                            'tor_title': title,
                            'tor_url': url,
                            'tor_size': str(size),
                        })
                        logger.debug('Found %s. Size: %s' % (title, size))
                    else:
                        logger.debug('Found %s but %s seeder%s' % (title, seeders, plural(seeders)))
                    rownum += 1

            except Exception as e:
                logger.error(u"An unknown error occurred in the %s parser: %s" % (provider, str(e)))

    logger.debug(
        u"Found %i result%s from %s for %s" %
        (len(results), plural(len(results)), provider, book['searchterm']))
    return results


def oldKAT(book=None):

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
        request = urllib2.Request(searchURL)
        if lazylibrarian.PROXY_HOST:
            request.set_proxy(lazylibrarian.PROXY_HOST, lazylibrarian.PROXY_TYPE)
        request.add_header('User-Agent', USER_AGENT)
        data = urllib2.urlopen(request, timeout=90)
    except (socket.timeout) as e:
        logger.debug('Timeout fetching data from %s' % provider)
        data = False
    except (urllib2.HTTPError, urllib2.URLError) as e:
        # seems KAT returns 404 if no results, not really an error
        if hasattr(e, 'code') and e.code == 404:
            logger.debug(u"No results found from %s for %s" % (provider, book['searchterm']))
        else:
            logger.debug(searchURL)
            if hasattr(e, 'reason'):
                errmsg = e.reason
            else:
                errmsg = str(e)
            logger.debug('Error fetching data from %s: %s' % (provider, errmsg))
        data = False

    results = []

    if data:
        logger.debug(u'Parsing results from <a href="%s">KAT</a>' % searchURL)
        d = feedparser.parse(data)
        if not len(d.entries):
            pass

        else:
            logger.debug(u"Found %i result%s from %s for %s, checking seeders" % (len(d.entries),
                         plural(len(d.entries)), provider, book['searchterm']))
            for item in d.entries:
                try:
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
                        logger.debug('Found %s but %s seeder%s' % (title, int(seeders), plural(int(seeders))))

                except Exception as e:
                    logger.error(u"An unknown error occurred in the KAT parser: %s" % str(e))

    logger.debug(u"Found %i results from %s for %s" % (len(results), provider, book['searchterm']))
    return results


def ZOO(book=None):

    provider = "zooqle"
    host = lazylibrarian.ZOO_HOST
    if not str(host)[:4] == "http":
        host = 'http://' + host

    providerurl = url_fix(host + "/search?q=" + book['searchterm'])

    params = {
        "category": "books",
        "fmt": "rss"
    }
    searchURL = providerurl + "&%s" % urllib.urlencode(params)

    try:
        request = urllib2.Request(searchURL)
        if lazylibrarian.PROXY_HOST:
            request.set_proxy(lazylibrarian.PROXY_HOST, lazylibrarian.PROXY_TYPE)
        request.add_header('User-Agent', USER_AGENT)
        data = urllib2.urlopen(request, timeout=90)
    except (socket.timeout) as e:
        logger.debug('Timeout fetching data from %s' % provider)
        data = False
    except (urllib2.HTTPError, urllib2.URLError) as e:
        # seems KAT returns 404 if no results, not really an error
        if hasattr(e, 'code') and e.code == 404:
            logger.debug(u"No results found from %s for %s" % (provider, book['searchterm']))
        else:
            logger.debug(searchURL)
            if hasattr(e, 'reason'):
                errmsg = e.reason
            else:
                errmsg = str(e)
            logger.debug('Error fetching data from %s: %s' % (provider, errmsg))
        data = False

    results = []

    minimumseeders = int(lazylibrarian.NUMBEROFSEEDERS) - 1
    if data:
        logger.debug(u'Parsing results from <a href="%s">%s</a>' % (searchURL, provider))
        d = feedparser.parse(data)
        if not len(d.entries):
            pass

        else:
            logger.debug(u"Found %i result%s from %s for %s, checking seeders" % (len(d.entries),
                         plural(len(d.entries)), provider, book['searchterm']))
            for item in d.entries:
                try:
                    title = item['title']
                    seeders = item['torrent_seeds']
                    link = item['links'][1]['href']
                    size = int(item['links'][1]['length'])
                    magnet = item['torrent_magneturi']

                    url = None
                    if link:
                        url = link
                    if magnet:  # prefer magnet over torrent
                        url = magnet

                    if not url or not title:
                        logger.debug('No url or title found')
                    elif minimumseeders < int(seeders):
                        results.append({
                            'bookid': book['bookid'],
                            'tor_prov': provider,
                            'tor_title': title,
                            'tor_url': url,
                            'tor_size': str(size),
                        })

                        logger.debug('Found %s. Size: %s' % (title, size))
                    else:
                        logger.debug('Found %s but %s seeder%s' % (title, int(seeders), plural(int(seeders))))

                except Exception as e:
                    logger.error(u"An unknown error occurred in the %s parser: %s" % (provider, str(e)))

    logger.debug(u"Found %i results from %s for %s" % (len(results), provider, book['searchterm']))
    return results


def TDL(book=None):

    provider = "torrentdownloads"
    host = lazylibrarian.TDL_HOST
    if not str(host)[:4] == "http":
        host = 'http://' + host

    providerurl = url_fix(host)

    params = {
        "type": "search",
        "cid": "2",
        "search": book['searchterm']
    }
    searchURL = providerurl + "/rss.xml?%s" % urllib.urlencode(params)

    try:
        request = urllib2.Request(searchURL)
        if lazylibrarian.PROXY_HOST:
            request.set_proxy(lazylibrarian.PROXY_HOST, lazylibrarian.PROXY_TYPE)
        request.add_header('User-Agent', USER_AGENT)
        data = urllib2.urlopen(request, timeout=90)
    except (socket.timeout) as e:
        logger.debug('Timeout fetching data from %s' % provider)
        data = False
    except (urllib2.HTTPError, urllib2.URLError) as e:
        # seems KAT returns 404 if no results, not really an error
        if hasattr(e, 'code') and e.code == 404:
            logger.debug(searchURL)
            logger.debug(u"No results found from %s for %s" % (provider, book['searchterm']))
        else:
            logger.debug(searchURL)
            if hasattr(e, 'reason'):
                errmsg = e.reason
            else:
                errmsg = str(e)
            logger.debug('Error fetching data from %s: %s' % (provider, errmsg))
        data = False

    results = []

    minimumseeders = int(lazylibrarian.NUMBEROFSEEDERS) - 1
    if data:
        logger.debug(u'Parsing results from <a href="%s">%s</a>' % (searchURL, provider))
        d = feedparser.parse(data)
        if not len(d.entries):
            pass

        else:
            logger.debug(u"Found %i result%s from %s for %s, checking seeders" % (len(d.entries),
                         plural(len(d.entries)), provider, book['searchterm']))
            for item in d.entries:
                try:
                    title = item['title']
                    seeders = item['seeders']
                    link = item['link']
                    size = int(item['size'])
                    url = None

                    if link and minimumseeders < seeders:
                        # no point requesting the magnet link if not enough seeders
                        request = urllib2.Request(link)
                        if lazylibrarian.PROXY_HOST:
                            request.set_proxy(lazylibrarian.PROXY_HOST, lazylibrarian.PROXY_TYPE)
                        request.add_header('User-Agent', USER_AGENT)

                        conn = urllib2.urlopen(request, timeout=90)
                        result = conn.read()
                        lines = result.split('\n')
                        for line in lines:
                            if 'href="magnet' in line:
                                try:
                                    url = 'magnet' + line.split('href="magnet')[1].split('"')[0]
                                    break
                                except IndexError:
                                    url = None

                    if minimumseeders < int(seeders):
                        if not url or not title:
                            logger.debug('No url or title found')
                        else:
                            results.append({
                                'bookid': book['bookid'],
                                'tor_prov': provider,
                                'tor_title': title,
                                'tor_url': url,
                                'tor_size': str(size),
                            })
                            logger.debug('Found %s. Size: %s' % (title, size))
                    else:
                        logger.debug('Found %s but %s seeder%s' % (title, int(seeders), plural(int(seeders))))

                except Exception as e:
                    logger.error(u"An unknown error occurred in the %s parser: %s" % (provider, str(e)))

    logger.debug(u"Found %i results from %s for %s" % (len(results), provider, book['searchterm']))
    return results
