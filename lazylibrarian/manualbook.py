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

import lazylibrarian
import urllib
from lazylibrarian.formatter import getList, unaccented_str
from lazylibrarian.common import internet
from lazylibrarian import logger
from lazylibrarian.providers import IterateOverRSSSites, IterateOverTorrentSites, IterateOverNewzNabSites
from lib.fuzzywuzzy import fuzz


def searchItem(item=None, bookid=None):
    """
    Call all active search providers asking for a "general" search for item
    return a list of results, each entry in list containing percentage_match, title, provider, size, url
    """
    results = []

    if not item:
        return results

    if not internet():
        logger.debug('Search Item: No internet connection')
        return results

    book = {}
    searchterm = unaccented_str(item)

    book['searchterm'] = searchterm
    if bookid:
        book['bookid'] = bookid
    else:
        book['bookid'] = searchterm

    nproviders = lazylibrarian.USE_NZB() + lazylibrarian.USE_TOR() + lazylibrarian.USE_RSS()
    logger.debug('Searching %s providers for %s' % (nproviders, searchterm))

    if lazylibrarian.USE_NZB():
        resultlist, nproviders = IterateOverNewzNabSites(book, 'general')
        if nproviders:
            results += resultlist
    if lazylibrarian.USE_TOR():
        resultlist, nproviders = IterateOverTorrentSites(book, 'general')
        if nproviders:
            results += resultlist
    if lazylibrarian.USE_RSS():
        resultlist, nproviders = IterateOverRSSSites()
        if nproviders:
            results += resultlist

    # reprocess to get consistent results
    searchresults = []
    for item in results:
        provider = ''
        title = ''
        url = ''
        size = ''
        date = ''
        mode = ''
        if 'nzbtitle' in item:
            title = item['nzbtitle']
        if 'nzburl' in item:
            url = item['nzburl']
        if 'nzbprov' in item:
            provider = item['nzbprov']
        if 'nzbsize' in item:
            size = item['nzbsize']
        if 'nzbdate' in item:
            date = item['nzbdate']
        if 'nzbmode' in item:
            mode = item['nzbmode']
        if 'tor_title' in item:
            title = item['tor_title']
        if 'tor_url' in item:
            url = item['tor_url']
        if 'tor_prov' in item:
            provider = item['tor_prov']
        if 'tor_size' in item:
            size = item['tor_size']
        if 'tor_date' in item:
            date = item['tor_date']
        if 'tor_type' in item:
            mode = item['tor_type']

        if title and provider and mode and url:
            # Not all results have a date or a size
            if not date:
                date = 'Fri, 01 Jan 1970 00:00:00 +0100'
            if not size:
                size = '1000'

            # calculate match percentage
            score = fuzz.token_set_ratio(searchterm, title)
            # lose a point for each extra word in the title so we get the closest match
            words = len(getList(searchterm))
            words -= len(getList(title))
            score -= abs(words)
            if score >= 40:  # ignore wildly wrong results?
                if '?' in url:
                    url = url.split('?')[0]
                result = {'score': score, 'title': title, 'provider': provider, 'size': size, 'date': date,
                          'url': urllib.quote_plus(url), 'mode': mode}

                searchresults.append(result)

            # from operator import itemgetter
            # searchresults = sorted(searchresults, key=itemgetter('score'), reverse=True)

    logger.debug('Found %s results for %s' % (len(searchresults), searchterm))
    return searchresults
