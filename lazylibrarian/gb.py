# example
# https://www.googleapis.com/books/v1/volumes?q=+inauthor:george+martin+intitle:song+ice+fire

import urllib, urllib2, json, re

import lazylibrarian
from lazylibrarian import logger, formatter, database

class GoogleBooks:

def find_book_name(name=None):

    url = 'https://www.googleapis.com/books/v1/volumes?q=' + urllib.quote_plus('intitle:' + self.name)
    jsonresults = json.JSONDecoder().decode(urllib2.urlopen(url, timeout=30).read())
    for item in jsonresults['items']:
        try:
            BookImgl = item['volumeInfo']['imageLinks']['thumbnail']
        except KeyError:
            logger.debug('No thumbnail found for: ' + self.name)


def find_author_name(name=None):
    url = 'https://www.googleapis.com/books/v1/volumes?q=' + urllib.quote_plus('inauthor:' + self.name)
    jsonresults = json.JSONDecoder().decode(urllib.urlopen(url).read())
    print jsonresults
    for item in jsonresults['items']:
        try:
            BookImgl = item['volumeInfo']['imageLinks']['thumbnail']
        except KeyError:
            logger.debug('No thumbnail found for: ' + self.name)

#            print item['volumeInfo']['title'], 'BookName'
#            print item['volumeInfo']['language'], 'BookLang'
#            print item['volumeInfo']['authors'][0:], 'AuthorNames'
#            print item['volumeInfo']['pageCount'], 'BookPages'
#            print item['volumeInfo']['imageLinks']



