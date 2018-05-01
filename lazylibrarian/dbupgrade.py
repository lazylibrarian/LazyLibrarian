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

from __future__ import with_statement

import datetime
import os
import shutil
import threading
import time
import traceback

import lazylibrarian
from lazylibrarian import logger, database, magazinescan, bookwork
from lazylibrarian.common import restartJobs, pwd_generator
from lazylibrarian.formatter import plural, bookSeries, makeUnicode, makeBytestr, md5_utf8
from lazylibrarian.importer import addAuthorToDB


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
    # 18 Added unique constraint to seriesauthors table
    # 19 add seriesdisplay to book table
    # 20 add booklibrary date to book table
    # 21 add audiofile audiolibrary date and audiostatus to books table
    # 22 add goodreads "follow" to author table
    # 23 add user accounts
    # 24 add HaveRead and ToRead to user accounts
    # 25 add index for magazine issues (title) for new dbchanges
    # 26 add Sync table
    # 27 add indexes for book/author/wanted status
    # 28 add CalibreRead and CalibreToRead columns to user table
    # 29 add goodreads workid to books table
    # 30 add BookType to users table
    # 31 add DateType to magazines table
    # 32 add counters to series table

    db_current_version = 32

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
    with open(os.path.join(lazylibrarian.CONFIG['LOGDIR'], 'dbupgrade.log'), 'a') as upgradelog:
        # noinspection PyBroadException
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
                myDB = database.DBConnection()
                if db_version:
                    lazylibrarian.UPDATE_MSG = 'Updating database to version %s, current version is %s' % (
                        db_current_version, db_version)
                    logger.info(lazylibrarian.UPDATE_MSG)
                    upgradelog.write("%s v0: %s\n" % (time.ctime(), lazylibrarian.UPDATE_MSG))
                else:
                    if not has_column(myDB, "authors", "AuthorID"):
                        # it's a new database. Create tables but no need for any upgrading
                        db_version = db_current_version
                        lazylibrarian.UPDATE_MSG = 'Creating new database, version %s' % db_version
                        upgradelog.write("%s v0: %s\n" % (time.ctime(), lazylibrarian.UPDATE_MSG))
                        logger.info(lazylibrarian.UPDATE_MSG)

                    myDB.action('CREATE TABLE IF NOT EXISTS authors (AuthorID TEXT UNIQUE, AuthorName TEXT UNIQUE, \
                AuthorImg TEXT, AuthorLink TEXT, DateAdded TEXT, Status TEXT, LastBook TEXT, LastBookImg TEXT, \
                LastLink Text, LastDate TEXT,  HaveBooks INTEGER, TotalBooks INTEGER, AuthorBorn TEXT, \
                AuthorDeath TEXT, UnignoredBooks INTEGER, Manual TEXT, GRfollow TEXT)')
                    myDB.action('CREATE TABLE IF NOT EXISTS books (AuthorID TEXT, \
                BookName TEXT, BookSub TEXT, BookDesc TEXT, BookGenre TEXT, BookIsbn TEXT, BookPub TEXT, \
                BookRate INTEGER, BookImg TEXT, BookPages INTEGER, BookLink TEXT, BookID TEXT UNIQUE, \
                BookFile TEXT, BookDate TEXT, BookLang TEXT, BookAdded TEXT, Status TEXT, WorkPage TEXT, \
                Manual TEXT, SeriesDisplay TEXT, BookLibrary TEXT, AudioFile TEXT, AudioLibrary TEXT, \
                AudioStatus TEXT, WorkID TEXT)')
                    myDB.action('CREATE TABLE IF NOT EXISTS wanted (BookID TEXT, NZBurl TEXT, NZBtitle TEXT, \
                NZBdate TEXT, NZBprov TEXT, Status TEXT, NZBsize TEXT, AuxInfo TEXT, NZBmode TEXT, Source TEXT, \
                DownloadID TEXT)')
                    myDB.action('CREATE TABLE IF NOT EXISTS pastissues AS SELECT * FROM wanted WHERE 0')  # same columns
                    myDB.action('CREATE TABLE IF NOT EXISTS magazines (Title TEXT UNIQUE, Regex TEXT, Status TEXT, \
                MagazineAdded TEXT, LastAcquired TEXT, IssueDate TEXT, IssueStatus TEXT, Reject TEXT, \
                LatestCover TEXT, DateType TEXT)')
                    myDB.action('CREATE TABLE IF NOT EXISTS languages (isbn TEXT, lang TEXT)')
                    myDB.action('CREATE TABLE IF NOT EXISTS issues (Title TEXT, IssueID TEXT UNIQUE, \
                IssueAcquired TEXT, IssueDate TEXT, IssueFile TEXT)')
                    myDB.action('CREATE TABLE IF NOT EXISTS stats (authorname text, GR_book_hits int, \
                GR_lang_hits int, LT_lang_hits int, GB_lang_change, cache_hits int, bad_lang int, bad_char int, \
                uncached int, duplicates int)')
                    myDB.action('CREATE TABLE IF NOT EXISTS series (SeriesID INTEGER UNIQUE, SeriesName TEXT, \
                Status TEXT, Have TEXT, Total TEXT)')
                    myDB.action('CREATE TABLE IF NOT EXISTS member (SeriesID INTEGER, BookID TEXT, WorkID TEXT, \
                                 SeriesNum TEXT)')
                    myDB.action('CREATE TABLE IF NOT EXISTS seriesauthors (SeriesID INTEGER, AuthorID TEXT, \
                UNIQUE (SeriesID,AuthorID))')
                    myDB.action('CREATE TABLE IF NOT EXISTS downloads (Count INTEGER, Provider TEXT)')
                    myDB.action('CREATE TABLE IF NOT EXISTS users (UserID TEXT UNIQUE, UserName TEXT UNIQUE, \
                                Password TEXT, Email TEXT, Name TEXT, Perms INTEGER, HaveRead TEXT, ToRead TEXT, \
                                CalibreRead TEXT, CalibreToRead TEXT, BookType TEXT)')
                    cmd = 'INSERT into users (UserID, UserName, Name, Password, Perms) VALUES (?, ?, ?, ?, ?)'
                    myDB.action(cmd, (pwd_generator(), 'admin', 'admin', md5_utf8('admin'), 65535))
                    logger.debug('Added admin user')
                    myDB.action('CREATE INDEX IF NOT EXISTS issues_Title_index ON issues (Title)')
                    myDB.action('CREATE INDEX IF NOT EXISTS books_index_authorid ON books(AuthorID)')

                    myDB.action('CREATE TABLE IF NOT EXISTS sync (UserID TEXT, Label TEXT, Date TEXT, SyncList TEXT)')
                    myDB.action('CREATE INDEX IF NOT EXISTS books_index_status ON books(Status)')
                    myDB.action('CREATE INDEX IF NOT EXISTS authors_index_status ON authors(Status)')
                    myDB.action('CREATE INDEX IF NOT EXISTS wanted_index_status ON wanted(Status)')

                # These are the incremental changes before database versioning was introduced.
                # Old database tables might already have these incorporated depending on version, so we need to check...
                if db_version < 1:
                    lazylibrarian.UPDATE_MSG = 'Updating database to version %s, current version is %s' % (
                        db_current_version, db_version)
                    logger.info(lazylibrarian.UPDATE_MSG)
                    upgradelog.write("%s v1: %s\n" % (time.ctime(), lazylibrarian.UPDATE_MSG))

                    if not has_column(myDB, "books", "BookSub"):
                        lazylibrarian.UPDATE_MSG = 'Updating database to hold book subtitles.'
                        logger.debug(lazylibrarian.UPDATE_MSG)
                        upgradelog.write("%s v1: %s\n" % (time.ctime(), lazylibrarian.UPDATE_MSG))
                        myDB.action('ALTER TABLE books ADD COLUMN BookSub TEXT')

                    if not has_column(myDB, "books", "BookSub"):
                        lazylibrarian.UPDATE_MSG = 'Updating database to hold book publisher'
                        logger.debug(lazylibrarian.UPDATE_MSG)
                        upgradelog.write("%s v1: %s\n" % (time.ctime(), lazylibrarian.UPDATE_MSG))
                        myDB.action('ALTER TABLE books ADD COLUMN BookPub TEXT')

                    if not has_column(myDB, "books", "BookGenre"):
                        lazylibrarian.UPDATE_MSG = 'Updating database to hold bookgenre'
                        logger.debug(lazylibrarian.UPDATE_MSG)
                        upgradelog.write("%s v1: %s\n" % (time.ctime(), lazylibrarian.UPDATE_MSG))
                        myDB.action('ALTER TABLE books ADD COLUMN BookGenre TEXT')

                    if not has_column(myDB, "books", "BookFile"):
                        lazylibrarian.UPDATE_MSG = 'Updating database to hold book filename'
                        logger.debug(lazylibrarian.UPDATE_MSG)
                        upgradelog.write("%s v1: %s\n" % (time.ctime(), lazylibrarian.UPDATE_MSG))
                        myDB.action('ALTER TABLE books ADD COLUMN BookFile TEXT')

                    if not has_column(myDB, "wanted", "AuxInfo"):
                        lazylibrarian.UPDATE_MSG = 'Updating database to hold AuxInfo'
                        logger.debug(lazylibrarian.UPDATE_MSG)
                        upgradelog.write("%s v1: %s\n" % (time.ctime(), lazylibrarian.UPDATE_MSG))
                        myDB.action('ALTER TABLE wanted ADD COLUMN AuxInfo TEXT')

                    if not has_column(myDB, "wanted", "NZBsize"):
                        lazylibrarian.UPDATE_MSG = 'Updating database to hold NZBsize'
                        logger.debug(lazylibrarian.UPDATE_MSG)
                        upgradelog.write("%s v1: %s\n" % (time.ctime(), lazylibrarian.UPDATE_MSG))
                        myDB.action('ALTER TABLE wanted ADD COLUMN NZBsize TEXT')

                    if not has_column(myDB, "wanted", "NZBmode"):
                        lazylibrarian.UPDATE_MSG = 'Updating database to hold NZBmode'
                        logger.debug(lazylibrarian.UPDATE_MSG)
                        upgradelog.write("%s v1: %s\n" % (time.ctime(), lazylibrarian.UPDATE_MSG))
                        myDB.action('ALTER TABLE wanted ADD COLUMN NZBmode TEXT')

                    if not has_column(myDB, "authors", "UnignoredBooks"):
                        lazylibrarian.UPDATE_MSG = 'Updating database to hold UnignoredBooks'
                        logger.debug(lazylibrarian.UPDATE_MSG)
                        upgradelog.write("%s v1: %s\n" % (time.ctime(), lazylibrarian.UPDATE_MSG))
                        myDB.action('ALTER TABLE authors ADD COLUMN UnignoredBooks INTEGER')

                    if not has_column(myDB, "magazines", "IssueStatus"):
                        lazylibrarian.UPDATE_MSG = 'Updating database to hold IssueStatus'
                        logger.debug(lazylibrarian.UPDATE_MSG)
                        upgradelog.write("%s v1: %s\n" % (time.ctime(), lazylibrarian.UPDATE_MSG))
                        myDB.action('ALTER TABLE magazines ADD COLUMN IssueStatus TEXT')

                    addedWorkPage = False
                    if not has_column(myDB, "books", "WorkPage"):
                        lazylibrarian.UPDATE_MSG = 'Updating database to hold WorkPage'
                        logger.debug(lazylibrarian.UPDATE_MSG)
                        upgradelog.write("%s v1: %s\n" % (time.ctime(), lazylibrarian.UPDATE_MSG))
                        myDB.action('ALTER TABLE books ADD COLUMN WorkPage TEXT')
                        addedWorkPage = True

                    addedSeries = False
                    if not has_column(myDB, "series", "SeriesID") and not has_column(myDB, "books", "Series"):
                        lazylibrarian.UPDATE_MSG = 'Updating database to hold Series'
                        logger.debug(lazylibrarian.UPDATE_MSG)
                        upgradelog.write("%s v1: %s\n" % (time.ctime(), lazylibrarian.UPDATE_MSG))
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
                        upgradelog.write("%s v1: %s\n" % (time.ctime(), lazylibrarian.UPDATE_MSG))
                        logger.debug(lazylibrarian.UPDATE_MSG)
                        myDB.action('ALTER TABLE books ADD COLUMN SeriesNum TEXT')
                        myDB.action('UPDATE books SET SeriesNum = SeriesOrder')
                        myDB.action('UPDATE books SET SeriesOrder = Null')

                    addedIssues = False
                    if not has_column(myDB, "issues", "Title"):
                        lazylibrarian.UPDATE_MSG = 'Updating database to hold Issues table'
                        upgradelog.write("%s v1: %s\n" % (time.ctime(), lazylibrarian.UPDATE_MSG))
                        logger.debug(lazylibrarian.UPDATE_MSG)
                        myDB.action('CREATE TABLE issues (Title TEXT, IssueID TEXT, IssueAcquired TEXT, \
                                    IssueDate TEXT, IssueFile TEXT)')
                        addedIssues = True

                    if not has_column(myDB, "issues", "IssueID"):
                        lazylibrarian.UPDATE_MSG = 'Updating Issues table to hold IssueID'
                        upgradelog.write("%s v1: %s\n" % (time.ctime(), lazylibrarian.UPDATE_MSG))
                        logger.debug(lazylibrarian.UPDATE_MSG)
                        myDB.action('ALTER TABLE issues ADD COLUMN IssueID TEXT')
                        addedIssues = True

                    myDB.action('DROP TABLE if exists capabilities')

                    if addedIssues:
                        try:
                            magazinescan.magazineScan()
                        except Exception as e:
                            msg = "Failed to scan magazines, %s %s" % (type(e).__name__, str(e))
                            logger.error(msg)
                            upgradelog.write("%s v1: %s\n" % (time.ctime(), msg))

                    if addedWorkPage:
                        try:
                            lazylibrarian.UPDATE_MSG = 'Adding WorkPage to existing books'
                            logger.debug(lazylibrarian.UPDATE_MSG)
                            threading.Thread(target=bookwork.setWorkPages, name="ADDWORKPAGE", args=[]).start()
                        except Exception as e:
                            msg = "Failed to update WorkPages, %s %s" % (type(e).__name__, str(e))
                            logger.error(msg)
                            upgradelog.write("%s v1: %s\n" % (time.ctime(), msg))

                    if addedSeries:
                        try:
                            books = myDB.select('SELECT BookID, BookName FROM books')
                            if books:
                                lazylibrarian.UPDATE_MSG = 'Adding series to existing books'
                                upgradelog.write("%s v1: %s\n" % (time.ctime(), lazylibrarian.UPDATE_MSG))
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
                                upgradelog.write("%s v1: %s\n" % (time.ctime(), lazylibrarian.UPDATE_MSG))
                        except Exception as e:
                            msg = 'Error adding series to books: %s %s' % (type(e).__name__, str(e))
                            logger.error(msg)
                            upgradelog.write("%s v1: %s\n" % (time.ctime(), msg))
                    upgradelog.write("%s v1: complete\n" % time.ctime())

                upgradefunctions = [db_v2, db_v3, db_v4, db_v5, db_v6, db_v7, db_v8, db_v9, db_v10, db_v11,
                                    db_v12, db_v13, db_v14, db_v15, db_v16, db_v17, db_v18, db_v19, db_v20,
                                    db_v21, db_v22, db_v23, db_v24, db_v25, db_v26, db_v27, db_v28, db_v29,
                                    db_v30, db_v31, db_v32]
                for index, upgrade_function in enumerate(upgradefunctions):
                    if index + 2 > db_version:
                        upgrade_function(myDB, upgradelog)

                # Now do any non-version-specific tidying
                try:
                    authors = myDB.select('SELECT AuthorID FROM authors WHERE AuthorName IS NULL')
                    if authors:
                        msg = 'Removing %s un-named author%s from database' % (len(authors), plural(len(authors)))
                        logger.debug(msg)
                        upgradelog.write("%s: %s\n" % (time.ctime(), msg))
                        for author in authors:
                            authorid = author["AuthorID"]
                            myDB.action('DELETE from authors WHERE AuthorID=?', (authorid,))
                            myDB.action('DELETE from books WHERE AuthorID=?', (authorid,))
                except Exception as e:
                    msg = 'Delete unnamed author error: %s %s' % (type(e).__name__, str(e))
                    logger.error(msg)
                    upgradelog.write("%s: %s\n" % (time.ctime(), msg))

                myDB.action('PRAGMA user_version=%s' % db_current_version)
                lazylibrarian.UPDATE_MSG = 'Cleaning Database'
                upgradelog.write("%s: %s\n" % (time.ctime(), lazylibrarian.UPDATE_MSG))
                myDB.action('vacuum')
                lazylibrarian.UPDATE_MSG = 'Database upgraded to version %s' % db_current_version
                logger.info(lazylibrarian.UPDATE_MSG)
                upgradelog.write("%s: %s\n" % (time.ctime(), lazylibrarian.UPDATE_MSG))

                restartJobs(start='Start')

            lazylibrarian.UPDATE_MSG = ''

        except Exception:
            msg = 'Unhandled exception in database upgrade: %s' % traceback.format_exc()
            upgradelog.write("%s: %s\n" % (time.ctime(), msg))
            logger.error(msg)
            lazylibrarian.UPDATE_MSG = ''


