#  This file is part of Lazylibrarian.
#  Lazylibrarian is free software : you can redistribute it and/or modify
#  it under the terms of the GNU General Public License as published by
#  the Free Software Foundation, either version 3 of the License, or
#  (at your option) any later version.
#  Lazylibrarian is distributed in the hope that it will be useful,
#  but WITHOUT ANY WARRANTY; without even the implied warranty of
#  MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
#  GNU General Public License for more details.
#  You should have received a copy of the GNU General Public License
#  along with Lazylibrarian.  If not, see <http://www.gnu.org/licenses/>.

# Purpose:
#   Look up book metadata or information, find it in the DB or add from dir

import logging
import os
import re
import shutil
import threading
import traceback
import zipfile
from xml.etree import ElementTree

from rapidfuzz import fuzz

import lazylibrarian
from lazylibrarian import database, ROLE
from lazylibrarian.bookrename import book_rename, audio_rename, id3read, delete_empty_folders
from lazylibrarian.cache import cache_img, ImageType
from lazylibrarian.config2 import CONFIG
from lazylibrarian.filesystem import (DIRS, path_exists, path_isdir, path_isfile, listdir, walk, any_file,
                                      opf_file, get_directory, book_file)
from lazylibrarian.formatter import (plural, is_valid_isbn, get_list, unaccented, replace_all, strip_quotes,
                                     split_title, now, make_unicode, split_author_names)
from lazylibrarian.common import extract_series_number, validate_series_match
from lazylibrarian.images import img_id
from lazylibrarian.importer import (update_totals, add_author_name_to_db, search_for, collate_nopunctuation,
                                    title_translates)
from lazylibrarian.preprocessor import preprocess_audio
from lib.mobi import Mobi


# noinspection PyBroadException
def get_book_meta(fdir, reason="get_book_meta"):
    # look for a bookid in a LL.() filename or a .desktop file and return author/title/bookid
    logger = logging.getLogger(__name__)
    libsynclogger = logging.getLogger('special.libsync')
    bookid = ''
    reason = f"{reason} [{fdir}]"
    libsynclogger.debug(reason)
    try:
        for item in listdir(fdir):
            libsynclogger.debug(f"Checking [{item}]")
            if 'LL.(' in item:
                bookid = item.split('LL.(')[1].split(')')[0]
                if bookid:
                    logger.debug(f"bookid {bookid} from {item}")
                    break
            if item.endswith('.desktop') or item.endswith('.url'):
                with open(os.path.join(fdir, item), 'r') as f:
                    try:
                        lynes = f.readlines()
                    except Exception as e:
                        logger.debug(f"Unable to readlines from {item}")
                        logger.debug(str(e))
                        lynes = []
                for lyne in lynes:
                    if '/book/show/' in lyne:
                        bookid = lyne.split('/book/show/')[1].split('-')[0].split('.')[0]
                        if bookid:
                            logger.debug(f"bookid {bookid} from {item}")
                            break
        if bookid:
            db = database.DBConnection()
            cmd = ("SELECT AuthorName,BookName FROM authors,books where authors.AuthorID = books.AuthorID and "
                   "books.BookID=?")
            existing_book = db.match(cmd, (bookid,))
            if not existing_book:
                logger.debug(f"Searching {CONFIG['BOOK_API']} for {bookid}")
                this_source = lazylibrarian.INFOSOURCES[CONFIG['BOOK_API']]
                api = this_source['api']
                api.add_bookid_to_db(bookid, None, None, reason)
                existing_book = db.match(cmd, (bookid,))
            db.close()
            if existing_book:
                logger.debug(f"Found {existing_book['AuthorName']}:{existing_book['BookName']} for {bookid}")
                return existing_book['AuthorName'], existing_book['BookName'], str(bookid)
        logger.debug(f"No match for {bookid} at {CONFIG['BOOK_API']}")
        return "", "", ""

    except Exception:
        logger.error(f'Error getting book meta: {traceback.format_exc()}')
        return "", "", ""


def get_book_info(fname):
    # only handles epub, mobi, azw3 and opf for now,
    # for pdf see notes below
    logger = logging.getLogger(__name__)
    fname = make_unicode(fname)
    res = {}
    extn = os.path.splitext(fname)[1]
    if not extn:
        return res

    res['type'] = extn[1:].lower()
    if res['type'] in ["mobi", "azw3"]:
        try:
            book = Mobi(fname)
            book.parse()
        except Exception as e:
            logger.error(f'Unable to parse mobi in {fname}, {type(e).__name__} {str(e)}')
            return res

        res['creator'] = make_unicode(book.author())
        res['title'] = make_unicode(book.title())
        res['language'] = make_unicode(book.language())
        res['isbn'] = make_unicode(book.isbn())
        return res

        # noinspection PyUnreachableCode
        """
                # none of the pdfs in my library had language,isbn
                # most didn't have author, or had the wrong author
                # (author set to publisher, or software used)
                # so probably not much point in looking at pdfs
                #
                from PyPDF2 import PdfFileReader
                if (extn == ".pdf"):
                    pdf = PdfFileReader(open(fname, "rb"))
                    txt = pdf.getDocumentInfo()
                    # repackage the data here to get components we need
                    res = {}
                    for s in ['title','language','creator']:
                        res[s] = txt[s]
                    res['identifier'] = txt['isbn']
                    res['type'] = "pdf"
                    return res
        """
    elif res['type'] == "epub":
        # prepare to read from the .epub file
        try:
            zipdata = zipfile.ZipFile(fname)
        except Exception as e:
            logger.error(f'Unable to parse epub file {fname}, {type(e).__name__} {str(e)}')
            return res

        # find the contents metafile
        txt = zipdata.read('META-INF/container.xml')
        try:
            tree = ElementTree.fromstring(txt)
        except Exception as e:
            logger.error(f"Error parsing metadata from epub zipfile: {type(e).__name__} {str(e)}")
            return res
        n = 0
        cfname = ""
        if not len(tree):
            return res

        while n < len(tree[0]):
            att = tree[0][n].attrib
            if 'full-path' in att:
                cfname = att['full-path']
                break
            n += 1

        # grab the metadata block from the contents metafile
        txt = zipdata.read(cfname)

    elif res['type'] == "opf":
        f = open(fname, 'rb')
        try:
            txt = f.read()
        finally:
            f.close()
        txt = make_unicode(txt)
        # sanitize any unmatched html tags or ElementTree won't parse
        dic = {'<br>': '', '</br>': ''}
        txt = replace_all(txt, dic)
    else:
        logger.error(f'Unhandled extension in get_book_info: {extn}')
        return res

    # repackage epub or opf metadata
    try:
        tree = ElementTree.fromstring(txt)
    except Exception as e:
        logger.error(f"Error parsing metadata from {fname}, {type(e).__name__} {str(e)}")
        return res

    if not len(tree):
        return res
    n = 0
    authors = []
    while n < len(tree[0]):
        tag = str(tree[0][n].tag).lower()
        if '}' in tag:
            tag = tag.split('}')[1]
            txt = tree[0][n].text
            attrib = tree[0][n].attrib
            txt = make_unicode(txt)
            if 'title' in tag:
                if not res.get('title') or attrib.get('id') == 'maintitle':
                    res['title'] = txt
            elif 'language' in tag:
                res['language'] = txt
            elif 'publisher' in tag:
                res['publisher'] = txt
            elif 'narrator' in tag:
                res['narrator'] = txt
            elif 'creator' in tag and txt:
                authors.append(txt)
            elif 'identifier' in tag:
                for k in attrib.keys():
                    if k.endswith('scheme'):  # can be "scheme" or "http://www.idpf.org/2007/opf:scheme"
                        if attrib[k] == 'ISBN' and is_valid_isbn(txt):
                            res['isbn'] = txt
                        elif attrib[k] == 'GOODREADS':
                            res['gr_id'] = txt
                        elif attrib[k] == 'OPENLIBRARY':
                            res['ol_id'] = txt
                        elif attrib[k] == 'HARDCOVER':
                            res['hc_id'] = txt
                        elif attrib[k] == 'GOOGLE':
                            res['gb_id'] = txt
                        elif attrib[k] == 'DNB':
                            res['dnb_id'] = txt
        n += 1
    if len(authors):
        res['creator'] = authors[0]
        res['authors'] = authors
    return res


