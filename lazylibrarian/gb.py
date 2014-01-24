# example
# https://www.googleapis.com/books/v1/volumes?q=+inauthor:george+martin+intitle:song+ice+fire

import urllib, urllib2, json, time, sys, re
from urllib2 import HTTPError

import lazylibrarian
from lazylibrarian import logger, formatter, database, SimpleCache

import lib.fuzzywuzzy as fuzzywuzzy
from lib.fuzzywuzzy import fuzz, process

class GoogleBooks:

    def __init__(self, name=None, type=None):
        self.name = name
        self.type = type
        self.url = 'https://www.googleapis.com/books/v1/volumes?q='
        self.params = {
            'maxResults': 40,
            'printType': 'books',
            }


    def find_results(self, authorname=None):
        resultlist = []
        api_strings = ['inauthor:', 'intitle:', 'isbn:']

        for api_value in api_strings:
            if api_value == "isbn:":
                set_url = self.url + urllib.quote(api_value + self.name)
            else:
                set_url = self.url + urllib.quote(api_value + '"' + self.name + '"')

            logger.info('Searching url: ' + set_url)

            try:
                startindex = 0
                resultcount = 0
                ignored = 0
                while True:

                    self.params['startIndex'] = startindex
                    URL = set_url + '&' + urllib.urlencode(self.params)

                    try:
                        jsonresults = json.JSONDecoder().decode(urllib2.urlopen(URL, timeout=30).read())
                    except HTTPError, err:
                        logger.Error('Google API returned HTTP Error - probably time/rate limiting - [%s]' % err.msg)
                        
                    startindex = startindex+40

                    for item in jsonresults['items']:

                        # skip if no author, no author is no book.
                        try:
                            Author = item['volumeInfo']['authors'][0]
                        except KeyError:
                            logger.debug('Skipped a result without authorfield.')
                            break

                        try:
                            #skip if language is in ignore list
                            booklang = item['volumeInfo']['language']
                            if not booklang in lazylibrarian.IMP_PREFLANG:
                                ignored = ignored+1
                                break
                        except KeyError:
                            ignored = ignored+1
                            logger.debug('Skipped a result where no language is found')
                            break

                        try:
                            bookpub = item['volumeInfo']['publisher']
                        except KeyError:
                            bookpub = None

                        try:
                            booksub = item['volumeInfo']['subtitle']
                        except KeyError:
                            booksub = None

                        try:
                            bookdate = item['volumeInfo']['publishedDate']
                        except KeyError:
                            bookdate = '0000-00-00'
                        bookdate = bookdate[:4]

                        try:
                            bookimg = item['volumeInfo']['imageLinks']['thumbnail']
                        except KeyError:
                            bookimg = 'images/nocover.png'

                        try:
                            bookrate = item['volumeInfo']['averageRating']
                        except KeyError:
                            bookrate = 0

                        try:
                            bookpages = item['volumeInfo']['pageCount']
                        except KeyError:
                            bookpages = '0'

                        try:
                            bookgenre = item['volumeInfo']['categories'][0]
                        except KeyError:
                            bookgenre = None

                        try:
                            bookdesc = item['volumeInfo']['description']
                        except KeyError:
                            bookdesc = 'Not available'

                        try:
                            if item['volumeInfo']['industryIdentifiers'][0]['type'] == 'ISBN_10':
                                bookisbn = item['volumeInfo']['industryIdentifiers'][0]['identifier']
                            else:
                                bookisbn = 0
                        except KeyError:
                            bookisbn = 0

                        author_fuzz = fuzz.ratio(Author.lower(), authorname.lower())
                        book_fuzz = fuzz.ratio(item['volumeInfo']['title'].lower(), authorname.lower())
                        try:
                            isbn_check = int(authorname[:-1])
                            if (len(str(isbn_check)) == 9) or (len(str(isbn_check)) == 12):
                                isbn_fuzz = int(100)
                            else:
                                isbn_fuzz = int(0)
                        except:
                            isbn_fuzz = int(0)
                        highest_fuzz = max(author_fuzz, book_fuzz, isbn_fuzz)

                        resultlist.append({
                            'authorname': Author,
                            'bookid': item['id'],
                            'bookname': item['volumeInfo']['title'],
                            'booksub': booksub,
                            'bookisbn': bookisbn,
                            'bookpub': bookpub,
                            'bookdate': bookdate,
                            'booklang': booklang,
                            'booklink': item['volumeInfo']['canonicalVolumeLink'],
                            'bookrate': float(bookrate),
                            'bookimg': bookimg,
                            'bookpages': bookpages,
                            'bookgenre': bookgenre,
                            'bookdesc': bookdesc,
                            'author_fuzz': author_fuzz,
                            'book_fuzz': book_fuzz,
                            'isbn_fuzz': isbn_fuzz,
                            'highest_fuzz': highest_fuzz
                            })

                        resultcount = resultcount+1

            except KeyError:
                logger.info('Found %s results for %s with value: %s' % (resultcount, api_value, self.name))
                if ignored > 0:
                    logger.info('Skipped %s results because it is not a preferred language.' % ignored)

        return resultlist

    def get_author_books(self, authorid=None, authorname=None, refresh=False):
        books_dict=[]
        set_url = self.url + urllib.quote('inauthor:' + '"' + authorname + '"')

        logger.info('[%s] Now updating book list' % authorname)
        logger.info('[%s] Searching url: %s' % (authorname, set_url))

        #Artist is loading
        myDB = database.DBConnection()
        controlValueDict = {"AuthorID": authorid}
        newValueDict = {"Status": "Loading"}
        myDB.upsert("authors", newValueDict, controlValueDict)

        try:
            startindex = 0
            resultcount = 0
            removedResults = 0
            ignored = 0
            added_count = 0
            updated_count = 0
            while True:

                self.params['startIndex'] = startindex
                URL = set_url + '&' + urllib.urlencode(self.params)

                try:
                    jsonresults = json.JSONDecoder().decode(urllib2.urlopen(URL, timeout=30).read())
                except HTTPError, err:
                    logger.Error('Google API returned HTTP Error - probably time/rate limiting - [%s]' % err.msg)
                    
                startindex = startindex+40

                for item in jsonresults['items']:

                    # skip if no author, no author is no book.
                    try:
                        Author = item['volumeInfo']['authors'][0]
                    except KeyError:
                        logger.debug('Skipped a result without authorfield.')
                        break

                    try:
                        #skip if language is in ignore list
                        booklang = item['volumeInfo']['language']
                        if not booklang in lazylibrarian.IMP_PREFLANG:
                            ignored = ignored+1
                            break
                    except KeyError:
                        ignored = ignored+1
                        logger.debug('Skipped a result where no language is found')
                        break

                    try:
                        bookpub = item['volumeInfo']['publisher']
                    except KeyError:
                        bookpub = None

                    try:
                        booksub = item['volumeInfo']['subtitle']
                    except KeyError:
                        booksub = None

                    try:
                        bookdate = item['volumeInfo']['publishedDate']
                    except KeyError:
                        bookdate = '0000-00-00'

                    try:
                        bookimg = item['volumeInfo']['imageLinks']['thumbnail']
                    except KeyError:
                        bookimg = 'images/nocover.png'

                    try:
                        bookrate = item['volumeInfo']['averageRating']
                    except KeyError:
                        bookrate = 0

                    try:
                        bookpages = item['volumeInfo']['pageCount']
                    except KeyError:
                        bookpages = 0

                    try:
                        bookgenre = item['volumeInfo']['categories'][0]
                    except KeyError:
                        bookgenre = None

                    try:
                        bookdesc = item['volumeInfo']['description']
                    except KeyError:
                        bookdesc = None

                    try:
                        if item['volumeInfo']['industryIdentifiers'][0]['type'] == 'ISBN_10':
                            bookisbn = item['volumeInfo']['industryIdentifiers'][0]['identifier']
                        else:
                            bookisbn = None
                    except KeyError:
                        bookisbn = None

                    bookid = item['id']
                    bookname = item['volumeInfo']['title']
                    booklink = item['volumeInfo']['canonicalVolumeLink']
                    bookrate = float(bookrate)

                    find_book_status = myDB.select("SELECT * FROM books WHERE BookID = '%s'" % bookid)
                    if find_book_status:
                        for resulted in find_book_status:
                            book_status = resulted['Status']
                    else:
                        book_status = "Skipped"


                    if not (re.match('[^\w-]', bookname)): #remove books with bad caracters in title
                        controlValueDict = {"BookID": bookid}
                        newValueDict = {
                            "AuthorName":   authorname,
                            "AuthorID":     authorid,
                            "AuthorLink":   "",
                            "BookName":     bookname,
                            "BookSub":      booksub,
                            "BookDesc":     bookdesc,
                            "BookIsbn":     bookisbn,
                            "BookPub":      bookpub,
                            "BookGenre":    bookgenre,
                            "BookImg":      bookimg,
                            "BookLink":     booklink,
                            "BookRate":     bookrate,
                            "BookPages":    bookpages,
                            "BookDate":     bookdate,
                            "BookLang":     booklang,
                            "Status":       book_status,
                            "BookAdded":    formatter.today()
                        }
                        resultcount = resultcount + 1

                        myDB.upsert("books", newValueDict, controlValueDict)
                        logger.debug(u"book found " + bookname + " " + bookdate)
                        if not find_book_status:
                            logger.info("[%s] Added book: %s" % (authorname, bookname))
                            added_count = added_count + 1
                        else:
                            updated_count = updated_count + 1
                    else:
                        removedResults = removedResults + 1

                        
        except KeyError:
            logger.info('[%s] Found %s results for name: %s' % (authorname, resultcount, authorname))
            if ignored > 0:
                logger.info('[%s] Skipped %s results because it is not a preferred language.' % (authorname, ignored))

        lastbook = myDB.action("SELECT BookName, BookLink, BookDate from books WHERE AuthorID='%s' AND Status != 'Ignored' order by BookDate DESC" % authorid).fetchone()
        unignoredbooks = myDB.select("SELECT COUNT(BookName) as unignored FROM books WHERE AuthorID='%s' AND Status != 'Ignored'" % authorid)
        bookCount = myDB.select("SELECT COUNT(BookName) as counter FROM books WHERE AuthorID='%s'" % authorid)   

        controlValueDict = {"AuthorID": authorid}
        newValueDict = {
                "Status": "Active",
                "TotalBooks": bookCount[0]['counter'],
                "UnignoredBooks": unignoredbooks[0]['unignored'],
                "LastBook": lastbook['BookName'],
                "LastLink": lastbook['BookLink'],
                "LastDate": lastbook['BookDate']
                }
        myDB.upsert("authors", newValueDict, controlValueDict)

                   
        logger.debug("Removed %s non-english and no publication year results for author" % removedResults)
        logger.debug("Found %s books for author" % resultcount)
        if refresh:
            logger.info("[%s] Book processing complete: Added %s books / Updated %s books" % (authorname, str(added_count), str(updated_count)))
        else:
            logger.info("[%s] Book processing complete: Added %s books to the database" % (authorname, str(added_count)))
        return books_dict
