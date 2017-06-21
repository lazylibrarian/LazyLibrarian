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
import urlparse
import traceback

import lazylibrarian
import lib.feedparser as feedparser
from lazylibrarian import logger
from lazylibrarian.cache import fetchURL
from lazylibrarian.formatter import plural, unaccented, formatAuthorName
from lib.BeautifulSoup import BeautifulSoup


def url_fix(s, charset='utf-8'):
    if isinstance(s, unicode):
        s = s.encode(charset, 'ignore')
    scheme, netloc, path, qs, anchor = urlparse.urlsplit(s)
    path = urllib.quote(path, '/%')
    qs = urllib.quote_plus(qs, ':&=')
    return urlparse.urlunsplit((scheme, netloc, path, qs, anchor))


def TPB(book=None):
    errmsg = ''
    provider = "TPB"
    host = lazylibrarian.CONFIG['TPB_HOST']
    if not str(host)[:4] == "http":
        host = 'http://' + host

    providerurl = url_fix(host + "/s/?q=" + book['searchterm'])

    cat = 0  # 601=ebooks, 102=audiobooks, 0=all, no mag category
    if 'library' in book:
        if book['library'] == 'AudioBook':
            cat = 102
        elif book['library'] == 'eBook':
            cat = 601
        elif book['library'] == 'magazine':
            cat = 0

    page = 0
    results = []
    next_page = True

    while next_page:

        params = {
            "category": cat,
            "page": page,
            "orderby": "99"
        }

        searchURL = providerurl + "&%s" % urllib.urlencode(params)
        next_page = False
        result, success = fetchURL(searchURL)
        if not success:
            # may return 404 if no results, not really an error
            if '404' in result:
                logger.debug(u"No results found from %s for %s" % (provider, book['searchterm']))
            else:
                logger.debug(searchURL)
                logger.debug('Error fetching data from %s: %s' % (provider, result))
                errmsg = result
            result = False

        if result:
            logger.debug(u'Parsing results from <a href="%s">%s</a>' % (searchURL, provider))
            minimumseeders = int(lazylibrarian.CONFIG['NUMBEROFSEEDERS']) - 1
            soup = BeautifulSoup(result)
            try:
                table = soup.findAll('table')[0]
                rows = table.findAll('tr')
            except Exception:   # no results = no table in result page
                rows = []

            if len(rows) == 1:
                rows = []

            for row in rows[1:]:
                td = row.findAll('td')
                if len(td) > 2:
                    try:
                        title = unaccented(str(td[1]).split('title=')[1].split('>')[1].split('<')[0])
                        magnet = str(td[1]).split('href="')[1].split('"')[0]
                        size = unaccented(td[1].text.split(', Size ')[1].split('iB')[0])
                        size = size.replace('&nbsp;', '')
                        mult = 1
                        try:
                            if 'K' in size:
                                size = size.split('K')[0]
                                mult = 1024
                            elif 'M' in size:
                                size = size.split('M')[0]
                                mult = 1024 * 1024
                            elif 'G' in size:
                                size = size.split('G')[0]
                                mult = 1024 * 1024 * 1024
                            size = int(float(size) * mult)
                        except (ValueError, IndexError):
                            size = 0
                        try:
                            seeders = int(td[2].text)
                        except ValueError:
                            seeders = 0

                        if minimumseeders < int(seeders):
                            # no point in asking for magnet link if not enough seeders
                            magurl = '%s/%s' % (host, magnet)
                            result, success = fetchURL(magurl)
                            if not success:
                                logger.debug('Error fetching url %s, %s' % (magurl, result))
                            else:
                                magnet = None
                                new_soup = BeautifulSoup(result)
                                for link in new_soup.findAll('a'):
                                    output = link.get('href')
                                    if output and output.startswith('magnet'):
                                        magnet = output
                                        break
                            if not magnet or not title:
                                logger.debug('Missing magnet or title')
                            else:
                                results.append({
                                    'bookid': book['bookid'],
                                    'tor_prov': provider,
                                    'tor_title': title,
                                    'tor_url': magnet,
                                    'tor_size': str(size),
                                    'tor_type': 'magnet',
                                    'priority': lazylibrarian.CONFIG['TPB_DLPRIORITY']
                                })
                                logger.debug('Found %s. Size: %s' % (title, size))
                                next_page = True
                        else:
                            logger.debug('Found %s but %s seeder%s' % (title, seeders, plural(seeders)))
                    except Exception as e:
                        logger.error(u"An error occurred in the %s parser: %s" % (provider, str(e)))
                        logger.debug('%s: %s' % (provider, traceback.format_exc()))

        page += 1
        if 0 < lazylibrarian.CONFIG['MAX_PAGES'] < page:
            logger.warn('Maximum results page search reached, still more results available')
            next_page = False

    logger.debug(u"Found %i result%s from %s for %s" %
                 (len(results), plural(len(results)), provider, book['searchterm']))
    return results, errmsg


