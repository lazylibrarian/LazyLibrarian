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

from __future__ import with_statement

import os
import shutil
import threading
import traceback

import lazylibrarian
from lazylibrarian import logger, database, magazinescan, bookwork
from lazylibrarian.bookwork import getWorkSeries, setSeries
from lazylibrarian.common import restartJobs
from lazylibrarian.formatter import plural, bookSeries, cleanName, unaccented

def upgrade_needed():
    """
    Check if database needs upgrading
    Return zero if up-to-date
    Return current version if needs upgrade
    """

    myDB = database.DBConnection()
    # Had a report of "index out of range", can't replicate it.
    # Maybe on some versions of sqlite an unset user_version
    # or unsupported pragma gives an empty result?
    db_version = 0
    result = myDB.match('PRAGMA user_version')
    if result and result[0]:
        value = str(result[0])
        if value.isdigit():
            db_version = int(value)

    # database version history:
    # 0 original version or new empty database
    # 1 changes up to June 2016
    # 2 removed " MB" from nzbsize field in wanted table
    # 3 removed SeriesOrder column from books table as redundant
    # 4 added duplicates column to stats table
    # 5 issue numbers padded to 4 digits with leading zeros
    # 6 added Manual field to books table for user editing
    # 7 added Source and DownloadID to wanted table for download monitoring
    # 8 move image cache from data/images/cache into datadir
    # 9 add regex to magazine table
    # 10 check for missing columns in pastissues table
    # 11 Keep most recent book image in author table
    # 12 Keep latest issue cover in magazine table
    # 13 add Manual column to author table for user editing
    # 14 separate book and author images in case id numbers collide
    # 15 move series and seriesnum into separate tables so book can appear in multiple series
    # 16 remove series, authorlink, authorname columns from book table, only in series/author tables now
    # 17 remove authorid from series table, new seriesauthor table to allow multiple authors per series

    db_current_version = 17
    if db_version < db_current_version:
        return db_current_version
    return 0


def has_column(myDB, table, column):
    columns = myDB.select('PRAGMA table_info(%s)' % table)
    if not columns:  # no such table
        return False
    for item in columns:
        if item[1] == column:
            return True
    # no such column
    return False


