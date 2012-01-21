import time, threading, urllib
from xml.etree import ElementTree
from xml.etree.ElementTree import Element, SubElement
#from xml.dom.minidom import parse

import lazylibrarian
from lazylibrarian import logger, formatter, database

class GoodReads:
    # http://www.goodreads.com/api/author_url/Orson%20Scott%20Card.xml?key=ckvsiSDsuqh7omh74ZZ6Q

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
                print booklist
                return booklist

    @staticmethod
    def find_author_booklist(name):
        with threading.Lock():
            URL = 'http://www.goodreads.com/author/list/%s.xml?key=ckvsiSDsuqh7omh74ZZ6Q' % name
            logger.info('Find all books from author with ID: ' + name)

            sourcexml = ElementTree.parse(urllib.urlopen(URL))
            rootxml = sourcexml.getroot()
            resultxml = rootxml.iter('book')

            if not len(rootxml):
                logger.info('No books found for author with ID: ' + name)
                booklist = []
            else:
                booklist = []

                for book in resultxml:
                    booklist.append({
                        'bookid':       book[1],
                        'bookisbn':     book[2],
                        'bookname':     book.find('title').text,
                        'booklink':     book.find('link').text,
                        'bookrate':     float(book.find('average_rating').text),
                        'bookimg_s':    book.find('small_image_url').text,
                        'bookimg_l':    book.find('image_url').text,
                        'bookpages':    book.find('num_pages').text
                        })
                return booklist

    @staticmethod
    def get_author_info(authorid):
        with threading.Lock():

            author_dict = {}

            URL = 'http://www.goodreads.com/author/show/%s.xml?key=ckvsiSDsuqh7omh74ZZ6Q' % authorid
            logger.info("Processing info for authorID: %s" % authorid)

            sourcexml = ElementTree.parse(urllib.urlopen(URL))
            rootxml = sourcexml.getroot()
            resultxml = rootxml.find('author')

            if not len(rootxml):
                logger.info('No author found with ID: ' + authorid)
            else:

                author_dict = {
                    'authorname':   resultxml[1].text,
                    'authorlink':   resultxml.find('link').text,
                    'authorimg_s':  resultxml.find('small_image_url').text,
                    'authorimg_l':  resultxml.find('image_url').text,
                    'totalbooks':   resultxml.find('works_count').text
                    }

                books = []
                resultxml = rootxml.iter('book')

                for book in resultxml:
                    books.append({
                        'bookid':       book[0].text,
                        'bookisbn':     book[1].text,
                        'bookname':     book[4].text,
                        'booklink':     book.find('link').text,
                        'bookimg_s':    book.find('small_image_url').text,
                        'bookimg_l':    book.find('image_url').text,
                        'bookpages':    book.find('num_pages').text,
                        'bookrate':     float(book.find('average_rating').text)
                        })

            author_dict['books'] = books
            return author_dict

    @staticmethod
    def get_author_books(authorid):
        with threading.Lock():

            book_dict = {}

            URL = 'http://www.goodreads.com/author/show/%s.xml?key=ckvsiSDsuqh7omh74ZZ6Q' % authorid
            logger.info("Find books from author with ID: %s" % authorid)

            sourcexml = ElementTree.parse(urllib.urlopen(URL))
            rootxml = sourcexml.getroot()
            resultxml = rootxml.iter('book')

            for book in resultxml:
                book_dict = {
                    'bookid':       book[0].text,
                    'bookisbn':     book[1].text,
                    'bookname':     book[4].text,
                    'booklink':     book.find('link').text,
                    'bookimg_s':    book.find('small_image_url').text,
                    'bookimg_l':    book.find('image_url').text,
                    'bookpages':    book.find('num_pages').text,
                    'bookrate':     float(book.find('average_rating').text)
                    }

            return book_dict
