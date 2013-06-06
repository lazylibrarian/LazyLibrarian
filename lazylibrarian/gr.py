import time, threading, urllib, urllib2, sys, re
from xml.etree import ElementTree
from xml.etree.ElementTree import Element, SubElement

import lazylibrarian
from lazylibrarian import logger, formatter, database, SimpleCache

import time

class GoodReads:
    # http://www.goodreads.com/api/

    def __init__(self, name=None, type=None):
        self.name = {"id": name.encode('utf-8')}
        self.type = type
        self.params = {"key":  lazylibrarian.GR_API}

    def find_author_id(self):

        URL = 'http://www.goodreads.com/api/author_url/?' + urllib.urlencode(self.name) + '&' + urllib.urlencode(self.params)
        logger.info("Searching for author with name: %s" % self.name)

        # Cache our request
        request = urllib2.Request(URL)
        opener = urllib2.build_opener(SimpleCache.CacheHandler(".AuthorCache"), SimpleCache.ThrottlingProcessor(5))
        resp = opener.open(request)

        try:
            sourcexml = ElementTree.parse(resp)
        except Exception, e:
            logger.error("Error fetching authorid: " + str(e))
        
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

            time.sleep(5)
            authorlist = self.get_author_info(authorid)
        
        return authorlist

    def get_author_info(self, authorid=None):

        URL = 'http://www.goodreads.com/author/show/' + authorid + '.xml?' + urllib.urlencode(self.params)

        # Cache our request
        request = urllib2.Request(URL)
        opener = urllib2.build_opener(SimpleCache.CacheHandler(".AuthorCache"), SimpleCache.ThrottlingProcessor(5))
        resp = opener.open(request)

        try:
            sourcexml = ElementTree.parse(resp)
            rootxml = sourcexml.getroot()
            resultxml = rootxml.find('author')
            author_dict = {}
        except Exception, e:
            logger.error("Error fetching author ID: " + str(e))

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

    def get_author_books(self, authorid=None):

        URL = 'http://www.goodreads.com/author/list/' + authorid + '.xml?' + urllib.urlencode(self.params)
        
        try:
            # Cache our request
            request = urllib2.Request(URL)
            opener = urllib2.build_opener(SimpleCache.CacheHandler(".AuthorCache"), SimpleCache.ThrottlingProcessor(5))
            resp = opener.open(request)
            sourcexml = ElementTree.parse(resp)
        except Exception, e:
            logger.error("Error fetching author info: " + str(e))

        rootxml = sourcexml.getroot()
        resultxml = rootxml.getiterator('book')
        books_dict = []

        if not len(rootxml):
            logger.info('No books found for author with ID: %s' % authorid)

        else:
            logger.info("Processing books for author with ID: %s" % authorid)

            resultsCount = 0
            removedResults = 0
            logger.debug(u"url " + URL)

            authorNameResult = rootxml.find('./author/name').text
            logger.debug(u"author name " + authorNameResult)
            loopCount = 1;
            
            while (len(resultxml)):
				
				for book in resultxml:
					if (book.find('publication_year').text == None):
						pubyear = "0000"
					else:
						pubyear = book.find('publication_year').text
	
					try:
						bookimg = book.find('image_url').text
						if (bookimg == 'http://www.goodreads.com/assets/nocover/111x148.png'):
							bookimg = 'images/nocover.png'
					except KeyError:
						bookimg = 'images/nocover.png'
					except AttributeError:
						bookimg = 'images/nocover.png'

					bookLanguage = 'Unknown'
					
					try:
						time.sleep(1) #sleep 1 second to respect goodreads api terms

						if (book.find('isbn13').text is not None):
							BOOK_URL = 'http://www.goodreads.com/book/isbn?isbn=' + book.find('isbn13').text + '&' + urllib.urlencode(self.params) 

							logger.debug(u"Book URL: " + str(BOOK_URL))
							
							try:
							    # Cache our request
							    request = urllib2.Request(BOOK_URL)
							    opener = urllib2.build_opener(SimpleCache.CacheHandler(".AuthorCache"), SimpleCache.ThrottlingProcessor(5))
							    resp = opener.open(request)
							except Exception, e:
							    logger.error("Error finding results: ", e)

							BOOK_sourcexml = ElementTree.parse(resp)
							BOOK_rootxml = BOOK_sourcexml.getroot()
							bookLanguage = BOOK_rootxml.find('./book/language_code').text
							logger.debug(u"language: " + str(BOOK_rootxml.find('./book/language_code').text))
					except Exception, e:
						logger.debug(u"An error has occured: " + str(e))

					if (bookLanguage is None):
						bookLanguage = "Unknown"
					
					if not (re.match('[^\w-]', book.find('title').text)): #remove books with bad caracters in title
						myDB = database.DBConnection()
						controlValueDict = {"BookID": book.find('id').text}
						newValueDict = {
						    "AuthorName":   authorNameResult,
						    "AuthorID":     authorid,
						    "AuthorLink":   "",
						    "BookName":     book.find('title').text,
						    "BookSub":      "",
						    "BookDesc":     book.find('description').text,
						    "BookIsbn":     book.find('isbn').text,
						    "BookPub":      book.find('publisher').text,
						    "BookGenre":    "",
						    "BookImg":      bookimg,
						    "BookLink":     book.find('link').text,
						    "BookRate":     float(book.find('average_rating').text),
						    "BookPages":    book.find('num_pages').text,
						    "BookDate":     pubyear,
						    "BookLang":     bookLanguage,
						    "Status":       "Skipped",
						    "BookAdded":    formatter.today()
						}

						myDB.upsert("books", newValueDict, controlValueDict)
						logger.debug(u"book found " + book.find('title').text + " " + pubyear)
						resultsCount = resultsCount + 1
						
						lastbook = myDB.action("SELECT BookName, BookLink, BookDate from books WHERE AuthorID='%s' order by BookDate DESC" % authorid).fetchone()
						bookCount = myDB.select("SELECT COUNT(BookName) as counter FROM books WHERE AuthorID='%s'" % authorid)			
						for count in bookCount:
						    controlValueDict = {"AuthorID": authorid}
						    newValueDict = {
						            "Status": "Active",
						            "TotalBooks": count['counter'],
						            "LastBook": lastbook['BookName'],
						            "LastLink": lastbook['BookLink'],
						            "LastDate": lastbook['BookDate']
						            }
						    myDB.upsert("authors", newValueDict, controlValueDict)
						    
					logger.debug(u"book found " + book.find('title').text + " " + pubyear)
					if  (re.match('[^\w-]', book.find('title').text)):
						removedResults = removedResults + 1
				loopCount = loopCount + 1
				URL = 'http://www.goodreads.com/author/list/' + authorid + '.xml?' + urllib.urlencode(self.params) + '&page=' + str(loopCount)
				
				try:
				    # Cache our request
				    request1 = urllib2.Request(URL)
				    opener1 = urllib2.build_opener(SimpleCache.CacheHandler(".AuthorCache"), SimpleCache.ThrottlingProcessor(5))
				    resp1 = opener1.open(request1)
				except Exception, e:
				    logger.error("Error finding results: " + str(e))				

				sourcexml = ElementTree.parse(resp1)
				rootxml = sourcexml.getroot()
				resultxml = rootxml.getiterator('book')
				
					
        logger.debug("Removed %s non-english and no publication year results for author" % removedResults)
        logger.debug("Found %s books for author" % resultsCount)
        logger.info("Processing complete: Added %s books to the database" % str(count['counter']))
        return books_dict
	