def KAT(book=None):
    errmsg = ''
    provider = "KAT"
    host = lazylibrarian.CONFIG['KAT_HOST']
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
        else:
            logger.debug(searchURL)
            logger.debug('Error fetching data from %s: %s' % (provider, result))
            errmsg = result
        result = False

    results = []

    if result:
        logger.debug(u'Parsing results from <a href="%s">%s</a>' % (searchURL, provider))
        minimumseeders = int(lazylibrarian.CONFIG['NUMBEROFSEEDERS']) - 1
        soup = BeautifulSoup(result)

        try:
            table = soup.findAll('table')[1]
            rows = table.findAll('tr')
        except Exception:  # no results = no table in result page
            rows = []

        if len(rows) == 1:
            rows = []

        for row in rows[1:]:
            td = row.findAll('td')
            if len(td) > 3:
                try:
                    title = unaccented(str(td[0]).split('cellMainLink">')[1].split('<')[0])
                    # kat can return magnet or torrent or both.
                    magnet = ''
                    url = ''
                    mode = 'torrent'
                    try:
                        magnet = 'magnet' + str(td[0]).split('href="magnet')[1].split('"')[0]
                        mode = 'magnet'
                    except IndexError:
                        pass
                    try:
                        url = 'http' + str(td[0]).split('href="http')[1].split('.torrent?')[0] + '.torrent'
                        mode = 'torrent'
                    except IndexError:
                        pass

                    if not url or (magnet and url and lazylibrarian.CONFIG['PREFER_MAGNET']):
                        url = magnet
                        mode = 'magnet'

                    try:
                        size = str(td[1].text).replace('&nbsp;', '').upper()
                        mult = 1
                        if 'K' in size:
                            size = size.split('K')[0]
                            mult = 1024
                        elif 'M' in size:
                            size = size.split('M')[0]
                            mult = 1024 * 1024
                        elif 'G' in size:
                            size = size.split('G')[0]
                            mult = 1024 * 1024 * 1024
                        size = int(float(size) * mult)
                    except (ValueError, IndexError):
                        size = 0
                    try:
                        seeders = int(td[3].text)
                    except ValueError:
                        seeders = 0

                    if not url or not title:
                        logger.debug('Missing url or title')
                    elif minimumseeders < int(seeders):
                        results.append({
                            'bookid': book['bookid'],
                            'tor_prov': provider,
                            'tor_title': title,
                            'tor_url': url,
                            'tor_size': str(size),
                            'tor_type': mode,
                            'priority': lazylibrarian.CONFIG['KAT_DLPRIORITY']
                        })
                        logger.debug('Found %s. Size: %s' % (title, size))
                    else:
                        logger.debug('Found %s but %s seeder%s' % (title, seeders, plural(seeders)))
                except Exception as e:
                    logger.error(u"An error occurred in the %s parser: %s" % (provider, str(e)))
                    logger.debug('%s: %s' % (provider, traceback.format_exc()))

    logger.debug(u"Found %i result%s from %s for %s" %
                 (len(results), plural(len(results)), provider, book['searchterm']))
    return results, errmsg


