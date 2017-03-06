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
import shutil
import time
import urllib

import lazylibrarian
from lazylibrarian import logger, database
from lazylibrarian.cache import cache_img, fetchURL
from lazylibrarian.formatter import safe_unicode, plural


def getAuthorImages():
    """ Try to get an author image for all authors without one"""
    myDB = database.DBConnection()
    authors = myDB.select('select AuthorID, AuthorName from authors where AuthorImg like "%nophoto%" and Manual is not "1"')
    if authors:
        logger.info('Checking images for %s author%s' % (len(authors), plural(len(authors))))
        counter = 0
        for author in authors:
            authorid = author['AuthorID']
            imagelink = getAuthorImage(authorid)
            if imagelink and "nophoto" not in imagelink:
                logger.debug('Updating %s image to %s' % (author['AuthorName'], imagelink))
                controlValueDict = {"AuthorID": authorid}
                newValueDict = {"AuthorImg": imagelink}
                myDB.upsert("authors", newValueDict, controlValueDict)
                counter += 1
        logger.info('Author Image check complete, updated %s image%s' % (counter, plural(counter)))
    else:
        logger.debug('No missing author images')


def getBookCovers():
    """ Try to get a cover image for all books """

    myDB = database.DBConnection()
    books = myDB.select('select BookID,BookImg from books where BookImg like "%nocover%" and Manual is not "1"')
    if books:
        logger.info('Checking covers for %s book%s' % (len(books), plural(len(books))))
        counter = 0
        for book in books:
            bookid = book['BookID']
            coverlink = getBookCover(bookid)
            if coverlink and "nocover" not in coverlink:
                controlValueDict = {"BookID": bookid}
                newValueDict = {"BookImg": coverlink}
                myDB.upsert("books", newValueDict, controlValueDict)
                counter += 1
        logger.info('Cover check complete, updated %s cover%s' % (counter, plural(counter)))
    else:
        logger.debug('No missing book covers')


def setAllBookSeries():
    """ Try to set series details for all books from workpages"""
    myDB = database.DBConnection()
    books = myDB.select('select BookID from books where Manual is not "1"')
    counter = 0
    if books:
        logger.info('Checking series for %s book%s' % (len(books), plural(len(books))))
        for book in books:
            bookid = book['BookID']
            seriesdict = getWorkSeries(bookid)
            if seriesdict:
                counter += 1
                setSeries(seriesdict, bookid)
    logger.info('Series check complete, updated %s book%s' % (counter, plural(counter)))

def setSeries(seriesdict=None, bookid=None):
    """ set series details in booktable and series/member tables from the supplied dict """
    myDB = database.DBConnection()
    if bookid:
        # delete any old entries
        myDB.action('DELETE from member WHERE Bookid=%s' % bookid)
        series = ''
        for item in seriesdict:
            # keep all series in the book table for speed
            newseries = "%s %s" % (item, seriesdict[item])
            newseries.strip()
            if series:
                series += '<br>'
            series += newseries
            # and each series in the series and member tables for searching
            match = myDB.match('SELECT SeriesID from series where SeriesName="%s"' % item)
            book = myDB.match('SELECT BookName, AuthorID from books where BookID=%s' % bookid)
            if not match:
                # new series, need to set status and get SeriesID
                myDB.action('INSERT into series (SeriesName, AuthorID, Status) VALUES ("%s", "%s", "Active")' %
                            (item, book['AuthorID']))
                match = myDB.match('SELECT SeriesID from series where SeriesName="%s"' % item)
            controlValueDict = {"BookID": bookid, "SeriesID": match['SeriesID']}
            newValueDict = {"SeriesNum": seriesdict[item]}
            myDB.upsert("member", newValueDict, controlValueDict)
        controlValueDict = {"BookID": bookid}
        newValueDict = {"Series": series}
        myDB.upsert("books", newValueDict, controlValueDict)
        deleteEmptySeries()


def deleteEmptySeries():
    """ remove any series from series table that have no entries in member table """
    myDB = database.DBConnection()
    series = myDB.select('SELECT SeriesID,SeriesName from series')
    for item in series:
        match = myDB.match('SELECT BookID from member where SeriesID=%s' % item['SeriesID'])
        if not match:
            logger.debug('Deleting empty series %s' % item['SeriesName'])
            myDB.action('DELETE from series where SeriesID=%s' % item['SeriesID'])

