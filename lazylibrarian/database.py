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
        # journal disabled since we never do rollbacks
        self.connection.execute("PRAGMA journal_mode = WAL")
        # sync less often as using WAL mode
        self.connection.execute("PRAGMA synchronous = NORMAL")
        # 32mb of cache
        self.connection.execute("PRAGMA cache_size=-%s" % (32 * 1024))
        # for cascade deletes
        self.connection.execute("PRAGMA foreign_keys = ON")
        self.connection.row_factory = sqlite3.Row

    # wrapper function with lock
    def action(self, query, args=None, suppress=None):
        if not query:
            return None
        with db_lock:
            return self._action(query, args, suppress)

    # do not use directly, use through action() or upsert() which add lock
    def _action(self, query, args=None, suppress=None):
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
                if "unable to open database file" in str(e) or "database is locked" in str(e):
                    logger.warn('Database Error: %s' % e)
                    logger.debug("Attempted db query: [%s]" % query)
                    attempt += 1
                    if attempt == 5:
                        logger.error("Failed db query: [%s]" % query)
                    else:
                        time.sleep(1)
                else:
                    logger.error('Database error: %s' % e)
                    logger.error("Failed query: [%s]" % query)
                    raise

            except sqlite3.IntegrityError as e:
                # we could ignore unique errors in sqlite by using "insert or ignore into" statements
                # but this would also ignore null values as we can't specify which errors to ignore :-(
                # Also the python interface to sqlite only returns english text messages, not error codes
                msg = str(e).lower()
                if suppress and 'UNIQUE' in suppress and ('not unique' in msg or 'unique constraint failed' in msg):
                    if lazylibrarian.LOGLEVEL & lazylibrarian.log_dbcomms:
                        logger.debug('Suppressed [%s] %s' % (query, e))
                        logger.debug("Suppressed args: [%s]" % str(args))
                    self.connection.commit()
                    break
                else:
                    logger.error('Database Integrity error: %s' % e)
                    logger.error("Failed query: [%s]" % query)
                    logger.error("Failed args: [%s]" % str(args))
                    raise

            except sqlite3.DatabaseError as e:
                logger.error('Fatal error executing %s :: %s' % (query, e))
                raise

        return sqlResult

    def match(self, query, args=None):
        try:
            # if there are no results, action() returns None and .fetchone() fails
            sqlResults = self.action(query, args).fetchone()
        except sqlite3.Error:
            return []
        if not sqlResults:
            return []

        return sqlResults

    def select(self, query, args=None):
        try:
            # if there are no results, action() returns None and .fetchall() fails
            sqlResults = self.action(query, args).fetchall()
        except sqlite3.Error:
            return []
        if not sqlResults:
            return []

        return sqlResults

    @staticmethod
    def genParams(myDict):
        return [x + " = ?" for x in list(myDict.keys())]

    def upsert(self, tableName, valueDict, keyDict):
        with db_lock:
            changesBefore = self.connection.total_changes

            query = "UPDATE " + tableName + " SET " + ", ".join(self.genParams(valueDict)) + \
                    " WHERE " + " AND ".join(self.genParams(keyDict))

            self._action(query, list(valueDict.values()) + list(keyDict.values()))

            # This version of upsert is not thread safe, each action() is thread safe,
            # but it's possible for another thread to jump in between the
            # UPDATE and INSERT statements so we use suppress=unique to log any conflicts
            # -- update -- should be thread safe now, threading lock moved

            if self.connection.total_changes == changesBefore:
                query = "INSERT INTO " + tableName + " ("
                query += ", ".join(list(valueDict.keys()) + list(keyDict.keys())) + ") VALUES ("
                query += ", ".join(["?"] * len(list(valueDict.keys()) + list(keyDict.keys()))) + ")"
                self._action(query, list(valueDict.values()) + list(keyDict.values()), suppress="UNIQUE")