def WWT(book=None):
    errmsg = ''
    provider = "WorldWideTorrents"
    host = lazylibrarian.CONFIG['WWT_HOST']
    if not str(host)[:4] == "http":
        host = 'http://' + host

    providerurl = url_fix(host + "/torrents-search.php")

    cat = 0  # 0=all, 36=ebooks, 52=mags, 56=audiobooks
    if 'library' in book:
        if book['library'] == 'AudioBook':
            cat = 56
        elif book['library'] == 'eBook':
            cat = 36
        elif book['library'] == 'magazine':
            cat = 52

    params = {
        "search": book['searchterm'],
        "cat": cat
    }
    searchURL = providerurl + "/?%s" % urllib.urlencode(params)

    result, success = fetchURL(searchURL)
    if not success:
        # seems KAT returns 404 if no results, not really an error
        if '404' in result:
            logger.debug(u"No results found from %s for %s" % (provider, book['searchterm']))
        else:
            logger.debug(searchURL)
            logger.debug('Error fetching data from %s: %s' % (provider, result))
            errmsg = result
        result = False

    results = []

    if result:
        logger.debug(u'Parsing results from <a href="%s">%s</a>' % (searchURL, provider))
        minimumseeders = int(lazylibrarian.CONFIG['NUMBEROFSEEDERS']) - 1
        soup = BeautifulSoup(result)

        try:
            table = soup.findAll('table')[2]
            rows = table.findAll('tr')
        except Exception:  # no results = no table in result page
            rows = []

        if len(rows) == 1:
            rows = []

        for row in rows[1:]:
            td = row.findAll('td')
            if len(td) > 3:
                try:
                    title = unaccented(str(td[0]).split('title="')[1].split('"')[0])

                    # kat can return magnet or torrent or both.
                    magnet = ''
                    url = ''
                    mode = 'torrent'
                    try:
                        magnet = 'magnet' + str(td[0]).split('href="magnet')[1].split('"')[0]
                        mode = 'magnet'
                    except IndexError:
                        pass
                    try:
                        url = url_fix(host + '/download.php') + \
                                      str(td[0]).split('href="download.php')[1].split('.torrent"')[0] + '.torrent'
                        mode = 'torrent'
                    except IndexError:
                        pass

                    if not url or (magnet and url and lazylibrarian.CONFIG['PREFER_MAGNET']):
                        url = magnet
                        mode = 'magnet'

                    try:
                        size = str(td[1].text).replace('&nbsp;', '').upper()
                        mult = 1
                        if 'K' in size:
                            size = size.split('K')[0]
                            mult = 1024
                        elif 'M' in size:
                            size = size.split('M')[0]
                            mult = 1024 * 1024
                        elif 'G' in size:
                            size = size.split('G')[0]
                            mult = 1024 * 1024 * 1024
                        size = int(float(size) * mult)
                    except (ValueError, IndexError):
                        size = 0
                    try:
                        seeders = int(td[2].text)
                    except ValueError:
                        seeders = 0
                    if not url or not title:
                        logger.debug('Missing url or title')
                    elif minimumseeders < int(seeders):
                        results.append({
                            'bookid': book['bookid'],
                            'tor_prov': provider,
                            'tor_title': title,
                            'tor_url': url,
                            'tor_size': str(size),
                            'tor_type': mode,
                            'priority': lazylibrarian.CONFIG['WWT_DLPRIORITY']
                        })
                        logger.debug('Found %s. Size: %s' % (title, size))
                    else:
                        logger.debug('Found %s but %s seeder%s' % (title, seeders, plural(seeders)))
                except Exception as e:
                    logger.error(u"An error occurred in the %s parser: %s" % (provider, str(e)))
                    logger.debug('%s: %s' % (provider, traceback.format_exc()))

    logger.debug(u"Found %i result%s from %s for %s" %
                 (len(results), plural(len(results)), provider, book['searchterm']))
    return results, errmsg


