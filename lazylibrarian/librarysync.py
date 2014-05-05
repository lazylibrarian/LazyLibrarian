import os
import glob
import re
import lazylibrarian
import shlex
from lazylibrarian import logger, database, importer
from lazylibrarian.gr import GoodReads

def getList(st):
        my_splitter = shlex.shlex(st, posix=True)
        my_splitter.whitespace += ','
        my_splitter.whitespace_split = True
	return list(my_splitter)


#assuming your directory structor is basedir/Author
def LibraryScan(dir=None):
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
	book_exists = False
	books = myDB.select('select AuthorName, BookName from books where Status=?',[u'Open'])

	for book in books:
		for book_type in getList(lazylibrarian.EBOOK_TYPE):
			#assuming download_dir/author/book/author - book.ebook_type
			#please update this to read config values
			bookName = book['BookName']
			bookAuthor = book['AuthorName']
			encoded_book_path = os.path.join(dir,bookAuthor,bookName,bookAuthor+" - "+bookName + "." + book_type).encode(lazylibrarian.SYS_ENCODING)
			if os.path.isfile(encoded_book_path):
				book_exists = True	
		if not book_exists:
			#should this be set to wanted?
			myDB.action('update books set Status=? where AuthorName=? and BookName=?',['Skipped',bookAuthor,bookName])
			logger.info('Book %s marked as skipped as not found on disk' % encoded_book_path.decode(lazylibrarian.SYS_ENCODING, 'replace'))
			new_authors.append(bookAuthor)

	latest_subdirectory = []
	for r,d,f in os.walk(dir):
		for directory in d[:]:
			if directory.startswith("."):
				d.remove(directory)
			#prevent magazine being scanned
			if directory.startswith("_"):
				d.remove(directory)
		for files in f:
			 subdirectory = r.replace(dir,'')
			 latest_subdirectory.append(subdirectory)
			 logger.info("[%s] Now scanning subdirectory %s" % (dir.decode(lazylibrarian.SYS_ENCODING, 'replace'), subdirectory.decode(lazylibrarian.SYS_ENCODING, 'replace')))
			 #assumed file name pattern, should be updated from the configuration string?
			 pattern = re.compile(r'(?P<author>.*?)\s\-\s(?P<book>.*?)\.(?P<format>.*?)', re.VERBOSE)
			 match = pattern.match(files)
			 if match:
				author = match.group("author")
				book = match.group("book")
			 	#check if book is in database, and not marked as in library
				check_exist_book = myDB.action("SELECT * FROM books where AuthorName=? and BookName=? and Status!=?",[author,book,'Open']).fetchone()
				if not check_exist_book:
					check_exist_author = myDB.action("SELECT * FROM authors where AuthorName=?",[author]).fetchone()
					if not check_exist_author:
						GR = GoodReads(author)
						author_gr = GR.find_author_id()
						#only try to add if GR data matches found author data
						if author_gr:
							authorid = author_gr['authorid']
							authorlink  = author_gr['authorlink'][(author['authorlink'].rfind('/'))+1:]
							if authorid+"."+author == authorlink:
								logger.info("Adding %s" % author)
								importer.addAuthorToDB(author)
								check_exist_book = myDB.action("SELECT * FROM books where AuthorName=? and BookName=?",[author,book]).fetchone()
								if check_exist_book:
									new_authors.append(author)
									myDB.action('UPDATE books set Status=? where AuthorName=? and BookName=?',['Open',author,book])
									new_book_count += 1
							else:
								logger.info("Unable to match %s in GoodReads database" % author)
							

				else:
					new_authors.append(author)
					myDB.action('UPDATE books set Status=? where AuthorName=? and BookName=?',['Open',author,book])
					new_book_count += 1
				
				file_count += 1
	
	logger.info("%s new/modified books found and added to the database" % new_book_count)
	logger.info('Found %i new authors' % len(new_authors))
	for auth in new_authors:
		havebooks = len(myDB.select('select BookName from Books where status=? and AuthorName=?',['Open',auth]))
		myDB.action('UPDATE authors set HaveBooks=? where AuthorName=?',[havebooks,auth])

	logger.info('Library scan complete')
