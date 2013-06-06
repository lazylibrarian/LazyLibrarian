import shutil, os, datetime, urllib, urllib2, threading

from urllib import FancyURLopener

import lazylibrarian

from lazylibrarian import database, logger, formatter

def processDir():
    logger.debug('Postprocessing has begun.')
	
    # rename this thread
    threading.currentThread().name = "POSTPROCESS"

    processpath = lazylibrarian.DOWNLOAD_DIR
    downloads = os.listdir(processpath)
    myDB = database.DBConnection()
    snatched = myDB.select('SELECT * from wanted')

    if snatched is None:
        logger.info('No books are snatched. Nothing to process.')
    elif downloads is None:
        logger.info('No downloads are found. Nothing to process.')
    else:
        ppcount=0

        for directory in downloads:
            if "LL.(" in directory:
                bookID = str(directory).split("LL.(")[1].split(")")[0];
                logger.debug("Book with id: " + str(bookID) + " is in downloads");
                pp_path = os.path.join(processpath, directory)

                if (os.path.exists(pp_path)):
                	logger.debug('Found folder %s.' % pp_path)

                	data = myDB.select("SELECT * from books WHERE BookID='%s'" % bookID)
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

                		try:
                		    os.chmod(os.path.join(lazylibrarian.DESTINATION_DIR, authorname).encode(lazylibrarian.SYS_ENCODING), 0777);
                		except Exception, e:
                		    logger.debug("Could not chmod author directory");

                		dest_path = authorname + os.sep + bookname
                		dic = {'<':'', '>':'', '...':'', ' & ':' ', ' = ': ' ', '?':'', '$':'s', ' + ':' ', '"':'', ',':'', '*':'', ':':'', ';':'', '\'':''}
                		dest_path = formatter.latinToAscii(formatter.replace_all(dest_path, dic))
                		dest_path = os.path.join(lazylibrarian.DESTINATION_DIR, dest_path).encode(lazylibrarian.SYS_ENCODING)

                		processBook = processDestination(pp_path, dest_path, authorname, bookname)

                		if processBook:

                		    ppcount = ppcount+1

                		    # try image
                		    processIMG(dest_path, bookimg)

                		    # try metadata
                		    processOPF(dest_path, authorname, bookname, bookisbn, bookID, bookpub, bookdate, bookdesc, booklang)

                		    #update nzbs
                		    controlValueDict = {"NZBurl": directory}
                		    newValueDict = {"Status": "Success"}
                		    myDB.upsert("wanted", newValueDict, controlValueDict)

                		    #update books
                		    controlValueDict = {"BookID": bookID}
                		    newValueDict = {"Status": "Open"}
                		    myDB.upsert("books", newValueDict, controlValueDict)

                		    #update authors
                		    query = 'SELECT COUNT(*) FROM books WHERE AuthorName="%s" AND (Status="Have" OR Status="Open")' % authorname
                		    countbooks = myDB.action(query).fetchone()
                		    havebooks = int(countbooks[0])
                		    controlValueDict = {"AuthorName": authorname}
                		    newValueDict = {"HaveBooks": havebooks}
                		    myDB.upsert("authors", newValueDict, controlValueDict)

                		    logger.info('Successfully processed: %s - %s' % (authorname, bookname))
                		else:
                		    logger.info('Postprocessing for %s has failed.' % bookname)
        if ppcount:
            logger.debug('%s books are downloaded and processed.' % ppcount)
        else:
            logger.debug('No snatched books have been found')

def processDestination(pp_path=None, dest_path=None, authorname=None, bookname=None):

    try:
        if not os.path.exists(dest_path):
            logger.debug('%s does not exist, so it\'s safe to create it' % dest_path)
        else:
            logger.debug('%s already exsists. It will be overwritten' % dest_path)
            logger.debug('Removing exsisting tree')
            shutil.rmtree(dest_path)

        logger.debug('Attempting to move tree')
        shutil.move(pp_path, dest_path)
        logger.debug('Successfully copied %s to %s.' % (pp_path, dest_path))

        pp = True
        
        #try and rename the actual book file
        for file2 in os.listdir(dest_path):
            logger.debug('file extension: ' + str(file2).split('.')[-1])
            if ((file2.lower().find(".jpg") <= 0) & (file2.lower().find(".opf") <= 0)):
                logger.debug('file: ' + str(file2))
                os.rename(os.path.join(dest_path, file2), os.path.join(dest_path, bookname + '.' + str(file2).split('.')[-1]))
        try:
            os.chmod(dest_path, 0777);
        except Exception, e:
            logger.debug("Could not chmod path: " + str(dest_path));
    except OSError:
        logger.info('Could not create destination folder or rename the downloaded ebook. Check permissions of: ' + lazylibrarian.DESTINATION_DIR)
        pp = False
    return pp

def processIMG(dest_path=None, bookimg=None):
    #handle pictures
    try:
        if not bookimg == ('images/nocover.png'):
            logger.debug('Downloading cover from ' + bookimg)
            coverpath = os.path.join(dest_path, 'cover.jpg')
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

def processOPF(dest_path=None, authorname=None, bookname=None, bookisbn=None, bookid=None, bookpub=None, bookdate=None, bookdesc=None, booklang=None):
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
    opfpath = os.path.join(dest_path, 'metadata.opf')
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

