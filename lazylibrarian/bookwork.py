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
import time

# noinspection PyUnresolvedReferences
from lib.six.moves.urllib_parse import quote_plus, quote, urlencode

import lazylibrarian
from lazylibrarian import logger, database
from lazylibrarian.cache import fetchURL, gr_xml_request
from lazylibrarian.common import proxyList
from lazylibrarian.formatter import safe_unicode, plural, cleanName, unaccented, formatAuthorName, \
    check_int
from lib.fuzzywuzzy import fuzz
from lib.six import PY2

try:
    import requests
except ImportError:
    import lib.requests as requests


def setAllBookAuthors():
    myDB = database.DBConnection()
    myDB.action('drop table if exists bookauthors')
    myDB.action('create table bookauthors (AuthorID TEXT, BookID TEXT, Role TEXT, UNIQUE (AuthorID, BookID, Role))')
    books = myDB.select('SELECT AuthorID,BookID from books')
    for item in books:
        myDB.action('insert into bookauthors (AuthorID, BookID, Role) values (?, ?, ?)',
                    (item['AuthorID'], item['BookID'], ''), suppress='UNIQUE')
    totalauthors = 0
    totalrefs = 0
    books = myDB.select('select bookid,bookname,authorid from books where workpage is not null and workpage != ""')
    for book in books:
        newauthors, newrefs = setBookAuthors(book)
        totalauthors += newauthors
        totalrefs += newrefs
    msg = "Added %s new authors to database, %s new bookauthors" % (totalauthors, totalrefs)
    logger.debug(msg)
    return totalauthors, totalrefs


def setBookAuthors(book):
    myDB = database.DBConnection()
    newauthors = 0
    newrefs = 0
    try:
        authorlist = getBookAuthors(book['bookid'])
        for author in authorlist:
            role = ''
            if 'id' in author:
                # it's a goodreads data source
                authorname = author['name']
                exists = myDB.match('select authorid from authors where authorid=?', (author['id'],))
                if 'role' in author:
                    role = author['role']
            else:
                # it's a librarything data source
                authorname = formatAuthorName(author['name'])
                exists = myDB.match('select authorid from authors where authorname=?', (authorname,))
                if 'type' in author:
                    authtype = author['type']
                    if authtype in ['primary author', 'main author', 'secondary author']:
                        role = authtype
                    elif author['role'] in ['Author', '&mdash;'] and author['work'] == 'all editions':
                        role = 'Author'
            if exists:
                authorid = exists['authorid']
            else:
                # try to add new author to database by name
                authorname, authorid, new = lazylibrarian.importer.addAuthorNameToDB(authorname, False, False)
                if new and authorid:
                    newauthors += 1
            if authorid:
                myDB.action('INSERT into bookauthors (AuthorID, BookID, Role) VALUES (?, ?, ?)',
                            (authorid, book['bookid'], role), suppress='UNIQUE')
                newrefs += 1
    except Exception as e:
        logger.error("Error parsing authorlist for %s: %s %s" % (book['bookname'], type(e).__name__, str(e)))
    return newauthors, newrefs


def setAllBookSeries():
    """ Try to set series details for all books """
    myDB = database.DBConnection()
    books = myDB.select('select BookID,WorkID from books where Manual is not "1"')
    counter = 0
    if books:
        logger.info('Checking series for %s book%s' % (len(books), plural(len(books))))
        for book in books:
            if lazylibrarian.CONFIG['BOOK_API'] == 'GoodReads':
                workid = book['WorkID']
            else:
                workid = book['BookID']
            serieslist = getWorkSeries(workid)
            if serieslist:
                counter += 1
                setSeries(serieslist, book['BookID'])
    deleteEmptySeries()
    msg = 'Updated %s book%s' % (counter, plural(counter))
    logger.info('Series check complete: ' + msg)
    return msg