def find_book_in_db(author, book, ignored=None, library='eBook', reason='find_book_in_db', source=''):
    # Fuzzy search for book in library, return LL bookid and status if found or zero
    # prefer an exact match on author & book
    # prefer 'Have' if the user has marked the one they want
    # or one already marked 'Open' so we match the same one as before
    # or prefer not ignored over ignored
    logger = logging.getLogger(__name__)
    fuzzlogger = logging.getLogger('special.fuzz')
    book = book.replace('\n', ' ')
    book = " ".join(book.split())
    author = " ".join(author.split())
    logger.debug(f'Searching database for [{book}] by [{author}] {source}')
    db = database.DBConnection()
    db.connection.create_collation('nopunctuation', collate_nopunctuation)
    new_author = False
    try:
        check_exist_author = db.match('SELECT AuthorID FROM authors where AuthorName=? COLLATE NOCASE', (author,))
        if check_exist_author:
            authorid = check_exist_author['AuthorID']
        else:
            newauthorname, authorid, new_author = add_author_name_to_db(author, False, reason=reason, title=book)
            if newauthorname and newauthorname != author:
                if new_author:
                    logger.debug(f"Authorname changed from [{author}] to [{newauthorname}]")
                else:
                    logger.debug(f"Authorname changed from [{author}] to existing [{newauthorname}]")
                author = make_unicode(newauthorname)
            if not newauthorname:
                authorid = 0

        if not authorid:
            logger.warning(f"Author [{author}] not recognised")
            return 0, ''

        cmd = ("SELECT BookID,books.Status,AudioStatus FROM books,authors where books.AuthorID = authors.AuthorID and "
               "authors.AuthorID=? and BookName=? COLLATE NOPUNCTUATION")
        if source:
            cmd += f' and books.{source} = BookID'
        res = db.select(cmd, (authorid, book))

        whichstatus = 'Status' if library == 'eBook' else 'AudioStatus'

        fuzzlogger.debug(f"Found {len(res)} exact match")
        for item in res:
            fuzzlogger.debug(f"{book} [{item[whichstatus]}]")

        match = None
        for item in res:
            if item[whichstatus] == 'Have':
                match = item
                break
        if not match:
            for item in res:
                if item[whichstatus] == 'Open':
                    match = item
                    break
        if not match:
            for item in res:
                if item[whichstatus] != 'Ignored':
                    match = item
                    break
        if not match:
            for item in res:
                if item[whichstatus] == 'Ignored':
                    match = item
                    break
        if match:
            logger.debug(f"Exact match [{book}] {match['BookID']}")
            return match['BookID'], match

        # Try a more complex fuzzy match against each book in the db by this author
        cmd = ("SELECT BookID,BookName,BookSub,BookISBN,books.Status,AudioStatus FROM books,authors where "
               "books.AuthorID = authors.AuthorID ")
        if source:
            cmd += f' and books.{source} = BookID '
        ign = ''
        if library == 'eBook':
            if ignored is True:
                cmd += "and books.Status = 'Ignored' "
                ign = 'ignored '
            elif ignored is False:
                cmd += "and books.Status != 'Ignored' "
        else:
            if ignored is True:
                cmd += "and AudioStatus = 'Ignored' "
                ign = 'ignored '
            elif ignored is False:
                cmd += "and AudioStatus != 'Ignored' "

        cmd += "and authors.AuthorID=?"
        books = db.select(cmd, (authorid,))

        if not len(books):
            logger.warning(f"No matching titles by {authorid}:{author} in database "
                           f"(source={source},library={library},ignored={ignored})")
            return 0, ''

        fuzzlogger.debug(cmd)

        best_ratio = 0.0
        best_partial = 0.0
        best_partname = 0.0
        have_prefix = False
        ratio_name = ""
        partial_name = ""
        partname_name = ""
        prefix_name = ""
        ratio_id = 0
        partial_id = 0
        partname_id = 0
        prefix_id = 0
        partname = 0
        best_type = ''
        partial_type = ''
        partname_type = ''
        prefix_type = ''

        book_lower = unaccented(book.lower(), only_ascii=False)
        book_lower = strip_quotes(book_lower)
        # source is the book_key eg hc_id, dnb_id
        # from this we need to see if the source provides subtitles
        has_subtitles = []
        for item in lazylibrarian.INFOSOURCES.keys():
            this_source = lazylibrarian.INFOSOURCES[item]
            if this_source['has_subs']:
                has_subtitles.append(this_source['book_key'])

        if source in has_subtitles:
            book_partname = ''
            book_sub = ''
        else:
            book_partname, book_sub, _ = split_title(author, book_lower)

        # We want to match a book on disk with a subtitle to a shorter book in the DB
        # - Strict prefix match with a : followed by junk is allowed
        # - Strict prefix match with a ()ed remainder is allowed
        # But the leading : is removed by has_clean_subtitle, so we allow all non (): subtitles
        has_clean_subtitle = re.search(r"^\s+([^:()]+|\([^)]+\))$", book_sub) is not None

        logger.debug(f"Searching {len(books)} {ign}{plural(len(books), 'book')} by "
                     f"[{authorid}:{author}] in database for [{book}]")
        if book_partname == book_lower:
            book_partname = ''
        fuzzlogger.debug(f'book partname [{book_partname}] book_sub [{book_sub}]')
        for a_book in books:
            a_bookname = a_book['BookName']
            if a_book['BookSub'] and book_sub:
                a_bookname += f" {a_book['BookSub']}"
            fuzzlogger.debug(f"Checking [{a_bookname}]")
            # tidy up everything to raise fuzziness scores
            # still need to lowercase for matching against partial_name later on
            a_book_lower = unaccented(a_bookname.lower(), only_ascii=False)
            a_book_lower = strip_quotes(a_book_lower)

            for entry in title_translates:
                if entry[0] in a_book_lower and entry[0] not in book_lower and entry[1] in book_lower:
                    a_book_lower = a_book_lower.replace(entry[0], entry[1])
                if entry[1] in a_book_lower and entry[1] not in book_lower and entry[0] in book_lower:
                    a_book_lower = a_book_lower.replace(entry[1], entry[0])
            
            # SERIES VALIDATION: Check series numbers match before fuzzy matching
            try:
                should_match, confidence = validate_series_match(book, a_bookname, a_book.get('BookID'))
                if not should_match:
                    fuzzlogger.debug(f"Skipping [{a_bookname}] - series number mismatch")
                    continue
            except Exception as e:
                fuzzlogger.error(f"Series validation error: {str(e)}")
                confidence = 1.0
            
            #
            # token sort ratio allows "Lord Of The Rings, The"   to match  "The Lord Of The Rings"
            ratio = fuzz.token_sort_ratio(book_lower, a_book_lower) * confidence
            # partial ratio allows "Lord Of The Rings"   to match  "The Lord Of The Rings"
            partial = fuzz.partial_ratio(book_lower, a_book_lower) * confidence
            if book_partname:
                # partname allows "Lord Of The Rings (illustrated edition)"   to match  "The Lord Of The Rings"
                partname = fuzz.partial_ratio(book_partname, a_book_lower) * confidence

            # lose points if the difference is just numbers so we don't match "book 2" and "book 3"
            # eg "He Who Fights With Monsters #7" is not the same as "He Who Fights With Monsters 05"
            set1 = set(book_lower.split())
            set2 = set(a_book_lower.split())
            differences = set1.symmetric_difference(set2)
            numbers = []
            for word in differences:
                # see if word coerces to an integer or a float
                try:
                    numbers.append(float(re.findall(r'\d+\.\d+', word)[0]))
                except IndexError:
                    try:
                        numbers.append(int(re.findall(r'\d+', word)[0]))
                    except IndexError:
                        pass
            if len(numbers) == 2 and numbers[0] != numbers[1]:
                # make sure we are below match threshold
                if ratio > CONFIG.get_int('NAME_RATIO'):
                    ratio = CONFIG.get_int('NAME_RATIO') - 1
                if partial > CONFIG.get_int('NAME_PARTIAL'):
                    partial = CONFIG.get_int('NAME_PARTIAL') - 1
                if partname > CONFIG.get_int('NAME_PARTNAME'):
                    partname = CONFIG.get_int('NAME_PARTNAME') - 1
                fuzzlogger.debug(f"Downgraded ratios as different numbers")

            # lose points if the difference is just numbers so we don't match "book 2" and "book 3"
            # eg "He Who Fights With Monsters #7" is not the same as "He Who Fights With Monsters 05"
            set1 = set(book_lower.split())
            set2 = set(a_book_lower.split())
            differences = set1.symmetric_difference(set2)
            numbers = []
            for word in differences:
                # see if word coerces to an integer or a float
                word = word.replace('-', '')
                try:
                    numbers.append(float(re.findall(r'\d+\.\d+', word)[0]))
                except IndexError:
                    try:
                        numbers.append(int(re.findall(r'\d+', word)[0]))
                    except IndexError:
                        pass
            if len(numbers) == 1 or (len(numbers) == 2 and numbers[0] != numbers[1]):
                # make sure we are below match threshold
                if ratio >= CONFIG.get_int('NAME_RATIO'):
                    ratio = CONFIG.get_int('NAME_RATIO') - 5
                if partial >= CONFIG.get_int('NAME_PARTIAL'):
                    partial = CONFIG.get_int('NAME_PARTIAL') - 5
                if partname >= CONFIG.get_int('NAME_PARTNAME'):
                    partname = CONFIG.get_int('NAME_PARTNAME') - 5
                fuzzlogger.debug(f"Downgraded ratios as different numbers")

            # lose a point for each extra word in the fuzzy matches so we get the closest match
            # this should also stop us matching single books against omnibus editions
            words = len(get_list(book_lower))
            words -= len(get_list(a_book_lower))
            ratio -= abs(words)
            partial -= abs(words)
            # don't subtract extra words from partname so we can compare books with/without subtitle
            # partname -= abs(words)

            def isitbest(aratio, abest_ratio, aratio_name, abest_type, astatus):
                use_it = False
                if aratio > abest_ratio:
                    use_it = True
                elif aratio == abest_ratio:
                    use_it = astatus == 'Have'
                    if not use_it:
                        want_words = get_list(book_lower)
                        best_words = get_list(aratio_name.lower())
                        new_words = get_list(a_bookname.lower())
                        best_cnt = 0
                        new_cnt = 0
                        for wrd in want_words:
                            if wrd in best_words:
                                best_cnt += 1
                            if wrd in new_words:
                                new_cnt += 1
                        if new_cnt > best_cnt:
                            use_it = True
                    if not use_it and abest_type == 'Ignored':
                        use_it = astatus != 'Ignored'
                return use_it

            if isitbest(ratio, best_ratio, ratio_name, best_type, a_book[whichstatus]):
                best_ratio = ratio
                best_type = a_book[whichstatus]
                ratio_name = a_book['BookName']
                ratio_id = a_book['BookID']

            if isitbest(partial, best_partial, partial_name, partial_type, a_book[whichstatus]):
                best_partial = partial
                partial_type = a_book[whichstatus]
                partial_name = a_book['BookName']
                partial_id = a_book['BookID']

            if isitbest(partname, best_partname, partname_name, partname_type, a_book[whichstatus]):
                best_partname = partname
                partname_type = a_book[whichstatus]
                partname_name = a_book['BookName']
                partname_id = a_book['BookID']

            if a_book_lower == book_partname and has_clean_subtitle:
                have_prefix = True
                prefix_type = a_book[whichstatus]
                prefix_name = a_book['BookName']
                prefix_id = a_book['BookID']

        if best_ratio >= CONFIG.get_int('NAME_RATIO'):
            logger.debug(f"Fuzz match ratio [{round(best_ratio, 2)}] [{book}] [{ratio_name}] {ratio_id}")
            return ratio_id, best_type
        if best_partial >= CONFIG.get_int('NAME_PARTIAL'):
            logger.debug(f"Fuzz match partial [{round(best_partial, 2)}] [{book}] [{partial_name}] {partial_id}")
            return partial_id, partial_type
        if best_partname >= CONFIG.get_int('NAME_PARTNAME'):
            logger.debug(f"Fuzz match partname [{round(best_partname, 2)}] [{book}] [{partname_name}] {partname_id}")
            return partname_id, partname_type

        if have_prefix:
            logger.debug(f"Fuzz match prefix [{book}] [{prefix_name}] {prefix_id}")
            return prefix_id, prefix_type

        if books:
            logger.debug(
                f'Best fuzz results [{author} - {book}] ratio [{round(best_ratio, 2)},{ratio_name},{ratio_id}], '
                f'partial [{round(best_partial, 2)},{partial_name},{partial_id}], '
                f'partname [{round(best_partname, 2)},{partname_name},{partname_id}]')

        if new_author:
            # we auto-added a new author but they don't have the book so we should remove them again
            db.action('DELETE from authors WHERE AuthorID=?', (authorid,))
        db.close()

    except Exception as e:
        logger.error(str(e))
        db.close()

    return 0, ''


