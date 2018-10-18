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


import threading
import traceback

import lazylibrarian
from lazylibrarian import logger, database
from lazylibrarian.common import scheduleJob
from lazylibrarian.csvfile import finditem
from lazylibrarian.formatter import plural, unaccented, formatAuthorName, check_int
from lazylibrarian.importer import import_book, search_for
from lazylibrarian.providers import IterateOverRSSSites, IterateOverWishLists
from lazylibrarian.resultlist import processResultList


def cron_search_rss_book():
    if 'SEARCHALLRSS' not in [n.name for n in [t for t in threading.enumerate()]]:
        search_rss_book()
    else:
        logger.debug("SEARCHALLRSS is already running")


def cron_search_wishlist():
    if 'SEARCHWISHLIST' not in [n.name for n in [t for t in threading.enumerate()]]:
        search_wishlist()
    else:
        logger.debug("SEARCHWISHLIST is already running")


# noinspection PyBroadException
def search_wishlist():
    try:
        threadname = threading.currentThread().name
        if "Thread-" in threadname:
            threading.currentThread().name = "SEARCHWISHLIST"

        myDB = database.DBConnection()

        resultlist, wishproviders = IterateOverWishLists()
        new_books = 0
        if not wishproviders:
            logger.debug('No wishlists are set')
            scheduleJob(action='Stop', target='search_wishlist')
            return  # No point in continuing

        # for each item in resultlist, add to database if necessary, and mark as wanted
        logger.debug('Processing %s item%s in wishlists' % (len(resultlist), plural(len(resultlist))))
        for book in resultlist:
            # we get rss_author, rss_title, maybe rss_isbn, rss_bookid (goodreads bookid)
            # we can just use bookid if goodreads, or try isbn and name matching on author/title if not
            # eg NYTimes wishlist
            if 'E' in book['types']:
                ebook_status = "Wanted"
            else:
                ebook_status = "Skipped"
            if 'A' in book['types']:
                audio_status = "Wanted"
            else:
                audio_status = "Skipped"
            if lazylibrarian.CONFIG['BOOK_API'] == "GoodReads" and book['rss_bookid']:
                cmd = 'select Status,AudioStatus,BookName,Requester,AudioRequester from books where bookid=?'
                bookmatch = myDB.match(cmd, (book['rss_bookid'],))
                if bookmatch:
                    bookname = bookmatch['BookName']
                    if bookmatch['Status'] in ['Open', 'Wanted', 'Have']:
                        logger.info('Found book %s, already marked as "%s"' % (bookname, bookmatch['Status']))
                        if bookmatch["Requester"]:  # Already on a wishlist
                            if book["dispname"] not in bookmatch["Requester"]:
                                newValueDict = {"Requester": bookmatch["Requester"] + book["dispname"] + ' '}
                                controlValueDict = {"BookID": book['rss_bookid']}
                                myDB.upsert("books", newValueDict, controlValueDict)
                        else:
                            newValueDict = {"Requester": book["dispname"] + ' '}
                            controlValueDict = {"BookID": book['rss_bookid']}
                            myDB.upsert("books", newValueDict, controlValueDict)
                    elif ebook_status == "Wanted":  # skipped/ignored
                        logger.info('Found book %s, marking as "Wanted"' % bookname)
                        controlValueDict = {"BookID": book['rss_bookid']}
                        newValueDict = {"Status": "Wanted"}
                        myDB.upsert("books", newValueDict, controlValueDict)
                        new_books += 1
                        if bookmatch["Requester"]:  # Already on a wishlist
                            if book["dispname"] not in bookmatch["Requester"]:
                                newValueDict = {"Requester": bookmatch["Requester"] + book["dispname"] + ' '}
                                controlValueDict = {"BookID": book['rss_bookid']}
                                myDB.upsert("books", newValueDict, controlValueDict)
                        else:
                            newValueDict = {"Requester": book["dispname"] + ' '}
                            controlValueDict = {"BookID": book['rss_bookid']}
                            myDB.upsert("books", newValueDict, controlValueDict)
                    if bookmatch['AudioStatus'] in ['Open', 'Wanted', 'Have']:
                        logger.info('Found audiobook %s, already marked as "%s"' % (bookname, bookmatch['AudioStatus']))
                        if bookmatch["AudioRequester"]:  # Already on a wishlist
                            if book["dispname"] not in bookmatch["AudioRequester"]:
                                newValueDict = {"AudioRequester": bookmatch["AudioRequester"] + book["dispname"] + ' '}
                                controlValueDict = {"BookID": book['rss_bookid']}
                                myDB.upsert("books", newValueDict, controlValueDict)
                        else:
                            newValueDict = {"AudioRequester": book["dispname"] + ' '}
                            controlValueDict = {"BookID": book['rss_bookid']}
                            myDB.upsert("books", newValueDict, controlValueDict)
                    elif audio_status == "Wanted":  # skipped/ignored
                        logger.info('Found audiobook %s, marking as "Wanted"' % bookname)
                        controlValueDict = {"BookID": book['rss_bookid']}
                        newValueDict = {"AudioStatus": "Wanted"}
                        myDB.upsert("books", newValueDict, controlValueDict)
                        new_books += 1
                        if bookmatch["AudioRequester"]:  # Already on a wishlist
                            if book["dispname"] not in bookmatch["AudioRequester"]:
                                newValueDict = {"AudioRequester": bookmatch["AudioRequester"] + book["dispname"] + ' '}
                                controlValueDict = {"BookID": book['rss_bookid']}
                                myDB.upsert("books", newValueDict, controlValueDict)
                        else:
                            newValueDict = {"AudioRequester": book["dispname"] + ' '}
                            controlValueDict = {"BookID": book['rss_bookid']}
                            myDB.upsert("books", newValueDict, controlValueDict)
                else:
                    import_book(book['rss_bookid'], ebook_status, audio_status)
                    new_books += 1
                    newValueDict = {"Requester": book["dispname"] + ' '}
                    controlValueDict = {"BookID": book['rss_bookid']}
                    myDB.upsert("books", newValueDict, controlValueDict)
                    newValueDict = {"AudioRequester": book["dispname"] + ' '}
                    controlValueDict = {"BookID": book['rss_bookid']}
                    myDB.upsert("books", newValueDict, controlValueDict)
            else:
                item = {}
                results = None
                item['Title'] = book['rss_title']
                if book['rss_bookid']:
                    item['BookID'] = book['rss_bookid']
                if book['rss_isbn']:
                    item['ISBN'] = book['rss_isbn']
                bookmatch = finditem(item, book['rss_author'])
                if bookmatch:  # it's already in the database
                    authorname = bookmatch['AuthorName']
                    bookname = bookmatch['BookName']
                    bookid = bookmatch['BookID']
                    if bookmatch['Status'] in ['Open', 'Wanted', 'Have']:
                        logger.info(
                            'Found book %s by %s, already marked as "%s"' % (bookname, authorname, bookmatch['Status']))
                        if bookmatch["Requester"]:  # Already on a wishlist
                            if book["dispname"] not in bookmatch["Requester"]:
                                newValueDict = {"Requester": bookmatch["Requester"] + book["dispname"] + ' '}
                                controlValueDict = {"BookID": bookid}
                                myDB.upsert("books", newValueDict, controlValueDict)
                        else:
                            newValueDict = {"Requester": book["dispname"] + ' '}
                            controlValueDict = {"BookID": bookid}
                            myDB.upsert("books", newValueDict, controlValueDict)
                    elif ebook_status == 'Wanted':  # skipped/ignored
                        logger.info('Found book %s by %s, marking as "Wanted"' % (bookname, authorname))
                        controlValueDict = {"BookID": bookid}
                        newValueDict = {"Status": "Wanted"}
                        myDB.upsert("books", newValueDict, controlValueDict)
                        new_books += 1
                        if bookmatch["Requester"]:  # Already on a wishlist
                            if book["dispname"] not in bookmatch["Requester"]:
                                newValueDict = {"Requester": bookmatch["Requester"] + book["dispname"] + ' '}
                                controlValueDict = {"BookID": bookid}
                                myDB.upsert("books", newValueDict, controlValueDict)
                        else:
                            newValueDict = {"Requester": book["dispname"] + ' '}
                            controlValueDict = {"BookID": bookid}
                            myDB.upsert("books", newValueDict, controlValueDict)
                    if bookmatch['AudioStatus'] in ['Open', 'Wanted', 'Have']:
                        logger.info(
                            'Found audiobook %s by %s, already marked as "%s"' %
                            (bookname, authorname, bookmatch['AudioStatus']))
                        if bookmatch["AudioRequester"]:  # Already on a wishlist
                            if book["dispname"] not in bookmatch["AudioRequester"]:
                                newValueDict = {"AudioRequester": bookmatch["AudioRequester"] + book["dispname"] + ' '}
                                controlValueDict = {"BookID": bookid}
                                myDB.upsert("books", newValueDict, controlValueDict)
                        else:
                            newValueDict = {"AudioRequester": book["dispname"] + ' '}
                            controlValueDict = {"BookID": bookid}
                            myDB.upsert("books", newValueDict, controlValueDict)
                    elif audio_status == 'Wanted':  # skipped/ignored
                        logger.info('Found audiobook %s by %s, marking as "Wanted"' % (bookname, authorname))
                        controlValueDict = {"BookID": bookid}
                        newValueDict = {"AudioStatus": "Wanted"}
                        myDB.upsert("books", newValueDict, controlValueDict)
                        new_books += 1
                        if bookmatch["AudioRequester"]:  # Already on a wishlist
                            if book["dispname"] not in bookmatch["AudioRequester"]:
                                newValueDict = {"AudioRequester": bookmatch["AudioRequester"] + book["dispname"] + ' '}
                                controlValueDict = {"BookID": bookid}
                                myDB.upsert("books", newValueDict, controlValueDict)
                        else:
                            newValueDict = {"AudioRequester": book["dispname"] + ' '}
                            controlValueDict = {"BookID": bookid}
                            myDB.upsert("books", newValueDict, controlValueDict)
                else:  # not in database yet
                    if book['rss_isbn']:
                        results = search_for(book['rss_isbn'])
                    if results:
                        result = results[0]  # type: dict
                        if result['isbn_fuzz'] > check_int(lazylibrarian.CONFIG['MATCH_RATIO'], 90):
                            logger.info("Found (%s%%) %s: %s" %
                                        (result['isbn_fuzz'], result['authorname'], result['bookname']))
                            import_book(result['bookid'], ebook_status, audio_status)
                            new_books += 1
                            newValueDict = {"Requester": book["dispname"] + ' '}
                            controlValueDict = {"BookID": result['bookid']}
                            myDB.upsert("books", newValueDict, controlValueDict)
                            newValueDict = {"AudioRequester": book["dispname"] + ' '}
                            myDB.upsert("books", newValueDict, controlValueDict)
                            bookmatch = True
                    if not results:
                        searchterm = "%s <ll> %s" % (item['Title'], formatAuthorName(book['rss_author']))
                        results = search_for(unaccented(searchterm))
                    if results:
                        result = results[0]  # type: dict
                        if result['author_fuzz'] > check_int(lazylibrarian.CONFIG['MATCH_RATIO'], 90) \
                                and result['book_fuzz'] > check_int(lazylibrarian.CONFIG['MATCH_RATIO'], 90):
                            logger.info("Found (%s%% %s%%) %s: %s" % (result['author_fuzz'], result['book_fuzz'],
                                                                      result['authorname'], result['bookname']))
                            import_book(result['bookid'], ebook_status, audio_status)
                            new_books += 1
                            newValueDict = {"Requester": book["dispname"] + ' '}
                            controlValueDict = {"BookID": result['bookid']}
                            myDB.upsert("books", newValueDict, controlValueDict)
                            newValueDict = {"AudioRequester": book["dispname"] + ' '}
                            myDB.upsert("books", newValueDict, controlValueDict)
                            bookmatch = True

                    if not bookmatch:
                        msg = "Skipping book %s by %s" % (item['Title'], book['rss_author'])
                        if not results:
                            msg += ', No results returned'
                            logger.warn(msg)
                        else:
                            msg += ', No match found'
                            logger.warn(msg)
                            result = results[0]  # type: dict
                            msg = "Closest match (%s%% %s%%) %s: %s" % (result['author_fuzz'], result['book_fuzz'],
                                                                        result['authorname'], result['bookname'])
                        logger.warn(msg)
        if new_books:
            logger.info("Wishlist marked %s book%s as Wanted" % (new_books, plural(new_books)))

    except Exception:
        logger.error('Unhandled exception in search_wishlist: %s' % traceback.format_exc())
    finally:
        threading.currentThread().name = "WEBSERVER"