def setSeries(serieslist=None, bookid=None):
    """ set series details in series/member tables from the supplied dict
        and a displayable summary in book table
        serislist is a tuple (SeriesID, SeriesNum, SeriesName) """
    myDB = database.DBConnection()
    if bookid:
        # delete any old series-member entries
        myDB.action('DELETE from member WHERE BookID=?', (bookid,))
        for item in serieslist:
            match = myDB.match('SELECT SeriesID from series where SeriesName=? COLLATE NOCASE', (item[2],))
            if match:
                seriesid = match['SeriesID']
            else:
                # new series, need to set status and get SeriesID
                if item[0]:
                    seriesid = item[0]
                else:
                    # no seriesid so generate it (row count + 1)
                    cnt = myDB.match("select count(*) as counter from series")
                    res = check_int(cnt['counter'], 0)
                    seriesid = str(res + 1)
                myDB.action('INSERT into series VALUES (?, ?, ?)', (seriesid, item[2], "Active"), suppress='UNIQUE')
                # don't ask what other books are in the series - leave for user to query if series wanted
                # _ = getSeriesMembers(match['SeriesID'])
            book = myDB.match('SELECT AuthorID,WorkID from books where BookID=?', (bookid,))
            if seriesid and book:
                controlValueDict = {"BookID": bookid, "SeriesID": seriesid}
                newValueDict = {"SeriesNum": item[1], "WorkID": book['WorkID']}
                myDB.upsert("member", newValueDict, controlValueDict)
                myDB.action('INSERT INTO seriesauthors ("SeriesID", "AuthorID") VALUES (?, ?)',
                            (seriesid, book['AuthorID']), suppress='UNIQUE')
            else:
                logger.debug('Unable to set series for book %s, %s' % (bookid, item))

        series = ''
        for item in serieslist:
            newseries = "%s %s" % (item[2], item[1])
            newseries.strip()
            if series and newseries:
                series += '<br>'
            series += newseries
        myDB.action('UPDATE books SET SeriesDisplay=? WHERE BookID=?', (series, bookid))


def setStatus(bookid=None, serieslist=None, default=None):
    """ Set the status of a book according to series/author/newbook/newauthor preferences
        return default if unchanged, default is passed in as newbook or newauthor status """
    myDB = database.DBConnection()
    if not bookid:
        return default

    match = myDB.match('SELECT Status,AuthorID,BookName from books WHERE BookID=?', (bookid,))
    if not match:
        return default

    # Don't update status if we already have the book but allow status change if ignored
    # might be we had ignore author set, but want to allow this series
    current_status = match['Status']
    if current_status in ['Have', 'Open']:
        return current_status

    new_status = ''
    authorid = match['AuthorID']
    bookname = match['BookName']
    # Is the book part of any series we want or don't want?
    for item in serieslist:
        match = myDB.match('SELECT Status from series where SeriesName=? COLLATE NOCASE', (item[2],))
        if match:
            if match['Status'] == 'Wanted':
                new_status = 'Wanted'
                logger.debug('Marking %s as %s, series %s' % (bookname, new_status, item[2]))
                break
            if match['Status'] == 'Skipped':
                new_status = 'Skipped'
                logger.debug('Marking %s as %s, series %s' % (bookname, new_status, item[2]))
                break

    if not new_status:
        # Author we want or don't want?
        match = myDB.match('SELECT Status from authors where AuthorID=?', (authorid,))
        if match:
            if match['Status'] in ['Paused', 'Ignored']:
                new_status = 'Skipped'
                logger.debug('Marking %s as %s, author %s' % (bookname, new_status, match['Status']))
            if match['Status'] == 'Wanted':
                new_status = 'Wanted'
                logger.debug('Marking %s as %s, author %s' % (bookname, new_status, match['Status']))

    # If none of these, leave default "newbook" or "newauthor" status
    if new_status:
        myDB.action('UPDATE books SET Status=? WHERE BookID=?', (new_status, bookid))
        return new_status

    return default


def deleteEmptySeries():
    """ remove any series from series table that have no entries in member table, return how many deleted """
    myDB = database.DBConnection()
    series = myDB.select('SELECT SeriesID,SeriesName from series')
    count = 0
    for item in series:
        match = myDB.match('SELECT BookID from member where SeriesID=?', (item['SeriesID'],))
        if not match:
            logger.debug('Deleting empty series %s' % item['SeriesName'])
            count += 1
            myDB.action('DELETE from series where SeriesID=?', (item['SeriesID'],))
    return count


