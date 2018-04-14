#  This file is part of Lazylibrarian.
#  Lazylibrarian is free software':'you can redistribute it and/or modify
#  it under the terms of the GNU General Public License as published by
#  the Free Software Foundation, either version 3 of the License, or
#  (at your option) any later version.
#  Lazylibrarian is distributed in the hope that it will be useful,
#  but WITHOUT ANY WARRANTY; without even the implied warranty of
#  MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
#  GNU General Public License for more details.
#  You should have received a copy of the GNU General Public License
#  along with Lazylibrarian.  If not, see <http://www.gnu.org/licenses/>.

import traceback

import lazylibrarian
from lazylibrarian import logger
from lazylibrarian.cache import fetchURL
from lazylibrarian.formatter import plural, formatAuthorName, makeUnicode
from lazylibrarian.torrentparser import url_fix
from lib.six import PY2
# noinspection PyUnresolvedReferences
from lib.six.moves.urllib_parse import urlparse, urlencode

if PY2:
    from lib.bs4 import BeautifulSoup
else:
    from lib3.bs4 import BeautifulSoup


# noinspection PyProtectedMember
def redirect_url(genhost, url):
    """ libgen.io might have dns blocked, but user can bypass using genhost 93.174.95.27 in config
        libgen might send us a book url that still contains http://libgen.io/  or /libgen.io/
        so we might need to redirect it to users genhost setting """

    myurl = urlparse(url)
    if myurl.netloc.lower() != 'libgen.io':
        return url

    host = urlparse(genhost)
    # genhost http://93.174.95.27 -> scheme http, netloc 93.174.95.27, path ""
    # genhost 93.174.95.27 -> scheme "", netloc "", path 93.174.95.27
    if host.netloc:
        if host.netloc.lower() != 'libgen.io':
            # noinspection PyArgumentList
            myurl = myurl._replace(**{"netloc": host.netloc})
            logger.debug('Redirected libgen.io to [%s]' % host.netloc)
    elif host.path:
        if host.path.lower() != 'libgen.io':
            # noinspection PyArgumentList
            myurl = myurl._replace(**{"netloc": host.netloc})
            logger.debug('Redirected libgen.io to [%s]' % host.netloc)
    return myurl.geturl()


