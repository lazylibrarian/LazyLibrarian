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

import os
import traceback

import lazylibrarian
import lib.csv as csv
from lazylibrarian import database, logger
from lazylibrarian.common import csv_file
from lazylibrarian.formatter import plural, is_valid_isbn, now
from lazylibrarian.importer import addAuthorToDB
from lazylibrarian.librarysync import find_book_in_db


def export_CSV(search_dir=None, status="Wanted"):
    """ Write a csv file to the search_dir containing all books marked as "Wanted" """
    try:
        if not search_dir:
            logger.warn("Alternate Directory not configured")
            return False
        elif not os.path.isdir(search_dir):
            logger.warn("Alternate Directory [%s] not found" % search_dir)
            return False
        elif not os.access(search_dir, os.W_OK | os.X_OK):
            logger.warn("Alternate Directory [%s] not writable" % search_dir)
            return False

        csvFile = os.path.join(search_dir, "%s - %s.csv" % (status, now().replace(':', '-')))

        myDB = database.DBConnection()

        find_status = myDB.select('SELECT * FROM books WHERE Status = "%s"' % status)

        if not find_status:
            logger.warn(u"No books marked as %s" % status)
        else:
            count = 0
            with open(csvFile, 'wb') as csvfile:
                csvwrite = csv.writer(csvfile, delimiter=',',
                                      quotechar='"', quoting=csv.QUOTE_MINIMAL)

                # write headers, change AuthorName BookName BookIsbn to match import csv names (Author, Title, ISBN10)
                csvwrite.writerow(['BookID', 'Author', 'Title', 'ISBN', 'AuthorID'])

                for resulted in find_status:
                    logger.debug(u"Exported CSV for book %s" % resulted['BookName'])
                    row = ([resulted['BookID'], resulted['AuthorName'], resulted['BookName'],
                            resulted['BookIsbn'], resulted['AuthorID']])
                    csvwrite.writerow([("%s" % s).encode(lazylibrarian.SYS_ENCODING) for s in row])
                    count += 1
            logger.info(u"CSV exported %s book%s to %s" % (count, plural(count), csvFile))
    except Exception:
        logger.error('Unhandled exception in exportCSV: %s' % traceback.format_exc())


def finditem(item, headers):
    """
    Try to find book matching the csv item in the database
    Return database entry, or False if not found
    """
    myDB = database.DBConnection()
    bookmatch = ""
    isbn10 = ""
    isbn13 = ""
    bookid = ""
    bookname = item['Title']
    authorname = item['Author']
    if isinstance(authorname, str):
        authorname = authorname.decode(lazylibrarian.SYS_ENCODING)
    if isinstance(bookname, str):
        bookname = bookname.decode(lazylibrarian.SYS_ENCODING)
    if 'ISBN' in headers:
        isbn10 = item['ISBN']
    if 'ISBN13' in headers:
        isbn13 = item['ISBN13']
    if 'BookID' in headers:
        bookid = item['BookID']

    # try to find book in our database using bookid or isbn, or if that fails, name matching
    if bookid:
        bookmatch = myDB.match('SELECT * FROM books where BookID=%s' % bookid)
    if not bookmatch:
        if is_valid_isbn(isbn10):
            bookmatch = myDB.match('SELECT * FROM books where BookIsbn=%s' % isbn10)
    if not bookmatch:
        if is_valid_isbn(isbn13):
            bookmatch = myDB.match('SELECT * FROM books where BookIsbn=%s' % isbn13)
    if not bookmatch:
        bookid = find_book_in_db(myDB, authorname, bookname)
        if bookid:
            bookmatch = myDB.match('SELECT * FROM books where BookID="%s"' % bookid)
    return bookmatch


# noinspection PyTypeChecker
def import_CSV(search_dir=None):
    """ Find a csv file in the search_dir and process all the books in it,
        adding authors to the database if not found
        and marking the books as "Wanted"
    """
    try:
        if not search_dir:
            logger.warn("Alternate Directory not configured")
            return False
        elif not os.path.isdir(search_dir):
            logger.warn("Alternate Directory [%s] not found" % search_dir)
            return False

        csvFile = csv_file(search_dir)

        headers = None
        content = {}

        if not csvFile:
            logger.warn(u"No CSV file found in %s" % search_dir)
        else:
            logger.debug(u'Reading file %s' % csvFile)
            reader = csv.reader(open(csvFile))
            for row in reader:
                if reader.line_num == 1:
                    # If we are on the first line, create the headers list from the first row
                    headers = row
                else:
                    # Otherwise, the key in the content dictionary is the first item in the
                    # row and we can create the sub-dictionary by using the zip() function.
                    # we include the key in the dictionary as our exported csv files use
                    # bookid as the key
                    content[row[0]] = dict(zip(headers, row))

            # We can now get to the content by using the resulting dictionary, so to see
            # the list of lines, we can do: print content.keys()  to get a list of keys
            # To see the list of fields available for each book:  print headers

            if 'Author' not in headers or 'Title' not in headers:
                logger.warn(u'Invalid CSV file found %s' % csvFile)
                return

            myDB = database.DBConnection()
            bookcount = 0
            authcount = 0
            skipcount = 0
            logger.debug(u"CSV: Found %s book%s in csv file" % (len(content.keys()), plural(len(content.keys()))))
            for item in content.keys():
                authorname = content[item]['Author']
                if isinstance(authorname, str):
                    authorname = authorname.decode(lazylibrarian.SYS_ENCODING)

                authmatch = myDB.match('SELECT * FROM authors where AuthorName="%s"' % authorname)

                if authmatch:
                    newauthor = False
                    logger.debug(u"CSV: Author %s found in database" % authorname)
                else:
                    newauthor = True
                    logger.debug(u"CSV: Author %s not found, adding to database" % authorname)
                    addAuthorToDB(authorname, False)
                    authcount += 1

                bookmatch = finditem(content[item], headers)

                # if we didn't find it, maybe author info is stale
                if not bookmatch and not newauthor:
                    addAuthorToDB(authorname, True)
                    bookmatch = finditem(content[item], headers)

                bookname = ''
                if bookmatch:
                    authorname = bookmatch['AuthorName']
                    # noinspection PyTypeChecker
                    bookname = bookmatch['BookName']
                    # noinspection PyTypeChecker
                    bookid = bookmatch['BookID']
                    # noinspection PyTypeChecker
                    bookstatus = bookmatch['Status']
                    if bookstatus == 'Open' or bookstatus == 'Wanted' or bookstatus == 'Have':
                        logger.info(u'Found book %s by %s, already marked as "%s"' % (bookname, authorname, bookstatus))
                    else:  # skipped/ignored
                        logger.info(u'Found book %s by %s, marking as "Wanted"' % (bookname, authorname))
                        controlValueDict = {"BookID": bookid}
                        newValueDict = {"Status": "Wanted"}
                        myDB.upsert("books", newValueDict, controlValueDict)
                        bookcount += 1
                else:
                    logger.warn(u"Skipping book %s by %s, not found in database" % (bookname, authorname))
                    skipcount += 1
            logger.info(u"Added %i new author%s, marked %i book%s as 'Wanted', %i book%s not found" %
                        (authcount, plural(authcount), bookcount, plural(bookcount), skipcount, plural(skipcount)))
    except Exception:
        logger.error('Unhandled exception in importCSV: %s' % traceback.format_exc())
