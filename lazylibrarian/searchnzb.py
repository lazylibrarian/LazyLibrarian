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
from lazylibrarian.providers import IterateOverNewzNabSites
from lazylibrarian.resultlist import processResultList


def cron_search_nzb_book():
    if 'SEARCHALLNZB' not in [n.name for n in [t for t in threading.enumerate()]]:
        search_nzb_book()


def search_nzb_book(books=None, library=None):
    """
    books is a list of new books to add, or None for backlog search
    library is "eBook" or "AudioBook" or None to search all book types
    """
    try:
        threadname = threading.currentThread().name
        if "Thread-" in threadname:
            if books is None:
                threading.currentThread().name = "SEARCHALLNZB"
            else:
                threading.currentThread().name = "SEARCHNZB"

        if not lazylibrarian.USE_NZB():
            logger.warn('No NEWZNAB/TORZNAB providers set, check config')
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
            logger.debug("SearchNZB - No books to search for")
            return

        logger.info('NZB Searching for %i book%s' % (len(searchbooks), plural(len(searchbooks))))

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

        nzb_count = 0
        for book in searchlist:
            # first attempt, try author/title in category "book"
            if book['library'] == 'AudioBook':
                searchtype = 'audio'
            else:
                searchtype = 'book'
            resultlist, nproviders = IterateOverNewzNabSites(book, searchtype)

            if not nproviders:
                logger.warn('No NewzNab or TorzNab providers are available')
                return  # no point in continuing

            found = processResultList(resultlist, book, searchtype, 'nzb')

            # if you can't find the book, try author/title without any "(extended details, series etc)"
            if not found and '(' in book['bookName']:
                searchtype = 'short' + searchtype
                resultlist, nproviders = IterateOverNewzNabSites(book, searchtype)
                found = processResultList(resultlist, book, searchtype, 'nzb')

            # if you can't find the book under "books", you might find under general search
            if not found:
                resultlist, nproviders = IterateOverNewzNabSites(book, 'general')
                found = processResultList(resultlist, book, "general", 'nzb')

            # if still not found, try general search again without any "(extended details, series etc)"
            if not found and '(' in book['bookName']:
                resultlist, nproviders = IterateOverNewzNabSites(book, 'shortgeneral')
                found = processResultList(resultlist, book, "shortgeneral", 'nzb')

            if not found:
                logger.info("NZB Searches for %s %s returned no results." % (book['library'], book['searchterm']))
            if found > True:
                nzb_count += 1  # we found it

        logger.info("NZBSearch for Wanted items complete, found %s book%s" % (nzb_count, plural(nzb_count)))

    except Exception:
        logger.error('Unhandled exception in search_nzb_book: %s' % traceback.format_exc())