def EXTRA(book=None):
    errmsg = ''
    provider = "Extratorrent"
    host = lazylibrarian.CONFIG['EXTRA_HOST']
    if not str(host)[:4] == "http":
        host = 'http://' + host

    providerurl = url_fix(host + "/rss")

    params = {
        "type": "search",
        "s_cat": "2",
        "search": book['searchterm']
    }
    searchURL = providerurl + "/?%s" % urllib.urlencode(params)

    data, success = fetchURL(searchURL)
    if not success:
        # may return 404 if no results, not really an error
        if '404' in data:
            logger.debug(u"No results found from %s for %s" % (provider, book['searchterm']))
        else:
            logger.debug('Error fetching data from %s: %s' % (provider, data))
            errmsg = data

        data = False

    results = []

    minimumseeders = int(lazylibrarian.CONFIG['NUMBEROFSEEDERS']) - 1
    if data:
        logger.debug(u'Parsing results from <a href="%s">%s</a>' % (searchURL, provider))
        d = feedparser.parse(data)
        if len(d.entries):
            for item in d.entries:
                try:
                    title = unaccented(item['title'])

                    try:
                        seeders = int(item['seeders'])
                    except ValueError:
                        seeders = 0

                    try:
                        size = int(item['size'])
                    except ValueError:
                        size = 0

                    url = None
                    for link in item['links']:
                        if 'x-bittorrent' in link['type']:
                            url = link['href']

                    if not url or not title:
                        logger.debug('No url or title found')
                    elif minimumseeders < int(seeders):
                        results.append({
                            'bookid': book['bookid'],
                            'tor_prov': provider,
                            'tor_title': title,
                            'tor_url': url,
                            'tor_size': str(size),
                            'tor_type': 'torrent',
                            'priority': lazylibrarian.CONFIG['EXTRA_DLPRIORITY']
                        })
                        logger.debug('Found %s. Size: %s' % (title, size))
                    else:
                        logger.debug('Found %s but %s seeder%s' % (title, seeders, plural(seeders)))

                except Exception as e:
                    logger.error(u"An error occurred in the %s parser: %s" % (provider, str(e)))
                    logger.debug('%s: %s' % (provider, traceback.format_exc()))

    logger.debug(u"Found %i result%s from %s for %s" %
                 (len(results), plural(len(results)), provider, book['searchterm']))
    return results, errmsg


def ZOO(book=None):
    errmsg = ''
    provider = "zooqle"
    host = lazylibrarian.CONFIG['ZOO_HOST']
    if not str(host)[:4] == "http":
        host = 'http://' + host

    providerurl = url_fix(host + "/search?q=" + book['searchterm'])

    params = {
        "category": "books",
        "fmt": "rss"
    }
    searchURL = providerurl + "&%s" % urllib.urlencode(params)

    data, success = fetchURL(searchURL)
    if not success:
        # may return 404 if no results, not really an error
        if '404' in data:
            logger.debug(u"No results found from %s for %s" % (provider, book['searchterm']))
        else:
            logger.debug(searchURL)
            logger.debug('Error fetching data from %s: %s' % (provider, data))
            errmsg = data
        data = False

    results = []

    minimumseeders = int(lazylibrarian.CONFIG['NUMBEROFSEEDERS']) - 1
    if data:
        logger.debug(u'Parsing results from <a href="%s">%s</a>' % (searchURL, provider))
        d = feedparser.parse(data)
        if len(d.entries):
            for item in d.entries:
                try:
                    title = unaccented(item['title'])
                    seeders = int(item['torrent_seeds'])
                    link = item['links'][1]['href']
                    size = int(item['links'][1]['length'])
                    magnet = item['torrent_magneturi']

                    url = None
                    mode = 'torrent'
                    if link:
                        url = link
                        mode = 'torrent'
                    if magnet:
                        if not url or (url and lazylibrarian.CONFIG['PREFER_MAGNET']):
                            url = magnet
                            mode = 'magnet'

                    if not url or not title:
                        logger.debug('No url or title found')
                    elif minimumseeders < int(seeders):
                        results.append({
                            'bookid': book['bookid'],
                            'tor_prov': provider,
                            'tor_title': title,
                            'tor_url': url,
                            'tor_size': str(size),
                            'tor_type': mode,
                            'priority': lazylibrarian.CONFIG['ZOO_DLPRIORITY']
                        })
                        logger.debug('Found %s. Size: %s' % (title, size))
                    else:
                        logger.debug('Found %s but %s seeder%s' % (title, seeders, plural(seeders)))

                except Exception as e:
                    if 'forbidden' in str(e).lower():
                        # looks like zooqle has ip based access limits
                        logger.error('Access forbidden. Please wait a while before trying %s again.' % provider)
                    else:
                        logger.error(u"An error occurred in the %s parser: %s" % (provider, str(e)))
                        logger.debug('%s: %s' % (provider, traceback.format_exc()))

    logger.debug(u"Found %i result%s from %s for %s" %
                 (len(results), plural(len(results)), provider, book['searchterm']))
    return results, errmsg


