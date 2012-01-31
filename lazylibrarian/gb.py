# example
# https://www.googleapis.com/books/v1/volumes?q=+inauthor:george+martin+intitle:song+ice+fire

import urllib, urllib2, json, re

import lazylibrarian
from lazylibrarian import logger, formatter, database

class GoogleBooks:

    def __init__(self, name=None):
        self.name = name
        self.url = 'https://www.googleapis.com/books/v1/volumes?q='

    def find_book_name(self):

        URL = self.url + urllib.quote_plus('intitle:' + self.name)
        jsonresults = json.JSONDecoder().decode(urllib2.urlopen(URL, timeout=30).read())
        print URL
        booklist = []
        #print jsonresults
        for item in jsonresults['items']:
            # try for author, if no author, skip result.
            try:
                item['volumeInfo']['authors'][0]
            except KeyError:
                logger.debug('No author found for %s, skipping this one ...' % item['volumeInfo']['title'])
                break

            booklist.append({
                'authorname': item['volumeInfo']['authors'][0],
                'bookid': item['volumeInfo']['id'],
                'bookname': item['volumeInfo']['title'],
                'booklink': item['volumeInfo']['canonicalVolumeLink'],
                'bookrate': item['volumeInfo']['averageRating'],
                'bookdesc': item['volumeInfo']['industryIdentifiers'][0]['identifier']
                })

            # need to find which items aren't common to be on GBS and set 'm in tries.
            try:
                booklist.append({'bookimgl': item['volumeInfo']['imageLinks']['thumbnail']})
            except KeyError:
                logger.debug('No thumbnail found for: ' + self.name)

        return booklist



    def find_author_name(name=None):
        url = 'https://www.googleapis.com/books/v1/volumes?q=' + urllib.quote_plus('inauthor:' + name)
        jsonresults = json.JSONDecoder().decode(urllib.urlopen(url).read())
        print jsonresults
        for item in jsonresults['items']:
            try:
                BookImgl = item['volumeInfo']['imageLinks']['thumbnail']
            except KeyError:
                logger.debug('No thumbnail found for: ' + self.name)



