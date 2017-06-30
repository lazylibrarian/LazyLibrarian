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
from lazylibrarian.common import scheduleJob
from lazylibrarian.csvfile import finditem
from lazylibrarian.formatter import plural, unaccented, formatAuthorName
from lazylibrarian.importer import import_book, search_for
from lazylibrarian.providers import IterateOverRSSSites, IterateOverGoodReads
from lazylibrarian.resultlist import processResultList


def cron_search_rss_book():
    if 'SEARCHALLRSS' not in [n.name for n in [t for t in threading.enumerate()]]:
        search_rss_book()


def search_rss_book(books=None, library=None):
    """
    books is a list of new books to add, or None for backlog search
    library is "eBook" or "AudioBook" or None to search all book types
    """
    try:
        threadname = threading.currentThread().name
        if "Thread-" in threadname:
            if books is None:
                threading.currentThread().name = "SEARCHALLRSS"
            else:
                threading.currentThread().name = "SEARCHRSS"

        if not (lazylibrarian.USE_RSS()):
            logger.warn('RSS search is disabled')
            scheduleJob(action='Stop', target='search_rss_book')
            return

        myDB = database.DBConnection()

        resultlist, wishproviders = IterateOverGoodReads()
        if not wishproviders:
            logger.debug('No rss wishlists are set')
        else:
            # for each item in resultlist, add to database if necessary, and mark as wanted
            for book in resultlist:
                # we get rss_author, rss_title, rss_isbn, rss_bookid (goodreads bookid)
                # we can just use bookid if goodreads, or try isbn and name matching on author/title if googlebooks
                # not sure if anyone would use a goodreads wishlist if not using goodreads interface...
                logger.debug('Processing %s item%s in wishlists' % (len(resultlist), plural(len(resultlist))))
                if book['rss_bookid'] and lazylibrarian.CONFIG['BOOK_API'] == "GoodReads":
                    bookmatch = myDB.match('select Status,BookName from books where bookid=?', (book['rss_bookid'],))
                    if bookmatch:
                        bookstatus = bookmatch['Status']
                        bookname = bookmatch['BookName']
                        if bookstatus in ['Open', 'Wanted', 'Have']:
                            logger.info(u'Found book %s, already marked as "%s"' % (bookname, bookstatus))
                        else:  # skipped/ignored
                            logger.info(u'Found book %s, marking as "Wanted"' % bookname)
                            controlValueDict = {"BookID": book['rss_bookid']}
                            newValueDict = {"Status": "Wanted"}
                            myDB.upsert("books", newValueDict, controlValueDict)
                    else:
                        import_book(book['rss_bookid'])
                else:
                    item = {}
                    headers = []
                    item['Title'] = book['rss_title']
                    if book['rss_bookid']:
                        item['BookID'] = book['rss_bookid']
                        headers.append('BookID')
                    if book['rss_isbn']:
                        item['ISBN'] = book['rss_isbn']
                        headers.append('ISBN')
                    bookmatch = finditem(item, book['rss_author'], headers)
                    if bookmatch:  # it's already in the database
                        authorname = bookmatch['AuthorName']
                        bookname = bookmatch['BookName']
                        bookid = bookmatch['BookID']
                        bookstatus = bookmatch['Status']
                        if bookstatus in ['Open', 'Wanted', 'Have']:
                            logger.info(
                                u'Found book %s by %s, already marked as "%s"' % (bookname, authorname, bookstatus))
                        else:  # skipped/ignored
                            logger.info(u'Found book %s by %s, marking as "Wanted"' % (bookname, authorname))
                            controlValueDict = {"BookID": bookid}
                            newValueDict = {"Status": "Wanted"}
                            myDB.upsert("books", newValueDict, controlValueDict)
                    else:  # not in database yet
                        results = ''
                        if book['rss_isbn']:
                            results = search_for(book['rss_isbn'])
                        if results:
                            result = results[0]
                            if result['isbn_fuzz'] > lazylibrarian.CONFIG['MATCH_RATIO']:
                                logger.info("Found (%s%%) %s: %s" %
                                            (result['isbn_fuzz'], result['authorname'], result['bookname']))
                                import_book(result['bookid'])
                                bookmatch = True
                        if not results:
                            searchterm = "%s <ll> %s" % (item['Title'], formatAuthorName(book['rss_author']))
                            results = search_for(unaccented(searchterm))
                        if results:
                            result = results[0]
                            if result['author_fuzz'] > lazylibrarian.CONFIG['MATCH_RATIO'] \
                                    and result['book_fuzz'] > lazylibrarian.CONFIG['MATCH_RATIO']:
                                logger.info("Found (%s%% %s%%) %s: %s" % (result['author_fuzz'], result['book_fuzz'],
                                                                          result['authorname'], result['bookname']))
                                import_book(result['bookid'])
                                bookmatch = True

                    if not bookmatch:
                        msg = "Skipping book %s by %s" % (item['Title'], book['rss_author'])
                        # noinspection PyUnboundLocalVariable
                        if not results:
                            msg += ', No results returned'
                            logger.warn(msg)
                        else:
                            msg += ', No match found'
                            logger.warn(msg)
                            msg = "Closest match (%s%% %s%%) %s: %s" % (result['author_fuzz'], result['book_fuzz'],
                                                                        result['authorname'], result['bookname'])
                            logger.warn(msg)

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
                for terms in results:
                    searchbooks.append(terms)

        if len(searchbooks) == 0:
            logger.debug("SearchRSS - No books to search for")
            return

        resultlist, nproviders = IterateOverRSSSites()
        if not nproviders and not wishproviders:
            logger.warn('No rss providers are available')
            return  # No point in continuing

        logger.info('RSS Searching for %i book%s' % (len(searchbooks), plural(len(searchbooks))))

        searchlist = []
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

        rss_count = 0
        for book in searchlist:
            if book['library'] == 'AudioBook':
                searchtype = 'audio'
            else:
                searchtype = 'book'
            found = processResultList(resultlist, book, searchtype, 'rss')

            # if you can't find the book, try title without any "(extended details, series etc)"
            if not found and '(' in book['bookName']:  # anything to shorten?
                searchtype = 'short' + searchtype
                found = processResultList(resultlist, book, searchtype, 'rss')

            if not found:
                logger.info("NZB Searches for %s %s returned no results." % (book['library'], book['searchterm']))
            if found > True:
                rss_count += 1

        logger.info("RSS Search for Wanted items complete, found %s book%s" % (rss_count, plural(rss_count)))

    except Exception:
        logger.error('Unhandled exception in search_rss_book: %s' % traceback.format_exc())
