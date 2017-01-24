#  This file is part of Lazylibrarian.
#
#  Lazylibrarian is free software':'you can redistribute it and/or modify
#  it under the terms of the GNU General Public License as published by
#  the Free Software Foundation, either version 3 of the License, or
#  (at your option) any later version.
#
#  Lazylibrarian is distributed in the hope that it will be useful,
#  but WITHOUT ANY WARRANTY; without even the implied warranty of
#  MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
#  GNU General Public License for more details.
#
#  You should have received a copy of the GNU General Public License
#  along with Lazylibrarian.  If not, see <http://www.gnu.org/licenses/>.

import traceback

from lazylibrarian import logger, database, importer
from lazylibrarian.formatter import plural


def dbUpdate(refresh=False):
    try:
        myDB = database.DBConnection()

        activeauthors = myDB.select('SELECT AuthorID from authors WHERE Status="Active" \
                                    or Status="Loading" order by DateAdded ASC')
        logger.info('Starting update for %i active author%s' % (len(activeauthors), plural(len(activeauthors))))

        for author in activeauthors:
            authorid = author[0]
            importer.addAuthorToDB(authorname='', refresh=refresh, authorid=authorid)

        logger.info('Active author update complete')
    except Exception:
        logger.error('Unhandled exception in dbUpdate: %s' % traceback.format_exc())