def db_v2(myDB, upgradelog):
    try:
        results = myDB.select('SELECT BookID,NZBsize FROM wanted WHERE NZBsize LIKE "% MB"')
        if results:
            lazylibrarian.UPDATE_MSG = 'Removing units from wanted table'
            logger.debug(lazylibrarian.UPDATE_MSG)
            upgradelog.write("%s v2: %s\n" % (time.ctime(), lazylibrarian.UPDATE_MSG))
            tot = len(results)
            cnt = 0
            for units in results:
                cnt += 1
                lazylibrarian.UPDATE_MSG = 'Removing units from wanted table: %s of %s' % (cnt, tot)
                nzbsize = units["NZBsize"]
                nzbsize = nzbsize.split(' ')[0]
                myDB.action(
                    'UPDATE wanted SET NZBsize=? WHERE BookID=?', (nzbsize, units["BookID"]))
            upgradelog.write("%s v2: %s\n" % (time.ctime(), lazylibrarian.UPDATE_MSG))
    except Exception as e:
        msg = 'Error removing units from wanted table: %s %s ' % (type(e).__name__, str(e))
        logger.error(msg)
        upgradelog.write("%s v2: %s\n" % (time.ctime(), msg))
    upgradelog.write("%s v2: complete\n" % time.ctime())