def LIME(book=None):
    errmsg = ''
    provider = "Limetorrent"
    host = lazylibrarian.CONFIG['LIME_HOST']
    if not str(host)[:4] == "http":
        host = 'http://' + host

    searchURL = url_fix(host + "/searchrss/other/?q=" + book['searchterm'])

    data, success = fetchURL(searchURL)
    if not success:
        # may return 404 if no results, not really an error
        if '404' in data:
            logger.debug(u"No results found from %s for %s" % (provider, book['searchterm']))
        else:
            logger.debug(searchURL)
            logger.debug('Error fetching data from %s: %s' % (provider, data))
            errmsg = data
        data = False

    results = []

    minimumseeders = int(lazylibrarian.CONFIG['NUMBEROFSEEDERS']) - 1
    if data:
        logger.debug(u'Parsing results from <a href="%s">%s</a>' % (searchURL, provider))
        d = feedparser.parse(data)
        if len(d.entries):
            for item in d.entries:
                try:
                    title = unaccented(item['title'])
                    try:
                        seeders = item['description']
                        seeders = int(seeders.split('Seeds:')[1].split(',')[0].strip())
                    except (IndexError, ValueError):
                        seeders = 0

                    size = item['size']
                    try:
                        size = int(size)
                    except ValueError:
                        size = 0

                    url = None
                    for link in item['links']:
                        if 'x-bittorrent' in link['type']:
                            url = link['url']

                    if not url or not title:
                        logger.debug('No url or title found')
                    elif minimumseeders < int(seeders):
                        results.append({
                            'bookid': book['bookid'],
                            'tor_prov': provider,
                            'tor_title': title,
                            'tor_url': url,
                            'tor_size': str(size),
                            'tor_type': 'torrent',
                            'priority': lazylibrarian.CONFIG['LIME_DLPRIORITY']
                        })
                        logger.debug('Found %s. Size: %s' % (title, size))
                    else:
                        logger.debug('Found %s but %s seeder%s' % (title, seeders, plural(seeders)))

                except Exception as e:
                    if 'forbidden' in str(e).lower():
                        # may have ip based access limits
                        logger.error('Access forbidden. Please wait a while before trying %s again.' % provider)
                    else:
                        logger.error(u"An error occurred in the %s parser: %s" % (provider, str(e)))
                        logger.debug('%s: %s' % (provider, traceback.format_exc()))

    logger.debug(u"Found %i result%s from %s for %s" %
                 (len(results), plural(len(results)), provider, book['searchterm']))
    return results, errmsg


