import os
import glob
import re
import lazylibrarian
from lazylibrarian import logger, database, importer
from lazylibrarian.gr import GoodReads
import lib.fuzzywuzzy as fuzzywuzzy
from lib.fuzzywuzzy import fuzz, process


#assuming your directory structor is basedir/Author
def AuthorAdd(dir=None):
	if not dir:
		if not lazylibrarian.DOWNLOAD_DIR:
			return
		else:
			dir = lazylibrarian.DOWNLOAD_DIR

	if not os.path.isdir(dir):
		logger.warn('Cannot find directory: %s. Not scanning' % dir.decode(lazylibrarian.SYS_ENCODING, 'replace'))
		return
	
	myDB = database.DBConnection()
	new_authors = []

	logger.info('Scanning ebook directory: %s' % dir.decode(lazylibrarian.SYS_ENCODING, 'replace'))

	book_list = []
	new_book_count = 0
	file_count = 0 

	latest_subdirectory = []
	for r,d,f in os.walk(dir):
		for directory in d[:]:
			if directory.startswith("."):
				d.remove(directory)
			if directory.startswith("_"):
				d.remove(directory)
		
		for directory in d[:]:
			activeauthors = myDB.select('SELECT AuthorName,AuthorID from authors WHERE Status="Active" or Status="Loading" order by DateAdded ASC')
			found = 0
			for authors in activeauthors:
				if directory == authors[0]:
					found = 1
			if r == dir:
				if found == 0:
					new_authors.append(directory)

	logger.info('Found %i new authors' % len(new_authors))

	for auth in new_authors:
		#make sure you can find before adding
		GR = GoodReads(auth)
		author = GR.find_author_id()
		if author:
			authorid = author['authorid']
			authorname  = author['authorlink'][(author['authorlink'].rfind('/'))+1:]
			logger.info(authorname)

			match_ratio = lazylibrarian.MATCH_RATIO
			author_match = fuzz.token_sort_ratio(authorname, authorid+"."+auth)
			logger.info("Author match %: "+ str(author_match))
			if (author_match > match_ratio):
				importer.addAuthorToDB(auth)