def setWorkPages():
    """ Set the workpage link for any books that don't already have one """

    myDB = database.DBConnection()

    books = myDB.select('select BookID,AuthorName,BookName from books where length(WorkPage) < 4')
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
        logger.debug('setWorkPages complete, updated %s page%s' % (counter, plural(counter)))
    else:
        logger.debug('No missing WorkPages')


def librarything_wait():
    """ Wait for a second between librarything api calls """
    time_now = int(time.time())
    if time_now <= lazylibrarian.LAST_LIBRARYTHING:  # called within the last second?
        time.sleep(1)  # sleep 1 second to respect librarything api terms
    lazylibrarian.LAST_LIBRARYTHING = time_now


def getBookWork(bookID=None, reason=None):
    """ return the contents of the LibraryThing workpage for the given bookid
        preferably from the cache. If not already cached cache the results
        Return None if no workpage available """
    if not bookID:
        logger.error("getBookWork - No bookID")
        return None

    if not reason:
        reason = ""

    myDB = database.DBConnection()

    item = myDB.match('select BookName,AuthorName,BookISBN from books where bookID="%s"' % bookID)
    if item:
        cacheLocation = "WorkCache"
        cacheLocation = os.path.join(lazylibrarian.CACHEDIR, cacheLocation)
        if not os.path.exists(cacheLocation):
            os.mkdir(cacheLocation)
        workfile = os.path.join(cacheLocation, bookID + '.html')

        # does the workpage need to expire? For now only expire if it was an error page
        # (small file) as librarything might get better info over time
        if os.path.isfile(workfile):
            if os.path.getsize(workfile) < 500:
                cache_modified_time = os.stat(workfile).st_mtime
                time_now = time.time()
                expiry = lazylibrarian.CONFIG['CACHE_AGE'] * 24 * 60 * 60  # expire cache after this many seconds
                if cache_modified_time < time_now - expiry:
                    # Cache entry is too old, delete it
                    os.remove(workfile)

        if os.path.isfile(workfile):
            # use cached file if possible to speed up refreshactiveauthors and librarysync re-runs
            lazylibrarian.CACHE_HIT = int(lazylibrarian.CACHE_HIT) + 1
            if reason:
                logger.debug(u"getBookWork: Returning Cached entry for %s %s" % (bookID, reason))
            else:
                logger.debug(u"getBookWork: Returning Cached workpage for %s" % bookID)

            with open(workfile, "r") as cachefile:
                source = cachefile.read()
            return source
        else:
            lazylibrarian.CACHE_MISS = int(lazylibrarian.CACHE_MISS) + 1
            title = safe_unicode(item['BookName']).encode(lazylibrarian.SYS_ENCODING)
            author = safe_unicode(item['AuthorName']).encode(lazylibrarian.SYS_ENCODING)
            safeparams = urllib.quote_plus("%s %s" % (author, title))
            URL = 'http://www.librarything.com/api/whatwork.php?title=' + safeparams
            librarything_wait()
            result, success = fetchURL(URL)
            if success:
                try:
                    workpage = result.split('<link>')[1].split('</link>')[0]
                    librarything_wait()
                    result, success = fetchURL(workpage)
                except Exception:
                    try:
                        errmsg = result.split('<error>')[1].split('</error>')[0]
                    except Exception:
                        errmsg = "Unknown Error"
                    # if no workpage link, try isbn instead
                    if item['BookISBN']:
                        URL = 'http://www.librarything.com/api/whatwork.php?isbn=' + item['BookISBN']
                        librarything_wait()
                        result, success = fetchURL(URL)
                        if success:
                            try:
                                workpage = result.split('<link>')[1].split('</link>')[0]
                                librarything_wait()
                                result, success = fetchURL(workpage)
                            except Exception:
                                # no workpage link found by isbn
                                try:
                                    errmsg = result.split('<error>')[1].split('</error>')[0]
                                except Exception:
                                    errmsg = "Unknown Error"
                                # still cache if whatwork returned a result without a link, so we don't keep retrying
                                logger.debug("getBookWork: Librarything error: [%s] for %s" %
                                            (errmsg, item['BookISBN']))
                                success = True
                    else:
                        # still cache if whatwork returned a result without a link, so we don't keep retrying
                        msg = "getBookWork: Librarything error: [" + errmsg + "] for "
                        logger.debug(msg + item['AuthorName'] + ' ' + item['BookName'])
                        success = True
                if success:
                    with open(workfile, "w") as cachefile:
                        cachefile.write(result)
                        logger.debug(u"getBookWork: Caching workpage for %s" % workfile)
                        # return None if we got an error page back
                        if '</request><error>' in result:
                            return None
                    return result
                else:
                    logger.debug(u"getBookWork: Unable to cache workpage, got %s" % result)
                return None
            else:
                logger.debug(u"getBookWork: Unable to cache response for %s, got %s" % (URL, result))
                return None
    else:
        logger.debug('Get Book Work - Invalid bookID [%s]' % bookID)
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


