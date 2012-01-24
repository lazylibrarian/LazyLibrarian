import time, threading, urllib, sys
from xml.etree import ElementTree
from xml.etree.ElementTree import Element, SubElement

import lazylibrarian
from lazylibrarian import logger, formatter, database

class GoodReads:
    # http://www.goodreads.com/api/

    @staticmethod
    def find_author_name(name):
        with threading.Lock():
            BASE_URL = 'http://www.goodreads.com/api/author_url/'
            BASE_API = '.xml?key=ckvsiSDsuqh7omh74ZZ6Q'
            URL = '%s%s%s' % (BASE_URL, name, BASE_API)
            logger.info("Searching for author with name: %s" % name)

            sourcexml = ElementTree.parse(urllib.urlopen(URL))
            rootxml = sourcexml.getroot()
            resultxml = rootxml.iter('author')

            if not len(rootxml):
                logger.info('No authors found with name: %s' % name)
                authorlist = []
            else:
                authorlist = []
                for author in resultxml:
                    logger.info('Found author: %s' % author[0].text)
                    authorlist.append({
                        'authorid':   author.attrib.get("id"),
                        'authorname': author[0].text,
                        'authorlink': author[1].text
                        })
            return authorlist

    @staticmethod
    def find_book_name(name):
        with threading.Lock():
            BASE_URL = 'http://www.goodreads.com/search/index.xml?key=ckvsiSDsuqh7omh74ZZ6Q&search[field]=title&q='
            URL = '%s%s' % (BASE_URL, name)
            logger.info("Searching for books with name: %s" % name)

            sourcexml = ElementTree.parse(urllib.urlopen(URL))
            rootxml = sourcexml.getroot()
            resultxml = rootxml.iter('work')

            if not len(rootxml):
                logger.info('No books found with name: %s' % name)
                booklist = []
            else:
                # logger.info('Found %s books with name: %s' % len(resultxml), name)
                booklist = []

                for book in resultxml:
                    work = book.find('best_book')
                    authorlink = 'http://www.goodreads.com/author/show/'
                    booklink = 'http://www.goodreads.com/book/show/'
                    booklist.append({
                        'authorid':     work.find('author')[0].text,
                        'authorname':   work.find('author')[1].text,
                        'authorlink':   '%s%s' % (authorlink, work.find('author')[0].text),
                        'bookid':       work[0].text,
                        'bookname':     work[1].text,
                        'booklink':     '%s%s' % (booklink, work[0].text),
                        'bookrate':     float(book.find('average_rating').text),
                        'bookimg_s':    work.find('small_image_url').text,
                        'bookimg_m':    work.find('image_url').text
                        })
                return booklist

    @staticmethod
    def get_author_info(authorid):
        with threading.Lock():

            URL = 'http://www.goodreads.com/author/show/%s.xml?key=ckvsiSDsuqh7omh74ZZ6Q' % authorid
            sourcexml = ElementTree.parse(urllib.urlopen(URL))
            rootxml = sourcexml.getroot()
            resultxml = rootxml.find('author')
            author_dict = {}

            if not len(rootxml):
                logger.info('No author found with ID: ' + authorid)

            else:
                logger.info("Processing info for authorID: %s" % authorid)

                author_dict = {
                    'authorname':   resultxml[1].text,
                    'authorlink':   resultxml.find('link').text,
                    'authorimg_s':  resultxml.find('small_image_url').text,
                    'authorimg_l':  resultxml.find('image_url').text,
                    'authorborn':   resultxml.find('born_at').text,
                    'authordeath':  resultxml.find('died_at').text,
                    'totalbooks':   resultxml.find('works_count').text
                    }
                totalbooks = int(float(resultxml.find('works_count').text))

            # pause 1 to respect api terms
            time.sleep(1)

            books = []
            bookcount = 0
            pagenumber = 0
            while totalbooks > bookcount:

                if pagenumber == 0:
                    logger.info("Processing books for authorID: %s" % authorid)
                    page = ''
                else:
                    time.sleep(1)
                    logger.info("Processing books page %s" % pagenumber)
                    page = '&page=%s' % pagenumber

                URL = 'http://www.goodreads.com/author/list/%s.xml?key=ckvsiSDsuqh7omh74ZZ6Q%s' % (authorid, page)
                sourcexml = ElementTree.parse(urllib.urlopen(URL))
                rootxml = sourcexml.getroot()
                resultxml = rootxml.iter('book')

                if not len(rootxml):
                    logger.info('No author found with ID: ' + authorid)

                else:
                    for book in resultxml:
                        books.append({
                            'bookid':       book[0].text,
                            'bookisbn':     book[1].text,
                            'bookname':     book[4].text,
                            'booklink':     book.find('link').text,
                            'bookimg_s':    book.find('small_image_url').text,
                            'bookimg_l':    book.find('image_url').text,
                            'bookpages':    book.find('num_pages').text,
                            'bookrate':     float(book.find('average_rating').text),
                            'bookdate':     book.find('published').text
                            })
                    bookcount = len(books)
                    pagenumber = pagenumber+1

            author_dict['books'] = books
            return author_dict
