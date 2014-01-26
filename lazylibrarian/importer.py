import time, os, threading

import lazylibrarian
from lazylibrarian import logger, formatter, database
from lazylibrarian.gr import GoodReads
from lazylibrarian.gb import GoogleBooks


def addAuthorToDB(authorname=None, refresh=False):
    threading.currentThread().name = "DBIMPORT"
    type = 'author'
    myDB = database.DBConnection()

    GR = GoodReads(authorname)
    
    query = "SELECT * from authors WHERE AuthorName='%s'" % authorname.replace("'","''")
    dbauthor = myDB.action(query).fetchone()
    controlValueDict = {"AuthorName": authorname}

    if dbauthor is None:
        newValueDict = {
            "AuthorID":   "0: %s" % (authorname),
            "Status":       "Loading"
            }
        logger.info("Now adding new author: %s to database" % authorname)
    else:
        newValueDict = {"Status": "Loading"}
        logger.info("Now updating author: %s" % authorname)
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
    if lazylibrarian.BOOK_API == "GoogleBooks":
        book_api = GoogleBooks()
        book_api.get_author_books(authorid, authorname, refresh=refresh)
    elif lazylibrarian.BOOK_API == "GoodReads":
        GR.get_author_books(authorid, authorname, refresh=refresh)

    logger.info("[%s] Author update complete" % authorname)