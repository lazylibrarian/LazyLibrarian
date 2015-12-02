import shutil
import os
#import datetime
#import urllib
#import urllib2
import threading

from urllib import FancyURLopener

import lazylibrarian

from lazylibrarian import database, logger, formatter, notifiers, common

def processDir():
    # rename this thread
    threading.currentThread().name = "POSTPROCESS"

    processpath = lazylibrarian.DOWNLOAD_DIR

    logger.debug(' Checking [%s] for files to post process' % processpath)

    # TODO - try exception on os.listdir - it throws debug level
    # exception if dir doesn't exist - bloody hard to catch
    try:
        downloads = os.listdir(processpath)
    except OSError:
        logger.error('Could not access [%s] directory ' % processpath)
        return False
        
    myDB = database.DBConnection()
    snatched = myDB.select('SELECT * from wanted WHERE Status="Snatched"')

    if snatched is None:
        logger.info('No books are snatched. Nothing to process.')
    elif downloads is None:
        logger.info('No downloads are found. Nothing to process.')
    else:
        ppcount = 0
        for book in snatched:
            if book['NZBtitle'] in downloads:
                pp_path = os.path.join(processpath, book['NZBtitle'])
                logger.info('Found book/mag folder %s.' % pp_path)

                data = myDB.select('SELECT * from books WHERE BookID="%s"' % book['BookID'])
                if data:
                    authorname = data[0]['AuthorName']
                    bookname = data[0]['BookName']
                    
                    # Default destination path, should be allowed change per config file.
                    dest_path = lazylibrarian.EBOOK_DEST_FOLDER.replace('$Author', authorname).replace('$Title', bookname)
                    global_name = lazylibrarian.EBOOK_DEST_FILE.replace('$Author', authorname).replace('$Title', bookname)
                    # dest_path = authorname+'/'+bookname
                    # global_name = bookname + ' - ' + authorname
                    dest_path = os.path.join(lazylibrarian.DESTINATION_DIR, dest_path).encode(lazylibrarian.SYS_ENCODING)
                else:
                    data = myDB.select('SELECT * from magazines WHERE Title="%s"' % book['BookID'])
                    if data:
                        # AuxInfo was added for magazine release date, normally housed in 'magazines' but if multiple
                        # files are downloading, there will be an error in post-processing, trying to go to the
                        # same directory.
                        mostrecentissue = data[0]['IssueDate'] # keep this for processing issues arriving out of order
                        dest_path = lazylibrarian.MAG_DEST_FOLDER.replace('$IssueDate', book['AuxInfo']).replace('$Title', book['BookID'])
                        # dest_path = '_Magazines/'+title+'/'+book['AuxInfo']
                        if lazylibrarian.MAG_RELATIVE:
                            if dest_path[0] not in '._':
                                dest_path = '_' + dest_path
                            dest_path = os.path.join(lazylibrarian.DESTINATION_DIR, dest_path).encode(lazylibrarian.SYS_ENCODING)
                        else:
                            dest_path = dest_path.encode(lazylibrarian.SYS_ENCODING)
                        authorname = None
                        bookname = None
                        global_name = lazylibrarian.MAG_DEST_FILE.replace('$IssueDate', book['AuxInfo']).replace('$Title', book['BookID'])
                        # global_name = book['AuxInfo']+' - '+title
                    else:
                        logger.info("Snatched magazine %s is not in download directory" % (book['BookID']))
                        continue                    
            else:
                logger.info("Snatched NZB %s is not in download directory" % (book['NZBtitle']))
                continue

            dic = {'<': '', '>': '', '...': '', ' & ': ' ', ' = ': ' ', '?': '', '$': 's', ' + ': ' ', '"': '', ',': '', '*': '', ':': '', ';': '', '\'': ''}
            dest_path = formatter.latinToAscii(formatter.replace_all(dest_path, dic))
            try:
                os.chmod(dest_path, 0777)
            except Exception, e:
                logger.debug("Could not chmod post-process directory: " + str(dest_path))

            processBook = processDestination(pp_path, dest_path, authorname, bookname, global_name, book['BookID'])

            if processBook:

                ppcount = ppcount + 1

                # update nzbs
                controlValueDict = {"NZBurl": book['NZBurl']}
                newValueDict = {"Status": "Processed", "NZBDate": formatter.today()} # say when we processed it
                myDB.upsert("wanted", newValueDict, controlValueDict)
                    
                if bookname is not None: # it's a book, if None it's a magazine
                    processExtras(myDB, dest_path, global_name, data)
                else: 
                    # update mags
                    controlValueDict = {"Title": book['BookID']}
                    if mostrecentissue > book['AuxInfo']: # check this in case processing issues arriving out of order
                        newValueDict = {"LastAcquired": formatter.today(), "IssueStatus": "Open"}
                    else:    
                        newValueDict = {"IssueDate": book['AuxInfo'], "LastAcquired": formatter.today(), "IssueStatus": "Open"}
                    myDB.upsert("magazines", newValueDict, controlValueDict)
                    # dest_path is where we put the magazine after processing, but we don't have the full filename
                    # so look for any "book" in that directory
                    dest_file = book_file(dest_path)
                    controlValueDict = {"Title": book['BookID'], "IssueDate": book['AuxInfo']}
                    newValueDict = {"IssueAcquired": formatter.today(), "IssueFile": dest_file}
                    myDB.upsert("issues", newValueDict, controlValueDict)
                                    
                logger.info('Successfully processed: %s' % global_name)
                notifiers.notify_download(formatter.latinToAscii(global_name) + ' at ' + formatter.now())
            else:
                logger.error('Postprocessing for %s has failed.' % global_name)
                logger.error('Warning - Residual files remain in %s' % pp_path)
        #
        # TODO Seems to be duplication here. Can we just scan once for snatched books 
        # instead of scan for snatched and then scan for directories with "LL.(bookID)" in?
        # Should there be any directories with "LL.(bookID)" that aren't in snatched?
        # Maybe this was put in for manually downloaded books?
        #  
        downloads = os.listdir(processpath) # check in case we processed/deleted some above      
        for directory in downloads:
            if "LL.(" in directory:
                bookID = str(directory).split("LL.(")[1].split(")")[0]
                logger.debug("Book with id: " + str(bookID) + " is in downloads")
                pp_path = os.path.join(processpath, directory)

                if os.path.isfile(pp_path): # ?? what is this supposed to do
                    pp_path = os.path.join(processpath) # this is missing a parameter, join what?

                if (os.path.isdir(pp_path)):
                    logger.debug('Found LL folder %s.' % pp_path)

                    data = myDB.select('SELECT * from books WHERE BookID="%s"' % bookID)
                    if data:
                        authorname = data[0]['AuthorName']
                        bookname = data[0]['BookName']
                        
                        try:
                            auth_dir = os.path.join(lazylibrarian.DESTINATION_DIR, authorname).encode(lazylibrarian.SYS_ENCODING)
                            os.chmod(auth_dir, 0777)
                        except Exception, e:
                            logger.debug("Could not chmod author directory: " + str(auth_dir))
                        dest_path = lazylibrarian.EBOOK_DEST_FOLDER.replace('$Author', authorname).replace('$Title', bookname)
                        global_name = lazylibrarian.EBOOK_DEST_FILE.replace('$Author', authorname).replace('$Title', bookname)
                        dic = {'<': '', '>': '', '...': '', ' & ': ' ', ' = ': ' ', '?': '', '$': 's', ' + ': ' ', '"': '', ',': '', '*': '', ':': '', ';': '', '\'': ''}
                        dest_path = formatter.latinToAscii(formatter.replace_all(dest_path, dic))
                        dest_path = os.path.join(lazylibrarian.DESTINATION_DIR, dest_path).encode(lazylibrarian.SYS_ENCODING)

                        processBook = processDestination(pp_path, dest_path, authorname, bookname, global_name, bookID)

                        if processBook:
                            # update nzbs
                            controlValueDict = {"BookID": bookID}
                            newValueDict = {"Status": "Processed", "NZBDate": formatter.today()} # say when we processed it
                            myDB.upsert("wanted", newValueDict, controlValueDict)
                            ppcount = ppcount + 1
                            processExtras(myDB, dest_path, global_name, data)
                        else:
                            logger.error('Postprocessing for %s has failed.' % global_name)
                            logger.error('Warning - Residual files remain in %s' % pp_path)
        if ppcount:
            logger.info('%s books/mags are downloaded and processed.' % ppcount)
        else:
            logger.info('No snatched books/mags have been found')

