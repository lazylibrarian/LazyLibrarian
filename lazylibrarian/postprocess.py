import shutil, os, datetime, urllib, urllib2, threading

from urllib import FancyURLopener

import lazylibrarian

from lazylibrarian import database, logger, formatter, notifiers

def processDir():
	# rename this thread
	threading.currentThread().name = "POSTPROCESS"

	processpath = lazylibrarian.DOWNLOAD_DIR
	
	logger.debug(' Checking [%s] for files to post process' % processpath)
	
	#TODO - try exception on os.listdir - it throws debug level 
	#exception if dir doesn't exist - bloody hard to catch
	try :
		downloads = os.listdir(processpath)
	except OSError:
			logger.error('Could not access [%s] directory ' % processpath)
			
	myDB = database.DBConnection()
	snatched = myDB.select('SELECT * from wanted WHERE Status="Snatched"')

	if snatched is None:
		logger.info('No books are snatched. Nothing to process.')
	elif downloads is None:
		logger.info('No downloads are found. Nothing to process.')
	else:
		ppcount=0
		for book in snatched:
			if book['NZBtitle'] in downloads:
				pp_path = os.path.join(processpath, book['NZBtitle'])
				logger.info('Found folder %s.' % pp_path)

				data = myDB.select("SELECT * from books WHERE BookID='%s'" % book['BookID'])
				if data:
					for metadata in data:
						authorname = metadata['AuthorName']
						authorimg = metadata['AuthorLink']
						bookname = metadata['BookName']
						bookdesc = metadata['BookDesc']
						bookisbn = metadata['BookIsbn']
						bookrate = metadata['BookRate']
						bookimg = metadata['BookImg']
						bookpage = metadata['BookPages']
						booklink = metadata['BookLink']
						bookdate = metadata['BookDate']
						booklang = metadata['BookLang']
						bookpub = metadata['BookPub']

					#Default destination path, should be allowed change per config file.
					dest_path = lazylibrarian.EBOOK_DEST_FOLDER.replace('$Author', authorname).replace('$Title', bookname)
					#dest_path = authorname+'/'+bookname
					global_name = lazylibrarian.EBOOK_DEST_FILE.replace('$Author', authorname).replace('$Title', bookname)
					#global_name = bookname + ' - ' + authorname
				else:
					data = myDB.select("SELECT * from magazines WHERE Title='%s'" % book['BookID'])
					for metadata in data:
						title = metadata['Title']
					#AuxInfo was added for magazine release date, normally housed in 'magazines' but if multiple
					#files are downloading, there will be an error in post-processing, trying to go to the 
					#same directory.
					dest_path = lazylibrarian.MAG_DEST_FOLDER.replace('$IssueDate', book['AuxInfo']).replace('$Title', title)
					#dest_path = '_Magazines/'+title+'/'+book['AuxInfo']
					authorname = None
					bookname = None
					global_name = lazylibrarian.MAG_DEST_FILE.replace('$IssueDate', book['AuxInfo']).replace('$Title', title)
					#global_name = book['AuxInfo']+' - '+title
			else:
				logger.info("Snatched NZB %s is not in download directory" % (book['NZBtitle']))
				continue

			try:
				os.chmod(os.path.join(lazylibrarian.DESTINATION_DIR, dest_path).encode(lazylibrarian.SYS_ENCODING), 0777);
			except Exception, e:
				logger.debug("Could not chmod post-process directory");

			dic = {'<':'', '>':'', '...':'', ' & ':' ', ' = ': ' ', '?':'', '$':'s', ' + ':' ', '"':'', ',':'', '*':'', ':':'', ';':'', '\'':''}
			dest_path = formatter.latinToAscii(formatter.replace_all(dest_path, dic))
			dest_path = os.path.join(lazylibrarian.DESTINATION_DIR, dest_path).encode(lazylibrarian.SYS_ENCODING)

			processBook = processDestination(pp_path, dest_path, authorname, bookname, global_name)

			if processBook:

				ppcount = ppcount+1
				
				# If you use auto add by Calibre you need the book in a single directory, not nested
				#So take the file you Copied/Moved to Dest_path and copy it to a Calibre auto add folder.
				if lazylibrarian.IMP_AUTOADD:
					processAutoAdd(dest_path)

				#update nzbs
				controlValueDict = {"NZBurl": book['NZBurl']}
				newValueDict = {"Status": "Processed"}
				myDB.upsert("wanted", newValueDict, controlValueDict)

				# try image
				if bookname is not None:
					processIMG(dest_path, bookimg, global_name)

					# try metadata
					processOPF(dest_path, authorname, bookname, bookisbn, book['BookID'], bookpub, bookdate, bookdesc, booklang, global_name)

					#update books
					controlValueDict = {"BookID": book['BookID']}
					newValueDict = {"Status": "Open"}
					myDB.upsert("books", newValueDict, controlValueDict)

					#update authors
					query = 'SELECT COUNT(*) FROM books WHERE AuthorName="%s" AND (Status="Have" OR Status="Open")' % authorname
					countbooks = myDB.action(query).fetchone()
					havebooks = int(countbooks[0])
					controlValueDict = {"AuthorName": authorname}
					newValueDict = {"HaveBooks": havebooks}
					author_query = 'SELECT * FROM authors WHERE AuthorName="%s"' % authorname
					countauthor = myDB.action(author_query).fetchone()
					if countauthor:
						myDB.upsert("authors", newValueDict, controlValueDict)

				else:
					#update mags
					controlValueDict = {"Title": book['BookID']}
					newValueDict = {"IssueStatus": "Open"}
					myDB.upsert("magazines", newValueDict, controlValueDict)

				logger.info('Successfully processed: %s' % (global_name))
				notifiers.notify_download(global_name+' at '+formatter.now())
			else:
				logger.error('Postprocessing for %s has failed. Warning - AutoAdd will be repeated' % global_name)
		if ppcount:
			logger.debug('%s books are downloaded and processed.' % ppcount)
		else:
			logger.debug('No snatched books have been found')

