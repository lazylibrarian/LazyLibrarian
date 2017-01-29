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

from __future__ import with_statement

import sqlite3
import threading
import time

import lazylibrarian
from lazylibrarian import logger

db_lock = threading.Lock()


class DBConnection:
    def __init__(self):
        self.connection = sqlite3.connect(lazylibrarian.DBFILE, 20)
        self.connection.row_factory = sqlite3.Row

    def action(self, query, args=None):
        with db_lock:

            if not query:
                return

            sqlResult = None
            attempt = 0

            while attempt < 5:

                try:
                    if not args:
                        sqlResult = self.connection.execute(query)
                    else:
                        sqlResult = self.connection.execute(query, args)
                    self.connection.commit()
                    break

                except sqlite3.OperationalError as e:
                    if "unable to open database file" in e.message or "database is locked" in e.message:
                        logger.warn('Database Error: %s' % e)
                        attempt += 1
                        if attempt == 5:
                            logger.debug("Failed query: %s" % query)
                        else:
                            time.sleep(1)
                    else:
                        logger.error('Database error: %s' % e)
                        raise

                except sqlite3.DatabaseError as e:
                    logger.error('Fatal error executing %s :: %s' % (query, e))
                    raise

            return sqlResult

    def match(self, query, args=None):
        try:
            # if there are no results, action() returns None and .fetchone() fails
            sqlResults = self.action(query, args).fetchone()
        except Exception:
            return []
        if not sqlResults:
            return []

        return sqlResults

    def select(self, query, args=None):
        try:
            # if there are no results, action() returns None and .fetchall() fails
            sqlResults = self.action(query, args).fetchall()
        except Exception:
            return []
        if not sqlResults:
            return []

        return sqlResults

    @staticmethod
    def genParams(myDict):
        return [x + " = ?" for x in myDict.keys()]

    def upsert(self, tableName, valueDict, keyDict):
        changesBefore = self.connection.total_changes

        # genParams = lambda myDict: [x + " = ?" for x in myDict.keys()]

        query = "UPDATE " + tableName + " SET " + ", ".join(self.genParams(valueDict)) + \
                " WHERE " + " AND ".join(self.genParams(keyDict))

        self.action(query, valueDict.values() + keyDict.values())

        if self.connection.total_changes == changesBefore:
            query = "INSERT INTO " + tableName + " (" + ", ".join(valueDict.keys() + keyDict.keys()) + ")" + \
                    " VALUES (" + ", ".join(["?"] * len(valueDict.keys() + keyDict.keys())) + ")"
            self.action(query, valueDict.values() + keyDict.values())
