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

from lazylibrarian import importer, postprocess, versioncheck, logger, database, updater, librarysync, magazinescan, formatter, bookcovers
from lazylibrarian.searchnzb import search_nzb_book
from lazylibrarian.searchtorrents import search_tor_book
from lazylibrarian.searchmag import search_magazines
from lazylibrarian.searchrss import search_rss_book
from lazylibrarian.gr import GoodReads
from lazylibrarian.gb import GoogleBooks

import lazylibrarian
import json
import threading
import Queue

cmd_dict = {'help':'list available commands',
            'getIndex':'list all authors',
            'getAuthor':'&id= get author and list their books from AuthorID',
            'getWanted':'list wanted books',
            'getSnatched':'list snatched books',
            'getHistory':'list history',
            'getLogs':'show current log',
            'clearLogs':'clear current log',
            'getMagazines':'list magazines',
            'getIssues':'&name= list issues for named magazine',
            'forceMagSearch':'search for all wanted magazines',
            'forceBookSearch':'search for all wanted books',
            'forceProcess':'process books/mags in download dir',
            'pauseAuthor':'&id= pause author by AuthorID',
            'resumeAuthor':'&id= resume author by AuthorID',
            'refreshAuthor':'&name= refresh author by name',
            'forceActiveAuthorsUpdate':'refresh all active authors and reload their books',
            'forceLibraryScan':'refresh whole book library',
            'forceMagazineScan':'refresh whole magazine library',
            'getVersion':'show git version',
            'shutdown':'stop lazylibrarian',
            'restart':'restart lazylibrarian',
            'update':'update lazylibrarian',
            'findAuthor':'&name= search goodreads/googlebooks for named author',
            'findBook':'&name= search goodreads/googlebooks for named book',
            'addAuthor':'&name= add author to database by name',
            'delAuthor':'&id= delete author from database by AuthorID',
            'refreshAuthor':'&name= refresh author by name',
            'addMagazine':'&name= add magazine to database by name',
            'delMagazine':'&name= delete magazine and issues from database by name',
            'queueBook':'&id= mark book as Wanted',
            'unqueueBook':'&id= mark book as Skipped',
            'readCFG':'&section=&name= read value of config variable',
            'writeCFG':'&section=&name=&value= set config variable name=value',
            'loadCFG':'reload config from file',
            'getBookCover':'&id= fetch a cover from google for one BookID',
            'getBookCovers':'fetch covers from google for all books with no existing cover',
            'getAllBooks':'list all books in the database'
            }

