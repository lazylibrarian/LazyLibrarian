import time, threading, urllib, urllib2, sys
from xml.etree import ElementTree
from xml.etree.ElementTree import Element, SubElement

import lazylibrarian
from lazylibrarian import logger, formatter, database

class GoodReads:
    # http://www.goodreads.com/api/

    def __init__(self, name=None, type=None):
        self.name = {"id": name}
        self.type = type
        self.params = {"key":  lazylibrarian.GR_API}

    def find_author_id(self):

        URL = 'http://www.goodreads.com/api/author_url/?' + urllib.urlencode(self.name) + '&' + urllib.urlencode(self.params)
        logger.info("Searching for author with name: %s" % self.name)

        try:
            sourcexml = ElementTree.parse(urllib2.urlopen(URL, timeout=20))
        except (urllib2.URLError, IOError, EOFError), e:
            logger.error("Error fetching authorid: ", e)
        
        rootxml = sourcexml.getroot()
        resultxml = rootxml.getiterator('author')
        authorlist = []

        if not len(rootxml):
            logger.info('No authors found with name: %s' % self.name)
            return authorlist
        else:
            for author in resultxml:
                authorid = author.attrib.get("id")
                logger.info('Found author: %s with GoodReads-id: %s' % (author[0].text, authorid))

            time.sleep(1)
            authorlist = self.get_author_info(authorid)
        return authorlist

    def get_author_info(self, authorid=None):

        URL = 'http://www.goodreads.com/author/show/' + authorid + '.xml?' + urllib.urlencode(self.params)
        sourcexml = ElementTree.parse(urllib2.urlopen(URL, timeout=20))
        rootxml = sourcexml.getroot()
        resultxml = rootxml.find('author')
        author_dict = {}

        if not len(rootxml):
            logger.info('No author found with ID: ' + authorid)

        else:
            logger.info("Processing info for authorID: %s" % authorid)

            author_dict = {
                'authorid':   resultxml[0].text,
                'authorlink':   resultxml.find('link').text,
                'authorimg':  resultxml.find('image_url').text,
                'authorborn':   resultxml.find('born_at').text,
                'authordeath':  resultxml.find('died_at').text,
                'totalbooks':   resultxml.find('works_count').text
                }
        return author_dict