def db_v3(myDB, upgradelog):
    if has_column(myDB, "books", "SeriesOrder"):
        lazylibrarian.UPDATE_MSG = 'Removing SeriesOrder from books table'
        upgradelog.write("%s v3: %s\n" % (time.ctime(), lazylibrarian.UPDATE_MSG))
        logger.debug(lazylibrarian.UPDATE_MSG)
        myDB.action('CREATE TABLE IF NOT EXISTS temp_books (AuthorID TEXT, AuthorName TEXT, \
                    AuthorLink TEXT, BookName TEXT, BookSub TEXT, BookDesc TEXT, BookGenre TEXT, BookIsbn TEXT, \
                    BookPub TEXT, BookRate INTEGER, BookImg TEXT, BookPages INTEGER, BookLink TEXT, \
                    BookID TEXT UNIQUE, BookFile TEXT, BookDate TEXT, BookLang TEXT, BookAdded TEXT, Status TEXT, \
                    Series TEXT, SeriesNum TEXT, WorkPage TEXT)')
        myDB.action('INSERT INTO temp_books SELECT AuthorID,AuthorName,AuthorLink,BookName,BookSub, \
                    BookDesc,BookGenre,BookIsbn,BookPub,BookRate,BookImg,BookPages,BookLink,BookID, \
                    BookFile,BookDate,BookLang,BookAdded,Status,Series,SeriesNum,WorkPage FROM books')
        myDB.action('DROP TABLE books')
        myDB.action('ALTER TABLE temp_books RENAME TO books')

    if not has_column(myDB, "pastissues", "BookID"):
        lazylibrarian.UPDATE_MSG = 'Moving magazine past issues into new table'
        upgradelog.write("%s v3: %s\n" % (time.ctime(), lazylibrarian.UPDATE_MSG))
        logger.debug(lazylibrarian.UPDATE_MSG)
        myDB.action('CREATE TABLE pastissues AS SELECT * FROM wanted WHERE Status="Skipped" \
                                    AND length(AuxInfo) > 0')
        myDB.action('DELETE FROM wanted WHERE Status="Skipped" AND length(AuxInfo) > 0')
    upgradelog.write("%s v3: complete\n" % time.ctime())