def setWorkPages():
    """ Set the workpage link for any books that don't already have one """

    myDB = database.DBConnection()
    cmd = 'select BookID,AuthorName,BookName from books,authors where length(WorkPage) < 4'
    cmd += ' and books.AuthorID = authors.AuthorID'
    books = myDB.select(cmd)
    if books:
        logger.debug('Setting WorkPage for %s book%s' % (len(books), plural(len(books))))
        counter = 0
        for book in books:
            bookid = book['BookID']
            worklink = getWorkPage(bookid)
            if worklink:
                controlValueDict = {"BookID": bookid}
                newValueDict = {"WorkPage": worklink}
                myDB.upsert("books", newValueDict, controlValueDict)
                counter += 1
            else:
                logger.debug('No WorkPage found for %s: %s' % (book['AuthorName'], book['BookName']))
        msg = 'Updated %s page%s' % (counter, plural(counter))
        logger.debug("setWorkPages complete: " + msg)
    else:
        msg = 'No missing WorkPages'
        logger.debug(msg)
    return msg


def librarything_wait():
    """ Wait for a second between librarything api calls """
    time_now = time.time()
    delay = time_now - lazylibrarian.LAST_LIBRARYTHING
    if delay < 1.0:
        sleep_time = 1.0 - delay
        logger.debug("LibraryThing sleep %.3f" % sleep_time)
        time.sleep(sleep_time)
        lazylibrarian.LT_SLEEP += sleep_time
    lazylibrarian.LAST_LIBRARYTHING = time_now


# Feb 2018 librarything have disabled "whatwork"
# might only be temporary, but for now disable looking for new workpages
# and do not expire cached ones
ALLOW_NEW = False
LAST_NEW = 0


