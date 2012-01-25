import os, urllib, urllib2
import datetime

import lazylibrarian

from lazylibrarian import logger, database

def SABnzbd(nzbname=None, nzblink=None):

    HOST = lazylibrarian.SAB_HOST + ":" + lazylibrarian.SAB_PORT
    if not str(HOST)[:4] == "http":
        HOST = 'http://' + HOST

    params = {
        "nzbname": nzbname,
        "apikey": lazylibrarian.SAB_API
        }

    if lazylibrarian.SAB_CAT:
        params["cat"] = lazylibrarian.SAB_CAT

    ## FUTURE-CODE
    #        if lazylibrarian.SAB_PRIO:
    #            params["priority"] = lazylibrarian.SAB_PRIO
    #        if lazylibrarian.SAB_PP:
    #            params["script"] = lazylibrarian.SAB_SCRIPT

    URL = HOST + "/api?mode=addurl&name=" + nzblink + urllib.urlencode(params)

    # to debug because of api
    logger.debug(u'Request url for <a href="%s">SABnzbd</a>' % URL)

    try:
        request = urllib2.urlopen(URL)

    except (EOFError, IOError), e:
        logger.error(u"Unable to connect to SAB with URL: %s" % url)
        return False

    except httplib.InvalidURL, e:
        logger.error(u"Invalid SAB host, check your config. Current host: %s" % HOST)
        return False

    result = request.read().strip()
    if not result:
        log.error("SABnzbd didn't return anything.")
        return False

    logger.debug("Result text from SAB: " + result)
    if result == "ok":
        logger.info("NZB sent to SAB successfully.")
        return True
    elif result == "Missing authentication":
        logger.error("Incorrect username/password.")
        return False
    else:
        logger.error("Unknown error: " + result)
        return False
