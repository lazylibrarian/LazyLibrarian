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

import traceback
import threading
import lazylibrarian
import Queue
from lib.fuzzywuzzy import fuzz

from operator import itemgetter
from lazylibrarian import logger, database
from lazylibrarian.bookwork import getAuthorImage
from lazylibrarian.cache import cache_img
from lazylibrarian.formatter import today, unaccented
from lazylibrarian.common import formatAuthorName
from lazylibrarian.gb import GoogleBooks
from lazylibrarian.gr import GoodReads


def addAuthorNameToDB(author, refresh=False, addbooks=True):
    # get authors name in a consistent format, look them up in the database
    # if not in database, try to import them.
    # return authorname,new where new=False if author already in db, new=True if added
    # authorname returned is our preferred name, or empty string if not found or unable to add
    myDB = database.DBConnection()
    new = False
    author = formatAuthorName(author)
    # Check if the author exists, and import the author if not,
    check_exist_author = myDB.match('SELECT * FROM authors where AuthorName="%s"' % author.replace('"', '""'))

    if not check_exist_author and lazylibrarian.CONFIG['ADD_AUTHOR']:
        logger.debug('Author %s not found in database, trying to add' % author)
        # no match for supplied author, but we're allowed to add new ones
        GR = GoodReads(author)
        try:
            author_gr = GR.find_author_id()
        except Exception as e:
            logger.warn("Error finding author id for [%s] %s" % (author, str(e)))
            return "", False

        # only try to add if GR data matches found author data
        if author_gr:
            authorname = author_gr['authorname']
            authorid = author_gr['authorid']
            # "J.R.R. Tolkien" is the same person as "J. R. R. Tolkien" and "J R R Tolkien"
            match_auth = author.replace('.', ' ')
            match_auth = ' '.join(match_auth.split())

            match_name = authorname.replace('.', ' ')
            match_name = ' '.join(match_name.split())

            match_name = unaccented(match_name)
            match_auth = unaccented(match_auth)

            # allow a degree of fuzziness to cater for different accented character handling.
            # some author names have accents,
            # filename may have the accented or un-accented version of the character
            # The currently non-configurable value of fuzziness might need to go in config
            # We stored GoodReads unmodified author name in
            # author_gr, so store in LL db under that
            # fuzz.ratio doesn't lowercase for us
            match_fuzz = fuzz.ratio(match_auth.lower(), match_name.lower())
            if match_fuzz < 90:
                logger.debug("Failed to match author [%s] to authorname [%s] fuzz [%d]" %
                                (author, match_name, match_fuzz))

            # To save loading hundreds of books by unknown authors at GR or GB, ignore unknown
            if (author != "Unknown") and (match_fuzz >= 90):
                # use "intact" name for author that we stored in
                # GR author_dict, not one of the various mangled versions
                # otherwise the books appear to be by a different author!
                author = author_gr['authorname']
                authorid = author_gr['authorid']
                # this new authorname may already be in the
                # database, so check again
                check_exist_author = myDB.match('SELECT AuthorID FROM authors where AuthorID="%s"' % authorid)
                if check_exist_author:
                    logger.debug('Found goodreads authorname %s in database' % author)
                else:
                    logger.info("Adding new author [%s]" % author)
                    try:
                        addAuthorToDB(authorname=author, refresh=refresh, authorid=authorid, addbooks=addbooks)
                        check_exist_author = myDB.match('SELECT AuthorID FROM authors where AuthorID="%s"' % authorid)
                        if check_exist_author:
                            new = True
                    except Exception:
                        logger.debug('Failed to add author [%s] to db' % author)
    # check author exists in db, either newly loaded or already there
    if not check_exist_author:
        logger.debug("Failed to match author [%s] in database" % author)
        return "", False
    return author, new