def book_file(search_dir=None):
    # find a book file in this directory, any book will do
    # return full pathname of book, or empty string if no book found
    booktype_list = formatter.getlist(lazylibrarian.EBOOK_TYPE)
    if search_dir and os.path.isdir(search_dir):
        for fname in os.listdir(search_dir):
            if '.' in fname:
                words = fname.split('.')
                extn = words[len(words) - 1]
                if extn in booktype_list:
                    return os.path.join(search_dir, fname)
    return ""                           

def processExtras(myDB=None, dest_path=None, global_name=None, data=None):
    # given book data, handle calibre autoadd, book image, opf,
    # and update author and book counts
    authorname = data[0]['AuthorName']
    bookid = data[0]['BookID']
    bookname = data[0]['BookName']
    bookdesc = data[0]['BookDesc']
    bookisbn = data[0]['BookIsbn']
    bookimg = data[0]['BookImg']
    bookdate = data[0]['BookDate']
    booklang = data[0]['BookLang']
    bookpub = data[0]['BookPub']

    # If you use auto add by Calibre you need the book in a single directory, not nested
    # So take the file you Copied/Moved to Dest_path and copy it to a Calibre auto add folder.
    if lazylibrarian.IMP_AUTOADD:
        processAutoAdd(dest_path)
                
    # try image
    processIMG(dest_path, bookimg, global_name)

    # try metadata
    processOPF(dest_path, authorname, bookname, bookisbn, bookid, bookpub, bookdate, bookdesc, booklang, global_name)

    # update books
    # dest_path is where we put the book after processing, but we don't have the full filename
    # we don't keep the extension, so look for any "book" in that directory
    dest_file = book_file(dest_path)
    controlValueDict = {"BookID": bookid}
    newValueDict = {"Status": "Open", "BookFile": dest_file}
    myDB.upsert("books", newValueDict, controlValueDict)

    # update authors
    query = 'SELECT COUNT(*) FROM books WHERE AuthorName="%s" AND (Status="Have" OR Status="Open")' % authorname
    countbooks = myDB.action(query).fetchone()
    havebooks = int(countbooks[0])
    controlValueDict = {"AuthorName": authorname}
    newValueDict = {"HaveBooks": havebooks}
    author_query = 'SELECT * FROM authors WHERE AuthorName="%s"' % authorname
    countauthor = myDB.action(author_query).fetchone()
    if countauthor:
        myDB.upsert("authors", newValueDict, controlValueDict)
    