def getBookWork(bookID=None, reason=None, seriesID=None):
    """ return the contents of the LibraryThing workpage for the given bookid, or seriespage if seriesID given
        preferably from the cache. If not already cached cache the results
        Return None if no workpage/seriespage available """
    global ALLOW_NEW, LAST_NEW
    if not bookID and not seriesID:
        logger.error("getBookWork - No bookID or seriesID")
        return None

    if not reason:
        reason = ""

    myDB = database.DBConnection()
    if bookID:
        cmd = 'select BookName,AuthorName,BookISBN from books,authors where bookID=?'
        cmd += ' and books.AuthorID = authors.AuthorID'
        cacheLocation = "WorkCache"
        item = myDB.match(cmd, (bookID,))
    else:
        cmd = 'select SeriesName from series where SeriesID=?'
        cacheLocation = "SeriesCache"
        item = myDB.match(cmd, (seriesID,))
    if item:
        cacheLocation = os.path.join(lazylibrarian.CACHEDIR, cacheLocation)
        if bookID:
            workfile = os.path.join(cacheLocation, str(bookID) + '.html')
        else:
            workfile = os.path.join(cacheLocation, str(seriesID) + '.html')

        # does the workpage need to expire? For now only expire if it was an error page
        # (small file) or a series page as librarything might get better info over time, more series members etc
        if os.path.isfile(workfile):
            if seriesID or os.path.getsize(workfile) < 500:
                cache_modified_time = os.stat(workfile).st_mtime
                time_now = time.time()
                expiry = lazylibrarian.CONFIG['CACHE_AGE'] * 24 * 60 * 60  # expire cache after this many seconds
                if cache_modified_time < time_now - expiry:
                    # Cache entry is too old, delete it
                    if ALLOW_NEW:
                        os.remove(workfile)

        if os.path.isfile(workfile):
            # use cached file if possible to speed up refreshactiveauthors and librarysync re-runs
            lazylibrarian.CACHE_HIT = int(lazylibrarian.CACHE_HIT) + 1
            if bookID:
                if reason:
                    logger.debug("getBookWork: Returning Cached entry for %s %s" % (bookID, reason))
                else:
                    logger.debug("getBookWork: Returning Cached workpage for %s" % bookID)
            else:
                logger.debug("getBookWork: Returning Cached seriespage for %s" % item['seriesName'])

            if PY2:
                with open(workfile, "r") as cachefile:
                    source = cachefile.read()
            else:
                # noinspection PyArgumentList
                with open(workfile, "r", errors="backslashreplace") as cachefile:
                    source = cachefile.read()
            return source
        else:
            lazylibrarian.CACHE_MISS = int(lazylibrarian.CACHE_MISS) + 1
            if not ALLOW_NEW:
                # don't nag. Show message no more than every 12 hrs
                timenow = int(time.time())
                if check_int(LAST_NEW, 0) + 43200 < timenow:
                    logger.warn("New WhatWork is disabled")
                    LAST_NEW = timenow
                return None
            if bookID:
                title = safe_unicode(item['BookName'])
                author = safe_unicode(item['AuthorName'])
                if PY2:
                    title = title.encode(lazylibrarian.SYS_ENCODING)
                    author = author.encode(lazylibrarian.SYS_ENCODING)
                URL = 'http://www.librarything.com/api/whatwork.php?author=%s&title=%s' % \
                      (quote_plus(author), quote_plus(title))
            else:
                seriesname = safe_unicode(item['seriesName'])
                if PY2:
                    seriesname = seriesname.encode(lazylibrarian.SYS_ENCODING)
                URL = 'http://www.librarything.com/series/%s' % quote_plus(seriesname)

            librarything_wait()
            result, success = fetchURL(URL)
            if bookID and success:
                # noinspection PyBroadException
                try:
                    workpage = result.split('<link>')[1].split('</link>')[0]
                    librarything_wait()
                    result, success = fetchURL(workpage)
                except Exception:
                    try:
                        errmsg = result.split('<error>')[1].split('</error>')[0]
                    except IndexError:
                        errmsg = "Unknown Error"
                    # if no workpage link, try isbn instead
                    if item['BookISBN']:
                        URL = 'http://www.librarything.com/api/whatwork.php?isbn=' + item['BookISBN']
                        librarything_wait()
                        result, success = fetchURL(URL)
                        if success:
                            # noinspection PyBroadException
                            try:
                                workpage = result.split('<link>')[1].split('</link>')[0]
                                librarything_wait()
                                result, success = fetchURL(workpage)
                            except Exception:
                                # no workpage link found by isbn
                                try:
                                    errmsg = result.split('<error>')[1].split('</error>')[0]
                                except IndexError:
                                    errmsg = "Unknown Error"
                                # still cache if whatwork returned a result without a link, so we don't keep retrying
                                logger.debug("Librarything: [%s] for ISBN %s" % (errmsg, item['BookISBN']))
                                success = True
                    else:
                        # still cache if whatwork returned a result without a link, so we don't keep retrying
                        msg = "Librarything: [" + errmsg + "] for "
                        logger.debug(msg + item['AuthorName'] + ' ' + item['BookName'])
                        success = True
            if success:
                with open(workfile, "w") as cachefile:
                    cachefile.write(result)
                    if bookID:
                        logger.debug("getBookWork: Caching workpage for %s" % workfile)
                    else:
                        logger.debug("getBookWork: Caching series page for %s" % workfile)
                    # return None if we got an error page back
                    if '</request><error>' in result:
                        return None
                return result
            else:
                if bookID:
                    logger.debug("getBookWork: Unable to cache workpage, got %s" % result)
                else:
                    logger.debug("getBookWork: Unable to cache series page, got %s" % result)
            return None
    else:
        if bookID:
            logger.debug('Get Book Work - Invalid bookID [%s]' % bookID)
        else:
            logger.debug('Get Book Work - Invalid seriesID [%s]' % seriesID)
        return None


def getWorkPage(bookID=None):
    """ return the URL of the LibraryThing workpage for the given bookid
        or an empty string if no workpage available """
    if not bookID:
        logger.error("getWorkPage - No bookID")
        return ''
    work = getBookWork(bookID, "Workpage")
    if work:
        try:
            page = work.split('og:url')[1].split('="')[1].split('"')[0]
        except IndexError:
            return ''
        return page
    return ''


def getAllSeriesAuthors():
    """ For each entry in the series table, get a list of authors contributing to the series
        and import those authors (and their books) into the database """
    myDB = database.DBConnection()
    series = myDB.select('select SeriesID from series')
    if series:
        logger.debug('Getting series authors for %s series' % len(series))
        counter = 0
        total = 0
        for entry in series:
            seriesid = entry['SeriesID']
            result = getSeriesAuthors(seriesid)
            if result:
                counter += 1
                total += result
            else:
                logger.debug('No series info found for series %s' % seriesid)
        msg = 'Updated authors for %s series, added %s new author%s' % (counter, total, plural(total))
        logger.debug("Series pages complete: " + msg)
    else:
        msg = 'No entries in the series table'
        logger.debug(msg)
    return msg


