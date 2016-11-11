from __future__ import with_statement

import os
import sqlite3
import threading
import time
import shutil
import lazylibrarian

from lazylibrarian import logger

db_lock = threading.Lock()


def dbupdate(db_current_version):

    conn = sqlite3.connect(lazylibrarian.DBFILE)
    c = conn.cursor()

    c.execute('PRAGMA user_version')
    result = c.fetchone()
    db_version = result[0]

    if db_version < db_current_version:
        lazylibrarian.UPDATE_MSG = 'Updating database to version %s, current version is %s' % (db_current_version, db_version)
        logger.info(lazylibrarian.UPDATE_MSG)
        myDB = DBConnection()

        if db_version < 1:
            c.execute('CREATE TABLE IF NOT EXISTS authors (AuthorID TEXT, AuthorName TEXT UNIQUE, AuthorImg TEXT, \
                 AuthorLink TEXT, DateAdded TEXT, Status TEXT, LastBook TEXT, LastLink Text, LastDate TEXT, \
                 HaveBooks INTEGER, TotalBooks INTEGER, AuthorBorn TEXT, AuthorDeath TEXT, UnignoredBooks INTEGER)')
            c.execute('CREATE TABLE IF NOT EXISTS books (AuthorID TEXT, AuthorName TEXT, AuthorLink TEXT, \
                BookName TEXT, BookSub TEXT, BookDesc TEXT, BookGenre TEXT, BookIsbn TEXT, BookPub TEXT, \
                BookRate INTEGER, BookImg TEXT, BookPages INTEGER, BookLink TEXT, BookID TEXT UNIQUE, BookFile TEXT, \
                BookDate TEXT, BookLang TEXT, BookAdded TEXT, Status TEXT, Series TEXT, SeriesNum TEXT, \
                WorkPage TEXT, Manual TEXT)')
            c.execute('CREATE TABLE IF NOT EXISTS wanted (BookID TEXT, NZBurl TEXT, NZBtitle TEXT, NZBdate TEXT, \
                NZBprov TEXT, Status TEXT, NZBsize TEXT, AuxInfo TEXT, NZBmode TEXT, Source TEXT, DownloadID TEXT)')
            c.execute('CREATE TABLE IF NOT EXISTS pastissues AS SELECT * FROM wanted')  # same columns
            c.execute('CREATE TABLE IF NOT EXISTS magazines (Title TEXT, Frequency TEXT, Regex TEXT, Status TEXT, \
                MagazineAdded TEXT, LastAcquired TEXT, IssueDate TEXT, IssueStatus TEXT)')
            c.execute('CREATE TABLE IF NOT EXISTS languages (isbn TEXT, lang TEXT)')
            c.execute('CREATE TABLE IF NOT EXISTS issues (Title TEXT, IssueID TEXT, IssueAcquired TEXT, IssueDate TEXT, \
                IssueFile TEXT)')
            c.execute('CREATE TABLE IF NOT EXISTS stats (authorname text, GR_book_hits int, GR_lang_hits int, \
                LT_lang_hits int, GB_lang_change, cache_hits int, bad_lang int, bad_char int, uncached int, duplicates int)')

        # These are the incremental changes before database versioning was introduced.
        # New database tables already have these incorporated so we need to check first...
            try:
                c.execute('SELECT BookSub from books')
            except sqlite3.OperationalError:
                lazylibrarian.UPDATE_MSG = 'Updating database to hold book subtitles.'
                logger.info(lazylibrarian.UPDATE_MSG)
                c.execute('ALTER TABLE books ADD COLUMN BookSub TEXT')

            try:
                c.execute('SELECT BookPub from books')
            except sqlite3.OperationalError:
                lazylibrarian.UPDATE_MSG = 'Updating database to hold book publisher'
                logger.info(lazylibrarian.UPDATE_MSG)
                c.execute('ALTER TABLE books ADD COLUMN BookPub TEXT')

            try:
                c.execute('SELECT BookGenre from books')
            except sqlite3.OperationalError:
                lazylibrarian.UPDATE_MSG = 'Updating database to hold bookgenre'
                logger.info(lazylibrarian.UPDATE_MSG)
                c.execute('ALTER TABLE books ADD COLUMN BookGenre TEXT')

            try:
                c.execute('SELECT BookFile from books')
            except sqlite3.OperationalError:
                lazylibrarian.UPDATE_MSG = 'Updating database to hold book filename'
                logger.info(lazylibrarian.UPDATE_MSG)
                c.execute('ALTER TABLE books ADD COLUMN BookFile TEXT')

            try:
                c.execute('SELECT AuxInfo from wanted')
            except sqlite3.OperationalError:
                lazylibrarian.UPDATE_MSG = 'Updating database to hold AuxInfo'
                logger.info(lazylibrarian.UPDATE_MSG)
                c.execute('ALTER TABLE wanted ADD COLUMN AuxInfo TEXT')

            try:
                c.execute('SELECT NZBsize from wanted')
            except sqlite3.OperationalError:
                lazylibrarian.UPDATE_MSG = 'Updating database to hold NZBsize'
                logger.info(lazylibrarian.UPDATE_MSG)
                c.execute('ALTER TABLE wanted ADD COLUMN NZBsize TEXT')

            try:
                c.execute('SELECT NZBmode from wanted')
            except sqlite3.OperationalError:
                lazylibrarian.UPDATE_MSG = 'Updating database to hold NZBmode'
                logger.info(lazylibrarian.UPDATE_MSG)
                c.execute('ALTER TABLE wanted ADD COLUMN NZBmode TEXT')

            try:
                c.execute('SELECT UnignoredBooks from authors')
            except sqlite3.OperationalError:
                lazylibrarian.UPDATE_MSG = 'Updating database to hold UnignoredBooks'
                logger.info(lazylibrarian.UPDATE_MSG)
                c.execute('ALTER TABLE authors ADD COLUMN UnignoredBooks INTEGER')

            try:
                c.execute('SELECT IssueStatus from magazines')
            except sqlite3.OperationalError:
                lazylibrarian.UPDATE_MSG = 'Updating database to hold IssueStatus'
                logger.info(lazylibrarian.UPDATE_MSG)
                c.execute('ALTER TABLE magazines ADD COLUMN IssueStatus TEXT')

            addedWorkPage = False
            try:
                c.execute('SELECT WorkPage from books')
            except sqlite3.OperationalError:
                lazylibrarian.UPDATE_MSG = 'Updating database to hold WorkPage'
                logger.info(lazylibrarian.UPDATE_MSG)
                c.execute('ALTER TABLE books ADD COLUMN WorkPage TEXT')
                addedWorkPage = True

            addedSeries = False
            try:
                c.execute('SELECT Series from books')
            except sqlite3.OperationalError:
                lazylibrarian.UPDATE_MSG = 'Updating database to hold Series'
                logger.info(lazylibrarian.UPDATE_MSG)
                c.execute('ALTER TABLE books ADD COLUMN Series TEXT')
                addedSeries = True

            # SeriesOrder shouldn't be an integer, some later written books
            # and novellas logically go inbetween books of the main series,
            # and their SeriesOrder is not an integer, eg 1.5
            # so we need to update SeriesOrder to store as text.
            # Because sqlite can't drop columns we create a new column SeriesNum,
            # inherit the old column values, and use SeriesNum instead
            try:
                c.execute('SELECT SeriesNum from books')
            except sqlite3.OperationalError:
                # no SeriesNum column, so create one
                lazylibrarian.UPDATE_MSG = 'Updating books to hold SeriesNum'
                logger.info(lazylibrarian.UPDATE_MSG)
                c.execute('ALTER TABLE books ADD COLUMN SeriesNum TEXT')
                c.execute('UPDATE books SET SeriesNum = SeriesOrder')
                c.execute('UPDATE books SET SeriesOrder = Null')

            addedIssues = False
            try:
                c.execute('SELECT Title from issues')
            except sqlite3.OperationalError:
                lazylibrarian.UPDATE_MSG = 'Updating database to hold Issues table'
                logger.info(lazylibrarian.UPDATE_MSG)
                c.execute(
                    'CREATE TABLE issues (Title TEXT, IssueID TEXT, IssueAcquired TEXT, IssueDate TEXT, IssueFile TEXT)')
                addedIssues = True
            try:
                c.execute('SELECT IssueID from issues')
            except sqlite3.OperationalError:
                lazylibrarian.UPDATE_MSG = 'Updating Issues table to hold IssueID'
                logger.info(lazylibrarian.UPDATE_MSG)
                c.execute('ALTER TABLE issues ADD COLUMN IssueID TEXT')
                addedIssues = True

            c.execute('DROP TABLE if exists capabilities')

            conn.commit()

            if addedIssues:
                try:
                    magazinescan.magazineScan(thread='MAIN')
                except Exception as e:
                    logger.debug("Failed to scan magazines, %s" % str(e))

            if addedWorkPage:
                try:
                    lazylibrarian.UPDATE_MSG = 'Adding WorkPage to existing books'
                    logger.info(lazylibrarian.UPDATE_MSG)
                    threading.Thread(target=bookwork.setWorkPages, name="ADDWORKPAGE", args=[]).start()
                except Exception as e:
                    logger.debug("Failed to update WorkPages, %s" % str(e))

            if addedSeries:
                try:
                    books = myDB.select('SELECT BookID, BookName FROM books')
                    if books:
                        lazylibrarian.UPDATE_MSG = 'Adding series to existing books'
                        logger.info(lazylibrarian.UPDATE_MSG)
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
                    logger.info('Error: ' + str(e))

        if db_version < 2:
            try:
                results = myDB.select('SELECT BookID,NZBsize FROM wanted WHERE NZBsize LIKE "% MB"')
                if results:
                    lazylibrarian.UPDATE_MSG = 'Removing units from wanted table'
                    logger.info(lazylibrarian.UPDATE_MSG)
                    tot = len(results)
                    cnt = 0
                    for units in results:
                        cnt += 1
                        lazylibrarian.UPDATE_MSG = 'Removing units from wanted table: %s of %s' % (cnt, tot)
                        nzbsize = units["NZBsize"]
                        nzbsize = nzbsize.split(' ')[0]
                        myDB.action('UPDATE wanted SET NZBsize = "%s" WHERE BookID = "%s"' % (nzbsize, units["BookID"]))

            except Exception as e:
                logger.info('Error: ' + str(e))

        if db_version < 3:
            try:
                c.execute('SELECT SeriesOrder from books')
                lazylibrarian.UPDATE_MSG = 'Removing SeriesOrder from books table'
                logger.info(lazylibrarian.UPDATE_MSG)
                try:
                    c.execute('CREATE TABLE IF NOT EXISTS temp_books (AuthorID TEXT, AuthorName TEXT, AuthorLink TEXT, \
                        BookName TEXT, BookSub TEXT, BookDesc TEXT, BookGenre TEXT, BookIsbn TEXT, BookPub TEXT, \
                        BookRate INTEGER, BookImg TEXT, BookPages INTEGER, BookLink TEXT, BookID TEXT UNIQUE, \
                        BookFile TEXT, BookDate TEXT, BookLang TEXT, BookAdded TEXT, Status TEXT, Series TEXT, \
                        SeriesNum TEXT, WorkPage TEXT)')
                    c.execute('INSERT INTO temp_books SELECT AuthorID,AuthorName,AuthorLink,BookName,BookSub, \
                        BookDesc,BookGenre,BookIsbn,BookPub,BookRate,BookImg,BookPages,BookLink,BookID, \
                        BookFile,BookDate,BookLang,BookAdded,Status,Series,SeriesNum,WorkPage FROM books')
                    c.execute('DROP TABLE books')
                    c.execute('ALTER TABLE temp_books RENAME TO books')
                    conn.commit()
                except sqlite3.OperationalError:
                    logger.warn('Failed to remove SeriesOrder from books table')
            except sqlite3.OperationalError:
                # if it's a new install there is no SeriesOrder column, so nothing to remove
                pass

            try:
                c.execute('SELECT BookID from pastissues')
            except sqlite3.OperationalError:
                lazylibrarian.UPDATE_MSG = 'Moving magazine past issues into new table'
                logger.info(lazylibrarian.UPDATE_MSG)
                c.execute(
                    'CREATE TABLE pastissues AS SELECT * FROM wanted WHERE Status="Skipped" AND length(AuxInfo) > 0')
                c.execute('DELETE FROM wanted WHERE Status="Skipped" AND length(AuxInfo) > 0')

        if db_version < 4:
            try:
                c.execute('SELECT duplicates from stats')
            except sqlite3.OperationalError:
                lazylibrarian.UPDATE_MSG = 'Updating stats table to hold duplicates'
                logger.info(lazylibrarian.UPDATE_MSG)
                c.execute('ALTER TABLE stats ADD COLUMN duplicates INT')

        if db_version < 5:
            issues = myDB.select(
                'SELECT IssueID,IssueDate from issues WHERE length(IssueDate) < 4 and length(IssueDate) > 0')
            if issues:
                lazylibrarian.UPDATE_MSG = 'Updating issues table to hold 4 digit issue numbers'
                logger.info(lazylibrarian.UPDATE_MSG)
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
                logger.info(lazylibrarian.UPDATE_MSG)
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
            try:
                c.execute('SELECT Manual from books')
            except sqlite3.OperationalError:
                lazylibrarian.UPDATE_MSG = 'Updating books table to hold Manual'
                logger.info(lazylibrarian.UPDATE_MSG)
                c.execute('ALTER TABLE books ADD COLUMN Manual TEXT')

        if db_version < 7:
            try:
                c.execute('SELECT Source from wanted')
            except sqlite3.OperationalError:
                lazylibrarian.UPDATE_MSG = 'Updating wanted table to hold Source and DownloadID'
                logger.info(lazylibrarian.UPDATE_MSG)
                c.execute('ALTER TABLE wanted ADD COLUMN Source TEXT')
                c.execute('ALTER TABLE wanted ADD COLUMN DownloadID TEXT')

        if db_version < 8:
            src = os.path.join(lazylibrarian.PROG_DIR, 'data/images/cache/')
            dst = lazylibrarian.CACHEDIR
            images = myDB.select('SELECT AuthorID, AuthorImg FROM authors WHERE AuthorImg LIKE "images/cache/%"')
            if images:
                logger.info('Moving author images to new location')
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
                            logger.warn("dbupdate: %s" % str(e))

            images = myDB.select('SELECT BookID, BookImg FROM books WHERE BookImg LIKE "images/cache/%"')
            if images:
                logger.info('Moving book images to new location')
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
                            logger.warn("dbupdate: %s" % str(e))

            logger.info("Image cache updated")

        lazylibrarian.UPDATE_MSG = 'Database updated to version %s' % db_current_version
        logger.info(lazylibrarian.UPDATE_MSG)
        c.execute('PRAGMA user_version = %s' % db_current_version)
        conn.commit()
        conn.close()

