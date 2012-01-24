import time
import os

import lazylibrarian
from lazylibrarian import logger, formatter, database
from lazylibrarian.gr import GoodReads

def is_exists(authorid):

    myDB = database.DBConnection()

    # See if the author is already in the database
    authorlist = myDB.select('SELECT AuthorID, AuthorName from authors WHERE AuthorID=?', [authorid])

    if any(authorid in x for x in authorlist):
        logger.info(authorlist[0][1] + u" is already in the database. Updating books only.")
        return True
    else:
        return False


def authorlist_to_grids(authorlist, forced=False):

    for author in authorlist:
        GR = GoodReads()

        if forced:
            author = unicode(author, 'utf-8')

        results = GR.find_author_name(author, limit=1)

        if not results:
            logger.info('No results found for: %s' % author)
            continue

        try:
            authorid = results[0]['authorid']

        except IndexError:
            logger.info('GoodReads query turned up no matches for: %s' % author)
            continue

        # Add to database if it doesn't exist
        if not is_exists(authorid):
            addAuthortoDB(authorid)

        # Just update the books if it does
        else:
            myDB = db.DBConnection()
            havebooks = len(myDB.select('SELECT BookName from books WHERE AuthorID=?', [authorid])) + len(myDB.select('SELECT BookName from have WHERE AuthorName like ?', [authorname]))
            myDB.action('UPDATE authors SET HaveBooks=? WHERE AuthorID=?', [havebooks, authorid])

def addAuthorToDB(authorid):

    myDB = database.DBConnection()

    # We need the current minimal info in the database instantly
    # so we don't throw a 500 error when we redirect to the authorPage

    controlValueDict = {"AuthorID": authorid}

    # Don't replace a known author name with an "Artist ID" placeholder
    dbauthor = myDB.action('SELECT * FROM authors WHERE AuthorID=?', [authorid]).fetchone()
    if dbauthor is None:
        newValueDict = {
            "AuthorName":   "Author ID: %s" % (authorid),
            "Status":       "Loading"
            }
    else:
        newValueDict = {"Status": "Loading"}

    myDB.upsert("authors", newValueDict, controlValueDict)

    GR = GoodReads()
    author = GR.get_author_info(authorid)

    if not author:
        logger.warn("Error fetching author with ID: " + authorid)
        if dbauthor is None:
            newValueDict = {
                "AuthorName":   "Fetch failed for author ID: %s, try refreshing." % (authorid),
                "Status":       "Active"
                }
        else:
            newValueDict = {"Status": "Active"}
        myDB.upsert("authors", newValueDict, controlValueDict)
        return
    else:
        logger.info('Adding author to database')

    controlValueDict = {
        "AuthorID": authorid
        }

    newValueDict = {
        "AuthorName":   author['authorname'],
        "AuthorLink":   author['authorlink'],
        "AuthorImgs":   author['authorimg_s'],
        "AuthorImgl":   author['authorimg_l'],
        "AuthorBorn":   author['authorborn'],
        "AuthorDeath":  author['authordeath'],
        "TotalBooks":   author['totalbooks'],
        "DateAdded":    formatter.today(),
        "Status":       "Loading"
        }

    myDB.upsert("authors", newValueDict, controlValueDict)

    # now process books
    if not len(author['books']):
        logger.warn("Error processing books for author ID: " + authorid)
    else:
        logger.info("Adding books to database")

    bookcount = 0
    isbncount = 0
    langcount = 0

    for book in author['books']:

        bookcount = bookcount+1
        controlValueDict = {
            "BookID": book['bookid']
            }

        # need to build a language list here
        isbn = book['bookisbn']
        if isbn:
            if formatter.is_valid_isbn(isbn):
                isbncount = isbncount+1
                if str(isbn)[0] == '0' or str(isbn)[0] == '1':
                    booklang = 'en'
                    langcount = langcount+1
                elif str(isbn)[0] == '2':
                    booklang = 'fr'
                    langcount = langcount+1
                elif str(isbn)[0] == '3':
                    booklang = 'ge'
                    langcount = langcount+1
                elif str(isbn)[0] == '4':
                    booklang = 'ja'
                    langcount = langcount+1
                elif str(isbn)[0] == '5':
                    booklang = 'ru'
                    langcount = langcount+1
                elif str(isbn)[0] == '7':
                    booklang = 'ch'
                    langcount = langcount+1
                elif str(isbn)[:2] == '90' or str(isbn)[:2] == '94':
                    booklang = 'nl'
                    langcount = langcount+1
                else:
                    booklang = None
            else:
                booklang = None
        else:
            booklang = None

        newValueDict = {
            "AuthorID":     authorid,
            "AuthorName":   author['authorname'],
            "AuthorLink":   author['authorlink'],
            "BookName":     str.strip(book['bookname']),
            "BookIsbn":     book['bookisbn'],
            "BookImgs":     book['bookimg_s'],
            "BookImgl":     book['bookimg_l'],
            "BookLink":     book['booklink'],
            "BookRate":     book['bookrate'],
            "BookPages":    book['bookpages'],
            "BookDate":     book['bookdate'],
            "BookLang":     booklang,
            "DateAdded":    formatter.today()
            }

        myDB.upsert("books", newValueDict, controlValueDict)

    controlValueDict = {"AuthorID": authorid}
    newValueDict = {"Status": "Active"}

    myDB.upsert("authors", newValueDict, controlValueDict)

    logger.debug("Added %s books, %s with ISBN, language found for %s books." % (str(bookcount), str(isbncount), str(langcount)))
    logger.info(u"Processing complete for authorID: " + authorid)
