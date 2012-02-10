import shutil, os, datetime, urllib, urllib2

from urllib import FancyURLopener

import lazylibrarian

from lazylibrarian import database, logger

class imgGoogle(FancyURLopener):
    # Hack because Google wants a user agent for downloading images, which is stupid because it's so easy to circumvent.
    version = 'Mozilla/5.0 (X11; U; Linux i686) Gecko/20071127 Firefox/2.0.0.11'

class PostProcess:

    def __init__(self, processpath=None):
        self.destination = lazylibrarian.DESTINATION_DIR
        self.keep_original = lazylibrarian.DESTINATION_COPY
        if processpath:
            self.processpath = processpath
        else:
            self.processpath = lazylibrarian.DOWNLOAD_DIR
        self.downloads = os.listdir(self.processpath)

    def CheckFolder(self):
        myDB = database.DBConnection()
        snatched = myDB.select('SELECT * from wanted WHERE Status="Snatched"')

        if not snatched:
            logger.debug('No books are snatched. Nothing to process.')
        elif self.downloads:
            for book in snatched:
                if book['NZBtitle'] in self.downloads:
                    self.pp_path = os.path.join(self.processpath, book['NZBtitle'])
                    logger.info('Found folder %s.' % self.pp_path)

                    data = myDB.select("SELECT * from books WHERE BookID='%s'" % book['BookID'])
                    for metadata in data:
                        self.authorname = metadata[1]
                        self.authorimg = metadata[2]
                        self.bookname = metadata[3]
                        self.bookdesc = metadata[4]
                        self.bookisbn = metadata[5]
                        self.bookrate = metadata[6]
                        self.bookimg = metadata[7]
                        self.bookpage = metadata[8]
                        self.booklink = metadata[9]
                        self.bookdate = metadata[11]
                        self.booklang = metadata[12]

                    processBook = self.ProcessPath()
                    if processBook:
                        logger.info('Postprocessing for %s succeeded.' % self.bookname)

                        #update nzbs
                        controlValueDict = {"NZBurl": book['NZBurl']}
                        newValueDict = {"Status": "Success"}
                        myDB.upsert("wanted", newValueDict, controlValueDict)

                        #update books
                        controlValueDict = {"BookID": book['BookID']}
                        newValueDict = {"Status": "Have"}
                        myDB.upsert("books", newValueDict, controlValueDict)

                        #update authors
                        query = 'SELECT COUNT(*) FROM books WHERE AuthorName="%s" AND Status="Have"' % self.authorname
                        countbooks = myDB.action(query).fetchone()
                        havebooks = int(countbooks[0])
                        controlValueDict = {"AuthorName": self.authorname}
                        newValueDict = {"HaveBooks": havebooks}
                        myDB.upsert("authors", newValueDict, controlValueDict)
                    else:
                        logger.info('Postprocessing %s has failed.' % self.bookname)
        else:
            logger.info('No books are found in %s, nothing to process' % self.processpath)


    def ProcessPath(self):

        self.final_dest = os.path.join(self.destination, self.authorname, self.bookname)
        if not os.path.exists(self.final_dest):
            logger.info('%s does not exist, so it\'s safe to create it' % self.final_dest)
            try:
                if self.keep_original:
                    shutil.copytree(self.pp_path, self.final_dest)
                    logger.info('Successfully copied %s to %s.' % (self.pp_path, self.final_dest))
                else:
                    shutil.move(self.pp_path, self.final_dest)
                    logger.info('Successfully moved %s to %s.' % (self.pp_path, self.final_dest))
                pp = True
            except OSError:
                logger.error('Could not create destinationfolder. Check permissions of: ' + self.destination)
                pp = False

            #handle pictures
            try:
                if not self.bookimg == 'images/nocover.png':
                    logger.debug('Downloading cover from ' + self.bookimg)
                    coverpath = os.path.join(self.final_dest, 'cover.jpg')
                    img = open(coverpath,'wb')
                    imggoogle = imgGoogle()
                    img.write(imggoogle.open(self.bookimg).read())
                    img.close()

            except (IOError, EOFError), e:
                logger.error('Error fetching cover from url: %s, %s' % (self.bookimg, e))

            #handle metadata
            opfpath = os.path.join(self.final_dest, 'metadata.opf')
            if not os.path.exists(opfpath):
                meta = self.CreateOPF()
                opf = open(opfpath, 'wb')
                opf.write(meta)
                opf.close()
                logger.info('Saved metadata to: ' + opfpath)
            else:
                logger.info('%s allready exists. Did not create one.' % opfpath)

        else:
            logger.debug('Did not create %s because it allready exists (need to code more for that to work around existing files)' % self.destination)
            pp = False

        return pp


    def CreateOPF(self):
        opfinfo = '<?xml version="1.0"  encoding="UTF-8"?>\n\
<package version="2.0" xmlns="http://www.idpf.org/2007/opf" >\n\
    <metadata xmlns:dc="http://purl.org/dc/elements/1.1/" xmlns:opf="http://www.idpf.org/2007/opf">\n\
        <dc:title>%s</dc:title>\n\
        <creator>%s</creator>\n\
        <dc:identifier scheme="ISBN">%s</dc:identifier>\n\
        <dc:date>%s</dc:date>\n\
        <dc:description>%s</dc:description>\n\
        <dc:language>%s</dc:language>\n\
        <guide>\n\
            <reference href="cover.jpg" type="cover" title="Cover"/>\n\
        </guide>\n\
    </metadata>\n\
</package>' % (self.bookname, self.authorname, self.bookisbn, self.bookdate, self.bookdesc, self.booklang)

        return opfinfo
