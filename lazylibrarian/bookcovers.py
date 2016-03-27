import os
import threading
import urllib
import urllib2
import socket
import hashlib
import time

import lazylibrarian
from lazylibrarian import logger, formatter, database
from lazylibrarian.common import USER_AGENT

def fetchURL(URL):
    request = urllib2.Request(URL)
    if lazylibrarian.PROXY_HOST:
        request.set_proxy(lazylibrarian.PROXY_HOST, lazylibrarian.PROXY_TYPE)
    # google insists on having a user-agent
    request.add_header('User-Agent', USER_AGENT)
    try:
        resp = urllib2.urlopen(request, timeout=30)
        if str(resp.getcode()).startswith("2"):
            # (200 OK etc)
            result = resp.read()
            return result, True
        else:
            return str(resp), False                     
    except (urllib2.HTTPError, urllib2.URLError, socket.timeout) as e:
        return e.reason, False
            

def getBookCovers(bookids=None):
    if not bookids:
        logger.info("Get Book Covers - No matching BookIDs")
        return

    myDB = database.DBConnection()
     
    num = len(bookids)
    if num > 1:
        logger.info("Fetching book covers for %i books" % num)   
    for bookid in bookids:
        item = myDB.action('select BookName,AuthorName,BookLink from books where BookID="%s"' % bookid).fetchone()
        if item:
            title = formatter.safe_unicode(item['BookName']).encode('utf-8')
            author = formatter.safe_unicode(item['AuthorName']).encode('utf-8')
            booklink = item['BookLink']
            safeparams = urllib.quote_plus("%s %s" % (author, title))
            
            hashID = hashlib.md5(safeparams).hexdigest()
            cachedir = os.path.join(str(lazylibrarian.PROG_DIR),
                                    'data' + os.sep + 'images' + os.sep + 'cache')
            if not os.path.isdir(cachedir):
                os.makedirs(cachedir)
            coverfile = os.path.join(cachedir, hashID + '.jpg')
            link = 'images' + os.sep + 'cache' + os.sep + hashID + '.jpg'
            covertype = ""

            if os.path.isfile(coverfile):
                # use cached image if possible to speed up refreshactiveauthors and librarysync re-runs
                covertype = "" #cached"
            
            if not covertype and 'goodreads' in booklink:
                # if the bookid is a goodreads one, we can call https://www.goodreads.com/book/show/{bookid}
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
                        img = ""
                    if img.startswith('http'):
                        time_now = int(time.time())
                        if time_now <= lazylibrarian.LAST_GOODREADS:
                            time.sleep(1)
                            lazylibrarian.LAST_GOODREADS = time_now
                        result, success = fetchURL(img)
                        if success:
                            with open(coverfile, 'wb') as img:
                                img.write(result)
                            covertype = "goodreads"
                        else:
                            logger.debug("Error getting goodreads image for %s, [%s]" % (img, result))
                    else:
                        logger.debug("No image found in goodreads page for %s" % bookid)
                else:
                    logger.debug("Error getting page %s, [%s]" % (booklink, result))
          
            # if this failed, try a google image search...
       
            if not covertype:
                URL="https://www.google.com/search?as_st=y&tbm=isch&as_q=" + safeparams + \
                    "+ebook&tbs=isz:l,ift:jpg&gws_rd=cr&ei=Ff30Vo_HOaWuygO13bvYBQ"
                result, success = fetchURL(URL)
                if success:
                    try:
                        img = result.split('url?q=')[1].split('">')[1].split('src="')[1].split('"')[0]
                    except IndexError:
                        img = ""
                    if img.startswith('http'):
                        result, success = fetchURL(img)
                        if success:
                            with open(coverfile, 'wb') as img:
                                img.write(result)
                            covertype = "google"
                        else:
                            logger.debug("Error getting google image %s, [%s]" % (img, result))
                    else:
                        logger.debug("No image found in google page for %s" % bookid)
                else:
                    logger.debug("Error getting google page for %s, [%s]" % (safeparams, result))
            
            if covertype:
                # image downloaded, or was already there, now update the link
                logger.debug("Found %s cover for %s %s" % (covertype, author, title))
                myDB.action('update books set BookImg="%s" where BookID="%s"' % (link, bookid))
    if num > 1:
        logger.info("Get Book Covers - update complete")

