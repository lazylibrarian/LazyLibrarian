import urllib, urllib2, sys, re
import thread, threading, time, Queue
from xml.etree import ElementTree
from xml.etree.ElementTree import Element, SubElement

import lazylibrarian
from lazylibrarian import logger, formatter, database, SimpleCache

from lazylibrarian.common import USER_AGENT

import lib.fuzzywuzzy as fuzzywuzzy
from lib.fuzzywuzzy import fuzz, process

import time
from lib.unidecode import unidecode

class GoodReads:
	# http://www.goodreads.com/api/

	def __init__(self, name=None):
		self.name = name.encode('utf-8')
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
				if lazylibrarian.PROXY_HOST:
					request.set_proxy(lazylibrarian.PROXY_HOST, lazylibrarian.PROXY_TYPE)
				request.add_header('User-Agent', USER_AGENT)
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
				booklang = "Unknown" 

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

		logger.debug('Found %s results with keyword: %s' % (resultcount, authorname))
		logger.debug('The GoodReads API was hit %s times for keyword %s' % (str(api_hits), authorname))

		queue.put(resultlist)

	def find_author_id(self):
		author = self.name
		author = author.replace('. ',' ')
		author = author.replace('.',' ')
		author = author.replace('  ',' ')
		URL = 'http://www.goodreads.com/api/author_url/' + urllib.quote(author) + '?' + urllib.urlencode(self.params)
		logger.debug("Searching for author with name: %s" % author)
		
		# Cache our request
		request = urllib2.Request(URL)
		if lazylibrarian.PROXY_HOST:
			request.set_proxy(lazylibrarian.PROXY_HOST, lazylibrarian.PROXY_TYPE)
		request.add_header('User-Agent', USER_AGENT)
		opener = urllib2.build_opener(SimpleCache.CacheHandler(".AuthorCache"), SimpleCache.ThrottlingProcessor(5))
		resp = opener.open(request)
		authorlist = []
		try:
			sourcexml = ElementTree.parse(resp)
		except Exception, e:
			logger.error("Error fetching authorid: " + str(e) + str(URL))
			return authorlist

		rootxml = sourcexml.getroot()
		resultxml = rootxml.getiterator('author')
	
		if not len(resultxml):
			logger.info('No authors found with name: %s' % self.name)
		else:
			# In spite of how this looks, goodreads only returns one result, even if there are multiple matches
			# we just have to hope we get the right one. eg search for "James Lovelock" returns "James E. Lovelock"
			# who only has one book listed under googlebooks, the rest are under "James Lovelock"
			# goodreads has all his books under "James E. Lovelock". Can't come up with a good solution yet. 
			# For now we'll have to let the user handle this by selecting/adding the author manually 
			for author in resultxml:
				authorid = author.attrib.get("id")
				authorname = author[0].text
				authorlist = self.get_author_info(authorid, authorname)

		return authorlist

	def get_author_info(self, authorid=None, authorname=None, refresh=False):

		URL = 'http://www.goodreads.com/author/show/' + authorid + '.xml?' + urllib.urlencode(self.params)

		# Cache our request
		request = urllib2.Request(URL)
		if lazylibrarian.PROXY_HOST:
			request.set_proxy(lazylibrarian.PROXY_HOST, lazylibrarian.PROXY_TYPE)
		request.add_header('User-Agent', USER_AGENT)
		opener = urllib2.build_opener(SimpleCache.CacheHandler(".AuthorCache"), SimpleCache.ThrottlingProcessor(5))
		resp = opener.open(request)

		try:
			sourcexml = ElementTree.parse(resp)
			rootxml = sourcexml.getroot()
			resultxml = rootxml.find('author')
			author_dict = {}
		except Exception, e:
			logger.error("Error fetching author ID: " + str(e))

		if not len(resultxml):
			logger.info('No author found with ID: ' + authorid)

		else:
			logger.info("[%s] Processing info for authorID: %s" % (authorname, authorid))

			# PAB added authorname to author_dict - this holds the intact name preferred by GR
			author_dict = {
				'authorid':   resultxml[0].text,
				'authorlink':   resultxml.find('link').text,
				'authorimg':  resultxml.find('image_url').text,
				'authorborn':   resultxml.find('born_at').text,
				'authordeath':  resultxml.find('died_at').text,
				'totalbooks':   resultxml.find('works_count').text,
				'authorname':   authorname
				}
		return author_dict

	def get_author_books(self, authorid=None, authorname=None, refresh=False):
		
		api_hits = 0
		gr_lang_hits = 0
		lt_lang_hits = 0
		gb_lang_change = 0
		cache_hits = 0
		not_cached = 0
		URL = 'http://www.goodreads.com/author/list/' + authorid + '.xml?' + urllib.urlencode(self.params)

		#Artist is loading
		myDB = database.DBConnection()
		controlValueDict = {"AuthorID": authorid}
		newValueDict = {"Status": "Loading"}
		myDB.upsert("authors", newValueDict, controlValueDict)
		
		try:
			# Cache our request
			request = urllib2.Request(URL)
			if lazylibrarian.PROXY_HOST:
				request.set_proxy(lazylibrarian.PROXY_HOST, lazylibrarian.PROXY_TYPE)
			request.add_header('User-Agent', USER_AGENT)
			opener = urllib2.build_opener(SimpleCache.CacheHandler(".AuthorCache"), SimpleCache.ThrottlingProcessor(5))
			resp = opener.open(request)
			api_hits = api_hits + 1
			sourcexml = ElementTree.parse(resp)
		except Exception, e:
			logger.error("Error fetching author info: " + str(e))

		rootxml = sourcexml.getroot()
		resultxml = rootxml.getiterator('book')
		books_dict = []
		valid_langs = ([valid_lang.strip() for valid_lang in lazylibrarian.IMP_PREFLANG.split(',')])
					
		if not len(resultxml):
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

					
# PAB this next section tries to get the book language using the isbn13 to look it up. If no isbn13 we skip the book entirely, rather than 
# including it with an "Unknown" language. Changed this so we can still include the book with language set to "Unknown"
# There is a setting in config.ini to allow or skip books with "Unknown" language if you really don't want to include them.
# Not all GR books have isbn13 filled in, but all have a GR bookid, which we've already got, so use that.
# Also, with GR API rules we can only call the API once per second, which slows us down a lot when all we want is to get the language.
# We sleep for one second per book that GR knows about for each author you have in your library.
# The libraryThing API has the same 1 second restriction, and is limited to 1000 hits per day, but has fewer books with unknown language
# To get around this and speed up the process, see if we already have a book in the database with a similar start to the ISBN.
# The way ISBNs work, digits 3-5 of a 13 char ISBN or digits 0-2 of a 10 digit ISBN indicate the region/language 
# so if two books have the same 3 digit isbn code, they _should_ be the same language.
# I ran a simple python script on my library of 1500 books, and these codes were 100% correct on matching book languages, no mis-matches.
# It did result in a small number of books with "unknown" language being wrongly matched, but most "unknown" were matched to the correct language. 
# We could look up ISBNs we already know about in the database, but this only holds books in the languages we want to keep, which reduces the number of
# cache hits, so we create a new database table, holding ALL results including the ISBNs for languages we don't want and books we reject.
# The new table is created (if not exists) in init.py so by the time we get here there is an existing table. 
# 
# If we haven't an already matching partial ISBN, look up language code from libraryThing  "http://www.librarything.com/api/thingLang.php?isbn=1234567890"
# If you find a matching language, add it to the database.  If "unknown" or "invalid", try GR as maybe GR can provide a match.
# If both LT and GR return unknown, add isbn to db as "unknown". No point in repeatedly asking LT for a code it's told you it doesn't know.
#
# As an extra option, if language includes "All" in config.ini, we can skip this whole section and process everything much faster by not querying for language at all.
# It does mean we include a lot of unwanted foreign translations in the database, but it's _much_ faster.
#
					bookLanguage = "Unknown"
					find_field="id"
					isbn=""
					isbnhead=""
					if "All" not in valid_langs: # do we care about language
						if (book.find('isbn').text is not None):
							find_field="isbn"
							isbn=book.find('isbn').text
							isbnhead=isbn[0:3]
					    	else:
							if (book.find('isbn13').text is not None):
						    		find_field="isbn13"
						    		isbn=book.find('isbn13').text
						    		isbnhead=isbn[3:6]
					    	if (find_field != 'id'): # isbn or isbn13 found
							
							match = myDB.action('SELECT lang FROM languages where isbn = "%s"' % (isbnhead)).fetchone()
					        	if (match):
						    		bookLanguage=match['lang']
								cache_hits = cache_hits + 1
				    				logger.debug("Found cached language [%s] for %s [%s]" % (bookLanguage, find_field, isbnhead))
							else:
								# no match in cache, try searching librarything for a language code using the isbn
								# if no language found, librarything return value is "invalid" or "unknown"
								# returns plain text, not xml
 								BOOK_URL = 'http://www.librarything.com/api/thingLang.php?isbn=' + isbn
 								try:
									time.sleep(1) #sleep 1 second to respect librarything api terms
									resp = urllib2.urlopen(BOOK_URL, timeout=30).read()
                        						lt_lang_hits = lt_lang_hits + 1
									logger.debug("LibraryThing reports language [%s] for %s" % (resp, isbnhead))
									
									if (resp == 'invalid' or resp == 'unknown'):
										find_field="id" # reset the field to force search on goodreads	
									else:
										bookLanguage=resp # found a language code
										myDB.action('insert into languages values ("%s", "%s")' % (isbnhead, bookLanguage))
										logger.debug(u"LT language: " + str(bookLanguage))
								except Exception, e:
									find_field="id" # reset the field to search on goodreads
					    				logger.error("Error finding results: ", e)
							
						if (find_field == 'id'): # [or bookLanguage == "Unknown"] no earlier match, we'll have to search the goodreads api
					    		try:
						   		if (book.find(find_field).text is not None):
									BOOK_URL = 'http://www.goodreads.com/book/show?id=' + book.find(find_field).text + '&' + urllib.urlencode(self.params) 
									logger.debug(u"Book URL: " + str(BOOK_URL))
							
									try:
										# Cache our request
										if (isbnhead == ""): # no isbn found, so we didn't try librarything
											time.sleep(1) # only sleep for GR API if we didn't sleep for librarything
										request = urllib2.Request(BOOK_URL)
										if lazylibrarian.PROXY_HOST:
											request.set_proxy(lazylibrarian.PROXY_HOST, lazylibrarian.PROXY_TYPE)
										request.add_header('User-Agent', USER_AGENT)
										opener = urllib2.build_opener(SimpleCache.CacheHandler(".AuthorCache"), SimpleCache.ThrottlingProcessor(5))
										resp = opener.open(request)
										gr_lang_hits = gr_lang_hits + 1
									except Exception, e:
										logger.error("Error finding results: ", e)

									BOOK_sourcexml = ElementTree.parse(resp)
									BOOK_rootxml = BOOK_sourcexml.getroot()

									bookLanguage = BOOK_rootxml.find('./book/language_code').text
									if not bookLanguage:
										bookLanguage = "Unknown"
									
									if (isbnhead != ""): # GR didn't give an isbn so we can't cache it, just use for this book
										myDB.action('insert into languages values ("%s", "%s")' % (isbnhead, bookLanguage))
										logger.debug("GoodReads reports language [%s] for %s" % (bookLanguage, isbnhead))
									else:
										not_cached = not_cached + 1

									logger.debug(u"GR language: " + str(bookLanguage))
						   		else:
									logger.debug("No %s provided for [%s]" % (find_field, book.find('title').text))
									#continue

					  		except Exception, e:
								logger.debug(u"An error has occured: " + str(e))
			
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

                                        result = re.search(r"\(([\S\s]+)\, #(\d+)|\(([\S\s]+) #(\d+)", bookname)
                                        if result:
                                                if result.group(1) == None:
                                                        series = result.group(3)
                                                        seriesOrder = result.group(4)
                                                else:
                                                        series = result.group(1)
                                                        seriesOrder = result.group(2)
                                        else:
                                                series = None
                                                seriesOrder = None
                            
					find_book_status = myDB.select("SELECT * FROM books WHERE BookID = '%s'" % bookid)
					if find_book_status:
						for resulted in find_book_status:
							book_status = resulted['Status']
					else:
						book_status = lazylibrarian.NEWBOOK_STATUS

    					bookname = bookname.replace(':','')
					bookname = unidecode(u'%s' % bookname)
					bookname = bookname.strip() # strip whitespace
					
					if not (re.match('[^\w-]', bookname)): #remove books with bad characters in title
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
								"BookAdded":    formatter.today(),
                                                                "Series":       series,
                                                                "SeriesOrder":  seriesOrder
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
						logger.debug(u"removed result [" + bookname + "] for bad characters")
						removedResults = removedResults + 1

				loopCount = loopCount + 1
				URL = 'http://www.goodreads.com/author/list/' + authorid + '.xml?' + urllib.urlencode(self.params) + '&page=' + str(loopCount)

				try:
					# Cache our request
					request1 = urllib2.Request(URL)
					if lazylibrarian.PROXY_HOST:
						request1.set_proxy(lazylibrarian.PROXY_HOST, lazylibrarian.PROXY_TYPE)
					request1.add_header('User-Agent', USER_AGENT)
					opener1 = urllib2.build_opener(SimpleCache.CacheHandler(".AuthorCache"), SimpleCache.ThrottlingProcessor(5))
					resp1 = opener1.open(request1)
					api_hits = api_hits + 1
				except Exception, e:
					logger.error("Error finding results: " + str(e))				

				sourcexml = ElementTree.parse(resp1)
				rootxml = sourcexml.getroot()
				resultxml = rootxml.getiterator('book')


		lastbook = myDB.action("SELECT BookName, BookLink, BookDate from books WHERE AuthorID='%s' AND Status != 'Ignored' order by BookDate DESC" % authorid).fetchone()
		if lastbook:
                        lastbookname = lastbook['BookName']
                        lastbooklink = lastbook['BookLink']
                        lastbookdate = lastbook['BookDate']
                else:
                        lastbookname = None
                        lastbooklink = None
                        lastbookdate = None
                        
		unignoredbooks = myDB.select("SELECT COUNT(BookName) as unignored FROM books WHERE AuthorID='%s' AND Status != 'Ignored'" % authorid)
		bookCount = myDB.select("SELECT COUNT(BookName) as counter FROM books WHERE AuthorID='%s'" % authorid)   
		
		controlValueDict = {"AuthorID": authorid}
		newValueDict = {
				"Status": "Active",
				"TotalBooks": bookCount[0]['counter'],
				"UnignoredBooks": unignoredbooks[0]['unignored'],
				"LastBook": lastbookname,
				"LastLink": lastbooklink,
				"LastDate": lastbookdate
				}
		myDB.upsert("authors", newValueDict, controlValueDict)

		#This is here because GoodReads sometimes has several entries with the same BookID!
		modified_count = added_count + updated_count
					
		logger.debug("Found %s total books for author" % total_count)
		logger.debug("Removed %s bad language results for author" % ignored)
		logger.debug("Removed %s bad character results for author" % removedResults)
		logger.debug("Ignored %s books by author marked as Ignored" % book_ignore_count)
		logger.debug("Imported/Updated %s books for author" % modified_count)
		
		myDB.action('insert into stats values ("%s", %i, %i, %i, %i, %i, %i, %i, %i)' % (authorname, api_hits, gr_lang_hits, lt_lang_hits, gb_lang_change, cache_hits, ignored, removedResults, not_cached))

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
			if lazylibrarian.PROXY_HOST:
				request.set_proxy(lazylibrarian.PROXY_HOST, lazylibrarian.PROXY_TYPE)
			request.add_header('User-Agent', USER_AGENT)
			opener = urllib2.build_opener(SimpleCache.CacheHandler(".AuthorCache"), SimpleCache.ThrottlingProcessor(5))
			resp = opener.open(request)
			sourcexml = ElementTree.parse(resp)
		except Exception, e:
			logger.error("Error fetching book info: " + str(e))

		rootxml = sourcexml.getroot()

		bookLanguage = rootxml.find('./book/language_code').text
		bookname = rootxml.find('./book/title').text
		
		if not bookLanguage:
			bookLanguage = "Unknown"
#
## PAB user has said they want this book, don't block for bad language, just warn
#
		valid_langs = ([valid_lang.strip() for valid_lang in lazylibrarian.IMP_PREFLANG.split(',')])
		if bookLanguage not in valid_langs:
			logger.info('Book %s language does not match preference' % bookname)

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
