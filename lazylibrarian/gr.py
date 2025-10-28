#  This file is part of Lazylibrarian.
#  Lazylibrarian is free software, you can redistribute it and/or modify
#  it under the terms of the GNU General Public License as published by
#  the Free Software Foundation, either version 3 of the License, or
#  (at your option) any later version.
#  Lazylibrarian is distributed in the hope that it will be useful,
#  but WITHOUT ANY WARRANTY; without even the implied warranty of
#  MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
#  GNU General Public License for more details.
#  You should have received a copy of the GNU General Public License
#  along with Lazylibrarian.  If not, see <http://www.gnu.org/licenses/>.

import logging
import time
import traceback
import unicodedata
from urllib.parse import quote, quote_plus, urlencode

from rapidfuzz import fuzz

import lazylibrarian
from lazylibrarian import database, ROLE
from lazylibrarian.bookwork import get_work_series, delete_empty_series, \
    set_series, get_status, isbn_from_words, isbnlang, get_book_pubdate, get_gb_info, \
    get_gr_genres, set_genres, genre_filter, is_set_or_part
from lazylibrarian.cache import gr_xml_request, html_request
from lazylibrarian.config2 import CONFIG
from lazylibrarian.formatter import plural, today, replace_all, book_series, unaccented, split_title, get_list, \
    clean_name, is_valid_isbn, format_author_name, check_int, make_unicode, check_year, check_float, \
    make_utf8bytes, thread_name, date_format
from lazylibrarian.images import cache_bookimg, get_book_cover
from lazylibrarian.common import extract_series_number, validate_series_match