def processDestination(pp_path=None, dest_path=None, authorname=None, bookname=None, global_name=None, book_id=None):

    logger.debug("dest_path = %s %s" % (type(dest_path), common.to_str(dest_path)))
    logger.debug("pp_path = %s %s" % (type(pp_path), common.to_str(pp_path)))
    pp_path = pp_path.encode(lazylibrarian.SYS_ENCODING)

    # check we got a book in the downloaded files
    pp = False
    booktype_list = formatter.getlist(lazylibrarian.EBOOK_TYPE)
    for bookfile in os.listdir(pp_path):
        if ((str(bookfile).split('.')[-1]) in booktype_list):    
            pp = True
    if pp == False:
        # no book found in a format we wanted. Leave for the user to delete or convert manually
        logger.debug('Failed to locate a book in downloaded files, leaving for manual processing')
        return pp    
        
    try:
        if not os.path.exists(dest_path):
            logger.debug('%s does not exist, so it\'s safe to create it' % dest_path)
        else:
            logger.debug('%s already exists. Removing existing tree.' % dest_path)
            shutil.rmtree(dest_path)

        logger.debug('Attempting to copy/move tree')
        if lazylibrarian.DESTINATION_COPY == 1 and lazylibrarian.DOWNLOAD_DIR != pp_path:
            shutil.copytree(pp_path, dest_path)
            logger.debug('Successfully copied %s to %s.' % (pp_path, dest_path))
        elif lazylibrarian.DOWNLOAD_DIR == pp_path:
            booktype_list = formatter.getlist(lazylibrarian.EBOOK_TYPE)
            for file3 in os.listdir(pp_path):
                if ((str(file3).split('.')[-1]) in booktype_list):
                    bookID = str(file3).split("LL.(")[1].split(")")[0]
                    if bookID == book_id:
                        logger.info('Processing %s' % bookID)
                        if not os.path.exists(dest_path):
                            try:
                                os.makedirs(dest_path)
                            except Exception, e:
                                logger.debug(str(e))
                        if lazylibrarian.DESTINATION_COPY == 1:
                            shutil.copyfile(os.path.join(pp_path, file3), os.path.join(dest_path, file3))
                        else:
                            shutil.move(os.path.join(pp_path, file3), os.path.join(dest_path, file3))
        else:
            shutil.move(pp_path, dest_path)
            logger.debug('Successfully moved %s to %s.' % (pp_path, dest_path))

        pp = True

        # try and rename the actual book file & remove non-book files
        booktype_list = formatter.getlist(lazylibrarian.EBOOK_TYPE)
        for file2 in os.listdir(dest_path):
            #logger.debug('file extension: ' + str(file2).split('.')[-1])
            if ((file2.lower().find(".jpg") <= 0) & (file2.lower().find(".opf") <= 0)):
                if ((str(file2).split('.')[-1]) not in booktype_list):
                    logger.debug('Removing unwanted file: %s' % str(file2))
                    os.remove(os.path.join(dest_path, file2))
                else:
                    logger.debug('Moving %s to directory %s' % (file2, dest_path))
                    os.rename(os.path.join(dest_path, file2), os.path.join(dest_path, global_name + '.' + str(file2).split('.')[-1]))
        try:
            os.chmod(dest_path, 0777)
        except Exception, e:
            logger.debug("Could not chmod path: " + str(dest_path))
    except OSError, e:
        logger.info('Could not create destination folder or rename the downloaded ebook. Check permissions of: ' + lazylibrarian.DESTINATION_DIR)
        logger.info(str(e))
        pp = False
    return pp