#Added .encode to allow for characters to be converted to utf-8 to be used in the search function.
	
    def find_results(self, authorname=None):
        resultlist = []
        logger.info(authorname)
        url = urllib.quote_plus(authorname.encode('utf-8'))
        set_url = 'http://www.goodreads.com/search.xml?q=' + url + '&' + urllib.urlencode(self.params)
        logger.info('Searching for author at: %s' % set_url)

        try:

            try:
                # Cache our request
                request = urllib2.Request(set_url)
                opener = urllib2.build_opener(SimpleCache.CacheHandler(".AuthorCache"), SimpleCache.ThrottlingProcessor(5))
                resp = opener.open(request)
                sourcexml = ElementTree.parse(resp)
            except Exception, e:
                logger.error("Error finding results: " + str(e))

            rootxml = sourcexml.getroot()
            resultxml = rootxml.getiterator('work')
            author_dict = []
            resultcount = 0
            for author in resultxml:
                bookdate = "0001-01-01"

                if (author.find('original_publication_year').text == None):
                    bookdate = "0000"
                else:
                    bookdate = author.find('original_publication_year').text

                authorNameResult = author.find('./best_book/author/name').text
                booksub = ""
                bookpub = ""
                booklang = "en"

                try:
                    bookimg = author.find('./best_book/image_url').text
                    if (bookimg == 'http://www.goodreads.com/assets/nocover/111x148.png'):
                        bookimg = 'images/nocover.png'
                except KeyError:
                    bookimg = 'images/nocover.png'
                except AttributeError:
                    bookimg = 'images/nocover.png'

                try:
                    bookrate = author.find('average_rating').text
                except KeyError:
                    bookrate = 0

                bookpages = '0'
                bookgenre = ''
                bookdesc = 'Not available'

                bookisbn = author.find('./best_book/id').text

                if (author.find('./best_book/title').text == None):
                    bookTitle = ""
                else:
                    bookTitle = author.find('./best_book/title').text

                resultlist.append({
					'authorname': author.find('./best_book/author/name').text,
					'bookid': author.find('./best_book/id').text,
					'authorid' : author.find('./best_book/author/id').text,
					'bookname': bookTitle.encode("ascii", "ignore"),
					'booksub': booksub,
					'bookisbn': bookisbn,
					'bookpub': bookpub,
					'bookdate': bookdate,
					'booklang': booklang,
					'booklink': '/',
					'bookrate': float(bookrate),
					'bookimg': bookimg,
					'bookpages': bookpages,
					'bookgenre': bookgenre,
					'bookdesc': bookdesc
				})

                resultcount = resultcount+1

        except urllib2.HTTPError, err:               	
            if err.code == 404:
                logger.info('Received a 404 error when searching for author')
            if err.code == 403:
                logger.info('Access to api is denied: usage exceeded')
            else:
                logger.info('An unexpected error has occurred when searching for an author')

            logger.info('Found %s results' % (resultcount))

        return resultlist
