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

import os
import lazylibrarian
from lazylibrarian import logger, database
from lazylibrarian.gr import GoodReads
from lazylibrarian.gb import GoogleBooks
from lazylibrarian.formatter import today
from lazylibrarian.cache import cache_cover
from lazylibrarian.bookwork import getAuthorImage


def addAuthorToDB(authorname=None, refresh=False):
    """
    Add an author to the database, and get  list of all their books
    If author already exists in database, refresh their details and booklist
    """
    try:
        myDB = database.DBConnection()

        GR = GoodReads(authorname)

        query = "SELECT * from authors WHERE AuthorName='%s'" % authorname.replace("'", "''")
        dbauthor = myDB.match(query)
        controlValueDict = {"AuthorName": authorname}

        if not dbauthor:
            newValueDict = {
                "AuthorID": "0: %s" % (authorname),
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
            authorlink = author['authorlink']
            authorimg = author['authorimg']
            controlValueDict = {"AuthorName": authorname}
            newValueDict = {
                "AuthorID": authorid,
                "AuthorLink": authorlink,
                "AuthorImg": authorimg,
                "AuthorBorn": author['authorborn'],
                "AuthorDeath": author['authordeath'],
                "DateAdded": today(),
                "Status": "Loading"
            }
            myDB.upsert("authors", newValueDict, controlValueDict)
        else:
            logger.warn(u"Nothing found for %s" % authorname)
            myDB.action('DELETE from authors WHERE AuthorName="%s"' % authorname)
            return

        new_img = False
        if authorimg and 'nophoto' in authorimg:
            authorimg = getAuthorImage(authorid)
            new_img = True
        if authorimg and authorimg.startswith('http'):
            newimg = cache_cover(authorid, authorimg)
            if newimg:
                authorimg = newimg
                new_img = True

        if new_img:
            controlValueDict = {"AuthorID": authorid}
            newValueDict = {"AuthorImg": authorimg}
            myDB.upsert("authors", newValueDict, controlValueDict)


        # process books
        if lazylibrarian.BOOK_API == "GoogleBooks":
            book_api = GoogleBooks()
            book_api.get_author_books(authorid, authorname, refresh=refresh)
        elif lazylibrarian.BOOK_API == "GoodReads":
            GR.get_author_books(authorid, authorname, refresh=refresh)

        # update totals works for existing authors only.
        # New authors need their totals updating after libraryscan or import of books.
        if dbauthor:
            update_totals(authorid)
        logger.debug("[%s] Author update complete" % authorname)
    except Exception as e:
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
