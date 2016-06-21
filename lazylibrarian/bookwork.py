import os
import urllib
import urllib2
import socket
import time
import threading
import lazylibrarian
from lazylibrarian import logger, formatter, database
from lazylibrarian.common import USER_AGENT

def getBookCovers(thread=None):
    """ Try to get a cover image for all books """
    if thread is None:
        threading.currentThread().name = "GETBOOKCOVERS"

    myDB = database.DBConnection()
    books = myDB.select('select BookID,BookImg from books where BookImg like "%nocover%"')
    if books:    
        logger.info('Checking covers for %s books' % len(books))
        counter = 0
        for book in books:
            bookid = book['BookID']
            coverlink = getBookCover(bookid)
            if coverlink and not "nocover" in coverlink:
                controlValueDict = {"BookID": bookid}
                newValueDict = {"BookImg": coverlink}
                myDB.upsert("books", newValueDict, controlValueDict)
                counter += 1
        logger.info('Cover check completed, updated %s covers' % counter)
    else:
        logger.debug('No missing covers')

       
def setWorkPages(thread=None):
    """ Set the workpage link for any books that don't already have one """
    if thread is None:
        threading.currentThread().name = "SETWORKPAGES"

    myDB = database.DBConnection()
     
    books = myDB.select('select BookID,AuthorName,BookName from books where length(WorkPage) < 4')
    if books:    
        logger.debug('Setting WorkPage for %s books' % len(books))
        for book in books:
            bookid = book['BookID']
            worklink = getWorkPage(bookid)
            if worklink:
                controlValueDict = {"BookID": bookid}
                newValueDict = {"WorkPage": worklink}
                myDB.upsert("books", newValueDict, controlValueDict)
            else:
               logger.debug('No WorkPage found for %s: %s' % (book['AuthorName'], book['BookName'])) 
        logger.debug('setWorkPages completed')

def fetchURL(URL):
    """ Return the result of fetching a URL and True if success
        Otherwise return error message and False
        Allow one retry on timeout """
    
    request = urllib2.Request(URL)
    if lazylibrarian.PROXY_HOST:
        request.set_proxy(lazylibrarian.PROXY_HOST, lazylibrarian.PROXY_TYPE)
    # google insists on having a user-agent
    request.add_header('User-Agent', USER_AGENT)
    try:
        resp = urllib2.urlopen(request, timeout=30)
        if str(resp.getcode()).startswith("2"):
            # (200 OK etc)
            try:
                result = resp.read()
            except socket.error as e:
                return e, False
            return result, True
        else:
            return str(resp), False  
    except (socket.timeout) as e:
        logger.warn(u"fetchURL: retrying - got timeout on %s" % URL)
        try:
            resp = urllib2.urlopen(request, timeout=30)  # don't get stuck
            if str(resp.getcode()).startswith("2"):
                # (200 OK etc)
                try:
                    result = resp.read()
                except socket.error as e:
                    return e, False
                return result, True
            else:
                return str(resp), False  
        except (urllib2.URLError, socket.timeout) as e:
            logger.error(u"fetchURL: Error getting response for %s: %s" % (URL, e))
            return e, False                    
    except (urllib2.HTTPError, urllib2.URLError) as e:
        return e.reason, False
            
def librarything_wait():
    """ Wait for a second between librarything api calls """
    time_now = int(time.time())
    if time_now <= lazylibrarian.LAST_LIBRARYTHING:  # called within the last second?
        time.sleep(1)  # sleep 1 second to respect librarything api terms
    lazylibrarian.LAST_LIBRARYTHING = time_now
    
    