def getBookAuthors(bookid):
    """ Get a list of authors contributing to a book from the goodreads bookpage or the librarything bookwork file """
    authorlist = []
    if lazylibrarian.CONFIG['BOOK_API'] == 'GoodReads':
        params = {"key": lazylibrarian.CONFIG['GR_API']}
        URL = 'https://www.goodreads.com/book/show/' + bookid + '?' + urlencode(params)
        try:
            rootxml, in_cache = gr_xml_request(URL)
            if rootxml is None:
                logger.debug("Error requesting book %s" % bookid)
                return []
        except Exception as e:
            logger.error("%s finding book %s: %s" % (type(e).__name__, bookid, str(e)))
            return []

        book = rootxml.find('book')
        authors = book.find('authors')
        anames = authors.getiterator('author')
        if anames is None:
            logger.warn('No authors found for %s' % bookid)
            return []
        for aname in anames:
            author = {}
            if aname.find('id') is not None:
                author['id'] = aname.find('id').text
            if aname.find('name') is not None:
                author['name'] = aname.find('name').text
            if aname.find('role') is not None:
                role = aname.find('role').text
                if not role:
                    role = ''
                author['role'] = role
            if author:
                authorlist.append(author)
    else:
        data = getBookWork(bookid, "Authors")
        if data:
            try:
                data = data.split('otherauthors_container')[1].split('</table>')[0].split('<table')[1].split('>', 1)[1]
            except IndexError:
                data = ''

        authorlist = []
        if data and 'Work?' in data:
            try:
                rows = data.split('<tr')
                for row in rows[2:]:
                    author = {}
                    col = row.split('<td>')
                    author['name'] = col[1].split('">')[1].split('<')[0]
                    author['role'] = col[2].split('<')[0]
                    author['type'] = col[3].split('<')[0]
                    author['work'] = col[4].split('<')[0]
                    author['status'] = col[5].split('<')[0]
                    authorlist.append(author)
            except IndexError:
                logger.debug('Error parsing authorlist for %s' % bookid)
    return authorlist


def getSeriesAuthors(seriesid):
    """ Get a list of authors contributing to a series
        and import those authors (and their books) into the database
        Return how many authors you added """
    myDB = database.DBConnection()
    result = myDB.match("select count(*) as counter from authors")
    start = int(result['counter'])
    result = myDB.match('select SeriesName from series where SeriesID=?', (seriesid,))
    seriesname = result['SeriesName']
    members = getSeriesMembers(seriesid)
    if members:
        myDB = database.DBConnection()
        for member in members:
            # order = member[0]
            bookname = member[1]
            authorname = member[2]
            # workid = member[3]
            authorid = member[4]

            if not authorid:
                # goodreads gives us all the info we need, librarything/google doesn't
                base_url = 'https://www.goodreads.com/search.xml?q='
                params = {"key": lazylibrarian.CONFIG['GR_API']}
                searchname = bookname + ' ' + authorname
                searchname = cleanName(unaccented(searchname))
                if PY2:
                    searchname = searchname.encode(lazylibrarian.SYS_ENCODING)
                searchterm = quote_plus(searchname)
                set_url = base_url + searchterm + '&' + urlencode(params)
                try:
                    rootxml, in_cache = gr_xml_request(set_url)
                    if rootxml is None:
                        logger.warn('Error getting XML for %s' % searchname)
                    else:
                        resultxml = rootxml.getiterator('work')
                        for item in resultxml:
                            try:
                                booktitle = item.find('./best_book/title').text
                            except (KeyError, AttributeError):
                                booktitle = ""
                            book_fuzz = fuzz.token_set_ratio(booktitle, bookname)
                            if book_fuzz >= 98:
                                try:
                                    author = item.find('./best_book/author/name').text
                                except (KeyError, AttributeError):
                                    author = ""
                                # try:
                                #     workid = item.find('./work/id').text
                                # except (KeyError, AttributeError):
                                #     workid = ""
                                try:
                                    authorid = item.find('./best_book/author/id').text
                                except (KeyError, AttributeError):
                                    authorid = ""
                                logger.debug("Author Search found %s %s, authorid %s" %
                                             (author, booktitle, authorid))
                                break
                    if not authorid:  # try again with title only
                        searchname = cleanName(unaccented(bookname))
                        if PY2:
                            searchname = searchname.encode(lazylibrarian.SYS_ENCODING)
                        searchterm = quote_plus(searchname)
                        set_url = base_url + searchterm + '&' + urlencode(params)
                        rootxml, in_cache = gr_xml_request(set_url)
                        if rootxml is None:
                            logger.warn('Error getting XML for %s' % searchname)
                        else:
                            resultxml = rootxml.getiterator('work')
                            for item in resultxml:
                                booktitle = item.find('./best_book/title').text
                                book_fuzz = fuzz.token_set_ratio(booktitle, bookname)
                                if book_fuzz >= 98:
                                    try:
                                        author = item.find('./best_book/author/name').text
                                    except (KeyError, AttributeError):
                                        author = ""
                                    # try:
                                    #     workid = item.find('./work/id').text
                                    # except (KeyError, AttributeError):
                                    #     workid = ""
                                    try:
                                        authorid = item.find('./best_book/author/id').text
                                    except (KeyError, AttributeError):
                                        authorid = ""
                                    logger.debug("Title Search found %s %s, authorid %s" %
                                                 (author, booktitle, authorid))
                                    break
                    if not authorid:
                        logger.warn("GoodReads doesn't know about %s %s" % (authorname, bookname))
                except Exception as e:
                    logger.error("Error finding goodreads results: %s %s" % (type(e).__name__, str(e)))

            if authorid:
                lazylibrarian.importer.addAuthorToDB(refresh=False, authorid=authorid)

    result = myDB.match("select count(*) as counter from authors")
    finish = int(result['counter'])
    newauth = finish - start
    logger.info("Added %s new author%s for %s" % (newauth, plural(newauth), seriesname))
    return newauth