def db_v4(myDB, upgradelog):
    if not has_column(myDB, "stats", "duplicates"):
        lazylibrarian.UPDATE_MSG = 'Updating stats table to hold duplicates'
        upgradelog.write("%s v4: %s\n" % (time.ctime(), lazylibrarian.UPDATE_MSG))
        logger.debug(lazylibrarian.UPDATE_MSG)
        myDB.action('ALTER TABLE stats ADD COLUMN duplicates INT')
    upgradelog.write("%s v4: complete\n" % time.ctime())


def db_v5(myDB, upgradelog):
    issues = myDB.select(
        'SELECT IssueID,IssueDate from issues WHERE length(IssueDate) < 4 and length(IssueDate) > 0')
    if issues:
        lazylibrarian.UPDATE_MSG = 'Updating issues table to hold 4 digit issue numbers'
        upgradelog.write("%s v5: %s\n" % (time.ctime(), lazylibrarian.UPDATE_MSG))
        logger.debug(lazylibrarian.UPDATE_MSG)
        tot = len(issues)
        cnt = 0
        for issue in issues:
            cnt += 1
            lazylibrarian.UPDATE_MSG = 'Updating issues table 4 digits: %s of %s' % (cnt, tot)
            issueid = issue['IssueID']
            issuedate = str(issue['IssueDate'])
            issuedate = issuedate.zfill(4)
            myDB.action('UPDATE issues SET IssueDate=? WHERE IssueID=?', (issuedate, issueid))
        upgradelog.write("%s v5: %s\n" % (time.ctime(), lazylibrarian.UPDATE_MSG))

    mags = myDB.select(
        'SELECT Title,IssueDate from magazines WHERE length(IssueDate) < 4 and length(IssueDate) > 0')
    if mags:
        lazylibrarian.UPDATE_MSG = 'Updating magazines table to 4 digits'
        upgradelog.write("%s v5: %s\n" % (time.ctime(), lazylibrarian.UPDATE_MSG))
        logger.debug(lazylibrarian.UPDATE_MSG)
        tot = len(mags)
        cnt = 0
        for mag in mags:
            cnt += 1
            lazylibrarian.UPDATE_MSG = 'Updating magazines table to 4 digits: %s of %s' % (cnt, tot)
            title = mag['Title']
            issuedate = str(mag['IssueDate'])
            issuedate = issuedate.zfill(4)
            myDB.action('UPDATE magazines SET IssueDate=? WHERE Title=?', (issuedate, title))
        upgradelog.write("%s v5: %s\n" % (time.ctime(), lazylibrarian.UPDATE_MSG))
    upgradelog.write("%s v5: complete\n" % time.ctime())


def db_v6(myDB, upgradelog):
    if not has_column(myDB, "books", "Manual"):
        lazylibrarian.UPDATE_MSG = 'Updating books table to hold Manual setting'
        upgradelog.write("%s v6: %s\n" % (time.ctime(), lazylibrarian.UPDATE_MSG))
        logger.debug(lazylibrarian.UPDATE_MSG)
        myDB.action('ALTER TABLE books ADD COLUMN Manual TEXT')
    upgradelog.write("%s v6: complete\n" % time.ctime())


def db_v7(myDB, upgradelog):
    if not has_column(myDB, "wanted", "Source"):
        lazylibrarian.UPDATE_MSG = 'Updating wanted table to hold Source and DownloadID'
        upgradelog.write("%s v7: %s\n" % (time.ctime(), lazylibrarian.UPDATE_MSG))
        logger.debug(lazylibrarian.UPDATE_MSG)
        myDB.action('ALTER TABLE wanted ADD COLUMN Source TEXT')
        myDB.action('ALTER TABLE wanted ADD COLUMN DownloadID TEXT')
    upgradelog.write("%s v7: complete\n" % time.ctime())


def db_v8(myDB, upgradelog):
    src = os.path.join(lazylibrarian.PROG_DIR, 'data/images/cache/')
    dst = lazylibrarian.CACHEDIR
    images = myDB.select(
        'SELECT AuthorID, AuthorImg FROM authors WHERE AuthorImg LIKE "images/cache/%"')
    if images:
        lazylibrarian.UPDATE_MSG = 'Moving author images to new location'
        logger.debug(lazylibrarian.UPDATE_MSG)
        upgradelog.write("%s v8: %s\n" % (time.ctime(), lazylibrarian.UPDATE_MSG))
        tot = len(images)
        cnt = 0
        for image in images:
            cnt += 1
            lazylibrarian.UPDATE_MSG = "Moving author images to new location: %s of %s" % (cnt, tot)
            img = image['AuthorImg']
            img = img[7:]
            myDB.action(
                'UPDATE authors SET AuthorImg=? WHERE AuthorID=?', (img, image['AuthorID']))
            img = img[6:]
            srcfile = os.path.join(src, img)
            if os.path.isfile(srcfile):
                try:
                    shutil.move(os.path.join(src, img), os.path.join(dst, img))
                except Exception as e:
                    msg = "dbupgrade: %s %s" % (type(e).__name__, str(e))
                    logger.error(msg)
                    upgradelog.write("%s v8: %s\n" % (time.ctime(), msg))
        upgradelog.write("%s v8: %s" % (time.ctime(), lazylibrarian.UPDATE_MSG))
        logger.debug("Author Image cache updated")

    images = myDB.select('SELECT BookID, BookImg FROM books WHERE BookImg LIKE "images/cache/%"')
    if images:
        lazylibrarian.UPDATE_MSG = 'Moving book images to new location'
        logger.debug(lazylibrarian.UPDATE_MSG)
        upgradelog.write("%s v8: %s\n" % (time.ctime(), lazylibrarian.UPDATE_MSG))
        tot = len(images)
        cnt = 0
        for image in images:
            cnt += 1
            lazylibrarian.UPDATE_MSG = "Moving book images to new location: %s of %s" % (cnt, tot)
            img = image['BookImg']
            img = img[7:]
            myDB.action('UPDATE books SET BookImg=? WHERE BookID=?', (img, image['BookID']))
            img = img[6:]
            srcfile = os.path.join(src, img)
            if os.path.isfile(srcfile):
                try:
                    shutil.move(srcfile, os.path.join(dst, img))
                except Exception as e:
                    msg = "dbupgrade: %s %s %s" % (srcfile, type(e).__name__, str(e))
                    upgradelog.write("%s v8: %s\n" % (time.ctime(), msg))
                    logger.error(msg)
        upgradelog.write("%s v8: %s\n" % (time.ctime(), lazylibrarian.UPDATE_MSG))
        logger.debug("Book Image cache updated")
    upgradelog.write("%s v8: complete\n" % time.ctime())