def getBookWork(bookID=None):
    """ return the contents of the LibraryThing workpage for the given bookid
        preferably from the cache. If not already cached cache the results
        Return None if no workpage available """
    if not bookID:
        logger.error("getBookWork - No bookID")
        return None

    myDB = database.DBConnection()
     
    item = myDB.action('select BookName,AuthorName,BookISBN from books where bookID="%s"' % bookID).fetchone()
    if item:    
        cacheLocation = "WorkCache"
        # does the workpage need to expire?
        # expireafter = lazylibrarian.CACHE_AGE
        cacheLocation = os.path.join(lazylibrarian.CACHEDIR, cacheLocation)
        if not os.path.exists(cacheLocation):
            os.mkdir(cacheLocation)
        workfile = os.path.join(cacheLocation, bookID + '.html')
        
        if os.path.isfile(workfile):
            # use cached file if possible to speed up refreshactiveauthors and librarysync re-runs
            lazylibrarian.CACHE_HIT = int(lazylibrarian.CACHE_HIT) + 1
            logger.debug(u"getBookWork: Returning Cached response for %s" % workfile)
            with open(workfile, "r") as cachefile:
                source = cachefile.read()
            return source
        else:
            lazylibrarian.CACHE_MISS = int(lazylibrarian.CACHE_MISS) + 1
            bookisbn = item['BookISBN']
            if bookisbn:
                URL='http://www.librarything.com/api/whatwork.php?isbn=' + bookisbn
            else:
                title = formatter.safe_unicode(item['BookName']).encode('utf-8')
                author = formatter.safe_unicode(item['AuthorName']).encode('utf-8')
                safeparams = urllib.quote_plus("%s %s" % (author, title))
                URL='http://www.librarything.com/api/whatwork.php?title=' + safeparams  
            librarything_wait()
            result, success = fetchURL(URL)
            if success:
                try:
                    workpage = result.split('<link>')[1].split('</link>')[0] 
                    librarything_wait()
                    result, success = fetchURL(workpage)
                except:
                    try:
                        errmsg = result.split('<error>')[1].split('</error>')[0]
                        # still cache if whatwork returned a result without a link, so we don't keep retrying
                        logger.debug(u"getBookWork: Got librarything error page: [%s] %s" % (errmsg, URL.split('?')[1]))
                    except:
                        logger.debug(u"getBookWork: Unable to find workpage link for %s" % URL.split('?')[1])    
                        return None
                if success:
                    logger.debug(u"getBookWork: Caching response for %s" % workfile)
                    with open(workfile, "w") as cachefile:
                        cachefile.write(result)
                    return result
                else:
                    logger.debug(u"getBookWork: Unable to cache response for %s, got %s" % (workpage, result))
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
    work = getBookWork(bookID)
    if work:
        try:
            page = work.split('og:url')[1].split('="')[1].split('"')[0]
        except IndexError:
            return ''
        return page
    return ''
        
def getWorkSeries(bookID=None):
    """ Return the series name and number in series for the given bookid
        Returns None if no series or series number """
    if not bookID:
        logger.error("getWorkSeries - No bookID")
        return None, None
    work = getBookWork(bookID)
    if work:
        try:
            series = work.split('<a href="/series/')[1].split('">')[1].split('</a>')[0]
        except IndexError:
            return None, None
        series = formatter.safe_unicode(series).encode('utf-8')
        if series and '(' in series:
            seriesnum = series.split('(')[1].split(')')[0]
            series = series.split(' (')[0]
        else:
            seriesnum = None
        return series, seriesnum
    return None, None
    