def getSeriesMembers(seriesID=None):
    """ Ask librarything or goodreads for details on all books in a series
        order, bookname, authorname, workid, authorid
        (workid and authorid are goodreads only)
        Return as a list of lists """
    results = []
    if lazylibrarian.CONFIG['BOOK_API'] == 'GoodReads':
        params = {"format": "xml", "key": lazylibrarian.CONFIG['GR_API']}
        URL = 'https://www.goodreads.com/series/' + seriesID + '?' + urlencode(params)
        try:
            rootxml, in_cache = gr_xml_request(URL)
            if rootxml is None:
                logger.debug("Error requesting series %s" % seriesID)
                return []
        except Exception as e:
            logger.error("%s finding series %s: %s" % (type(e).__name__, seriesID, str(e)))
            return []

        works = rootxml.find('series/series_works')
        books = works.getiterator('series_work')
        if books is None:
            logger.warn('No books found for %s' % seriesID)
            return []
        for book in books:
            mydict = {}
            for mykey, location in [('order', 'user_position'),
                                    ('bookname', 'work/best_book/title'),
                                    ('authorname', 'work/best_book/author/name'),
                                    ('workid', 'work/id'),
                                    ('authorid', 'work/best_book/author/id')
                                    ]:
                if book.find(location) is not None:
                    mydict[mykey] = book.find(location).text
                else:
                    mydict[mykey] = ""
            results.append([mydict['order'], mydict['bookname'], mydict['authorname'],
                            mydict['workid'], mydict['authorid']])
    else:
        data = getBookWork(None, "SeriesPage", seriesID)
        if data:
            try:
                table = data.split('class="worksinseries"')[1].split('</table>')[0]
                rows = table.split('<tr')
                for row in rows:
                    if 'href=' in row:
                        booklink = row.split('href="')[1]
                        bookname = booklink.split('">')[1].split('<')[0]
                        # booklink = booklink.split('"')[0]
                        try:
                            authorlink = row.split('href="')[2]
                            authorname = authorlink.split('">')[1].split('<')[0]
                            # authorlink = authorlink.split('"')[0]
                            order = row.split('class="order">')[1].split('<')[0]
                            results.append([order, bookname, authorname, '', ''])
                        except IndexError:
                            logger.debug('Incomplete data in series table for series %s' % seriesID)
            except IndexError:
                if 'class="worksinseries"' in data:  # error parsing, or just no series data available?
                    logger.debug('Error in series table for series %s' % seriesID)
    return results


