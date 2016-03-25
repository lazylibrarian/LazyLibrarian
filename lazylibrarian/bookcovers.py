import os
import threading
import urllib
import urllib2
import socket
import hashlib

import lazylibrarian
from lazylibrarian import logger, formatter, database
from lazylibrarian.common import USER_AGENT

def getBookCovers(bookids=None):
    if not bookids:
        logger.info("Get Book Covers - No matching BookIDs")
        return

    myDB = database.DBConnection()
     
    num = len(bookids)
    if num == 1:
        logger.info("Fetching google images cover for %s" % bookids)
    else:
        logger.info("Fetching google images covers for %i books" % len(bookids))
        
    for bookid in bookids:
        item = myDB.action('select BookName,AuthorName from books where BookID="%s"' % bookid).fetchone()
        if len(item):
            title = formatter.safe_unicode(item['BookName']).encode('utf-8')
            author = formatter.safe_unicode(item['AuthorName']).encode('utf-8')
            safeparams = urllib.quote_plus("%s %s" % (author, title))
            URL4="https://www.google.com/search?as_st=y&tbm=isch&as_q=" + safeparams + "+ebook&tbs=isz:l,ift:jpg&gws_rd=cr&ei=Ff30Vo_HOaWuygO13bvYBQ"
    
            request = urllib2.Request(URL4)
            #if lazylibrarian.PROXY_HOST:
            #    request.set_proxy(lazylibrarian.PROXY_HOST, lazylibrarian.PROXY_TYPE)
            # google insists on having a user-agent
            request.add_header('User-Agent', USER_AGENT)
       
            hashID = hashlib.md5(safeparams).hexdigest()
            #cachedir = os.path.join(str(lazylibrarian.PROG_DIR),
            cachedir = os.path.join('/opt/LazyLibrarian',
                                    'data' + os.sep + 'images' + os.sep + 'cache')
            if not os.path.isdir(cachedir):
                os.makedirs(cachedir)
            coverfile = os.path.join(cachedir, hashID + '.jpg')
            link = 'images' + os.sep + 'cache' + os.sep + hashID + '.jpg'

            try:
                resp = urllib2.urlopen(request, timeout=30)
                if str(resp.getcode()).startswith("2"):
                    # (200 OK etc)
                    source_page = resp.read()
                    #with open(coverfile + 'src', 'wb') as img:
                    #    img.write(source_page)
                    #print coverfile + 'src'
                    try:
                        img = source_page.split('url?q=')[1].split('">')[1].split('src="')[1].split('"')[0]
                    except IndexError:
                        img = "Not found"
                    if img.startswith('http'):
                        request = urllib2.Request(img)
                        request.add_header('User-Agent', USER_AGENT)
                        try:
                            resp = urllib2.urlopen(request, timeout=30)
                            if str(resp.getcode()).startswith("2"):
                                # (200 OK etc)
                                with open(coverfile, 'wb') as img:
                                    img.write(resp.read())
                                update = True
                            else:
                                logger.debug("Error getting image: %s" % str(resp))
                        except (urllib2.HTTPError, urllib2.URLError, socket.timeout) as e:
                            logger.debug("Error getting image : %s" % e.reason)
                    else:
                        logger.debug("Error getting url [%s]" % img)                      
            except (urllib2.HTTPError, urllib2.URLError, socket.timeout) as e:
                logger.debug("Error getting source page : %s" % e.reason)

            # image downloaded, now update the link
            logger.debug("%s %s %s" % (link, author, title))
            myDB.action('update books set BookImg="%s" where BookID="%s"' % (link, bookid))
    if num > 1:
        logger.debug("Get Book Covers - update complete")