def addAuthorToDB(authorname=None, refresh=False, authorid=None, addbooks=True):
    """
    Add an author to the database by name or id, and optionally get a list of all their books
    If author already exists in database, refresh their details and optionally booklist
    """
    threadname = threading.currentThread().name
    if "Thread-" in threadname:
        threading.currentThread().name = "AddAuthorToDB"
    try:
        myDB = database.DBConnection()
        match = False
        authorimg = ''
        new_author = not refresh
        if authorid:
            controlValueDict = {"AuthorID": authorid}
            newValueDict = {"Status": "Loading"}

            dbauthor = myDB.match("SELECT * from authors WHERE AuthorID='%s'" % authorid)
            if not dbauthor:
                authorname = 'unknown author'
                logger.debug("Now adding new author id: %s to database" % authorid)
                new_author = True
            else:
                authorname = dbauthor['authorname']
                logger.debug("Now updating author %s " % authorname)
                new_author = False

            myDB.upsert("authors", newValueDict, controlValueDict)

            GR = GoodReads(authorname)
            author = GR.get_author_info(authorid=authorid)
            if author:
                authorname = author['authorname']
                authorimg = author['authorimg']
                controlValueDict = {"AuthorID": authorid}
                newValueDict = {
                    "AuthorLink": author['authorlink'],
                    "DateAdded": today()
                }
                if not dbauthor or (dbauthor and not dbauthor['manual']):
                    newValueDict["AuthorName"] = author['authorname']
                    newValueDict["AuthorImg"] = author['authorimg']
                    newValueDict["AuthorBorn"] = author['authorborn']
                    newValueDict["AuthorDeath"] = author['authordeath']

                myDB.upsert("authors", newValueDict, controlValueDict)
                match = True
            else:
                logger.warn(u"Nothing found for %s" % authorid)
                if not dbauthor:
                    myDB.action('DELETE from authors WHERE AuthorID="%s"' % authorid)

        if authorname and not match:
            authorname = ' '.join(authorname.split())  # ensure no extra whitespace
            GR = GoodReads(authorname)

            query = "SELECT * from authors WHERE AuthorName='%s'" % authorname.replace("'", "''")
            dbauthor = myDB.match(query)
            controlValueDict = {"AuthorName": authorname}

            if not dbauthor:
                newValueDict = {
                    "AuthorID": "0: %s" % authorname,
                    "Status": "Loading"
                }
                logger.debug("Now adding new author: %s to database" % authorname)
                new_author = True
            else:
                newValueDict = {"Status": "Loading"}
                logger.debug("Now updating author: %s" % authorname)
                new_author = False
            myDB.upsert("authors", newValueDict, controlValueDict)

            author = GR.find_author_id(refresh=refresh)
            if author:
                authorid = author['authorid']
                authorimg = author['authorimg']
                controlValueDict = {"AuthorName": authorname}
                newValueDict = {
                    "AuthorID": author['authorid'],
                    "AuthorLink": author['authorlink'],
                    "DateAdded": today(),
                    "Status": "Loading"
                }
                if not dbauthor or (dbauthor and not dbauthor['manual']):
                    newValueDict["AuthorImg"] = author['authorimg']
                    newValueDict["AuthorBorn"] = author['authorborn']
                    newValueDict["AuthorDeath"] = author['authordeath']

                myDB.upsert("authors", newValueDict, controlValueDict)
                match = True
            else:
                logger.warn(u"Nothing found for %s" % authorname)
                if not dbauthor:
                    myDB.action('DELETE from authors WHERE AuthorName="%s"' % authorname)
                return
        if not match:
            logger.error("AddAuthorToDB: No matching result for authorname or authorid")
            return

        # if author is set to manual, should we allow replacing 'nophoto' ?
        new_img = False
        match = myDB.match("SELECT Manual from authors WHERE AuthorID='%s'" % authorid)
        if not match or not match['Manual']:
            if authorimg and 'nophoto' in authorimg:
                newimg = getAuthorImage(authorid)
                if newimg:
                    authorimg = newimg
                    new_img = True

        # allow caching
        if authorimg and authorimg.startswith('http'):
            newimg, success = cache_img("author", authorid, authorimg, refresh=refresh)
            if success:
                authorimg = newimg
                new_img = True
            else:
                logger.debug('Failed to cache image for %s' % authorimg)

        if new_img:
            controlValueDict = {"AuthorID": authorid}
            newValueDict = {"AuthorImg": authorimg}
            myDB.upsert("authors", newValueDict, controlValueDict)

        if addbooks:
            if new_author:
                bookstatus = lazylibrarian.CONFIG['NEWAUTHOR_STATUS']
            else:
                bookstatus = lazylibrarian.CONFIG['NEWBOOK_STATUS']

            # process books
            if lazylibrarian.CONFIG['BOOK_API'] == "GoogleBooks":
                book_api = GoogleBooks()
                book_api.get_author_books(authorid, authorname, bookstatus, refresh=refresh)
            elif lazylibrarian.CONFIG['BOOK_API'] == "GoodReads":
                GR = GoodReads(authorname)
                GR.get_author_books(authorid, authorname, bookstatus, refresh=refresh)

            # update totals works for existing authors only.
            # New authors need their totals updating after libraryscan or import of books.
            if not new_author:
                update_totals(authorid)
        msg = "[%s] Author update complete" % authorname
        logger.debug(msg)
        return msg
    except Exception:
        msg = 'Unhandled exception in addAuthorToDB: %s' % traceback.format_exc()
        logger.error(msg)
        return msg

