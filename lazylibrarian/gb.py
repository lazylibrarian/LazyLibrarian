# example
# https://www.googleapis.com/books/v1/volumes?q=+inauthor:george+martin+intitle:song+ice+fire

import urllib
import urllib2
import socket
import json
import time
import re
from urllib2 import HTTPError

import lazylibrarian
from lazylibrarian import logger, database
from lazylibrarian.bookwork import librarything_wait, getBookCover, getWorkSeries, getWorkPage
from lazylibrarian.gr import GoodReads
from lazylibrarian.cache import get_json_request, cache_cover

from lib.fuzzywuzzy import fuzz
from lazylibrarian.formatter import plural, today, replace_all, unaccented, unaccented_str, is_valid_isbn


class GoogleBooks:

    def __init__(self, name=None, type=None):
        self.name = name
        self.type = type
        if not lazylibrarian.GB_API:
            logger.warn('No GoogleBooks API key, check config')
        self.url = 'https://www.googleapis.com/books/v1/volumes?q='
        self.params = {
            'maxResults': 40,
            'printType': 'books',
            'key': lazylibrarian.GB_API
        }

    def find_results(self, authorname=None, queue=None):

        myDB = database.DBConnection()
        resultlist = []
        # See if we should check ISBN field, otherwise ignore it
        api_strings = ['inauthor:', 'intitle:']
        if is_valid_isbn(authorname):
            api_strings = ['isbn:']

        api_hits = 0
        logger.debug(
            'Now searching Google Books API with keyword: ' +
            self.name)

        for api_value in api_strings:
            startindex = 0
            if api_value == "isbn:":
                set_url = self.url + urllib.quote(api_value + self.name.encode(lazylibrarian.SYS_ENCODING))
            else:
                set_url = self.url + \
                    urllib.quote(api_value + '"' + self.name.encode(lazylibrarian.SYS_ENCODING) + '"')

            try:
                startindex = 0
                resultcount = 0
                ignored = 0
                number_results = 1
                total_count = 0
                no_author_count = 0

                while startindex < number_results:

                    self.params['startIndex'] = startindex
                    URL = set_url + '&' + urllib.urlencode(self.params)

                    try:
                        jsonresults, in_cache = get_json_request(URL)
                        if jsonresults is None:
                            number_results = 0
                        else:
                            if not in_cache:
                                api_hits = api_hits + 1
                            number_results = jsonresults['totalItems']
                            logger.debug('Searching url: ' + URL)
                        if number_results == 0:
                            logger.warn(
                                'Found no results for %s with value: %s' %
                                (api_value, self.name))
                            break
                        else:
                            pass
                    except HTTPError as err:
                        logger.warn(
                            'Google Books API Error [%s]: Check your API key or wait a while' %
                            err.reason)
                        break

                    startindex = startindex + 40

                    for item in jsonresults['items']:

                        total_count = total_count + 1

                        # skip if no author, no author is no book.
                        try:
                            Author = item['volumeInfo']['authors'][0]
                        except KeyError:
                            logger.debug(
                                'Skipped a result without authorfield.')
                            no_author_count = no_author_count + 1
                            continue

                        valid_langs = ([valid_lang.strip()
                                       for valid_lang in lazylibrarian.IMP_PREFLANG.split(',')])

                        if "All" not in valid_langs:  # don't care about languages, accept all
                            try:
                                # skip if language is not in valid list -
                                booklang = item['volumeInfo']['language']
                                if booklang not in valid_langs:
                                    logger.debug(
                                        'Skipped a book with language %s' %
                                        booklang)
                                    ignored = ignored + 1
                                    continue
                            except KeyError:
                                ignored = ignored + 1
                                logger.debug(
                                    'Skipped a result where no language is found')
                                continue

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
                            num_reviews = item['volumeInfo']['ratingsCount']
                        except KeyError:
                            num_reviews = 0

                        try:
                            if item['volumeInfo']['industryIdentifiers'][0]['type'] == 'ISBN_10':
                                bookisbn = item['volumeInfo'][
                                    'industryIdentifiers'][0]['identifier']
                            else:
                                bookisbn = 0
                        except KeyError:
                            bookisbn = 0

                        author_fuzz = fuzz.token_set_ratio(Author, authorname)
                        book_fuzz = fuzz.token_set_ratio(
                            item['volumeInfo']['title'],
                            authorname)

                        isbn_fuzz = 0
                        if is_valid_isbn(authorname):
                            isbn_fuzz = 100

                        highest_fuzz = max(author_fuzz, book_fuzz, isbn_fuzz)

                        bookname = item['volumeInfo']['title']
                        dic = {':': '', '"': '', '\'': ''}
                        bookname = replace_all(bookname, dic)

                        bookname = unaccented(bookname)
                        bookname = bookname.strip()  # strip whitespace
                        bookid = item['id']

                        author = myDB.select(
                            'SELECT AuthorID FROM authors WHERE AuthorName = "%s"' %
                            Author.replace('"', '""'))
                        if author:
                            AuthorID = author[0]['authorid']
                        else:
                            AuthorID = ''

                        resultlist.append({
                            'authorname': Author,
                            'authorid': AuthorID,
                            'bookid': bookid,
                            'bookname': bookname,
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
                            'highest_fuzz': highest_fuzz,
                            'num_reviews': num_reviews
                        })

                        resultcount = resultcount + 1

            except KeyError:
                break

        logger.debug("Found %s total result%s" % (total_count, plural(total_count)))
        logger.debug("Removed %s bad language result%s" % (ignored, plural(ignored)))
        logger.debug("Removed %s book%s with no author" % (no_author_count, plural(no_author_count)))
        logger.debug(
            "Showing %s result%s for (%s) with keyword: %s" %
            (resultcount, plural(resultcount), api_value, authorname))
        logger.debug(
            'The Google Books API was hit %s time%s for keyword %s' %
            (api_hits, plural(api_hits), self.name))
        queue.put(resultlist)

    def get_author_books(self, authorid=None, authorname=None, refresh=False):

        logger.debug('[%s] Now processing books with Google Books API' % authorname)
        # google doesnt like accents in author names
        set_url = self.url + urllib.quote('inauthor:"%s"' % unaccented_str(authorname))
        URL = set_url + '&' + urllib.urlencode(self.params)

        books_dict = []
        api_hits = 0
        gr_lang_hits = 0
        lt_lang_hits = 0
        gb_lang_change = 0
        cache_hits = 0
        not_cached = 0

        # Artist is loading
        myDB = database.DBConnection()
        controlValueDict = {"AuthorID": authorid}
        newValueDict = {"Status": "Loading"}
        myDB.upsert("authors", newValueDict, controlValueDict)

        try:
            startindex = 0
            resultcount = 0
            removedResults = 0
            duplicates = 0
            ignored = 0
            added_count = 0
            updated_count = 0
            book_ignore_count = 0
            total_count = 0
            number_results = 1

            valid_langs = ([valid_lang.strip()
                           for valid_lang in lazylibrarian.IMP_PREFLANG.split(',')])

            while startindex < number_results:

                self.params['startIndex'] = startindex
                URL = set_url + '&' + urllib.urlencode(self.params)

                try:
                    jsonresults, in_cache = get_json_request(URL, useCache=not refresh)
                    if jsonresults is None:
                        number_results = 0
                    else:
                        if not in_cache:
                            api_hits = api_hits + 1
                        number_results = jsonresults['totalItems']
                except HTTPError as err:
                    logger.warn(
                        'Google Books API Error [%s]: Check your API key or wait a while' %
                        err.reason)
                    break

                if number_results == 0:
                    logger.warn('Found no results for %s' % authorname)
                    break
                else:
                    logger.debug('Found %s result%s for %s' % (number_results, plural(number_results), authorname))

                startindex = startindex + 40

                for item in jsonresults['items']:

                    total_count = total_count + 1

                    # skip if no author, no author is no book.
                    try:
                        Author = item['volumeInfo']['authors'][0]
                    except KeyError:
                        logger.debug('Skipped a result without authorfield.')
                        continue

                    try:
                        if item['volumeInfo']['industryIdentifiers'][0]['type'] == 'ISBN_10':
                            bookisbn = item['volumeInfo'][
                                'industryIdentifiers'][0]['identifier']
                        else:
                            bookisbn = ""
                    except KeyError:
                        bookisbn = ""

                    isbnhead = ""
                    if len(bookisbn) == 10:
                        isbnhead = bookisbn[0:3]

                    try:
                        booklang = item['volumeInfo']['language']
                    except KeyError:
                        booklang = "Unknown"

                    # do we care about language?
                    if "All" not in valid_langs:
                        if bookisbn != "":
                            # seems google lies to us, sometimes tells us books
                            # are in english when they are not
                            if booklang == "Unknown" or booklang == "en":
                                googlelang = booklang
                                match = myDB.match('SELECT lang FROM languages where isbn = "%s"' %
                                                   (isbnhead))
                                if (match):
                                    booklang = match['lang']
                                    cache_hits = cache_hits + 1
                                    logger.debug(
                                        "Found cached language [%s] for [%s]" %
                                        (booklang, isbnhead))

                                else:
                                    # no match in cache, try searching librarything for a language code using the isbn
                                    # if no language found, librarything return value is "invalid" or "unknown"
                                    # librarything returns plain text, not xml
                                    BOOK_URL = 'http://www.librarything.com/api/thingLang.php?isbn=' + \
                                        bookisbn
                                    try:
                                        librarything_wait()
                                        resp = urllib2.urlopen(BOOK_URL, timeout=30).read()
                                        lt_lang_hits = lt_lang_hits + 1
                                        logger.debug(
                                            "LibraryThing reports language [%s] for %s" % (resp, isbnhead))

                                        if (resp != 'invalid' and resp != 'unknown'):
                                            booklang = resp  # found a language code
                                            myDB.action('insert into languages values ("%s", "%s")' %
                                                        (isbnhead, booklang))
                                            logger.debug(u"LT language: " + booklang)
                                    except Exception as e:
                                        booklang = ""
                                        logger.error("Error finding language: %s" % str(e))

                                if googlelang == "en" and booklang not in ["en-US", "en-GB", "eng"]:
                                    # these are all english, may need to expand
                                    # this list
                                    booknamealt = item['volumeInfo']['title']
                                    logger.debug("%s Google thinks [%s], we think [%s]" %
                                                 (booknamealt, googlelang, booklang))
                                    gb_lang_change = gb_lang_change + 1
                            else:
                                match = myDB.match('SELECT lang FROM languages where isbn = "%s"' %
                                                   (isbnhead))
                                if (not match):
                                    myDB.action(
                                        'insert into languages values ("%s", "%s")' %
                                        (isbnhead, booklang))
                                    logger.debug(u"GB language: " + booklang)

                        # skip if language is in ignore list
                        if booklang not in valid_langs:
                            booknamealt = item['volumeInfo']['title']
                            logger.debug(
                                'Skipped [%s] with language %s' %
                                (booknamealt, booklang))
                            ignored = ignored + 1
                            continue

                    try:
                        bookpub = item['volumeInfo']['publisher']
                    except KeyError:
                        bookpub = None

                    try:
                        booksub = item['volumeInfo']['subtitle']
                    except KeyError:
                        booksub = None

                    if booksub is None:
                        series = None
                        seriesNum = None
                    else:
                        try:
                            series = booksub.split('(')[1].split(' Series ')[0]
                        except IndexError:
                            series = None
                        try:
                            seriesNum = booksub.split('(')[1].split(' Series ')[1].split(')')[0]
                            if seriesNum[0] == '#':
                                seriesNum = seriesNum[1:]
                        except IndexError:
                            seriesNum = None

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

                    bookname = item['volumeInfo']['title']
                    bookname = unaccented(bookname)
                    dic = {':': '', '"': '', '\'': ''}
                    bookname = replace_all(bookname, dic)
                    bookname = bookname.strip()  # strip whitespace

                    booklink = item['volumeInfo']['canonicalVolumeLink']
                    bookrate = float(bookrate)
                    bookid = item['id']

                    # GoodReads sometimes has multiple bookids for the same book (same author/title, different editions)
                    # and sometimes uses the same bookid if the book is the same but the title is slightly different
                    #
                    # Not sure if googlebooks does too, but we only want one...
                    find_book_status = myDB.select('SELECT * FROM books WHERE BookID = "%s"' % bookid)
                    if find_book_status:
                        for resulted in find_book_status:
                            book_status = resulted['Status']
                            locked = resulted['Manual']
                    else:
                        book_status = lazylibrarian.NEWBOOK_STATUS
                        locked = False

                    rejected = False
                    if re.match('[^\w-]', bookname):  # remove books with bad characters in title
                        logger.debug("[%s] removed book for bad characters" % bookname)
                        removedResults = removedResults + 1
                        rejected = True

                    if not rejected and not bookname:
                        logger.debug('Rejecting bookid %s for %s, no bookname' %
                                     (bookid, authorname))
                        removedResults = removedResults + 1
                        rejected = True

                    if not rejected:
                        find_books = myDB.select('SELECT * FROM books WHERE BookName = "%s" and AuthorName = "%s"' %
                                                 (bookname.replace('"', '""'), authorname.replace('"', '""')))
                        if find_books:
                            for find_book in find_books:
                                if find_book['BookID'] != bookid:
                                    # we have a book with this author/title already
                                    logger.debug('Rejecting bookid %s for [%s][%s] already got %s' %
                                                 (find_book['BookID'], authorname, bookname, bookid))
                                    rejected = True
                                    duplicates = duplicates + 1

                    if not rejected:
                        find_books = myDB.select('SELECT * FROM books WHERE BookID = "%s"' % bookid)
                        if find_books:
                            # we have a book with this bookid already
                            logger.debug('Rejecting bookid %s for [%s][%s] already got this bookid in database' %
                                         (bookid, authorname, bookname))
                            duplicates = duplicates + 1
                            rejected = True

                    if not rejected:
                        if book_status != "Ignored" and not locked:
                            controlValueDict = {"BookID": bookid}
                            newValueDict = {
                                "AuthorName": authorname,
                                "AuthorID": authorid,
                                "AuthorLink": "",
                                "BookName": bookname,
                                "BookSub": booksub,
                                "BookDesc": bookdesc,
                                "BookIsbn": bookisbn,
                                "BookPub": bookpub,
                                "BookGenre": bookgenre,
                                "BookImg": bookimg,
                                "BookLink": booklink,
                                "BookRate": bookrate,
                                "BookPages": bookpages,
                                "BookDate": bookdate,
                                "BookLang": booklang,
                                "Status": book_status,
                                "BookAdded": today(),
                                "Series": series,
                                "SeriesNum": seriesNum
                            }
                            resultcount = resultcount + 1

                            myDB.upsert("books", newValueDict, controlValueDict)
                            logger.debug(u"Book found: " + bookname + " " + bookdate)

                            if 'nocover' in bookimg or 'nophoto' in bookimg:
                                # try to get a cover from librarything
                                workcover = getBookCover(bookid)
                                if workcover:
                                    logger.debug(u'Updated cover for %s to %s' % (bookname, workcover))
                                    controlValueDict = {"BookID": bookid}
                                    newValueDict = {"BookImg": workcover}
                                    myDB.upsert("books", newValueDict, controlValueDict)

                            elif bookimg and bookimg.startswith('http'):
                                link = cache_cover(bookid, bookimg)
                                if link is not None:
                                    controlValueDict = {"BookID": bookid}
                                    newValueDict = {"BookImg": link}
                                    myDB.upsert("books", newValueDict, controlValueDict)

                            if seriesNum is None:
                                # try to get series info from librarything
                                series, seriesNum = getWorkSeries(bookid)
                                if seriesNum:
                                    logger.debug(u'Updated series: %s [%s]' % (series, seriesNum))
                                    controlValueDict = {"BookID": bookid}
                                    newValueDict = {
                                        "Series": series,
                                        "SeriesNum": seriesNum
                                    }
                                    myDB.upsert("books", newValueDict, controlValueDict)

                            worklink = getWorkPage(bookid)
                            if worklink:
                                controlValueDict = {"BookID": bookid}
                                newValueDict = {"WorkPage": worklink}
                                myDB.upsert("books", newValueDict, controlValueDict)

                            if not find_book_status:
                                logger.debug("[%s] Added book: %s [%s]" % (authorname, bookname, booklang))
                                added_count = added_count + 1
                            else:
                                updated_count = updated_count + 1
                                logger.debug("[%s] Updated book: %s" % (authorname, bookname))
                        else:
                            book_ignore_count = book_ignore_count + 1
        except KeyError:
            pass

        logger.debug('[%s] The Google Books API was hit %s time%s to populate book list' %
                     (authorname, api_hits, plural(api_hits)))

        lastbook = myDB.match('SELECT BookName, BookLink, BookDate from books WHERE AuthorID="%s" \
                               AND Status != "Ignored" order by BookDate DESC' % authorid)

        if lastbook:  # maybe there are no books [remaining] for this author
            lastbookname = lastbook['BookName']
            lastbooklink = lastbook['BookLink']
            lastbookdate = lastbook['BookDate']
        else:
            lastbookname = None
            lastbooklink = None
            lastbookdate = None

        controlValueDict = {"AuthorID": authorid}
        newValueDict = {
            "Status": "Active",
            "LastBook": lastbookname,
            "LastLink": lastbooklink,
            "LastDate": lastbookdate
        }

        myDB.upsert("authors", newValueDict, controlValueDict)

        logger.debug("Found %s total book%s for author" % (total_count, plural(total_count)))
        logger.debug("Removed %s bad language result%s for author" % (ignored, plural(ignored)))
        logger.debug(
            "Removed %s bad character or no-name result%s for author" %
            (removedResults, plural(removedResults)))
        logger.debug("Removed %s duplicate result%s for author" % (duplicates, plural(duplicates)))
        logger.debug("Ignored %s book%s by author marked as Ignored" % (book_ignore_count, plural(book_ignore_count)))
        logger.debug("Imported/Updated %s book%s for author" % (resultcount, plural(resultcount)))

        myDB.action('insert into stats values ("%s", %i, %i, %i, %i, %i, %i, %i, %i, %i)' %
                    (authorname.replace('"', '""'), api_hits, gr_lang_hits, lt_lang_hits, gb_lang_change, cache_hits,
                     ignored, removedResults, not_cached, duplicates))

        if refresh:
            logger.info("[%s] Book processing complete: Added %s book%s / Updated %s book%s" %
                        (authorname, added_count, plural(added_count), updated_count, plural(updated_count)))
        else:
            logger.info("[%s] Book processing complete: Added %s book%s to the database" %
                        (authorname, added_count, plural(added_count)))
        return books_dict

    def find_book(self, bookid=None, queue=None):
        myDB = database.DBConnection()
        if not lazylibrarian.GB_API:
            logger.warn('No GoogleBooks API key, check config')
        URL = 'https://www.googleapis.com/books/v1/volumes/' + \
            str(bookid) + "?key=" + lazylibrarian.GB_API
        jsonresults, in_cache = get_json_request(URL)

        if jsonresults is None:
            logger.debug('No results found for %s' % bookname)
            return

        bookname = jsonresults['volumeInfo']['title']
        dic = {':': '', '"': '', '\'': ''}
        bookname = replace_all(bookname, dic)

        bookname = unaccented(bookname)
        bookname = bookname.strip()  # strip whitespace

        try:
            authorname = jsonresults['volumeInfo']['authors'][0]
        except KeyError:
            logger.debug(
                'Book %s does not contain author field, skipping' %
                bookname)
            return
        try:
            # warn if language is in ignore list, but user said they wanted
            # this book
            booklang = jsonresults['volumeInfo']['language']
            valid_langs = ([valid_lang.strip()
                           for valid_lang in lazylibrarian.IMP_PREFLANG.split(',')])
            if booklang not in valid_langs:
                logger.debug(
                    'Book %s language does not match preference' %
                    bookname)
        except KeyError:
            logger.debug('Book does not have language field')
            booklang = "Unknown"

        try:
            bookpub = jsonresults['volumeInfo']['publisher']
        except KeyError:
            bookpub = None

        series = None
        seriesNum = None
        try:
            booksub = jsonresults['volumeInfo']['subtitle']
            try:
                series = booksub.split('(')[1].split(' Series ')[0]
            except IndexError:
                series = None
            try:
                seriesNum = booksub.split('(')[1].split(' Series ')[1].split(')')[0]
                if seriesNum[0] == '#':
                    seriesNum = seriesNum[1:]
            except IndexError:
                seriesNum = None
        except KeyError:
            booksub = None

        try:
            bookdate = jsonresults['volumeInfo']['publishedDate']
        except KeyError:
            bookdate = '0000-00-00'

        try:
            bookimg = jsonresults['volumeInfo']['imageLinks']['thumbnail']
        except KeyError:
            bookimg = 'images/nocover.png'

        try:
            bookrate = jsonresults['volumeInfo']['averageRating']
        except KeyError:
            bookrate = 0

        try:
            bookpages = jsonresults['volumeInfo']['pageCount']
        except KeyError:
            bookpages = 0

        try:
            bookgenre = jsonresults['volumeInfo']['categories'][0]
        except KeyError:
            bookgenre = None

        try:
            bookdesc = jsonresults['volumeInfo']['description']
        except KeyError:
            bookdesc = None

        try:
            if jsonresults['volumeInfo']['industryIdentifiers'][0]['type'] == 'ISBN_10':
                bookisbn = jsonresults['volumeInfo'][
                    'industryIdentifiers'][0]['identifier']
            else:
                bookisbn = None
        except KeyError:
            bookisbn = None

        booklink = jsonresults['volumeInfo']['canonicalVolumeLink']
        bookrate = float(bookrate)

        name = jsonresults['volumeInfo']['authors'][0]
        GR = GoodReads(name)
        author = GR.find_author_id()
        if author:
            AuthorID = author['authorid']

        controlValueDict = {"BookID": bookid}
        newValueDict = {
            "AuthorName": authorname,
            "AuthorID": AuthorID,
            "AuthorLink": "",
            "BookName": bookname,
            "BookSub": booksub,
            "BookDesc": bookdesc,
            "BookIsbn": bookisbn,
            "BookPub": bookpub,
            "BookGenre": bookgenre,
            "BookImg": bookimg,
            "BookLink": booklink,
            "BookRate": bookrate,
            "BookPages": bookpages,
            "BookDate": bookdate,
            "BookLang": booklang,
            "Status": "Wanted",
            "BookAdded": today(),
            "Series": series,
            "SeriesNum": seriesNum
        }

        myDB.upsert("books", newValueDict, controlValueDict)
        logger.debug("%s added to the books database" % bookname)

        if 'nocover' in bookimg or 'nophoto' in bookimg:
            # try to get a cover from librarything
            workcover = getBookCover(bookid)
            if workcover:
                logger.debug(u'Updated cover for %s to %s' % (bookname, workcover))
                controlValueDict = {"BookID": bookid}
                newValueDict = {"BookImg": workcover}
                myDB.upsert("books", newValueDict, controlValueDict)

            elif bookimg and bookimg.startswith('http'):
                link = cache_cover(bookid, bookimg)
                if link is not None:
                    controlValueDict = {"BookID": bookid}
                    newValueDict = {"BookImg": link}
                    myDB.upsert("books", newValueDict, controlValueDict)

        if seriesNum is None:
            # try to get series info from librarything
            series, seriesNum = getWorkSeries(bookid)
            if seriesNum:
                logger.debug(u'Updated series: %s [%s]' % (series, seriesNum))
                controlValueDict = {"BookID": bookid}
                newValueDict = {
                    "Series": series,
                    "SeriesNum": seriesNum
                }
                myDB.upsert("books", newValueDict, controlValueDict)

        worklink = getWorkPage(bookid)
        if worklink:
            controlValueDict = {"BookID": bookid}
            newValueDict = {"WorkPage": worklink}
            myDB.upsert("books", newValueDict, controlValueDict)
