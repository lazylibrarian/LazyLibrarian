import time, threading, urllib, urllib2, os, re

from xml.etree import ElementTree
from xml.etree.ElementTree import Element, SubElement

import lazylibrarian

from lazylibrarian import logger

class NZBProviders:

    @staticmethod
    def NewzNab(bookid=None, searchterm=None):
        with threading.Lock():

            HOST = lazylibrarian.NEWZNAB_HOST

            params = {
                "t": "search",
                "apikey": lazylibrarian.NEWZNAB_API,
                "cat": 7020,
                "q": searchterm
                }

            if not str(HOST)[:4] == "http":
                HOST = 'http://' + HOST

            URL = HOST + '/api?' + urllib.urlencode(params)

            # to debug because of api
            logger.debug(u'Parsing results from <a href="%s">%s</a>' % (URL, lazylibrarian.NEWZNAB_HOST))

            try:
                sourcexml = ElementTree.parse(urllib2.urlopen(URL, timeout=20))
                url_error = False
            except urllib2.URLError, e:
                logger.warn('Error fetching data from %s: %s' % (lazylibrarian.NEWZNAB_HOST, e))
                url_error = True

            if not url_error:
                rootxml = sourcexml.getroot()
                resultxml = rootxml.iter('item')
                nzbs = []

                if not len(rootxml):
                    logger.error('Nothing found @ URL: ' + URL)

                else:
                    for item in resultxml:
                        if item is None:
                            logger.info('No nzbs found with : %s' % searchterm)
                        else:
                            nzbs.append({
                                'jobname': item[0].text,
                                'provlink': item[1].text,
                                'nzblink': item[2].text,
                                'pubdate': item[4].text,
                                'description': item[6].text,
                                'filesize': item[7].attrib.get('length')
                                })

            wanted_dict = {"BookID": bookid}
            wanted_dict['nzbs'] = nzbs
            return wanted_dict