# noinspection PyBroadException
def search_rss_book(books=None, library=None):
    """
    books is a list of new books to add, or None for backlog search
    library is "eBook" or "AudioBook" or None to search all book types
    """
    if not (lazylibrarian.USE_RSS()):
        logger.warn('RSS search is disabled')
        scheduleJob(action='Stop', target='search_rss_book')
        return
    try:
        threadname = threading.currentThread().name
        if "Thread-" in threadname:
            if not books:
                threading.currentThread().name = "SEARCHALLRSS"
            else:
                threading.currentThread().name = "SEARCHRSS"

        myDB = database.DBConnection()

        searchbooks = []
        if not books:
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

        resultlist, nproviders, _ = IterateOverRSSSites()
        if not nproviders:
            logger.warn('No rss providers are available')
            scheduleJob(action='Stop', target='search_rss_book')
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
                    cmd = 'SELECT BookID from wanted WHERE BookID=? and AuxInfo="eBook" and Status="Snatched"'
                    snatched = myDB.match(cmd, (searchbook["BookID"],))
                    if snatched:
                        logger.warn('eBook %s %s already marked snatched in wanted table' %
                                    (searchbook['AuthorName'], searchbook['BookName']))
                    else:
                        searchlist.append(
                            {"bookid": searchbook['BookID'],
                             "bookName": searchbook['BookName'],
                             "bookSub": searchbook['BookSub'],
                             "authorName": searchbook['AuthorName'],
                             "library": "eBook",
                             "searchterm": searchterm})

            if library is None or library == 'AudioBook':
                if searchbook['AudioStatus'] == "Wanted":
                    cmd = 'SELECT BookID from wanted WHERE BookID=? and AuxInfo="AudioBook" and Status="Snatched"'
                    snatched = myDB.match(cmd, (searchbook["BookID"],))
                    if snatched:
                        logger.warn('AudioBook %s %s already marked snatched in wanted table' %
                                    (searchbook['AuthorName'], searchbook['BookName']))
                    else:
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
                logger.info("RSS Searches for %s %s returned no results." % (book['library'], book['searchterm']))
            if found > 1:
                rss_count += 1

        logger.info("RSS Search for Wanted items complete, found %s book%s" % (rss_count, plural(rss_count)))

    except Exception:
        logger.error('Unhandled exception in search_rss_book: %s' % traceback.format_exc())
    finally:
        threading.currentThread().name = "WEBSERVER"
