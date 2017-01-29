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
from lazylibrarian import logger, database
from lazylibrarian.bookwork import getAuthorImage
from lazylibrarian.cache import cache_cover
from lazylibrarian.formatter import today
from lazylibrarian.gb import GoogleBooks
from lazylibrarian.gr import GoodReads


def addAuthorToDB(authorname=None, refresh=False, authorid=None):
    """
    Add an author to the database by name or id, and get a list of all their books
    If author already exists in database, refresh their details and booklist
    """
    threadname = threading.currentThread().name
    if "Thread-" in threadname:
        threading.currentThread().name = "AddAuthorToDB"
    try:
        myDB = database.DBConnection()
        match = False
        authorimg = ''
        if authorid:
            controlValueDict = {"AuthorID": authorid}
            newValueDict = {"Status": "Loading"}

            dbauthor = myDB.match("SELECT * from authors WHERE AuthorID='%s'" % authorid)
            if not dbauthor:
                authorname = 'unknown author'
                logger.debug("Now adding new author id: %s to database" % authorid)
            else:
                authorname = dbauthor['authorname']
                logger.debug("Now updating author %s " % authorname)

            myDB.upsert("authors", newValueDict, controlValueDict)

            GR = GoodReads(authorname)
            author = GR.get_author_info(authorid=authorid, authorname=authorname)
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
                GR = GoodReads(authorname)
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
            else:
                newValueDict = {"Status": "Loading"}
                logger.debug("Now updating author: %s" % authorname)
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
        dbauthor = myDB.match("SELECT Manual from authors WHERE AuthorID='%s'" % authorid)
        if not dbauthor['Manual']:
            if authorimg and 'nophoto' in authorimg:
                authorimg = getAuthorImage(authorid)
                new_img = True

        # allow caching
        if authorimg and authorimg.startswith('http'):
            newimg = cache_cover(authorid, authorimg)
            if newimg:
                authorimg = newimg
                new_img = True

        if new_img:
            controlValueDict = {"AuthorID": authorid}
            newValueDict = {"AuthorImg": authorimg}
            myDB.upsert("authors", newValueDict, controlValueDict)

        if dbauthor:
            bookstatus = lazylibrarian.NEWBOOK_STATUS
        else:
            bookstatus = lazylibrarian.NEWAUTHOR_STATUS

        # process books
        if lazylibrarian.BOOK_API == "GoogleBooks":
            book_api = GoogleBooks()
            book_api.get_author_books(authorid, authorname, bookstatus, refresh=refresh)
        elif lazylibrarian.BOOK_API == "GoodReads":
            GR = GoodReads(authorname)
            GR.get_author_books(authorid, authorname, bookstatus, refresh=refresh)

        # update totals works for existing authors only.
        # New authors need their totals updating after libraryscan or import of books.
        if dbauthor:
            update_totals(authorid)
        logger.debug("[%s] Author update complete" % authorname)
    except Exception:
        logger.error('Unhandled exception in addAuthorToDB: %s' % traceback.format_exc())


def update_totals(AuthorID):
    myDB = database.DBConnection()
    # author totals needs to be updated every time a book is marked differently
    authorsearch = myDB.select('SELECT * from authors WHERE AuthorID="%s"' % AuthorID)
    if not authorsearch:
        return

    lastbook = myDB.match('SELECT BookName, BookLink, BookDate from books WHERE \
                           AuthorID="%s" AND Status != "Ignored" order by BookDate DESC' %
                          AuthorID)
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