def db_v9(myDB, upgradelog):
    if not has_column(myDB, "magazines", "Reject"):
        # remove frequency column, rename regex to reject, add new regex column for searches
        lazylibrarian.UPDATE_MSG = 'Updating magazines table'
        upgradelog.write("%s v9: %s\n" % (time.ctime(), lazylibrarian.UPDATE_MSG))
        logger.debug(lazylibrarian.UPDATE_MSG)
        myDB.action('CREATE TABLE IF NOT EXISTS temp_table (Title TEXT, Regex TEXT, Status TEXT, \
                            MagazineAdded TEXT, LastAcquired TEXT, IssueDate TEXT, IssueStatus TEXT, Reject TEXT)')
        myDB.action('INSERT INTO temp_table SELECT Title, Regex, Status, MagazineAdded, LastAcquired, \
                            IssueDate, IssueStatus, Regex FROM magazines')
        myDB.action('DROP TABLE magazines')
        myDB.action('ALTER TABLE temp_table RENAME TO magazines')
        myDB.action('UPDATE magazines SET Regex = Null')
    upgradelog.write("%s v9: complete\n" % time.ctime())


def db_v10(myDB, upgradelog):
    # make sure columns in pastissues match those in wanted table
    # needed when upgrading from old 3rd party packages (eg freenas)
    upgradelog.write("%s v10: %s\n" % (time.ctime(), "Re-creating past issues table"))
    myDB.action('DROP TABLE pastissues')
    myDB.action(
        'CREATE TABLE pastissues AS SELECT * FROM wanted WHERE 0')  # same columns, but empty table
    upgradelog.write("%s v10: complete\n" % time.ctime())


def db_v11(myDB, upgradelog):
    # keep last book image
    if not has_column(myDB, "authors", "LastBookImg"):
        lazylibrarian.UPDATE_MSG = 'Updating author table to hold last book image'
        upgradelog.write("%s v11: %s\n" % (time.ctime(), lazylibrarian.UPDATE_MSG))
        logger.debug(lazylibrarian.UPDATE_MSG)
        myDB.action('ALTER TABLE authors ADD COLUMN LastBookImg TEXT')
        books = myDB.select('SELECT AuthorID, AuthorName, LastBook from authors')

        if books:
            for book in books:
                lazylibrarian.UPDATE_MSG = 'Updating last book image for %s' % book['AuthorName']
                if book['LastBook']:
                    match = myDB.match(
                        'SELECT BookImg from books WHERE AuthorID=? AND BookName=?',
                        (book['AuthorID'], book['LastBook']))
                    if match:
                        myDB.action('UPDATE authors SET LastBookImg=? WHERE AuthorID=?',
                                    (match['BookImg'], book['AuthorID']))
        upgradelog.write("%s v11: %s\n" % (time.ctime(), lazylibrarian.UPDATE_MSG))
    upgradelog.write("%s v11: complete\n" % time.ctime())


def db_v12(myDB, upgradelog):
    # keep last magazine issue image
    if not has_column(myDB, "Magazines", "LatestCover"):
        lazylibrarian.UPDATE_MSG = 'Updating magazine table to hold last issue image'
        upgradelog.write("%s v12: %s\n" % (time.ctime(), lazylibrarian.UPDATE_MSG))
        logger.debug(lazylibrarian.UPDATE_MSG)
        myDB.action('ALTER TABLE magazines ADD COLUMN LatestCover TEXT')
        mags = myDB.select('SELECT Title, LastAcquired from magazines')

        if mags:
            for mag in mags:
                lazylibrarian.UPDATE_MSG = 'Updating last issue image for %s' % mag['Title']
                match = myDB.match(
                    'SELECT IssueFile from issues WHERE IssueAcquired=? AND Title=?',
                    (mag['LastAcquired'], mag['Title']))
                if match:
                    coverfile = os.path.splitext(match['IssueFile'])[0] + '.jpg'
                    if os.path.exists(coverfile):
                        myDB.action('UPDATE magazines SET LatestCover=? WHERE Title=?',
                                    (coverfile, mag['Title']))
        upgradelog.write("%s v12: %s\n" % (time.ctime(), lazylibrarian.UPDATE_MSG))
    upgradelog.write("%s v12: complete\n" % time.ctime())


def db_v13(myDB, upgradelog):
    if not has_column(myDB, "authors", "Manual"):
        lazylibrarian.UPDATE_MSG = 'Updating authors table to hold Manual setting'
        upgradelog.write("%s v13: %s\n" % (time.ctime(), lazylibrarian.UPDATE_MSG))
        logger.debug(lazylibrarian.UPDATE_MSG)
        myDB.action('ALTER TABLE authors ADD COLUMN Manual TEXT')
    upgradelog.write("%s v13: complete\n" % time.ctime())


def db_v14(myDB, upgradelog):
    upgradelog.write("%s v14: %s\n" % (time.ctime(), "Moving image caches"))
    src = lazylibrarian.CACHEDIR
    try:
        os.mkdir(os.path.join(src, 'author'))
    except OSError as e:
        if e.errno is not 17:  # already exists is ok
            msg = 'mkdir author cache reports: %s' % str(e)
            logger.debug(msg)
            upgradelog.write("%s v14: %s\n" % (time.ctime(), msg))

    query = 'SELECT AuthorName, AuthorID, AuthorImg FROM authors '
    query += 'WHERE AuthorImg LIKE "cache/%" '
    query += 'AND AuthorImg NOT LIKE "cache/author/%"'

    images = myDB.select(query)
    if images:
        tot = len(images)
        msg = 'Moving %s author images to new location' % tot
        logger.debug(msg)
        upgradelog.write("%s v14: %s\n" % (time.ctime(), msg))
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
                        myDB.action(
                            'UPDATE authors SET AuthorImg="cache/author/?" WHERE AuthorID=?',
                            (img, image['AuthorID']))
                    except Exception as e:
                        logger.error("dbupgrade: %s %s" % (type(e).__name__, str(e)))
            except Exception as e:
                msg = 'Failed to update author image for %s: %s %s' % (image['AuthorName'], type(e).__name__, str(e))
                logger.warn(msg)
                upgradelog.write("%s v14: %s\n" % (time.ctime(), msg))
        upgradelog.write("%s v14: %s\n" % (time.ctime(), lazylibrarian.UPDATE_MSG))
        logger.debug("Author Image cache updated")

    try:
        os.mkdir(os.path.join(src, 'book'))
    except OSError as e:
        if e.errno is not 17:  # already exists is ok
            msg = 'mkdir book cache reports: %s' % str(e)
            logger.debug(msg)
            upgradelog.write("%s v14: %s\n" % (time.ctime(), msg))

    query = 'SELECT BookName, BookID, BookImg FROM books '
    query += 'WHERE BookImg LIKE "cache/%" '
    query += 'AND BookImg NOT LIKE "cache/book/%"'
    images = myDB.select(query)

    if images:
        tot = len(images)
        msg = 'Moving %s book images to new location' % tot
        upgradelog.write("%s v14: %s\n" % (time.ctime(), msg))
        logger.debug(msg)
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
                        myDB.action('UPDATE books SET BookImg="cache/book/?" WHERE BookID=?',
                                    (img, image['BookID']))
                    except Exception as e:
                        logger.error("dbupgrade: %s %s" % (type(e).__name__, str(e)))
            except Exception as e:
                logger.warn('Failed to update book image for %s: %s %s' %
                            (image['BookName'], type(e).__name__, str(e)))
        upgradelog.write("%s v14: %s\n" % (time.ctime(), lazylibrarian.UPDATE_MSG))
        logger.debug("Book Image cache updated")

    # at this point there should be no more .jpg files in the root of the cachedir
    # any that are still there are for books/authors deleted from database
    # or magazine latest issue cover files that get copied as required
    for image in os.listdir(makeBytestr(src)):
        image = makeUnicode(image)
        if image.endswith('.jpg'):
            os.remove(os.path.join(src, image))
    upgradelog.write("%s v14: complete\n" % time.ctime())


