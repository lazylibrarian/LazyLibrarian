import os
import lib.csv as csv
import lazylibrarian

from lazylibrarian import database, logger
from lazylibrarian.formatter import plural, is_valid_isbn, now
from lazylibrarian.importer import addAuthorToDB
from lazylibrarian.common import csv_file
from lazylibrarian.librarysync import find_book_in_db


def export_CSV(search_dir=None, status="Wanted"):
    """ Write a csv file to the search_dir containing all books marked as "Wanted" """

    if not search_dir or os.path.isdir(search_dir) is False:
        logger.warn("Please check Alternate Directory setting")
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
                count = count + 1
        logger.info(u"CSV exported %s book%s to %s" % (count, plural(count), csvFile))


def import_CSV(search_dir=None):
    """ Find a csv file in the search_dir and process all the books in it,
    adding authors to the database if not found, and marking the books as "Wanted" """

    if not search_dir or os.path.isdir(search_dir) is False:
        logger.warn(u"Please check Alternate Directory setting")
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
                # by taking a slice from item 1  as we don't need the very first header.
                headers = row[1:]
            else:
                # Otherwise, the key in the content dictionary is the first item in the
                # row and we can create the sub-dictionary by using the zip() function.
                content[row[0]] = dict(zip(headers, row[1:]))

        # We can now get to the content by using the resulting dictionary, so to see
        # the list of lines, we can do:
        # print content.keys() # to get a list of bookIDs
        # To see the list of fields available for each book
        # print headers

        if 'Author' not in headers or 'Title' not in headers:
            logger.warn(u'Invalid CSV file found %s' % csvFile)
            return

        myDB = database.DBConnection()
        bookcount = 0
        authcount = 0
        skipcount = 0
        logger.debug(u"CSV: Found %s book%s in csv file" % (len(content.keys()), plural(len(content.keys()))))
        for bookid in content.keys():
            authorname = content[bookid]['Author']
            if hasattr(authorname, 'decode'):
                authorname = authorname.decode(lazylibrarian.SYS_ENCODING)

            authmatch = myDB.action('SELECT * FROM authors where AuthorName="%s"' % (authorname)).fetchone()

            if authmatch:
                logger.debug(u"CSV: Author %s found in database" % (authorname))
            else:
                logger.debug(u"CSV: Author %s not found, adding to database" % (authorname))
                addAuthorToDB(authorname)
                authcount = authcount + 1

            bookmatch = 0
            isbn10 = ""
            isbn13 = ""
            bookname = content[bookid]['Title']
            if hasattr(bookname, 'decode'):
                bookname = bookname.decode(lazylibrarian.SYS_ENCODING)
            if 'ISBN' in headers:
                isbn10 = content[bookid]['ISBN']
            if 'ISBN13' in headers:
                isbn13 = content[bookid]['ISBN13']

            # try to find book in our database using isbn, or if that fails, name matching
            if is_valid_isbn(isbn10):
                bookmatch = myDB.action('SELECT * FROM books where Bookisbn=%s' % (isbn10)).fetchone()
            if not bookmatch:
                if is_valid_isbn(isbn13):
                    bookmatch = myDB.action('SELECT * FROM books where BookIsbn=%s' % (isbn13)).fetchone()
            if not bookmatch:
                bookid = find_book_in_db(myDB, authorname, bookname)
                if bookid:
                    bookmatch = myDB.action('SELECT * FROM books where BookID="%s"' % (bookid)).fetchone()
            if bookmatch:
                authorname = bookmatch['AuthorName']
                bookname = bookmatch['BookName']
                bookid = bookmatch['BookID']
                bookstatus = bookmatch['Status']
                if bookstatus == 'Open' or bookstatus == 'Wanted' or bookstatus == 'Have':
                    logger.info(u'Found book %s by %s, already marked as "%s"' % (bookname, authorname, bookstatus))
                else:  # skipped/ignored
                    logger.info(u'Found book %s by %s, marking as "Wanted"' % (bookname, authorname))
                    controlValueDict = {"BookID": bookid}
                    newValueDict = {"Status": "Wanted"}
                    myDB.upsert("books", newValueDict, controlValueDict)
                    bookcount = bookcount + 1
            else:
                logger.warn(u"Skipping book %s by %s, not found in database" % (bookname, authorname))
                skipcount = skipcount + 1
        logger.info(u"Added %i new author%s, marked %i book%s as 'Wanted', %i book%s not found" %
                    (authcount, plural(authcount), bookcount, plural(bookcount), skipcount, plural(skipcount)))
