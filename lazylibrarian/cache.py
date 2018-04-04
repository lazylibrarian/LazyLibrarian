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

import json
import os
import shutil
import time
from xml.etree import ElementTree
try:
    import requests
except ImportError:
    import lib.requests as requests
from lib.six import PY2

import lazylibrarian
from lazylibrarian import logger
from lazylibrarian.common import USER_AGENT, proxyList
from lazylibrarian.formatter import check_int, md5_utf8


def fetchURL(URL, headers=None, retry=True, raw=None):
    """ Return the result of fetching a URL and True if success
        Otherwise return error message and False
        Return data as raw/bytes n python2 or if raw == True
        On python3 default to unicode, need to set raw=True for images/data
        Allow one retry on timeout by default"""

    if raw is None:
        if PY2:
            raw = True
        else:
            raw = False

    if headers is None:
        # some sites insist on having a user-agent, default is to add one
        # if you don't want any headers, send headers=[]
        headers = {'User-Agent': USER_AGENT}
    proxies = proxyList()
    try:
        timeout = check_int(lazylibrarian.CONFIG['HTTP_TIMEOUT'], 30)
        r = requests.get(URL, headers=headers, timeout=timeout, proxies=proxies)

        if str(r.status_code).startswith('2'):  # (200 OK etc)
            if raw:
                return r.content, True
            try:
                result = r.content.decode('utf-8')
            except UnicodeDecodeError:
                result = r.content.decode('latin-1')
            return result, True

        # noinspection PyBroadException
        try:
            # noinspection PyProtectedMember
            msg = requests.status_codes._codes[r.status_code][0]
        except Exception:
            msg = str(r.content)
        return "Response status %s: %s" % (r.status_code, msg), False
    except requests.exceptions.Timeout as e:
        if not retry:
            logger.error("fetchURL: Timeout getting response from %s" % URL)
            return "Timeout %s" % str(e), False
        logger.debug("fetchURL: retrying - got timeout on %s" % URL)
        result, success = fetchURL(URL, headers=headers, retry=False, raw=False)
        return result, success
    except Exception as e:
        if hasattr(e, 'reason'):
            return "Exception %s: Reason: %s" % (type(e).__name__, str(e.reason)), False
        return "Exception %s: %s" % (type(e).__name__, str(e)), False


def cache_img(img_type, img_ID, img_url, refresh=False):
    """ Cache the image from the given filename or URL in the local images cache
        linked to the id, return the link to the cached file, True
        or error message, False if failed to cache """

    if img_type not in ['book', 'author']:
        logger.error('Internal error in cache_img, img_type = [%s]' % img_type)
        img_type = 'book'

    cachefile = os.path.join(lazylibrarian.CACHEDIR, img_type, img_ID + '.jpg')
    link = 'cache/%s/%s.jpg' % (img_type, img_ID)
    if os.path.isfile(cachefile) and not refresh:  # overwrite any cached image
        logger.debug("Cached %s image exists %s" % (img_type, cachefile))
        return link, True

    if img_url.startswith('http'):
        result, success = fetchURL(img_url, raw=True)
        if success:
            try:
                with open(cachefile, 'wb') as img:
                    img.write(result)
                return link, True
            except Exception as e:
                logger.error("%s writing image to %s, %s" % (type(e).__name__, cachefile, str(e)))
                return str(e), False
        return result, False
    else:
        try:
            shutil.copyfile(img_url, cachefile)
            return link, True
        except Exception as e:
            logger.error("%s copying image to %s, %s" % (type(e).__name__, cachefile, str(e)))
            return str(e), False


def gr_xml_request(my_url, useCache=True):
    # respect goodreads api limit
    time_now = int(time.time())
    if time_now <= lazylibrarian.LAST_GOODREADS:
        time.sleep(1)
    result, in_cache = get_cached_request(url=my_url, useCache=useCache, cache="XML")
    if not in_cache:
        lazylibrarian.LAST_GOODREADS = time_now
    return result, in_cache


def gb_json_request(my_url, useCache=True):
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
    myhash = md5_utf8(url)
    valid_cache = False
    source = None
    hashfilename = cacheLocation + os.path.sep + myhash + "." + cache.lower()
    expiry = lazylibrarian.CONFIG['CACHE_AGE'] * 24 * 60 * 60  # expire cache after this many seconds

    if useCache and os.path.isfile(hashfilename):
        cache_modified_time = os.stat(hashfilename).st_mtime
        time_now = time.time()
        if cache_modified_time < time_now - expiry:
            # Cache entry is too old, delete it
            logger.debug("Expiring %s" % myhash)
            os.remove(hashfilename)
        else:
            valid_cache = True

    if valid_cache:
        lazylibrarian.CACHE_HIT = int(lazylibrarian.CACHE_HIT) + 1
        if lazylibrarian.LOGLEVEL > 2:
            logger.debug("CacheHandler: Returning CACHED response %s for %s" % (hashfilename, url))
        if cache == "JSON":
            try:
                source = json.load(open(hashfilename))
            except ValueError:
                logger.debug("Error decoding json from %s" % hashfilename)
                return None, False
        elif cache == "XML":
            with open(hashfilename, "r") as cachefile:
                result = cachefile.read()
            if result and result.startswith('<?xml'):
                try:
                    source = ElementTree.fromstring(result)
                except ElementTree.ParseError:
                    source = None
            if source is None:
                logger.debug("Error reading xml from %s" % hashfilename)
                os.remove(hashfilename)
                return None, False
    else:
        lazylibrarian.CACHE_MISS = int(lazylibrarian.CACHE_MISS) + 1
        result, success = fetchURL(url)
        if success:
            logger.debug("CacheHandler: Storing %s %s for %s" % (cache, myhash, url))
            if cache == "JSON":
                try:
                    source = json.loads(result)
                    if not expiry:
                        return source, False
                except Exception as e:
                    logger.error("%s decoding json from %s" % (type(e).__name__, url))
                    logger.debug("%s : %s" % (e, result))
                    return None, False
                json.dump(source, open(hashfilename, "w"))
            elif cache == "XML":
                if result and result.startswith('<?xml'):
                    try:
                        source = ElementTree.fromstring(result)
                        if not expiry:
                            return source, False
                    except ElementTree.ParseError:
                        logger.debug("Error parsing xml from %s" % url)
                        source = None
                if source is not None:
                    with open(hashfilename, "w") as cachefile:
                        cachefile.write(result)
                else:
                    logger.debug("Error getting xml data from %s" % url)
                    return None, False
        else:
            logger.debug("Got error response for %s: %s" % (url, result))
            return None, False
    return source, valid_cache
