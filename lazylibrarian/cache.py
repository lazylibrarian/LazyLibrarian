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
import shutil
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
    if lazylibrarian.CONFIG['PROXY_HOST']:
        request.set_proxy(lazylibrarian.CONFIG['PROXY_HOST'], lazylibrarian.CONFIG['PROXY_TYPE'])
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
        logger.debug(u"fetchURL: retrying - got timeout on %s" % URL)
        result, success = fetchURL(URL, headers=headers, retry=False)
        return result, success
    except Exception as e:
        if hasattr(e, 'reason'):
            return e.reason, False
        return str(e), False


def cache_img(img_type, img_ID, img_url, refresh=False):
    """ Cache the image from the given filename or URL in the local images cache
        linked to the id, return the link to the cached file, True
        or error message, False if failed to cache """

    if img_type not in ['book', 'author']:
        logger.debug('Internal error in cache_img, img_type = [%s]' % img_type)
        img_type = 'book'

    cachefile = os.path.join(lazylibrarian.CACHEDIR, img_type, img_ID + '.jpg')
    link = 'cache/%s/%s.jpg' % (img_type, img_ID)
    if os.path.isfile(cachefile) and not refresh:  # overwrite any cached image
        return link, True

    if img_url.startswith('http'):
        result, success = fetchURL(img_url)
        if success:
            try:
                with open(cachefile, 'wb') as img:
                    img.write(result)
                return link, True
            except Exception as e:
                logger.debug("Error writing image to %s, %s" % (cachefile, str(e)))
                return str(e), False
        return result, False
    else:
        try:
            shutil.copyfile(img_url, cachefile)
            return link, True
        except Exception as e:
            logger.debug("Error copying image to %s, %s" % (cachefile, str(e)))
            return str(e), False


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
        expiry = lazylibrarian.CONFIG['CACHE_AGE'] * 24 * 60 * 60  # expire cache after this many seconds
        if cache_modified_time < time_now - expiry:
            # Cache entry is too old, delete it
            os.remove(hashfilename)
        else:
            valid_cache = True

    if valid_cache:
        lazylibrarian.CACHE_HIT = int(lazylibrarian.CACHE_HIT) + 1
        logger.debug(u"CacheHandler: Returning CACHED response for %s" % url)
        if cache == "JSON":
            try:
                source = json.load(open(hashfilename))
            except ValueError:
                logger.debug(u"Error decoding json from %s" % hashfilename)
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
                logger.debug(u"Error reading xml from %s" % hashfilename)
                os.remove(hashfilename)
                return None, False
    else:
        lazylibrarian.CACHE_MISS = int(lazylibrarian.CACHE_MISS) + 1
        result, success = fetchURL(url)
        if success:
            logger.debug(u"CacheHandler: Storing %s for %s" % (cache, url))
            if cache == "JSON":
                try:
                    source = json.loads(result)
                except Exception as e:
                    logger.debug(u"Error decoding json from %s" % url)
                    logger.debug(u"%s : %s" % (e, result))
                    return None, False
                json.dump(source, open(hashfilename, "w"))
            elif cache == "XML":
                if result and result.startswith('<?xml'):
                    try:
                        source = ElementTree.fromstring(result)
                    except ElementTree.ParseError:
                        logger.debug(u"Error parsing xml from %s" % url)
                        source = None
                if source is not None:
                    with open(hashfilename, "w") as cachefile:
                        cachefile.write(result)
                else:
                    logger.debug(u"Error getting xml data from %s" % url)
                    return None, False
        else:
            logger.debug(u"Got error response for %s: %s" % (url, result))
            return None, False
    return source, valid_cache