def processDestination(pp_path=None, dest_path=None, authorname=None, bookname=None, global_name=None):

	try:
		if not os.path.exists(dest_path):
			logger.debug('%s does not exist, so it\'s safe to create it' % dest_path)
		else:
			logger.debug('%s already exists. It will be overwritten' % dest_path)
			logger.debug('Removing existing tree')
			shutil.rmtree(dest_path)

		logger.debug('Attempting to copy/move tree')
		if lazylibrarian.DESTINATION_COPY == 1:
			shutil.copytree(pp_path, dest_path)
			logger.debug('Successfully copied %s to %s.' % (pp_path, dest_path))
		else:
			shutil.move(pp_path, dest_path)
			logger.debug('Successfully moved %s to %s.' % (pp_path, dest_path))

		pp = True
		
		#try and rename the actual book file & remove non-book files
		for file2 in os.listdir(dest_path):
			logger.debug('file extension: ' + str(file2).split('.')[-1])
			if ((file2.lower().find(".jpg") <= 0) & (file2.lower().find(".opf") <= 0)):
				logger.debug('file: ' + str(file2))
				if ((str(file2).split('.')[-1]) not in lazylibrarian.EBOOK_TYPE):
					os.remove(os.path.join(dest_path, file2))
				else:
					os.rename(os.path.join(dest_path, file2), os.path.join(dest_path, global_name + '.' + str(file2).split('.')[-1]))

		try:
			os.chmod(dest_path, 0777);
		except Exception, e:
			logger.debug("Could not chmod path: " + str(dest_path));
	except OSError:
		logger.info('Could not create destination folder or rename the downloaded ebook. Check permissions of: ' + lazylibrarian.DESTINATION_DIR)
		pp = False
	return pp

