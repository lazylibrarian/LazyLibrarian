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

import threading
import traceback

import lazylibrarian
from lazylibrarian import logger, database
from lazylibrarian.formatter import plural
from lazylibrarian.providers import IterateOverNewzNabSites, IterateOverTorrentSites, IterateOverRSSSites, \
    IterateOverDirectSites
from lazylibrarian.resultlist import findBestResult, downloadResult


def cron_search_book():
    if 'SEARCHALLBOOKS' not in [n.name for n in [t for t in threading.enumerate()]]:
        search_book()
    else:
        logger.debug("SEARCHALLBOOKS is already running")


def goodEnough(match):
    if match and int(match[0]) >= int(lazylibrarian.CONFIG['MATCH_RATIO']):
        return True
    return False


def search_book(books=None, library=None):
    """
    books is a list of new books to add, or None for backlog search
    library is "eBook" or "AudioBook" or None to search all book types
    """
    # noinspection PyBroadException
    try:
        threadname = threading.currentThread().name
        if "Thread-" in threadname:
            if books is None:
                threading.currentThread().name = "SEARCHALLBOOKS"
            else:
                threading.currentThread().name = "SEARCHBOOKS"

        myDB = database.DBConnection()
        searchlist = []
        searchbooks = []

        if books is None:
            # We are performing a backlog search
            cmd = 'SELECT BookID, AuthorName, Bookname, BookSub, BookAdded, books.Status, AudioStatus '
            cmd += 'from books,authors WHERE (books.Status="Wanted" OR AudioStatus="Wanted") '
            cmd += 'and books.AuthorID = authors.AuthorID order by BookAdded desc'
            results = myDB.select(cmd)
            for terms in results:
                searchbooks.append(terms)
        else:
            # The user has added a new book
            for book in books:
                cmd = 'SELECT BookID, AuthorName, BookName, BookSub, books.Status, AudioStatus '
                cmd += 'from books,authors WHERE BookID=? AND books.AuthorID = authors.AuthorID'
                results = myDB.select(cmd, (book['bookid'],))
                if results:
                    for terms in results:
                        searchbooks.append(terms)
                else:
                    logger.debug("SearchBooks - BookID %s is not in the database" % book['bookid'])

        if len(searchbooks) == 0:
            logger.debug("SearchBooks - No books to search for")
            return

        nproviders = lazylibrarian.USE_NZB() + lazylibrarian.USE_TOR() + \
                     lazylibrarian.USE_RSS() + lazylibrarian.USE_DIRECT()

        if nproviders == 0:
            logger.debug("SearchBooks - No providers to search")
            return

        modelist = []
        if lazylibrarian.USE_NZB():
            modelist.append('nzb')
        if lazylibrarian.USE_TOR():
            modelist.append('tor')
        if lazylibrarian.USE_DIRECT():
            modelist.append('direct')
        if lazylibrarian.USE_RSS():
            modelist.append('rss')

        logger.info('Searching %s provider%s %s for %i book%s' %
                    (nproviders, plural(nproviders), str(modelist), len(searchbooks), plural(len(searchbooks))))

        for searchbook in searchbooks:
            # searchterm is only used for display purposes
            searchterm = searchbook['AuthorName'] + ' ' + searchbook['BookName']
            if searchbook['BookSub']:
                searchterm = searchterm + ': ' + searchbook['BookSub']

            if library is None or library == 'eBook':
                if searchbook['Status'] == "Wanted":
                    searchlist.append(
                        {"bookid": searchbook['BookID'],
                         "bookName": searchbook['BookName'],
                         "bookSub": searchbook['BookSub'],
                         "authorName": searchbook['AuthorName'],
                         "library": "eBook",
                         "searchterm": searchterm})

            if library is None or library == 'AudioBook':
                if searchbook['AudioStatus'] == "Wanted":
                    searchlist.append(
                        {"bookid": searchbook['BookID'],
                         "bookName": searchbook['BookName'],
                         "bookSub": searchbook['BookSub'],
                         "authorName": searchbook['AuthorName'],
                         "library": "AudioBook",
                         "searchterm": searchterm})

        # only get rss results once per run, as they are not search specific
        rss_resultlist = None
        if 'rss' in modelist:
            rss_resultlist, nproviders = IterateOverRSSSites()
            if not nproviders:
                modelist.remove('rss')

        book_count = 0
        for book in searchlist:
            matches = []
            for mode in modelist:
                # first attempt, try author/title in category "book"
                if book['library'] == 'AudioBook':
                    searchtype = 'audio'
                else:
                    searchtype = 'book'

                resultlist = None
                if mode == 'nzb':
                    resultlist, nproviders = IterateOverNewzNabSites(book, searchtype)
                    if not nproviders:
                        logger.debug("No active nzb providers found")
                        if 'nzb' in modelist:
                            modelist.remove('nzb')
                elif mode == 'tor':
                    resultlist, nproviders = IterateOverTorrentSites(book, searchtype)
                    if not nproviders:
                        logger.debug("No active tor providers found")
                        if 'tor' in modelist:
                            modelist.remove('tor')
                elif mode == 'direct':
                    resultlist, nproviders = IterateOverDirectSites(book, searchtype)
                    if not nproviders:
                        logger.debug("No active direct providers found")
                        if 'direct' in modelist:
                            modelist.remove('direct')
                elif mode == 'rss':
                    if rss_resultlist:
                        resultlist = rss_resultlist
                    else:
                        logger.debug("No active rss providers found")
                        if 'rss' in modelist:
                            modelist.remove('rss')

                if resultlist:
                    match = findBestResult(resultlist, book, searchtype, mode)
                else:
                    match = None

                # if you can't find the book, try author/title without any "(extended details, series etc)"
                if not goodEnough(match) and '(' in book['bookName']:
                    searchtype = 'short' + searchtype
                    if mode == 'nzb':
                        resultlist, nproviders = IterateOverNewzNabSites(book, searchtype)
                        if not nproviders:
                            logger.debug("No active nzb providers found")
                            if 'nzb' in modelist:
                                modelist.remove('nzb')
                    elif mode == 'tor':
                        resultlist, nproviders = IterateOverTorrentSites(book, searchtype)
                        if not nproviders:
                            logger.debug("No active tor providers found")
                            if 'tor' in modelist:
                                modelist.remove('tor')
                    elif mode == 'direct':
                        resultlist, nproviders = IterateOverDirectSites(book, searchtype)
                        if not nproviders:
                            logger.debug("No active direct providers found")
                            if 'direct' in modelist:
                                modelist.remove('direct')
                    elif mode == 'rss':
                        resultlist = rss_resultlist

                    if resultlist:
                        match = findBestResult(resultlist, book, searchtype, mode)
                    else:
                        match = None

                # if you can't find the book under "books", you might find under general search
                # general search is the same as booksearch for torrents and rss, no need to check again
                if not goodEnough(match):
                    searchtype = 'general'
                    if mode == 'nzb':
                        resultlist, nproviders = IterateOverNewzNabSites(book, searchtype)
                        if not nproviders:
                            logger.debug("No active nzb providers found")
                            modelist.remove('nzb')
                        if resultlist:
                            match = findBestResult(resultlist, book, searchtype, mode)
                        else:
                            match = None

                # if still not found, try general search again without any "(extended details, series etc)"
                if not goodEnough(match) and '(' in book['searchterm']:
                    searchtype = 'shortgeneral'
                    if mode == 'nzb':
                        resultlist, _ = IterateOverNewzNabSites(book, searchtype)
                        if not nproviders:
                            logger.debug("No active nzb providers found")
                            if 'nzb' in modelist:
                                modelist.remove('nzb')
                        if resultlist:
                            match = findBestResult(resultlist, book, searchtype, mode)
                        else:
                            match = None

                if not goodEnough(match):
                    logger.info("%s Searches for %s %s returned no results." %
                                (mode.upper(), book['library'], book['searchterm']))
                else:
                    logger.info("Found %s result: %s %s%%, %s priority %s" %
                                (mode.upper(), searchtype, match[0], match[2]['NZBprov'], match[4]))
                    matches.append(match)

            if matches:
                highest = max(matches, key=lambda s: (s[0], s[4]))  # sort on percentage and priority
                logger.info("Requesting %s download: %s%% %s: %s" %
                            (book['library'], highest[0], highest[2]['NZBprov'], highest[1]))
                if downloadResult(highest, book) > True:
                    book_count += 1  # we found it

        logger.info("Search for Wanted items complete, found %s book%s" % (book_count, plural(book_count)))

    except Exception:
        logger.error('Unhandled exception in search_book: %s' % traceback.format_exc())
