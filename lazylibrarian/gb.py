# example
# https://www.googleapis.com/books/v1/volumes?q=+inauthor:george+martin+intitle:song+ice+fire

import urllib, urllib2, json, time

import lazylibrarian
from lazylibrarian import logger, formatter, database

class GoogleBooks:

    def __init__(self, name=None, type=None):
        self.name = name
        self.type = type
        self.url = 'https://www.googleapis.com/books/v1/volumes?q='
        self.params = {
            'maxResults': 40,
            'printType': 'books',
            }


    def find_results(self):
        resultlist = []

        if self.type == 'book':
            set_url = self.url + urllib.quote('intitle:' + '"' + self.name + '"')
        else:
            set_url = self.url + urllib.quote('inauthor:' + '"' + self.name + '"')

        logger.info('Searching url: ' + URL)

        try:
            startindex = 0
            resultcount = 0
            while True:

                self.params['startIndex'] = startindex
                URL = set_url + '&' + urllib.urlencode(self.params)

                jsonresults = json.JSONDecoder().decode(urllib2.urlopen(URL, timeout=30).read())
                startindex = startindex+40

                for item in jsonresults['items']:

                    try:
                        authorname = item['volumeInfo']['authors'][0]
                    except KeyError:
                        logger.debug('Skipped a result without authorfield.')
                        # skip if no author, no author is no book.
                        break

                    bookname = item['volumeInfo']['title']
                    logger.info('Collecting info for: ' + bookname)

                    # need to find which items aren't common to be on GBS and set 'm in tries.
                    try:
                        bookrate = float(item['volumeInfo']['averageRating'])
                    except KeyError:
                        bookrate = 0

                    try:
                        bookpage = item['volumeInfo']['pageCount']
                    except KeyError:
                        bookpage = 'Unknown'

                    try:
                        bookgenre = item['volumeInfo']['categories']
                    except KeyError:
                        bookgenre = 'Unknown'

                    try:
                        bookdesc = item['volumeInfo']['description']
                    except KeyError:
                        bookdesc = 'Not available'

                    resultlist.append({
                        'authorname': authorname,
                        'bookid': item['id'],
                        'bookname': bookname,
                        'booklink': item['volumeInfo']['canonicalVolumeLink'],
                        'bookisbn': item['volumeInfo']['industryIdentifiers'][0]['identifier'],
                        'bookrate': bookrate,
                        'bookimg': item['volumeInfo']['canonicalVolumeLink'] + '&printsec=frontcover&img=1&zoom=1',
                        'bookpage': bookpage,
                        'bookgenre': bookgenre,
                        'bookdesc': bookdesc
                        })

                time.sleep(1)
                resultcount = resultcount+len(resultlist)

        except KeyError:
            logger.info('Found %s results for %s with name: %s' % (resultcount, self.type, self.name))

        return resultlist