def getWorkSeries(bookID=None):
    """ Return the series names and numbers in series for the given id as a list of tuples
        For goodreads the id is a WorkID, for librarything it's a BookID """
    myDB = database.DBConnection()
    serieslist = []
    if not bookID:
        logger.error("getWorkSeries - No bookID")
        return serieslist

    if lazylibrarian.CONFIG['BOOK_API'] == 'GoodReads':
        URL = "https://www.goodreads.com/work/"
        seriesurl = URL + bookID + "/series?format=xml&key=" + lazylibrarian.CONFIG['GR_API']

        rootxml, in_cache = gr_xml_request(seriesurl)
        if rootxml is None:
            logger.warn('Error getting XML for %s' % seriesurl)
        else:
            resultxml = rootxml.getiterator('series_work')
            for item in resultxml:
                try:
                    seriesname = item.find('./series/title').text
                    seriesname = seriesname.strip('\n').strip('\n').strip()
                    seriesid = item.find('./series/id').text
                    seriesnum = item.find('./user_position').text
                except (KeyError, AttributeError):
                    continue
                if seriesname and seriesid:
                    seriesname = cleanName(unaccented(seriesname), '&/')
                    seriesnum = cleanName(unaccented(seriesnum))
                    serieslist.append((seriesid, seriesnum, seriesname))
                    match = myDB.match('SELECT SeriesID from series WHERE SeriesName=?', (seriesname,))
                    if not match:
                        myDB.action('INSERT INTO series VALUES (?, ?, ?)', (seriesid, seriesname, "Active"))
                    elif match['SeriesID'] != seriesid:
                        myDB.action('UPDATE series SET SeriesID=? WHERE SeriesName=?', (seriesid, seriesname))
    else:
        work = getBookWork(bookID, "Series")
        if work:
            try:
                slist = work.split('<h3><b>Series:')[1].split('</h3>')[0].split('<a href="/series/')
                for item in slist[1:]:
                    try:
                        series = item.split('">')[1].split('</a>')[0]
                        if series and '(' in series:
                            seriesnum = series.split('(')[1].split(')')[0].strip()
                            series = series.split(' (')[0].strip()
                        else:
                            seriesnum = ''
                            series = series.strip()
                        seriesname = cleanName(unaccented(series), '&/')
                        seriesnum = cleanName(unaccented(seriesnum))
                        serieslist.append(('', seriesnum, seriesname))
                    except IndexError:
                        pass
            except IndexError:
                pass

    return serieslist


def thingLang(isbn):
    # try searching librarything for a language code using the isbn
    # if no language found, librarything return value is "invalid" or "unknown"
    # librarything returns plain text, not xml
    BOOK_URL = 'http://www.librarything.com/api/thingLang.php?isbn=' + isbn
    proxies = proxyList()
    booklang = ''
    try:
        librarything_wait()
        timeout = check_int(lazylibrarian.CONFIG['HTTP_TIMEOUT'], 30)
        r = requests.get(BOOK_URL, timeout=timeout, proxies=proxies)
        resp = r.text
        logger.debug("LibraryThing reports language [%s] for %s" % (resp, isbn))
        if resp != 'invalid' and resp != 'unknown':
            booklang = resp
    except Exception as e:
        logger.error("%s finding language: %s" % (type(e).__name__, str(e)))
    finally:
        return booklang


def isbn_from_words(words):
    """Use Google to get an ISBN from words from title and author's name."""
    baseurl = "http://www.google.com/search?q=ISBN+"
    if not PY2:
        search_url = baseurl + quote(words.replace(' ', '+'))
    else:
        search_url = baseurl + words.replace(' ', '+')

    headers = {'User-Agent': 'w3m/0.5.3',
               'Content-Type': 'text/plain; charset="UTF-8"',
               'Content-Transfer-Encoding': 'Quoted-Printable',
               }
    content, success = fetchURL(search_url, headers=headers)
    # noinspection Annotator
    RE_ISBN13 = re.compile(r'97[89]{1}(?:-?\d){10,16}|97[89]{1}[- 0-9]{10,16}')
    RE_ISBN10 = re.compile(r'ISBN\x20(?=.{13}$)\d{1,5}([- ])\d{1,7}'
                           r'\1\d{1,6}\1(\d|X)$|[- 0-9X]{10,16}')

    # take the first answer that's a plain isbn, no spaces, dashes etc.
    res = RE_ISBN13.findall(content)
    for item in res:
        if len(item) == 13:
            return item

    res = RE_ISBN10.findall(content)
    for item in res:
        if len(item) == 10:
            return item

    logger.debug('No ISBN found for %s' % words)
    return None
