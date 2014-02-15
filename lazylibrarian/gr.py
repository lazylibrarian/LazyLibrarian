import urllib, urllib2, sys, re
import thread, threading, time, Queue
from xml.etree import ElementTree
from xml.etree.ElementTree import Element, SubElement

import lazylibrarian
from lazylibrarian import logger, formatter, database, SimpleCache

import lib.fuzzywuzzy as fuzzywuzzy
from lib.fuzzywuzzy import fuzz, process

import time

class GoodReads:
	# http://www.goodreads.com/api/

	def __init__(self, name=None):
		self.name = {"id": name.encode('utf-8')}
		#self.type = type
		self.params = {"key":  lazylibrarian.GR_API}

	def find_results(self, authorname=None, queue=None):
		threading.currentThread().name = "GR-SEARCH"
		resultlist = []
		api_hits = 0
		url = urllib.quote_plus(authorname.encode('utf-8'))
		set_url = 'http://www.goodreads.com/search.xml?q=' + url + '&' + urllib.urlencode(self.params)
		logger.info('Now searching GoodReads API with keyword: ' + authorname)
		logger.debug('Searching for %s at: %s' % (authorname, set_url))

		try:

			try:
				# Cache our request
				request = urllib2.Request(set_url)
				opener = urllib2.build_opener(SimpleCache.CacheHandler(".AuthorCache"), SimpleCache.ThrottlingProcessor(5))
				resp = opener.open(request)
				api_hits = api_hits + 1
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
				bookdesc = ''
				bookisbn = ''
				booklink = 'http://www.goodreads.com/book/show/'+author.find('./best_book/id').text

				if (author.find('./best_book/title').text == None):
					bookTitle = ""
				else:
					bookTitle = author.find('./best_book/title').text

				author_fuzz = fuzz.ratio(authorNameResult.lower(), authorname.lower())
				book_fuzz = fuzz.ratio(bookTitle.lower(), authorname.lower())
				try:
					isbn_check = int(authorname[:-1])
					if (len(str(isbn_check)) == 9) or (len(str(isbn_check)) == 12):
						isbn_fuzz = int(100)
					else:
						isbn_fuzz = int(0)
				except:
					isbn_fuzz = int(0)
				highest_fuzz = max(author_fuzz, book_fuzz, isbn_fuzz)

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
					'booklink': booklink,
					'bookrate': float(bookrate),
					'bookimg': bookimg,
					'bookpages': bookpages,
					'bookgenre': bookgenre,
					'bookdesc': bookdesc,
					'author_fuzz': author_fuzz,
					'book_fuzz': book_fuzz,
					'isbn_fuzz': isbn_fuzz,
					'highest_fuzz': highest_fuzz,
					'num_reviews': float(bookrate)
				})

				resultcount = resultcount+1

		except urllib2.HTTPError, err:                  
			if err.code == 404:
				logger.info('Received a 404 error when searching for author')
			if err.code == 403:
				logger.info('Access to api is denied: usage exceeded')
			else:
				logger.info('An unexpected error has occurred when searching for an author')

		logger.info('Found %s results with keyword: %s' % (resultcount, authorname))
		logger.info('The GoodReads API was hit %s times for keyword %s' % (str(api_hits), authorname))

		queue.put(resultlist)

	def find_author_id(self):

		URL = 'http://www.goodreads.com/api/author_url/?' + urllib.urlencode(self.name) + '&' + urllib.urlencode(self.params)
		logger.debug("Searching for author with name: %s" % self.name)

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
				authorname = author[0].text
				logger.info('Found author: %s with GoodReads-id: %s' % (authorname, authorid))

			authorlist = self.get_author_info(authorid, authorname)

		return authorlist

	def get_author_info(self, authorid=None, authorname=None, refresh=False):

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
			logger.info("[%s] Processing info for authorID: %s" % (authorname, authorid))

			author_dict = {
				'authorid':   resultxml[0].text,
				'authorlink':   resultxml.find('link').text,
				'authorimg':  resultxml.find('image_url').text,
				'authorborn':   resultxml.find('born_at').text,
				'authordeath':  resultxml.find('died_at').text,
				'totalbooks':   resultxml.find('works_count').text
				}
		return author_dict

	def get_author_books(self, authorid=None, authorname=None, refresh=False):

		api_hits = 0
		URL = 'http://www.goodreads.com/author/list/' + authorid + '.xml?' + urllib.urlencode(self.params)

		#Artist is loading
		myDB = database.DBConnection()
		controlValueDict = {"AuthorID": authorid}
		newValueDict = {"Status": "Loading"}
		myDB.upsert("authors", newValueDict, controlValueDict)
		
		try:
			# Cache our request
			request = urllib2.Request(URL)
			opener = urllib2.build_opener(SimpleCache.CacheHandler(".AuthorCache"), SimpleCache.ThrottlingProcessor(5))
			resp = opener.open(request)
			api_hits = api_hits + 1
			sourcexml = ElementTree.parse(resp)
		except Exception, e:
			logger.error("Error fetching author info: " + str(e))

		rootxml = sourcexml.getroot()
		resultxml = rootxml.getiterator('book')
		books_dict = []

		if not len(rootxml):
			logger.info('[%s] No books found for author with ID: %s' % (authorname, authorid))

		else:
			logger.info("[%s] Now processing books with GoodReads API" % authorname)

			resultsCount = 0
			removedResults = 0
			ignored = 0
			added_count = 0
			updated_count = 0
			book_ignore_count = 0
			total_count = 0
			logger.debug(u"url " + URL)

			authorNameResult = rootxml.find('./author/name').text
			logger.debug(u"author name " + authorNameResult)
			loopCount = 1;
			
			while (len(resultxml)):
				
				for book in resultxml:
					total_count = total_count + 1

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

					bookLanguage = "Unknown"

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

							logger.debug(u"language: " + str(bookLanguage))
						else:
							logger.debug("No ISBN provided, skipping")
							continue

					except Exception, e:
						logger.debug(u"An error has occured: " + str(e))

					if not bookLanguage:
						bookLanguage = "Unknown"
					valid_langs = ([valid_lang.strip() for valid_lang in lazylibrarian.IMP_PREFLANG.split(',')])
					if bookLanguage not in valid_langs:
						logger.debug('Skipped a book with language %s' % bookLanguage)
						ignored = ignored + 1
						continue

					bookname = book.find('title').text
					bookid = book.find('id').text
					bookdesc = book.find('description').text
					bookisbn = book.find('isbn').text
					bookpub = book.find('publisher').text
					booklink = book.find('link').text
					bookrate = float(book.find('average_rating').text)
					bookpages = book.find('num_pages').text

					find_book_status = myDB.select("SELECT * FROM books WHERE BookID = '%s'" % bookid)
					if find_book_status:
						for resulted in find_book_status:
							book_status = resulted['Status']
					else:
						book_status = "Skipped"
					
					if not (re.match('[^\w-]', bookname)): #remove books with bad caracters in title
						if book_status != "Ignored":
							controlValueDict = {"BookID": bookid}
							newValueDict = {
								"AuthorName":   authorNameResult,
								"AuthorID":     authorid,
								"AuthorLink":   None,
								"BookName":     bookname,
								"BookSub":      None,
								"BookDesc":     bookdesc,
								"BookIsbn":     bookisbn,
								"BookPub":      bookpub,
								"BookGenre":    None,
								"BookImg":      bookimg,
								"BookLink":     booklink,
								"BookRate":     bookrate,
								"BookPages":    bookpages,
								"BookDate":     pubyear,
								"BookLang":     bookLanguage,
								"Status":       book_status,
								"BookAdded":    formatter.today()
							}

							resultsCount = resultsCount + 1

							myDB.upsert("books", newValueDict, controlValueDict)
							logger.debug(u"book found " + book.find('title').text + " " + pubyear)
							if not find_book_status:
								logger.info("[%s] Added book: %s" % (authorname, bookname))
								added_count = added_count + 1
							else:
								logger.info("[%s] Updated book: %s" % (authorname, bookname))
								updated_count = updated_count + 1
						else:
							book_ignore_count = book_ignore_count + 1
					else:
						removedResults = removedResults + 1

				loopCount = loopCount + 1
				URL = 'http://www.goodreads.com/author/list/' + authorid + '.xml?' + urllib.urlencode(self.params) + '&page=' + str(loopCount)

				try:
					# Cache our request
					request1 = urllib2.Request(URL)
					opener1 = urllib2.build_opener(SimpleCache.CacheHandler(".AuthorCache"), SimpleCache.ThrottlingProcessor(5))
					resp1 = opener1.open(request1)
					api_hits = api_hits + 1
				except Exception, e:
					logger.error("Error finding results: " + str(e))				

				sourcexml = ElementTree.parse(resp1)
				rootxml = sourcexml.getroot()
				resultxml = rootxml.getiterator('book')

		logger.info('[%s] The GoodReads API was hit %s times to populate book list' % (authorname, str(api_hits)))
		
		lastbook = myDB.action("SELECT BookName, BookLink, BookDate from books WHERE AuthorID='%s' AND Status != 'Ignored' order by BookDate DESC" % authorid).fetchone()
		unignoredbooks = myDB.select("SELECT COUNT(BookName) as unignored FROM books WHERE AuthorID='%s' AND Status != 'Ignored'" % authorid)
		bookCount = myDB.select("SELECT COUNT(BookName) as counter FROM books WHERE AuthorID='%s'" % authorid)   

		controlValueDict = {"AuthorID": authorid}
		newValueDict = {
				"Status": "Active",
				"TotalBooks": bookCount[0]['counter'],
				"UnignoredBooks": unignoredbooks[0]['unignored'],
				"LastBook": lastbook['BookName'],
				"LastLink": lastbook['BookLink'],
				"LastDate": lastbook['BookDate']
				}
		myDB.upsert("authors", newValueDict, controlValueDict)

		#This is here because GoodReads sometimes has several entries with the same BookID!
		modified_count = added_count + updated_count
					
		logger.debug("Found %s total books for author" % total_count)
		logger.debug("Removed %s bad language results for author" % ignored)
		logger.debug("Removed %s bad character results for author" % removedResults)
		logger.debug("Ignored %s books by author marked as Ignored" % book_ignore_count)
		logger.debug("Imported/Updated %s books for author" % modified_count)
		if refresh:
			logger.info("[%s] Book processing complete: Added %s books / Updated %s books" % (authorname, str(added_count), str(updated_count)))
		else:
			logger.info("[%s] Book processing complete: Added %s books to the database" % (authorname, str(added_count)))
		return books_dict

	def find_book(self, bookid=None, queue=None):
		threading.currentThread().name = "GR-ADD-BOOK"
		myDB = database.DBConnection()

		URL = 'https://www.goodreads.com/book/show/' + bookid + '?' + urllib.urlencode(self.params)

		try:
			# Cache our request
			request = urllib2.Request(URL)
			opener = urllib2.build_opener(SimpleCache.CacheHandler(".AuthorCache"), SimpleCache.ThrottlingProcessor(5))
			resp = opener.open(request)
			sourcexml = ElementTree.parse(resp)
		except Exception, e:
			logger.error("Error fetching book info: " + str(e))

		rootxml = sourcexml.getroot()

		bookLanguage = rootxml.find('./book/language_code').text

		if not bookLanguage:
			bookLanguage = "Unknown"
		valid_langs = ([valid_lang.strip() for valid_lang in lazylibrarian.IMP_PREFLANG.split(',')])
		if bookLanguage not in valid_langs:
			logger.debug('Skipped a book with language %s' % bookLanguage)

		if (rootxml.find('./book/publication_year').text == None):
			bookdate = "0000"
		else:
			bookdate = rootxml.find('./book/publication_year').text

		try:
			bookimg = rootxml.find('./book/img_url').text
			if (bookimg == 'http://www.goodreads.com/assets/nocover/111x148.png'):
				bookimg = 'images/nocover.png'
		except KeyError:
			bookimg = 'images/nocover.png'
		except AttributeError:
			bookimg = 'images/nocover.png'

		authorname = rootxml.find('./book/authors/author/name').text
		bookname = rootxml.find('./book/title').text
		bookdesc = rootxml.find('./book/description').text
		bookisbn = rootxml.find('./book/isbn').text
		bookpub = rootxml.find('./book/publisher').text
		booklink = rootxml.find('./book/link').text
		bookrate = float(rootxml.find('./book/average_rating').text)
		bookpages = rootxml.find('.book/num_pages').text

		name = authorname
		GR = GoodReads(name)
		author = GR.find_author_id()
		if author:
			AuthorID = author['authorid']

		controlValueDict = {"BookID": bookid}
		newValueDict = {
			"AuthorName":   authorname,
			"AuthorID":     AuthorID,
			"AuthorLink":   None,
			"BookName":     bookname,
			"BookSub":      None,
			"BookDesc":     bookdesc,
			"BookIsbn":     bookisbn,
			"BookPub":      bookpub,
			"BookGenre":    None,
			"BookImg":      bookimg,
			"BookLink":     booklink,
			"BookRate":     bookrate,
			"BookPages":    bookpages,
			"BookDate":     bookdate,
			"BookLang":     bookLanguage,
			"Status":       "Wanted",
			"BookAdded":    formatter.today()
			}

		#print newValueDict
		myDB.upsert("books", newValueDict, controlValueDict)
		logger.info("%s added to the books database" % bookname)
