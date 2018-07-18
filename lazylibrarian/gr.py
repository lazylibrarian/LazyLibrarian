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

import re
import time
import traceback
import unicodedata

try:
    import requests
except ImportError:
    import lib.requests as requests

import lazylibrarian
from lazylibrarian import logger, database
from lazylibrarian.bookwork import getWorkSeries, getWorkPage, deleteEmptySeries, \
    setSeries, setStatus, isbn_from_words, thingLang
from lazylibrarian.images import getBookCover
from lazylibrarian.cache import gr_xml_request, cache_img
from lazylibrarian.formatter import plural, today, replace_all, bookSeries, unaccented, split_title, getList, \
    cleanName, is_valid_isbn, formatAuthorName, check_int, makeUnicode, check_year
from lib.fuzzywuzzy import fuzz
from lib.six import PY2
# noinspection PyUnresolvedReferences
from lib.six.moves.urllib_parse import quote, quote_plus, urlencode


class GoodReads:
    # https://www.goodreads.com/api/

    def __init__(self, name=None):
        self.name = makeUnicode(name)
        # self.type = type
        if not lazylibrarian.CONFIG['GR_API']:
            logger.warn('No Goodreads API key, check config')
        self.params = {"key": lazylibrarian.CONFIG['GR_API']}

    def find_results(self, searchterm=None, queue=None):
        # noinspection PyBroadException
        try:
            resultlist = []
            api_hits = 0
            searchtitle = ''
            searchauthorname = ''

            if ' <ll> ' in searchterm:  # special token separates title from author
                searchtitle, searchauthorname = searchterm.split(' <ll> ')
                searchterm = searchterm.replace(' <ll> ', ' ')

            if PY2:
                searchterm = searchterm.encode(lazylibrarian.SYS_ENCODING)
            url = quote_plus(searchterm)
            set_url = 'https://www.goodreads.com/search.xml?q=' + url + '&' + urlencode(self.params)
            logger.debug('Now searching GoodReads API with searchterm: %s' % searchterm)
            # logger.debug('Searching for %s at: %s' % (searchterm, set_url))

            resultcount = 0
            try:
                try:
                    rootxml, in_cache = gr_xml_request(set_url)
                except Exception as e:
                    logger.error("%s finding gr results: %s" % (type(e).__name__, str(e)))
                    return
                if rootxml is None:
                    logger.debug("Error requesting results")
                    return

                totalresults = check_int(rootxml.find('search/total-results').text, 0)

                resultxml = rootxml.getiterator('work')
                loopCount = 1
                while resultxml:
                    for author in resultxml:
                        try:
                            if author.find('original_publication_year').text is None:
                                bookdate = "0000"
                            else:
                                bookdate = author.find('original_publication_year').text
                        except (KeyError, AttributeError):
                            bookdate = "0000"

                        try:
                            authorNameResult = author.find('./best_book/author/name').text
                            # Goodreads sometimes puts extra whitespace in the author names!
                            authorNameResult = ' '.join(authorNameResult.split())
                        except (KeyError, AttributeError):
                            authorNameResult = ""

                        booksub = ""
                        bookpub = ""
                        booklang = "Unknown"

                        try:
                            bookimg = author.find('./best_book/image_url').text
                            if bookimg == 'https://www.goodreads.com/assets/nocover/111x148.png':
                                bookimg = 'images/nocover.png'
                        except (KeyError, AttributeError):
                            bookimg = 'images/nocover.png'

                        try:
                            bookrate = author.find('average_rating').text
                        except KeyError:
                            bookrate = 0
                        try:
                            bookrate_count = int(author.find('ratings_count').text)
                        except KeyError:
                            bookrate_count = 0

                        bookpages = '0'
                        bookgenre = ''
                        bookdesc = ''
                        bookisbn = ''
                        workid = ''

                        try:
                            booklink = 'https://www.goodreads.com/book/show/' + author.find('./best_book/id').text
                        except (KeyError, AttributeError):
                            booklink = ""

                        try:
                            authorid = author.find('./best_book/author/id').text
                        except (KeyError, AttributeError):
                            authorid = ""

                        try:
                            if author.find('./best_book/title').text is None:
                                bookTitle = ""
                            else:
                                bookTitle = author.find('./best_book/title').text
                        except (KeyError, AttributeError):
                            bookTitle = ""

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
                            bookisbn = searchterm

                        highest_fuzz = max((author_fuzz + book_fuzz) / 2, isbn_fuzz)

                        try:
                            bookid = author.find('./best_book/id').text
                        except (KeyError, AttributeError):
                            bookid = ""

                        resultlist.append({
                            'authorname': authorNameResult,
                            'bookid': bookid,
                            'authorid': authorid,
                            'bookname': bookTitle,
                            'booksub': booksub,
                            'bookisbn': bookisbn,
                            'bookpub': bookpub,
                            'bookdate': bookdate,
                            'booklang': booklang,
                            'booklink': booklink,
                            'bookrate': float(bookrate),
                            'bookrate_count': bookrate_count,
                            'bookimg': bookimg,
                            'bookpages': bookpages,
                            'bookgenre': bookgenre,
                            'bookdesc': bookdesc,
                            'workid': workid,
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
                    elif totalresults and resultcount >= totalresults:
                        # fix for goodreads bug on isbn searches
                        resultxml = None
                    else:
                        URL = set_url + '&page=' + str(loopCount)
                        resultxml = None
                        try:
                            rootxml, in_cache = gr_xml_request(URL)
                            if rootxml is None:
                                logger.debug('Error requesting page %s of results' % loopCount)
                            else:
                                resultxml = rootxml.getiterator('work')
                                if not in_cache:
                                    api_hits += 1
                        except Exception as e:
                            resultxml = None
                            logger.error("%s finding page %s of results: %s" % (type(e).__name__, loopCount, str(e)))

                    if resultxml:
                        if all(False for _ in resultxml):  # returns True if iterator is empty
                            resultxml = None

            except Exception as err:
                if hasattr(err, 'code') and err.code == 404:
                    logger.error('Received a 404 error when searching for author')
                elif hasattr(err, 'code') and err.code == 403:
                    logger.warn('Access to api is denied 403: usage exceeded')
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
        URL = 'https://www.goodreads.com/api/author_url/' + quote(author) + \
              '?' + urlencode(self.params)

        # googlebooks gives us author names with long form unicode characters
        author = makeUnicode(author)  # ensure it's unicode
        author = unicodedata.normalize('NFC', author)  # normalize to short form

        logger.debug("Searching for author with name: %s" % author)

        authorlist = []
        try:
            rootxml, in_cache = gr_xml_request(URL, useCache=not refresh)
        except Exception as e:
            logger.error("%s finding authorid: %s, %s" % (type(e).__name__, URL, str(e)))
            return authorlist
        if rootxml is None:
            logger.debug("Error requesting authorid")
            return authorlist

        resultxml = rootxml.getiterator('author')

        if resultxml is None:
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

        URL = 'https://www.goodreads.com/author/show/' + authorid + '.xml?' + urlencode(self.params)
        author_dict = {}
        try:
            rootxml, in_cache = gr_xml_request(URL)
        except Exception as e:
            logger.error("%s getting author info: %s" % (type(e).__name__, str(e)))
            return author_dict
        if rootxml is None:
            logger.debug("Error requesting author info")
            return author_dict

        resultxml = rootxml.find('author')

        if resultxml is None:
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

    @staticmethod
    def get_bookdict(book):
        """ Return all the book info we need as a dictionary or default value if no key """
        mydict = {}
        for val, idx, default in [
                ('name', 'title', ''),
                ('id', 'id', ''),
                ('desc', 'description', ''),
                ('pub', 'publisher', ''),
                ('link', 'link', ''),
                ('rate', 'average_rating', 0.0),
                ('pages', 'num_pages', 0),
                ('date', 'publication_year', '0000'),
                ('workid', 'work/id', ''),
                ('isbn13', 'isbn13', ''),
                ('isbn10', 'isbn', ''),
                ('img', 'image_url', '')
                ]:

                value = default
                res = book.find(idx)
                if res is not None:
                    value = res.text
                if value is None:
                    value = default
                if idx == 'rate':
                    value = float(value)
                mydict[val] = value

        return mydict

    def get_author_books(self, authorid=None, authorname=None, bookstatus="Skipped", audiostatus='Skipped',
                         entrystatus='Active', refresh=False):
        # noinspection PyBroadException
        try:
            api_hits = 0
            gr_lang_hits = 0
            lt_lang_hits = 0
            gb_lang_change = 0
            cache_hits = 0
            not_cached = 0
            URL = 'https://www.goodreads.com/author/list/' + authorid + '.xml?' + urlencode(self.params)

            # Artist is loading
            myDB = database.DBConnection()
            controlValueDict = {"AuthorID": authorid}
            newValueDict = {"Status": "Loading"}
            myDB.upsert("authors", newValueDict, controlValueDict)

            try:
                rootxml, in_cache = gr_xml_request(URL, useCache=not refresh)
            except Exception as e:
                logger.error("%s fetching author books: %s" % (type(e).__name__, str(e)))
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
            loopCount = 0
            cover_count = 0
            isbn_count = 0
            cover_time = 0
            isbn_time = 0
            auth_start = time.time()
            # these are reject reasons we might want to override, so optionally add to database as "ignored"
            ignorable = ['future', 'date', 'isbn', 'word', 'set']
            if lazylibrarian.CONFIG['NO_LANG']:
                ignorable.append('lang')

            if resultxml is None:
                logger.warn('[%s] No books found for author with ID: %s' % (authorname, authorid))
            else:
                logger.debug("[%s] Now processing books with GoodReads API" % authorname)
                logger.debug("url " + URL)
                authorNameResult = rootxml.find('./author/name').text
                # Goodreads sometimes puts extra whitespace in the author names!
                authorNameResult = ' '.join(authorNameResult.split())
                logger.debug("GoodReads author name [%s]" % authorNameResult)
                loopCount = 1

                while resultxml:
                    for book in resultxml:
                        total_count += 1
                        rejected = None
                        reason = ''
                        booksub = ''
                        series = ''
                        seriesNum = ''
                        bookLanguage = "Unknown"
                        find_field = "id"
                        bookisbn = ""
                        isbnhead = ""

                        bookdict = self.get_bookdict(book)

                        bookname = bookdict['name']
                        bookid = bookdict['id']
                        bookdesc = bookdict['desc']
                        bookpub = bookdict['pub']
                        booklink = bookdict['link']
                        bookrate = bookdict['rate']
                        bookpages = bookdict['pages']
                        bookdate = bookdict['date']
                        bookimg = bookdict['img']
                        workid = bookdict['workid']
                        isbn13 = bookdict['isbn13']
                        isbn10 = bookdict['isbn10']

                        if not bookname:
                            logger.debug('Rejecting bookid %s for %s, no bookname' %
                                         (bookid, authorNameResult))
                            rejected = 'name', 'No bookname'

                        if not rejected and re.match('[^\w-]', bookname):  # reject books with bad characters in title
                            logger.debug("removed result [" + bookname + "] for bad characters")
                            rejected = 'chars', 'Bad characters in bookname'

                        if not rejected:
                            if lazylibrarian.CONFIG['NO_FUTURE']:
                                if bookdate > today()[:4]:
                                    rejected = 'future', 'Future publication date [%s]' % bookdate
                                    logger.debug('Rejecting %s, %s' % (bookname, rejected[1]))

                        if not rejected:
                            if lazylibrarian.CONFIG['NO_PUBDATE']:
                                if not bookdate or bookdate == '0000':
                                    rejected = 'date', 'No publication date'
                                    logger.debug('Rejecting %s, %s' % (bookname, rejected[1]))

                        if not rejected:
                            if not bookimg or 'nocover' in bookimg:
                                bookimg = 'images/nocover.png'

                            if isbn13:
                                find_field = "isbn13"
                                bookisbn = isbn13
                                isbnhead = bookisbn[3:6]
                            elif isbn10:
                                    find_field = "isbn"
                                    bookisbn = isbn10
                                    isbnhead = bookisbn[0:3]

                            if not isbnhead and lazylibrarian.CONFIG['ISBN_LOOKUP']:
                                # try lookup by name
                                if bookname:
                                    try:
                                        isbn_count += 1
                                        start = time.time()
                                        res = isbn_from_words(unaccented(bookname) + ' ' +
                                                              unaccented(authorNameResult))
                                        isbn_time += (time.time() - start)
                                    except Exception as e:
                                        res = None
                                        logger.warn("Error from isbn: %s" % e)
                                    if res:
                                        logger.debug("isbn found %s for %s" % (res, bookid))
                                        bookisbn = res
                                        if len(res) == 13:
                                            isbnhead = res[3:6]
                                        else:
                                            isbnhead = res[0:3]

                            # Try to use shortcut of ISBN identifier codes described here...
                            # http://en.wikipedia.org/wiki/List_of_ISBN_identifier_groups
                            if isbnhead:
                                if find_field == "isbn13" and bookisbn.startswith('979'):
                                    for item in lazylibrarian.isbn_979_dict:
                                        if isbnhead.startswith(item):
                                            bookLanguage = lazylibrarian.isbn_979_dict[item]
                                            break
                                    if bookLanguage != "Unknown":
                                        logger.debug("ISBN979 returned %s for %s" % (bookLanguage, isbnhead))
                                elif (find_field == "isbn") or (find_field == "isbn13" and
                                                                bookisbn.startswith('978')):
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
                                    bookLanguage = thingLang(bookisbn)
                                    lt_lang_hits += 1
                                    if bookLanguage:
                                        myDB.action('insert into languages values (?, ?)', (isbnhead, bookLanguage))

                            if not bookLanguage or bookLanguage == "Unknown":
                                # still  no earlier match, we'll have to search the goodreads api
                                try:
                                    if book.find(find_field).text:
                                        BOOK_URL = 'https://www.goodreads.com/book/show?id=' + \
                                                   book.find(find_field).text + \
                                                   '&' + urlencode(self.params)
                                        logger.debug("Book URL: " + BOOK_URL)
                                        bookLanguage = ""
                                        try:
                                            BOOK_rootxml, in_cache = gr_xml_request(BOOK_URL)
                                            if BOOK_rootxml is None:
                                                logger.debug('Error requesting book page')
                                            else:
                                                try:
                                                    bookLanguage = BOOK_rootxml.find('./book/language_code').text
                                                except Exception as e:
                                                    logger.error("%s finding language_code in book xml: %s" %
                                                                 (type(e).__name__, str(e)))
                                                # noinspection PyBroadException
                                                try:
                                                    res = BOOK_rootxml.find('./book/isbn').text
                                                    isbnhead = res[0:3]
                                                except Exception:
                                                    # noinspection PyBroadException
                                                    try:
                                                        res = BOOK_rootxml.find('./book/isbn13').text
                                                        isbnhead = res[3:6]
                                                    except Exception:
                                                        isbnhead = ''
                                                # if bookLanguage and not isbnhead:
                                                #     print(BOOK_URL)
                                        except Exception as e:
                                            logger.error("%s getting book xml: %s" % (type(e).__name__, str(e)))

                                        if not in_cache:
                                            gr_lang_hits += 1
                                        if not bookLanguage:
                                            bookLanguage = "Unknown"
                                        elif isbnhead:
                                            # if GR didn't give an isbn we can't cache it
                                            # just use language for this book
                                            myDB.action('insert into languages values (?, ?)',
                                                        (isbnhead, bookLanguage))
                                            logger.debug("GoodReads reports language [%s] for %s" %
                                                         (bookLanguage, isbnhead))
                                        else:
                                            not_cached += 1

                                        logger.debug("GR language: " + bookLanguage)
                                    else:
                                        logger.debug("No %s provided for [%s]" % (find_field, bookname))
                                        # continue

                                except Exception as e:
                                    logger.error("Goodreads language search failed: %s %s" %
                                                 (type(e).__name__, str(e)))

                            if not isbnhead and lazylibrarian.CONFIG['NO_ISBN']:
                                rejected = 'isbn', 'No ISBN'
                                logger.debug('Rejecting %s, %s' % (bookname, rejected[1]))

                            if "All" not in valid_langs:  # do we care about language
                                if bookLanguage not in valid_langs:
                                    rejected = 'lang', 'Invalid language [%s]' % bookLanguage
                                    logger.debug('Rejecting %s, %s' % (bookname, rejected[1]))

                        if not rejected:
                            dic = {'.': ' ', '-': ' ', '/': ' ', '+': ' ', '_': ' ', '(': '', ')': '',
                                   '[': ' ', ']': ' ', '#': '# ', ':': ' ', ';': ' '}
                            name = replace_all(bookname, dic).strip()
                            name = name.lower()
                            # remove extra spaces if they're in a row
                            name = " ".join(name.split())
                            namewords = name.split(' ')
                            badwords = getList(lazylibrarian.CONFIG['REJECT_WORDS'], ',')
                            for word in badwords:
                                if (' ' in word and word in name) or word in namewords:
                                    rejected = 'word', 'Contains [%s]' % word
                                    logger.debug('Rejecting %s, %s' % (bookname, rejected[1]))
                                    break

                        if not rejected:
                            bookname = unaccented(bookname)
                            if lazylibrarian.CONFIG['NO_SETS']:
                                if re.search(r'\d+ of \d+', bookname) or \
                                        re.search(r'\d+/\d+', bookname):
                                    rejected = 'set', 'Set or Part'
                                    logger.debug('Rejected %s, %s' % (bookname, rejected[1]))
                        if not rejected:
                            bookname = unaccented(bookname)
                            if lazylibrarian.CONFIG['NO_SETS']:
                                # allow date ranges eg 1981-95
                                m = re.search(r'(\d+)-(\d+)', bookname)
                                if m:
                                    if check_year(m.group(1), past=1800, future=0):
                                        logger.debug("Allow %s, looks like a date range" % bookname)
                                    else:
                                        rejected = 'set', 'Set or Part %s' % m.group(0)
                                        logger.debug('Rejected %s, %s' % (bookname, rejected[1]))

                        if not rejected:
                            bookname, booksub = split_title(authorNameResult, bookname)
                            dic = {':': '.', '"': ''}  # do we need to strip apostrophes , '\'': ''}
                            bookname = replace_all(bookname, dic)
                            bookname = bookname.strip()
                            booksub = replace_all(booksub, dic)
                            booksub = booksub.strip()
                            if booksub:
                                seriesdetails = booksub
                            else:
                                seriesdetails = bookname

                            series, seriesNum = bookSeries(seriesdetails)

                            # seems the author/list page only contains one author per book
                            # even if the book/show page has multiple?
                            authors = book.find('authors')
                            anames = authors.getiterator('author')
                            amatch = False
                            alist = ''
                            role = ''
                            for aname in anames:
                                aid = aname.find('id').text
                                anm = aname.find('name').text
                                role = aname.find('role').text
                                if alist:
                                    alist += ', '
                                alist += anm
                                if aid == authorid or anm == authorNameResult:
                                    if aid != authorid:
                                        logger.warn("Author %s has different authorid %s:%s" % (anm, aid, authorid))
                                    if role is None or 'author' in role.lower() or \
                                            'creator' in role.lower() or \
                                            'pseudonym' in role.lower() or \
                                            'pen name' in role.lower():
                                        amatch = True
                                    else:
                                        logger.debug('Ignoring %s for %s, role is %s' % (anm, bookname, role))
                            if not amatch:
                                rejected = 'author', 'Wrong Author (got %s,%s)' % (alist, role)
                                logger.debug('Rejecting %s for %s, %s' %
                                             (bookname, authorNameResult, rejected[1]))

                        if not rejected:
                            cmd = 'SELECT BookID FROM books,authors WHERE books.AuthorID = authors.AuthorID'
                            cmd += ' and BookName=? COLLATE NOCASE and AuthorName=? COLLATE NOCASE'
                            match = myDB.match(cmd, (bookname, authorNameResult.replace('"', '""')))
                            if match:
                                if match['BookID'] != bookid:
                                    # we have a different bookid for this author/title already
                                    duplicates += 1
                                    rejected = 'bookid', 'Got %s under bookid %s' % (bookid, match['BookID'])
                                    logger.debug('Rejecting bookid %s for [%s][%s] already got %s' %
                                                 (bookid, authorNameResult, bookname, match['BookID']))

                        if not rejected:
                            cmd = 'SELECT AuthorName,BookName,books.Status FROM books,authors'
                            cmd += ' WHERE authors.AuthorID = books.AuthorID AND BookID=?'
                            match = myDB.match(cmd, (bookid,))
                            if match:
                                # we have a book with this bookid already
                                if match['BookName'] == 'Untitled' and bookname != 'Untitled':
                                    # goodreads has updated the name
                                    logger.debug('Renaming bookid %s for [%s][%s] to [%s]' %
                                                 (bookid, authorNameResult, match['BookName'], bookname))
                                elif bookname != match['BookName']:
                                    rejected = 'bookname', 'Different bookname for this bookid [%s][%s]' % (
                                                bookname, match['BookName'])
                                    logger.debug('Rejecting bookid %s, %s' % (bookid, rejected[1]))
                                elif authorNameResult != match['AuthorName']:
                                    rejected = 'author', 'Different author for this bookid [%s][%s]' % (
                                                authorNameResult, match['AuthorName'])
                                    logger.debug('Rejecting bookid %s, %s' % (bookid, rejected[1]))
                                else:
                                    logger.debug('Bookid %s for [%s][%s] is in database marked %s' %
                                                 (bookid, authorNameResult, bookname, match['Status']))

                        if rejected and rejected[0] not in ignorable:
                            removedResults += 1
                        if not rejected or (rejected and rejected[0] in ignorable and
                                             lazylibrarian.CONFIG['IMP_IGNORE']):
                            updated = False
                            cmd = 'SELECT Status,AudioStatus,Manual,BookAdded,BookName FROM books WHERE BookID=?'
                            existing = myDB.match(cmd, (bookid,))
                            if existing:
                                book_status = existing['Status']
                                audio_status = existing['AudioStatus']
                                locked = existing['Manual']
                                added = existing['BookAdded']
                                if bookname != existing['BookName']:
                                    updated = True
                                if locked is None:
                                    locked = False
                                elif locked.isdigit():
                                    locked = bool(int(locked))
                            else:
                                book_status = bookstatus  # new_book status, or new_author status
                                audio_status = audiostatus
                                added = today()
                                locked = False

                            if rejected:
                                reason = rejected[1]
                                if rejected[0] in ignorable:
                                    book_status = 'Ignored'
                                    audio_status = 'Ignored'
                                    book_ignore_count += 1
                            else:
                                reason = ''

                            # Leave alone if locked
                            if not locked:
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
                                    "BookDate": bookdate,
                                    "BookLang": bookLanguage,
                                    "Status": book_status,
                                    "AudioStatus": audio_status,
                                    "BookAdded": added,
                                    "WorkID": workid,
                                    "ScanResult": reason
                                }

                                resultsCount += 1

                                myDB.upsert("books", newValueDict, controlValueDict)
                                # logger.debug("Book found: %s %s" % (bookname, bookdate))

                                if 'nocover' in bookimg or 'nophoto' in bookimg:
                                    # try to get a cover from another source
                                    start = time.time()
                                    workcover, source = getBookCover(bookid)
                                    if source != 'cache':
                                        cover_count += 1
                                        cover_time += (time.time() - start)

                                    if workcover:
                                        logger.debug('Updated cover for %s using %s' % (bookname, source))
                                        controlValueDict = {"BookID": bookid}
                                        newValueDict = {"BookImg": workcover}
                                        myDB.upsert("books", newValueDict, controlValueDict)
                                        updated = True

                                elif bookimg and bookimg.startswith('http'):
                                    start = time.time()
                                    link, success, was_already_cached = cache_img("book", bookid, bookimg)
                                    if not was_already_cached:
                                        cover_count += 1
                                        cover_time += (time.time() - start)
                                    if success:
                                        controlValueDict = {"BookID": bookid}
                                        newValueDict = {"BookImg": link}
                                        myDB.upsert("books", newValueDict, controlValueDict)
                                        updated = True
                                    else:
                                        logger.debug('Failed to cache image for %s' % bookimg)

                                serieslist = []
                                if series:
                                    serieslist = [('', seriesNum, cleanName(unaccented(series), '&/'))]
                                if lazylibrarian.CONFIG['ADD_SERIES']:
                                    newserieslist = getWorkSeries(workid)
                                    if newserieslist:
                                        serieslist = newserieslist
                                        logger.debug('Updated series: %s [%s]' % (bookid, serieslist))
                                        updated = True
                                setSeries(serieslist, bookid)

                                if not rejected:
                                    new_status = setStatus(bookid, serieslist, bookstatus)

                                    if new_status != book_status:
                                        book_status = new_status
                                        updated = True

                                worklink = getWorkPage(bookid)
                                if worklink:
                                    controlValueDict = {"BookID": bookid}
                                    newValueDict = {"WorkPage": worklink}
                                    myDB.upsert("books", newValueDict, controlValueDict)

                                if not existing:
                                    logger.debug("[%s] Added book: %s [%s] status %s" %
                                                 (authorname, bookname, bookLanguage, book_status))
                                    added_count += 1
                                elif updated:
                                    logger.debug("[%s] Updated book: %s [%s] status %s" %
                                                 (authorname, bookname, bookLanguage, book_status))
                                    updated_count += 1

                    loopCount += 1
                    if 0 < lazylibrarian.CONFIG['MAX_BOOKPAGES'] < loopCount:
                        resultxml = None
                    else:
                        URL = 'https://www.goodreads.com/author/list/' + authorid + '.xml?' + \
                              urlencode(self.params) + '&page=' + str(loopCount)
                        resultxml = None
                        try:
                            rootxml, in_cache = gr_xml_request(URL, useCache=not refresh)
                            if rootxml is None:
                                logger.debug('Error requesting next page of results')
                            else:
                                resultxml = rootxml.getiterator('book')
                                if not in_cache:
                                    api_hits += 1
                        except Exception as e:
                            resultxml = None
                            logger.error("%s finding next page of results: %s" % (type(e).__name__, str(e)))

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
                "Status": entrystatus,
                "LastBook": lastbookname,
                "LastLink": lastbooklink,
                "LastDate": lastbookdate,
                "LastBookImg": lastbookimg
            }
            myDB.upsert("authors", newValueDict, controlValueDict)

            # This is here because GoodReads sometimes has several entries with the same BookID!
            modified_count = added_count + updated_count
            loopCount -= 1
            logger.debug("Found %s result%s in %s page%s" % (total_count, plural(total_count),
                                                             loopCount, plural(loopCount)))
            logger.debug("Removed %s unwanted language result%s" % (ignored, plural(ignored)))
            logger.debug("Removed %s incorrect/incomplete result%s" % (removedResults, plural(removedResults)))
            logger.debug("Removed %s duplicate result%s" % (duplicates, plural(duplicates)))
            logger.debug("Marked %s book%s by author as Ignored" % (book_ignore_count, plural(book_ignore_count)))
            logger.debug("Imported/Updated %s book%s in %d secs" % (modified_count, plural(modified_count),
                                                                    int(time.time() - auth_start)))
            if cover_count:
                logger.debug("Fetched %s cover%s in %.2f sec" % (cover_count, plural(cover_count), cover_time))
            if isbn_count:
                logger.debug("Fetched %s ISBN in %.2f sec" % (isbn_count, isbn_time))

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

    def find_book(self, bookid=None, bookstatus=None, audiostatus=None):
        myDB = database.DBConnection()
        reason = ''
        URL = 'https://www.goodreads.com/book/show/' + bookid + '?' + urlencode(self.params)

        try:
            rootxml, in_cache = gr_xml_request(URL)
            if rootxml is None:
                logger.debug("Error requesting book")
                return
        except Exception as e:
            logger.error("%s finding book: %s" % (type(e).__name__, str(e)))
            return

        if not bookstatus:
            bookstatus = lazylibrarian.CONFIG['NEWBOOK_STATUS']
        if not audiostatus:
            audiostatus = lazylibrarian.CONFIG['NEWAUDIO_STATUS']
        bookLanguage = rootxml.find('./book/language_code').text
        bookname = rootxml.find('./book/title').text

        if not bookLanguage:
            bookLanguage = "Unknown"
        #
        # user has said they want this book, don't block for unwanted language, just warn
        #
        valid_langs = getList(lazylibrarian.CONFIG['IMP_PREFLANG'])
        if bookLanguage not in valid_langs:
            reason = 'Language [%s] does not match preference' % bookLanguage
            logger.warn('Book %s, %s' % (bookname, reason))

        if rootxml.find('./book/publication_year').text is None:
            bookdate = "0000"
        else:
            bookdate = rootxml.find('./book/publication_year').text

        if lazylibrarian.CONFIG['NO_PUBDATE']:
            if not bookdate or bookdate == '0000':
                reason = 'Publication date [%s] does not match preference' % bookdate
                logger.warn('Book %s, %s' % (bookname, reason))

        if lazylibrarian.CONFIG['NO_FUTURE']:
            if bookdate > today()[:4]:
                reason = 'Future publication date [%s] does not match preference' % bookdate
                logger.warn('Book %s, %s' % (bookname, reason))
        try:
            bookimg = rootxml.find('./book/img_url').text
            if 'assets/nocover' in bookimg:
                bookimg = 'images/nocover.png'
        except (KeyError, AttributeError):
            bookimg = 'images/nocover.png'

        authorname = rootxml.find('./book/authors/author/name').text
        bookdesc = rootxml.find('./book/description').text
        bookisbn = rootxml.find('./book/isbn13').text
        if not bookisbn:
            bookisbn = rootxml.find('./book/isbn').text
        bookpub = rootxml.find('./book/publisher').text
        booklink = rootxml.find('./book/link').text
        bookrate = float(rootxml.find('./book/average_rating').text)
        bookpages = rootxml.find('.book/num_pages').text
        workid = rootxml.find('.book/work/id').text

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
                    # User hit "add book" button from a search, or a wishlist import, or api call
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

        if not bookisbn:
            try:
                res = isbn_from_words(bookname + ' ' + unaccented(authorname))
            except Exception as e:
                res = None
                logger.warn("Error from isbn: %s" % e)
            if res:
                logger.debug("isbn found %s for %s" % (res, bookname))
                bookisbn = res

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
            "Status": bookstatus,
            "AudioStatus": audiostatus,
            "BookAdded": today(),
            "WorkID": workid,
            "ScanResult": reason
        }

        myDB.upsert("books", newValueDict, controlValueDict)
        logger.info("%s by %s added to the books database" % (bookname, authorname))

        if 'nocover' in bookimg or 'nophoto' in bookimg:
            # try to get a cover from another source
            workcover, source = getBookCover(bookid)
            if workcover:
                logger.debug('Updated cover for %s using %s' % (bookname, source))
                controlValueDict = {"BookID": bookid}
                newValueDict = {"BookImg": workcover}
                myDB.upsert("books", newValueDict, controlValueDict)

        elif bookimg and bookimg.startswith('http'):
            link, success, _ = cache_img("book", bookid, bookimg)
            if success:
                controlValueDict = {"BookID": bookid}
                newValueDict = {"BookImg": link}
                myDB.upsert("books", newValueDict, controlValueDict)
            else:
                logger.debug('Failed to cache image for %s' % bookimg)

        serieslist = []
        if series:
            serieslist = [('', seriesNum, cleanName(unaccented(series), '&/'))]
        if lazylibrarian.CONFIG['ADD_SERIES']:
            newserieslist = getWorkSeries(workid)
            if newserieslist:
                serieslist = newserieslist
                logger.debug('Updated series: %s [%s]' % (bookid, serieslist))
        setSeries(serieslist, bookid)

        worklink = getWorkPage(bookid)
        if worklink:
            controlValueDict = {"BookID": bookid}
            newValueDict = {"WorkPage": worklink}
            myDB.upsert("books", newValueDict, controlValueDict)