# Now do any non-version-specific tidying

        try:
            authors = myDB.select('SELECT AuthorID FROM authors WHERE AuthorName IS NULL')
            if authors:
                logger.info('Removing un-named authors from database')
                for author in authors:
                    authorid = author["AuthorID"]
                    myDB.action('DELETE from authors WHERE AuthorID="%s"' % authorid)
                    myDB.action('DELETE from books WHERE AuthorID="%s"' % authorid)
        except Exception as e:
            logger.info('Error: ' + str(e))


class DBConnection:

    def __init__(self):
        self.connection = sqlite3.connect(lazylibrarian.DBFILE, 20)
        self.connection.row_factory = sqlite3.Row

    def action(self, query, args=None):
        with db_lock:

            if not query:
                return

            sqlResult = None
            attempt = 0

            while attempt < 5:

                try:
                    if not args:
                        sqlResult = self.connection.execute(query)
                    else:
                        sqlResult = self.connection.execute(query, args)
                    self.connection.commit()
                    break

                except sqlite3.OperationalError as e:
                    if "unable to open database file" in e.message or "database is locked" in e.message:
                        logger.warn('Database Error: %s' % e)
                        attempt += 1
                        time.sleep(1)
                    else:
                        logger.error('Database error: %s' % e)
                        raise

                except sqlite3.DatabaseError as e:
                    logger.error('Fatal error executing %s :: %s' % (query, e))
                    raise

            return sqlResult

    def match(self, query, args=None):
        try:
            # if there are no results, action() returns None and .fetchone() fails
            sqlResults = self.action(query, args).fetchone()
        except Exception:
            return []
        if not sqlResults:
            return []

        return sqlResults

    def select(self, query, args=None):
        try:
            # if there are no results, action() returns None and .fetchall() fails
            sqlResults = self.action(query, args).fetchall()
        except Exception:
            return []
        if not sqlResults:
            return []

        return sqlResults

    def genParams(self, myDict):
        return [x + " = ?" for x in myDict.keys()]

    def upsert(self, tableName, valueDict, keyDict):
        changesBefore = self.connection.total_changes

        # genParams = lambda myDict: [x + " = ?" for x in myDict.keys()]

        query = "UPDATE " + tableName + " SET " + ", ".join(self.genParams(valueDict)) + \
            " WHERE " + " AND ".join(self.genParams(keyDict))

        self.action(query, valueDict.values() + keyDict.values())

        if self.connection.total_changes == changesBefore:
            query = "INSERT INTO " + tableName + " (" + ", ".join(valueDict.keys() + keyDict.keys()) + ")" + \
                " VALUES (" + ", ".join(["?"] * len(valueDict.keys() + keyDict.keys())) + ")"
            self.action(query, valueDict.values() + keyDict.values())