def db_v15(myDB, upgradelog):
    myDB.action('CREATE TABLE IF NOT EXISTS series (SeriesID INTEGER PRIMARY KEY, SeriesName TEXT, \
                        AuthorID TEXT, Status TEXT)')
    myDB.action('CREATE TABLE IF NOT EXISTS member (SeriesID INTEGER, BookID TEXT, SeriesNum TEXT)')
    if has_column(myDB, "books", "SeriesNum"):
        lazylibrarian.UPDATE_MSG = 'Removing seriesnum from books table'
        myDB.action('CREATE TABLE IF NOT EXISTS temp_table (AuthorID TEXT, AuthorName TEXT, \
                    AuthorLink TEXT, BookName TEXT, BookSub TEXT, BookDesc TEXT, BookGenre TEXT, BookIsbn TEXT, \
                    BookPub TEXT, BookRate INTEGER, BookImg TEXT, BookPages INTEGER, BookLink TEXT, \
                    BookID TEXT UNIQUE, BookFile TEXT, BookDate TEXT, BookLang TEXT, BookAdded TEXT, Status TEXT, \
                    Series TEXT, WorkPage TEXT, Manual TEXT)')
        myDB.action('INSERT INTO temp_table SELECT AuthorID, AuthorName, AuthorLink, BookName, \
                    BookSub, BookDesc, BookGenre, BookIsbn, BookPub, BookRate, BookImg, BookPages, BookLink, BookID, \
                    BookFile, BookDate, BookLang, BookAdded, Status, Series, WorkPage, Manual from books')
        myDB.action('DROP TABLE books')
        myDB.action('ALTER TABLE temp_table RENAME TO books')
        upgradelog.write("%s v15: %s\n" % (time.ctime(), lazylibrarian.UPDATE_MSG))
        lazylibrarian.UPDATE_MSG = 'Reorganisation of books table complete'
    upgradelog.write("%s v15: complete\n" % time.ctime())


def db_v16(myDB, upgradelog):
    if has_column(myDB, "books", "AuthorLink"):
        lazylibrarian.UPDATE_MSG = 'Removing series, authorlink and authorname from books table'
        upgradelog.write("%s v16: %s\n" % (time.ctime(), lazylibrarian.UPDATE_MSG))
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
        upgradelog.write("%s v16: %s\n" % (time.ctime(), lazylibrarian.UPDATE_MSG))
    upgradelog.write("%s v16: complete\n" % time.ctime())


def db_v17(myDB, upgradelog):
    if has_column(myDB, "series", "AuthorID"):
        lazylibrarian.UPDATE_MSG = 'Creating seriesauthors table'
        upgradelog.write("%s v17: %s\n" % (time.ctime(), lazylibrarian.UPDATE_MSG))
        # In this version of the database there is only one author per series
        # so use that as starting point
        myDB.action('CREATE TABLE IF NOT EXISTS seriesauthors (SeriesID INTEGER, AuthorID TEXT, \
                                    UNIQUE (SeriesID,AuthorID))')
        series = myDB.select('SELECT SeriesID,AuthorID from series')
        cnt = 0
        tot = len(series)
        for item in series:
            cnt += 1
            lazylibrarian.UPDATE_MSG = "Updating seriesauthors: %s of %s" % (cnt, tot)
            if item['AuthorID']:
                myDB.action('insert into seriesauthors (SeriesID, AuthorID) values (?, ?)',
                            (item['SeriesID'], item['AuthorID']), suppress='UNIQUE')

        myDB.action('DROP TABLE IF EXISTS temp_table')
        myDB.action(
            'CREATE TABLE temp_table (SeriesID INTEGER PRIMARY KEY, SeriesName TEXT, Status TEXT)')
        myDB.action('INSERT INTO temp_table SELECT  SeriesID, SeriesName, Status FROM series \
                                    WHERE AuthorID IS NOT NULL')
        myDB.action('DROP TABLE series')
        myDB.action('ALTER TABLE temp_table RENAME TO series')
        lazylibrarian.UPDATE_MSG = 'Reorganisation of series table complete'
        upgradelog.write("%s v17: %s\n" % (time.ctime(), lazylibrarian.UPDATE_MSG))
    upgradelog.write("%s v17: complete\n" % time.ctime())


def db_v18(myDB, upgradelog):
    data = myDB.match('pragma index_list(seriesauthors)')
    if not data:
        lazylibrarian.UPDATE_MSG = 'Adding unique constraint to seriesauthors table'
        upgradelog.write("%s v18: %s\n" % (time.ctime(), lazylibrarian.UPDATE_MSG))
        myDB.action('DROP TABLE IF EXISTS temp_table')
        myDB.action('ALTER TABLE seriesauthors RENAME to temp_table')
        myDB.action(
            'CREATE TABLE seriesauthors (SeriesID INTEGER, AuthorID TEXT, UNIQUE (SeriesID,AuthorID))')
        series = myDB.select('SELECT SeriesID,AuthorID from temp_table')
        cnt = 0
        tot = len(series)
        for item in series:
            cnt += 1
            lazylibrarian.UPDATE_MSG = "Updating seriesauthors: %s of %s" % (cnt, tot)
            myDB.action('insert into seriesauthors (SeriesID, AuthorID) values (?, ?)',
                        (item['SeriesID'], item['AuthorID']), suppress='UNIQUE')
        myDB.action('DROP TABLE temp_table')
        lazylibrarian.UPDATE_MSG = 'Reorganisation of seriesauthors complete'
        upgradelog.write("%s v18: %s\n" % (time.ctime(), lazylibrarian.UPDATE_MSG))
    upgradelog.write("%s v18: complete\n" % time.ctime())


