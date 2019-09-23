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

import os
import re
import traceback
import shutil
from xml.etree import ElementTree
from lib.six import PY2

import lazylibrarian
from lazylibrarian import logger, database
from lazylibrarian.bookwork import setWorkPages
from lazylibrarian.bookrename import bookRename, audioProcess, id3read
from lazylibrarian.cache import cache_img, gr_xml_request
from lazylibrarian.common import opf_file, any_file
from lazylibrarian.formatter import plural, is_valid_isbn, is_valid_booktype, getList, unaccented, \
    cleanName, replace_all, split_title, now, makeUnicode, makeBytestr
from lazylibrarian.gb import GoogleBooks
from lazylibrarian.gr import GoodReads
from lazylibrarian.importer import update_totals, addAuthorNameToDB
from lib.fuzzywuzzy import fuzz
from lib.mobi import Mobi
# noinspection PyUnresolvedReferences
from lib.six.moves.urllib_parse import quote_plus, urlencode

try:
    from lib.tinytag import TinyTag
except ImportError:
    TinyTag = None

try:
    import zipfile
except ImportError:
    if PY2:
        import lib.zipfile as zipfile
    else:
        import lib3.zipfile as zipfile


def get_book_info(fname):
    # only handles epub, mobi, azw3 and opf for now,
    # for pdf see notes below
    res = {}
    extn = os.path.splitext(fname)[1]
    if not extn:
        return res

    if extn == ".mobi" or extn == ".azw3":
        res['type'] = extn[1:]
        try:
            book = Mobi(fname)
            book.parse()
        except Exception as e:
            logger.error('Unable to parse mobi in %s, %s %s' % (fname, type(e).__name__, str(e)))
            return res

        res['creator'] = makeUnicode(book.author())
        res['title'] = makeUnicode(book.title())
        res['language'] = makeUnicode(book.language())
        res['identifier'] = makeUnicode(book.isbn())
        return res

        # noinspection PyUnreachableCode
        """
                # none of the pdfs in my library had language,isbn
                # most didn't have author, or had the wrong author
                # (author set to publisher, or software used)
                # so probably not much point in looking at pdfs
                #
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
    elif extn == ".epub":
        res['type'] = "epub"

        # prepare to read from the .epub file
        try:
            zipdata = zipfile.ZipFile(fname)
        except Exception as e:
            logger.error('Unable to parse epub file %s, %s %s' % (fname, type(e).__name__, str(e)))
            return res

        # find the contents metafile
        txt = zipdata.read('META-INF/container.xml')
        try:
            tree = ElementTree.fromstring(txt)
        except Exception as e:
            logger.error("Error parsing metadata from epub zipfile: %s %s" % (type(e).__name__, str(e)))
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

    elif extn == ".opf":
        res['type'] = "opf"
        txt = open(fname).read()
        # sanitize any unmatched html tags or ElementTree won't parse
        dic = {'<br>': '', '</br>': ''}
        txt = replace_all(txt, dic)
    else:
        logger.error('Unhandled extension in get_book_info: %s' % extn)
        return res

    # repackage epub or opf metadata
    try:
        tree = ElementTree.fromstring(txt)
    except Exception as e:
        logger.error("Error parsing metadata from %s, %s %s" % (fname, type(e).__name__, str(e)))
        return res

    if not len(tree):
        return res
    n = 0
    while n < len(tree[0]):
        tag = str(tree[0][n].tag).lower()
        if '}' in tag:
            tag = tag.split('}')[1]
            txt = tree[0][n].text
            attrib = str(tree[0][n].attrib).lower()
            txt = makeUnicode(txt)
            if 'title' in tag:
                res['title'] = txt
            elif 'language' in tag:
                res['language'] = txt
            elif 'creator' in tag and 'creator' not in res:
                # take the first author name if multiple authors
                res['creator'] = txt
            elif 'identifier' in tag and 'isbn' in attrib:
                if is_valid_isbn(txt):
                    res['identifier'] = txt
            elif 'identifier' in tag and 'goodreads' in attrib:
                res['gr_id'] = txt
        n += 1
    return res


def find_book_in_db(author, book, ignored=None, library='eBook'):
    # Fuzzy search for book in library, return LL bookid and status if found or zero
    # prefer an exact match on author & book
    # prefer 'Have' if the user has marked the one they want
    # or one already marked 'Open' so we match the same one as before
    # or prefer not ignored over ignored
    logger.debug('Searching database for [%s] by [%s]' % (book, author))
    myDB = database.DBConnection()
    cmd = 'SELECT BookID,books.Status,AudioStatus FROM books,authors where books.AuthorID = authors.AuthorID'
    cmd += ' and AuthorName=? COLLATE NOCASE and BookName=? COLLATE NOCASE'
    res = myDB.select(cmd, (author, book))
    if library == 'eBook':
        whichstatus = 'Status'
    else:
        whichstatus = 'AudioStatus'
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
        logger.debug('Exact match [%s]' % book)
        return match['BookID'], match[whichstatus]
    else:
        # Try a more complex fuzzy match against each book in the db by this author
        # Using hard-coded ratios for now, maybe make ratios configurable in config.ini later
        cmd = 'SELECT BookID,BookName,BookISBN,books.Status,AudioStatus FROM books,authors'
        cmd += ' where books.AuthorID = authors.AuthorID '
        ign = ''
        if library == 'eBook':
            if ignored is True:
                cmd += 'and books.Status = "Ignored" '
                ign = 'ignored '
            elif ignored is False:
                cmd += 'and books.Status != "Ignored" '
        else:
            if ignored is True:
                cmd += 'and AudioStatus = "Ignored" '
                ign = 'ignored '
            elif ignored is False:
                cmd += 'and AudioStatus != "Ignored" '

        cmd += 'and AuthorName=? COLLATE NOCASE'
        books = myDB.select(cmd, (author,))
        best_ratio = 0
        best_partial = 0
        best_partname = 0
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

        dic = {u'\u2018': "", u'\u2019': "", u'\u201c': '', u'\u201d': '', "'": "", '"': ''}
        book_lower = unaccented(book.lower())
        book_lower = replace_all(book_lower, dic)
        book_partname, book_sub = split_title(author, book_lower)

        # We want to match a book on disk with a subtitle to a shorter book in the DB
        # - Strict prefix match with a : followed by junk is allowed
        # - Strict prefix match with a ()ed remainder is allowed
        # But the leading : is removed by has_clean_subtitle, so we allow all non (): subtitles
        has_clean_subtitle = re.search(r"^\s+([^:()]+|\([^)]+\))$", book_sub) is not None

        logger.debug('Searching %s %sbook%s by [%s] in database for [%s]' %
                     (len(books), ign, plural(len(books)), author, book))
        if lazylibrarian.LOGLEVEL & lazylibrarian.log_libsync:
            logger.debug('book partname [%s] book_sub [%s]' % (book_partname, book_sub))
        if book_partname == book_lower:
            book_partname = ''

        for a_book in books:
            # tidy up everything to raise fuzziness scores
            # still need to lowercase for matching against partial_name later on
            a_book_lower = unaccented(a_book['BookName'].lower())
            a_book_lower = replace_all(a_book_lower, dic)
            #
            # token sort ratio allows "Lord Of The Rings, The"   to match  "The Lord Of The Rings"
            ratio = fuzz.token_sort_ratio(book_lower, a_book_lower)
            if lazylibrarian.LOGLEVEL & lazylibrarian.log_fuzz:
                logger.debug("Ratio %s [%s][%s]" % (ratio, book_lower, a_book_lower))
            # partial ratio allows "Lord Of The Rings"   to match  "The Lord Of The Rings"
            partial = fuzz.partial_ratio(book_lower, a_book_lower)
            if lazylibrarian.LOGLEVEL & lazylibrarian.log_fuzz:
                logger.debug("PartialRatio %s [%s][%s]" % (partial, book_lower, a_book_lower))
            if book_partname:
                # partname allows "Lord Of The Rings (illustrated edition)"   to match  "The Lord Of The Rings"
                partname = fuzz.partial_ratio(book_partname, a_book_lower)
                if lazylibrarian.LOGLEVEL & lazylibrarian.log_fuzz:
                    logger.debug("PartName %s [%s][%s]" % (partname, book_partname, a_book_lower))

            # lose a point for each extra word in the fuzzy matches so we get the closest match
            # this should also stop us matching single books against omnibus editions
            words = len(getList(book_lower))
            words -= len(getList(a_book_lower))
            ratio -= abs(words)
            partial -= abs(words)
            partname -= abs(words)

            use_it = False
            if ratio > best_ratio:
                use_it = True
            elif ratio == best_ratio:
                if library == 'eBook' and a_book['Status'] == 'Have':
                    use_it = True
                if library != 'eBook' and a_book['AudioStatus'] == 'Have':
                    use_it = True
                if not use_it:
                    want_words = getList(book_lower)
                    best_words = getList(ratio_name.lower())
                    new_words = getList(a_book['BookName'].lower())
                    best_cnt = 0
                    new_cnt = 0
                    for word in want_words:
                        if word in best_words:
                            best_cnt += 1
                        if word in new_words:
                            new_cnt += 1
                    if new_cnt > best_cnt:
                        use_it = True
                if not use_it and best_type == 'Ignored':
                    if library == 'eBook' and a_book['Status'] != 'Ignored':
                        use_it = True
                    if library != 'eBook' and a_book['AudioStatus'] != 'Ignored':
                        use_it = True
            if use_it:
                best_ratio = ratio
                if library == 'eBook':
                    best_type = a_book['Status']
                else:
                    best_type = a_book['AudioStatus']
                ratio_name = a_book['BookName']
                ratio_id = a_book['BookID']

            use_it = False
            if partial > best_partial:
                use_it = True
            elif partial == best_partial:
                if library == 'eBook' and a_book['Status'] == 'Have':
                    use_it = True
                if library != 'eBook' and a_book['AudioStatus'] == 'Have':
                    use_it = True
                if not use_it:
                    want_words = getList(book_lower)
                    best_words = getList(partial_name.lower())
                    new_words = getList(a_book['BookName'].lower())
                    best_cnt = 0
                    new_cnt = 0
                    for word in want_words:
                        if word in best_words:
                            best_cnt += 1
                        if word in new_words:
                            new_cnt += 1
                    if new_cnt > best_cnt:
                        use_it = True
                if not use_it and partial_type == 'Ignored':
                    if library == 'eBook' and a_book['Status'] != 'Ignored':
                        use_it = True
                    if library != 'eBook' and a_book['AudioStatus'] != 'Ignored':
                        use_it = True
            if use_it:
                best_partial = partial
                if library == 'eBook':
                    partial_type = a_book['Status']
                else:
                    partial_type = a_book['AudioStatus']
                partial_name = a_book['BookName']
                partial_id = a_book['BookID']

            use_it = False
            if partname > best_partname:
                use_it = True
            elif partname == best_partname:
                if library == 'eBook' and a_book['Status'] == 'Have':
                    use_it = True
                if library != 'eBook' and a_book['AudioStatus'] == 'Have':
                    use_it = True
                if not use_it:
                    want_words = getList(book_lower)
                    best_words = getList(partname_name.lower())
                    new_words = getList(a_book['BookName'].lower())
                    best_cnt = 0
                    new_cnt = 0
                    for word in want_words:
                        if word in best_words:
                            best_cnt += 1
                        if word in new_words:
                            new_cnt += 1
                    if new_cnt > best_cnt:
                        use_it = True
                if not use_it and partname_type == 'Ignored':
                    if library == 'eBook' and a_book['Status'] != 'Ignored':
                        use_it = True
                    if library != 'eBook' and a_book['AudioStatus'] != 'Ignored':
                        use_it = True
            if use_it:
                best_partname = partname
                if library == 'eBook':
                    partname_type = a_book['Status']
                else:
                    partname_type = a_book['AudioStatus']
                partname_name = a_book['BookName']
                partname_id = a_book['BookID']

            if a_book_lower == book_partname and has_clean_subtitle:
                have_prefix = True
                if library == 'eBook':
                    prefix_type = a_book['Status']
                else:
                    prefix_type = a_book['Status']
                prefix_name = a_book['BookName']
                prefix_id = a_book['BookID']

        if best_ratio >= lazylibrarian.CONFIG['NAME_RATIO']:
            logger.debug("Fuzz match ratio [%d] [%s] [%s] %s" % (best_ratio, book, ratio_name, ratio_id))
            return ratio_id, best_type
        if best_partial >= lazylibrarian.CONFIG['NAME_PARTIAL']:
            logger.debug("Fuzz match partial [%d] [%s] [%s] %s" % (best_partial, book, partial_name, partial_id))
            return partial_id, partial_type
        if best_partname >= lazylibrarian.CONFIG['NAME_PARTNAME']:
            logger.debug("Fuzz match partname [%d] [%s] [%s] %s" % (best_partname, book, partname_name, partname_id))
            return partname_id, partname_type

        if have_prefix:
            logger.debug("Fuzz match prefix [%s] [%s] %s" % (book, prefix_name, prefix_id))
            return prefix_id, prefix_type

        if books:
            logger.debug(
                'Fuzz failed [%s - %s] ratio [%d,%s,%s], partial [%d,%s,%s], partname [%d,%s,%s]' %
                (author, book, best_ratio, ratio_name, ratio_id, best_partial, partial_name, partial_id,
                 best_partname, partname_name, partname_id))
        return 0, ''


def LibraryScan(startdir=None, library='eBook', authid=None, remove=True):
    """ Scan a directory tree adding new books into database
        Return how many books you added """

    destdir = lazylibrarian.DIRECTORY(library)
    if not startdir:
        if not destdir:
            logger.warn('Cannot find destination directory: %s. Not scanning' % destdir)
            return 0
        startdir = destdir

    if not os.path.isdir(startdir):
        logger.warn('Cannot find directory: %s. Not scanning' % startdir)
        return 0

    myDB = database.DBConnection()
    # noinspection PyBroadException
    try:
        # keep statistics of full library scans
        if startdir == destdir:
            lazylibrarian.AUTHORS_UPDATE = 1
            if library == 'eBook':
                lazylibrarian.EBOOK_UPDATE = 1
            elif library == 'AudioBook':
                lazylibrarian.AUDIO_UPDATE = 1
            myDB.action('DELETE from stats')
            try:  # remove any extra whitespace in authornames
                authors = myDB.select('SELECT AuthorID,AuthorName FROM authors WHERE AuthorName like "%  %"')
                if authors:
                    logger.info('Removing extra spaces from %s authorname%s' % (len(authors), plural(len(authors))))
                    for author in authors:
                        authorid = author["AuthorID"]
                        authorname = ' '.join(author['AuthorName'].split())
                        # Have we got author name both with-and-without extra spaces? If so, merge them
                        duplicate = myDB.match(
                            'Select AuthorID,AuthorName FROM authors WHERE AuthorName=?', (authorname,))
                        if duplicate:
                            myDB.action('DELETE from authors where authorname=?', (author['AuthorName'],))
                            if author['AuthorID'] != duplicate['AuthorID']:
                                myDB.action('UPDATE books set AuthorID=? WHERE AuthorID=?',
                                            (duplicate['AuthorID'], author['AuthorID']))
                        else:
                            myDB.action('UPDATE authors set AuthorName=? WHERE AuthorID=?', (authorname, authorid))
            except Exception as e:
                logger.error('%s %s' % (type(e).__name__, str(e)))
        else:
            if authid:
                match = myDB.match('SELECT authorid from authors where authorid=?', (authid,))
                if match:
                    controlValueDict = {"AuthorID": authid}
                    newValueDict = {"Status": "Loading"}
                    myDB.upsert("authors", newValueDict, controlValueDict)

        logger.info('Scanning %s directory: %s' % (library, startdir))
        new_book_count = 0
        modified_count = 0
        rescan_count = 0
        rescan_hits = 0
        file_count = 0

        # allow full_scan override so we can scan in alternate directories without deleting others
        if remove:
            if library == 'eBook':
                cmd = 'select AuthorName, BookName, BookFile, BookID from books,authors'
                cmd += ' where BookLibrary is not null and books.AuthorID = authors.AuthorID'
                if not startdir == destdir:
                    cmd += ' and BookFile like "' + startdir + '%"'
                books = myDB.select(cmd)
                status = lazylibrarian.CONFIG['NOTFOUND_STATUS']
                logger.info('Missing eBooks will be marked as %s' % status)
                for book in books:
                    bookfile = book['BookFile']

                    if bookfile and not os.path.isfile(bookfile):
                        myDB.action('update books set Status=?,BookFile="",BookLibrary="" where BookID=?',
                                    (status, book['BookID']))
                        logger.warn('eBook %s - %s updated as not found on disk' %
                                    (book['AuthorName'], book['BookName']))

            else:  # library == 'AudioBook':
                cmd = 'select AuthorName, BookName, AudioFile, BookID from books,authors'
                cmd += ' where AudioLibrary is not null and books.AuthorID = authors.AuthorID'
                if not startdir == destdir:
                    cmd += ' and AudioFile like "' + startdir + '%"'
                books = myDB.select(cmd)
                status = lazylibrarian.CONFIG['NOTFOUND_STATUS']
                logger.info('Missing AudioBooks will be marked as %s' % status)
                for book in books:
                    bookfile = book['AudioFile']

                    if bookfile and not os.path.isfile(bookfile):
                        myDB.action('update books set AudioStatus=?,AudioFile="",AudioLibrary="" where BookID=?',
                                    (status, book['BookID']))
                        logger.warn('Audiobook %s - %s updated as not found on disk' %
                                    (book['AuthorName'], book['BookName']))

        # to save repeat-scans of the same directory if it contains multiple formats of the same book,
        # keep track of which directories we've already looked at
        processed_subdirectories = []
        warned_no_new_authors = False  # only warn about the setting once
        matchString = ''
        for char in lazylibrarian.CONFIG['EBOOK_DEST_FILE']:
            matchString = matchString + '\\' + char
        # massage the EBOOK_DEST_FILE config parameter into something we can use
        # with regular expression matching
        booktypes = ''
        count = -1
        if library == 'eBook':
            booktype_list = getList(lazylibrarian.CONFIG['EBOOK_TYPE'])
        else:
            booktype_list = getList(lazylibrarian.CONFIG['AUDIOBOOK_TYPE'])
        for book_type in booktype_list:
            count += 1
            if count == 0:
                booktypes = book_type
            else:
                booktypes = booktypes + '|' + book_type

        matchString = matchString.replace("\\$\\A\\u\\t\\h\\o\\r", "(?P<author>.*?)").replace(
            "\\$\\T\\i\\t\\l\\e", "(?P<book>.*?)").replace(
            "\\$\\S\\e\\r\\i\\e\\s", "").replace(
            "\\$\\S\\e\\r\\N\\u\\m", "").replace(
            "\\$\\S\\e\\r\\N\\a\\m\\e", "").replace(
            "\\$\\$", "") + '\.[' + booktypes + ']'  # ignore any series, we just want author/title

        pattern = re.compile(matchString, re.VERBOSE)
        last_authorid = None
        # try to ensure startdir is str as os.walk can fail if it tries to convert a subdir or file
        # to utf-8 and fails (eg scandinavian characters in ascii 8bit)
        for rootdir, dirnames, filenames in os.walk(makeBytestr(startdir)):
            for directory in dirnames:
                # prevent magazine being scanned
                if PY2:
                    c = directory[0]
                    ignorefile = '.ll_ignore'
                else:
                    c = chr(directory[0])
                    ignorefile = b'.ll_ignore'
                if c in ["_", "."]:
                    logger.debug('Skipping %s' % os.path.join(rootdir, directory))
                    dirnames.remove(directory)
                    # ignore directories containing this special file
                elif os.path.exists(os.path.join(rootdir, directory, ignorefile)):
                    logger.debug('Found .ll_ignore file in %s' % os.path.join(rootdir, directory))
                    dirnames.remove(directory)

            rootdir = makeUnicode(rootdir)
            filenames = [makeUnicode(item) for item in filenames]

            for files in filenames:
                subdirectory = rootdir.replace(startdir, '')
                file_count += 1

                # Added new code to skip if we've done this directory before.
                # Made this conditional with a switch in config.ini
                # in case user keeps multiple different books in the same subdirectory
                if library == 'eBook' and lazylibrarian.CONFIG['IMP_SINGLEBOOK'] and \
                        (subdirectory in processed_subdirectories):
                    if lazylibrarian.LOGLEVEL & lazylibrarian.log_libsync:
                        logger.debug("[%s] already scanned" % subdirectory)
                elif library == 'AudioBook' and (subdirectory in processed_subdirectories):
                    if lazylibrarian.LOGLEVEL & lazylibrarian.log_libsync:
                        logger.debug("[%s] already scanned" % subdirectory)
                elif not os.path.isdir(rootdir):
                    logger.debug("[%s] missing (renamed?)" % rootdir)
                else:
                    # If this is a book, try to get author/title/isbn/language
                    # if epub or mobi, read metadata from the book
                    # If metadata.opf exists, use that allowing it to override
                    # embedded metadata. User may have edited metadata.opf
                    # to merge author aliases together
                    # If all else fails, try pattern match for author/title
                    # and look up isbn/lang from LT or GR later
                    match = 0
                    if (library == 'eBook' and is_valid_booktype(files, 'ebook')) or \
                            (library == 'AudioBook' and is_valid_booktype(files, 'audiobook')):

                        logger.debug("[%s] Now scanning subdirectory %s" % (startdir, subdirectory))

                        language = "Unknown"
                        isbn = ""
                        book = ""
                        author = ""
                        gr_id = ""
                        gb_id = ""
                        extn = os.path.splitext(files)[1]

                        # if it's an epub or a mobi we can try to read metadata from it
                        if extn in [".epub", ".mobi"]:
                            book_filename = os.path.join(rootdir, files)
                            if PY2:
                                book_filename = book_filename.encode(lazylibrarian.SYS_ENCODING)
                            try:
                                res = get_book_info(book_filename)
                            except Exception as e:
                                logger.error('get_book_info failed for %s, %s %s' %
                                             (book_filename, type(e).__name__, str(e)))
                                res = {}
                            # title and creator are the minimum we need
                            if 'title' in res and 'creator' in res:
                                book = res['title']
                                author = res['creator']
                                if author and book and len(book) > 2 and len(author) > 2:
                                    match = 1
                                if 'language' in res:
                                    language = res['language']
                                if 'identifier' in res:
                                    isbn = res['identifier']
                                if 'type' in res:
                                    extn = res['type']

                                logger.debug("book meta [%s] [%s] [%s] [%s] [%s]" %
                                             (isbn, language, author, book, extn))
                            if not match:
                                logger.debug("Book meta incomplete in %s" % book_filename)

                        # calibre uses "metadata.opf", LL uses "bookname - authorname.opf"
                        # just look for any .opf file in the current directory since we don't know
                        # LL preferred authorname/bookname at this point.
                        # Allow metadata in opf file to override book metadata as may be users pref
                        res = {}
                        metafile = ''
                        try:
                            metafile = opf_file(rootdir)
                            if metafile:
                                res = get_book_info(metafile)
                        except Exception as e:
                            logger.error('get_book_info failed for %s, %s %s' % (metafile, type(e).__name__, str(e)))

                        # title and creator are the minimum we need
                        if res and 'title' in res and 'creator' in res:
                            book = res['title']
                            author = res['creator']
                            author = author.strip()  # some audiobooks have fields of spaces
                            book = book.strip()
                            if author and book and len(book) > 2 and len(author) > 2:
                                match = 1
                            if 'language' in res:
                                language = res['language']
                            if 'identifier' in res:
                                isbn = res['identifier']
                            if 'gr_id' in res:
                                gr_id = res['gr_id']
                            logger.debug(
                                "file meta [%s] [%s] [%s] [%s] [%s]" % (isbn, language, author, book, gr_id))
                            if not match:
                                logger.debug("File meta incomplete in %s" % metafile)

                        if not match:
                            # no author/book from metadata file, and not embedded either
                            # or audiobook which may have id3 tags
                            if is_valid_booktype(files, 'audiobook'):
                                filename = os.path.join(rootdir, files)
                                if PY2:
                                    filename = filename.encode(lazylibrarian.SYS_ENCODING)
                                author, book = id3read(filename)
                                if author and book:
                                    match = True

                        # Failing anything better, just pattern match on filename
                        if not match:
                            # might need a different pattern match for audiobooks
                            # as they often seem to have xxChapter-Seriesnum Author Title
                            # but hopefully the tags will get there first...
                            match = pattern.match(files)
                            if match:
                                try:
                                    author = match.group("author")
                                except IndexError:
                                    author = ''
                                try:
                                    book = match.group("book")
                                except IndexError:
                                    book = ''

                                book = makeUnicode(book)
                                author = makeUnicode(author)
                                if len(book) > 2 and len(author) > 2:
                                    match = True
                                else:
                                    match = False
                            if not match:
                                logger.debug("Pattern match failed [%s]" % files)

                        if match:
                            # flag that we found a book in this subdirectory
                            if subdirectory:
                                processed_subdirectories.append(subdirectory)

                            # If we have a valid looking isbn, and language != "Unknown", add it to cache
                            if language != "Unknown" and is_valid_isbn(isbn):
                                logger.debug("Found Language [%s] ISBN [%s]" % (language, isbn))
                                # we need to add it to language cache if not already
                                # there, is_valid_isbn has checked length is 10 or 13
                                if len(isbn) == 10:
                                    isbnhead = isbn[0:3]
                                else:
                                    isbnhead = isbn[3:6]
                                match = myDB.match('SELECT lang FROM languages where isbn=?', (isbnhead,))
                                if not match:
                                    myDB.action('insert into languages values (?, ?)', (isbnhead, language))
                                    logger.debug("Cached Lang [%s] ISBN [%s]" % (language, isbnhead))
                                else:
                                    logger.debug("Already cached Lang [%s] ISBN [%s]" % (language, isbnhead))

                            newauthor, authorid, new = addAuthorNameToDB(author)  # get the author name as we know it...

                            if last_authorid and last_authorid != authorid:
                                update_totals(last_authorid)
                            last_authorid = authorid

                            if len(newauthor) and newauthor != author:
                                logger.debug("Preferred authorname changed from [%s] to [%s]" % (author, newauthor))
                                author = makeUnicode(newauthor)
                            if author:
                                # author exists, check if this book by this author is in our database
                                # metadata might have quotes in book name
                                # some books might be stored under a different author name
                                # eg books by multiple authors, books where author is "writing as"
                                # or books we moved to "merge" authors
                                # strip all ascii and non-ascii quotes/apostrophes
                                dic = {u'\u2018': "", u'\u2019': "", u'\u201c': '', u'\u201d': '', "'": "", '"': ''}
                                book = replace_all(book, dic)

                                # First try and find it under author and bookname
                                # as we may have it under a different bookid or isbn to goodreads/googlebooks
                                # which might have several bookid/isbn for the same book
                                bookid, mtype = find_book_in_db(author, book)
                                if bookid and mtype == "Ignored":
                                    logger.warn("Book %s by %s is marked Ignored in database, importing anyway" %
                                                (book, author))
                                if not bookid:
                                    # Title or author name might not match, or maybe multiple authors
                                    # See if the gr_id, gb_id is already in our database
                                    if gr_id:
                                        bookid = gr_id
                                    elif gb_id:
                                        bookid = gb_id

                                    if bookid:
                                        match = myDB.match('SELECT BookID FROM books where BookID=?', (bookid,))
                                        if not match:
                                            msg = 'Unable to find book %s by %s in database, trying to add it using '
                                            if bookid == gr_id:
                                                msg += "GoodReads ID " + gr_id
                                            if bookid == gb_id:
                                                msg += "GoogleBooks ID " + gb_id
                                            logger.debug(msg % (book, author))
                                            if lazylibrarian.CONFIG['BOOK_API'] == "GoodReads" and gr_id:
                                                GR_ID = GoodReads(gr_id)
                                                GR_ID.find_book(gr_id)
                                            elif lazylibrarian.CONFIG['BOOK_API'] == "GoogleBooks" and gb_id:
                                                GB_ID = GoogleBooks(gb_id)
                                                GB_ID.find_book(gb_id)
                                            # see if it's there now...
                                            match = myDB.match('SELECT BookID from books where BookID=?', (bookid,))
                                            if not match:
                                                logger.debug("Unable to add bookid %s to database" % bookid)
                                                bookid = ""

                                if not bookid and isbn:
                                    # See if the isbn is in our database
                                    match = myDB.match('SELECT BookID FROM books where BookIsbn=?', (isbn,))
                                    if match:
                                        bookid = match['BookID']

                                if not bookid:
                                    # get author name from parent directory of this book directory
                                    newauthor = os.path.basename(os.path.dirname(rootdir))
                                    newauthor = makeUnicode(newauthor)
                                    # calibre replaces trailing periods with _ eg Smith Jr. -> Smith Jr_
                                    if newauthor.endswith('_'):
                                        newauthor = newauthor[:-1] + '.'
                                    if author.lower() != newauthor.lower():
                                        logger.debug("Trying authorname [%s]" % newauthor)
                                        bookid, mtype = find_book_in_db(newauthor, book, ignored=False)
                                        if bookid and mtype == "Ignored":
                                            msg = "Book %s by %s is marked Ignored in database, importing anyway"
                                            logger.warn(msg % (book, newauthor))
                                        if bookid:
                                            logger.warn("%s not found under [%s], found under [%s]" %
                                                        (book, author, newauthor))

                                # at this point if we still have no bookid, it looks like we
                                # have author and book title but no database entry for it
                                if not bookid:
                                    if lazylibrarian.CONFIG['BOOK_API'] == "GoodReads":
                                        # Either goodreads doesn't have the book or it didn't match language prefs
                                        # or it's under a different author (pseudonym)
                                        # Since we have the book anyway, try and reload it
                                        rescan_count += 1
                                        base_url = 'https://www.goodreads.com/search.xml?q='
                                        params = {"key": lazylibrarian.CONFIG['GR_API']}
                                        if author[1] in '. ':
                                            surname = author
                                            forename = ''
                                            while surname and surname[1] in '. ':
                                                forename = forename + surname[0] + '.'
                                                surname = surname[2:].strip()
                                            if author != forename + ' ' + surname:
                                                logger.debug('Stripped authorname [%s] to [%s %s]' %
                                                             (author, forename, surname))
                                                author = forename + ' ' + surname

                                        author = ' '.join(author.split())  # ensure no extra whitespace

                                        searchname = author + ' ' + book
                                        searchname = cleanName(unaccented(searchname))
                                        if PY2:
                                            searchname = searchname.encode(lazylibrarian.SYS_ENCODING)
                                        searchterm = quote_plus(searchname)
                                        set_url = base_url + searchterm + '&' + urlencode(params)
                                        # noinspection PyBroadException
                                        try:
                                            rootxml, in_cache = gr_xml_request(set_url)
                                            if rootxml is None:
                                                logger.warn("Error requesting GoodReads for %s" % searchname)
                                                logger.debug(set_url)
                                            else:
                                                book, _ = split_title(author, book)
                                                dic = {u'\u2018': "", u'\u2019': "", u'\u201c': '', u'\u201d': '',
                                                       "'": "", '"': ''}
                                                book = replace_all(book, dic)
                                                resultxml = rootxml.getiterator('work')
                                                for item in resultxml:
                                                    try:
                                                        booktitle = item.find('./best_book/title').text
                                                        booktitle, _ = split_title(author, booktitle)
                                                        booktitle = replace_all(booktitle, dic)
                                                    except (KeyError, AttributeError):
                                                        booktitle = ""
                                                    book_fuzz = fuzz.token_set_ratio(booktitle, book)
                                                    if book_fuzz >= 98:
                                                        rescan_hits += 1
                                                        try:
                                                            bookid = item.find('./best_book/id').text
                                                        except (KeyError, AttributeError):
                                                            bookid = ""
                                                        logger.debug("Rescan found %s : %s: %s" %
                                                                     (booktitle, language, bookid))

                                                        if bookid:
                                                            cmd = 'SELECT * from books WHERE BookID=?'
                                                            check_status = myDB.match(cmd, (bookid,))
                                                            if check_status:
                                                                logger.debug("%s matched on rescan for %s" %
                                                                             (bookid, booktitle))
                                                            else:
                                                                logger.debug("Adding %s on rescan for %s" %
                                                                             (bookid, booktitle))
                                                                GR_ID = GoodReads(bookid)
                                                                GR_ID.find_book(bookid)
                                                                if language and language != "Unknown":
                                                                    # set language from book metadata
                                                                    logger.debug(
                                                                        "Setting language from metadata %s : %s" % (
                                                                            booktitle, language))
                                                                    myDB.action(
                                                                        'UPDATE books SET BookLang=? WHERE BookID=?',
                                                                        (language, bookid))
                                                            break
                                                if not bookid:
                                                    logger.warn("GoodReads doesn't know about %s" % book)
                                        except Exception:
                                            logger.error('Error finding rescan results: %s' % traceback.format_exc())
                                    elif lazylibrarian.CONFIG['BOOK_API'] == "GoogleBooks":
                                        # if we get here using googlebooks it's because googlebooks
                                        # doesn't have the book. No point in looking for it again.
                                        logger.warn("GoogleBooks doesn't know about %s" % book)

                                # see if it's there now...
                                if bookid:
                                    cmd = 'SELECT books.Status, AudioStatus, BookFile, AudioFile, AuthorName, BookName'
                                    cmd += ' from books,authors where books.AuthorID = authors.AuthorID'
                                    cmd += ' and BookID=?'
                                    check_status = myDB.match(cmd, (bookid,))

                                    if not check_status:
                                        logger.debug('Unable to find bookid %s in database' % bookid)
                                    else:
                                        book_filename = None
                                        if library == 'eBook':
                                            if check_status['Status'] != 'Open':
                                                # we found a new book
                                                new_book_count += 1
                                                myDB.action(
                                                    'UPDATE books set Status=?, BookLibrary=? where BookID=?',
                                                    (lazylibrarian.CONFIG['FOUND_STATUS'], now(), bookid))

                                            # check and store book location so we can check if it gets (re)moved
                                            book_filename = os.path.join(rootdir, files)

                                            book_basename = os.path.splitext(book_filename)[0]
                                            booktype_list = getList(lazylibrarian.CONFIG['EBOOK_TYPE'])
                                            for book_type in booktype_list:
                                                preferred_type = "%s.%s" % (book_basename, book_type)
                                                if os.path.exists(preferred_type):
                                                    book_filename = preferred_type
                                                    logger.debug("Librarysync link to preferred type %s: %s" %
                                                                 (book_type, book_filename))
                                                    break

                                            myDB.action('UPDATE books set BookFile=? where BookID=?',
                                                        (book_filename, bookid))

                                            if lazylibrarian.CONFIG['IMP_RENAME']:
                                                book_filename = bookRename(bookid)

                                            # location may have changed on rename
                                            if book_filename and book_filename != check_status['BookFile']:
                                                if check_status['BookFile'] and check_status['BookFile'] != 'None':
                                                    modified_count += 1
                                                    logger.warn("Updating book location for %s %s from %s to %s" %
                                                                (author, book, check_status['BookFile'], book_filename))
                                                logger.debug("%s %s matched %s BookID %s, [%s][%s]" %
                                                             (author, book, check_status['Status'], bookid,
                                                              check_status['AuthorName'], check_status['BookName']))
                                                myDB.action('UPDATE books set BookFile=? where BookID=?',
                                                            (book_filename, bookid))

                                        elif library == 'AudioBook':
                                            if check_status['AudioStatus'] != 'Open':
                                                # we found a new audiobook
                                                new_book_count += 1
                                                myDB.action(
                                                    'UPDATE books set AudioStatus=?, AudioLibrary=? where BookID=?',
                                                    (lazylibrarian.CONFIG['FOUND_STATUS'], now(), bookid))

                                            # store audiobook location so we can check if it gets (re)moved
                                            book_filename = os.path.join(rootdir, files)
                                            # link to the first part of multi-part audiobooks
                                            tokmatch = ''
                                            for token in [' 001.', ' 01.', ' 1.', ' 001 ', ' 01 ', ' 1 ', '01']:
                                                if tokmatch:
                                                    break
                                                for e in os.listdir(makeBytestr(rootdir)):
                                                    e = makeUnicode(e)
                                                    if is_valid_booktype(e, booktype='audiobook') and token in e:
                                                        book_filename = os.path.join(rootdir, e)
                                                        logger.debug("Librarysync link to preferred part %s: %s" %
                                                                     (token, book_filename))
                                                        tokmatch = token
                                                        break

                                            myDB.action('UPDATE books set AudioFile=? where BookID=?',
                                                        (book_filename, bookid))

                                            if lazylibrarian.CONFIG['AUDIOBOOK_DEST_FILE']:
                                                if lazylibrarian.CONFIG['IMP_RENAME']:
                                                    book_filename = audioProcess(bookid, rename=True, playlist=True)
                                                else:
                                                    book_filename = audioProcess(bookid, rename=False, playlist=True)

                                            # location may have changed since last scan
                                            if book_filename and book_filename != check_status['AudioFile']:
                                                if check_status['AudioFile'] and \
                                                        str(check_status['AudioFile']) != 'None':
                                                    modified_count += 1
                                                    logger.warn("Updating audiobook location for %s %s from %s to %s" %
                                                                (author, book, check_status['AudioFile'],
                                                                 book_filename))
                                                logger.debug("%s %s matched %s BookID %s, [%s][%s]" %
                                                             (author, book, check_status['AudioStatus'], bookid,
                                                              check_status['AuthorName'], check_status['BookName']))
                                                myDB.action('UPDATE books set AudioFile=? where BookID=?',
                                                            (book_filename, bookid))

                                        # update cover file to any .jpg in book folder, prefer cover.jpg
                                        if book_filename:
                                            bookdir = os.path.dirname(book_filename)
                                            cachedir = lazylibrarian.CACHEDIR
                                            cacheimg = os.path.join(cachedir, 'book', bookid + '.jpg')
                                            coverimg = os.path.join(bookdir, 'cover.jpg')
                                            if not os.path.isfile(coverimg):
                                                coverimg = any_file(bookdir, '.jpg')
                                            if coverimg:
                                                shutil.copyfile(coverimg, cacheimg)
                                else:
                                    if library == 'eBook':
                                        logger.warn(
                                            "Failed to match book [%s] by [%s] in database" % (book, author))
                                    else:
                                        logger.warn(
                                            "Failed to match audiobook [%s] by [%s] in database" % (book, author))
                            else:
                                if not warned_no_new_authors and not lazylibrarian.CONFIG['ADD_AUTHOR']:
                                    logger.warn("Add authors to database is disabled")
                                    warned_no_new_authors = True

        if last_authorid:
            update_totals(last_authorid)

        logger.info("%s/%s new/modified %s%s found and added to the database" %
                    (new_book_count, modified_count, library, plural(new_book_count + modified_count)))
        logger.info("%s file%s processed" % (file_count, plural(file_count)))

        if startdir == destdir:
            # On full library scans, check for missing workpages
            setWorkPages()
            # and books with unknown language
            nolang = myDB.match(
                "select count(*) as counter from Books where status='Open' and BookLang='Unknown'")
            nolang = nolang['counter']
            if nolang:
                logger.warn("Found %s book%s in your library with unknown language" % (nolang, plural(nolang)))
                # show stats if new books were added
            cmd = "SELECT sum(GR_book_hits), sum(GR_lang_hits), sum(LT_lang_hits), sum(GB_lang_change), "
            cmd += "sum(cache_hits), sum(bad_lang), sum(bad_char), sum(uncached), sum(duplicates) FROM stats"
            stats = myDB.match(cmd)

            st = {'GR_book_hits': stats['sum(GR_book_hits)'], 'GB_book_hits': stats['sum(GR_book_hits)'],
                  'GR_lang_hits': stats['sum(GR_lang_hits)'], 'LT_lang_hits': stats['sum(LT_lang_hits)'],
                  'GB_lang_change': stats['sum(GB_lang_change)'], 'cache_hits': stats['sum(cache_hits)'],
                  'bad_lang': stats['sum(bad_lang)'], 'bad_char': stats['sum(bad_char)'],
                  'uncached': stats['sum(uncached)'], 'duplicates': stats['sum(duplicates)']}

            # noinspection PyUnresolvedReferences
            for item in list(st.keys()):
                if st[item] is None:
                    st[item] = 0

            if lazylibrarian.CONFIG['BOOK_API'] == "GoogleBooks":
                logger.debug("GoogleBooks was hit %s time%s for books" %
                             (st['GR_book_hits'], plural(st['GR_book_hits'])))
                logger.debug("GoogleBooks language was changed %s time%s" %
                             (st['GB_lang_change'], plural(st['GB_lang_change'])))
            if lazylibrarian.CONFIG['BOOK_API'] == "GoodReads":
                logger.debug("GoodReads was hit %s time%s for books" %
                             (st['GR_book_hits'], plural(st['GR_book_hits'])))
                logger.debug("GoodReads was hit %s time%s for languages" %
                             (st['GR_lang_hits'], plural(st['GR_lang_hits'])))
            logger.debug("LibraryThing was hit %s time%s for languages" %
                         (st['LT_lang_hits'], plural(st['LT_lang_hits'])))
            logger.debug("Language cache was hit %s time%s" %
                         (st['cache_hits'], plural(st['cache_hits'])))
            logger.debug("Unwanted language removed %s book%s" %
                         (st['bad_lang'], plural(st['bad_lang'])))
            logger.debug("Invalid/Incomplete removed %s book%s" %
                         (st['bad_char'], plural(st['bad_char'])))
            logger.debug("Unable to cache language for %s book%s with missing ISBN" %
                         (st['uncached'], plural(st['uncached'])))
            logger.debug("Found %s duplicate book%s" %
                         (st['duplicates'], plural(st['duplicates'])))
            logger.debug("Rescan %s hit%s, %s miss" %
                         (rescan_hits, plural(rescan_hits), rescan_count - rescan_hits))
            logger.debug("Cache %s hit%s, %s miss" %
                         (lazylibrarian.CACHE_HIT, plural(lazylibrarian.CACHE_HIT), lazylibrarian.CACHE_MISS))
            cachesize = myDB.match("select count(*) as counter from languages")
            logger.debug("ISBN Language cache holds %s entries" % cachesize['counter'])

            # Cache any covers and images
            images = myDB.select('select bookid, bookimg, bookname from books where bookimg like "http%"')
            if len(images):
                logger.info("Caching cover%s for %i book%s" % (plural(len(images)), len(images), plural(len(images))))
                for item in images:
                    bookid = item['bookid']
                    bookimg = item['bookimg']
                    # bookname = item['bookname']
                    newimg, success, _ = cache_img("book", bookid, bookimg)
                    if success:
                        myDB.action('update books set BookImg=? where BookID=?', (newimg, bookid))

            images = myDB.select('select AuthorID, AuthorImg, AuthorName from authors where AuthorImg like "http%"')
            if len(images):
                logger.info("Caching image%s for %i author%s" % (plural(len(images)), len(images), plural(len(images))))
                for item in images:
                    authorid = item['authorid']
                    authorimg = item['authorimg']
                    # authorname = item['authorname']
                    newimg, success, _ = cache_img("author", authorid, authorimg)
                    if success:
                        myDB.action('update authors set AuthorImg=? where AuthorID=?', (newimg, authorid))

            if library == 'eBook':
                lazylibrarian.EBOOK_UPDATE = 0
            elif library == 'AudioBook':
                lazylibrarian.AUDIO_UPDATE = 0
            lazylibrarian.AUTHORS_UPDATE = 0
        else:
            if authid:
                match = myDB.match('SELECT authorid from authors where authorid=?', (authid,))
                if match:
                    controlValueDict = {"AuthorID": authid}
                    newValueDict = {"Status": "Active"}
                    myDB.upsert("authors", newValueDict, controlValueDict)
                    # On single author/book import, just update bookcount for that author
                    update_totals(authid)

        # logger.debug('Updating bookcounts for %i author%s' % (len(authors), plural(len(authors))))
        # for author in authors:
        #     update_totals(author['AuthorID'])

        logger.info('Library scan complete')
        return new_book_count

    except Exception:
        logger.error('Unhandled exception in libraryScan: %s' % traceback.format_exc())
        if startdir == destdir:  # full library scan
            if library == 'eBook':
                lazylibrarian.EBOOK_UPDATE = 0
            elif library == 'AudioBook':
                lazylibrarian.AUDIO_UPDATE = 0
        else:
            if authid:
                match = myDB.match('SELECT authorid from authors where authorid=?', (authid,))
                if match:
                    controlValueDict = {"AuthorID": authid}
                    newValueDict = {"Status": "Active"}
                    myDB.upsert("authors", newValueDict, controlValueDict)