def update_totals(AuthorID):
    myDB = database.DBConnection()
    # author totals needs to be updated every time a book is marked differently
    match = myDB.select('SELECT AuthorID from authors WHERE AuthorID="%s"' % AuthorID)
    if not match:
        return

    lastbook = myDB.match('SELECT BookName, BookLink, BookDate from books WHERE \
                           AuthorID="%s" AND Status != "Ignored" order by BookDate DESC' % AuthorID)
    unignoredbooks = myDB.match('SELECT count("BookID") as counter FROM books WHERE \
                                 AuthorID="%s" AND Status != "Ignored"' % AuthorID)
    totalbooks = myDB.match(
        'SELECT count("BookID") as counter FROM books WHERE AuthorID="%s"' % AuthorID)
    havebooks = myDB.match('SELECT count("BookID") as counter FROM books WHERE AuthorID="%s" AND \
                            (Status="Have" OR Status="Open")' % AuthorID)
    controlValueDict = {"AuthorID": AuthorID}

    newValueDict = {
        "TotalBooks": totalbooks['counter'],
        "UnignoredBooks": unignoredbooks['counter'],
        "HaveBooks": havebooks['counter'],
        "LastBook": lastbook['BookName'] if lastbook else None,
        "LastLink": lastbook['BookLink'] if lastbook else None,
        "LastDate": lastbook['BookDate'] if lastbook else None
    }
    myDB.upsert("authors", newValueDict, controlValueDict)

def import_book(bookid):
    """ search goodreads or googlebooks for a bookid and import the book """
    myDB = database.DBConnection()
    if lazylibrarian.CONFIG['BOOK_API'] == "GoogleBooks":
        GB = GoogleBooks(bookid)
        search_api = threading.Thread(target=GB.find_book, name='GB-IMPORT', args=[bookid]).start()
    else:  # lazylibrarian.CONFIG['BOOK_API'] == "GoodReads":
        GR = GoodReads(bookid)
        search_api = threading.Thread(target=GR.find_book, name='GR-RESULTS', args=[bookid]).start()


def search_for(searchterm):
    """ search goodreads or googlebooks for a searchterm, return a list of results
    """
    myDB = database.DBConnection()
    if lazylibrarian.CONFIG['BOOK_API'] == "GoogleBooks":
        GB = GoogleBooks(searchterm)
        queue = Queue.Queue()
        search_api = threading.Thread(target=GB.find_results, name='GB-RESULTS', args=[searchterm, queue])
        search_api.start()
    else:  # lazylibrarian.CONFIG['BOOK_API'] == "GoodReads":
        queue = Queue.Queue()
        GR = GoodReads(searchterm)
        search_api = threading.Thread(target=GR.find_results, name='GR-RESULTS', args=[searchterm, queue])
        search_api.start()

    search_api.join()
    searchresults = queue.get()
    sortedlist = sorted(searchresults, key=itemgetter('highest_fuzz', 'num_reviews'), reverse=True)
    return sortedlist
