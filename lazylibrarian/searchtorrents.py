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
from lazylibrarian.providers import IterateOverTorrentSites
from lazylibrarian.resultlist import processResultList


def cron_search_tor_book():
    if 'SEARCHALLTOR' not in [n.name for n in [t for t in threading.enumerate()]]:
        search_tor_book()


def search_tor_book(books=None, library=None):
    """
    books is a list of new books to add, or None for backlog search
    library is "eBook" or "AudioBook" or None to search all book types
    """
    try:
        threadname = threading.currentThread().name
        if "Thread-" in threadname:
            if books is None:
                threading.currentThread().name = "SEARCHALLTOR"
            else:
                threading.currentThread().name = "SEARCHTOR"

        if not lazylibrarian.USE_TOR():
            logger.warn('No Torrent providers set, check config')
            return

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
                cmd += 'from books,authors WHERE BookID="%s" ' % book['bookid']
                cmd += 'AND books.AuthorID = authors.AuthorID'
                results = myDB.select(cmd)
                for terms in results:
                    searchbooks.append(terms)

        if len(searchbooks) == 0:
            logger.debug("SearchTOR - No books to search for")
            return

        logger.info('TOR Searching for %i book%s' % (len(searchbooks), plural(len(searchbooks))))

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

        tor_count = 0
        for book in searchlist:
            # first attempt, try author/title in category "book"
            if book['library'] == 'AudioBook':
                searchtype = 'audio'
            else:
                searchtype = 'book'

            resultlist, nproviders = IterateOverTorrentSites(book, searchtype)
            if not nproviders:
                logger.warn('No torrent providers are available')
                return  # No point in continuing

            found = processResultList(resultlist, book, searchtype, 'tor')

            # if you can't find the book, try author/title without any "(extended details, series etc)"
            if not found and '(' in book['bookName']:
                searchtype = 'short' + searchtype
                resultlist, nproviders = IterateOverTorrentSites(book, searchtype)
                found = processResultList(resultlist, book, searchtype, 'tor')

            # general search is the same as booksearch for torrents
            # if not found:
            #    resultlist, nproviders = IterateOverTorrentSites(book, 'general')
            #    found = processResultList(resultlist, book, "general")

            if not found:
                logger.debug("Searches for %s %s returned no results." % (book['library'], book['searchterm']))
            if found > True:
                tor_count += 1

        logger.info("TORSearch for Wanted items complete, found %s book%s" % (tor_count, plural(tor_count)))

    except Exception:
        logger.error('Unhandled exception in search_tor_book: %s' % traceback.format_exc())
