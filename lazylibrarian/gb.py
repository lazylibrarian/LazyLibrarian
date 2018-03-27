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


# example
# https://www.googleapis.com/books/v1/volumes?q=+inauthor:george+martin+intitle:song+ice+fire

import re
import traceback

try:
    import requests
except ImportError:
    import lib.requests as requests

import lazylibrarian
from lazylibrarian import logger, database
from lazylibrarian.bookwork import librarything_wait, getBookCover, getWorkSeries, getWorkPage, deleteEmptySeries, \
    setSeries, setStatus
from lazylibrarian.cache import gb_json_request, cache_img
from lazylibrarian.formatter import plural, today, replace_all, unaccented, unaccented_str, is_valid_isbn, \
    getList, cleanName, check_int, makeUnicode
from lazylibrarian.common import proxyList
from lazylibrarian.gr import GoodReads
from lib.fuzzywuzzy import fuzz
from lib.six import PY2
# noinspection PyUnresolvedReferences
from lib.six.moves.urllib_parse import quote, quote_plus, urlencode


class GoogleBooks:
    def __init__(self, name=None):
        self.name = makeUnicode(name)
        if not lazylibrarian.CONFIG['GB_API']:
            logger.warn('No GoogleBooks API key, check config')
        self.url = 'https://www.googleapis.com/books/v1/volumes?q='
        self.params = {
            'maxResults': 40,
            'printType': 'books',
            'key': lazylibrarian.CONFIG['GB_API']
        }

    # noinspection PyBroadException
    def find_results(self, searchterm=None, queue=None):
        """ GoogleBooks performs much better if we search for author OR title
            not both at once, so if searchterm is not isbn, two searches needed.
            Lazylibrarian searches use <ll> to separate title from author in searchterm
            If this token isn't present, it's an isbn or searchterm as supplied by user
        """
        try:
            myDB = database.DBConnection()
            resultlist = []
            # See if we should check ISBN field, otherwise ignore it
            api_strings = ['inauthor:', 'intitle:']
            if is_valid_isbn(searchterm):
                api_strings = ['isbn:']

            api_hits = 0

            ignored = 0
            total_count = 0
            no_author_count = 0
            title = ''
            authorname = ''

            if ' <ll> ' in searchterm:  # special token separates title from author
                title, authorname = searchterm.split(' <ll> ')

            fullterm = searchterm.replace(' <ll> ', ' ')
            logger.debug('Now searching Google Books API with searchterm: %s' % fullterm)

            for api_value in api_strings:
                set_url = self.url
                if api_value == "isbn:":
                    set_url = set_url + quote(api_value + searchterm)
                elif api_value == 'intitle:':
                    searchterm = fullterm
                    if title:  # just search for title
                        # noinspection PyUnresolvedReferences
                        title = title.split(' (')[0]  # without any series info
                        searchterm = title
                    searchterm = searchterm.replace("'", "").replace('"', '').strip()  # and no quotes
                    if PY2:
                        searchterm = searchterm.encode(lazylibrarian.SYS_ENCODING)
                    set_url = set_url + quote(api_value + '"' + searchterm + '"')
                elif api_value == 'inauthor:':
                    searchterm = fullterm
                    if authorname:
                        searchterm = authorname  # just search for author
                    searchterm = searchterm.strip()
                    if PY2:
                        searchterm = searchterm.encode(lazylibrarian.SYS_ENCODING)
                    set_url = set_url + quote_plus(api_value + '"' + searchterm + '"')

                startindex = 0
                resultcount = 0
                ignored = 0
                number_results = 1
                total_count = 0
                no_author_count = 0
                try:
                    while startindex < number_results:

                        self.params['startIndex'] = startindex
                        URL = set_url + '&' + urlencode(self.params)

                        try:
                            jsonresults, in_cache = gb_json_request(URL)
                            if jsonresults is None:
                                number_results = 0
                            else:
                                if not in_cache:
                                    api_hits += 1
                                number_results = jsonresults['totalItems']
                                logger.debug('Searching url: ' + URL)
                            if number_results == 0:
                                logger.warn('Found no results for %s with value: %s' % (api_value, searchterm))
                                break
                            else:
                                pass
                        except Exception as err:
                            if hasattr(err, 'reason'):
                                errmsg = err.reason
                            else:
                                errmsg = str(err)
                            logger.warn(
                                'Google Books API Error [%s]: Check your API key or wait a while' % errmsg)
                            break

                        startindex += 40

                        for item in jsonresults['items']:
                            total_count += 1

                            book = bookdict(item)
                            if not book['author']:
                                logger.debug('Skipped a result without authorfield.')
                                no_author_count += 1
                                continue

                            if not book['name']:
                                logger.debug('Skipped a result without title.')
                                continue

                            valid_langs = getList(lazylibrarian.CONFIG['IMP_PREFLANG'])
                            if "All" not in valid_langs:  # don't care about languages, accept all
                                try:
                                    # skip if language is not in valid list -
                                    booklang = book['lang']
                                    if booklang not in valid_langs:
                                        logger.debug(
                                            'Skipped %s with language %s' % (bookname, booklang))
                                        ignored += 1
                                        continue
                                except KeyError:
                                    ignored += 1
                                    logger.debug('Skipped %s where no language is found' % bookname)
                                    continue

                            if authorname:
                                author_fuzz = fuzz.ratio(book['author'], authorname)
                            else:
                                author_fuzz = fuzz.ratio(book['author'], fullterm)

                            if title:
                                book_fuzz = fuzz.token_set_ratio(book['name'], title)
                                # lose a point for each extra word in the fuzzy matches so we get the closest match
                                words = len(getList(book['name']))
                                words -= len(getList(title))
                                book_fuzz -= abs(words)
                            else:
                                book_fuzz = fuzz.token_set_ratio(book['name'], fullterm)

                            isbn_fuzz = 0
                            if is_valid_isbn(fullterm):
                                isbn_fuzz = 100

                            highest_fuzz = max((author_fuzz + book_fuzz) / 2, isbn_fuzz)

                            dic = {':': '.', '"': '', '\'': ''}
                            bookname = replace_all(book['name'], dic)

                            bookname = unaccented(bookname)
                            bookname = bookname.strip()  # strip whitespace

                            match = myDB.match(
                                'SELECT AuthorID FROM authors WHERE AuthorName=?', (book['author'].replace('"', '""'),))
                            if book['author']:
                                AuthorID = match['authorid']
                            else:
                                AuthorID = ''

                            resultlist.append({
                                'authorname': book['author'],
                                'authorid': AuthorID,
                                'bookid': item['id'],
                                'bookname': bookname,
                                'booksub': book['sub'],
                                'bookisbn': book['isbn'],
                                'bookpub': book['pub'],
                                'bookdate': book['date'],
                                'booklang': book['lang'],
                                'booklink': book['link'],
                                'bookrate': float(book['rate']),
                                'bookimg': book['img'],
                                'bookpages': book['pages'],
                                'bookgenre': book['genre'],
                                'bookdesc': book['desc'],
                                'author_fuzz': author_fuzz,
                                'book_fuzz': book_fuzz,
                                'isbn_fuzz': isbn_fuzz,
                                'highest_fuzz': highest_fuzz,
                                'num_reviews': book['ratings']
                            })

                            resultcount += 1

                except KeyError:
                    break

                logger.debug("Returning %s result%s for (%s) with keyword: %s" %
                             (resultcount, plural(resultcount), api_value, searchterm))

            logger.debug("Found %s result%s" % (total_count, plural(total_count)))
            logger.debug("Removed %s unwanted language result%s" % (ignored, plural(ignored)))
            logger.debug("Removed %s book%s with no author" % (no_author_count, plural(no_author_count)))
            logger.debug('The Google Books API was hit %s time%s for searchterm: %s' %
                         (api_hits, plural(api_hits), fullterm))
            queue.put(resultlist)

        except Exception:
            logger.error('Unhandled exception in GB.find_results: %s' % traceback.format_exc())

    def get_author_books(self, authorid=None, authorname=None, bookstatus="Skipped",
                         entrystatus='Active', refresh=False):
        # noinspection PyBroadException
        try:
            logger.debug('[%s] Now processing books with Google Books API' % authorname)
            # google doesnt like accents in author names
            set_url = self.url + quote('inauthor:"%s"' % unaccented_str(authorname))

            api_hits = 0
            gr_lang_hits = 0
            lt_lang_hits = 0
            gb_lang_change = 0
            cache_hits = 0
            not_cached = 0
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

            valid_langs = getList(lazylibrarian.CONFIG['IMP_PREFLANG'])
            # Artist is loading
            myDB = database.DBConnection()
            controlValueDict = {"AuthorID": authorid}
            newValueDict = {"Status": "Loading"}
            myDB.upsert("authors", newValueDict, controlValueDict)

            try:
                while startindex < number_results:

                    self.params['startIndex'] = startindex
                    URL = set_url + '&' + urlencode(self.params)

                    try:
                        jsonresults, in_cache = gb_json_request(URL, useCache=not refresh)
                        if jsonresults is None:
                            number_results = 0
                        else:
                            if not in_cache:
                                api_hits += 1
                            number_results = jsonresults['totalItems']
                    except Exception as err:
                        if hasattr(err, 'reason'):
                            errmsg = err.reason
                        else:
                            errmsg = str(err)
                        logger.warn('Google Books API Error [%s]: Check your API key or wait a while' % errmsg)
                        break

                    if number_results == 0:
                        logger.warn('Found no results for %s' % authorname)
                        break
                    else:
                        logger.debug('Found %s result%s for %s' % (number_results, plural(number_results), authorname))

                    startindex += 40

                    for item in jsonresults['items']:

                        total_count += 1
                        book = bookdict(item)
                        # skip if no author, no author is no book.
                        if not book['author']:
                            logger.debug('Skipped a result without authorfield.')
                            continue

                        isbnhead = ""
                        if len(book['isbn']) == 10:
                            isbnhead = book['isbn'][0:3]
                        elif len(book['isbn']) == 13:
                            isbnhead = book['isbn'][3:6]

                        booklang = book['lang']
                        # do we care about language?
                        if "All" not in valid_langs:
                            if book['isbn']:
                                # seems google lies to us, sometimes tells us books are in english when they are not
                                if booklang == "Unknown" or booklang == "en":
                                    googlelang = booklang
                                    match = False
                                    lang = myDB.match('SELECT lang FROM languages where isbn=?', (isbnhead,))
                                    if lang:
                                        booklang = lang['lang']
                                        cache_hits += 1
                                        logger.debug("Found cached language [%s] for [%s]" % (booklang, isbnhead))
                                        match = True
                                    if not match:  # no match in cache, try lookup dict
                                        if isbnhead:
                                            if len(book['isbn']) == 13 and book['isbn'].startswith('979'):
                                                for lang in lazylibrarian.isbn_979_dict:
                                                    if isbnhead.startswith(lang):
                                                        booklang = lazylibrarian.isbn_979_dict[lang]
                                                        logger.debug("ISBN979 returned %s for %s" %
                                                                     (booklang, isbnhead))
                                                        match = True
                                                        break
                                            elif (len(book['isbn']) == 10) or \
                                                    (len(book['isbn']) == 13 and book['isbn'].startswith('978')):
                                                for lang in lazylibrarian.isbn_978_dict:
                                                    if isbnhead.startswith(lang):
                                                        booklang = lazylibrarian.isbn_978_dict[lang]
                                                        logger.debug("ISBN979 returned %s for %s" %
                                                                     (booklang, isbnhead))
                                                        match = True
                                                        break
                                            if match:
                                                myDB.action('insert into languages values (?, ?)',
                                                            (isbnhead, booklang))
                                                logger.debug("GB language: " + booklang)

                                    if not match:
                                        # try searching librarything for a language code using the isbn
                                        # if no language found, librarything return value is "invalid" or "unknown"
                                        # librarything returns plain text, not xml
                                        BOOK_URL = 'http://www.librarything.com/api/thingLang.php?isbn=' + book['isbn']
                                        proxies = proxyList()
                                        try:
                                            librarything_wait()
                                            timeout = check_int(lazylibrarian.CONFIG['HTTP_TIMEOUT'], 30)
                                            r = requests.get(BOOK_URL, timeout=timeout, proxies=proxies)
                                            resp = r.text
                                            lt_lang_hits += 1
                                            logger.debug(
                                                "LibraryThing reports language [%s] for %s" % (resp, isbnhead))
                                            if resp != 'invalid' and resp != 'unknown':
                                                booklang = resp  # found a language code
                                                match = True
                                                myDB.action('insert into languages values (?, ?)',
                                                            (isbnhead, booklang))
                                                logger.debug("LT language: " + booklang)
                                        except Exception as e:
                                            booklang = ""
                                            logger.error("%s finding language: %s" % (type(e).__name__, str(e)))

                                    if match:
                                        # We found a better language match
                                        if googlelang == "en" and booklang not in ["en-US", "en-GB", "eng"]:
                                            # these are all english, may need to expand this list
                                            logger.debug("%s Google thinks [%s], we think [%s]" %
                                                         (book['name'], googlelang, booklang))
                                            gb_lang_change += 1
                                    else:  # No match anywhere, accept google language
                                        booklang = googlelang

                            # skip if language is in ignore list
                            if booklang not in valid_langs:
                                logger.debug('Skipped [%s] with language %s' % (book['name'], booklang))
                                ignored += 1
                                continue

                        rejected = False
                        check_status = False
                        book_status = bookstatus  # new_book status, or new_author status
                        audio_status = lazylibrarian.CONFIG['NEWAUDIO_STATUS']
                        added = today()
                        locked = False
                        existing_book = None
                        bookname = book['name']
                        if not bookname:
                            logger.debug('Rejecting bookid %s for %s, no bookname' % (bookid, authorname))
                            removedResults += 1
                            rejected = True
                        else:
                            bookname = replace_all(unaccented(bookname), {':': '.', '"': '', '\'': ''}).strip()
                            bookid = item['id']

                            # GoodReads sometimes has multiple bookids for the same book (same author/title, different
                            # editions) and sometimes uses the same bookid if the book is the same but the title is
                            # slightly different. Not sure if googlebooks does too, but we only want one...
                            cmd = 'SELECT Status,AudioStatus,Manual,BookAdded FROM books WHERE BookID=?'
                            existing_book = myDB.match(cmd, (bookid,))
                            if existing_book:
                                book_status = existing_book['Status']
                                audio_status = existing_book['AudioStatus']
                                locked = existing_book['Manual']
                                added = existing_book['BookAdded']
                                if locked is None:
                                    locked = False
                                elif locked.isdigit():
                                    locked = bool(int(locked))

                        if not rejected and re.match('[^\w-]', bookname):  # remove books with bad characters in title
                            logger.debug("[%s] removed book for bad characters" % bookname)
                            removedResults += 1
                            rejected = True

                        if not rejected and lazylibrarian.CONFIG['NO_FUTURE']:
                            # googlebooks sometimes gives yyyy, sometimes yyyy-mm, sometimes yyyy-mm-dd
                            if book['date'] > today()[:len(book['date'])]:
                                logger.debug('Rejecting %s, future publication date %s' % (bookname, book['date']))
                                removedResults += 1
                                rejected = True

                        if not rejected:
                            cmd = 'SELECT BookID FROM books,authors WHERE books.AuthorID = authors.AuthorID'
                            cmd += ' and BookName=? COLLATE NOCASE and AuthorName=? COLLATE NOCASE'
                            match = myDB.match(cmd, (bookname.replace('"', '""'), authorname.replace('"', '""')))
                            if match:
                                if match['BookID'] != bookid:  # we have a different book with this author/title already
                                    logger.debug('Rejecting bookid %s for [%s][%s] already got %s' %
                                                 (match['BookID'], authorname, bookname, bookid))
                                    rejected = True
                                    duplicates += 1

                        if not rejected:
                            cmd = 'SELECT AuthorName,BookName FROM books,authors'
                            cmd += ' WHERE authors.AuthorID = books.AuthorID AND BookID=?'
                            match = myDB.match(cmd, (bookid,))
                            if match:  # we have a book with this bookid already
                                if bookname != match['BookName'] or authorname != match['AuthorName']:
                                    logger.debug('Rejecting bookid %s for [%s][%s] already got bookid for [%s][%s]' %
                                                 (bookid, authorname, bookname, match['AuthorName'], match['BookName']))
                                else:
                                    logger.debug('Rejecting bookid %s for [%s][%s] already got this book in database' %
                                                 (bookid, authorname, bookname))
                                    check_status = True
                                duplicates += 1
                                rejected = True

                        if check_status or not rejected:
                            if book_status != "Ignored" and not locked:
                                controlValueDict = {"BookID": bookid}
                                newValueDict = {
                                    "AuthorID": authorid,
                                    "BookName": bookname,
                                    "BookSub": book['sub'],
                                    "BookDesc": book['desc'],
                                    "BookIsbn": book['isbn'],
                                    "BookPub": book['pub'],
                                    "BookGenre": book['genre'],
                                    "BookImg": book['img'],
                                    "BookLink": book['link'],
                                    "BookRate": float(book['rate']),
                                    "BookPages": book['pages'],
                                    "BookDate": book['date'],
                                    "BookLang": booklang,
                                    "Status": book_status,
                                    "AudioStatus": audio_status,
                                    "BookAdded": added
                                }
                                resultcount += 1

                                myDB.upsert("books", newValueDict, controlValueDict)
                                logger.debug("Book found: " + bookname + " " + book['date'])
                                updated = False
                                if 'nocover' in book['img'] or 'nophoto' in book['img']:
                                    # try to get a cover from another source
                                    workcover, source = getBookCover(bookid)
                                    if workcover:
                                        logger.debug('Updated cover for %s using %s' % (bookname, source))
                                        controlValueDict = {"BookID": bookid}
                                        newValueDict = {"BookImg": workcover}
                                        myDB.upsert("books", newValueDict, controlValueDict)
                                        updated = True

                                elif book['img'] and book['img'].startswith('http'):
                                    link, success = cache_img("book", bookid, book['img'], refresh=refresh)
                                    if success:
                                        controlValueDict = {"BookID": bookid}
                                        newValueDict = {"BookImg": link}
                                        myDB.upsert("books", newValueDict, controlValueDict)
                                        updated = True
                                    else:
                                        logger.debug('Failed to cache image for %s' % book['img'])

                                serieslist = []
                                if book['series']:
                                    serieslist = [('', book['seriesNum'], cleanName(unaccented(book['series']), '&/'))]
                                if lazylibrarian.CONFIG['ADD_SERIES']:
                                    newserieslist = getWorkSeries(bookid)
                                    if newserieslist:
                                        serieslist = newserieslist
                                        logger.debug('Updated series: %s [%s]' % (bookid, serieslist))
                                        updated = True
                                setSeries(serieslist, bookid)

                                new_status = setStatus(bookid, serieslist, bookstatus)

                                if not new_status == book_status:
                                    book_status = new_status
                                    updated = True

                                worklink = getWorkPage(bookid)
                                if worklink:
                                    controlValueDict = {"BookID": bookid}
                                    newValueDict = {"WorkPage": worklink}
                                    myDB.upsert("books", newValueDict, controlValueDict)

                                if not existing_book:
                                    logger.debug("[%s] Added book: %s [%s] status %s" %
                                                 (authorname, bookname, booklang, book_status))
                                    added_count += 1
                                elif updated:
                                    logger.debug("[%s] Updated book: %s [%s] status %s" %
                                                 (authorname, bookname, booklang, book_status))
                                    updated_count += 1
                            else:
                                book_ignore_count += 1
            except KeyError:
                pass

            deleteEmptySeries()
            logger.debug('[%s] The Google Books API was hit %s time%s to populate book list' %
                         (authorname, api_hits, plural(api_hits)))
            cmd = 'SELECT BookName, BookLink, BookDate, BookImg from books WHERE AuthorID=?'
            cmd += ' AND Status != "Ignored" order by BookDate DESC'
            lastbook = myDB.match(cmd, (authorid,))

            if lastbook:  # maybe there are no books [remaining] for this author
                lastbookname = lastbook['BookName']
                lastbooklink = lastbook['BookLink']
                lastbookdate = lastbook['BookDate']
                lastbookimg = lastbook['BookImg']
            else:
                lastbookname = ""
                lastbooklink = ""
                lastbookdate = ""
                lastbookimg = ""

            controlValueDict = {"AuthorID": authorid}
            newValueDict = {
                "Status": entrystatus,
                "LastBook": lastbookname,
                "LastLink": lastbooklink,
                "LastDate": lastbookdate,
                "LastBookImg": lastbookimg
            }

            myDB.upsert("authors", newValueDict, controlValueDict)

            logger.debug("Found %s total book%s for author" % (total_count, plural(total_count)))
            logger.debug("Removed %s unwanted language result%s for author" % (ignored, plural(ignored)))
            logger.debug("Removed %s bad character or no-name result%s for author" %
                         (removedResults, plural(removedResults)))
            logger.debug("Removed %s duplicate result%s for author" % (duplicates, plural(duplicates)))
            logger.debug("Found %s book%s by author marked as Ignored" % (book_ignore_count, plural(book_ignore_count)))
            logger.debug("Imported/Updated %s book%s for author" % (resultcount, plural(resultcount)))

            myDB.action('insert into stats values (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)',
                        (authorname.replace('"', '""'), api_hits, gr_lang_hits, lt_lang_hits, gb_lang_change,
                         cache_hits, ignored, removedResults, not_cached, duplicates))

            if refresh:
                logger.info("[%s] Book processing complete: Added %s book%s / Updated %s book%s" %
                            (authorname, added_count, plural(added_count), updated_count, plural(updated_count)))
            else:
                logger.info("[%s] Book processing complete: Added %s book%s to the database" %
                            (authorname, added_count, plural(added_count)))

        except Exception:
            logger.error('Unhandled exception in GB.get_author_books: %s' % traceback.format_exc())

    def find_book(self, bookid=None, bookstatus="None"):
        myDB = database.DBConnection()
        if not lazylibrarian.CONFIG['GB_API']:
            logger.warn('No GoogleBooks API key, check config')
        URL = 'https://www.googleapis.com/books/v1/volumes/' + \
              str(bookid) + "?key=" + lazylibrarian.CONFIG['GB_API']
        jsonresults, in_cache = gb_json_request(URL)

        if jsonresults is None:
            logger.debug('No results found for %s' % bookid)
            return

        if not bookstatus:
            bookstatus = lazylibrarian.CONFIG['NEWBOOK_STATUS']

        book = bookdict(jsonresults)
        dic = {':': '.', '"': '', '\'': ''}
        bookname = replace_all(book['name'], dic)

        bookname = unaccented(bookname)
        bookname = bookname.strip()  # strip whitespace

        if not book['author']:
            logger.debug('Book %s does not contain author field, skipping' % bookname)
            return
        # warn if language is in ignore list, but user said they wanted this book
        valid_langs = getList(lazylibrarian.CONFIG['IMP_PREFLANG'])
        if book['lang'] not in valid_langs and 'All' not in valid_langs:
            logger.debug('Book %s googlebooks language does not match preference, %s' % (bookname, book['lang']))

        authorname = book['author']
        GR = GoodReads(authorname)
        author = GR.find_author_id()
        if author:
            AuthorID = author['authorid']
            match = myDB.match('SELECT AuthorID from authors WHERE AuthorID=?', (AuthorID,))
            if not match:
                match = myDB.match('SELECT AuthorID from authors WHERE AuthorName=?', (author['authorname'],))
                if match:
                    logger.debug('%s: Changing authorid from %s to %s' %
                                 (author['authorname'], AuthorID, match['AuthorID']))
                    AuthorID = match['AuthorID']  # we have a different authorid for that authorname
                else:  # no author but request to add book, add author with newauthor status
                    # User hit "add book" button from a search or a wishlist import
                    newauthor_status = 'Active'
                    if lazylibrarian.CONFIG['NEWAUTHOR_STATUS'] in ['Skipped', 'Ignored']:
                        newauthor_status = 'Paused'
                    controlValueDict = {"AuthorID": AuthorID}
                    newValueDict = {
                        "AuthorName": author['authorname'],
                        "AuthorImg": author['authorimg'],
                        "AuthorLink": author['authorlink'],
                        "AuthorBorn": author['authorborn'],
                        "AuthorDeath": author['authordeath'],
                        "DateAdded": today(),
                        "Status": newauthor_status
                    }
                    authorname = author['authorname']
                    myDB.upsert("authors", newValueDict, controlValueDict)
                    if lazylibrarian.CONFIG['NEWAUTHOR_BOOKS']:
                        self.get_author_books(AuthorID, entrystatus=lazylibrarian.CONFIG['NEWAUTHOR_STATUS'])
        else:
            logger.warn("No AuthorID for %s, unable to add book %s" % (book['author'], bookname))
            return

        controlValueDict = {"BookID": bookid}
        newValueDict = {
            "AuthorID": AuthorID,
            "BookName": bookname,
            "BookSub": book['sub'],
            "BookDesc": book['desc'],
            "BookIsbn": book['isbn'],
            "BookPub": book['pub'],
            "BookGenre": book['genre'],
            "BookImg": book['img'],
            "BookLink": book['link'],
            "BookRate": float(book['rate']),
            "BookPages": book['pages'],
            "BookDate": book['date'],
            "BookLang": book['lang'],
            "Status": bookstatus,
            "AudioStatus": lazylibrarian.CONFIG['NEWAUDIO_STATUS'],
            "BookAdded": today()
        }

        myDB.upsert("books", newValueDict, controlValueDict)
        logger.info("%s by %s added to the books database" % (bookname, authorname))

        if 'nocover' in book['img'] or 'nophoto' in book['img']:
            # try to get a cover from another source
            workcover, source = getBookCover(bookid)
            if workcover:
                logger.debug('Updated cover for %s using %s' % (bookname, source))
                controlValueDict = {"BookID": bookid}
                newValueDict = {"BookImg": workcover}
                myDB.upsert("books", newValueDict, controlValueDict)

            elif book['img'] and book['img'].startswith('http'):
                link, success = cache_img("book", bookid, book['img'])
                if success:
                    controlValueDict = {"BookID": bookid}
                    newValueDict = {"BookImg": link}
                    myDB.upsert("books", newValueDict, controlValueDict)
                else:
                    logger.debug('Failed to cache image for %s' % book['img'])

        serieslist = []
        if book['series']:
            serieslist = [('', book['seriesNum'], cleanName(unaccented(book['series']), '&/'))]
        if lazylibrarian.CONFIG['ADD_SERIES']:
            newserieslist = getWorkSeries(bookid)
            if newserieslist:
                serieslist = newserieslist
                logger.debug('Updated series: %s [%s]' % (bookid, serieslist))
        setSeries(serieslist, bookid)

        worklink = getWorkPage(bookid)
        if worklink:
            controlValueDict = {"BookID": bookid}
            newValueDict = {"WorkPage": worklink}
            myDB.upsert("books", newValueDict, controlValueDict)