def getWorkSeries(bookID=None):
    """ Return the series names and numbers in series for the given bookid as a dictionary """
    seriesdict = {}
    if not bookID:
        logger.error("getWorkSeries - No bookID")
        return seriesdict

    work = getBookWork(bookID, "Series")
    if work:
        try:
            serieslist = work.split('<h3><b>Series:')[1].split('</h3>')[0].split('<a href="/series/')
            for item in serieslist[1:]:
                try:
                    series = item.split('">')[1].split('</a>')[0]
                    series = safe_unicode(series).encode(lazylibrarian.SYS_ENCODING)
                    if series and '(' in series:
                        seriesnum = series.split('(')[1].split(')')[0].strip()
                        series = series.split(' (')[0].strip()
                    else:
                        seriesnum = ''
                        series = series.strip()
                    seriesdict[series] = seriesnum
                except IndexError:
                    pass
        except IndexError:
            pass

    return seriesdict


def getBookCover(bookID=None):
    """ Return link to a local file containing a book cover image for a bookid.
        Try 1. Local file cached from goodreads/googlebooks when book was imported
            2. cover.jpg if we have the book
            3. LibraryThing whatwork
            4. Goodreads search if book was imported from goodreads
            5. Google images search
        Return None if no cover available. """
    if not bookID:
        logger.error("getBookCover- No bookID")
        return None

    cachedir = lazylibrarian.CACHEDIR
    coverfile = os.path.join(cachedir, bookID + '.jpg')

    if os.path.isfile(coverfile):  # use cached image if there is one
        lazylibrarian.CACHE_HIT = int(lazylibrarian.CACHE_HIT) + 1
        logger.debug(u"getBookCover: Returning Cached response for %s" % coverfile)
        coverlink = 'cache/' + bookID + '.jpg'
        return coverlink

    lazylibrarian.CACHE_MISS = int(lazylibrarian.CACHE_MISS) + 1

    myDB = database.DBConnection()
    item = myDB.match('select BookFile from books where bookID="%s"' % bookID)
    if item:
        bookfile = item['BookFile']
        if bookfile:  # we may have a cover.jpg in the same folder
            bookdir = os.path.dirname(bookfile)
            coverimg = os.path.join(bookdir, "cover.jpg")
            if os.path.isfile(coverimg):
                logger.debug(u"getBookCover: Copying book cover to %s" % coverfile)
                shutil.copyfile(coverimg, coverfile)
                coverlink = 'cache/' + bookID + '.jpg'
                return coverlink

    # if no cover.jpg, see if librarything workpage has a cover
    work = getBookWork(bookID, "Cover")
    if work:
        try:
            img = work.split('og:image')[1].split('="')[1].split('"')[0]
            if img and img.startswith('http'):
                coverlink, success = cache_img("book", bookID, img)
                if success:
                    logger.debug(u"getBookCover: Caching librarything cover for %s" % bookID)
                    return coverlink
                else:
                    logger.debug('getBookCover: Failed to cache image for %s [%s]' % (img, coverlink))
            else:
                logger.debug("getBookCover: No image found in work page for %s" % bookID)
        except IndexError:
            logger.debug('getBookCover: Image not found in work page for %s' % bookID)

    # not found in librarything work page, try to get a cover from goodreads or google instead
    item = myDB.match('select BookName,AuthorName,BookLink from books where bookID="%s"' % bookID)
    if item:
        title = safe_unicode(item['BookName']).encode(lazylibrarian.SYS_ENCODING)
        author = safe_unicode(item['AuthorName']).encode(lazylibrarian.SYS_ENCODING)
        booklink = item['BookLink']
        safeparams = urllib.quote_plus("%s %s" % (author, title))
        if 'goodreads' in booklink:
            # if the bookID is a goodreads one, we can call https://www.goodreads.com/book/show/{bookID}
            # and scrape the page for og:image
            # <meta property="og:image" content="https://i.gr-assets.com/images/S/photo.goodreads.com/books/
            # 1388267702i/16304._UY475_SS475_.jpg"/>
            # to get the cover

            time_now = int(time.time())
            if time_now <= lazylibrarian.LAST_GOODREADS:
                time.sleep(1)
                lazylibrarian.LAST_GOODREADS = time_now
            result, success = fetchURL(booklink)
            if success:
                try:
                    img = result.split('og:image')[1].split('="')[1].split('"')[0]
                except IndexError:
                    img = None
                if img and img.startswith('http') and 'nocover' not in img and 'nophoto' not in img:
                    time_now = int(time.time())
                    if time_now <= lazylibrarian.LAST_GOODREADS:
                        time.sleep(1)
                        lazylibrarian.LAST_GOODREADS = time_now
                    coverlink, success = cache_img("book", bookID, img)
                    if success:
                        logger.debug("getBookCover: Caching goodreads cover for %s %s" %
                                    (item['AuthorName'],item['BookName']))
                        return coverlink
                    else:
                        logger.debug("getBookCover: Error getting goodreads image for %s, [%s]" % (img, coverlink))
                else:
                    logger.debug("getBookCover: No image found in goodreads page for %s" % bookID)
            else:
                logger.debug("getBookCover: Error getting page %s, [%s]" % (booklink, result))

        # if this failed, try a google image search...
        # tbm=isch      search images
        # tbs=isz:l     large images
        # ift:jpg       jpeg file type
        URL = "https://www.google.com/search?tbm=isch&tbs=isz:l,ift:jpg&as_q=" + safeparams + "+ebook"
        result, success = fetchURL(URL)
        if success:
            try:
                img = result.split('url?q=')[1].split('">')[1].split('src="')[1].split('"')[0]
            except IndexError:
                img = None
            if img and img.startswith('http'):
                coverlink, success = cache_img("book", bookID, img)
                if success:
                    logger.debug("getBookCover: Caching google cover for %s %s" %
                                (item['AuthorName'], item['BookName']))
                    return coverlink
                else:
                    logger.debug("getBookCover: Error getting google image %s, [%s]" % (img, coverlink))
            else:
                logger.debug("getBookCover: No image found in google page for %s" % bookID)
        else:
            logger.debug("getBookCover: Error getting google page for %s, [%s]" % (safeparams, result))
    return None


