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

import re
import time
import traceback
import unicodedata
import urllib
import urllib2

import lazylibrarian
from lazylibrarian import logger, database
from lazylibrarian.bookwork import librarything_wait, getBookCover, getWorkSeries, getWorkPage, deleteEmptySeries, \
    setSeries, setStatus
from lazylibrarian.cache import get_xml_request, cache_img
from lazylibrarian.formatter import plural, today, replace_all, bookSeries, unaccented, split_title, getList, \
    cleanName, is_valid_isbn, formatAuthorName
from lib.fuzzywuzzy import fuzz


class GoodReads:
    # http://www.goodreads.com/api/

    def __init__(self, name=None):
        if isinstance(name, str):
            self.name = name.decode(lazylibrarian.SYS_ENCODING)
        else:
            self.name = name
        # self.type = type
        if not lazylibrarian.CONFIG['GR_API']:
            logger.warn('No Goodreads API key, check config')
        self.params = {"key": lazylibrarian.CONFIG['GR_API']}

    def find_results(self, searchterm=None, queue=None):
        try:
            resultlist = []
            api_hits = 0

            if ' <ll> ' in searchterm:  # special token separates title from author
                searchtitle, searchauthorname = searchterm.split(' <ll> ')
            else:
                searchtitle = ''
                searchauthorname = ''
            searchterm = searchterm.replace(' <ll> ', ' ')

            url = urllib.quote_plus(searchterm.encode(lazylibrarian.SYS_ENCODING))
            set_url = 'http://www.goodreads.com/search.xml?q=' + url + '&' + urllib.urlencode(self.params)
            logger.debug('Now searching GoodReads API with searchterm: %s' % searchterm)
            # logger.debug('Searching for %s at: %s' % (searchterm, set_url))

            resultcount = 0
            try:
                try:
                    rootxml, in_cache = get_xml_request(set_url)
                except Exception as e:
                    logger.error("Error finding gr results: %s" % str(e))
                    return
                if rootxml is None or not len(rootxml):
                    logger.debug("Error requesting results")
                    return

                resultxml = rootxml.getiterator('work')
                loopCount = 1
                while resultxml:
                    for author in resultxml:

                        if author.find('original_publication_year').text is None:
                            bookdate = "0000"
                        else:
                            bookdate = author.find('original_publication_year').text

                        authorNameResult = author.find('./best_book/author/name').text
                        # Goodreads sometimes puts extra whitepase in the author names!
                        authorNameResult = ' '.join(authorNameResult.split())
                        booksub = ""
                        bookpub = ""
                        booklang = "Unknown"

                        try:
                            bookimg = author.find('./best_book/image_url').text
                            if bookimg == 'http://www.goodreads.com/assets/nocover/111x148.png':
                                bookimg = 'images/nocover.png'
                        except (KeyError, AttributeError):
                            bookimg = 'images/nocover.png'

                        try:
                            bookrate = author.find('average_rating').text
                        except KeyError:
                            bookrate = 0

                        bookpages = '0'
                        bookgenre = ''
                        bookdesc = ''
                        bookisbn = ''
                        booklink = 'http://www.goodreads.com/book/show/' + author.find('./best_book/id').text

                        if author.find('./best_book/title').text is None:
                            bookTitle = ""
                        else:
                            bookTitle = author.find('./best_book/title').text

                        if searchauthorname:
                            author_fuzz = fuzz.ratio(authorNameResult, searchauthorname)
                        else:
                            author_fuzz = fuzz.ratio(authorNameResult, searchterm)
                        if searchtitle:
                            book_fuzz = fuzz.token_set_ratio(bookTitle, searchtitle)
                            # lose a point for each extra word in the fuzzy matches so we get the closest match
                            words = len(getList(bookTitle))
                            words -= len(getList(searchtitle))
                            book_fuzz -= abs(words)
                        else:
                            book_fuzz = fuzz.token_set_ratio(bookTitle, searchterm)
                            words = len(getList(bookTitle))
                            words -= len(getList(searchterm))
                            book_fuzz -= abs(words)
                        isbn_fuzz = 0
                        if is_valid_isbn(searchterm):
                            isbn_fuzz = 100

                        highest_fuzz = max((author_fuzz + book_fuzz) / 2, isbn_fuzz)

                        bookid = author.find('./best_book/id').text

                        resultlist.append({
                            'authorname': author.find('./best_book/author/name').text,
                            'bookid': bookid,
                            'authorid': author.find('./best_book/author/id').text,
                            'bookname': bookTitle.encode("ascii", "ignore"),
                            'booksub': booksub,
                            'bookisbn': bookisbn,
                            'bookpub': bookpub,
                            'bookdate': bookdate,
                            'booklang': booklang,
                            'booklink': booklink,
                            'bookrate': float(bookrate),
                            'bookimg': bookimg,
                            'bookpages': bookpages,
                            'bookgenre': bookgenre,
                            'bookdesc': bookdesc,
                            'author_fuzz': author_fuzz,
                            'book_fuzz': book_fuzz,
                            'isbn_fuzz': isbn_fuzz,
                            'highest_fuzz': highest_fuzz,
                            'num_reviews': float(bookrate)
                        })

                        resultcount += 1

                    loopCount += 1
                    if 0 < lazylibrarian.CONFIG['MAX_PAGES'] < loopCount:
                        resultxml = None
                        logger.warn('Maximum results page search reached, still more results available')
                    else:
                        URL = set_url + '&page=' + str(loopCount)
                        resultxml = None
                        try:
                            rootxml, in_cache = get_xml_request(URL)
                            if rootxml is None:
                                logger.debug('Error requesting page %s of results' % loopCount)
                            else:
                                resultxml = rootxml.getiterator('work')
                                if not in_cache:
                                    api_hits += 1
                        except Exception as e:
                            resultxml = None
                            logger.error("Error finding page %s of results: %s" % (loopCount, str(e)))

                    if resultxml:
                        if all(False for _ in resultxml):  # returns True if iterator is empty
                            resultxml = None

            except urllib2.HTTPError as err:
                if err.code == 404:
                    logger.error('Received a 404 error when searching for author')
                if err.code == 403:
                    logger.warn('Access to api is denied: usage exceeded')
                else:
                    logger.error('An unexpected error has occurred when searching for an author: %s' % str(err))

            logger.debug('Found %s result%s with keyword: %s' % (resultcount, plural(resultcount), searchterm))
            logger.debug(
                'The GoodReads API was hit %s time%s for keyword %s' % (api_hits, plural(api_hits), searchterm))

            queue.put(resultlist)

        except Exception:
            logger.error('Unhandled exception in GR.find_results: %s' % traceback.format_exc())

    def find_author_id(self, refresh=False):
        author = self.name
        author = formatAuthorName(unaccented(author))
        URL = 'http://www.goodreads.com/api/author_url/' + urllib.quote(author) + '?' + urllib.urlencode(self.params)

        # googlebooks gives us author names with long form unicode characters
        if isinstance(author, str):
            author = author.decode('utf-8')  # make unicode
        author = unicodedata.normalize('NFC', author)  # normalize to short form

        logger.debug("Searching for author with name: %s" % author)

        authorlist = []
        try:
            rootxml, in_cache = get_xml_request(URL, useCache=not refresh)
        except Exception as e:
            logger.error("Error finding authorid: %s, %s" % (URL, str(e)))
            return authorlist
        if rootxml is None:
            logger.debug("Error requesting authorid")
            return authorlist

        resultxml = rootxml.getiterator('author')

        if not len(resultxml):
            logger.warn('No authors found with name: %s' % author)
        else:
            # In spite of how this looks, goodreads only returns one result, even if there are multiple matches
            # we just have to hope we get the right one. eg search for "James Lovelock" returns "James E. Lovelock"
            # who only has one book listed under googlebooks, the rest are under "James Lovelock"
            # goodreads has all his books under "James E. Lovelock". Can't come up with a good solution yet.
            # For now we'll have to let the user handle this by selecting/adding the author manually
            for author in resultxml:
                authorid = author.attrib.get("id")
                authorlist = self.get_author_info(authorid)
        return authorlist

    def get_author_info(self, authorid=None):

        URL = 'http://www.goodreads.com/author/show/' + authorid + '.xml?' + urllib.urlencode(self.params)
        author_dict = {}

        try:
            rootxml, in_cache = get_xml_request(URL)
        except Exception as e:
            logger.error("Error getting author info: %s" % str(e))
            return author_dict
        if rootxml is None:
            logger.debug("Error requesting author info")
            return author_dict

        resultxml = rootxml.find('author')

        if not len(resultxml):
            logger.warn('No author found with ID: ' + authorid)
        else:
            # added authorname to author_dict - this holds the intact name preferred by GR
            # except GR messes up names like "L. E. Modesitt, Jr." where it returns <name>Jr., L. E. Modesitt</name>
            authorname = resultxml[1].text
            if "," in authorname:
                postfix = getList(lazylibrarian.CONFIG['NAME_POSTFIX'])
                words = authorname.split(',')
                if len(words) == 2:
                    if words[0].strip().strip('.').lower in postfix:
                        authorname = words[1].strip() + ' ' + words[0].strip()

            logger.debug("[%s] Processing info for authorID: %s" % (authorname, authorid))
            author_dict = {
                'authorid': resultxml[0].text,
                'authorlink': resultxml.find('link').text,
                'authorimg': resultxml.find('image_url').text,
                'authorborn': resultxml.find('born_at').text,
                'authordeath': resultxml.find('died_at').text,
                'totalbooks': resultxml.find('works_count').text,
                'authorname': ' '.join(authorname.split())  # remove any extra whitespace
            }
        return author_dict

    def get_author_books(self, authorid=None, authorname=None, bookstatus="Skipped", refresh=False):
        try:
            api_hits = 0
            gr_lang_hits = 0
            lt_lang_hits = 0
            gb_lang_change = 0
            cache_hits = 0
            not_cached = 0
            URL = 'http://www.goodreads.com/author/list/' + authorid + '.xml?' + urllib.urlencode(self.params)

            # Artist is loading
            myDB = database.DBConnection()
            controlValueDict = {"AuthorID": authorid}
            newValueDict = {"Status": "Loading"}
            myDB.upsert("authors", newValueDict, controlValueDict)

            try:
                rootxml, in_cache = get_xml_request(URL, useCache=not refresh)
            except Exception as e:
                logger.error("Error fetching author books: %s" % str(e))
                return
            if rootxml is None:
                logger.debug("Error requesting author books")
                return
            if not in_cache:
                api_hits += 1
            resultxml = rootxml.getiterator('book')

            valid_langs = getList(lazylibrarian.CONFIG['IMP_PREFLANG'])

            resultsCount = 0
            removedResults = 0
            duplicates = 0
            ignored = 0
            added_count = 0
            updated_count = 0
            book_ignore_count = 0
            total_count = 0

            if not len(resultxml):
                logger.warn('[%s] No books found for author with ID: %s' % (authorname, authorid))
            else:
                logger.debug("[%s] Now processing books with GoodReads API" % authorname)
                logger.debug(u"url " + URL)

                authorNameResult = rootxml.find('./author/name').text
                # Goodreads sometimes puts extra whitespace in the author names!
                authorNameResult = ' '.join(authorNameResult.split())
                logger.debug(u"GoodReads author name [%s]" % authorNameResult)
                loopCount = 1

                while resultxml:
                    for book in resultxml:
                        total_count += 1

                        if book.find('publication_year').text is None:
                            pubyear = "0000"
                        else:
                            pubyear = book.find('publication_year').text

                        try:
                            bookimg = book.find('image_url').text
                            if 'nocover' in bookimg:
                                bookimg = 'images/nocover.png'
                        except (KeyError, AttributeError):
                            bookimg = 'images/nocover.png'

                        bookLanguage = "Unknown"
                        find_field = "id"
                        isbn = ""
                        isbnhead = ""
                        if "All" not in valid_langs:  # do we care about language
                            if book.find('isbn').text:
                                find_field = "isbn"
                                isbn = book.find('isbn').text
                                isbnhead = isbn[0:3]
                            else:
                                if book.find('isbn13').text:
                                    find_field = "isbn13"
                                    isbn = book.find('isbn13').text
                                    isbnhead = isbn[3:6]
                            # Try to use shortcut of ISBN identifier codes described here...
                            # http://en.wikipedia.org/wiki/List_of_ISBN_identifier_groups
                            if isbnhead:
                                if find_field == "isbn13" and isbn.startswith('979'):
                                    for item in lazylibrarian.isbn_979_dict:
                                        if isbnhead.startswith(item):
                                            bookLanguage = lazylibrarian.isbn_979_dict[item]
                                            break
                                    if bookLanguage != "Unknown":
                                        logger.debug("ISBN979 returned %s for %s" % (bookLanguage, isbnhead))
                                elif (find_field == "isbn") or (find_field == "isbn13" and isbn.startswith('978')):
                                    for item in lazylibrarian.isbn_978_dict:
                                        if isbnhead.startswith(item):
                                            bookLanguage = lazylibrarian.isbn_978_dict[item]
                                            break
                                    if bookLanguage != "Unknown":
                                        logger.debug("ISBN978 returned %s for %s" % (bookLanguage, isbnhead))

                            if bookLanguage == "Unknown" and isbnhead:
                                # Nothing in the isbn dictionary, try any cached results
                                match = myDB.match('SELECT lang FROM languages where isbn=?', (isbnhead,))
                                if match:
                                    bookLanguage = match['lang']
                                    cache_hits += 1
                                    logger.debug("Found cached language [%s] for %s [%s]" %
                                                 (bookLanguage, find_field, isbnhead))
                                else:
                                    # no match in cache, try searching librarything for a language code using the isbn
                                    # if no language found, librarything return value is "invalid" or "unknown"
                                    # returns plain text, not xml
                                    BOOK_URL = 'http://www.librarything.com/api/thingLang.php?isbn=' + isbn
                                    try:
                                        librarything_wait()
                                        resp = urllib2.urlopen(BOOK_URL, timeout=30).read()
                                        lt_lang_hits += 1
                                        logger.debug("LibraryThing reports language [%s] for %s" % (resp, isbnhead))

                                        if 'invalid' in resp or 'Unknown' in resp:
                                            bookLanguage = "Unknown"
                                        else:
                                            bookLanguage = resp  # found a language code
                                            myDB.action('insert into languages values (?, ?)',
                                                        (isbnhead, bookLanguage))
                                            logger.debug(u"LT language %s: %s" % (isbnhead, bookLanguage))
                                    except Exception as e:
                                        logger.error("Error finding LT language result for [%s], %s" % (isbn, str(e)))

                            if bookLanguage == "Unknown":
                                # still  no earlier match, we'll have to search the goodreads api
                                try:
                                    if book.find(find_field).text:
                                        BOOK_URL = 'http://www.goodreads.com/book/show?id=' + \
                                                   book.find(find_field).text + '&' + urllib.urlencode(self.params)
                                        logger.debug(u"Book URL: " + BOOK_URL)

                                        time_now = int(time.time())
                                        if time_now <= lazylibrarian.LAST_GOODREADS:
                                            time.sleep(1)

                                        bookLanguage = ""
                                        try:
                                            BOOK_rootxml, in_cache = get_xml_request(BOOK_URL)
                                            if BOOK_rootxml is None:
                                                logger.debug('Error requesting book language code')
                                            else:
                                                if not in_cache:
                                                    # only update last_goodreads if the result wasn't found in the cache
                                                    lazylibrarian.LAST_GOODREADS = time_now
                                                try:
                                                    bookLanguage = BOOK_rootxml.find('./book/language_code').text
                                                except Exception as e:
                                                    logger.debug("Error finding language_code in book xml: %s" % str(e))
                                        except Exception as e:
                                            logger.debug("Error getting book xml: %s" % str(e))

                                        if not in_cache:
                                            gr_lang_hits += 1
                                        if not bookLanguage:
                                            bookLanguage = "Unknown"
                                            # At this point, give up?
                                            # WhatWork on author/title doesn't give us a language.
                                            # It might give us the "original language" of the book (but not always)
                                            # and our copy might not be in the original language anyway
                                            # eg "The Girl With the Dragon Tattoo" original language Swedish
                                            # If we have an isbn, try WhatISBN to get alternatives
                                            # in case any of them give us a language, but it seems if thinglang doesn't
                                            # have a language for the first isbn code, it doesn't for any of the
                                            # alternatives either
                                            # Goodreads search results don't include the language. Although sometimes
                                            # it's in the html page, it's not in the xml results

                                        if isbnhead != "":
                                            # if GR didn't give an isbn we can't cache it
                                            # just use language for this book
                                            myDB.action('insert into languages values (?, ?)',
                                                        (isbnhead, bookLanguage))
                                            logger.debug("GoodReads reports language [%s] for %s" %
                                                         (bookLanguage, isbnhead))
                                        else:
                                            not_cached += 1

                                        logger.debug(u"GR language: " + bookLanguage)
                                    else:
                                        logger.debug("No %s provided for [%s]" % (find_field, book.find('title').text))
                                        # continue

                                except Exception as e:
                                    logger.debug(u"Goodreads language search failed: %s" % str(e))

                            if bookLanguage not in valid_langs:
                                logger.debug('Skipped %s with language %s' % (book.find('title').text, bookLanguage))
                                ignored += 1
                                continue

                        bookname = book.find('title').text
                        bookid = book.find('id').text
                        bookdesc = book.find('description').text
                        bookisbn = book.find('isbn').text
                        bookpub = book.find('publisher').text
                        booklink = book.find('link').text
                        bookrate = float(book.find('average_rating').text)
                        bookpages = book.find('num_pages').text
                        bookname = unaccented(bookname)

                        bookname, booksub = split_title(authorNameResult, bookname)

                        dic = {':': '.', '"': ''}  # do we need to strip apostrophes , '\'': ''}
                        bookname = replace_all(bookname, dic)
                        bookname = bookname.strip()  # strip whitespace
                        booksub = replace_all(booksub, dic)
                        booksub = booksub.strip()  # strip whitespace
                        if booksub:
                            series, seriesNum = bookSeries(booksub)
                        else:
                            series, seriesNum = bookSeries(bookname)

                        rejected = False
                        check_status = False

                        if re.match('[^\w-]', bookname):  # reject books with bad characters in title
                            logger.debug(u"removed result [" + bookname + "] for bad characters")
                            removedResults += 1
                            rejected = True

                        if not rejected and lazylibrarian.CONFIG['NO_FUTURE']:
                            if pubyear > today()[:4]:
                                logger.debug('Rejecting %s, future publication date %s' % (bookname, pubyear))
                                removedResults += 1
                                rejected = True

                        if not rejected and not bookname:
                            logger.debug('Rejecting bookid %s for %s, no bookname' %
                                         (bookid, authorNameResult))
                            removedResults += 1
                            rejected = True

                        if not rejected:
                            anames = book.find('authors')
                            amatch = False
                            for aname in anames:
                                aid = aname.find('id').text
                                if aid == authorid:
                                    role = aname.find('role').text
                                    if role is None or 'Author' in role:
                                        amatch = True
                                    else:
                                        logger.debug('Ignoring %s for %s, role is %s' %
                                                     (bookname, authorNameResult, role))
                                # else: # multiple authors or wrong author
                                #    logger.debug('Ignoring %s for %s, authorid %s' %
                                #                 (bookname, authorNameResult, aid))
                            if not amatch:
                                logger.debug('Ignoring %s for %s, wrong author?' % (bookname, authorNameResult))
                            rejected = not amatch

                        if not rejected:
                            cmd = 'SELECT BookID FROM books,authors WHERE books.AuthorID = authors.AuthorID'
                            cmd += ' and BookName=? COLLATE NOCASE and AuthorName=? COLLATE NOCASE'
                            match = myDB.match(cmd, (bookname, authorNameResult.replace('"', '""')))
                            if match:
                                if match['BookID'] != bookid:
                                    # we have a different book with this author/title already
                                    logger.debug('Rejecting bookid %s for [%s][%s] already got %s' %
                                                 (match['BookID'], authorNameResult, bookname, bookid))
                                    duplicates += 1
                                    rejected = True

                        if not rejected:
                            cmd = 'SELECT AuthorName,BookName FROM books,authors'
                            cmd += ' WHERE authors.AuthorID = books.AuthorID AND BookID=?'
                            match = myDB.match(cmd, (bookid,))
                            if match:
                                # we have a book with this bookid already
                                if bookname != match['BookName'] or authorNameResult != match['AuthorName']:
                                    logger.debug('Rejecting bookid %s for [%s][%s] already got bookid for [%s][%s]' %
                                                 (bookid, authorNameResult, bookname,
                                                  match['AuthorName'], match['BookName']))
                                else:
                                    logger.debug('Rejecting bookid %s for [%s][%s] already got this book in database' %
                                                 (bookid, authorNameResult, bookname))
                                    check_status = True
                                duplicates += 1
                                rejected = True

                        if check_status or not rejected:
                            existing_book = myDB.match('SELECT Status,Manual FROM books WHERE BookID=?', (bookid,))
                            if existing_book:
                                book_status = existing_book['Status']
                                locked = existing_book['Manual']
                                if locked is None:
                                    locked = False
                                elif locked.isdigit():
                                    locked = bool(int(locked))
                            else:
                                book_status = bookstatus  # new_book status, or new_author status
                                locked = False

                            # Is the book already in the database?
                            # Leave alone if locked or status "ignore"
                            if not locked and book_status != "Ignored":
                                controlValueDict = {"BookID": bookid}
                                newValueDict = {
                                    "AuthorID": authorid,
                                    "BookName": bookname,
                                    "BookSub": booksub,
                                    "BookDesc": bookdesc,
                                    "BookIsbn": bookisbn,
                                    "BookPub": bookpub,
                                    "BookGenre": "",
                                    "BookImg": bookimg,
                                    "BookLink": booklink,
                                    "BookRate": bookrate,
                                    "BookPages": bookpages,
                                    "BookDate": pubyear,
                                    "BookLang": bookLanguage,
                                    "Status": book_status,
                                    "AudioStatus": lazylibrarian.CONFIG['NEWAUDIO_STATUS'],
                                    "BookAdded": today()
                                }

                                resultsCount += 1
                                updated = False

                                myDB.upsert("books", newValueDict, controlValueDict)
                                logger.debug(u"Book found: " + book.find('title').text + " " + pubyear)

                                if 'nocover' in bookimg or 'nophoto' in bookimg:
                                    # try to get a cover from librarything
                                    workcover = getBookCover(bookid)
                                    if workcover:
                                        logger.debug(u'Updated cover for %s to %s' % (bookname, workcover))
                                        controlValueDict = {"BookID": bookid}
                                        newValueDict = {"BookImg": workcover}
                                        myDB.upsert("books", newValueDict, controlValueDict)
                                        updated = True

                                elif bookimg and bookimg.startswith('http'):
                                    link, success = cache_img("book", bookid, bookimg, refresh=refresh)
                                    if success:
                                        controlValueDict = {"BookID": bookid}
                                        newValueDict = {"BookImg": link}
                                        myDB.upsert("books", newValueDict, controlValueDict)
                                        updated = True
                                    else:
                                        logger.debug('Failed to cache image for %s' % bookimg)

                                seriesdict = {}
                                if lazylibrarian.CONFIG['ADD_SERIES']:
                                    # prefer series info from librarything
                                    seriesdict = getWorkSeries(bookid)
                                    if seriesdict:
                                        logger.debug(u'Updated series: %s [%s]' % (bookid, seriesdict))
                                        updated = True
                                    else:
                                        if series:
                                            seriesdict = {cleanName(unaccented(series)): seriesNum}
                                    setSeries(seriesdict, bookid)

                                new_status = setStatus(bookid, seriesdict, bookstatus)

                                if not new_status == book_status:
                                    book_status = new_status
                                    updated = True

                                worklink = getWorkPage(bookid)
                                if worklink:
                                    controlValueDict = {"BookID": bookid}
                                    newValueDict = {"WorkPage": worklink}
                                    myDB.upsert("books", newValueDict, controlValueDict)

                                if not existing_book:
                                    logger.debug(u"[%s] Added book: %s [%s] status %s" %
                                                 (authorname, bookname, bookLanguage, book_status))
                                    added_count += 1
                                elif updated:
                                    logger.debug(u"[%s] Updated book: %s [%s] status %s" %
                                                 (authorname, bookname, bookLanguage, book_status))
                                    updated_count += 1
                            else:
                                book_ignore_count += 1

                    loopCount += 1
                    if 0 < lazylibrarian.CONFIG['MAX_PAGES'] < loopCount:
                        resultxml = None
                        logger.warn('Maximum books page search reached, still more results available')
                    else:
                        URL = 'http://www.goodreads.com/author/list/' + authorid + '.xml?' + \
                              urllib.urlencode(self.params) + '&page=' + str(loopCount)
                        resultxml = None
                        try:
                            rootxml, in_cache = get_xml_request(URL, useCache=not refresh)
                            if rootxml is None:
                                logger.debug('Error requesting next page of results')
                            else:
                                resultxml = rootxml.getiterator('book')
                                if not in_cache:
                                    api_hits += 1
                        except Exception as e:
                            resultxml = None
                            logger.error("Error finding next page of results: %s" % str(e))

                    if resultxml:
                        if all(False for _ in resultxml):  # returns True if iterator is empty
                            resultxml = None

            deleteEmptySeries()
            cmd = 'SELECT BookName, BookLink, BookDate, BookImg from books WHERE AuthorID=?'
            cmd += ' AND Status != "Ignored" order by BookDate DESC'
            lastbook = myDB.match(cmd, (authorid,))
            if lastbook:
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
                "Status": "Active",
                "LastBook": lastbookname,
                "LastLink": lastbooklink,
                "LastDate": lastbookdate,
                "LastBookImg": lastbookimg
            }
            myDB.upsert("authors", newValueDict, controlValueDict)

            # This is here because GoodReads sometimes has several entries with the same BookID!
            modified_count = added_count + updated_count

            logger.debug("Found %s result%s" % (total_count, plural(total_count)))
            logger.debug("Removed %s unwanted language result%s" % (ignored, plural(ignored)))
            logger.debug(
                "Removed %s bad character or no-name result%s" %
                (removedResults, plural(removedResults)))
            logger.debug("Removed %s duplicate result%s" % (duplicates, plural(duplicates)))
            logger.debug("Found %s book%s by author marked as Ignored" % (book_ignore_count, plural(book_ignore_count)))
            logger.debug("Imported/Updated %s book%s" % (modified_count, plural(modified_count)))

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
            logger.error('Unhandled exception in GR.get_author_books: %s' % traceback.format_exc())

    # noinspection PyUnusedLocal
    def find_book(self, bookid=None, queue=None):
        myDB = database.DBConnection()

        URL = 'http://www.goodreads.com/book/show/' + bookid + '?' + urllib.urlencode(self.params)

        try:
            rootxml, in_cache = get_xml_request(URL)
            if rootxml is None:
                logger.debug("Error requesting book")
                return
        except Exception as e:
            logger.error("Error finding book: %s" % str(e))
            return

        bookLanguage = rootxml.find('./book/language_code').text
        bookname = rootxml.find('./book/title').text

        if not bookLanguage:
            bookLanguage = "Unknown"
        #
        # PAB user has said they want this book, don't block for unwanted language, just warn
        #
        valid_langs = getList(lazylibrarian.CONFIG['IMP_PREFLANG'])
        if bookLanguage not in valid_langs:
            logger.debug('Book %s goodreads language does not match preference, %s' % (bookname, bookLanguage))

        if rootxml.find('./book/publication_year').text is None:
            bookdate = "0000"
        else:
            bookdate = rootxml.find('./book/publication_year').text

        try:
            bookimg = rootxml.find('./book/img_url').text
            if 'assets/nocover' in bookimg:
                bookimg = 'images/nocover.png'
        except (KeyError, AttributeError):
            bookimg = 'images/nocover.png'

        authorname = rootxml.find('./book/authors/author/name').text
        bookdesc = rootxml.find('./book/description').text
        bookisbn = rootxml.find('./book/isbn').text
        bookpub = rootxml.find('./book/publisher').text
        booklink = rootxml.find('./book/link').text
        bookrate = float(rootxml.find('./book/average_rating').text)
        bookpages = rootxml.find('.book/num_pages').text

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
                else:  # no author but request to add book, add author as "ignored"
                    # User hit "add book" button from a search
                    controlValueDict = {"AuthorID": AuthorID}
                    newValueDict = {
                        "AuthorName": author['authorname'],
                        "AuthorImg": author['authorimg'],
                        "AuthorLink": author['authorlink'],
                        "AuthorBorn": author['authorborn'],
                        "AuthorDeath": author['authordeath'],
                        "DateAdded": today(),
                        "Status": "Ignored"
                    }
                    authorname = author['authorname']
                    myDB.upsert("authors", newValueDict, controlValueDict)
        else:
            logger.warn("No AuthorID for %s, unable to add book %s" % (authorname, bookname))
            return

        bookname = unaccented(bookname)
        bookname, booksub = split_title(authorname, bookname)
        dic = {':': '.', '"': '', '\'': ''}
        bookname = replace_all(bookname, dic).strip()
        booksub = replace_all(booksub, dic).strip()
        if booksub:
            series, seriesNum = bookSeries(booksub)
        else:
            series, seriesNum = bookSeries(bookname)

        controlValueDict = {"BookID": bookid}
        newValueDict = {
            "AuthorID": AuthorID,
            "BookName": bookname,
            "BookSub": booksub,
            "BookDesc": bookdesc,
            "BookIsbn": bookisbn,
            "BookPub": bookpub,
            "BookGenre": "",
            "BookImg": bookimg,
            "BookLink": booklink,
            "BookRate": bookrate,
            "BookPages": bookpages,
            "BookDate": bookdate,
            "BookLang": bookLanguage,
            "Status": "Wanted",
            "AudioStatus": lazylibrarian.CONFIG['NEWAUDIO_STATUS'],
            "BookAdded": today()
        }

        myDB.upsert("books", newValueDict, controlValueDict)
        logger.info("%s by %s added to the books database" % (bookname, authorname))

        if 'nocover' in bookimg or 'nophoto' in bookimg:
            # try to get a cover from librarything
            workcover = getBookCover(bookid)
            if workcover:
                logger.debug(u'Updated cover for %s to %s' % (bookname, workcover))
                controlValueDict = {"BookID": bookid}
                newValueDict = {"BookImg": workcover}
                myDB.upsert("books", newValueDict, controlValueDict)

        elif bookimg and bookimg.startswith('http'):
            link, success = cache_img("book", bookid, bookimg)
            if success:
                controlValueDict = {"BookID": bookid}
                newValueDict = {"BookImg": link}
                myDB.upsert("books", newValueDict, controlValueDict)
            else:
                logger.debug('Failed to cache image for %s' % bookimg)

        if lazylibrarian.CONFIG['ADD_SERIES']:
            # prefer series info from librarything
            seriesdict = getWorkSeries(bookid)
            if seriesdict:
                logger.debug(u'Updated series: %s [%s]' % (bookid, seriesdict))
            else:
                if series:
                    seriesdict = {cleanName(unaccented(series)): seriesNum}
            setSeries(seriesdict, bookid)

        worklink = getWorkPage(bookid)
        if worklink:
            controlValueDict = {"BookID": bookid}
            newValueDict = {"WorkPage": worklink}
            myDB.upsert("books", newValueDict, controlValueDict)