def bookdict(item):
    """ Return all the book info we need as a dictionary or default value if no key """
    mydict = {}
    for val, idx1, idx2, default in [
        ('author', 'authors', 0, ''),
        ('name', 'title', None, ''),
        ('lang', 'language', None, ''),
        ('pub', 'publisher', None, ''),
        ('sub', 'subtitle', None, ''),
        ('date', 'publishedDate', None, '0000'),
        ('rate', 'averageRating', None, 0),
        ('pages', 'pageCount', None, 0),
        ('desc', 'description', None, 'Not available'),
        ('link', 'canonicalVolumeLink', None, ''),
        ('img', 'imageLinks', 'thumbnail', 'images/nocover.png'),
        ('genre', 'categories', 0, ''),
        ('ratings', 'ratingsCount', None, 0)
    ]:
        try:
            if idx2 is None:
                mydict[val] = item['volumeInfo'][idx1]
            else:
                mydict[val] = item['volumeInfo'][idx1][idx2]
        except KeyError:
            mydict[val] = default

    try:
        if item['volumeInfo']['industryIdentifiers'][0]['type'] in ['ISBN_10', 'ISBN_13']:
            mydict['isbn'] = item['volumeInfo']['industryIdentifiers'][0]['identifier']
        else:
            mydict['isbn'] = ""
    except KeyError:
        mydict['isbn'] = ""

    # googlebooks has a few series naming systems in the authors books page...
    # title or subtitle (seriesname num) eg (Discworld 24)
    # title or subtitle (seriesname #num) eg (Discworld #24)
    # title or subtitle (seriesname Series num)  eg (discworld Series 24)
    # subtitle Book num of seriesname  eg Book 24 of Discworld
    # There may be others...
    #
    try:
        seriesNum, series = mydict['sub'].split('Book ')[1].split(' of ')
    except IndexError:
        series = ""
        seriesNum = ""

    if not series:
        for item in [mydict['name'], mydict['sub']]:
            if ' Series ' in item:
                try:
                    series, seriesNum = item.split('(')[1].split(' Series ')
                    seriesNum = seriesNum.rstrip(')').lstrip('#')
                except IndexError:
                    series = ""
                    seriesNum = ""
            if not series and '#' in item:
                try:
                    series, seriesNum = item.rsplit('#', 1)
                    series = series.split('(')[1].strip()
                    seriesNum = seriesNum.rstrip(')')
                except IndexError:
                    series = ""
                    seriesNum = ""
            if not series and ' ' in item:
                try:
                    series, seriesNum = item.rsplit(' ', 1)
                    series = series.split('(')[1].strip()
                    seriesNum = seriesNum.rstrip(')')
                    # has to be unicode for isnumeric()
                    if not (u"%s" % seriesNum).isnumeric():
                        series = ""
                        seriesNum = ""
                except IndexError:
                    series = ""
                    seriesNum = ""
            if series and seriesNum:
                break

    mydict['series'] = series
    mydict['seriesNum'] = seriesNum

    return mydict