def library_scan(startdir=None, library='eBook', authid=None, remove=True):
    """ Scan a directory tree adding new books into database
        Return how many books you added """
    logger = logging.getLogger(__name__)
    libsynclogger = logging.getLogger('special.libsync')
    matchinglogger = logging.getLogger('special.matching')
    destdir = get_directory(library)
    if not startdir:
        if not destdir:
            logger.warning(f'Cannot find destination directory: {destdir}. Not scanning')
            return 0
        startdir = destdir

    if not path_isdir(startdir):
        logger.warning(f'Cannot find directory: {startdir}. Not scanning')
        return 0

    if startdir == destdir:
        lazylibrarian.AUTHORS_UPDATE = 1
    logger.debug(f"Counting directories: {startdir}")
    dir_cnt = 0
    for rootdir, dirnames, filenames in walk(startdir):
        for directory in dirnames:
            lazylibrarian.libraryscan_data = f"Counting directories: {dir_cnt}"
            # prevent magazine being scanned
            c = directory[0]
            ignorefile = '.ll_ignore'
            dirname = os.path.join(rootdir, directory)
            if c in ["_", "."]:
                logger.debug(f'Skipping {dirname}')
                # ignore directories containing this special file
            elif path_exists(os.path.join(rootdir, directory, ignorefile)):
                logger.debug(f'Found .ll_ignore file in {dirname}')
            elif (book_file(dirname, booktype='ebook', config=CONFIG, recurse=False) or
                  book_file(dirname, booktype='audiobook', config=CONFIG, recurse=False)):
                dir_cnt += 1
    msg = f"Found {dir_cnt} directories"
    logger.debug(msg)
    lazylibrarian.libraryscan_data = msg

    db = database.DBConnection()
    processed_subdirectories = []
    rehit = []
    remiss = []
    # noinspection PyBroadException
    try:
        # keep statistics of full library scans
        if startdir == destdir:
            lazylibrarian.AUTHORS_UPDATE = 1
            if library == 'eBook':
                lazylibrarian.EBOOK_UPDATE = 1
            elif library == 'AudioBook':
                lazylibrarian.AUDIO_UPDATE = 1
            db.action('DELETE from stats')
            try:  # remove any extra whitespace in authornames
                authors = db.select("SELECT AuthorID,AuthorName FROM authors WHERE instr(AuthorName, '  ') > 0")
                if authors:
                    logger.info(f"Removing extra spaces from {len(authors)} {plural(len(authors), 'authorname')}")
                    for author in authors:
                        authorid = author["AuthorID"]
                        authorname = ' '.join(author['AuthorName'].split())
                        # Have we got author name both with-and-without extra spaces? If so, merge them
                        duplicate = db.match(
                            'Select AuthorID,AuthorName FROM authors WHERE AuthorName=?', (authorname,))
                        if duplicate:
                            db.action('DELETE from authors where authorname=?', (author['AuthorName'],))
                            if author['AuthorID'] != duplicate['AuthorID']:
                                db.action('UPDATE books set AuthorID=? WHERE AuthorID=?',
                                          (duplicate['AuthorID'], author['AuthorID']))
                        else:
                            db.action('UPDATE authors set AuthorName=? WHERE AuthorID=?', (authorname, authorid))
            except Exception as e:
                logger.error(f'{type(e).__name__} {str(e)}')
        else:
            if authid:
                match = db.match('SELECT authorid from authors where authorid=?', (authid,))
                if match:
                    control_value_dict = {"AuthorID": authid}
                    new_value_dict = {"Status": "Loading"}
                    db.upsert("authors", new_value_dict, control_value_dict)

        logger.info(f'Scanning {library} directory: {startdir}')
        new_book_count = 0
        modified_count = 0
        rescan_count = 0
        rescan_hits = 0
        file_count = 0

        # allow full_scan override so we can scan in alternate directories without deleting others
        if remove:
            if library == 'eBook':
                cmd = ("select AuthorName, BookName, BookFile, BookID from books,authors where BookLibrary "
                       "is not null and books.AuthorID = authors.AuthorID")
                if not startdir == destdir:
                    cmd += f" and instr(BookFile, '{startdir}') = 1"
                books = db.select(cmd)
                status = CONFIG['NOTFOUND_STATUS']
                logger.info(f'Missing eBooks will be marked as {status}')
                for book in books:
                    bookfile = book['BookFile']

                    if bookfile and not path_isfile(bookfile):
                        db.action("update books set Status=?,BookFile='',BookLibrary='' where BookID=?",
                                  (status, book['BookID']))
                        logger.warning(f"eBook {book['AuthorName']} - {book['BookName']} updated as not found on disk")

            else:  # library == 'AudioBook':
                cmd = ("select AuthorName, BookName, AudioFile, BookID from books,authors where AudioLibrary "
                       "is not null and books.AuthorID = authors.AuthorID")
                if not startdir == destdir:
                    cmd += f" and instr(AudioFile, '{startdir}') = 1"
                books = db.select(cmd)
                status = CONFIG['NOTFOUND_STATUS']
                logger.info(f'Missing AudioBooks will be marked as {status}')
                for book in books:
                    bookfile = book['AudioFile']

                    if bookfile and not path_isfile(bookfile):
                        db.action("update books set AudioStatus=?,AudioFile='',AudioLibrary='' where BookID=?",
                                  (status, book['BookID']))
                        logger.warning(
                            f"Audiobook {book['AuthorName']} - {book['BookName']} updated as not found on disk")

        # to save repeat-scans of the same directory if it contains multiple formats of the same book,
        # keep track of which directories we've already looked at
        warned_no_new_authors = False  # only warn about the setting once
        booktypes = ''
        count = -1
        if library == 'eBook':
            booktype_list = get_list(CONFIG['EBOOK_TYPE'])
            for book_type in booktype_list:
                count += 1
                if count == 0:
                    booktypes = book_type
                else:
                    booktypes = f"{booktypes}|{book_type}"

            matchto = CONFIG['EBOOK_DEST_FILE']
        else:
            booktype_list = get_list(CONFIG['AUDIOBOOK_TYPE'])
            for book_type in booktype_list:
                count += 1
                if count == 0:
                    booktypes = book_type
                else:
                    booktypes = f"{booktypes}|{book_type}"

            matchto = CONFIG['AUDIOBOOK_DEST_FILE']

        match_string = ''
        for char in matchto:
            if not char.isalpha():
                match_string += '\\'
            match_string = match_string + char

        match_string = match_string.replace(
            "\\$Author", "(?P<author>.*?)").replace(
            "\\$SortAuthor", "(?P<sauthor>.*?)").replace(
            "\\$Title", "(?P<book>.*?)").replace(
            "\\$SortTitle", "(?P<sbook>.*?)").replace(
            "\\$Series", "(?P<series>.*?)").replace(
            "\\$SerNum", "(?P<sernum>.*?)").replace(
            "\\$SerName", "(?P<sername>.*?)").replace(
            "\\$FmtName", "(?P<fmtname>.*?)").replace(
            "\\$FmtNum", "(?P<fmtnum>.*?)").replace(
            "\\$PadNum", "(?P<padnum>.*?)").replace(
            "\\$PubYear", "(?P<pubyear>.*?)").replace(
            "\\$SerYear", "(?P<seryear>.*?)").replace(
            "\\$Part", "(?P<part>.*?)").replace(
            "\\$Total", "(?P<total>.*?)").replace(
            "\\$Abridged", "(?P<abridged>.*?)").replace(
            "\\$\\$", "\\ ") + r'\.[' + booktypes + ']'
        matchinglogger.debug(f"Pattern [{match_string}]")

        # noinspection PyBroadException
        try:
            pattern = re.compile(match_string, re.VERBOSE | re.IGNORECASE)
        except Exception as e:
            logger.error(f"Pattern failed for [{matchto}] {str(e)}")
            pattern = None

        last_authorid = None
        for rootdir, dirnames, filenames in walk(startdir):
            for directory in dirnames:
                # prevent magazine being scanned
                c = directory[0]
                ignorefile = '.ll_ignore'
                if c in ["_", "."]:
                    logger.debug(f'Skipping {os.path.join(rootdir, directory)}')
                    dirnames.remove(directory)
                    # ignore directories containing this special file
                elif path_exists(os.path.join(rootdir, directory, ignorefile)):
                    logger.debug(f'Found .ll_ignore file in {os.path.join(rootdir, directory)}')
                    dirnames.remove(directory)
            subdirectory = rootdir.replace(make_unicode(startdir), '')
            total_items = dir_cnt
            for files in filenames:
                current_item = len(processed_subdirectories)
                current_percent = int(current_item * 100 / total_items) if total_items else 0
                lazylibrarian.libraryscan_data = f"{current_item}/{total_items}/{current_percent}"
                # Added new code to skip if we've done this directory before.
                # Made this conditional with a switch in config.ini
                # in case user keeps multiple different books in the same subdirectory
                if library == 'eBook' and CONFIG.get_bool('IMP_SINGLEBOOK') and \
                        (subdirectory in processed_subdirectories):
                    libsynclogger.debug(f"[{subdirectory}] already scanned")
                elif library == 'AudioBook' and (subdirectory in processed_subdirectories):
                    libsynclogger.debug(f"[{subdirectory}] already scanned")
                elif not path_isdir(rootdir):
                    logger.debug(f"Directory {repr(rootdir)} missing (renamed?)")
                else:
                    # If this is a book, try to get author/title/isbn/language
                    # if epub or mobi, read metadata from the book
                    # If metadata.opf exists, use that allowing it to override
                    # embedded metadata. User may have edited metadata.opf
                    # to merge author aliases together
                    # If all else fails, try pattern match for author/title
                    # and look up isbn/lang from LT or GR later
                    if (library == 'eBook' and CONFIG.is_valid_booktype(files, 'ebook')) or \
                            (library == 'AudioBook' and CONFIG.is_valid_booktype(files, 'audiobook')):

                        logger.debug(f"[{startdir}] Now scanning subdirectory {subdirectory}")
                        file_count += 1
                        language = "Unknown"
                        isbn = ""
                        book = ""
                        author = ""
                        publisher = ""
                        narrator = ""
                        extn = os.path.splitext(files)[1]
                        bookid = None
                        forced_bookid = ''

                        # if it's an epub or a mobi we can try to read metadata from it
                        res = {}
                        if extn.lower() in [".epub", ".mobi"]:
                            book_filename = os.path.join(rootdir, files)
                            try:
                                res = get_book_info(book_filename)
                            except Exception as e:
                                logger.error(f'get_book_info failed for {book_filename}, {type(e).__name__} {str(e)}')
                                res = {}
                            # title and creator are the minimum we need
                            if 'title' in res and 'creator' in res:
                                book = res['title']
                                author = res['creator']
                                if 'language' in res:
                                    language = res['language']
                                isbn = res.get('isbn', '')
                                if 'type' in res:
                                    extn = res['type']

                                logger.debug(f"book meta [{isbn}] [{language}] [{author}] [{book}] [{extn}]")
                            if not author and book:
                                logger.debug(f"Book meta incomplete in {book_filename}")

                        # calibre uses "metadata.opf", LL uses "bookname - authorname.opf"
                        # just look for any .opf file in the current directory since we don't know
                        # LL preferred authorname/bookname at this point.
                        # Allow metadata in opf file to override book metadata as may be users pref
                        metafile = ''
                        try:
                            metafile = opf_file(rootdir)
                            if metafile:
                                res2 = get_book_info(metafile)
                                for item in res2:
                                    res[item] = res2[item]
                        except Exception as e:
                            logger.error(f'get_book_info failed for {metafile}, {type(e).__name__} {str(e)}')

                        # title and creator are the minimum we need
                        if res and 'title' in res and 'creator' in res:
                            book = res['title']
                            author = res['creator']
                            author = author.strip()  # some audiobooks have fields of spaces
                            book = book.strip()
                            if 'language' in res:
                                language = res['language']
                            if 'isbn' in res:
                                isbn = res['isbn']
                            if 'publisher' in res:
                                publisher = res['publisher']
                            if 'narrator' in res:
                                narrator = res['narrator']
                            ident = ''
                            if 'gr_id' in res:
                                gr_id = res['gr_id']
                                ident = f"GR: {gr_id}"
                            if 'gb_id' in res:
                                gb_id = res['gb_id']
                                ident = f"GB: {gb_id}"
                            if 'ol_id' in res:
                                ol_id = res['ol_id']
                                ident = f"OL: {ol_id}"
                            if 'hc_id' in res:
                                hc_id = res['hc_id']
                                ident = f"HC: {hc_id}"
                            if 'dnb_id' in res:
                                dnb_id = res['dnb_id']
                                ident = f"DN: {dnb_id}"
                            logger.debug(
                                f"file meta [{isbn}] [{language}] [{author}] [{book}] [{ident}] [{publisher}] "
                                f"[{narrator}]")
                            if not author or not book:
                                logger.debug(f"File meta incomplete in {metafile}")

                        if not author or not book:
                            # no author/book from metadata file, and not embedded either
                            # or audiobook which may have id3 tags
                            if CONFIG.is_valid_booktype(files, 'audiobook'):
                                filename = os.path.join(rootdir, files)
                                id3tags = id3read(filename)
                                author = id3tags.get('author')
                                book = id3tags.get('title')
                                if not narrator:
                                    narrator = id3tags.get('narrator')

                        if not author or not book:
                            # try for details from a special file
                            author, book, forced_bookid = get_book_meta(rootdir, reason="libraryscan")

                        # Failing anything better, just pattern match on filename
                        if pattern and (not author or not book):
                            # might need a different pattern match for audiobooks
                            # as they often seem to have xxChapter-Seriesnum Author Title
                            # but hopefully the tags will get there first...
                            match = pattern.match(files)
                            if match:
                                try:
                                    author = match.group("author")
                                except IndexError:
                                    author = ''
                                if not author:
                                    try:
                                        author = match.group("sauthor")
                                    except IndexError:
                                        author = ''
                                try:
                                    book = match.group("book")
                                except IndexError:
                                    book = ''
                                if not book:
                                    try:
                                        book = match.group("sbook")
                                    except IndexError:
                                        book = ''

                                book = make_unicode(book)
                                author = make_unicode(author)

                            if not author or not book:
                                logger.debug(f"Pattern match failed [{files}]")
                            else:
                                logger.debug(f"Pattern match author[{author}] book[{book}]")

                        if publisher:
                            if publisher.lower() in get_list(CONFIG['REJECT_PUBLISHER']):
                                logger.warning(f"Ignoring {files}: Publisher {publisher}")
                                author = ''  # suppress

                        if not author or not book:
                            logger.debug(f"No valid {library} found in {subdirectory}")
                        else:
                            # flag that we found a book in this subdirectory
                            if subdirectory:
                                processed_subdirectories.append(subdirectory)

                            # If we have a valid looking isbn, and language != "Unknown", add it to cache
                            if language != "Unknown" and is_valid_isbn(isbn):
                                logger.debug(f"Found Language [{language}] ISBN [{isbn}]")
                                # we need to add it to language cache if not already
                                # there, is_valid_isbn has checked length is 10 or 13
                                if len(isbn) == 10:
                                    isbnhead = isbn[0:3]
                                else:
                                    isbnhead = isbn[3:6]
                                match = db.match('SELECT lang FROM languages where isbn=?', (isbnhead,))
                                if not match:
                                    db.action('insert into languages values (?, ?)', (isbnhead, language))
                                    logger.debug(f"Cached Lang [{language}] ISBN [{isbnhead}]")
                                else:
                                    logger.debug(f"Already cached Lang [{language}] ISBN [{isbnhead}]")

                            newauthorname, authorid, new_author = add_author_name_to_db(
                                author, addbooks=None, reason=f"Add author of {book}", title=book)

                            if last_authorid and last_authorid != authorid:
                                update_totals(last_authorid)
                            last_authorid = authorid

                            if newauthorname and newauthorname != author:
                                logger.debug(f"Preferred authorname changed from [{author}] to [{newauthorname}]")
                                author = make_unicode(newauthorname)
                            if not authorid:
                                logger.warning(f"Authorname {author} not added to database")

                            if authorid:
                                # author exists, check if this book by this author is in our database
                                # metadata might have quotes in book name
                                # some books might be stored under a different author name
                                # e.g. books by multiple authors, books where author is "writing as"
                                # or books we moved to "merge" authors
                                book = strip_quotes(book)

                                # If we have a valid ID, use that
                                mtype = ''
                                match = None
                                this_source = lazylibrarian.INFOSOURCES[CONFIG['BOOK_API']]
                                try:
                                    bookid = eval(this_source['book_key'])
                                except NameError:
                                    bookid = None
                                if bookid:
                                    match = db.match('SELECT AuthorID,Status FROM books where BookID=?',
                                                     (bookid,))
                                    if match:
                                        mtype = match['Status']
                                        if authorid != match['AuthorID']:
                                            logger.warning(
                                                f"Metadata authorid [{authorid}] does not match database "
                                                f"[{match['AuthorID']}]")
                                    if not match:
                                        cmd = "SELECT Status,BookID FROM books where BookName=? and AuthorID=?"
                                        match = db.match(cmd, (book, authorid))
                                        if match:
                                            logger.warning(
                                                f"Metadata bookid [{bookid}] not found in database, title matches "
                                                f"{match['BookID']}")
                                            mtype = match['Status']
                                            # update stored bookid to match preferred (owned) book
                                            db.action('PRAGMA foreign_keys = OFF')
                                            for table in ['books', 'member', 'wanted', 'failedsearch', 'genrebooks']:
                                                cmd = f"UPDATE {table} SET BookID=? WHERE BookID=?"
                                                db.action(cmd, (bookid, match['BookID']))
                                            db.action('PRAGMA foreign_keys = ON')

                                if not match:
                                    # Try and find in database under author and bookname
                                    # as we may have it under a different bookid or isbn to goodreads/googlebooks
                                    # which might have several bookid/isbn for the same book
                                    reason = f'Author exists for {book}'
                                    logger.debug(reason)
                                    oldbookid = bookid
                                    bookid, mtype = find_book_in_db(author, book, reason=reason)
                                    if bookid:
                                        if oldbookid:
                                            logger.warning(
                                                f"Metadata bookid [{oldbookid}] not found in database, using {bookid}")
                                        else:
                                            logger.debug(f"Found bookid {bookid} for {book}")
                                    elif oldbookid:
                                        bookid = oldbookid
                                        logger.warning(
                                            f"Metadata bookid [{bookid}] not found in database, trying to add...")

                                        this_source = lazylibrarian.INFOSOURCES[CONFIG['BOOK_API']]
                                        api = this_source['api']
                                        book_id = eval(this_source['book_key'])
                                        if book_id:
                                            src = this_source['src']
                                            api.add_bookid_to_db(book_id, None, None, f"Added by {src}"
                                                                 f" librarysync")
                                    if bookid:
                                        # see if it's there now...
                                        match = db.match('SELECT AuthorID,BookName,Status from books where BookID=?',
                                                         (bookid,))
                                        if match:
                                            mtype = match['Status']
                                            book = match['BookName']
                                            if authorid != match['AuthorID']:
                                                logger.warning(
                                                    f"Metadata authorid [{authorid}] does not match database "
                                                    f"[{match['AuthorID']}]")
                                        else:
                                            logger.debug(f"Unable to add bookid via metadata bookid ({bookid})")
                                            bookid = ""

                                if not bookid and isbn:
                                    # See if the isbn is in our database
                                    match = db.match('SELECT AuthorID,BookID,Status FROM books where BookIsbn=?',
                                                     (isbn,))
                                    if match:
                                        bookid = match['BookID']
                                        mtype = match['Status']
                                        if authorid != match['AuthorID']:
                                            logger.warning(
                                                f"Metadata authorid [{authorid}] does not match database "
                                                f"[{match['AuthorID']}]")

                                if bookid and mtype == "Ignored":
                                    logger.warning(
                                        f"Book {book} by {author} is marked Ignored in database, importing anyway")

                                if not bookid and forced_bookid:
                                    if lazylibrarian.postprocess.process_book_from_dir(source_dir=rootdir,
                                                                                       library=library,
                                                                                       bookid=forced_bookid):
                                        bookid = forced_bookid

                                if not bookid:
                                    # get author name from (grand)parent directory of this book directory
                                    book_filename = os.path.join(rootdir, files)
                                    newauthorname = book_filename[len(startdir.rstrip(os.sep)) + 1:].split(os.sep)[0]
                                    if ' ' not in newauthorname:
                                        newauthorname = os.path.basename(os.path.dirname(rootdir))
                                    newauthorname = make_unicode(newauthorname)
                                    # calibre replaces trailing periods with _ e.g. Smith Jr. -> Smith Jr_
                                    if newauthorname.endswith('_'):
                                        newauthorname = f"{newauthorname[:-1]}."
                                    if author.lower() != newauthorname.lower():
                                        logger.debug(f"Trying authorname [{newauthorname}]")
                                        bookid, mtype = find_book_in_db(newauthorname, book, ignored=False,
                                                                        reason=f'New author for {book}')
                                        if bookid and mtype == "Ignored":
                                            logger.warning(f"Book {book} by {newauthorname} is marked "
                                                           f"Ignored in database, importing anyway")
                                        if bookid:
                                            logger.warning(
                                                f"{book} not found under [{author}], found under [{newauthorname}]")

                                # at this point if we still have no bookid, it looks like we
                                # have author and book title but no database entry for it
                                if not bookid:
                                    sources = [CONFIG['BOOK_API']]
                                    if CONFIG.get_bool('MULTI_SOURCE'):
                                        # Either original source doesn't have the book, or it didn't match language
                                        # prefs, or it's under another author (pseudonym, series continuation author)
                                        # Since we have the book anyway, try and reload it
                                        for source in lazylibrarian.INFOSOURCES.keys():
                                            this_source = lazylibrarian.INFOSOURCES[source]
                                            if source not in sources and CONFIG[this_source['enabled']]:
                                                sources.append(source)

                                    searchresults = []
                                    for source in sources:
                                        searchresults += search_for(f"{book}<ll>{author}", source)

                                    sortedlist = sorted(searchresults,
                                                        key=lambda x: (x['highest_fuzz'], x['bookrate_count']),
                                                        reverse=True)
                                    rescan_count += 1
                                    bookid = ''
                                    bookauthor = ''
                                    booktitle = ''
                                    language = ''
                                    source = ''
                                    closest = 0
                                    bestmatch = 0
                                    if sortedlist:
                                        item = sortedlist[0]
                                        closest = item['highest_fuzz']
                                        while bestmatch + 1 < len(sortedlist) and item['source'] != CONFIG['BOOK_API']:
                                            bestmatch += 1
                                            if sortedlist[bestmatch]['highest_fuzz'] < closest:
                                                break
                                            if sortedlist[bestmatch]['source'] == CONFIG['BOOK_API']:
                                                item = sortedlist[bestmatch]

                                        if closest >= CONFIG.get_int('NAME_PARTIAL'):
                                            rescan_hits += 1
                                            logger.debug(
                                                f"Rescan {item['source']} found [{item['authorname']}] "
                                                f"{item['bookname']} : {item['booklang']}: {item['bookid']}")
                                            bookid = item['bookid']
                                            bookauthor = item['authorname']
                                            booktitle = item['bookname']
                                            language = item['booklang']
                                            source = item['source']
                                            rehit.append(booktitle)
                                    if bookid:
                                        cmd = "SELECT * from books WHERE BookID=?"
                                        check_status = db.match(cmd, (bookid,))
                                        if check_status:
                                            logger.debug(f"{bookid} [{bookauthor}] matched on rescan for {booktitle}")
                                        else:
                                            logger.debug(f"Adding {bookid} [{bookauthor}] on rescan for {booktitle}")
                                            this_source = lazylibrarian.INFOSOURCES[source]
                                            api = this_source['api']
                                            api.add_bookid_to_db(bookid, reason=f"Librarysync {source} "
                                                                                f"rescan {bookauthor}")
                                            if language and language != "Unknown":
                                                # set language from book metadata
                                                logger.debug(f"Setting language from metadata {booktitle} : {language}")
                                                cmd = "UPDATE books SET BookLang=? WHERE BookID=?"
                                                db.action(cmd, (language, bookid))
                                    else:
                                        logger.warning(f"Rescan no match for {book}, closest {round(closest, 2)}%")
                                        remiss.append(f"{book}:{author} ({round(closest, 2)}%)")

                                # see if it's there now...
                                if bookid:
                                    cmd = ("SELECT books.Status, books.AuthorID, AudioStatus, BookFile, AudioFile, "
                                           "AuthorName, BookName, BookID, BookDesc, BookGenre,Narrator from "
                                           "books,authors where books.AuthorID = authors.AuthorID and BookID=?")
                                    check_status = db.match(cmd, (bookid,))

                                    if not check_status:
                                        logger.debug(f'Unable to find bookid {bookid} in database')
                                    else:
                                        if CONFIG['CONTRIBUTING_AUTHORS'] and res and 'authors' in res:
                                            authorlist = split_author_names(res['authors'],
                                                                            get_list(CONFIG['MULTI_AUTHOR_SPLIT']))
                                            for auth in authorlist:
                                                if auth != check_status['AuthorID']:  # primary author already added
                                                    aname, aid, added = (
                                                        add_author_name_to_db(auth, addbooks=False,
                                                                              reason=f"Contributor to "
                                                                                     f"{check_status['BookName']}"))
                                                    if aid:
                                                        # Add any new authors as contributing authors
                                                        db.action('INSERT into bookauthors (AuthorID, BookID, Role) '
                                                                  'VALUES (?, ?, ?)',
                                                                  (aid, check_status['BookID'], ROLE['CONTRIBUTING']),
                                                                  suppress='UNIQUE')
                                                        update_totals(aid)

                                        book_filename = None
                                        if library == 'eBook':
                                            if check_status['Status'] != 'Open':
                                                # we found a new book
                                                new_book_count += 1
                                                db.action(
                                                    'UPDATE books set Status=?, BookLibrary=? where BookID=?',
                                                    (CONFIG['FOUND_STATUS'], now(), bookid))

                                            # create an opf file if there isn't one
                                            book_filename = os.path.join(rootdir, files)
                                            _ = lazylibrarian.postprocess.create_opf(os.path.dirname(book_filename),
                                                                                     check_status,
                                                                                     os.path.splitext(os.path.basename(
                                                                                         book_filename))[0],
                                                                                     overwrite=False)

                                            db.action("UPDATE books SET BookFile=? where BookID=?",
                                                      (book_filename, bookid))

                                            if CONFIG.get_bool('IMP_RENAME'):
                                                book_filename, _ = book_rename(bookid)

                                            # check preferred type and store book location
                                            # so we can check if it gets (re)moved
                                            book_basename = os.path.splitext(book_filename)[0]
                                            booktype_list = get_list(CONFIG['EBOOK_TYPE'])
                                            for book_type in booktype_list:
                                                preferred_type = f"{book_basename}.{book_type}"
                                                if path_exists(preferred_type):
                                                    book_filename = preferred_type
                                                    logger.debug(f"Librarysync link to preferred type {book_type}")
                                                    break

                                            # location may have changed on rename
                                            if book_filename != check_status['BookFile']:
                                                db.action('UPDATE books SET BookFile=? WHERE BookID=?',
                                                          (book_filename, bookid))
                                                modified_count += 1

                                            if 'unknown' in check_status['AuthorName'].lower():
                                                newauth = db.match("SELECT * from authors WHERE AuthorName=?",
                                                                   (author,))
                                                if newauth:
                                                    logger.debug(
                                                        f"Moving {bookid} from {check_status['AuthorName']} "
                                                        f"to {author}")
                                                    db.action('UPDATE books set AuthorID=? where BookID=?',
                                                              (newauth['AuthorID'], bookid))
                                                    db.action("DELETE from authors WHERE AuthorID=?",
                                                              (check_status['AuthorID'],))

                                        elif library == 'AudioBook':
                                            if 'narrator' and not check_status['Narrator']:
                                                db.action("update books set narrator=? where bookid=?", (narrator,
                                                                                                         bookid))
                                                check_status = db.match(cmd, (bookid,))

                                            if check_status['AudioStatus'] != 'Open':
                                                # we found a new audiobook
                                                new_book_count += 1
                                                db.action(
                                                    'UPDATE books set AudioStatus=?, AudioLibrary=? where BookID=?',
                                                    (CONFIG['FOUND_STATUS'], now(), bookid))

                                            # store audiobook location so we can check if it gets (re)moved
                                            book_filename = os.path.join(rootdir, files)
                                            # create an opf if there isn't one
                                            _ = lazylibrarian.postprocess.create_opf(os.path.dirname(book_filename),
                                                                                     check_status,
                                                                                     check_status['BookName'],
                                                                                     overwrite=False)
                                            # link to the first part of multi-part audiobooks
                                            tokmatch = ''
                                            for token in [' 001.', ' 01.', ' 1.', ' 001 ', ' 01 ', ' 1 ', '01']:
                                                if tokmatch:
                                                    break
                                                for e in listdir(rootdir):
                                                    if CONFIG.is_valid_booktype(e, booktype='audiobook') and token in e:
                                                        book_filename = os.path.join(rootdir, e)
                                                        logger.debug(
                                                            f"Librarysync link to preferred part {token}: "
                                                            f"{book_filename}")
                                                        tokmatch = token
                                                        break

                                            db.action('UPDATE books set AudioFile=? where BookID=?',
                                                      (book_filename, bookid))

                                            if CONFIG['AUDIOBOOK_DEST_FILE']:
                                                if CONFIG.get_bool('IMP_RENAME'):
                                                    book_filename = audio_rename(bookid, rename=True, playlist=True)
                                                    preprocess_audio(os.path.dirname(book_filename), bookid,
                                                                     author, book, tag=True)
                                                else:
                                                    book_filename = audio_rename(bookid, rename=False, playlist=True)

                                            # location may have changed since last scan
                                            if book_filename and book_filename != check_status['AudioFile']:
                                                modified_count += 1
                                                logger.warning(f"Updating audiobook location for {author} {book} from "
                                                               f"{check_status['AudioFile']} to {book_filename}")
                                                db.action('UPDATE books set AudioFile=? where BookID=?',
                                                          (book_filename, bookid))

                                        # update cover file to any .jpg in book folder, prefer cover.jpg
                                        if book_filename:
                                            bookdir = os.path.dirname(book_filename)
                                            cachedir = DIRS.CACHEDIR
                                            cacheimg = os.path.join(cachedir, 'book', f"{bookid}.jpg")
                                            coverimg = os.path.join(bookdir, 'cover.jpg')
                                            if not path_isfile(coverimg):
                                                coverimg = any_file(bookdir, '.jpg')
                                            if coverimg:
                                                shutil.copyfile(coverimg, cacheimg)
                                else:
                                    if library == 'eBook':
                                        logger.warning(
                                            f"Failed to match book [{book}] by [{author}] in database")
                                    else:
                                        logger.warning(
                                            f"Failed to match audiobook [{book}] by [{author}] in database")

                            if not authorid:
                                if not warned_no_new_authors and not CONFIG.get_bool('ADD_AUTHOR'):
                                    logger.warning("Add authors to database is disabled")
                                    warned_no_new_authors = True

                            if new_author and not bookid:
                                # we auto-added a new author but they don't have the book so we should remove them again
                                db.action('DELETE from authors WHERE AuthorID=?', (authorid,))
        if last_authorid:
            update_totals(last_authorid)

        logger.info(
            f"{new_book_count}/{modified_count} new/modified {library}{plural(new_book_count + modified_count)} "
            f"found and added to the database")
        logger.info(f"{file_count} {plural(file_count, 'file')} processed")

        if startdir == destdir:
            if len(remiss):
                lazylibrarian.libraryscan_data = (f'<div class="alert alert-danger">'
                                                  f'Failed to match {len(remiss)}<br></div>')
            # On full library scans, check for books with unknown language
            nolang = db.match(
                "select count(*) as counter from Books where status='Open' and BookLang='Unknown'")
            nolang = nolang['counter']
            if nolang:
                logger.warning(f"Found {nolang} {plural(nolang, 'book')} in your library with unknown language")
                # show stats if new books were added
            cmd = ("SELECT sum(GR_book_hits), sum(GR_lang_hits), sum(LT_lang_hits), sum(GB_lang_change), "
                   "sum(cache_hits), sum(bad_lang), sum(bad_char), sum(uncached), sum(duplicates) FROM stats")
            stats = db.match(cmd)

            st = {'GR_book_hits': stats['sum(GR_book_hits)'], 'GB_book_hits': stats['sum(GR_book_hits)'],
                  'GR_lang_hits': stats['sum(GR_lang_hits)'], 'LT_lang_hits': stats['sum(LT_lang_hits)'],
                  'GB_lang_change': stats['sum(GB_lang_change)'], 'cache_hits': stats['sum(cache_hits)'],
                  'bad_lang': stats['sum(bad_lang)'], 'bad_char': stats['sum(bad_char)'],
                  'uncached': stats['sum(uncached)'], 'duplicates': stats['sum(duplicates)']}

            # noinspection PyUnresolvedReferences
            for item in list(st.keys()):
                if st[item] is None:
                    st[item] = 0

            if CONFIG['BOOK_API'] == "GoogleBooks":
                logger.debug(f"GoogleBooks was hit {st['GR_book_hits']} {plural(st['GR_book_hits'], 'time')} for books")
                logger.debug(
                    f"GoogleBooks language was changed {st['GB_lang_change']} {plural(st['GB_lang_change'], 'time')}")
            elif CONFIG['BOOK_API'] == "OpenLibrary":
                logger.debug(f"OpenLibrary was hit {st['GR_book_hits']} {plural(st['GR_book_hits'], 'time')} for books")
            elif CONFIG['BOOK_API'] == "HardCover":
                logger.debug(f"HardCover was hit {st['GR_book_hits']} {plural(st['GR_book_hits'], 'time')} for books")
            elif CONFIG['BOOK_API'] == "GoodReads":
                logger.debug(f"GoodReads was hit {st['GR_book_hits']} {plural(st['GR_book_hits'], 'time')} for books")
                logger.debug(
                    f"GoodReads was hit {st['GR_lang_hits']} {plural(st['GR_lang_hits'], 'time')} for languages")
            logger.debug(
                f"LibraryThing was hit {st['LT_lang_hits']} {plural(st['LT_lang_hits'], 'time')} for languages")
            logger.debug(f"Language cache was hit {st['cache_hits']} {plural(st['cache_hits'], 'time')}")
            logger.debug(f"Unwanted language removed {st['bad_lang']} {plural(st['bad_lang'], 'book')}")
            logger.debug(f"Invalid/Incomplete removed {st['bad_char']} {plural(st['bad_char'], 'book')}")
            logger.debug(
                f"Unable to cache language for {st['uncached']} {plural(st['uncached'], 'book')} with missing ISBN")
            logger.debug(f"Found {st['duplicates']} duplicate {plural(st['duplicates'], 'book')}")
            logger.debug(f"Rescan {rescan_hits} {plural(rescan_hits, 'hit')}, {rescan_count - rescan_hits} miss")
            for bk in rehit:
                logger.debug(f"HIT: {bk}")
            for bk in remiss:
                logger.debug(f"MISS: {bk}")
            logger.debug(
                f"Cache {lazylibrarian.CACHE_HIT} {plural(lazylibrarian.CACHE_HIT, 'hit')}, "
                f"{lazylibrarian.CACHE_MISS} miss")
            cachesize = db.match("select count(*) as counter from languages")
            logger.debug(f"ISBN Language cache holds {cachesize['counter']} {plural(cachesize['counter'], 'entry')}")

            # Cache any covers and images
            images = db.select("select bookid, bookimg, bookname from books where instr(bookimg, 'http') = 1")
            if len(images):
                logger.info(f"Caching {plural(len(images), 'cover')} for {len(images)} {plural(len(images), 'book')}")
                for item in images:
                    bookid = item['bookid']
                    bookimg = item['bookimg']
                    # bookname = item['bookname']
                    newimg, success, _ = cache_img(ImageType.BOOK, bookid, bookimg)
                    if success:
                        db.action('update books set BookImg=? where BookID=?', (newimg, bookid))
                    else:
                        logger.warning(f"Unable to cache image for BookID {bookid}")
                        db.action('update books set BookImg=? where BookID=?', ('images/nocover.png', bookid))

            images = db.select("select AuthorID, AuthorImg, AuthorName from authors where instr(AuthorImg, 'http') = 1")
            if len(images):
                logger.info(f"Caching {plural(len(images), 'image')} for {len(images)} {plural(len(images), 'author')}")
                for item in images:
                    authorid = item['authorid']
                    authorimg = item['authorimg']
                    # authorname = item['authorname']
                    newimg, success, _ = cache_img(ImageType.AUTHOR, img_id(), authorimg)
                    if success:
                        db.action('update authors set AuthorImg=? where AuthorID=?', (newimg, authorid))
                    else:
                        logger.warning(f"Unable to cache image for AuthorID {authorid}")
                        db.action('update authors set AuthorImg=? where AuthorID=?', ('images/nophoto.png', authorid))

            cnt = len(delete_empty_folders(startdir))  # tidy up
            logger.debug(f"Deleted {cnt} empty {plural(cnt, 'folder')} in {startdir}")

            if library == 'eBook':
                lazylibrarian.EBOOK_UPDATE = 0
            elif library == 'AudioBook':
                lazylibrarian.AUDIO_UPDATE = 0
            lazylibrarian.AUTHORS_UPDATE = 0
        else:
            if authid:
                match = db.match('SELECT authorid from authors where authorid=?', (authid,))
                if match:
                    control_value_dict = {"AuthorID": authid}
                    new_value_dict = {"Status": "Active"}
                    db.upsert("authors", new_value_dict, control_value_dict)
                    # On single author/book import, just update bookcount for that author
                    update_totals(authid)

        if remove:
            # sometimes librarything tells us about a series contributor
            # but openlibrary doesn't agree...
            res = db.select("select * from authors where status='Paused' and totalbooks=0")
            if len(res):
                logger.debug(f"Removed {len(res)} empty series authors")
                db.action("delete from authors where status='Paused' and totalbooks=0")

        logger.info('Library scan complete')
        return new_book_count

    except Exception:
        logger.error(f'Unhandled exception in library_scan: {traceback.format_exc()}')
        if startdir == destdir:  # full library scan
            if library == 'eBook':
                lazylibrarian.EBOOK_UPDATE = 0
            elif library == 'AudioBook':
                lazylibrarian.AUDIO_UPDATE = 0
        else:
            if authid:
                match = db.match('SELECT authorid from authors where authorid=?', (authid,))
                if match:
                    control_value_dict = {"AuthorID": authid}
                    new_value_dict = {"Status": "Active"}
                    db.upsert("authors", new_value_dict, control_value_dict)
    finally:
        logger.debug(f"Processed folders: {len(processed_subdirectories)}, "
                     f"matched books: {len(rehit)}, unmatched: {len(remiss)}")
        if '_SCAN' in threading.current_thread().name:
            threading.current_thread().name = 'WEBSERVER'
        db.close()
