import shutil, os, datetime

import lazylibrarian

from lazylibrarian import database, logger

class PostProcess:

    def __init__(self, processpath=None):
        self.destination = lazylibrarian.DESTINATION_DIR
        if processpath:
            self.processpath = processpath
        else:
           self.processpath = lazylibrarian.DOWNLOAD_DIR 

    def CheckFolder(self):
        myDB = database.DBConnection()
        snatched = myDB.select('SELECT * from wanted WHERE Status="Snatched"')
        downloads = os.listdir(self.processpath)

        if not snatched:
            logger.debug('No books are snatched. Nothing to process.')
        elif not downloads:
            logger.debug('%s is empty, nothing to process' % self.processpath)
        else:
            for book in snatched:
                if book['NZBtitle'] in downloads:
                    self.pp_path = os.path.join(self.processpath, book['NZBtitle'])
                    logger.info('Found folder %s.' % self.pp_path)
                    controlValueDict = {"NZBurl": book['NZBurl']}
                    newValueDict = {"Status": "Success"}
                    myDB.upsert("wanted", newValueDict, controlValueDict)

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

                    processBook = self.ProcessPath()




    def ProcessPath(self):

        self.final_dest = os.path.join(self.destination, self.authorname, self.bookname)
        if not os.path.exists(self.final_dest):
            logger.info('%s does not exist, so it\'s safe to create it' % self.final_dest)
            try:
                shutil.copytree(self.pp_path, self.final_dest)
                return True
                # add author.jpg as folder.jpg in this folder.
            except OSError:
                logger.error('Could not create destinationfolder. Check permissions of: ' + self.destination)
                return False

            logger.info('Successfully moved %s to %s.' % (self.pp_path, self.final_dest))
            controlValueDict = {"BookID": book['BookID']}
            newValueDict = {"Status": "Have"}
            myDB.upsert("books", newValueDict, controlValueDict)

        else:
            logger.info('Path allready exists. Skipping for now ...')




    #def processFiles(self, dest_pathsub=None, bookid=None, author=None, book=None):
    #    if new:
    #        rename all
    #        add folder/cover.jpg if no cover.jpg is found here and BookImgl is not nocover.

#    else:
#        if os.file.exists(dest_pathsub, bookfile
#            blahblah
#            remove old dir in the end or make it optional.
#            overwrite cover.jpg if found if BookImgl is not nocover

