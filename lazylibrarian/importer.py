import time, os, threading

import lazylibrarian
from lazylibrarian import logger, formatter, database
from lazylibrarian.gr import GoodReads


def addBookToDB(bookid, authorname):
    type = 'book'
    myDB = database.DBConnection()
    GR = GoodReads(authorname, type)

# process book
    dbbook = myDB.action('SELECT * from books WHERE BookID=?', [bookid]).fetchone()
    controlValueDict = {"BookID": bookid}

    if dbbook is None:
        newValueDict = {
            "BookID":   "BookID: %s" % (bookid),
            "Status":       "Loading"
            }
    else:
        newValueDict = {"Status": "Loading"}
    myDB.upsert("books", newValueDict, controlValueDict)

    book = GR.find_book()

    if not book:
        logger.warn("Error fetching bookinfo for BookID: " + bookid)

    else:
        controlValueDict = {"BookID": book['bookid']}
        newValueDict = {
            "AuthorName":   book['authorname'],
            "BookName":     book['bookname'],
            "BookDesc":     book['bookdesc'],
            "BookIsbn":     book['bookisbn'],
            "BookImg":      book['bookimg'],
            "BookLink":     book['booklink'],
            "BookRate":     book['bookrate'],
            "BookPages":    book['bookpages'],
            "BookDate":     book['bookdate'],
            "BookLang":     book['booklang'],
            "Status":       "Skipped",
            "BookAdded":    formatter.today()
            }

        myDB.upsert("books", newValueDict, controlValueDict)

# process author
    dbauthor = myDB.action("SELECT * from authors WHERE AuthorName='?'", [authorname]).fetchone()
    controlValueDict = {"AuthorName": authorname}

    if dbauthor is None:
        newValueDict = {
            "AuthorName":   "Authorname: %s" % (authorname),
            "Status":       "Loading"
            }
    else:
        newValueDict = {"Status": "Loading"}

    author = GR.find_author_id()

    if not author:
        logger.warn("Error fetching authorinfo with name: " + authorname)

    else:
        controlValueDict = {"AuthorName": authorname}
        newValueDict = {
            "AuthorID":     author['authorid'],
            "AuthorLink":   author['authorlink'],
            "AuthorImg":    author['authorimg'],
            "AuthorBorn":   author['authorborn'],
            "AuthorDeath":  author['authordeath'],
            "DateAdded":    formatter.today(),
            "Status":       "Loading"
            }
        myDB.upsert("authors", newValueDict, controlValueDict)

def addAuthorToDB(authorname=None):
    threading.currentThread().name = "DBIMPORT"
    type = 'author'
    myDB = database.DBConnection()

    GR = GoodReads(authorname, type)
    
    query = "SELECT * from authors WHERE AuthorName='%s'" % authorname.replace("'","''")
    dbauthor = myDB.action(query).fetchone()
    controlValueDict = {"AuthorName": authorname}

    if dbauthor is None:
        newValueDict = {
            "AuthorID":   "0: %s" % (authorname),
            "Status":       "Loading"
            }
    else:
        newValueDict = {"Status": "Loading"}
    myDB.upsert("authors", newValueDict, controlValueDict)

    author = GR.find_author_id()
    if author:
        authorid = author['authorid']
        authorlink = author['authorlink']
        authorimg = author['authorimg']
        controlValueDict = {"AuthorName": authorname}
        newValueDict = {
            "AuthorID":     authorid,
            "AuthorLink":   authorlink,
            "AuthorImg":    authorimg,
            "AuthorBorn":   author['authorborn'],
            "AuthorDeath":  author['authordeath'],
            "DateAdded":    formatter.today(),
            "Status":       "Loading"
            }
        myDB.upsert("authors", newValueDict, controlValueDict)
    else:
        logger.error("Nothing found")

# process books

    GR.get_author_books(authorid)
