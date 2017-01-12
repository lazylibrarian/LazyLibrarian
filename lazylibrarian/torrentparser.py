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

import lazylibrarian
import lib.feedparser as feedparser
from lazylibrarian import logger
from lazylibrarian.cache import fetchURL
from lazylibrarian.formatter import plural, unaccented
from lib.BeautifulSoup import BeautifulSoup


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
        # may return 404 if no results, not really an error
        if '404' in result:
            logger.debug(u"No results found from %s for %s" % (provider, book['searchterm']))
        else:
            logger.debug(searchURL)
            logger.debug('Error fetching data from %s: %s' % (provider, result))
        result = False

    results = []

    if result:
        logger.debug(u'Parsing results from <a href="%s">%s</a>' % (searchURL, provider))
        minimumseeders = int(lazylibrarian.NUMBEROFSEEDERS) - 1
        soup = BeautifulSoup(result)
        try:
            table = soup.findAll('table')[0]
            rows = table.findAll('tr')
        except Exception:   # no results = no table in result page
            rows = []

        c1 = []
        c2 = []

        if len(rows) > 1:
            for row in rows[1:]:
                if len(row.findAll('td')) > 2:
                    c1.append(row.findAll('td')[1])
                    c2.append(row.findAll('td')[2])

        for col1, col2 in zip(c1, c2):
            try:
                title = unaccented(str(col1).split('title=')[1].split('>')[1].split('<')[0])
                magnet = str(col1).split('href="')[1].split('"')[0]
                size = unaccented(col1.text.split(', Size ')[1].split('iB')[0])
                mult = 1
                try:
                    if 'K' in size:
                        size = size.split('K')[0]
                        mult = 1024
                    elif 'M' in size:
                        size = size.split('M')[0]
                        mult = 1024 * 1024
                    size = int(float(size) * mult)
                except (ValueError, IndexError):
                    size = 0
                try:
                    seeders = int(col2.text)
                except ValueError:
                    seeders = 0

                if magnet and minimumseeders < seeders:
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
                        if minimumseeders < seeders:
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
                else:
                    logger.debug('Found %s but %s seeder%s' % (title, seeders, plural(seeders)))
            except Exception as e:
                logger.error(u"An error occurred in the %s parser: %s" % (provider, str(e)))

    logger.debug(u"Found %i result%s from %s for %s" %
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
        else:
            logger.debug(searchURL)
            logger.debug('Error fetching data from %s: %s' % (provider, result))
        result = False

    results = []

    if result:
        logger.debug(u'Parsing results from <a href="%s">%s</a>' % (searchURL, provider))
        minimumseeders = int(lazylibrarian.NUMBEROFSEEDERS) - 1
        soup = BeautifulSoup(result)

        try:
            table = soup.findAll('table')[1]
            rows = table.findAll('tr')
        except Exception:  # no results = no table in result page
            rows = []

        c0 = []
        c1 = []
        c3 = []

        if len(rows) > 1:
            for row in rows[1:]:
                if len(row.findAll('td')) > 3:
                    c0.append(row.findAll('td')[0])
                    c1.append(row.findAll('td')[1])
                    c3.append(row.findAll('td')[3])

        for col0, col1, col3 in zip(c0, c1, c3):
            try:
                title = unaccented(str(col0).split('cellMainLink">')[1].split('<')[0])
                # kat can return magnet or torrent or both.
                magnet = ''
                url = ''
                try:
                    magnet = 'magnet' + str(col0).split('href="magnet')[1].split('"')[0]
                except IndexError:
                    pass
                try:
                    url = 'http' + str(col0).split('href="http')[1].split('.torrent?')[0] + '.torrent'
                except IndexError:
                    pass

                if not url or (magnet and url and lazylibrarian.PREFER_MAGNET):
                    url = magnet

                try:
                    size = str(col1.text).replace('&nbsp;', '').upper()
                    mult = 1
                    if 'K' in size:
                        size = size.split('K')[0]
                        mult = 1024
                    elif 'M' in size:
                        size = size.split('M')[0]
                        mult = 1024 * 1024
                    size = int(float(size) * mult)
                except (ValueError, IndexError):
                    size = 0
                try:
                    seeders = int(col3.text)
                except ValueError:
                    seeders = 0

                if not url or not title:
                    logger.debug('Missing url or title')
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
            except Exception as e:
                logger.error(u"An error occurred in the %s parser: %s" % (provider, str(e)))

    logger.debug(u"Found %i result%s from %s for %s" %
                 (len(results), plural(len(results)), provider, book['searchterm']))
    return results


def EXTRA(book=None):

    provider = "Extratorrent"
    host = lazylibrarian.EXTRA_HOST
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
        data = False

    results = []

    minimumseeders = int(lazylibrarian.NUMBEROFSEEDERS) - 1
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

                except Exception as e:
                    logger.error(u"An error occurred in the %s parser: %s" % (provider, str(e)))

    logger.debug(u"Found %i result%s from %s for %s" %
                 (len(results), plural(len(results)), provider, book['searchterm']))
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

    data, success = fetchURL(searchURL)
    if not success:
        # may return 404 if no results, not really an error
        if '404' in data:
            logger.debug(u"No results found from %s for %s" % (provider, book['searchterm']))
        else:
            logger.debug(searchURL)
            logger.debug('Error fetching data from %s: %s' % (provider, data))
        data = False

    results = []

    minimumseeders = int(lazylibrarian.NUMBEROFSEEDERS) - 1
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
                    if link:
                        url = link
                    if magnet:
                        if not url or (url and lazylibrarian.PREFER_MAGNET):
                            url = magnet

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

                except Exception as e:
                    if 'forbidden' in str(e).lower():
                        # looks like zooqle has ip based access limits
                        logger.error('Access forbidden. Please wait a while before trying %s again.' % provider)
                    else:
                        logger.error(u"An error occurred in the %s parser: %s" % (provider, str(e)))

    logger.debug(u"Found %i result%s from %s for %s" %
                 (len(results), plural(len(results)), provider, book['searchterm']))
    return results


def LIME(book=None):

    provider = "Limetorrent"
    host = lazylibrarian.LIME_HOST
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
        data = False

    results = []

    minimumseeders = int(lazylibrarian.NUMBEROFSEEDERS) - 1
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

                except Exception as e:
                    if 'forbidden' in str(e).lower():
                        # may have ip based access limits
                        logger.error('Access forbidden. Please wait a while before trying %s again.' % provider)
                    else:
                        logger.error(u"An error occurred in the %s parser: %s" % (provider, str(e)))

    logger.debug(u"Found %i result%s from %s for %s" %
                 (len(results), plural(len(results)), provider, book['searchterm']))
    return results


def GEN(book=None):

    provider = "libgen"
    host = lazylibrarian.GEN_HOST
    if not str(host)[:4] == "http":
        host = 'http://' + host

    searchURL = url_fix(host + "/search.php?view=simple&open=0&phrase=0&column=def&res=100&req=" +
                        book['searchterm'])

    result, success = fetchURL(searchURL)
    if not success:
        # may return 404 if no results, not really an error
        if '404' in result:
            logger.debug(u"No results found from %s for %s" % (provider, book['searchterm']))
        elif '111' in result:
            # looks like libgen has ip based access limits
            logger.error('Access forbidden. Please wait a while before trying %s again.' % provider)
        else:
            logger.debug(searchURL)
            logger.debug('Error fetching data from %s: %s' % (provider, result))
        result = False

    results = []

    if result:
        logger.debug(u'Parsing results from <a href="%s">%s</a>' % (searchURL, provider))
        soup = BeautifulSoup(result)
        try:
            table = soup.findAll('table')[2]
            rows = table.findAll('tr')
        except Exception:  # no results = no table in result page
            rows = []

        c1 = []
        c2 = []
        c7 = []
        c8 = []

        if len(rows) > 1:
            for row in rows[1:]:
                if len(row.findAll('td')) > 8:
                    c1.append(row.findAll('td')[1])
                    c2.append(row.findAll('td')[2])
                    c7.append(row.findAll('td')[7])
                    c8.append(row.findAll('td')[8])

        for col1, col2, col7, col8 in zip(c1, c2, c7, c8):
            try:
                author = unaccented(col1.text)
                title = unaccented(str(col2).split('>')[2].split('<')[0].strip())
                link = str(col2).split('href="')[1].split('?')[1].split('"')[0]
                size = unaccented(col7.text).upper()
                extn = col8.text

                try:
                    mult = 1
                    if 'K' in size:
                        size = size.split('K')[0]
                        mult = 1024
                    elif 'M' in size:
                        size = size.split('M')[0]
                        mult = 1024 * 1024
                    size = int(float(size) * mult)
                except (ValueError, IndexError):
                    size = 0

                if link and title:
                    if author:
                        title = author.strip() + ' ' + title.strip()
                    if extn:
                        title = title + '.' + extn

                    bookURL = url_fix(host + "/ads.php?" + link)
                    bookresult, success = fetchURL(bookURL)
                    if not success:
                        # may return 404 if no results, not really an error
                        if '404' in bookresult:
                            logger.debug(u"No results found from %s for %s" % (provider, book['searchterm']))
                        else:
                            logger.debug(bookURL)
                            logger.debug('Error fetching data from %s: %s' % (provider, bookresult))
                        bookresult = False
                    if bookresult:
                        url = None
                        new_soup = BeautifulSoup(bookresult)
                        for link in new_soup.findAll('a'):
                            output = link.get('href')
                            if output and output.startswith('/get.php'):
                                url = output
                                break

                        if url:
                            url = url_fix(host + url)
                            results.append({
                                'bookid': book['bookid'],
                                'tor_prov': provider,
                                'tor_title': title,
                                'tor_url': url,
                                'tor_size': str(size),
                            })
                            logger.debug('Found %s, Size %s' % (title, size))

            except Exception as e:
                logger.error(u"An error occurred in the %s parser: %s" % (provider, str(e)))

    logger.debug(u"Found %i result%s from %s for %s" %
                 (len(results), plural(len(results)), provider, book['searchterm']))
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

    data, success = fetchURL(searchURL)
    if not success:
        # may return 404 if no results, not really an error
        if '404' in data:
            logger.debug(u"No results found from %s for %s" % (provider, book['searchterm']))
        else:
            logger.debug(searchURL)
            logger.debug('Error fetching data from %s: %s' % (provider, data))
        data = False

    results = []

    minimumseeders = int(lazylibrarian.NUMBEROFSEEDERS) - 1
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

                    if link and minimumseeders < seeders:
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

                    if minimumseeders < int(seeders):
                        if not url or not title:
                            logger.debug('Missing url or title')
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
                        logger.debug('Found %s but %s seeder%s' % (title, seeders, plural(seeders)))

                except Exception as e:
                    logger.error(u"An error occurred in the %s parser: %s" % (provider, str(e)))

    logger.debug(u"Found %i result%s from %s for %s" %
                 (len(results), plural(len(results)), provider, book['searchterm']))
    return results
