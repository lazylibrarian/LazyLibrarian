import shutil, os, datetime

import lazylibrarian

from lazylibrarian import database, logger

def CheckFolder():
    myDB = database.DBConnection()
    snatched = myDB.select('SELECT * from wanted WHERE Status="Snatched"')

    if snatched:
        for book in snatched:
            pp_pathsub = os.path.join(lazylibrarian.SAB_DIR, book['NZBtitle'])
            bookid = book['BookID']
            logger.info('Looking for %s' % pp_pathsub)

            if os.path.exists(pp_pathsub):
                logger.debug('Found %s. Processing %s' % (book['NZBtitle'], pp_pathsub))
                ProcessPath(bookid, pp_pathsub)
            else:
                logger.debug('No path found for: %s. Can\'t process it.' % book['NZBtitle'])
    else:
        logger.info('No books with status Snatched are found, nothing to process.')

def ProcessPath(bookid=None, pp_pathsub=None):
    myDB = database.DBConnection
    query = 'SELECT * from books WHERE BookID=%s' % bookid
    metadata = myDB.select(query)
    dest_path = lazylibrarian.SAB_DIR

    author = metadata['AuthorName']
    book =  metadata['BookName']

    dest_pathsub = os.path.join(dest_path, author, book)
    if not os.path.exists(dest_pathsub):
        logger.info('%s does not exist, so it\'s safe to create it' % dest_pathsub)
        try:
            shutil.copytree(pp_pathsub, dest_pathsub)
            # add author.jpg as folder.jpg in this folder.
        except OSError:
            logger.error('Could not create destinationfolder. Check permissions of: ' + dest_path)

        logger.info('Successfully moved %s to %s.' % (pp_pathsub, dest_pathsub))
        processFiles(dest_pathsub, bookid, author, book, new=True)
    else:
        logger.info('%s allready exists. Moving files only' % dest_pathsub)
        processFiles(dest_pathsub, bookid, author, book, new=False)

    #def processFiles(self, dest_pathsub=None, bookid=None, author=None, book=None):
    #    if new:
    #        rename all
    #        add folder/cover.jpg if no cover.jpg is found here and BookImgl is not nocover.

#    else:
#        if os.file.exists(dest_pathsub, bookfile
#            blahblah
#            remove old dir in the end or make it optional.
#            overwrite cover.jpg if found if BookImgl is not nocover