def processAutoAdd(src_path=None):
	#Called to copy the book files to an auto add directory for the likes of Calibre which can't do nested dirs
	autoadddir = lazylibrarian.IMP_AUTOADD
	logger.debug('AutoAdd - Attempt to copy from [%s] to [%s]' % (src_path, autoadddir))
	
	
	if not os.path.exists(autoadddir):
		logger.info('AutoAdd directory [%s] is missing or not set - cannot perform autoadd copy' % autoadddir)
		return False
	else:
		#Now try and copy all the book files into a single dir.
		
		try:
			names = os.listdir(src_path)
			#TODO : n files jpg, opf & book(s) should have same name
			#Caution - book may be pdf, mobi, epub or all 3.
			#for now simply copy all files, and let the autoadder sort it out

			#os.makedirs(autoadddir)
			errors = []
			for name in names:
				srcname = os.path.join(src_path, name)
				dstname = os.path.join(autoadddir, name)
				logger.debug('AutoAdd Copying named file [%s] as copy [%s] to [%s]' % (name, srcname, dstname))
				try:
					shutil.copy2(srcname, dstname)
				except (IOError, os.error) as why:
					logger.error('AutoAdd - Failed to copy file because [%s] ' % str(why))

					
		except OSError as why:
			logger.error('AutoAdd - Failed because [%s]'  % str(why))
			return False
		
	logger.info('Auto Add completed for [%s]' % dstname)
	return True
	
def processIMG(dest_path=None, bookimg=None, global_name=None):
	#handle pictures
	try:
		if not bookimg == ('images/nocover.png'):
			logger.debug('Downloading cover from ' + bookimg)
			coverpath = os.path.join(dest_path, global_name+'.jpg')
			img = open(coverpath,'wb')
			imggoogle = imgGoogle()
			img.write(imggoogle.open(bookimg).read())
			img.close()
			try:
				os.chmod(coverpath, 0777);
			except Exception, e:
				logger.info("Could not chmod path: " + str(coverpath));

	except (IOError, EOFError), e:
		logger.error('Error fetching cover from url: %s, %s' % (bookimg, e))

def processOPF(dest_path=None, authorname=None, bookname=None, bookisbn=None, bookid=None, bookpub=None, bookdate=None, bookdesc=None, booklang=None, global_name=None):
	opfinfo = '<?xml version="1.0"  encoding="UTF-8"?>\n\
<package version="2.0" xmlns="http://www.idpf.org/2007/opf" >\n\
	<metadata xmlns:dc="http://purl.org/dc/elements/1.1/" xmlns:opf="http://www.idpf.org/2007/opf">\n\
		<dc:title>%s</dc:title>\n\
		<creator>%s</creator>\n\
		<dc:language>%s</dc:language>\n\
		<dc:identifier scheme="GoogleBooks">%s</dc:identifier>\n' % (bookname, authorname, booklang, bookid)

	if bookisbn:
		opfinfo += '        <dc:identifier scheme="ISBN">%s</dc:identifier>\n' % bookisbn

	if bookpub:
		opfinfo += '        <dc:publisher>%s</dc:publisher>\n' % bookpub

	if bookdate:
		opfinfo += '        <dc:date>%s</dc:date>\n' % bookdate

	if bookdesc:
		opfinfo += '        <dc:description>%s</dc:description>\n' % bookdesc

	opfinfo += '        <guide>\n\
			<reference href="cover.jpg" type="cover" title="Cover"/>\n\
		</guide>\n\
	</metadata>\n\
</package>'

	dic = {'...':'', ' & ':' ', ' = ': ' ', '$':'s', ' + ':' ', ',':'', '*':''}

	opfinfo = formatter.latinToAscii(formatter.replace_all(opfinfo, dic))

	#handle metadata
	opfpath = os.path.join(dest_path, global_name+'.opf')
	if not os.path.exists(opfpath):
		opf = open(opfpath, 'wb')
		opf.write(opfinfo)
		opf.close()

		try:
			os.chmod(opfpath, 0777);
		except Exception, e:
			logger.info("Could not chmod path: " + str(opfpath));

		logger.debug('Saved metadata to: ' + opfpath)
	else:
		logger.debug('%s allready exists. Did not create one.' % opfpath)

class imgGoogle(FancyURLopener):
	# Hack because Google wants a user agent for downloading images, which is stupid because it's so easy to circumvent.
	version = 'Mozilla/5.0 (X11; U; Linux i686) Gecko/20071127 Firefox/2.0.0.11'