def db_v19(myDB, upgradelog):
    if not has_column(myDB, "books", "SeriesDisplay"):
        lazylibrarian.UPDATE_MSG = 'Adding series display to book table'
        upgradelog.write("%s v19: %s\n" % (time.ctime(), lazylibrarian.UPDATE_MSG))
        myDB.action('ALTER TABLE books ADD COLUMN SeriesDisplay TEXT')
        books = myDB.select('SELECT BookID from books')
        if books:
            cnt = 0
            tot = len(books)
            for book in books:
                cnt += 1
                lazylibrarian.UPDATE_MSG = "Updating series display: %s of %s" % (cnt, tot)
                cmd = 'SELECT SeriesName,SeriesNum from series,member WHERE '
                cmd += 'series.SeriesID = member.SeriesID and member.BookID=?'

                whichseries = myDB.select(cmd, (book['BookID'],))

                series = ''
                for item in whichseries:
                    newseries = "%s %s" % (item['SeriesName'], item['SeriesNum'])
                    newseries.strip()
                    if series and newseries:
                        series += '<br>'
                    series += newseries

                myDB.action('UPDATE books SET SeriesDisplay=? WHERE BookID=?',
                            (series, book['BookID']))

        lazylibrarian.UPDATE_MSG = 'Reorganisation of series display complete'
        upgradelog.write("%s v19: %s\n" % (time.ctime(), lazylibrarian.UPDATE_MSG))
    upgradelog.write("%s v19: complete\n" % time.ctime())


def db_v20(myDB, upgradelog):
    if not has_column(myDB, "books", "BookLibrary"):
        lazylibrarian.UPDATE_MSG = 'Adding BookLibrary to book table'
        upgradelog.write("%s v20: %s\n" % (time.ctime(), lazylibrarian.UPDATE_MSG))
        myDB.action('ALTER TABLE books ADD COLUMN BookLibrary TEXT')

        lazylibrarian.UPDATE_MSG = 'Updating BookLibrary dates'
        upgradelog.write("%s v20: %s\n" % (time.ctime(), lazylibrarian.UPDATE_MSG))
        books = myDB.select('SELECT BookID,BookFile from books')
        cnt = 0
        mod = 0
        if books:
            tot = len(books)
            for book in books:
                cnt += 1
                lazylibrarian.UPDATE_MSG = "Updating BookLibrary date: %s of %s" % (cnt, tot)
                if book['BookFile'] and os.path.isfile(book['BookFile']):
                    mod += 1
                    t = os.path.getctime(book['BookFile'])
                    filedate = datetime.datetime.utcfromtimestamp(int(t)).strftime("%Y-%m-%d %H:%M:%S")
                    myDB.action('UPDATE books SET BookLibrary=? WHERE BookID=?',
                                (filedate, book['BookID']))

            lazylibrarian.UPDATE_MSG = 'Adding BookLibrary date complete, %s/%s books' % (mod, cnt)
            upgradelog.write("%s v20: %s\n" % (time.ctime(), lazylibrarian.UPDATE_MSG))
    upgradelog.write("%s v20: complete\n" % time.ctime())


def db_v21(myDB, upgradelog):
    if not has_column(myDB, "books", "AudioLibrary"):
        lazylibrarian.UPDATE_MSG = 'Adding AudioBook support to book table'
        upgradelog.write("%s v21: %s\n" % (time.ctime(), lazylibrarian.UPDATE_MSG))
        myDB.action('ALTER TABLE books ADD COLUMN AudioFile TEXT')
        myDB.action('ALTER TABLE books ADD COLUMN AudioLibrary TEXT')
        myDB.action('ALTER TABLE books ADD COLUMN AudioStatus TEXT')
        myDB.action('UPDATE books SET AudioStatus="Skipped"')
        lazylibrarian.UPDATE_MSG = 'Creating downloads table'
        upgradelog.write("%s v21: %s\n" % (time.ctime(), lazylibrarian.UPDATE_MSG))
        myDB.action('CREATE TABLE IF NOT EXISTS downloads (Count INTEGER, Provider TEXT)')
        downloads = myDB.select('SELECT NZBprov from wanted WHERE Status="Processed"')
        for download in downloads:
            entry = myDB.match('SELECT Count FROM downloads where Provider=?', (download['NZBprov'],))
            if entry:
                counter = int(entry['Count'])
                myDB.action('UPDATE downloads SET Count=? WHERE Provider=?',
                            (counter + 1, download['NZBprov']))
            else:
                myDB.action('INSERT into downloads (Count, Provider) VALUES  (?, ?)',
                            (1, download['NZBprov']))
    upgradelog.write("%s v21: complete\n" % time.ctime())


def db_v22(myDB, upgradelog):
    if not has_column(myDB, "authors", "GRfollow"):
        lazylibrarian.UPDATE_MSG = 'Adding Goodreads Follow support to author table'
        upgradelog.write("%s v22: %s\n" % (time.ctime(), lazylibrarian.UPDATE_MSG))
        myDB.action('ALTER TABLE authors ADD COLUMN GRfollow TEXT')
    upgradelog.write("%s v22: complete\n" % time.ctime())


def db_v23(myDB, upgradelog):
    if not has_column(myDB, "users", "Perms"):
        lazylibrarian.UPDATE_MSG = 'Adding Users table'
        upgradelog.write("%s v23: %s\n" % (time.ctime(), lazylibrarian.UPDATE_MSG))
        cmd = 'CREATE TABLE IF NOT EXISTS users '
        cmd += '(UserID TEXT UNIQUE, UserName TEXT UNIQUE, Password TEXT, Email TEXT, '
        cmd += 'Name TEXT, Perms INTEGER)'
        myDB.action(cmd)
        cmd = 'INSERT into users (UserID, UserName, Name, Password, Email, Perms) VALUES (?, ?, ?, ?, ?, ?)'
        user = lazylibrarian.CONFIG['HTTP_USER']
        pwd = lazylibrarian.CONFIG['HTTP_PASS']
        email = lazylibrarian.CONFIG['ADMIN_EMAIL']
        name = 'admin'
        if not user or not pwd:
            user = 'admin'
            pwd = 'admin'
        myDB.action(cmd, (pwd_generator(), user, name, md5_utf8(pwd), email,
                          lazylibrarian.perm_admin))
        logger.debug('Added admin user %s' % user)
    upgradelog.write("%s v23: complete\n" % time.ctime())


def db_v24(myDB, upgradelog):
    if not has_column(myDB, "users", "HaveRead"):
        lazylibrarian.UPDATE_MSG = 'Adding read lists to Users table'
        upgradelog.write("%s v24: %s\n" % (time.ctime(), lazylibrarian.UPDATE_MSG))
        myDB.action('ALTER TABLE users ADD COLUMN HaveRead TEXT')
        myDB.action('ALTER TABLE users ADD COLUMN ToRead TEXT')
    upgradelog.write("%s v24: complete\n" % time.ctime())


def db_v25(myDB, upgradelog):
    myDB.action('CREATE INDEX IF NOT EXISTS issues_Title_index ON issues (Title)')
    myDB.action('CREATE INDEX IF NOT EXISTS books_index_authorid ON books(AuthorID)')
    upgradelog.write("%s v25: complete\n" % time.ctime())


def db_v26(myDB, upgradelog):
    if not has_column(myDB, "sync", "UserID"):
        lazylibrarian.UPDATE_MSG = 'Adding sync table'
        upgradelog.write("%s v26: %s\n" % (time.ctime(), lazylibrarian.UPDATE_MSG))
        myDB.action('CREATE TABLE IF NOT EXISTS sync (UserID TEXT, Label TEXT, Date TEXT, SyncList TEXT)')
    upgradelog.write("%s v26: complete\n" % time.ctime())