def GEN(book=None):
    errmsg = ''
    provider = "libgen"
    host = lazylibrarian.CONFIG['GEN_HOST']
    search = lazylibrarian.CONFIG['GEN_SEARCH']
    if not str(host)[:4] == "http":
        host = 'http://' + host

    page = 1
    results = []
    next_page = True

    while next_page:
        if not search or not search.endswith('.php'):
            search = 'search.php'
        if not 'index.php' in search and not 'search.php' in search:
            search = 'search.php'
        if search[0] == '/':
            search = search[1:]

        pagenum = ''
        if page > 1:
            pagenum = '&page=%s' % page

        if 'index.php' in search:
            searchURL = url_fix(host + "/%s?%s&s=%s" %
                                (search, pagenum, book['searchterm']))
        else:
            searchURL = url_fix(host + "/%s?view=simple&open=0&phrase=0&column=def&res=100%s&req=%s" %
                                (search, pagenum, book['searchterm']))

        next_page = False
        result, success = fetchURL(searchURL)
        if not success:
            # may return 404 if no results, not really an error
            if '404' in result:
                logger.debug(u"No results found from %s for %s" % (provider, book['searchterm']))
            elif '111' in result:
                # looks like libgen has ip based access limits
                logger.error('Access forbidden. Please wait a while before trying %s again.' % provider)
                errmsg = result
            else:
                logger.debug(searchURL)
                logger.debug('Error fetching data from %s: %s' % (provider, result))
                errmsg = result

            result = False

        if result:
            logger.debug(u'Parsing results from <a href="%s">%s</a>' % (searchURL, provider))
            try:
                soup = BeautifulSoup(result)
                try:
                    table = soup.findAll('table')[2]
                    rows = table.findAll('tr')
                except Exception:  # no results = no table in result page
                    rows = []

                if 'search.php' in search and len(rows) > 1:
                    rows = rows[1:]

                for row in rows:
                    author = ''
                    title = ''
                    size = ''
                    extn = ''
                    link = ''
                    td = row.findAll('td')
                    if 'index.php' in search and len(td) > 3:
                        try:
                            author = formatAuthorName(unaccented(td[0].text))
                            title = unaccented(td[2].text)
                            temp = str(td[4])
                            temp = temp.split('onmouseout')[1]
                            extn = temp.split('">')[1].split('(')[0]
                            size = temp.split('">')[1].split('(')[1].split(')')[0]
                            size = size.upper()
                            link = temp.split('href=')[2].split('"')[1]
                        except IndexError as e:
                            logger.debug('Error parsing libgen search.php results: %s' % str(e))

                    elif 'search.php' in search and len(td) > 8:
                        try:
                            author = formatAuthorName(unaccented(td[1].text))
                            title = unaccented(str(td[2]).split('>')[2].split('<')[0].strip())
                            link = str(td[2]).split('href="')[1].split('?')[1].split('"')[0]
                            size = unaccented(td[7].text).upper()
                            extn = td[8].text
                        except IndexError as e:
                            logger.debug('Error parsing libgen search.php results; %s' % str(e))

                    if not size:
                        size = 0
                    else:
                        try:
                            mult = 1
                            if 'K' in size:
                                size = size.split('K')[0]
                                mult = 1024
                            elif 'M' in size:
                                size = size.split('M')[0]
                                mult = 1024 * 1024
                            elif 'G' in size:
                                size = size.split('G')[0]
                                mult = 1024 * 1024 * 1024
                            size = int(float(size) * mult)
                        except (ValueError, IndexError):
                            size = 0

                    if link and title:
                        if author:
                            title = author.strip() + ' ' + title.strip()
                        if extn:
                            title = title + '.' + extn

                        if link.startswith('http'):
                            url = link
                        else:
                            url = url_fix(host + "/ads.php?" + link)
                        bookresult, success = fetchURL(url)
                        if not success:
                            # may return 404 if no results, not really an error
                            if '404' in bookresult:
                                logger.debug(u"No results found from %s for %s" % (provider, book['searchterm']))
                            else:
                                logger.debug(url)
                                logger.debug('Error fetching data from %s: %s' % (provider, bookresult))
                                errmsg = bookresult
                            bookresult = False

                        if bookresult:
                            url = None
                            new_soup = BeautifulSoup(bookresult)
                            for link in new_soup.findAll('a'):
                                output = link.get('href')
                                if output:
                                    if '/get.php' in output:
                                        url = '/get.php' + output.split('/get.php')[1]
                                        break
                                    elif '/download/book' in output:
                                        url = '/download/book' + output.split('/download/book')[1]
                                        break
                            if url:
                                url = url_fix(host + url)

                        results.append({
                            'bookid': book['bookid'],
                            'tor_prov': provider,
                            'tor_title': title,
                            'tor_url': url,
                            'tor_size': str(size),
                            'tor_type': 'direct',
                            'priority': lazylibrarian.CONFIG['GEN_DLPRIORITY']
                        })
                        logger.debug('Found %s, Size %s' % (title, size))
                        next_page = True

            except Exception as e:
                logger.error(u"An error occurred in the %s parser: %s" % (provider, str(e)))
                logger.debug('%s: %s' % (provider, traceback.format_exc()))

        page += 1
        if 0 < lazylibrarian.CONFIG['MAX_PAGES'] < page:
            logger.warn('Maximum results page search reached, still more results available')
            next_page = False

    logger.debug(u"Found %i result%s from %s for %s" %
                 (len(results), plural(len(results)), provider, book['searchterm']))
    return results, errmsg


