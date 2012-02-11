import shutil, os, datetime, urllib, urllib2

from urllib import FancyURLopener

import lazylibrarian

from lazylibrarian import database, logger

def processDir():
    processpath = lazylibrarian.DOWNLOAD_DIR
    downloads = os.listdir(processpath)
    myDB = database.DBConnection()
    snatched = myDB.select('SELECT * from wanted WHERE Status="Snatched"')

    if snatched is None:
        logger.debug('No books are snatched. Nothing to process.')
    elif downloads is None:
        logger.debug('No downloads are found. Nothing to process.')
    else:
        for book in snatched:
            if not book['NZBtitle'] in downloads:
                logger.debug('No snatched books are found. Nothing to process')
            else:
                pp_path = os.path.join(processpath, book['NZBtitle'])
                logger.debug('Found folder %s.' % pp_path)

                data = myDB.select("SELECT * from books WHERE BookID='%s'" % book['BookID'])
                for metadata in data:
                    authorname = metadata[1]
                    authorimg = metadata[2]
                    bookname = metadata[3]
                    bookdesc = metadata[4]
                    bookisbn = metadata[5]
                    bookrate = metadata[6]
                    bookimg = metadata[7]
                    bookpage = metadata[8]
                    booklink = metadata[9]
                    bookdate = metadata[11]
                    booklang = metadata[12]

                dest_path = os.path.join(lazylibrarian.DESTINATION_DIR, authorname, bookname)
                processBook = processDestination(pp_path, dest_path, authorname, bookname)

                if processBook:

                    # try image
                    processIMG(dest_path, bookimg)

                    # try metadata
                    processOPF(dest_path, authorname, bookname, bookisbn, book['BookID'], bookdate, bookdesc, booklang)

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
                    logger.debug('Postprocessing for %s has failed.' % bookname)

def processDestination(pp_path=None, dest_path=None, authorname=None, bookname=None):

    if not os.path.exists(dest_path):
        logger.debug('%s does not exist, so it\'s safe to create it' % dest_path)
        try:
            if lazylibrarian.DESTINATION_COPY:
                shutil.copytree(pp_path, dest_path)
                logger.debug('Successfully copied %s to %s.' % (pp_path, dest_path))
            else:
                shutil.move(pp_path, dest_path)
                logger.debug('Successfully moved %s to %s.' % (pp_path, dest_path))
            pp = True

        except OSError:
            logger.error('Could not create destinationfolder. Check permissions of: ' + lazylibrarian.DESTINATION_DIR)
            pp = False
    else:
        pp = False
    return pp

def processIMG(dest_path=None, bookimg=None):
    #handle pictures
    try:
        if not bookimg == 'images/nocover.png':
            logger.debug('Downloading cover from ' + bookimg)
            coverpath = os.path.join(dest_path, 'cover.jpg')
            img = open(coverpath,'wb')
            imggoogle = imgGoogle()
            img.write(imggoogle.open(bookimg).read())
            img.close()

    except (IOError, EOFError), e:
        logger.error('Error fetching cover from url: %s, %s' % (bookimg, e))

def processOPF(dest_path=None, authorname=None, bookname=None, bookisbn=None, bookid=None, bookdate=None, bookdesc=None, booklang=None):
    opfinfo = '<?xml version="1.0"  encoding="UTF-8"?>\n\
<package version="2.0" xmlns="http://www.idpf.org/2007/opf" >\n\
    <metadata xmlns:dc="http://purl.org/dc/elements/1.1/" xmlns:opf="http://www.idpf.org/2007/opf">\n\
        <dc:title>%s</dc:title>\n\
        <creator>%s</creator>\n\
        <dc:identifier scheme="ISBN">%s</dc:identifier>\n\
        <dc:identifier scheme="GoogleBooks">%s</dc:identifier>\n\
        <dc:date>%s</dc:date>\n\
        <dc:description>%s</dc:description>\n\
        <dc:language>%s</dc:language>\n\
        <guide>\n\
            <reference href="cover.jpg" type="cover" title="Cover"/>\n\
        </guide>\n\
    </metadata>\n\
</package>' % (bookname, authorname, bookisbn, bookid, bookdate, bookdesc, booklang)

    #handle metadata
    opfpath = os.path.join(dest_path, 'metadata.opf')
    if not os.path.exists(opfpath):
        opf = open(opfpath, 'wb')
        opf.write(opfinfo)
        opf.close()
        logger.debug('Saved metadata to: ' + opfpath)
    else:
        logger.debug('%s allready exists. Did not create one.' % opfpath)

class imgGoogle(FancyURLopener):
    # Hack because Google wants a user agent for downloading images, which is stupid because it's so easy to circumvent.
    version = 'Mozilla/5.0 (X11; U; Linux i686) Gecko/20071127 Firefox/2.0.0.11'