def GEN(book=None, prov=None, test=False):
    errmsg = ''
    provider = "libgen.io"
    if prov is None:
        prov = 'GEN'
    host = lazylibrarian.CONFIG[prov + '_HOST']
    if not host.startswith('http'):
        host = 'http://' + host

    search = lazylibrarian.CONFIG[prov + '_SEARCH']
    if not search or not search.endswith('.php'):
        search = 'search.php'
    if 'index.php' not in search and 'search.php' not in search:
        search = 'search.php'
    if search[0] == '/':
        search = search[1:]

    sterm = makeUnicode(book['searchterm'])

    page = 1
    results = []
    next_page = True

    while next_page:
        if 'index.php' in search:
            params = {
                "s": book['searchterm'],
                "f_lang": "All",
                "f_columns": 0,
                "f_ext": "All"
            }
        else:
            params = {
                "view": "simple",
                "open": 0,
                "phrase": 0,
                "column": "def",
                "res": 100,
                "req": book['searchterm']
            }

        if page > 1:
            params['page'] = page

        providerurl = url_fix(host + "/%s" % search)
        searchURL = providerurl + "?%s" % urlencode(params)

        next_page = False
        result, success = fetchURL(searchURL)
        if not success:
            # may return 404 if no results, not really an error
            if '404' in result:
                logger.debug("No results found from %s for %s" % (provider, sterm))
                success = True
            elif '111' in result:
                # looks like libgen has ip based access limits
                logger.error('Access forbidden. Please wait a while before trying %s again.' % provider)
                errmsg = result
            else:
                logger.debug(searchURL)
                logger.debug('Error fetching page data from %s: %s' % (provider, result))
                errmsg = result
            result = False

        if test:
            return success

        if result:
            logger.debug('Parsing results from <a href="%s">%s</a>' % (searchURL, provider))
            try:
                soup = BeautifulSoup(result, 'html5lib')
                rows = []

                try:
                    table = soup.find_all('table')[2]  # un-named table
                    if table:
                        rows = table.find_all('tr')
                except IndexError:  # no results table in result page
                    rows = []

                if 'search.php' in search and len(rows) > 1:
                    rows = rows[1:]

                for row in rows:
                    author = ''
                    title = ''
                    size = ''
                    extn = ''
                    link = ''
                    td = row.find_all('td')

                    if 'index.php' in search and len(td) > 3:
                        try:
                            author = formatAuthorName(td[0].text)
                            title = td[2].text
                            newsoup = BeautifulSoup(str(td[4]), 'html5lib')
                            data = newsoup.find('a')
                            link = data.get('href')
                            extn = data.text.split('(')[0]
                            size = data.text.split('(')[1].split(')')[0]
                            size = size.upper()
                        except IndexError as e:
                            logger.debug('Error parsing libgen index.php results: %s' % str(e))

                    elif 'search.php' in search and len(td) > 8:
                        try:
                            author = formatAuthorName(td[1].text)
                            title = td[2].text
                            size = td[7].text.upper()
                            extn = td[8].text
                            link = ''
                            newsoup = BeautifulSoup(str(td[2]), 'html5lib')
                            for res in newsoup.find_all('a'):
                                output = res.get('href')
                                if 'md5' in output:
                                    link = output
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
                            url = redirect_url(host, link)
                        else:
                            if "/index.php?" in link:
                                link = 'md5' + link.split('md5')[1]

                            if "/ads.php?" in link:
                                url = url_fix(host + "/" + link)
                            else:
                                url = url_fix(host + "/ads.php?" + link)

                        bookresult, success = fetchURL(url)
                        if not success:
                            # may return 404 if no results, not really an error
                            if '404' in bookresult:
                                logger.debug("No results found from %s for %s" % (provider, sterm))
                            else:
                                logger.debug(url)
                                logger.debug('Error fetching link data from %s: %s' % (provider, bookresult))
                                errmsg = bookresult
                            bookresult = False

                        if bookresult:
                            url = None
                            try:
                                new_soup = BeautifulSoup(bookresult, 'html5lib')
                                for link in new_soup.find_all('a'):
                                    output = link.get('href')
                                    if output:
                                        if output.startswith('http') and '/get.php' in output:
                                            url = output
                                            break
                                        elif '/get.php' in output:
                                            url = '/get.php' + output.split('/get.php')[1]
                                            break
                                        elif '/download/book' in output:
                                            url = '/download/book' + output.split('/download/book')[1]
                                            break

                                if url and not url.startswith('http'):
                                    url = url_fix(host + url)
                                else:
                                    url = redirect_url(host, url)
                            except Exception as e:
                                logger.error('%s parsing bookresult for %s: %s' % (type(e).__name__, link, str(e)))
                                url = None

                        if url:
                            results.append({
                                'bookid': book['bookid'],
                                'tor_prov': provider + '/' + search,
                                'tor_title': title,
                                'tor_url': url,
                                'tor_size': str(size),
                                'tor_type': 'direct',
                                'priority': lazylibrarian.CONFIG[prov + '_DLPRIORITY']
                            })
                            logger.debug('Found %s, Size %s' % (title, size))
                        next_page = True

            except Exception as e:
                logger.error("An error occurred in the %s parser: %s" % (provider, str(e)))
                logger.debug('%s: %s' % (provider, traceback.format_exc()))

        page += 1
        if 0 < lazylibrarian.CONFIG['MAX_PAGES'] < page:
            logger.warn('Maximum results page search reached, still more results available')
            next_page = False

    logger.debug("Found %i result%s from %s for %s" % (len(results), plural(len(results)), provider, sterm))
    return results, errmsg