def TDL(book=None):
    errmsg = ''
    provider = "torrentdownloads"
    host = lazylibrarian.CONFIG['TDL_HOST']
    if not str(host)[:4] == "http":
        host = 'http://' + host

    providerurl = url_fix(host)

    params = {
        "type": "search",
        "cid": "2",
        "search": book['searchterm']
    }
    searchURL = providerurl + "/rss.xml?%s" % urllib.urlencode(params)

    data, success = fetchURL(searchURL)
    if not success:
        # may return 404 if no results, not really an error
        if '404' in data:
            logger.debug(u"No results found from %s for %s" % (provider, book['searchterm']))
        else:
            logger.debug(searchURL)
            logger.debug('Error fetching data from %s: %s' % (provider, data))
            errmsg = data
        data = False

    results = []

    minimumseeders = int(lazylibrarian.CONFIG['NUMBEROFSEEDERS']) - 1
    if data:
        logger.debug(u'Parsing results from <a href="%s">%s</a>' % (searchURL, provider))
        d = feedparser.parse(data)
        if len(d.entries):
            for item in d.entries:
                try:
                    title = item['title']
                    seeders = int(item['seeders'])
                    link = item['link']
                    size = int(item['size'])
                    url = None

                    if link and minimumseeders < int(seeders):
                        # no point requesting the magnet link if not enough seeders
                        # TDL gives us a relative link
                        result, success = fetchURL(providerurl+link)
                        url = None
                        if success:
                            new_soup = BeautifulSoup(result)
                            for link in new_soup.findAll('a'):
                                output = link.get('href')
                                if output and output.startswith('magnet'):
                                    url = output
                                    break

                        if not url or not title:
                            logger.debug('Missing url or title')
                        else:
                            results.append({
                                'bookid': book['bookid'],
                                'tor_prov': provider,
                                'tor_title': title,
                                'tor_url': url,
                                'tor_size': str(size),
                                'tor_type': 'magnet',
                                'priority': lazylibrarian.CONFIG['TDL_DLPRIORITY']
                            })
                            logger.debug('Found %s. Size: %s' % (title, size))
                    else:
                        logger.debug('Found %s but %s seeder%s' % (title, seeders, plural(seeders)))

                except Exception as e:
                    logger.error(u"An error occurred in the %s parser: %s" % (provider, str(e)))
                    logger.debug('%s: %s' % (provider, traceback.format_exc()))

    logger.debug(u"Found %i result%s from %s for %s" %
                 (len(results), plural(len(results)), provider, book['searchterm']))
    return results, errmsg
