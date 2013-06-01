import shutil, os, datetime, urllib, urllib2, threading

from urllib import FancyURLopener

import lazylibrarian

from lazylibrarian import database, logger, formatter

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

                dest_path = authorname+'/'+bookname
                dic = {'<':'', '>':'', '=':'', '?':'', '"':'', ',':'', '*':'', ':':'', ';':''}
                dest_path = formatter.latinToAscii(formatter.replace_all(dest_path, dic))
                dest_path = os.path.join(lazylibrarian.DESTINATION_DIR, dest_path).encode(lazylibrarian.SYS_ENCODING)

                processBook = processDestination(pp_path, dest_path, authorname, bookname)

                #TODO - Remove this later - just makes debug easier
                processAutoAdd(dest_path)


                if processBook:

                    ppcount = ppcount+1
                    
                    # If you use auto add by Calibre you need the book in a single directory, not nested
                    #So take the file you Copied/Moved to Dest_path and copy it to a Calibre auto add folder.
                    #processAutoAdd(dest_path)

                    # try image
                    processIMG(dest_path, bookimg)

                    # try metadata
                    processOPF(dest_path, authorname, bookname, bookisbn, book['BookID'], bookpub, bookdate, bookdesc, booklang)

                    #update nzbs
                    controlValueDict = {"NZBurl": book['NZBurl']}
                    newValueDict = {"Status": "Success"}
                    myDB.upsert("wanted", newValueDict, controlValueDict)

                    #update books
                    controlValueDict = {"BookID": book['BookID']}
                    newValueDict = {"Status": "Have"}
                    myDB.upsert("books", newValueDict, controlValueDict)

                    #update authors
                    query = 'SELECT COUNT(*) FROM books WHERE AuthorName="%s" AND Status="Have"' % authorname
                    countbooks = myDB.action(query).fetchone()
                    havebooks = int(countbooks[0])
                    controlValueDict = {"AuthorName": authorname}
                    newValueDict = {"HaveBooks": havebooks}
                    myDB.upsert("authors", newValueDict, controlValueDict)

                    logger.info('Successfully processed: %s - %s' % (authorname, bookname))
                else:
                    logger.error('Postprocessing for %s has failed. Warning - AutoAdd will be repeated' % bookname)
        if ppcount:
            logger.info('%s books are downloaded and processed.' % ppcount)
    logger.debug(' - Completed all snatched/downloaded files')

def processDestination(pp_path=None, dest_path=None, authorname=None, bookname=None):

    if not os.path.exists(dest_path):
        logger.info('%s does not exist, so it\'s safe to create it' % dest_path)
        try:
            if lazylibrarian.DESTINATION_COPY:
                shutil.copytree(pp_path, dest_path)
                logger.info('Successfully copied %s to %s.' % (pp_path, dest_path))
            else:
                shutil.move(pp_path, dest_path)
                logger.info('Successfully moved %s to %s.' % (pp_path, dest_path))
            pp = True

        except OSError:
            logger.error('Could not create destinationfolder. Check permissions of: ' + lazylibrarian.DESTINATION_DIR)
            pp = False
    else:
        logger.error('Directory [%s] exists. Playing safe - and not over writing from [%s]' % (dest_path, pp_path))
        pp = False
    return pp

def processAutoAdd(src_path=None):
    #Called to copy the book files to an auto add directory for the likes of Calibre which can't do nested dirs
    autoadddir = lazylibrarian.IMP_AUTOADD
    logger.debug('AutoAdd - Attempt to copy from [%s] to [%s]' % (src_path, autoadddir))
    
    
    if not os.path.exists(autoadddir):
        logger.error('AutoAdd directory [%s] is missing or not set - cannot perform autoadd copy' % autoadddir)
        return False
    else:
        #Now try and copy all the book files into a single dir.
        
        try:
            names = os.listdir(src_path)
            #TODO : 3 files jpg, opf & book should have same name
            #Caution - book may be pdf, mobi, epub or all 3.
            #for now simply copy all files, and let the autoadder sort it out

            #os.makedirs(autoadddir)
            errors = []
            for name in names:
                srcname = os.path.join(src_path, name)
                dstname = os.path.join(autoadddir, name)
                logger.debug('AutoAdd Coping named file [%s] as copy [%s] to [%s]' % (name, srcname, dstname))
                try:
                    shutil.copy2(srcname, dstname)
                except (IOError, os.error) as why:
                    logger.error('AutoAdd - Failed to copy file because [%s] ' % str(why))

                    
        except OSError as why:
            logger.error('AutoAdd - Failed because [%s]'  % str(why))
            return False
        
    logger.info('Auto Add completed for [%s]' % src_path)
    return True
    
def processIMG(dest_path=None, bookimg=None):
    #handle pictures
    try:
        if not bookimg == 'images/nocover.png':
            logger.info('Downloading cover from ' + bookimg)
            coverpath = os.path.join(dest_path, 'cover.jpg')
            img = open(coverpath,'wb')
            imggoogle = imgGoogle()
            img.write(imggoogle.open(bookimg).read())
            img.close()

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
        logger.info('Saved metadata to: ' + opfpath)
    else:
        logger.info('%s allready exists. Did not create one.' % opfpath)

class imgGoogle(FancyURLopener):
    # Hack because Google wants a user agent for downloading images, which is stupid because it's so easy to circumvent.
    version = 'Mozilla/5.0 (X11; U; Linux i686) Gecko/20071127 Firefox/2.0.0.11'