class GoodReads:
    # https://www.goodreads.com/api/

    def __init__(self):
        self.logger = logging.getLogger(__name__)
        self.searchinglogger = logging.getLogger('special.searching')
        if not CONFIG['GR_API']:
            self.logger.warning('No Goodreads API key, check config')
        self.params = {"key": CONFIG['GR_API']}

    def find_results(self, searchterm=None, queue=None):
        # noinspection PyBroadException
        try:
            resultlist = []
            api_hits = 0
            searchtitle = ''
            searchauthorname = ''

            if '<ll>' in searchterm:  # special token separates title from author
                searchtitle, searchauthorname = searchterm.split('<ll>')
                searchterm = searchterm.replace('<ll>', ' ')
                searchtitle = searchtitle.split(' (')[0]  # without any series info

            url = quote_plus(make_utf8bytes(searchterm)[0])
            set_url = '/'.join([CONFIG['GR_URL'],
                                f"search.xml?q={url}&{urlencode(self.params)}"])
            self.logger.debug(f'Now searching GoodReads API with searchterm: {searchterm}')
            self.searchinglogger.debug(set_url)

            resultcount = 0
            try:
                try:
                    rootxml, in_cache = gr_xml_request(set_url)
                except Exception as e:
                    self.logger.error(f"{type(e).__name__} finding gr results: {str(e)}")
                    queue.put(resultlist)
                    return
                if rootxml is None:
                    self.logger.debug("Error requesting results")
                    queue.put(resultlist)
                    return

                totalresults = check_int(rootxml.find('search/total-results').text, 0)

                resultxml = rootxml.iter('work')
                loop_count = 1
                while resultxml:
                    contents = {}
                    for item in rootxml.iter('books'):
                        contents = item.attrib
                    for author in resultxml:
                        try:
                            if author.find('original_publication_year').text is None:
                                bookdate = "0000"
                            elif check_year(author.find('original_publication_year').text, past=1800, future=0):
                                bookdate = author.find('original_publication_year').text
                                try:
                                    bookmonth = check_int(author.find('original_publication_month').text, 0)
                                    bookday = check_int(author.find('original_publication_day').text, 0)
                                    if bookmonth and bookday:
                                        bookdate = "%s-%02d-%02d" % (bookdate, bookmonth, bookday)
                                except (KeyError, AttributeError):
                                    pass
                            else:
                                bookdate = "0000"
                        except (KeyError, AttributeError):
                            bookdate = "0000"

                        try:
                            author_name_result = author.find('./best_book/author/name').text
                            # Goodreads sometimes puts extra whitespace in the author names!
                            author_name_result = ' '.join(author_name_result.split())
                        except (KeyError, AttributeError):
                            author_name_result = ""

                        booksub = ""
                        bookpub = ""
                        booklang = "Unknown"

                        try:
                            bookimg = author.find('./best_book/image_url').text
                            if not bookimg or 'nocover' in bookimg or 'nophoto' in bookimg:
                                bookimg = 'images/nocover.png'
                        except (KeyError, AttributeError):
                            bookimg = 'images/nocover.png'

                        try:
                            bookrate = check_float(author.find('average_rating').text, 0)
                        except KeyError:
                            bookrate = 0.0
                        try:
                            bookrate_count = check_int(author.find('ratings_count').text, 0)
                        except KeyError:
                            bookrate_count = 0

                        bookpages = '0'
                        bookgenre = ''
                        bookdesc = ''
                        bookisbn = ''
                        workid = ''

                        try:
                            booklink = '/'.join([CONFIG['GR_URL'],
                                                 f"book/show/{author.find('./best_book/id').text}"])
                        except (KeyError, AttributeError):
                            booklink = ""

                        try:
                            authorid = author.find('./best_book/author/id').text
                        except (KeyError, AttributeError):
                            authorid = ""

                        try:
                            if author.find('./best_book/title').text is None:
                                book_title = ""
                            else:
                                book_title = author.find('./best_book/title').text
                        except (KeyError, AttributeError):
                            book_title = ""

                        if searchauthorname:
                            author_fuzz = fuzz.token_sort_ratio(author_name_result, searchauthorname)
                        else:
                            author_fuzz = fuzz.token_sort_ratio(author_name_result, searchterm)
                        if searchtitle:
                            if book_title.endswith(')'):
                                book_title = book_title.rsplit(' (', 1)[0]
                            book_fuzz = fuzz.token_set_ratio(book_title, searchtitle)
                            # lose a point for each extra word in the fuzzy matches so we get the closest match
                            words = len(get_list(book_title))
                            words -= len(get_list(searchtitle))
                            book_fuzz -= abs(words)
                        else:
                            book_fuzz = fuzz.token_set_ratio(book_title, searchterm)
                            words = len(get_list(book_title))
                            words -= len(get_list(searchterm))
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

                        # Don't query google for every book we find, it's too slow and too many
                        # api hits. Only query the ones we want to add to db later
                        # if not bookdesc:
                        #     bookdesc = get_book_desc(isbn=bookisbn, author=authorNameResult, title=bookTitle)
                        resultlist.append({
                            'authorname': author_name_result,
                            'bookid': bookid,
                            'authorid': authorid,
                            'bookname': book_title,
                            'booksub': booksub,
                            'bookisbn': bookisbn,
                            'bookpub': bookpub,
                            'bookdate': bookdate,
                            'booklang': booklang,
                            'booklink': booklink,
                            'bookrate': bookrate,
                            'bookrate_count': bookrate_count,
                            'bookimg': bookimg,
                            'bookpages': bookpages,
                            'bookgenre': bookgenre,
                            'bookdesc': bookdesc,
                            'workid': workid,
                            'author_fuzz': round(author_fuzz, 2),
                            'book_fuzz': round(book_fuzz, 2),
                            'isbn_fuzz': round(isbn_fuzz, 2),
                            'highest_fuzz': round(highest_fuzz, 2),
                            'source': 'GoodReads'
                        })

                        resultcount += 1

                    loop_count += 1

                    if 0 < CONFIG.get_int('MAX_PAGES') < loop_count:
                        resultxml = None
                        self.logger.warning('Maximum results page search reached, still more results available')
                    elif totalresults and resultcount >= totalresults:
                        # fix for goodreads bug on isbn searches
                        resultxml = None
                    elif contents.get('end') == contents.get('total'):
                        # this was last page of results
                        resultxml = None
                    else:
                        url = f"{set_url}&page={str(loop_count)}"
                        resultxml = None
                        self.searchinglogger.debug(set_url)
                        try:
                            rootxml, in_cache = gr_xml_request(url)
                            if rootxml is None:
                                self.logger.debug(f'Error requesting page {loop_count} of results')
                            else:
                                resultxml = rootxml.iter('work')
                                if not in_cache:
                                    api_hits += 1
                        except Exception as e:
                            resultxml = None
                            self.logger.error(f"{type(e).__name__} finding page {loop_count} of results: {str(e)}")

                    if resultxml:
                        if all(False for _ in resultxml):  # returns True if iterator is empty
                            resultxml = None

            except Exception as err:
                # noinspection PyUnresolvedReferences
                if hasattr(err, 'code') and err.code == 404:
                    self.logger.error('Received a 404 error when searching for author')
                # noinspection PyUnresolvedReferences
                elif hasattr(err, 'code') and err.code == 403:
                    self.logger.warning('Access to api is denied 403: usage exceeded')
                else:
                    self.logger.error(f'An unexpected error has occurred when searching for an author: {str(err)}')
                    self.logger.error(f'in GR.find_results: {traceback.format_exc()}')

            self.logger.debug(f"Found {resultcount} {plural(resultcount, 'result')} with keyword: {searchterm}")
            self.logger.debug(
                f"The GoodReads API was hit {api_hits} {plural(api_hits, 'time')} for keyword {searchterm}")

            queue.put(resultlist)

        except Exception:
            self.logger.error(f'Unhandled exception in GR.find_results: {traceback.format_exc()}')

    def find_author_id(self, authorname='', title='', refresh=False):
        author = authorname
        if '<ll>' in author:
            author, _ = author.split('<ll>')
        author = format_author_name(unaccented(author, only_ascii='_'),
                                    postfix=get_list(CONFIG.get_csv('NAME_POSTFIX')))
        # googlebooks gives us author names with long form unicode characters
        author = make_unicode(author)  # ensure it's unicode
        author = unicodedata.normalize('NFC', author)  # normalize to short form
        self.logger.debug(f"Getting GR author id for {author}, refresh={refresh}")
        url = '/'.join([CONFIG['GR_URL'], 'api/author_url/'])
        try:
            url += f"{quote(make_utf8bytes(author)[0])}?{urlencode(self.params)}"
            self.searchinglogger.debug(url)
            rootxml, _ = gr_xml_request(url, use_cache=not refresh)
        except Exception as e:
            self.logger.error(f"{type(e).__name__} finding authorid: {url}, {str(e)}")
            return {}
        if rootxml is None:
            self.logger.debug("Error requesting authorid")
            return {}

        resultxml = rootxml.iter('author')

        if resultxml is None:
            self.logger.warning(f'No authors found with name: {author}')
            return {}

        # In spite of how this looks, goodreads only returns one result, even if there are multiple matches
        # we just have to hope we get the right one. e.g. search for "James Lovelock" returns "James E. Lovelock"
        # who only has one book listed under googlebooks, the rest are under "James Lovelock"
        # goodreads has all his books under "James E. Lovelock". Can't come up with a good solution yet.
        # For now, we'll have to let the user handle this by selecting/adding the author manually
        for res in resultxml:
            authorid = res.attrib.get("id")
            authorname = res.find('name').text
            authorname = format_author_name(unaccented(authorname, only_ascii=False),
                                            postfix=get_list(CONFIG.get_csv('NAME_POSTFIX')))
            match = fuzz.ratio(author, authorname)
            if match >= CONFIG.get_int('NAME_RATIO'):
                return self.get_author_info(authorid)

            match = fuzz.partial_ratio(author, authorname)
            if match >= CONFIG.get_int('NAME_PARTNAME'):
                return self.get_author_info(authorid)
            self.logger.debug(f"Fuzz failed: {round(match, 2)} [{author}][{authorname}]")
        return {}

    def get_author_info(self, authorid=None, authorname=None):

        url = '/'.join([CONFIG['GR_URL'],
                        f"author/show/{authorid}.xml?{urlencode(self.params)}"])

        try:
            self.searchinglogger.debug(url)
            rootxml, _ = gr_xml_request(url)
        except Exception as e:
            self.logger.error(f"{type(e).__name__} getting author info: {str(e)}")
            return {}
        if rootxml is None:
            self.logger.debug(f"Failed to get author info for {authorid}")
            return {}

        resultxml = rootxml.find('author')
        if resultxml is None:
            self.logger.warning(f"No author found with ID: {authorid}")
            return {}

        # added authorname to author_dict - this holds the intact name preferred by GR
        # except GR messes up names like "L. E. Modesitt, Jr." where it returns <name>Jr., L. E. Modesitt</name>
        authorname = format_author_name(resultxml[1].text, postfix=get_list(CONFIG.get_csv('NAME_POSTFIX')))
        if resultxml[0].text:
            authorid = resultxml[0].text
        self.logger.debug(f"[{authorname}] Returning GR info for authorID: {authorid}")
        author_dict = {
            'authorid': authorid,
            'authorlink': resultxml.find('link').text,
            'authorimg': resultxml.find('image_url').text,
            'authorborn': resultxml.find('born_at').text,
            'authordeath': resultxml.find('died_at').text,
            'about': resultxml.find('about').text,
            'totalbooks': resultxml.find('works_count').text,
            'authorname': authorname
        }
        return author_dict

    @staticmethod
    def get_bookdict(book):
        """ Return all the book info we need as a dictionary or default value if no key """
        mydict = {}
        for val, idx, default in [
            ('name', 'title', ''),
            ('shortname', 'title_without_series', ''),
            ('id', 'id', ''),
            ('desc', 'description', ''),
            ('pub', 'publisher', ''),
            ('link', 'link', ''),
            ('rate', 'average_rating', 0.0),
            ('pages', 'num_pages', 0),
            ('pub_year', 'publication_year', '0000'),
            ('pub_month', 'publication_month', '0'),
            ('pub_day', 'publication_day', '0'),
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
                value = check_float(value, 0.0)
            mydict[val] = value

        return mydict

    def get_author_books(self, authorid=None, authorname=None, bookstatus="Skipped", audiostatus='Skipped',
                         entrystatus='Active', refresh=False, reason='gr.get_author_books'):
        # noinspection PyBroadException
        db = database.DBConnection()
        try:
            entryreason = reason
            api_hits = 0
            gr_lang_hits = 0
            lt_lang_hits = 0
            gb_lang_change = 0
            cache_hits = 0
            not_cached = 0

            # Artist is loading
            db.action("UPDATE authors SET Status='Loading' WHERE AuthorID=?", (authorid,))

            gr_id = ''
            match = db.match('SELECT gr_id,authorid FROM authors where authorid=? or gr_id=?', (authorid, authorid))
            if match:
                gr_id = match['gr_id']
                authorid = match['authorid']
            if not gr_id:
                gr_id = authorid

            url = '/'.join([CONFIG['GR_URL'],
                            f"author/list/{gr_id}.xml?{urlencode(self.params)}"])
            try:
                self.searchinglogger.debug(url)
                rootxml, in_cache = gr_xml_request(url, use_cache=not refresh)
            except Exception as e:
                self.logger.error(f"{type(e).__name__} fetching author books: {str(e)}")
                return
            if rootxml is None:
                self.logger.debug("Error requesting author books")
                return
            if not in_cache:
                api_hits += 1

            resultxml = rootxml.iter('book')

            valid_langs = get_list(CONFIG['IMP_PREFLANG'])

            removed_results = 0
            duplicates = 0
            bad_lang = 0
            added_count = 0
            updated_count = 0
            book_ignore_count = 0
            total_count = 0
            locked_count = 0
            loop_count = 0
            cover_count = 0
            isbn_count = 0
            cover_time = 0
            isbn_time = 0
            auth_start = time.time()
            # these are reject reasons we might want to override, so optionally add to database as "ignored"
            ignorable = ['future', 'date', 'isbn', 'set', 'word', 'publisher']
            if CONFIG.get_bool('NO_LANG'):
                ignorable.append('lang')

            if resultxml is None:
                self.logger.warning(f'[{authorname}] No books found for author with ID: {gr_id}')
            else:
                self.logger.debug(f"[{authorname}] Now processing books with GoodReads API")
                author_name_result = rootxml.find('./author/name').text
                # Goodreads sometimes puts extra whitespace in the author names!
                author_name_result = ' '.join(author_name_result.split())
                self.logger.debug(f"GoodReads author name [{author_name_result}]")
                loop_count = 1
                threadname = thread_name()
                while resultxml:
                    if lazylibrarian.STOPTHREADS and threadname == "AUTHORUPDATE":
                        self.logger.debug(f"Aborting {threadname}")
                        break
                    contents = {}
                    for item in rootxml.iter('books'):
                        contents = item.attrib
                    for book in resultxml:
                        if lazylibrarian.STOPTHREADS and threadname == "AUTHORUPDATE":
                            self.logger.debug(f"Aborting {threadname}")
                            break
                        total_count += 1
                        rejected = []
                        book_language = "Unknown"
                        find_field = "id"
                        bookisbn = ""
                        isbnhead = ""
                        originalpubdate = ""
                        bookgenre = ''
                        contributors = []
                        bookdict = self.get_bookdict(book)
                        shortname = bookdict['shortname']
                        bookname = bookdict['name']
                        bookid = bookdict['id']
                        bookdesc = bookdict['desc']
                        bookpub = bookdict['pub']
                        booklink = bookdict['link']
                        bookrate = bookdict['rate']
                        bookpages = bookdict['pages']
                        bookimg = bookdict['img']
                        workid = bookdict['workid']
                        isbn13 = bookdict['isbn13']
                        isbn10 = bookdict['isbn10']
                        bookdate = bookdict['pub_year']
                        if check_year(bookdate, past=1800, future=0):
                            mn = check_int(bookdict['pub_month'], 0)
                            dy = check_int(bookdict['pub_day'], 0)
                            if mn and dy:
                                bookdate = "%s-%02d-%02d" % (bookdate, mn, dy)

                        if not bookname:
                            self.logger.debug(f'Rejecting bookid {bookid} for {author_name_result}, no bookname')
                            rejected.append(['name', 'No bookname'])

                        if bookpub:
                            if bookpub.lower() in get_list(CONFIG['REJECT_PUBLISHER']):
                                self.logger.warning(f"Ignoring {bookname}: Publisher {bookpub}")
                                rejected.append(['publisher', bookpub])

                        if not bookimg or 'nocover' in bookimg or 'nophoto' in bookimg:
                            bookimg = 'images/nocover.png'

                        if book_language == "Unknown":
                            book_language = ""
                            if isbn13:
                                find_field = 'isbn13'
                                book_language, cache_hit, thing_hit = isbnlang(isbn13)
                                if thing_hit:
                                    lt_lang_hits += 1
                            if not book_language and isbn10:
                                find_field = 'isbn'
                                book_language, cache_hit, thing_hit = isbnlang(isbn10)
                                if thing_hit:
                                    lt_lang_hits += 1

                        if not book_language or book_language == "Unknown" or not bookdate or bookdate == '0000':
                            # still  no earlier match, we'll have to search the goodreads api
                            try:
                                if book.find(find_field).text:
                                    book_url = '/'.join([CONFIG['GR_URL'],
                                                         f"book/show?id={book.find(find_field).text}"
                                                         f"&{urlencode(self.params)}"])
                                    self.logger.debug(f"Book URL: {book_url}")
                                    book_language = ""
                                    try:
                                        book_rootxml, in_cache = gr_xml_request(book_url)
                                        if book_rootxml is None:
                                            self.logger.debug(f'Failed to get book page for {find_field} '
                                                              f'{book.find(find_field).text}')
                                        else:
                                            try:
                                                book_language = book_rootxml.find('./book/language_code').text
                                            except Exception as e:
                                                self.logger.error(
                                                    f"{type(e).__name__} finding language_code in book xml: "
                                                    f"{str(e)}")
                                            # noinspection PyBroadException
                                            try:
                                                res = book_rootxml.find('./book/isbn').text
                                                isbnhead = res[0:3]
                                            except Exception:
                                                # noinspection PyBroadException
                                                try:
                                                    res = book_rootxml.find('./book/isbn13').text
                                                    isbnhead = res[3:6]
                                                except Exception:
                                                    isbnhead = ''
                                            # if bookLanguage and not isbnhead:
                                            #     print(BOOK_URL)

                                            # might as well get the original publication date from here
                                            # noinspection PyBroadException
                                            try:
                                                bookdate = book_rootxml.find(
                                                    './book/work/original_publication_year').text
                                                if check_year(bookdate, past=1800, future=0):
                                                    try:
                                                        mn = check_int(book_rootxml.find(
                                                            './book/work/original_publication_month').text, 0)
                                                        dy = check_int(book_rootxml.find(
                                                            './book/work/original_publication_day').text, 0)
                                                        if mn and dy:
                                                            bookdate = "%s-%02d-%02d" % (bookdate, mn, dy)
                                                    except (KeyError, AttributeError):
                                                        self.logger.debug("No extended date info")
                                                        pass
                                            except Exception:
                                                pass

                                    except Exception as e:
                                        self.logger.error(f"{type(e).__name__} getting book xml: {str(e)}")

                                    if not in_cache:
                                        gr_lang_hits += 1
                                    if not book_language:
                                        book_language = "Unknown"
                                    elif isbnhead:
                                        # if GR didn't give an isbn we can't cache it
                                        # just use language for this book
                                        control_value_dict = {"isbn": isbnhead}
                                        new_value_dict = {"lang": book_language}
                                        db.upsert("languages", new_value_dict, control_value_dict)
                                        self.logger.debug(
                                            f"GoodReads reports language [{book_language}] for {isbnhead}")
                                    else:
                                        not_cached += 1

                                    self.logger.debug(f"GR language: {book_language}")
                                else:
                                    self.logger.debug(f"No {find_field} provided for [{bookname}]")
                                    # continue

                            except Exception as e:
                                self.logger.error(f"Goodreads language search failed: {type(e).__name__} {str(e)}")

                        if not isbnhead and CONFIG.get_bool('ISBN_LOOKUP'):
                            # try lookup by name
                            if bookname or shortname:
                                if shortname:
                                    name = replace_all(shortname, {':': ' ', '"': '', '\'': ''}).strip()
                                else:
                                    name = replace_all(bookname, {':': ' ', '"': '', '\'': ''}).strip()
                                try:
                                    isbn_count += 1
                                    start = time.time()
                                    res = isbn_from_words(
                                        f"{unaccented(name, only_ascii=False)} "
                                        f"{unaccented(author_name_result, only_ascii=False)}")
                                    isbn_time += (time.time() - start)
                                except Exception as e:
                                    res = None
                                    self.logger.warning(f"Error from isbn: {e}")
                                if res:
                                    self.logger.debug(f"isbn found {res} for {bookid}")
                                    bookisbn = res
                                    if len(res) == 13:
                                        isbnhead = res[3:6]
                                    else:
                                        isbnhead = res[0:3]

                        if not isbnhead and CONFIG.get_bool('NO_ISBN'):
                            rejected.append(['isbn', 'No ISBN'])

                        if not book_language:
                            book_language = 'Unknown'

                        if "All" not in valid_langs:  # do we care about language
                            if book_language not in valid_langs:
                                rejected.append(['lang', f'Invalid language [{book_language}]'])

                        if CONFIG.get_bool('NO_FUTURE'):
                            if bookdate and bookdate > today()[:len(bookdate)]:
                                rejected.append(['future', f'Future publication date [{bookdate}]'])

                        if CONFIG.get_bool('NO_PUBDATE'):
                            if not bookdate or bookdate == '0000':
                                rejected.append(['date', 'No publication date'])

                        dic = {'.': ' ', '-': ' ', '/': ' ', '+': ' ', '_': ' ', '(': '', ')': '',
                               '[': ' ', ']': ' ', '#': '# ', ':': ' ', ';': ' '}
                        name = replace_all(shortname, dic).strip()
                        if not name:
                            name = replace_all(bookname, dic).strip()
                        name = name.lower()
                        # remove extra spaces if they're in a row
                        name = " ".join(name.split())
                        namewords = name.split(' ')
                        badwords = get_list(CONFIG['REJECT_WORDS'], ',')
                        for word in badwords:
                            if (' ' in word and word in name) or word in namewords:
                                rejected.append(['word', f'Name contains [{word}]'])
                                break

                        name = unaccented(bookname, only_ascii=False)
                        if CONFIG.get_bool('NO_SETS'):
                            is_set, set_msg = is_set_or_part(name)
                            if is_set:
                                rejected.append(['set', set_msg])

                        oldbookname = bookname
                        bookname, booksub, bookseries = split_title(author_name_result, bookname)
                        if shortname:
                            sbookname, sbooksub, _ = split_title(author_name_result, shortname)
                            if sbookname != bookname:
                                self.logger.warning(f'Different titles [{oldbookname}][{sbookname}][{bookname}]')
                                bookname = sbookname
                            if sbooksub != booksub:
                                self.logger.warning(f'Different subtitles [{sbooksub}][{booksub}]')
                                booksub = sbooksub

                        if bookname and booksub:
                            bookname = f"{bookname} - {booksub}"
                            booksub = ''

                        dic = {':': '.', '"': ''}  # do we need to strip apostrophes , '\'': ''}
                        bookname = replace_all(bookname, dic).strip()
                        booksub = replace_all(booksub, dic).strip()
                        bookseries = replace_all(bookseries, dic).strip()
                        if bookseries:
                            series, series_num = book_series(bookseries)
                        elif booksub:
                            series, series_num = book_series(booksub)
                        else:
                            series, series_num = book_series(bookname)

                        # 1. The author/list page only contains one author per book even if the book/show page
                        #    and html show multiple authors
                        # 2. The author/list page doesn't always include the publication date even if the
                        #    book/show page and html include it
                        # 3. The author/list page gives the publication date of the "best book" edition
                        #    and does not include the original publication date, though the book/show page
                        #    and html often show it
                        # We can't call book/show for every book because of api limits, and we can't scrape
                        # the html as it breaks goodreads terms of service
                        authors = book.find('authors')
                        anames = authors.iter('author')
                        amatch = False
                        alist = ''
                        role = ''
                        for aname in anames:
                            aid = aname.find('id').text
                            anm = aname.find('name').text
                            role = aname.find('role').text
                            contributors.append([aid, anm, role])
                            if alist:
                                alist += ', '
                            alist += anm
                            if aid == gr_id or anm == author_name_result:
                                if aid != gr_id:
                                    self.logger.warning(f"Author {anm} has different authorid {aid}:{gr_id}")
                                if role is None or 'author' in role.lower() or \
                                        'writer' in role.lower() or \
                                        'creator' in role.lower() or \
                                        'pseudonym' in role.lower() or \
                                        'pen name' in role.lower():
                                    amatch = True
                                else:
                                    self.logger.debug(f'Got {anm} for {bookname}, role is {role}')
                        if not amatch:
                            rejected.append(['author', f'Wrong Author or role (got {alist},{role})'])

                        cmd = ("SELECT AuthorName,BookName,AudioStatus,books.Status,ScanResult FROM books,authors "
                               "WHERE authors.AuthorID = books.AuthorID AND BookID=?")
                        match = db.match(cmd, (bookid,))
                        not_rejectable = None
                        if match:
                            # we have a book with this bookid already
                            if author_name_result != match['AuthorName']:
                                rejected.append(['author', (f"Different author for this bookid [{author_name_result}]"
                                                            f"[{match['AuthorName']}]")])
                            elif bookname != match['BookName']:
                                # same bookid and author, assume goodreads fixed the title, use the new title
                                db.action("UPDATE books SET BookName=? WHERE BookID=?", (bookname, bookid))
                                self.logger.warning(f"Updated bookname [{match['BookName']}] to [{bookname}]")

                            msg = (f"Bookid {bookid} for [{author_name_result}][{bookname}] is in database marked "
                                   f"{match['Status']}")
                            if CONFIG.get_bool('AUDIO_TAB'):
                                msg += f",{match['AudioStatus']}"
                            msg += f" {match['ScanResult']}"
                            self.logger.debug(msg)

                            # Make sure we don't reject books we have already got or want
                            if match['Status'] not in ['Ignored', 'Skipped']:
                                not_rejectable = f"Status: {match['Status']}"
                            elif match['AudioStatus'] not in ['Ignored', 'Skipped']:
                                not_rejectable = f"AudioStatus: {match['AudioStatus']}"

                        if not match:
                            cmd = ("SELECT BookID,books.gr_id FROM books,authors WHERE "
                                   "books.AuthorID = authors.AuthorID and "
                                   "BookName=? COLLATE NOCASE and BookSub=? COLLATE NOCASE and AuthorName=? "
                                   "COLLATE NOCASE and books.Status != 'Ignored' and AudioStatus != 'Ignored'")
                            match = db.match(cmd, (bookname, booksub, author_name_result))

                            if not match:
                                in_db = lazylibrarian.librarysync.find_book_in_db(author_name_result, bookname,
                                                                                  source='gr_id',
                                                                                  ignored=False, library='eBook',
                                                                                  reason='gr_get_author_books')
                                if in_db and in_db[0]:
                                    cmd = ("SELECT AuthorName,BookName,BookID,AudioStatus,books.Status,"
                                           "ScanResult,books.gr_id FROM books,authors WHERE "
                                           "authors.AuthorID = books.AuthorID AND BookID=?")
                                    match = db.match(cmd, (in_db[0],))
                            if match:
                                if match['BookID'] != bookid:
                                    # we have a different bookid for this author/title already
                                    # Check series numbers before rejecting as duplicate
                                    should_match, confidence = validate_series_match(bookname, match['BookName'], None)
                                    if not should_match:
                                        self.logger.debug(f"Different series numbers - allowing both {bookname} and {match['BookName']}")
                                    elif not_rejectable:
                                        self.logger.debug(
                                            f"Not rejecting duplicate title {bookname} ({bookid}/{match['BookID']}) "
                                            f"as {not_rejectable}")
                                    else:
                                        duplicates += 1
                                        if not match['gr_id']:
                                            cmd = "UPDATE books SET gr_id=? WHERE BookID=?"
                                            db.action(cmd, (bookid, match['BookID']))
                                        rejected.append(['bookid', f"Duplicate title {bookname} "
                                                                   f"({bookid}/{match['BookID']})"])
                        fatal = False
                        reason = ''
                        ignore_book = False
                        ignore_audio = False
                        if rejected:
                            for reject in rejected:
                                if reject[0] not in ignorable:
                                    if reject[0] == 'lang':
                                        bad_lang += 1
                                    if reject[0] == 'dupe':
                                        duplicates += 1
                                    if reject[0] == 'name':
                                        removed_results += 1
                                    fatal = True
                                    reason = reject[1]
                                    break

                            if not CONFIG['IMP_IGNORE']:
                                reason = str(rejected)
                                fatal = True

                            if not fatal:
                                for reject in rejected:
                                    if reject[0] in ignorable:
                                        ignore_book = True
                                        ignore_audio = True
                                        book_ignore_count += 1
                                        reason = f"Ignored: {reject[1]}"
                                        break
                        elif 'author_update' in entryreason:
                            reason += f" Author: {author_name_result}"
                        else:
                            reason = entryreason

                        if fatal:
                            self.logger.debug(f"Rejected {bookid}:{reason}:{rejected}")
                        else:
                            cmd = ("SELECT Status,AudioStatus,BookFile,AudioFile,Manual,BookAdded,BookName,"
                                   "OriginalPubDate,BookDesc,BookGenre,ScanResult FROM books WHERE BookID=?")
                            existing = db.match(cmd, (bookid,))
                            if existing:
                                book_status = existing['Status']
                                audio_status = existing['AudioStatus']
                                bookdesc = existing['BookDesc']
                                bookgenre = existing['BookGenre']
                                if CONFIG['FOUND_STATUS'] == 'Open':
                                    if book_status == 'Have' and existing['BookFile']:
                                        book_status = 'Open'
                                    if audio_status == 'Have' and existing['AudioFile']:
                                        audio_status = 'Open'
                                locked = existing['Manual']
                                added = existing['BookAdded']
                                if locked is None:
                                    locked = False
                                elif locked.isdigit():
                                    locked = bool(int(locked))
                                if not originalpubdate:
                                    originalpubdate = existing['OriginalPubDate']
                            else:
                                # new_book status, or new_author status or ignored
                                book_status = 'Ignored' if ignore_book else bookstatus
                                audio_status = 'Ignored' if ignore_audio else audiostatus
                                added = today()
                                locked = False

                            if not originalpubdate or len(originalpubdate) < 5:
                                # already set with language code or existing book?
                                newdate, in_cache = get_book_pubdate(bookid)
                                if not originalpubdate:
                                    originalpubdate = newdate
                                elif originalpubdate < newdate:  # more detailed date
                                    originalpubdate = newdate
                                    self.logger.debug(f"Extended date info found: {newdate}")
                                if not in_cache:
                                    api_hits += 1

                            if originalpubdate:
                                bookdate = originalpubdate

                            if (not bookdate or bookdate == '0000') and booklink:
                                result, in_cache = html_request(booklink)
                                try:
                                    pubdate = result.split(b"publicationInfo")[1].split(b"ublished ")[1].split(b"<")[0]
                                    bookdate = date_format(pubdate.decode('utf-8'))
                                except IndexError:
                                    pass

                            # Leave alone if locked
                            if locked:
                                locked_count += 1
                            else:
                                if not bookgenre:
                                    genres, _ = get_gr_genres(bookid)
                                    if genres:
                                        bookgenre = ', '.join(genres)
                                infodict = get_gb_info(isbn=bookisbn, author=author_name_result,
                                                       title=bookname, expire=False)
                                if infodict:  # None if api blocked
                                    gbupdate = []
                                    if not bookdesc and infodict['desc']:
                                        bookdesc = infodict['desc']
                                        gbupdate.append('Description')
                                    if not bookdate or bookdate == '0000' or len(infodict['date']) > len(bookdate):
                                        bookdate = infodict['date']
                                        gbupdate.append('Publication Date')
                                    if infodict['rate'] and not bookrate:
                                        bookrate = infodict['rate']
                                        gbupdate.append('Rating')
                                    if infodict['pub'] and not bookpub:
                                        bookpub = infodict['pub']
                                        gbupdate.append('Publisher')
                                    if infodict['pages'] and not bookpages:
                                        bookpages = infodict['pages']
                                        gbupdate.append('Pages')
                                    if not bookgenre and infodict['genre']:
                                        bookgenre = genre_filter(infodict['genre'])
                                        gbupdate.append('Genres')
                                    if gbupdate:
                                        self.logger.debug(f"Updated {', '.join(gbupdate)} from googlebooks")

                                threadname = thread_name()
                                reason = f"[{threadname}] {reason}"
                                control_value_dict = {"BookID": bookid}
                                new_value_dict = {
                                    "AuthorID": authorid,
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
                                    "BookLang": book_language,
                                    "Status": book_status,
                                    "AudioStatus": audio_status,
                                    "BookAdded": added,
                                    "WorkID": workid,
                                    "gr_id": bookid,
                                    "ScanResult": reason,
                                    "OriginalPubDate": originalpubdate
                                }
                                db.upsert("books", new_value_dict, control_value_dict)
                                db.action('INSERT into bookauthors (AuthorID, BookID, Role) VALUES (?, ?, ?)',
                                          (authorid, bookid, ROLE['PRIMARY']), suppress='UNIQUE')

                                set_genres(get_list(bookgenre, ','), bookid)

                                update_value_dict = {}
                                # need to run get_work_series AFTER adding to book table (foreign key constraint)
                                serieslist = []
                                if series:
                                    serieslist = [('', series_num, clean_name(series, '&/'))]
                                if CONFIG.get_bool('ADD_SERIES') and "Ignored:" not in reason:
                                    newserieslist = get_work_series(workid, 'GR', reason=reason)
                                    if newserieslist:
                                        serieslist = newserieslist
                                        self.logger.debug(f'Updated series: {bookid} {serieslist}')
                                    _api_hits, pubdate = set_series(serieslist, bookid, reason=reason)
                                    api_hits += _api_hits
                                    if pubdate and pubdate > originalpubdate:  # more detailed
                                        update_value_dict["OriginalPubDate"] = pubdate

                                if not fatal:
                                    if existing and existing['ScanResult'] and \
                                            ' publication date' in existing['ScanResult'] and \
                                            bookdate and bookdate != '0000' and \
                                            bookdate <= today()[:len(bookdate)]:
                                        # was rejected on previous scan but bookdate has become valid
                                        self.logger.debug(
                                            f"valid bookdate [{bookdate}] previous scanresult "
                                            f"[{existing['ScanResult']}]")
                                        update_value_dict["ScanResult"] = f"bookdate {bookdate} is now valid"
                                        self.searchinglogger.debug(
                                            f"entry status {entrystatus} {bookstatus},{audiostatus}")
                                        book_stat, audio_stat = get_status(bookid, serieslist, bookstatus,
                                                                           audiostatus, entrystatus)
                                        if existing['Status'] not in ['Wanted', 'Open', 'Have'] and not ignore_book:
                                            update_value_dict["Status"] = book_stat
                                        if (existing['AudioStatus'] not in ['Wanted', 'Open', 'Have'] and not
                                                ignore_audio):
                                            update_value_dict["AudioStatus"] = audio_stat
                                        self.searchinglogger.debug(f"status is now {book_status},{audio_status}")
                                    elif not existing:
                                        update_value_dict["ScanResult"] = reason

                                    if 'nocover' in bookimg or 'nophoto' in bookimg:
                                        # try to get a cover from another source
                                        start = time.time()
                                        link, source = get_book_cover(bookid, ignore='goodreads')
                                        if source != 'cache':
                                            cover_count += 1
                                            cover_time += (time.time() - start)
                                        if link:
                                            update_value_dict["BookImg"] = link
                                    elif bookimg and bookimg.startswith('http'):
                                        link = cache_bookimg(bookimg, bookid, 'gr')
                                        update_value_dict["BookImg"] = link

                                if update_value_dict:
                                    db.upsert("books", update_value_dict, control_value_dict)

                                if CONFIG.get_bool('CONTRIBUTING_AUTHORS'):
                                    for contributor in contributors:
                                        aid, anm, role = contributor
                                        if aid != gr_id:  # skip primary author
                                            if not role:
                                                role = 'UNKNOWN'
                                            else:
                                                role = role.upper()
                                            if role not in ROLE:
                                                role = 'CONTRIBUTING'
                                            reason = f"Contributor to {bookname}"
                                            auth_id = lazylibrarian.importer.add_author_to_db(authorname=anm,
                                                                                              refresh=False,
                                                                                              authorid=aid,
                                                                                              addbooks=False,
                                                                                              reason=reason)
                                            if auth_id:
                                                db.action('INSERT into bookauthors (AuthorID, BookID, Role) '
                                                          'VALUES (?, ?, ?)',
                                                          (auth_id, bookid, ROLE[role]), suppress='UNIQUE')
                                                lazylibrarian.importer.update_totals(auth_id)
                                            else:
                                                self.logger.debug(f"Unable to add {auth_id}")

                                if not existing:
                                    typ = 'Added'
                                    added_count += 1
                                else:
                                    typ = 'Updated'
                                    updated_count += 1
                                msg = f"[{authorname}] {typ} book: {bookname} [{book_language}] status {book_status}"
                                if CONFIG.get_bool('AUDIO_TAB'):
                                    msg += f" audio {audio_status}"
                                self.logger.debug(msg)
                    loop_count += 1
                    if 0 < CONFIG.get_int('MAX_BOOKPAGES') < loop_count:
                        resultxml = None
                    elif contents.get('end') == contents.get('total'):
                        # this was last page of results
                        resultxml = None
                    else:
                        url = '/'.join([CONFIG['GR_URL'],
                                        f"author/list/{gr_id}.xml?{urlencode(self.params)}&page={str(loop_count)}"])
                        resultxml = None
                        try:
                            self.searchinglogger.debug(url)
                            rootxml, in_cache = gr_xml_request(url, use_cache=not refresh)
                            if rootxml is None:
                                self.logger.debug('Failed to get next page of results')
                            else:
                                resultxml = rootxml.iter('book')
                                if not in_cache:
                                    api_hits += 1
                        except Exception as e:
                            resultxml = None
                            self.logger.error(f"{type(e).__name__} finding next page of results: {str(e)}")

                    if resultxml:
                        if all(False for _ in resultxml):  # returns True if iterator is empty
                            resultxml = None

            self.verify_ids(authorid)
            delete_empty_series()
            lazylibrarian.importer.update_totals(authorid)
            cmd = ("SELECT BookName, BookLink, BookDate, BookImg, BookID from books WHERE AuthorID=? AND "
                   "Status != 'Ignored' order by BookDate DESC")
            lastbook = db.match(cmd, (authorid,))
            if lastbook:
                lastbookname = lastbook['BookName']
                lastbooklink = lastbook['BookLink']
                lastbookdate = lastbook['BookDate']
                lastbookid = lastbook['BookID']
                lastbookimg = lastbook['BookImg']
            else:
                lastbookname = ""
                lastbooklink = ""
                lastbookdate = ""
                lastbookid = ""
                lastbookimg = ""

            control_value_dict = {"AuthorID": authorid}
            new_value_dict = {
                "Status": entrystatus,
                "LastBook": lastbookname,
                "LastLink": lastbooklink,
                "LastDate": lastbookdate,
                "LastBookID": lastbookid,
                "LastBookImg": lastbookimg
            }
            db.upsert("authors", new_value_dict, control_value_dict)

            resultcount = added_count + updated_count
            loop_count -= 1
            self.logger.debug(
                f"Found {total_count} {plural(total_count, 'result')} in {loop_count} {plural(loop_count, 'page')}")
            self.logger.debug(f"Found {locked_count} locked {plural(locked_count, 'book')}")
            self.logger.debug(f"Removed {bad_lang} unwanted language {plural(bad_lang, 'result')}")
            self.logger.debug(f"Removed {removed_results} incorrect/incomplete {plural(removed_results, 'result')}")
            self.logger.debug(f"Removed {duplicates} duplicate {plural(duplicates, 'result')}")
            self.logger.debug(f"Ignored {book_ignore_count} {plural(book_ignore_count, 'book')}")
            self.logger.debug(
                f"Imported/Updated {resultcount} {plural(resultcount, 'book')} in "
                f"{int(time.time() - auth_start)} secs using {api_hits} api {plural(api_hits, 'hit')}")
            if cover_count:
                self.logger.debug(f"Fetched {cover_count} {plural(cover_count, 'cover')} in {cover_time:.2f} sec")
            if isbn_count:
                self.logger.debug(f"Fetched {isbn_count} ISBN in {isbn_time:.2f} sec")

            control_value_dict = {"authorname": authorname.replace('"', '""')}
            new_value_dict = {
                "GR_book_hits": api_hits,
                "GR_lang_hits": gr_lang_hits,
                "LT_lang_hits": lt_lang_hits,
                "GB_lang_change": gb_lang_change,
                "cache_hits": cache_hits,
                "bad_lang": bad_lang,
                "bad_char": removed_results,
                "uncached": not_cached,
                "duplicates": duplicates
            }
            db.upsert("stats", new_value_dict, control_value_dict)

            if refresh:
                self.logger.info(
                    f"[{authorname}] Book processing complete: Added {added_count} "
                    f"{plural(added_count, 'book')} / Updated {updated_count} {plural(updated_count, 'book')}")
            else:
                self.logger.info(
                    f"[{authorname}] Book processing complete: Added {added_count} "
                    f"{plural(added_count, 'book')} to the database")

        except Exception:
            self.logger.error(f'Unhandled exception in GR.get_author_books: {traceback.format_exc()}')
        finally:
            db.close()

    def verify_ids(self, authorid):
        """ GoodReads occasionally consolidates bookids/workids and renumbers so check if changed... """
        db = database.DBConnection()
        try:
            cmd = "select BookID,gr_id,BookName from books WHERE AuthorID=? and gr_id is not NULL"
            books = db.select(cmd, (authorid,))
            counter = 0
            self.logger.debug(f"Checking BookID/WorkID for {len(books)} {plural(len(books), 'book')}")
            page = ''
            pages = []
            for book in books:
                bookid = book['gr_id']
                if not bookid:
                    self.logger.warning(f"No gr_id for {book['BookName']}")
                else:
                    if page:
                        page += ','
                    page += bookid
                    counter += 1
                    if counter == 50:
                        counter = 0
                        pages.append(page)
                        page = ''
            if page:
                pages.append(page)

            found = 0
            differ = 0
            notfound = []
            pagecount = 0
            for page in pages:
                pagecount += 1
                url = '/'.join([CONFIG['GR_URL'], f"book/id_to_work_id/{page}?{urlencode(self.params)}"])
                try:
                    self.searchinglogger.debug(url)
                    rootxml, _ = gr_xml_request(url, use_cache=False)
                    if rootxml is None:
                        self.logger.debug(f"Failed to get id_to_work_id page {page}")
                    else:
                        resultxml = rootxml.find('work-ids')
                        if len(resultxml):
                            ids = resultxml.iter('item')
                            books = get_list(page)
                            cnt = 0
                            for item in ids:
                                workid = item.text
                                if not workid:
                                    notfound.append(books[cnt])
                                    self.logger.debug(f"No workid returned for {books[cnt]}")
                                else:
                                    found += 1
                                    res = db.match("SELECT WorkID from books WHERE bookid=?", (books[cnt],))
                                    if res:
                                        if res['WorkID'] != workid:
                                            differ += 1
                                            self.logger.debug(
                                                f"Updating workid for {books[cnt]} from [{res['WorkID']}] "
                                                f"to [{workid}]")
                                            control_value_dict = {"gr_id": books[cnt]}
                                            new_value_dict = {"WorkID": workid}
                                            db.upsert("books", new_value_dict, control_value_dict)
                                cnt += 1

                except Exception as e:
                    self.logger.error(f"{type(e).__name__} parsing id_to_work_id page: {str(e)}")
            self.logger.debug(f"BookID/WorkID Found {found}, Differ {differ}, Missing {len(notfound)}")

            cnt = 0
            for bookid in notfound:
                res = db.match("SELECT BookName,Status,AudioStatus from books WHERE gr_id=?", (bookid,))
                if res:
                    if CONFIG.get_bool('FULL_SCAN'):
                        if res['Status'] in ['Wanted', 'Open', 'Have']:
                            self.logger.warning(
                                f"Keeping unknown goodreads bookid {bookid}: {res['BookName']}, "
                                f"Status is {res['Status']}")
                        elif res['AudioStatus'] in ['Wanted', 'Open', 'Have']:
                            self.logger.warning(
                                f"Keeping unknown goodreads bookid {bookid}: {res['BookName']}, "
                                f"AudioStatus is {res['Status']}")
                        else:
                            self.logger.debug(f"Deleting unknown goodreads bookid {bookid}: {res['BookName']}")
                            db.action("DELETE from books WHERE gr_id=?", (bookid,))
                            cnt += 1
                    else:
                        self.logger.warning(f"Unknown goodreads bookid {bookid}: {res['BookName']}")
            if cnt:
                self.logger.warning(f"Deleted {cnt} {plural(cnt, 'entry')} with unknown goodreads bookid")
        finally:
            db.close()

    def add_bookid_to_db(self, bookid=None, bookstatus=None, audiostatus=None, reason='gr.add_bookid'):
        url = '/'.join([CONFIG['GR_URL'], f"book/show/{bookid}?{urlencode(self.params)}"])
        try:
            self.searchinglogger.debug(url)
            rootxml, _ = gr_xml_request(url)
            if rootxml is None:
                self.logger.debug(f"Failed to get book info for {bookid}")
                return
        except Exception as e:
            self.logger.error(f"{type(e).__name__} finding book: {str(e)}")
            return

        threadname = thread_name()
        if not bookstatus:
            bookstatus = CONFIG['NEWBOOK_STATUS']
            self.logger.debug(f"No bookstatus passed, using default {bookstatus}")
        if not audiostatus:
            audiostatus = CONFIG['NEWAUDIO_STATUS']
            self.logger.debug(f"No audiostatus passed, using default {audiostatus}")
        self.logger.debug(f"bookstatus={bookstatus}, audiostatus={audiostatus}")
        book_language = rootxml.find('./book/language_code').text
        bookname = rootxml.find('./book/title').text

        if not book_language:
            book_language = "Unknown"
        #
        # user has said they want this book, don't block for unwanted language etc.
        # Ignore book if adding as part of a series, else just warn and include it
        #
        valid_langs = get_list(CONFIG['IMP_PREFLANG'])
        if book_language not in valid_langs and 'All' not in valid_langs:
            msg = f'Book {bookname} Language [{book_language}] does not match preference'
            self.logger.warning(msg)
            if reason.startswith("Series:") or threadname.startswith('SERIES'):
                return

        if rootxml.find('./book/work/original_publication_year').text is None:
            originalpubdate = ''
            if rootxml.find('./book/publication_year').text is None:
                bookdate = "0000"
            else:
                bookdate = rootxml.find('./book/publication_year').text
                if check_year(bookdate, past=1800, future=0):
                    try:
                        mn = check_int(rootxml.find('./book/publication_month').text, 0)
                        dy = check_int(rootxml.find('./book/publication_day').text, 0)
                        if mn and dy:
                            bookdate = "%s-%02d-%02d" % (bookdate, mn, dy)
                    except (KeyError, AttributeError):
                        pass
        else:
            originalpubdate = rootxml.find('./book/work/original_publication_year').text
            if check_year(originalpubdate, past=1800, future=0):
                try:
                    mn = check_int(rootxml.find('./book/work/original_publication_month').text, 0)
                    dy = check_int(rootxml.find('./book/work/original_publication_day').text, 0)
                    if mn and dy:
                        originalpubdate = "%s-%02d-%02d" % (originalpubdate, mn, dy)
                except (KeyError, AttributeError):
                    pass
            bookdate = originalpubdate

        if CONFIG.get_bool('NO_PUBDATE'):
            if not bookdate or bookdate == '0000':
                msg = f'Book {bookname} Publication date [{bookdate}] does not match preference'
                self.logger.warning(msg)
                if reason.startswith("Series:") or threadname.startswith('SERIES'):
                    return

        if CONFIG.get_bool('NO_FUTURE'):
            # may have yyyy or yyyy-mm-dd
            if bookdate > today()[:len(bookdate)]:
                msg = f'Book {bookname} Future publication date [{bookdate}] does not match preference'
                self.logger.warning(msg)
                if reason.startswith("Series:") or threadname.startswith('SERIES'):
                    return

        if CONFIG.get_bool('NO_SETS'):
            is_set, set_msg = is_set_or_part(bookname)
            if is_set:
                msg = f'Book {bookname} {set_msg}'
                self.logger.warning(msg)
                if reason.startswith("Series:") or threadname.startswith('SERIES'):
                    return
        try:
            bookimg = rootxml.find('./book/img_url').text
            if not bookimg or 'nocover' in bookimg or 'nophoto' in bookimg:
                bookimg = 'images/nocover.png'
        except (KeyError, AttributeError):
            bookimg = 'images/nocover.png'

        #  multiauth info
        # for each author in './book/authors'
        # get author/id author/name author/role
        contributors = []
        authors = rootxml.find('./book/authors')
        anames = authors.iter('author')
        for aname in anames:
            aid = aname.find('id').text
            anm = aname.find('name').text
            role = aname.find('role').text
            contributors.append([aid, anm, role])

        authorname = rootxml.find('./book/authors/author/name').text
        authorid = rootxml.find('./book/authors/author/id').text
        bookdesc = rootxml.find('./book/description').text
        bookisbn = rootxml.find('./book/isbn13').text
        if not bookisbn:
            bookisbn = rootxml.find('./book/isbn').text
        bookpub = rootxml.find('./book/publisher').text
        booklink = rootxml.find('./book/link').text
        bookrate = check_float(rootxml.find('./book/average_rating').text, 0)
        bookpages = rootxml.find('.book/num_pages').text
        workid = rootxml.find('.book/work/id').text

        db = database.DBConnection()
        try:
            match = db.match('SELECT AuthorName from authors WHERE AuthorID=?', (authorid,))
            if match:
                author = {'authorid': authorid, 'authorname': match['AuthorName']}
            else:
                match = db.match('SELECT AuthorID from authors WHERE AuthorName=?', (authorname,))
                if match:
                    self.logger.debug(f"{authorname}: Changing authorid from {authorid} to {match['AuthorID']}")
                    author = {'authorid': match['AuthorID'], 'authorname': authorname}
                else:
                    gr = GoodReads()
                    author = gr.find_author_id(authorname=authorname)
            if author:
                author_id = author['authorid']
                match = db.match('SELECT * from authors WHERE AuthorID=?', (author_id,))
                if not match:
                    # no author but request to add book, add author with newauthor status
                    # User hit "add book" button from a search, or a wishlist import, or api call
                    newauthor_status = 'Active'
                    if CONFIG['NEWAUTHOR_STATUS'] in ['Skipped', 'Ignored']:
                        newauthor_status = 'Paused'
                    # also pause author if adding as a series contributor/wishlist/grsync
                    if (reason.startswith("Series:") or "grsync" in reason or "wishlist" in reason
                            or threadname.startswith('SERIES')):
                        newauthor_status = 'Paused'
                    control_value_dict = {"AuthorID": author_id}
                    new_value_dict = {
                        "AuthorName": author['authorname'],
                        "AuthorImg": author['authorimg'],
                        "AuthorLink": author['authorlink'],
                        "AuthorBorn": author['authorborn'],
                        "AuthorDeath": author['authordeath'],
                        "DateAdded": today(),
                        "Updated": int(time.time()),
                        "Status": newauthor_status,
                        "Reason": reason
                    }
                    self.logger.debug(f"Adding author {author_id} {author['authorname']}, {newauthor_status}")
                    db.upsert("authors", new_value_dict, control_value_dict)
                    db.commit()  # shouldn't really be necessary as context manager commits?
                    authorname = author['authorname']
                    if CONFIG.get_bool('NEWAUTHOR_BOOKS') and newauthor_status != 'Paused':
                        self.get_author_books(author_id, entrystatus=CONFIG['NEWAUTHOR_STATUS'],
                                              reason=reason)
            else:
                self.logger.warning(f"No AuthorID for {authorname}, unable to add book {bookname}")
                return

            # bookname = unaccented(bookname, only_ascii=False)
            bookname, booksub, bookseries = split_title(authorname, bookname)
            dic = {':': '.', '"': ''}
            bookname = replace_all(bookname, dic).strip()
            booksub = replace_all(booksub, dic).strip()
            if bookseries:
                series, series_num = book_series(bookseries)
            elif booksub:
                series, series_num = book_series(booksub)
            else:
                series, series_num = book_series(bookname)

            if not bookisbn:
                try:
                    res = isbn_from_words(f"{bookname} {unaccented(authorname, only_ascii=False)}")
                except Exception as e:
                    res = None
                    self.logger.warning(f"Failed to get isbn: {e}")
                if res:
                    self.logger.debug(f"isbn found {res} for {bookname}")
                    bookisbn = res

            bookgenre = ''
            genres, _ = get_gr_genres(bookid)
            if genres:
                bookgenre = ', '.join(genres)
            if not bookdesc:
                infodict = get_gb_info(isbn=bookisbn, author=authorname, title=bookname, expire=False)
                if infodict is not None:  # None if api blocked
                    if infodict and infodict['desc']:
                        bookdesc = infodict['desc']
                    else:
                        bookdesc = 'No Description'
                    if not bookgenre:
                        if infodict and infodict['genre']:
                            bookgenre = genre_filter(infodict['genre'])
                        else:
                            bookgenre = 'Unknown'

            threadname = thread_name()
            reason = f"[{threadname}] {reason}"
            match = db.match("SELECT * from authors where AuthorID=?", (author_id,))
            if not match:
                self.logger.warning(f"Authorid {author_id} not found in database, unable to add {bookname}")
            else:
                control_value_dict = {"BookID": bookid}
                new_value_dict = {
                    "AuthorID": author_id,
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
                    "BookLang": book_language,
                    "Status": bookstatus,
                    "AudioStatus": audiostatus,
                    "BookAdded": today(),
                    "WorkID": workid,
                    "gr_id": bookid,
                    "ScanResult": reason,
                    "OriginalPubDate": originalpubdate
                }

                if 'nocover' in bookimg or 'nophoto' in bookimg:
                    # try to get a cover from another source
                    link, _ = get_book_cover(bookid, ignore='goodreads')
                    if link:
                        new_value_dict["BookImg"] = link
                elif bookimg and bookimg.startswith('http'):
                    new_value_dict["BookImg"] = cache_bookimg(bookimg, bookid, 'gr')

                db.upsert("books", new_value_dict, control_value_dict)
                self.logger.info(f"{bookname} by {authorname} added to the books database, {bookstatus}/{audiostatus}")
                serieslist = []
                if series:
                    serieslist = [('', series_num, clean_name(series, '&/'))]
                if CONFIG.get_bool('ADD_SERIES') and "Ignored:" not in reason:
                    newserieslist = get_work_series(workid, 'GR', reason=reason)
                    if newserieslist:
                        serieslist = newserieslist
                        self.logger.debug(f'Updated series: {bookid} [{serieslist}]')
                    set_series(serieslist, bookid, reason=reason)

                set_genres(get_list(bookgenre, ','), bookid)

                db.action('INSERT into bookauthors (AuthorID, BookID, Role) VALUES (?, ?, ?)',
                          (author_id, bookid, ROLE['PRIMARY']), suppress='UNIQUE')
                lazylibrarian.importer.update_totals(author_id)

                if CONFIG.get_bool('CONTRIBUTING_AUTHORS'):
                    contributors.pop(0)  # skip primary author
                    for entry in contributors:
                        auth_id = lazylibrarian.importer.add_author_to_db(authorname=entry[1], refresh=False,
                                                                          authorid=entry[0], addbooks=False,
                                                                          reason=f"Contributor to {bookname}")
                        if auth_id:
                            if entry[2] and entry[2].upper() in ROLE:
                                role = ROLE[entry[2].upper()]
                            else:
                                role = ROLE['CONTRIBUTING']
                            db.action('INSERT into bookauthors (AuthorID, BookID, Role) VALUES (?, ?, ?)',
                                      (auth_id, bookid, role), suppress='UNIQUE')
                            lazylibrarian.importer.update_totals(auth_id)
                        else:
                            self.logger.debug(f"Unable to add {auth_id}")

        finally:
            db.close()