def dbupgrade(db_current_version):
  try:
    myDB = database.DBConnection()
    db_version = 0
    result = myDB.match('PRAGMA user_version')
    if result and result[0]:
        value = str(result[0])
        if value.isdigit():
            db_version = int(value)

    check = myDB.match('PRAGMA integrity_check')
    if check and check[0]:
        result = check[0]
        if result == 'ok':
            logger.debug('Database integrity check: %s' % result)
        else:
            logger.error('Database integrity check: %s' % result)
            # should probably abort now

    if db_version < db_current_version:
        lazylibrarian.UPDATE_MSG = 'Updating database to version %s, current version is %s' % (
            db_current_version, db_version)
        logger.info(lazylibrarian.UPDATE_MSG)
        myDB = database.DBConnection()

        if db_version < 1:
            myDB.action('CREATE TABLE IF NOT EXISTS authors (AuthorID TEXT UNIQUE, AuthorName TEXT UNIQUE, \
                AuthorImg TEXT, AuthorLink TEXT, DateAdded TEXT, Status TEXT, LastBook TEXT, LastBookImg TEXT, \
                LastLink Text, LastDate TEXT,  HaveBooks INTEGER, TotalBooks INTEGER, AuthorBorn TEXT, \
                AuthorDeath TEXT, UnignoredBooks INTEGER, Manual TEXT)')
            myDB.action('CREATE TABLE IF NOT EXISTS books (AuthorID TEXT, \
                BookName TEXT, BookSub TEXT, BookDesc TEXT, BookGenre TEXT, BookIsbn TEXT, BookPub TEXT, \
                BookRate INTEGER, BookImg TEXT, BookPages INTEGER, BookLink TEXT, BookID TEXT UNIQUE, BookFile TEXT, \
                BookDate TEXT, BookLang TEXT, BookAdded TEXT, Status TEXT, WorkPage TEXT, Manual TEXT)')
            myDB.action('CREATE TABLE IF NOT EXISTS wanted (BookID TEXT, NZBurl TEXT, NZBtitle TEXT, NZBdate TEXT, \
                NZBprov TEXT, Status TEXT, NZBsize TEXT, AuxInfo TEXT, NZBmode TEXT, Source TEXT, DownloadID TEXT)')
            myDB.action('CREATE TABLE IF NOT EXISTS pastissues AS SELECT * FROM wanted WHERE 0')  # same columns
            myDB.action('CREATE TABLE IF NOT EXISTS magazines (Title TEXT UNIQUE, Regex TEXT, Status TEXT, \
                MagazineAdded TEXT, LastAcquired TEXT, IssueDate TEXT, IssueStatus TEXT, Reject TEXT, \
                LatestCover TEXT)')
            myDB.action('CREATE TABLE IF NOT EXISTS languages (isbn TEXT, lang TEXT)')
            myDB.action('CREATE TABLE IF NOT EXISTS issues (Title TEXT, IssueID TEXT UNIQUE, IssueAcquired TEXT, \
                IssueDate TEXT, IssueFile TEXT)')
            myDB.action('CREATE TABLE IF NOT EXISTS stats (authorname text, GR_book_hits int, GR_lang_hits int, \
                LT_lang_hits int, GB_lang_change, cache_hits int, bad_lang int, bad_char int, uncached int, \
                duplicates int)')
            myDB.action('CREATE TABLE IF NOT EXISTS series (SeriesID INTEGER PRIMARY KEY, SeriesName TEXT, \
                Status TEXT)')
            myDB.action('CREATE TABLE IF NOT EXISTS member (SeriesID INTEGER, BookID TEXT, SeriesNum TEXT)')
            myDB.action('CREATE TABLE IF NOT EXISTS seriesauthors (SeriesID INTEGER, AuthorID TEXT)')


            # These are the incremental changes before database versioning was introduced.
            # New database tables should already have these incorporated so we need to check first...

            if not has_column(myDB, "books", "BookSub"):
                lazylibrarian.UPDATE_MSG = 'Updating database to hold book subtitles.'
                logger.debug(lazylibrarian.UPDATE_MSG)
                myDB.action('ALTER TABLE books ADD COLUMN BookSub TEXT')

            if not has_column(myDB, "books", "BookSub"):
                lazylibrarian.UPDATE_MSG = 'Updating database to hold book publisher'
                logger.debug(lazylibrarian.UPDATE_MSG)
                myDB.action('ALTER TABLE books ADD COLUMN BookPub TEXT')

            if not has_column(myDB, "books", "BookGenre"):
                lazylibrarian.UPDATE_MSG = 'Updating database to hold bookgenre'
                logger.debug(lazylibrarian.UPDATE_MSG)
                myDB.action('ALTER TABLE books ADD COLUMN BookGenre TEXT')

            if not has_column(myDB, "books", "BookFile"):
                lazylibrarian.UPDATE_MSG = 'Updating database to hold book filename'
                logger.debug(lazylibrarian.UPDATE_MSG)
                myDB.action('ALTER TABLE books ADD COLUMN BookFile TEXT')

            if not has_column(myDB, "wanted", "AuxInfo"):
                lazylibrarian.UPDATE_MSG = 'Updating database to hold AuxInfo'
                logger.debug(lazylibrarian.UPDATE_MSG)
                myDB.action('ALTER TABLE wanted ADD COLUMN AuxInfo TEXT')

            if not has_column(myDB, "wanted", "NZBsize"):
                lazylibrarian.UPDATE_MSG = 'Updating database to hold NZBsize'
                logger.debug(lazylibrarian.UPDATE_MSG)
                myDB.action('ALTER TABLE wanted ADD COLUMN NZBsize TEXT')

            if not has_column(myDB, "wanted", "NZBmode"):
                lazylibrarian.UPDATE_MSG = 'Updating database to hold NZBmode'
                logger.debug(lazylibrarian.UPDATE_MSG)
                myDB.action('ALTER TABLE wanted ADD COLUMN NZBmode TEXT')

            if not has_column(myDB, "authors", "UnignoredBooks"):
                lazylibrarian.UPDATE_MSG = 'Updating database to hold UnignoredBooks'
                logger.debug(lazylibrarian.UPDATE_MSG)
                myDB.action('ALTER TABLE authors ADD COLUMN UnignoredBooks INTEGER')

            if not has_column(myDB, "magazines", "IssueStatus"):
                lazylibrarian.UPDATE_MSG = 'Updating database to hold IssueStatus'
                logger.debug(lazylibrarian.UPDATE_MSG)
                myDB.action('ALTER TABLE magazines ADD COLUMN IssueStatus TEXT')

            addedWorkPage = False
            if not has_column(myDB, "books", "WorkPage"):
                lazylibrarian.UPDATE_MSG = 'Updating database to hold WorkPage'
                logger.debug(lazylibrarian.UPDATE_MSG)
                myDB.action('ALTER TABLE books ADD COLUMN WorkPage TEXT')
                addedWorkPage = True

            addedSeries = False
            if not has_column(myDB, "series", "SeriesID") and not has_column(myDB, "books", "Series"):
                lazylibrarian.UPDATE_MSG = 'Updating database to hold Series'
                logger.debug(lazylibrarian.UPDATE_MSG)
                myDB.action('ALTER TABLE books ADD COLUMN Series TEXT')
                addedSeries = True

            # SeriesOrder shouldn't be an integer, some later written books
            # and novellas logically go inbetween books of the main series,
            # and their SeriesOrder is not an integer, eg 1.5
            # so we need to update SeriesOrder to store as text.
            # Because sqlite can't drop columns we create a new column SeriesNum,
            # inherit the old column values, and use SeriesNum instead
            if not has_column(myDB, "books", "SeriesNum") and has_column(myDB, "books", "SeriesOrder"):
                # no SeriesNum column, so create one
                lazylibrarian.UPDATE_MSG = 'Updating books to hold SeriesNum'
                logger.debug(lazylibrarian.UPDATE_MSG)
                myDB.action('ALTER TABLE books ADD COLUMN SeriesNum TEXT')
                myDB.action('UPDATE books SET SeriesNum = SeriesOrder')
                myDB.action('UPDATE books SET SeriesOrder = Null')

            addedIssues = False
            if not has_column(myDB, "issues", "Title"):
                lazylibrarian.UPDATE_MSG = 'Updating database to hold Issues table'
                logger.debug(lazylibrarian.UPDATE_MSG)
                myDB.action(
                    'CREATE TABLE issues (Title TEXT, IssueID TEXT, IssueAcquired TEXT, IssueDate TEXT, IssueFile TEXT)')
                addedIssues = True

            if not has_column(myDB, "issues", "IssueID"):
                lazylibrarian.UPDATE_MSG = 'Updating Issues table to hold IssueID'
                logger.debug(lazylibrarian.UPDATE_MSG)
                myDB.action('ALTER TABLE issues ADD COLUMN IssueID TEXT')
                addedIssues = True

            myDB.action('DROP TABLE if exists capabilities')

            if addedIssues:
                try:
                    magazinescan.magazineScan()
                except Exception as e:
                    logger.debug("Failed to scan magazines, %s" % str(e))

            if addedWorkPage:
                try:
                    lazylibrarian.UPDATE_MSG = 'Adding WorkPage to existing books'
                    logger.debug(lazylibrarian.UPDATE_MSG)
                    threading.Thread(target=bookwork.setWorkPages, name="ADDWORKPAGE", args=[]).start()
                except Exception as e:
                    logger.debug("Failed to update WorkPages, %s" % str(e))

            if addedSeries:
                try:
                    books = myDB.select('SELECT BookID, BookName FROM books')
                    if books:
                        lazylibrarian.UPDATE_MSG = 'Adding series to existing books'
                        logger.debug(lazylibrarian.UPDATE_MSG)
                        tot = len(books)
                        cnt = 0
                        for book in books:
                            cnt += 1
                            lazylibrarian.UPDATE_MSG = 'Adding series to existing books: %s of %s' % (cnt, tot)
                            series, seriesNum = bookSeries(book["BookName"])
                            if series:
                                controlValueDict = {"BookID": book["BookID"]}
                                newValueDict = {
                                    "series": series,
                                    "seriesNum": seriesNum
                                }
                                myDB.upsert("books", newValueDict, controlValueDict)
                except Exception as e:
                    logger.error('Error: ' + str(e))

        if db_version < 2:
            try:
                results = myDB.select('SELECT BookID,NZBsize FROM wanted WHERE NZBsize LIKE "% MB"')
                if results:
                    lazylibrarian.UPDATE_MSG = 'Removing units from wanted table'
                    logger.debug(lazylibrarian.UPDATE_MSG)
                    tot = len(results)
                    cnt = 0
                    for units in results:
                        cnt += 1
                        lazylibrarian.UPDATE_MSG = 'Removing units from wanted table: %s of %s' % (cnt, tot)
                        nzbsize = units["NZBsize"]
                        nzbsize = nzbsize.split(' ')[0]
                        myDB.action('UPDATE wanted SET NZBsize = "%s" WHERE BookID = "%s"' % (nzbsize, units["BookID"]))

            except Exception as e:
                logger.error('Error: ' + str(e))

        if db_version < 3:
            if has_column(myDB, "books", "SeriesOrder"):
                lazylibrarian.UPDATE_MSG = 'Removing SeriesOrder from books table'
                logger.debug(lazylibrarian.UPDATE_MSG)
                myDB.action('CREATE TABLE IF NOT EXISTS temp_books (AuthorID TEXT, AuthorName TEXT, AuthorLink TEXT, \
                    BookName TEXT, BookSub TEXT, BookDesc TEXT, BookGenre TEXT, BookIsbn TEXT, BookPub TEXT, \
                    BookRate INTEGER, BookImg TEXT, BookPages INTEGER, BookLink TEXT, BookID TEXT UNIQUE, \
                    BookFile TEXT, BookDate TEXT, BookLang TEXT, BookAdded TEXT, Status TEXT, Series TEXT, \
                    SeriesNum TEXT, WorkPage TEXT)')
                myDB.action('INSERT INTO temp_books SELECT AuthorID,AuthorName,AuthorLink,BookName,BookSub, \
                    BookDesc,BookGenre,BookIsbn,BookPub,BookRate,BookImg,BookPages,BookLink,BookID, \
                    BookFile,BookDate,BookLang,BookAdded,Status,Series,SeriesNum,WorkPage FROM books')
                myDB.action('DROP TABLE books')
                myDB.action('ALTER TABLE temp_books RENAME TO books')

            if not has_column(myDB, "pastissues", "BookID"):
                lazylibrarian.UPDATE_MSG = 'Moving magazine past issues into new table'
                logger.debug(lazylibrarian.UPDATE_MSG)
                myDB.action(
                    'CREATE TABLE pastissues AS SELECT * FROM wanted WHERE Status="Skipped" AND length(AuxInfo) > 0')
                myDB.action('DELETE FROM wanted WHERE Status="Skipped" AND length(AuxInfo) > 0')

        if db_version < 4:
            if not has_column(myDB, "stats", "duplicates"):
                lazylibrarian.UPDATE_MSG = 'Updating stats table to hold duplicates'
                logger.debug(lazylibrarian.UPDATE_MSG)
                myDB.action('ALTER TABLE stats ADD COLUMN duplicates INT')

        if db_version < 5:
            issues = myDB.select(
                'SELECT IssueID,IssueDate from issues WHERE length(IssueDate) < 4 and length(IssueDate) > 0')
            if issues:
                lazylibrarian.UPDATE_MSG = 'Updating issues table to hold 4 digit issue numbers'
                logger.debug(lazylibrarian.UPDATE_MSG)
                tot = len(issues)
                cnt = 0
                for issue in issues:
                    cnt += 1
                    lazylibrarian.UPDATE_MSG = 'Updating issues table 4 digits: %s of %s' % (cnt, tot)
                    issueid = issue['IssueID']
                    issuedate = str(issue['IssueDate'])
                    issuedate = issuedate.zfill(4)
                    myDB.action('UPDATE issues SET IssueDate="%s" WHERE IssueID="%s"' % (issuedate, issueid))

            mags = myDB.select(
                'SELECT Title,IssueDate from magazines WHERE length(IssueDate) < 4 and length(IssueDate) > 0')
            if mags:
                lazylibrarian.UPDATE_MSG = 'Updating magazines table to 4 digits'
                logger.debug(lazylibrarian.UPDATE_MSG)
                tot = len(mags)
                cnt = 0
                for mag in mags:
                    cnt += 1
                    lazylibrarian.UPDATE_MSG = 'Updating magazines table to 4 digits: %s of %s' % (cnt, tot)
                    title = mag['Title']
                    issuedate = str(mag['IssueDate'])
                    issuedate = issuedate.zfill(4)
                    myDB.action('UPDATE magazines SET IssueDate="%s" WHERE Title="%s"' % (issuedate, title))

        if db_version < 6:
            if not has_column(myDB, "books", "Manual"):
                lazylibrarian.UPDATE_MSG = 'Updating books table to hold Manual setting'
                logger.debug(lazylibrarian.UPDATE_MSG)
                myDB.action('ALTER TABLE books ADD COLUMN Manual TEXT')

        if db_version < 7:
            if not has_column(myDB, "wanted", "Source"):
                lazylibrarian.UPDATE_MSG = 'Updating wanted table to hold Source and DownloadID'
                logger.debug(lazylibrarian.UPDATE_MSG)
                myDB.action('ALTER TABLE wanted ADD COLUMN Source TEXT')
                myDB.action('ALTER TABLE wanted ADD COLUMN DownloadID TEXT')

        if db_version < 8:
            src = os.path.join(lazylibrarian.PROG_DIR, 'data/images/cache/')
            dst = lazylibrarian.CACHEDIR
            images = myDB.select('SELECT AuthorID, AuthorImg FROM authors WHERE AuthorImg LIKE "images/cache/%"')
            if images:
                logger.debug('Moving author images to new location')
                tot = len(images)
                cnt = 0
                for image in images:
                    cnt += 1
                    lazylibrarian.UPDATE_MSG = "Moving author images to new location: %s of %s" % (cnt, tot)
                    img = image['AuthorImg']
                    img = img[7:]
                    myDB.action('UPDATE authors SET AuthorImg="%s" WHERE AuthorID="%s"' % (img, image['AuthorID']))
                    img = img[6:]
                    srcfile = os.path.join(src, img)
                    if os.path.isfile(srcfile):
                        try:
                            shutil.move(os.path.join(src, img), os.path.join(dst, img))
                        except Exception as e:
                            logger.warn("dbupgrade: %s" % str(e))
                logger.debug("Author Image cache updated")

            images = myDB.select('SELECT BookID, BookImg FROM books WHERE BookImg LIKE "images/cache/%"')
            if images:
                logger.debug('Moving book images to new location')
                tot = len(images)
                cnt = 0
                for image in images:
                    cnt += 1
                    lazylibrarian.UPDATE_MSG = "Moving book images to new location: %s of %s" % (cnt, tot)
                    img = image['BookImg']
                    img = img[7:]
                    myDB.action('UPDATE books SET BookImg="%s" WHERE BookID="%s"' % (img, image['BookID']))
                    img = img[6:]
                    srcfile = os.path.join(src, img)
                    if os.path.isfile(srcfile):
                        try:
                            shutil.move(srcfile, os.path.join(dst, img))
                        except Exception as e:
                            logger.warn("dbupgrade: %s" % str(e))
                logger.debug("Book Image cache updated")

        if db_version < 9:
            if not has_column(myDB, "magazines", "Reject"):
                # remove frequency column, rename regex to reject, add new regex column for searches
                lazylibrarian.UPDATE_MSG = 'Updating magazines table'
                logger.debug(lazylibrarian.UPDATE_MSG)
                myDB.action('CREATE TABLE IF NOT EXISTS temp_table (Title TEXT, Regex TEXT, Status TEXT, \
                            MagazineAdded TEXT, LastAcquired TEXT, IssueDate TEXT, IssueStatus TEXT, Reject TEXT)')
                myDB.action('INSERT INTO temp_table SELECT Title, Regex, Status, MagazineAdded, LastAcquired, \
                            IssueDate, IssueStatus, Regex FROM magazines')
                myDB.action('DROP TABLE magazines')
                myDB.action('ALTER TABLE temp_table RENAME TO magazines')
                myDB.action('UPDATE magazines SET Regex = Null')

        if db_version < 10:
            # make sure columns in pastissues match those in wanted table
            # needed when upgrading from old 3rd party packages (eg freenas)
            myDB.action('DROP TABLE pastissues')
            myDB.action('CREATE TABLE pastissues AS SELECT * FROM wanted WHERE 0')  # same columns, but empty table

        if db_version < 11:
            # keep last book image
            if not has_column(myDB, "authors", "LastBookImg"):
                lazylibrarian.UPDATE_MSG = 'Updating author table to hold last book image'
                logger.debug(lazylibrarian.UPDATE_MSG)
                myDB.action('ALTER TABLE authors ADD COLUMN LastBookImg TEXT')
                books = myDB.select('SELECT AuthorID, AuthorName, LastBook from authors')

                if books:
                    for book in books:
                        lazylibrarian.UPDATE_MSG = 'Updating last book image for %s' % book['AuthorName']
                        if book['LastBook']:
                            match = myDB.match('SELECT BookImg from books WHERE AuthorID="%s" AND BookName="%s"' %
                                                (book['AuthorID'], book['LastBook']))
                            if match:
                                myDB.action('UPDATE authors SET LastBookImg="%s" WHERE AuthorID=%s' % (match['BookImg'], book['AuthorID']))

        if db_version < 12:
            # keep last magazine issue image
            if not has_column(myDB, "Magazines", "LatestCover"):
                lazylibrarian.UPDATE_MSG = 'Updating magazine table to hold last issue image'
                logger.debug(lazylibrarian.UPDATE_MSG)
                myDB.action('ALTER TABLE magazines ADD COLUMN LatestCover TEXT')
                mags = myDB.select('SELECT Title, LastAcquired from magazines')

                if mags:
                    for mag in mags:
                        lazylibrarian.UPDATE_MSG = 'Updating last issue image for %s' % mag['Title']
                        match = myDB.match('SELECT IssueFile from issues WHERE IssueAcquired="%s" AND Title="%s"' %
                                                (mag['LastAcquired'], mag['Title']))
                        if match:
                            coverfile = os.path.splitext(match['IssueFile'])[0] + '.jpg'
                            if os.path.exists(coverfile):
                                myDB.action('UPDATE magazines SET LatestCover="%s" WHERE Title="%s"' % (coverfile, mag['Title']))

        if db_version < 13:
            if not has_column(myDB, "authors", "Manual"):
                lazylibrarian.UPDATE_MSG = 'Updating authors table to hold Manual setting'
                logger.debug(lazylibrarian.UPDATE_MSG)
                myDB.action('ALTER TABLE authors ADD COLUMN Manual TEXT')

        if db_version < 14:
            src = lazylibrarian.CACHEDIR
            try:
                os.mkdir(os.path.join(src, 'author'))
            except OSError as e:
                if e.errno is not 17:  # already exists is ok
                    logger.debug('mkdir author cache reports: %s' % str(e))

            query = 'SELECT AuthorName, AuthorID, AuthorImg FROM authors '
            query += 'WHERE AuthorImg LIKE "cache/%" '
            query += 'AND AuthorImg NOT LIKE "cache/author/%"'

            images = myDB.select(query)
            if images:
                tot = len(images)
                logger.debug('Moving %s author images to new location' % tot)
                cnt = 0
                for image in images:
                    cnt += 1
                    lazylibrarian.UPDATE_MSG = "Moving author images to new location: %s of %s" % (cnt, tot)
                    try:
                        img = image['AuthorImg']
                        img = img.rsplit('/', 1)[1]
                        srcfile = os.path.join(src, img)
                        if os.path.isfile(srcfile):
                            try:
                                shutil.move(srcfile, os.path.join(src, "author", img))
                                myDB.action('UPDATE authors SET AuthorImg="cache/author/%s" WHERE AuthorID="%s"' %
                                            (img, image['AuthorID']))
                            except Exception as e:
                                logger.warn("dbupgrade: %s" % str(e))
                    except Exception as e:
                        logger.warn('Failed to update author image for %s: %s' % (image['AuthorName'], str(e)))
                logger.debug("Author Image cache updated")

            try:
                os.mkdir(os.path.join(src, 'book'))
            except OSError as e:
                if e.errno is not 17:  # already exists is ok
                    logger.debug('mkdir book cache reports: %s' % str(e))

            query = 'SELECT BookName, BookID, BookImg FROM books '
            query += 'WHERE BookImg LIKE "cache/%" '
            query += 'AND BookImg NOT LIKE "cache/book/%"'
            images = myDB.select(query)

            if images:
                tot = len(images)
                logger.debug('Moving %s book images to new location' % tot)
                cnt = 0
                for image in images:
                    cnt += 1
                    lazylibrarian.UPDATE_MSG = "Moving book images to new location: %s of %s" % (cnt, tot)
                    try:
                        img = image['BookImg']
                        img = img.rsplit('/', 1)[1]
                        srcfile = os.path.join(src, img)
                        if os.path.isfile(srcfile):
                            try:
                                shutil.move(srcfile, os.path.join(src, "book", img))
                                myDB.action('UPDATE books SET BookImg="cache/book/%s" WHERE BookID="%s"' %
                                            (img, image['BookID']))
                            except Exception as e:
                                logger.warn("dbupgrade: %s" % str(e))
                    except Exception as e:
                        logger.warn('Failed to update book image for %s: %s' % (image['BookName'], str(e)))
                logger.debug("Book Image cache updated")

            # at this point there should be no more .jpg files in the root of the cachedir
            # any that are still there are for books/authors deleted from database
            # or magazine latest issue cover files that get copied as required
            for image in os.listdir(src):
                if image.endswith('.jpg'):
                    os.remove(os.path.join(src, image))


        if db_version < 15:
            myDB.action('CREATE TABLE IF NOT EXISTS series (SeriesID INTEGER PRIMARY KEY, SeriesName TEXT, \
                        AuthorID TEXT, Status TEXT)')
            myDB.action('CREATE TABLE IF NOT EXISTS member (SeriesID INTEGER, BookID TEXT, SeriesNum TEXT)')
            if has_column(myDB, "books", "SeriesNum"):
                lazylibrarian.UPDATE_MSG = 'Populating series and member tables'
                books = myDB.select('SELECT BookID, Series, SeriesNum from books')
                if books:
                    tot = len(books)
                    logger.debug("Updating book series for %s book%s" % (tot, plural(tot)))
                    cnt = 0
                    for book in books:
                        cnt += 1
                        lazylibrarian.UPDATE_MSG = "Updating book series: %s of %s" % (cnt, tot)
                        seriesdict = getWorkSeries(book['BookID'])
                        if not seriesdict:  # no workpage series, use the current values if present
                            if book['Series'] and book['SeriesNum']:
                                seriesdict = {cleanName(unaccented(book['Series'])): book['SeriesNum']}
                        setSeries(seriesdict, book['BookID'])
                    # deleteEmptySeries  # shouldn't be any on first run?
                    lazylibrarian.UPDATE_MSG = "Book series update complete"
                    logger.debug(lazylibrarian.UPDATE_MSG)

                lazylibrarian.UPDATE_MSG = 'Removing seriesnum from books table'
                myDB.action('CREATE TABLE IF NOT EXISTS temp_table (AuthorID TEXT, AuthorName TEXT, AuthorLink TEXT, \
                    BookName TEXT, BookSub TEXT, BookDesc TEXT, BookGenre TEXT, BookIsbn TEXT, BookPub TEXT, \
                    BookRate INTEGER, BookImg TEXT, BookPages INTEGER, BookLink TEXT, BookID TEXT UNIQUE, \
                    BookFile TEXT, BookDate TEXT, BookLang TEXT, BookAdded TEXT, Status TEXT, Series TEXT, \
                    WorkPage TEXT, Manual TEXT)')
                myDB.action('INSERT INTO temp_table SELECT AuthorID, AuthorName, AuthorLink, BookName, BookSub, \
                    BookDesc, BookGenre, BookIsbn, BookPub, BookRate, BookImg, BookPages, BookLink, BookID, \
                    BookFile, BookDate, BookLang, BookAdded, Status, Series, WorkPage, Manual from books')
                myDB.action('DROP TABLE books')
                myDB.action('ALTER TABLE temp_table RENAME TO books')
                lazylibrarian.UPDATE_MSG = 'Reorganisation of books table complete'

        if db_version < 16:
            if has_column(myDB, "books", "AuthorLink"):
                lazylibrarian.UPDATE_MSG = 'Removing series, authorlink and authorname from books table'
                myDB.action('CREATE TABLE IF NOT EXISTS temp_table (AuthorID TEXT, \
                    BookName TEXT, BookSub TEXT, BookDesc TEXT, BookGenre TEXT, BookIsbn TEXT, BookPub TEXT, \
                    BookRate INTEGER, BookImg TEXT, BookPages INTEGER, BookLink TEXT, BookID TEXT UNIQUE, \
                    BookFile TEXT, BookDate TEXT, BookLang TEXT, BookAdded TEXT, Status TEXT, WorkPage TEXT, \
                    Manual TEXT)')
                myDB.action('INSERT INTO temp_table SELECT AuthorID, BookName, BookSub, \
                    BookDesc, BookGenre, BookIsbn, BookPub, BookRate, BookImg, BookPages, BookLink, BookID, \
                    BookFile, BookDate, BookLang, BookAdded, Status, WorkPage, Manual from books')
                myDB.action('DROP TABLE books')
                myDB.action('ALTER TABLE temp_table RENAME TO books')
                lazylibrarian.UPDATE_MSG = 'Reorganisation of books table complete'

        if db_version < 17:
            if has_column(myDB, "series", "AuthorID"):
                lazylibrarian.UPDATE_MSG = 'Creating seriesauthors table'
                # In this version of the database there is only one author per series so use that as starting point
                myDB.action('CREATE TABLE IF NOT EXISTS seriesauthors (SeriesID INTEGER, AuthorID TEXT)')
                myDB.action('INSERT INTO seriesauthors SELECT SeriesID, AuthorID FROM series')
                myDB.action('CREATE TABLE IF NOT EXISTS temp_table (SeriesID INTEGER PRIMARY KEY, SeriesName TEXT, \
                    Status TEXT)')
                myDB.action('INSERT INTO temp_table SELECT  SeriesID, SeriesName, Status FROM series')
                myDB.action('DROP TABLE series')
                myDB.action('ALTER TABLE temp_table RENAME TO series')
                lazylibrarian.UPDATE_MSG = 'Reorganisation of series table complete'


        # Now do any non-version-specific tidying
        try:
            authors = myDB.select('SELECT AuthorID FROM authors WHERE AuthorName IS NULL')
            if authors:
                logger.debug('Removing %s un-named author%s from database' % (len(authors), plural(len(authors))))
                for author in authors:
                    authorid = author["AuthorID"]
                    myDB.action('DELETE from authors WHERE AuthorID="%s"' % authorid)
                    myDB.action('DELETE from books WHERE AuthorID="%s"' % authorid)
        except Exception as e:
            logger.error('Error: ' + str(e))

        myDB.action('PRAGMA user_version = %s' % db_current_version)
        lazylibrarian.UPDATE_MSG = 'Cleaning Database after upgrade'
        myDB.action('vacuum')
        lazylibrarian.UPDATE_MSG = 'Database updated to version %s' % db_current_version
        logger.info(lazylibrarian.UPDATE_MSG)

        restartJobs(start='Start')

    lazylibrarian.UPDATE_MSG = ''

  except Exception:
    logger.error('Unhandled exception in database update: %s' % traceback.format_exc())
    lazylibrarian.UPDATE_MSG = ''