def db_v27(myDB, upgradelog):
    myDB.action('CREATE INDEX IF NOT EXISTS books_index_status ON books(Status)')
    myDB.action('CREATE INDEX IF NOT EXISTS authors_index_status ON authors(Status)')
    myDB.action('CREATE INDEX IF NOT EXISTS wanted_index_status ON wanted(Status)')
    upgradelog.write("%s v27: complete\n" % time.ctime())


def db_v28(myDB, upgradelog):
    if not has_column(myDB, "users", "CalibreRead"):
        lazylibrarian.UPDATE_MSG = 'Adding Calibre column names to Users table'
        upgradelog.write("%s v28: %s\n" % (time.ctime(), lazylibrarian.UPDATE_MSG))
        myDB.action('ALTER TABLE users ADD COLUMN CalibreRead TEXT')
        myDB.action('ALTER TABLE users ADD COLUMN CalibreToRead TEXT')
    upgradelog.write("%s v28: complete\n" % time.ctime())


def calc_eta(start_time, start_count, done):
    percent_done = done * 100 / start_count
    if not percent_done:
        secs_left = start_count * 1.5
    else:
        time_elapsed = time.time() - start_time
        secs_per_percent = time_elapsed / percent_done
        percent_left = 100 - percent_done
        secs_left = percent_left * secs_per_percent

    eta = int(secs_left / 60) + (secs_left % 60 > 0)
    if eta < 2:
        return "Completed %s%% eta %s minute" % (int(percent_done), eta)
    if eta < 120:
        return "Completed %s%% eta %s minutes" % (int(percent_done), eta)
    else:
        eta = int(secs_left / 3600) + (secs_left % 3600 > 0)
        return "Completed %s%% eta %s hours" % (int(percent_done), eta)


def db_v29(myDB, upgradelog):
    if not has_column(myDB, "books", "WorkID"):
        lazylibrarian.UPDATE_MSG = 'Adding WorkID to member and books tables'
        upgradelog.write("%s v29: %s\n" % (time.ctime(), lazylibrarian.UPDATE_MSG))
        myDB.action('ALTER TABLE books ADD COLUMN WorkID TEXT')
    if not has_column(myDB, "member", "WorkID"):
        myDB.action('ALTER TABLE member ADD COLUMN WorkID TEXT')
        myDB.action('DROP TABLE IF EXISTS temp_table')
        myDB.action('ALTER TABLE series RENAME TO temp_table')
        myDB.action('CREATE TABLE series (SeriesID INTEGER UNIQUE, SeriesName TEXT, Status TEXT)')
        myDB.action('INSERT INTO series SELECT SeriesID,SeriesName,Status FROM temp_table')
        myDB.action('DROP TABLE temp_table')
    if lazylibrarian.CONFIG['BOOK_API'] == 'GoodReads':
        authors = myDB.select('SELECT AuthorID,AuthorName,TotalBooks from authors WHERE Status != "Ignored"')
        books = myDB.match('SELECT sum(totalbooks) as total from authors  WHERE Status != "Ignored"')
        tot = len(authors)
        if tot:
            upgradelog.write("%s v29: Upgrading %s authors, %s books\n" % (time.ctime(), tot, books['total']))
            start_count = int(books['total']) + tot
            start_time = time.time()
            entries_done = 0
            myDB.action('DELETE FROM seriesauthors')
            cnt = 0
            for author in authors:
                cnt += 1
                expected_books = author['TotalBooks']
                if not expected_books:
                    expected_books = '0'
                lazylibrarian.UPDATE_MSG = "Updating %s (%s books): %s" % (author['AuthorName'], expected_books,
                                                                           calc_eta(start_time, start_count,
                                                                                    entries_done))
                addAuthorToDB(authorname=None, refresh=True, authorid=author['AuthorID'], addbooks=True)
                entries_done += int(expected_books)  # may have extra books now, don't overcount
                entries_done += 1   # one less author

        members = myDB.select('SELECT BookID from member')
        tot = len(members)
        if tot:
            upgradelog.write("%s v29: Upgrading %s series members\n" % (time.ctime(), tot))
            cnt = 0
            for member in members:
                cnt += 1
                lazylibrarian.UPDATE_MSG = "Updating series members %s of %s" % (cnt, tot)
                res = myDB.match('SELECT WorkID from books WHERE BookID=?', (member['BookID'],))
                if res:
                    myDB.action('UPDATE member SET WorkID=? WHERE BookID=?', (res['WorkID'], member['BookID']))
    upgradelog.write("%s v29: complete\n" % time.ctime())


def db_v30(myDB, upgradelog):
    if not has_column(myDB, "users", "BookType"):
        lazylibrarian.UPDATE_MSG = 'Adding BookType to Users table'
        upgradelog.write("%s v30: %s\n" % (time.ctime(), lazylibrarian.UPDATE_MSG))
        myDB.action('ALTER TABLE users ADD COLUMN BookType TEXT')
    upgradelog.write("%s v30: complete\n" % time.ctime())


def db_v31(myDB, upgradelog):
    if not has_column(myDB, "magazines", "DateType"):
        lazylibrarian.UPDATE_MSG = 'Adding DateType to Magazines table'
        upgradelog.write("%s v31: %s\n" % (time.ctime(), lazylibrarian.UPDATE_MSG))
        myDB.action('ALTER TABLE magazines ADD COLUMN DateType TEXT')
    upgradelog.write("%s v31: complete\n" % time.ctime())


def db_v32(myDB, upgradelog):
    if not has_column(myDB, "series", "Have"):
        lazylibrarian.UPDATE_MSG = 'Adding counters to Series table'
        upgradelog.write("%s v32: %s\n" % (time.ctime(), lazylibrarian.UPDATE_MSG))
        myDB.action('ALTER TABLE series ADD COLUMN Have TEXT')
        myDB.action('ALTER TABLE series ADD COLUMN Total TEXT')

    cmd = "select series.seriesid as Series,sum(case books.status when 'Ignored' then 0 else 1 end) as Total,"
    cmd += "sum(case when books.status == 'Have' then 1 when books.status == 'Open' then 1"
    cmd += " when books.audiostatus == 'Have' then 1 when books.audiostatus == 'Open' then 1"
    cmd += " else 0 end) as Have from books,member,series where member.bookid=books.bookid"
    cmd += " and member.seriesid = series.seriesid group by series.seriesid"
    series = myDB.select(cmd)
    tot = len(series)
    if tot:
        upgradelog.write("%s v32: Upgrading %s series counters\n" % (time.ctime(), tot))
        cnt = 0
        for entry in series:
            cnt += 1
            lazylibrarian.UPDATE_MSG = "Updating series counters %s of %s" % (cnt, tot)
            myDB.action('UPDATE series SET Have=?, Total=? WHERE SeriesID=?',
                        (entry['Have'], entry['Total'], entry['Series']))
    upgradelog.write("%s v32: complete\n" % time.ctime())