def getBookCover(bookID=None):
    """ Return link to a local file containing a book cover image for a bookid. 
        Try 1. Local file cached from goodreads/googlebooks when book was imported
            2. LibraryThing whatwork
            3. Goodreads search if book was imported from goodreads
            4. Google images search
        Return None if no cover available. """
    if not bookID:
        logger.error("getBookCover- No bookID")
        return None

    cachedir = os.path.join(str(lazylibrarian.PROG_DIR), 'data' + os.sep + 'images' + os.sep + 'cache')
    coverfile = os.path.join(cachedir, bookID + '.jpg')

    if os.path.isfile(coverfile):  # use cached image if there is one
        lazylibrarian.CACHE_HIT = int(lazylibrarian.CACHE_HIT) + 1
        logger.debug(u"getBookCover: Returning Cached response for %s" % coverfile)
        coverlink = 'images/cache/' + bookID + '.jpg'
        return coverlink
                
    lazylibrarian.CACHE_MISS = int(lazylibrarian.CACHE_MISS) + 1    
    work = getBookWork(bookID)
    if work:
        try:
            img = work.split('og:image')[1].split('content="')[1].split('"')[0]
            if img and img.startswith('http'):
                coverlink = cache_cover(bookID, img)
                if coverlink is not None:
                    logger.debug(u"getBookCover: Caching librarything cover for %s" % bookID)
                    return coverlink
            else:
                logger.debug("getBookCover: No image found in work page for %s" % bookID)
        except IndexError:
            logger.debug('getBookCover: Image not found in work page for %s' % bookID)
    
    # not found in librarything work page, try to get a cover from goodreads or google instead

    myDB = database.DBConnection()
     
    item = myDB.action('select BookName,AuthorName,BookLink from books where bookID="%s"' % bookID).fetchone()
    if item:
        title = formatter.safe_unicode(item['BookName']).encode('utf-8')
        author = formatter.safe_unicode(item['AuthorName']).encode('utf-8')
        booklink = item['BookLink']
        safeparams = urllib.quote_plus("%s %s" % (author, title))
        
        if 'goodreads' in booklink:
            # if the bookID is a goodreads one, we can call https://www.goodreads.com/book/show/{bookID}
            # and scrape the page for og:image
            # <meta property="og:image" content="https://i.gr-assets.com/images/S/photo.goodreads.com/books/1388267702i/16304._UY475_SS475_.jpg"/>
            # to get the cover
                
            time_now = int(time.time())
            if time_now <= lazylibrarian.LAST_GOODREADS:
                time.sleep(1)
                lazylibrarian.LAST_GOODREADS = time_now
            result, success = fetchURL(booklink)
            if success:
                try:
                    img = result.split('og:image')[1].split('content="')[1].split('"/>')[0]
                except IndexError:
                    img = None
                if img and img.startswith('http') and not 'nocover' in img and not 'nophoto' in img:
                    time_now = int(time.time())
                    if time_now <= lazylibrarian.LAST_GOODREADS:
                        time.sleep(1)
                        lazylibrarian.LAST_GOODREADS = time_now
                    coverlink = cache_cover(bookID, img)
                    if coverlink is not None:
                        logger.debug("getBookCover: Caching goodreads cover for %s %s" % (author, title))
                        return coverlink
                    else:
                        logger.debug("getBookCover: Error getting goodreads image for %s, [%s]" % (img, result))
                else:
                    logger.debug("getBookCover: No image found in goodreads page for %s" % bookID)
            else:
                logger.debug("getBookCover: Error getting page %s, [%s]" % (booklink, result))
      
        # if this failed, try a google image search...
        # tbm=isch      search books
        # tbs=isz:l     large images
        # ift:jpg       jpeg file type
        URL="https://www.google.com/search?tbm=isch&tbs=isz:l,ift:jpg&as_q=" + safeparams + "+ebook"
        result, success = fetchURL(URL)
        if success:
            try:
                img = result.split('url?q=')[1].split('">')[1].split('src="')[1].split('"')[0]
            except IndexError:
                img = None
            if img and img.startswith('http'):
                coverlink = cache_cover(bookID, img)
                if coverlink is not None:
                    logger.debug("getBookCover: Caching google cover for %s %s" % (author, title))
                    return coverlink
                else:
                    logger.debug("getBookCover: Error getting google image %s, [%s]" % (img, result))
            else:
                logger.debug("getBookCover: No image found in google page for %s" % bookID)
        else:
            logger.debug("getBookCover: Error getting google page for %s, [%s]" % (safeparams, result))        
    return None
        
def cache_cover(bookID, img_url):
    """ Cache the image from the given URL in the local images cache
        linked to the bookid, return the link to the cached file
        or None if failed to cache """
        
    cachedir = os.path.join(str(lazylibrarian.PROG_DIR),
                            'data' + os.sep + 'images' + os.sep + 'cache')
    if not os.path.isdir(cachedir):
        os.makedirs(cachedir)
    coverfile = os.path.join(cachedir, bookID + '.jpg')
    link = 'images/cache/' + bookID + '.jpg'
    #if os.path.isfile(coverfile):  # overwrite any cached image
    #    return link

    result, success = fetchURL(img_url)
    
    if success:
        try:
            with open(coverfile, 'wb') as img:
                img.write(result)
            return link
        except:
            logger.debug("Error writing image to %s" % coverfile)
    return None