class Api(object):

    def __init__(self):

        self.apikey = None
        self.cmd = None
        self.id = None

        self.kwargs = None

        self.data = None

        self.callback = None

    def checkParams(self, *args, **kwargs):

        if not lazylibrarian.API_ENABLED:
            self.data = 'API not enabled'
            return
        if not lazylibrarian.API_KEY:
            self.data = 'API key not generated'
            return
        if len(lazylibrarian.API_KEY) != 32:
            self.data = 'API key not generated correctly'
            return

        if 'apikey' not in kwargs:
            self.data = 'Missing api key'
            return

        if kwargs['apikey'] != lazylibrarian.API_KEY:
            self.data = 'Incorrect API key'
            return
        else:
            self.apikey = kwargs.pop('apikey')

        if 'cmd' not in kwargs:
            self.data = 'Missing parameter: cmd, try cmd=help'
            return

        if kwargs['cmd'] not in cmd_dict:
            self.data = 'Unknown command: %s, try cmd=help' % kwargs['cmd']
            return
        else:
            self.cmd = kwargs.pop('cmd')

        self.kwargs = kwargs
        self.data = 'OK'

    def fetchData(self):

        if self.data == 'OK':
            args = []
            if 'name' in self.kwargs:
               args.append({"name": self.kwargs['name']}) 
            if 'id' in self.kwargs:
               args.append({"id": self.kwargs['id']}) 
            if 'section' in self.kwargs:
               args.append({"section": self.kwargs['section']}) 
            if 'value' in self.kwargs:
               args.append({"value": self.kwargs['value']}) 
            logger.info('Received API command: %s %s' % (self.cmd, args))
            methodToCall = getattr(self, "_" + self.cmd)
            methodToCall(**self.kwargs)
            if 'callback' not in self.kwargs:
                if isinstance(self.data, basestring):
                    return self.data
                else:
                    return json.dumps(self.data)
            else:
                self.callback = self.kwargs['callback']
                self.data = json.dumps(self.data)
                self.data = self.callback + '(' + self.data + ');'
                return self.data
        else:
            return self.data

    def _dic_from_query(self, query):

        myDB = database.DBConnection()
        rows = myDB.select(query)

        rows_as_dic = []

        for row in rows:
            row_as_dic = dict(zip(row.keys(), row))
            rows_as_dic.append(row_as_dic)

        return rows_as_dic

    def _help(self, **kwargs):
        self.data = dict(cmd_dict)
        return

    def _getHistory(self, **kwargs):
        self.data = self._dic_from_query(
            "SELECT * from wanted WHERE Status != 'Skipped' and Status != 'Ignored'")
        return
 
    def _getWanted(self, **kwargs):
        self.data = self._dic_from_query(
            "SELECT * from books WHERE Status='Wanted'")
        return

    def _getSnatched(self, **kwargs):
        self.data = self._dic_from_query(
            "SELECT * from books WHERE Status='Snatched'")
        return
        
    def _getLogs(self, **kwargs):
        self.data = lazylibrarian.LOGLIST
        return

    def _clearLogs(self, **kwargs):
        lazylibrarian.LOGLIST = []
        self.data = 'Cleared log'
        return

    def _getIndex(self, **kwargs):
        self.data = self._dic_from_query(
            'SELECT * from authors order by AuthorName COLLATE NOCASE')
        return

    def _getAuthor(self, **kwargs):
        if 'id' not in kwargs:
            self.data = 'Missing parameter: id'
            return
        else:
            self.id = kwargs['id']

        author = self._dic_from_query(
            'SELECT * from authors WHERE AuthorID="' + self.id + '"')
        books = self._dic_from_query(
            'SELECT * from books WHERE AuthorID="' + self.id + '"')
        
        self.data = {
            'author': author, 'books': books}
        return

    def _getMagazines(self, **kwargs):
        self.data = self._dic_from_query(
            'SELECT * from magazines order by Title COLLATE NOCASE')
        return

    def _getAllBooks(self, **kwargs):
        self.data = self._dic_from_query(
            'SELECT AuthorID,AuthorName,AuthorLink, BookName,BookSub,BookGenre,BookIsbn,BookPub, \
            BookRate,BookImg,BookPages,BookLink,BookID,BookDate, BookLang,BookAdded,Status,Series,SeriesOrder \
            from books')
        return

    def _getIssues(self, **kwargs):
        if 'name' not in kwargs:
            self.data = 'Missing parameter: name'
            return
        else:
            self.id = kwargs['name']

        magazine = self._dic_from_query(
            'SELECT * from magazines WHERE Title="' + self.id + '"')
        issues = self._dic_from_query(
            'SELECT * from issues WHERE Title="' + self.id + '" order by IssueDate DESC')
        
        self.data = {
            'magazine': magazine, 'issues': issues}
        return

    def _getBook(self, **kwargs):
        if 'id' not in kwargs:
            self.data = 'Missing parameter: id'
            return
        else:
            self.id = kwargs['id']

        book = self._dic_from_query(
            'SELECT * from books WHERE BookID="' + self.id + '"')
        self.data = {'book': book}
        return

    def _queueBook(self, **kwargs):
        if 'id' not in kwargs:
            self.data = 'Missing parameter: id'
            return
        else:
            self.id = kwargs['id']

        myDB = database.DBConnection()
        controlValueDict = {'BookID': self.id}
        newValueDict = {'Status': 'Wanted'}
        myDB.upsert("books", newValueDict, controlValueDict)
        return

    def _unqueueBook(self, **kwargs):
        if 'id' not in kwargs:
            self.data = 'Missing parameter: id'
            return
        else:
            self.id = kwargs['id']

        myDB = database.DBConnection()
        controlValueDict = {'BookID': self.id}
        newValueDict = {'Status': 'Skipped'}
        myDB.upsert("books", newValueDict, controlValueDict)
        return

    def _addMagazine(self, **kwargs):
        if 'name' not in kwargs:
            self.data = 'Missing parameter: name'
            return
        else:
            self.id = kwargs['name']
        
        controlValueDict = {"Title": self.id}
        newValueDict = {
            "Frequency": None,
            "Regex": None,
            "Status": "Active",
            "MagazineAdded": formatter.today(),
            "IssueStatus": "Wanted"
        }
        myDB.upsert("magazines", newValueDict, controlValueDict)
        mags = [{"bookid": self.id}]
        if lazylibrarian.USE_NZB() or lazylibrarian.USE_TOR():
            threading.Thread(target=search_magazines, args=[mags, False]).start()
        return
        
    def _delMagazine(self, **kwargs):
        if 'name' not in kwargs:
            self.data = 'Missing parameter: name'
            return
        else:
            self.id = kwargs['name']

        myDB = database.DBConnection()
        myDB.action('DELETE from magazines WHERE Title="%s"' % self.id)
        myDB.action('DELETE from wanted WHERE BookID="%s"' % self.id)
        myDB.action('DELETE from issues WHERE Title="%s"' % self.id)
        return
        
    def _pauseAuthor(self, **kwargs):
        if 'id' not in kwargs:
            self.data = 'Missing parameter: id'
            return
        else:
            self.id = kwargs['id']

        myDB = database.DBConnection()
        controlValueDict = {'AuthorID': self.id}
        newValueDict = {'Status': 'Paused'}
        myDB.upsert("authors", newValueDict, controlValueDict)

    def _resumeAuthor(self, **kwargs):
        if 'id' not in kwargs:
            self.data = 'Missing parameter: id'
            return
        else:
            self.id = kwargs['id']

        myDB = database.DBConnection()
        controlValueDict = {'AuthorID': self.id}
        newValueDict = {'Status': 'Active'}
        myDB.upsert("authors", newValueDict, controlValueDict)

    def _refreshAuthor(self, **kwargs):
        if 'name' not in kwargs:
            self.data = 'Missing parameter: name'
            return
        else:
            self.id = kwargs['name']

        try:
            importer.addAuthorToDB(self.id, refresh=True)
        except Exception as e:
            self.data = e
        return

    def _forceActiveAuthorsUpdate(self, **kwargs):
        threading.Thread(target=updater.dbUpdate, args=[False]).start()

    def _forceMagSearch(self, **kwargs):
        if lazylibrarian.USE_NZB() or lazylibrarian.USE_TOR():
                threading.Thread(target=search_magazines, args=[None, True]).start()

    def _forceBookSearch(self, **kwargs):
        if lazylibrarian.USE_NZB():
                threading.Thread(target=search_nzb_book).start()
        if lazylibrarian.USE_TOR():
            threading.Thread(target=search_tor_book).start()
        if lazylibrarian.USE_RSS():
            threading.Thread(target=search_rss_book).start()

    def _forceProcess(self, **kwargs):
        postprocess.processDir()

    def _forceLibraryScan(self, **kwargs):
        threading.Thread(target=librarysync.LibraryScan(lazylibrarian.DESTINATION_DIR)).start()
    
    def _forceMagazineScan(self, **kwargs):
        threading.Thread(target=magazinescan.magazineScan()).start()
    
    def _getVersion(self, **kwargs):
        self.data = {
            'install_type': lazylibrarian.INSTALL_TYPE,
            'current_version': lazylibrarian.CURRENT_VERSION,
            'latest_version': lazylibrarian.LATEST_VERSION,
            'commits_behind': lazylibrarian.COMMITS_BEHIND,
        }

    def _shutdown(self, **kwargs):
        lazylibrarian.SIGNAL = 'shutdown'

    def _restart(self, **kwargs):
        lazylibrarian.SIGNAL = 'restart'

    def _update(self, **kwargs):
        lazylibrarian.SIGNAL = 'update'

    def _findAuthor(self, **kwargs):
        if 'name' not in kwargs:
            self.data = 'Missing parameter: name'
            return

        myDB = database.DBConnection()
        if lazylibrarian.BOOK_API == "GoogleBooks":
            GB = GoogleBooks(kwargs['name'])
            queue = Queue.Queue()
            search_api = threading.Thread(
                target=GB.find_results, args=[kwargs['name'], queue])
            search_api.start()
        elif lazylibrarian.BOOK_API == "GoodReads":
            queue = Queue.Queue()
            GR = GoodReads(kwargs['name'])
            search_api = threading.Thread(
                target=GR.find_results, args=[kwargs['name'], queue])
            search_api.start()

        search_api.join()
        self.data = queue.get()

    def _findBook(self, **kwargs):
        if 'name' not in kwargs:
            self.data = 'Missing parameter: name'
            return
        myDB = database.DBConnection()
        if lazylibrarian.BOOK_API == "GoogleBooks":
            GB = GoogleBooks(kwargs['name'])
            queue = Queue.Queue()
            search_api = threading.Thread(
                target=GB.find_results, args=[kwargs['name'], queue])
            search_api.start()
        elif lazylibrarian.BOOK_API == "GoodReads":
            queue = Queue.Queue()
            GR = GoodReads(kwargs['name'])
            search_api = threading.Thread(
                target=GR.find_results, args=[kwargs['name'], queue])
            search_api.start()

        search_api.join()
        self.data = queue.get()
        

    def _addAuthor(self, **kwargs):
        if 'name' not in kwargs:
            self.data = 'Missing parameter: name'
            return
        else:
            self.id = kwargs['name']

        try:
            importer.addAuthorToDB(self.id, refresh=False)
        except Exception as e:
            self.data = e

        return

    def _delAuthor(self, **kwargs):
        if 'id' not in kwargs:
            self.data = 'Missing parameter: id'
            return
        else:
            self.id = kwargs['id']

        myDB = database.DBConnection()
        authorsearch = myDB.select(
            'SELECT AuthorName from authors WHERE AuthorID="%s"' % AuthorID)
        if len(authorsearch):  # to stop error if try to delete an author while they are still loading
            AuthorName = authorsearch[0]['AuthorName']
            logger.info(u"Removing all references to author: %s" % AuthorName)

            myDB.action('DELETE from authors WHERE AuthorID="%s"' % AuthorID)
            myDB.action('DELETE from books WHERE AuthorID="%s"' % AuthorID)

    def _writeCFG(self, **kwargs):
        if 'name' not in kwargs:
            self.data = 'Missing parameter: name'
            return
        if 'value' not in kwargs:
            self.data = 'Missing parameter: value'
            return
        if 'section' not in kwargs:
            self.data = 'Missing parameter: section'
            return
        
        try:
            self.data = '["%s"]' % lazylibrarian.CFG.get(kwargs['section'], kwargs['name'])
            lazylibrarian.CFG.set(kwargs['section'], kwargs['name'], kwargs['value'])
            with open(lazylibrarian.CONFIGFILE, 'wb') as configfile:
                lazylibrarian.CFG.write(configfile)
            lazylibrarian.config_read(reloaded=True)
        except:
            self.data = 'Unable to update CFG entry for %s: %s' % (kwargs['section'], kwargs['name'])
            
    def _readCFG(self, **kwargs):
        if 'name' not in kwargs:
            self.data = 'Missing parameter: name'
            return
        if 'section' not in kwargs:
            self.data = 'Missing parameter: section'
            return
        
        try:
            self.data = '["%s"]' % lazylibrarian.CFG.get(kwargs['section'], kwargs['name'])
        except:
            self.data = 'No CFG entry for %s: %s' % (kwargs['section'], kwargs['name'])
            
    def _loadCFG(self, **kwargs):
        lazylibrarian.config_read(reloaded=True)

    def _getBookCover(self, **kwargs):
        if 'id' not in kwargs:
            self.data = 'Missing parameter: id'
            return
        else:
            self.id = kwargs['id']
        booklist=[]
        booklist.append(self.id)
        threading.Thread(target=bookcovers.getBookCovers, args=[booklist]).start()
        return

    def _getBookCovers(self, **kwargs):
        booklist=[]
        myDB = database.DBConnection()
        need_covers = myDB.action('select bookid from books where bookimg like "%nocover%" or bookimg like "%nophoto%"')
        for item in need_covers:
            bookid = item['bookid']
            booklist.append(bookid)
        self.data = 'Fetching covers for %i books' % len(booklist)
        threading.Thread(target=bookcovers.getBookCovers, args=[booklist]).start()
        return