def processAutoAdd(src_path=None):
    # Called to copy the book files to an auto add directory for the likes of Calibre which can't do nested dirs
    autoadddir = lazylibrarian.IMP_AUTOADD
    logger.debug('AutoAdd - Attempt to copy from [%s] to [%s]' % (src_path, autoadddir))

    if not os.path.exists(autoadddir):
        logger.info('AutoAdd directory [%s] is missing or not set - cannot perform autoadd copy' % autoadddir)
        return False
    else:
        # Now try and copy all the book files into a single dir.

        try:
            names = os.listdir(src_path)
            # TODO : n files jpg, opf & book(s) should have same name
            # Caution - book may be pdf, mobi, epub or all 3.
            # for now simply copy all files, and let the autoadder sort it out

            # os.makedirs(autoadddir)
            #errors = []
            for name in names:
                srcname = os.path.join(src_path, name)
                dstname = os.path.join(autoadddir, name)
                logger.debug('AutoAdd Copying named file [%s] as copy [%s] to [%s]' % (name, srcname, dstname))
                try:
                    shutil.copy2(srcname, dstname)
                except (IOError, os.error) as why:
                    logger.error('AutoAdd - Failed to copy file because [%s] ' % str(why))

        except OSError as why:
            logger.error('AutoAdd - Failed because [%s]' % str(why))
            return False

    logger.info('Auto Add completed for [%s]' % dstname)
    return True


def processIMG(dest_path=None, bookimg=None, global_name=None):
    # handle pictures
    try:
        if not bookimg == ('images/nocover.png'):
            logger.debug('Downloading cover from ' + bookimg)
            coverpath = os.path.join(dest_path, global_name + '.jpg')
            img = open(coverpath, 'wb')
            imggoogle = imgGoogle()
            img.write(imggoogle.open(bookimg).read())
            img.close()
            try:
                os.chmod(coverpath, 0777)
            except Exception, e:
                logger.info("Could not chmod path: " + str(coverpath))

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

    dic = {'...': '', ' & ': ' ', ' = ': ' ', '$': 's', ' + ': ' ', ',': '', '*': ''}

    opfinfo = formatter.latinToAscii(formatter.replace_all(opfinfo, dic))

    # handle metadata
    opfpath = os.path.join(dest_path, global_name + '.opf')
    if not os.path.exists(opfpath):
        opf = open(opfpath, 'wb')
        opf.write(opfinfo)
        opf.close()

        try:
            os.chmod(opfpath, 0777)
        except Exception, e:
            logger.info("Could not chmod path: " + str(opfpath))

        logger.debug('Saved metadata to: ' + opfpath)
    else:
        logger.debug('%s allready exists. Did not create one.' % opfpath)


class imgGoogle(FancyURLopener):
    # Hack because Google wants a user agent for downloading images, which is stupid because it's so easy to circumvent.
    version = 'Mozilla/5.0 (X11; U; Linux i686) Gecko/20071127 Firefox/2.0.0.11'
