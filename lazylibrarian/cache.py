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

import hashlib
import json
import os
import socket
import time
import urllib2
from xml.etree import ElementTree

import lazylibrarian
from lazylibrarian import logger
from lazylibrarian.common import USER_AGENT


def fetchURL(URL, headers=None, retry=True):
    """ Return the result of fetching a URL and True if success
        Otherwise return error message and False
        Allow one retry on timeout by default"""
    request = urllib2.Request(URL)
    if lazylibrarian.PROXY_HOST:
        request.set_proxy(lazylibrarian.PROXY_HOST, lazylibrarian.PROXY_TYPE)
    if headers is None:
        # some sites insist on having a user-agent, default is to add one
        # if you don't want any headers, send headers=[]
        request.add_header('User-Agent', USER_AGENT)
    else:
        for item in headers:
            request.add_header(item, headers[item])
    try:
        resp = urllib2.urlopen(request, timeout=30)
        if str(resp.getcode()).startswith("2"):  # (200 OK etc)
            try:
                result = resp.read()
            except socket.error as e:
                return str(e), False
            return result, True
        return str(resp.getcode()), False
    except socket.timeout as e:
        if not retry:
            logger.error(u"fetchURL: Timeout getting response from %s" % URL)
            return str(e), False
        logger.warn(u"fetchURL: retrying - got timeout on %s" % URL)
        result, success = fetchURL(URL, headers=headers, retry=False)
        return result, success
    except Exception as e:
        if hasattr(e, 'reason'):
            return e.reason, False
        return str(e), False


def cache_cover(bookID, img_url):
    """ Cache the image from the given URL in the local images cache
        linked to the bookid, return the link to the cached file
        or None if failed to cache """

    cachedir = lazylibrarian.CACHEDIR
    coverfile = os.path.join(cachedir, bookID + '.jpg')
    link = 'cache/' + bookID + '.jpg'
    # if os.path.isfile(coverfile):  # overwrite any cached image
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
    result, in_cache = get_cached_request(url=my_url, useCache=useCache, cache="XML")
    return result, in_cache


def get_json_request(my_url, useCache=True):
    result, in_cache = get_cached_request(url=my_url, useCache=useCache, cache="JSON")
    return result, in_cache


def get_cached_request(url, useCache=True, cache="XML"):
    # hashfilename = hash of url
    # if hashfilename exists in cache and isn't too old, return its contents
    # if not, read url and store the result in the cache
    # return the result, and boolean True if source was cache
    #
    cacheLocation = cache + "Cache"
    cacheLocation = os.path.join(lazylibrarian.CACHEDIR, cacheLocation)
    if not os.path.exists(cacheLocation):
        os.mkdir(cacheLocation)
    myhash = hashlib.md5(url).hexdigest()
    valid_cache = False
    source = None
    hashfilename = cacheLocation + os.sep + myhash + "." + cache.lower()

    if useCache and os.path.isfile(hashfilename):
        cache_modified_time = os.stat(hashfilename).st_mtime
        time_now = time.time()
        expiry = lazylibrarian.CACHE_AGE * 24 * 60 * 60  # expire cache after this many seconds
        if cache_modified_time < time_now - expiry:
            # Cache entry is too old, delete it
            os.remove(hashfilename)
        else:
            valid_cache = True

    if valid_cache:
        lazylibrarian.CACHE_HIT = int(lazylibrarian.CACHE_HIT) + 1
        logger.debug(u"CacheHandler: Returning CACHED response for %s" % url)
        if cache == "JSON":
            source = json.load(open(hashfilename))
        elif cache == "XML":
            with open(hashfilename, "r") as cachefile:
                result = cachefile.read()
            source = ElementTree.fromstring(result)
    else:
        lazylibrarian.CACHE_MISS = int(lazylibrarian.CACHE_MISS) + 1
        result, success = fetchURL(url)
        if success:
            logger.debug(u"CacheHandler: Storing %s for %s" % (cache, url))
            if cache == "JSON":
                source = json.loads(result)
                json.dump(source, open(hashfilename, "w"))
            elif cache == "XML":
                with open(hashfilename, "w") as cachefile:
                    cachefile.write(result)
                source = ElementTree.fromstring(result)
        else:
            logger.warn(u"Got error response for %s: %s" % (url, result))
            return None, False
    return source, valid_cache
