import lazylibrarian

from lazylibrarian import logger, database, importer
from lazylibrarian.formatter import plural

def dbUpdate(forcefull=False):

    myDB = database.DBConnection()

    activeauthors = myDB.select('SELECT AuthorID, AuthorName from authors WHERE Status="Active" \
                                or Status="Loading" order by DateAdded ASC')
    logger.info('Starting update for %i active author%s' % (len(activeauthors), plural(len(activeauthors))))

    for author in activeauthors:
        # authorid = author[0]
        authorname = author[1]
        importer.addAuthorToDB(authorname, refresh=True)

    logger.info('Active author update complete')