def getAuthorImage(authorid=None):
    # tbm=isch      search images
    # tbs=ift:jpg  jpeg file type
    if not authorid:
        logger.error("getAuthorImage: No authorid")
        return None

    cachedir = lazylibrarian.CACHEDIR
    coverfile = os.path.join(cachedir, authorid + '.jpg')

    if os.path.isfile(coverfile):  # use cached image if there is one
        lazylibrarian.CACHE_HIT = int(lazylibrarian.CACHE_HIT) + 1
        logger.debug(u"getAuthorImage: Returning Cached response for %s" % coverfile)
        coverlink = 'cache/' + authorid + '.jpg'
        return coverlink

    lazylibrarian.CACHE_MISS = int(lazylibrarian.CACHE_MISS) + 1
    myDB = database.DBConnection()
    authors = myDB.select('select AuthorName from authors where AuthorID = "%s"' % authorid)
    if authors:
        authorname = safe_unicode(authors[0][0]).encode(lazylibrarian.SYS_ENCODING)
        safeparams = urllib.quote_plus("author %s" % authorname)
        URL = "https://www.google.com/search?tbm=isch&tbs=ift:jpg&as_q=" + safeparams
        result, success = fetchURL(URL)
        if success:
            try:
                img = result.split('url?q=')[1].split('">')[1].split('src="')[1].split('"')[0]
            except IndexError:
                img = None
            if img and img.startswith('http'):
                coverlink, success = cache_img("author", authorid, img)
                if success:
                    logger.debug("Cached google image for %s" % authorname)
                    return coverlink
                else:
                    logger.debug("Error getting google image %s, [%s]" % (img, coverlink))
            else:
                logger.debug("No image found in google page for %s" % authorname)
        else:
            logger.debug("Error getting google page for %s, [%s]" % (safeparams, result))
    else:
        logger.debug("No author found for %s" % authorid)
    return None
