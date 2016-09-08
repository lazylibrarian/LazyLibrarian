import lazylibrarian
import os
import md5
import hashlib
import json
import urllib2
import socket
import time
from xml.etree import ElementTree
from lazylibrarian import logger
from lazylibrarian.common import USER_AGENT


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
                return str(e), False
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
                    return str(e), False
                return result, True
            else:
                return str(resp), False
        except (socket.timeout) as e:
            logger.error(u"fetchURL: Timeout getting response from %s" % URL)
            return str(e), False
        except (urllib2.URLError) as e:
            logger.error(u"fetchURL: Error getting response for %s: %s" % (URL, e.reason))
            return e.reason, False
    except (urllib2.HTTPError, urllib2.URLError) as e:
        if hasattr(e, 'reason'):
            return e.reason, False
        else:
            return str(e), False

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
        except Exception as e:
            logger.debug("Error writing image to %s, %s" % (coverfile, str(e)))
    return None

def get_xml_request(my_url, useCache=True):
    # Original simplecache
    # opener = urllib.request.build_opener(SimpleCache.CacheHandler(".AuthorCache"),
    # SimpleCache.ThrottlingProcessor(5))
    # resp = opener.open(request)
    # Simplified simplecache, no throttling, no headers as we dont use them, added cache expiry
    # we can simply cache the xml with...
    # hashfilename = hash url
    # if hashfilename exists, return its contents
    # if not, urllib2.urlopen()
    # store the xml
    # return the xml, and whether it was found in the cache
    # Need to expire the cache entries, or we won't search for anything new
    # default to 30 days for now. Authors dont write that quickly.
    #
    cacheLocation = "XMLCache"
    cacheLocation = os.path.join(lazylibrarian.CACHEDIR, cacheLocation)
    if not os.path.exists(cacheLocation):
        os.mkdir(cacheLocation)
    myhash = md5.new(my_url).hexdigest()
    valid_cache = False
    hashname = cacheLocation + os.sep + myhash + ".xml"

    if useCache and os.path.isfile(hashname):
        cache_modified_time = os.stat(hashname).st_mtime
        time_now = time.time()
        if cache_modified_time < time_now - (lazylibrarian.CACHE_AGE * 24 * 60 * 60):  # expire after this many seconds
            # Cache is old, delete entry
            os.remove(hashname)
        else:
            valid_cache = True

    if valid_cache:
        lazylibrarian.CACHE_HIT = int(lazylibrarian.CACHE_HIT) + 1
        logger.debug(u"CacheHandler: Returning CACHED response for %s" % my_url)
        with open(hashname, "r") as cachefile:
            source_xml = cachefile.read()
    else:
        lazylibrarian.CACHE_MISS = int(lazylibrarian.CACHE_MISS) + 1
        source_xml, success = fetchURL(my_url)
        if success:
            logger.debug(u"CacheHandler: Storing XML for %s" % my_url)
            with open(hashname, "w") as cachefile:
                cachefile.write(source_xml)
        else:
            logger.warn(u"Got error response for %s: %s" % (my_url, source_xml))
            return None, False

    root = ElementTree.fromstring(source_xml)
    return root, valid_cache


def get_json_request(my_url, useCache=True):
    # broadly similar to get_xml_request above, but caches json results
    # hashfilename = hash url
    # if hashfilename exists, return its contents
    # if not, urllib2.urlopen()
    # store the result
    # return the result, and whether it was found in the cache
    # Need to expire the cache entries, or we won't search for anything new
    # default to 30 days for now. Authors dont write that quickly.
    #
    cacheLocation = "JSONCache"
    cacheLocation = os.path.join(lazylibrarian.CACHEDIR, cacheLocation)
    if not os.path.exists(cacheLocation):
        os.mkdir(cacheLocation)
    myhash = md5.new(my_url).hexdigest()
    valid_cache = False
    hashname = cacheLocation + os.sep + myhash + ".json"

    if useCache and os.path.isfile(hashname):
        cache_modified_time = os.stat(hashname).st_mtime
        time_now = time.time()
        if cache_modified_time < time_now - (lazylibrarian.CACHE_AGE * 24 * 60 * 60):  # expire after this many seconds
            # Cache is old, delete entry
            os.remove(hashname)
        else:
            valid_cache = True

    if valid_cache:
        lazylibrarian.CACHE_HIT = int(lazylibrarian.CACHE_HIT) + 1
        logger.debug(
            u"CacheHandler: Returning CACHED response for %s" % my_url)
        source_json = json.load(open(hashname))
    else:
        lazylibrarian.CACHE_MISS = int(lazylibrarian.CACHE_MISS) + 1
        result, success = fetchURL(my_url)
        if success:
            logger.debug(u"CacheHandler: Storing JSON for %s" % my_url)
            source_json = json.JSONDecoder().decode(result)
            json.dump(source_json, open(hashname, "w"))
        else:
            logger.warn(u"Got error response for %s: %s" % (my_url, result))
            return None, False
    return source_json, valid_cache
