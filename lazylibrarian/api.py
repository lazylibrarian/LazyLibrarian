#  This file is part of Lazylibrarian.
#  Lazylibrarian is free software':'you can redistribute it and/or modify
#  it under the terms of the GNU General Public License as published by
#  the Free Software Foundation, either version 3 of the License, or
#  (at your option) any later version.
#  Lazylibrarian is distributed in the hope that it will be useful,
#  but WITHOUT ANY WARRANTY; without even the implied warranty of
#  MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
#  GNU General Public License for more details.
#  You should have received a copy of the GNU General Public License
#  along with Lazylibrarian.  If not, see <http://www.gnu.org/licenses/>.


import json
import os
import sys
import shutil
import threading
import cherrypy
from lib.six import PY2, string_types
# noinspection PyUnresolvedReferences
from lib.six.moves import configparser, queue

import lazylibrarian
from lazylibrarian import logger, database
from lazylibrarian.bookwork import setWorkPages, getBookCovers, getWorkSeries, getWorkPage, setAllBookSeries, \
    getBookCover, getAuthorImage, getAuthorImages, getSeriesMembers, getSeriesAuthors, deleteEmptySeries, \
    getBookAuthors, setAllBookAuthors, audioRename
from lazylibrarian.cache import cache_img
from lazylibrarian.common import clearLog, cleanCache, restartJobs, showJobs, checkRunningJobs, aaUpdate, setperm, \
    logHeader
from lazylibrarian.csvfile import import_CSV, export_CSV
from lazylibrarian.formatter import today, formatAuthorName, check_int, plural, makeUnicode, makeBytestr, replace_all
from lazylibrarian.gb import GoogleBooks
from lazylibrarian.gr import GoodReads
from lazylibrarian.grsync import grfollow, grsync
from lazylibrarian.importer import addAuthorToDB, addAuthorNameToDB, update_totals
from lazylibrarian.librarysync import LibraryScan
from lazylibrarian.magazinescan import magazineScan, create_covers
from lazylibrarian.manualbook import searchItem
from lazylibrarian.postprocess import processDir, processAlternate, processOPF
from lazylibrarian.searchbook import search_book
from lazylibrarian.searchmag import search_magazines, get_issue_date
from lazylibrarian.searchrss import search_rss_book
from lazylibrarian.calibre import syncCalibreList, calibreList
from lazylibrarian.providers import get_capabilities

cmd_dict = {'help': 'list available commands. ' +
                    'Time consuming commands take an optional &wait parameter if you want to wait for completion, ' +
                    'otherwise they return OK straight away and run in the background',
            'showMonths': 'List installed monthnames',
            'dumpMonths': 'Save installed monthnames to file',
            'getIndex': 'list all authors',
            'getAuthor': '&id= get author by AuthorID and list their books',
            'getAuthorImage': '&id= get an image for this author',
            'setAuthorImage': '&id= &img= set a new image for this author',
            'setAuthorLock': '&id= lock author name/image/dates',
            'setAuthorUnlock': '&id= unlock author name/image/dates',
            'setBookLock': '&id= lock book details',
            'setBookUnlock': '&id= unlock book details',
            'setBookImage': '&id= &img= set a new image for this book',
            'getAuthorImages': '[&wait] get images for all authors without one',
            'getWanted': 'list wanted books',
            'getRead': 'list read books for current user',
            'getToRead': 'list to-read books for current user',
            'getSnatched': 'list snatched books',
            'getHistory': 'list history',
            'getLogs': 'show current log',
            'getDebug': 'show debug log header',
            'getModules': 'show installed modules',
            'checkModules': 'Check using lazylibrarian library modules',
            'clearLogs': 'clear current log',
            'getMagazines': 'list magazines',
            'getIssues': '&name= list issues of named magazine',
            'getIssueName': '&name= get name of issue from path/filename',
            'createMagCovers': '[&wait] [&refresh] create covers for magazines, optionally refresh existing ones',
            'forceMagSearch': '[&wait] search for all wanted magazines',
            'forceBookSearch': '[&wait] [&type=eBook/AudioBook] search for all wanted books',
            'forceRSSSearch': '[&wait] search all entries in rss wishlists',
            'forceProcess': '[&dir] [ignorekeepseeding] process books/mags in download or named dir',
            'pauseAuthor': '&id= pause author by AuthorID',
            'resumeAuthor': '&id= resume author by AuthorID',
            'ignoreAuthor': '&id= ignore author by AuthorID',
            'unignoreAuthor': '&id= unignore author by AuthorID',
            'refreshAuthor': '&name= [&refresh] reload author (and their books) by name, optionally refresh cache',
            'forceActiveAuthorsUpdate': '[&wait] [&refresh] reload all active authors and book data, refresh cache',
            'forceLibraryScan': '[&wait] [&remove] [&dir=] [&id=] rescan whole or part book library',
            'forceAudioBookScan': '[&wait] [&remove] [&dir=] [&id=] rescan whole or part audiobook library',
            'forceMagazineScan': '[&wait] rescan whole magazine library',
            'getVersion': 'show lazylibrarian current/git version',
            'shutdown': 'stop lazylibrarian',
            'restart': 'restart lazylibrarian',
            'update': 'update lazylibrarian',
            'findAuthor': '&name= search goodreads/googlebooks for named author',
            'findBook': '&name= search goodreads/googlebooks for named book',
            'addBook': '&id= add book details to the database',
            'moveBooks': '&fromname= &toname= move all books from one author to another by AuthorName',
            'moveBook': '&id= &toid= move one book to new author by BookID and AuthorID',
            'addAuthor': '&name= add author to database by name',
            'addAuthorID': '&id= add author to database by AuthorID',
            'removeAuthor': '&id= remove author from database by AuthorID',
            'addMagazine': '&name= add magazine to database by name',
            'removeMagazine': '&name= remove magazine and all of its issues from database by name',
            'queueBook': '&id= [&type=eBook/AudioBook] mark book as Wanted, default eBook',
            'unqueueBook': '&id= [&type=eBook/AudioBook] mark book as Skipped, default eBook',
            'readCFG': '&name=&group= read value of config variable "name" in section "group"',
            'writeCFG': '&name=&group=&value= set config variable "name" in section "group" to value',
            'loadCFG': 'reload config from file',
            'getBookCover': '&id= [&src=] fetch cover link from cache/cover/librarything/goodreads/google for BookID',
            'getAllBooks': 'list all books in the database',
            'getNoLang': 'list all books in the database with unknown language',
            'listIgnoredAuthors': 'list all authors in the database marked ignored',
            'listIgnoredBooks': 'list all books in the database marked ignored',
            'listIgnoredSeries': 'list all series in the database marked ignored',
            'listMissingWorkpages': 'list all books with errorpage or no workpage',
            'searchBook': '&id= [&wait] [&type=eBook/AudioBook] search for one book by BookID',
            'searchItem': '&item= get search results for an item (author, title, isbn)',
            'showJobs': 'show status of running jobs',
            'restartJobs': 'restart background jobs',
            'showThreads': 'show threaded processes',
            'checkRunningJobs': 'ensure all needed jobs are running',
            'vacuum': 'vacuum the database',
            'getWorkSeries': '&id= Get series from Librarything BookWork using BookID',
            'getSeriesMembers': '&id= Get list of series members from Librarything using SeriesID',
            'getSeriesAuthors': '&id= Get all authors from Librarything for a series and import them',
            'getWorkPage': '&id= Get url of Librarything BookWork using BookID',
            'getBookCovers': '[&wait] Check all books for cached cover and download one if missing',
            'getBookAuthors': '&id= Get list of authors associated with this book',
            'cleanCache': '[&wait] Clean unused and expired files from the LazyLibrarian caches',
            'deleteEmptySeries': 'Delete any book series that have no members',
            'setWorkPages': '[&wait] Set the WorkPages links in the database',
            'setAllBookSeries': '[&wait] Set the series details from book workpages',
            'setAllBookAuthors': '[&wait] Set all authors for all books from book workpages',
            'importAlternate': '[&wait] [&dir=] Import books from named or alternate folder and any subfolders',
            'importCSVwishlist': '[&wait] [&dir=] Import a CSV wishlist from named or alternate directory',
            'exportCSVwishlist': '[&wait] [&dir=] Export a CSV wishlist to named or alternate directory',
            'grSync': '&status= &shelf= Sync books with given status to a goodreads shelf',
            'grFollow': '&id= Follow an author on goodreads',
            'grFollowAll': 'Follow all lazylibrarian authors on goodreads',
            'grUnfollow': '&id= Unfollow an author on goodreads',
            'writeOPF': '&id= [&refresh] write out an opf file for a bookid, optionally overwrite existing opf',
            'writeAllOPF': '[&refresh] write out opf files for all books, optionally overwrite existing opf',
            'renameAudio': '&id Rename an audiobook using configured pattern',
            'showCaps': '&provider= get a list of capabilities from a provider',
            'calibreList': '[&toread=] [&read=] get a list of books in calibre library',
            'syncCalibreList': '[&toread=] [&read=] sync list of read/toread books with calibre',
            'logMessage': '&level= &text=  send a message to lazylibrarian logger',
            }


class Api(object):
    def __init__(self):

        self.apikey = None
        self.cmd = None
        self.id = None

        self.kwargs = None

        self.data = None

        self.callback = None

    def checkParams(self, **kwargs):

        if not lazylibrarian.CONFIG['API_ENABLED']:
            self.data = 'API not enabled'
            return
        if not lazylibrarian.CONFIG['API_KEY']:
            self.data = 'API key not generated'
            return
        if len(lazylibrarian.CONFIG['API_KEY']) != 32:
            self.data = 'API key is invalid'
            return

        if 'apikey' not in kwargs:
            self.data = 'Missing api key'
            return

        if kwargs['apikey'] != lazylibrarian.CONFIG['API_KEY']:
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

    @property
    def fetchData(self):

        threading.currentThread().name = "API"

        if self.data == 'OK':
            if 'X-Forwarded-For' in cherrypy.request.headers:
                remote_ip = cherrypy.request.headers['X-Forwarded-For']  # apache2
            elif 'X-Host' in cherrypy.request.headers:
                remote_ip = cherrypy.request.headers['X-Host']  # lighthttpd
            elif 'Host' in cherrypy.request.headers:
                remote_ip = cherrypy.request.headers['Host']  # nginx
            else:
                remote_ip = cherrypy.request.remote.ip
            logger.debug('Received API command from %s: %s %s' % (remote_ip, self.cmd, self.kwargs))
            methodToCall = getattr(self, "_" + self.cmd)
            methodToCall(**self.kwargs)
            if 'callback' not in self.kwargs:
                if isinstance(self.data, string_types):
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

    @staticmethod
    def _dic_from_query(query):

        myDB = database.DBConnection()
        rows = myDB.select(query)

        rows_as_dic = []

        for row in rows:
            row_as_dic = dict(list(zip(list(row.keys()), row)))
            rows_as_dic.append(row_as_dic)

        return rows_as_dic

    def _syncCalibreList(self, **kwargs):
        col1 = None
        col2 = None
        if 'toread' in kwargs:
            col2 = kwargs['toread']
        if 'read' in kwargs:
            col1 = kwargs['read']
        self.data = syncCalibreList(col1, col2)

    def _calibreList(self, **kwargs):
        col1 = None
        col2 = None
        if 'toread' in kwargs:
            col2 = kwargs['toread']
        if 'read' in kwargs:
            col1 = kwargs['read']
        self.data = calibreList(col1, col2)

    def _showCaps(self, **kwargs):
        if 'provider' not in kwargs:
            self.data = 'Missing parameter: provider'
            return

        prov = kwargs['provider']
        match = False
        for provider in lazylibrarian.NEWZNAB_PROV:
            if prov == provider['HOST']:
                prov = provider
                match = True
                break
        if not match:
            for provider in lazylibrarian.TORZNAB_PROV:
                if prov == provider['HOST']:
                    prov = provider
                    match = True
                    break
        if not match:
            self.data = 'Invalid parameter: provider'
            return
        self.data = get_capabilities(prov, True)

    def _help(self):
        self.data = dict(cmd_dict)

    def _getHistory(self):
        self.data = self._dic_from_query(
            "SELECT * from wanted WHERE Status != 'Skipped' and Status != 'Ignored'")

    def _showThreads(self):
        self.data = [n.name for n in [t for t in threading.enumerate()]]

    def _showMonths(self):
        self.data = lazylibrarian.MONTHNAMES

    def _renameAudio(self, **kwargs):
        if 'id' not in kwargs:
            self.data = 'Missing parameter: id'
            return
        self.data = audioRename(kwargs['id'])

    def _writeAllOPF(self, **kwargs):
        myDB = database.DBConnection()
        books = myDB.select('select BookID from books where BookFile is not null')
        counter = 0
        if books:
            for book in books:
                bookid = book['BookID']
                if 'refresh' in kwargs:
                    self._writeOPF(id=bookid, refresh=True)
                else:
                    self._writeOPF(id=bookid)
                try:
                    if self.data[1] is True:
                        counter += 1
                except IndexError:
                    counter = counter
        self.data = 'Updated opf for %s book%s' % (counter, plural(counter))

    def _writeOPF(self, **kwargs):
        if 'id' not in kwargs:
            self.data = 'Missing parameter: id'
            return
        else:
            self.id = kwargs['id']
            myDB = database.DBConnection()
            cmd = 'SELECT AuthorName,BookID,BookName,BookDesc,BookIsbn,BookImg,BookDate,BookLang,BookPub,BookFile'
            cmd += ' from books,authors WHERE BookID=? and books.AuthorID = authors.AuthorID'
            res = myDB.match(cmd, (kwargs['id'],))
            if not res:
                self.data = 'No data found for bookid %s' % kwargs['id']
                return
            if not res['BookFile']:
                self.data = 'No bookfile found for bookid %s' % kwargs['id']
                return
            dest_path = os.path.dirname(res['BookFile'])
            global_name = os.path.splitext(os.path.basename(res['BookFile']))[0]
            refresh = False
            if 'refresh' in kwargs:
                refresh = True
            self.data = processOPF(dest_path, res, global_name, refresh)

    @staticmethod
    def _dumpMonths():
        json_file = os.path.join(lazylibrarian.DATADIR, 'monthnames.json')
        with open(json_file, 'w') as f:
            json.dump(lazylibrarian.MONTHNAMES, f)

    def _getWanted(self):
        self.data = self._dic_from_query(
            "SELECT * from books WHERE Status='Wanted'")

    def _getRead(self):
        userid = None
        cookie = cherrypy.request.cookie
        if cookie and 'll_uid' in list(cookie.keys()):
            userid = cookie['ll_uid'].value
        if not userid:
            self.data = 'No userid'
        else:
            self.data = self._dic_from_query(
                "SELECT haveread from users WHERE userid='%s'" % userid)

    def _getToRead(self):
        userid = None
        cookie = cherrypy.request.cookie
        if cookie and 'll_uid' in list(cookie.keys()):
            userid = cookie['ll_uid'].value
        if not userid:
            self.data = 'No userid'
        else:
            self.data = self._dic_from_query(
                "SELECT toread from users WHERE userid='%s'" % userid)

    def _vacuum(self):
        self.data = self._dic_from_query("vacuum; pragma integrity_check")

    def _getSnatched(self):
        self.data = self._dic_from_query(
            "SELECT * from books WHERE Status='Snatched'")

    def _getLogs(self):
        self.data = lazylibrarian.LOGLIST

    def _logMessage(self, **kwargs):
        if 'level' not in kwargs:
            self.data = 'Missing parameter: level'
            return
        if 'text' not in kwargs:
            self.data = 'Missing parameter: text'
            return
        self.data = kwargs['text']
        if kwargs['level'].upper() == 'INFO':
            logger.info(self.data)
            return
        if kwargs['level'].upper() == 'WARN':
            logger.warn(self.data)
            return
        if kwargs['level'].upper() == 'ERROR':
            logger.error(self.data)
            return
        if kwargs['level'].upper() == 'DEBUG':
            logger.debug(self.data)
            return
        self.data = 'Invalid level: %s' % kwargs['level']
        return

    def _getDebug(self):
        self.data = logHeader().replace('\n', '<br>')

    def _getModules(self):
        lst = ''
        for item in sys.modules:
            lst = lst + "%s: %s<br>" % (item, str(sys.modules[item]).replace('<', '').replace('>', ''))
        self.data = lst

    def _checkModules(self):
        lst = []
        for item in sys.modules:
            data = str(sys.modules[item]).replace('<', '').replace('>', '')
            for libname in ['apscheduler', 'bs4', 'deluge_client', 'feedparser', 'fuzzywuzzy', 'html5lib',
                            'httplib2', 'mobi', 'oauth2', 'pynma', 'pythontwitter', 'requests', 'simplejson',
                            'unrar', 'six', 'webencodings']:
                if libname in data and 'dist-packages' in data:
                    lst.append("%s: %s" % (item, data))
        self.data = lst

    def _clearLogs(self):
        self.data = clearLog()

    def _getIndex(self):
        self.data = self._dic_from_query(
            'SELECT * from authors order by AuthorName COLLATE NOCASE')

    def _getNoLang(self):
        q = 'SELECT BookID,BookISBN,BookName,AuthorName from books,authors where books.AuthorID = authors.AuthorID'
        q += ' and BookLang="Unknown" or BookLang="" or BookLang is NULL'
        self.data = self._dic_from_query(q)

    def _listIgnoredSeries(self):
        q = 'SELECT SeriesID,SeriesName from series where Status="Ignored"'
        self.data = self._dic_from_query(q)

    def _listIgnoredBooks(self):
        q = 'SELECT BookID,BookName from books where Status="Ignored"'
        self.data = self._dic_from_query(q)

    def _listIgnoredAuthors(self):
        q = 'SELECT AuthorID,AuthorName from authors where Status="Ignored"'
        self.data = self._dic_from_query(q)

    def _listMissingWorkpages(self):
        # first the ones with no workpage
        q = 'SELECT BookID from books where length(WorkPage) < 4'
        res = self._dic_from_query(q)
        # now the ones with an error page
        cache = os.path.join(lazylibrarian.CACHEDIR, "WorkCache")
        if os.path.isdir(cache):
            for cached_file in os.listdir(makeBytestr(cache)):
                cached_file = makeUnicode(cached_file)
                target = os.path.join(cache, cached_file)
                if os.path.isfile(target):
                    if os.path.getsize(target) < 500 and '.' in cached_file:
                        bookid = cached_file.split('.')[0]
                        res.append({"BookID": bookid})
        self.data = res

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

        self.data = {'author': author, 'books': books}

    def _getMagazines(self):
        self.data = self._dic_from_query('SELECT * from magazines order by Title COLLATE NOCASE')

    def _getAllBooks(self):
        q = 'SELECT authors.AuthorID,AuthorName,AuthorLink,BookName,BookSub,BookGenre,BookIsbn,BookPub,'
        q += 'BookRate,BookImg,BookPages,BookLink,BookID,BookDate,BookLang,BookAdded,books.Status '
        q += 'from books,authors where books.AuthorID = authors.AuthorID'
        self.data = self._dic_from_query(q)

    def _getIssues(self, **kwargs):
        if 'name' not in kwargs:
            self.data = 'Missing parameter: name'
            return
        self.id = kwargs['name']
        magazine = self._dic_from_query(
            'SELECT * from magazines WHERE Title="' + self.id + '"')
        issues = self._dic_from_query(
            'SELECT * from issues WHERE Title="' + self.id + '" order by IssueDate DESC')

        self.data = {'magazine': magazine, 'issues': issues}

    def _getIssueName(self, **kwargs):
        if 'name' not in kwargs:
            self.data = 'Missing parameter: name'
            return
        self.data = ''
        filename = os.path.basename(kwargs['name'])
        dirname = os.path.dirname(kwargs['name'])
        dic = {'.': ' ', '-': ' ', '/': ' ', '+': ' ', '_': ' ', '(': '', ')': ''}
        name_formatted = replace_all(filename, dic).strip()
        if name_formatted and name_formatted[0] == '[' and name_formatted[-1] == ']':
            name_formatted = name_formatted[1:-1]
        # remove extra spaces if they're in a row
        name_formatted = " ".join(name_formatted.split())
        name_exploded = name_formatted.split(' ')
        regex_pass, issuedate = get_issue_date(name_exploded)
        if regex_pass:
            if int(regex_pass) > 3:  # it's an issue number
                if issuedate.isdigit():
                    issuedate = issuedate.zfill(4)  # pad with leading zeros
            if dirname:
                title = os.path.basename(dirname)
                if '$Title' in lazylibrarian.CONFIG['MAG_DEST_FILE']:
                    fname = lazylibrarian.CONFIG['MAG_DEST_FILE'].replace('$IssueDate', issuedate).replace(
                            '$Title', title)
                else:
                    fname = lazylibrarian.CONFIG['MAG_DEST_FILE'].replace('$IssueDate', issuedate)
                self.data = os.path.join(dirname, fname + '.' + name_exploded[-1])
            else:
                self.data = issuedate

    def _createMagCovers(self, **kwargs):
        if 'refresh' in kwargs:
            refresh = True
        else:
            refresh = False
        if 'wait' in kwargs:
            self.data = create_covers(refresh=refresh)
        else:
            threading.Thread(target=create_covers, name='API-MAGCOVERS', args=[refresh]).start()

    def _getBook(self, **kwargs):
        if 'id' not in kwargs:
            self.data = 'Missing parameter: id'
            return
        else:
            self.id = kwargs['id']

        book = self._dic_from_query('SELECT * from books WHERE BookID="' + self.id + '"')
        self.data = {'book': book}

    def _queueBook(self, **kwargs):
        if 'id' not in kwargs:
            self.data = 'Missing parameter: id'
            return
        else:
            self.id = kwargs['id']

        myDB = database.DBConnection()
        controlValueDict = {'BookID': self.id}
        newValueDict = {'Status': 'Wanted'}
        if 'type' in kwargs and kwargs['type'] == 'AudioBook':
            newValueDict = {'AudioStatus': 'Wanted'}
        myDB.upsert("books", newValueDict, controlValueDict)

    def _unqueueBook(self, **kwargs):
        if 'id' not in kwargs:
            self.data = 'Missing parameter: id'
            return
        else:
            self.id = kwargs['id']

        myDB = database.DBConnection()
        controlValueDict = {'BookID': self.id}
        newValueDict = {'Status': 'Skipped'}
        if 'type' in kwargs and kwargs['type'] == 'AudioBook':
            newValueDict = {'AudioStatus': 'Skipped'}
        myDB.upsert("books", newValueDict, controlValueDict)

    def _addMagazine(self, **kwargs):
        if 'name' not in kwargs:
            self.data = 'Missing parameter: name'
            return
        else:
            self.id = kwargs['name']

        myDB = database.DBConnection()
        controlValueDict = {"Title": self.id}
        newValueDict = {
            "Regex": None,
            "Status": "Active",
            "MagazineAdded": today(),
            "IssueStatus": "Wanted",
            "Reject": None
        }
        myDB.upsert("magazines", newValueDict, controlValueDict)

    def _removeMagazine(self, **kwargs):
        if 'name' not in kwargs:
            self.data = 'Missing parameter: name'
            return
        else:
            self.id = kwargs['name']

        myDB = database.DBConnection()
        myDB.action('DELETE from magazines WHERE Title=?', (self.id,))
        myDB.action('DELETE from wanted WHERE BookID=?', (self.id,))
        myDB.action('DELETE from issues WHERE Title=?', (self.id,))

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

    def _ignoreAuthor(self, **kwargs):
        if 'id' not in kwargs:
            self.data = 'Missing parameter: id'
            return
        else:
            self.id = kwargs['id']

        myDB = database.DBConnection()
        controlValueDict = {'AuthorID': self.id}
        newValueDict = {'Status': 'Ignored'}
        myDB.upsert("authors", newValueDict, controlValueDict)

    def _unignoreAuthor(self, **kwargs):
        if 'id' not in kwargs:
            self.data = 'Missing parameter: id'
            return
        else:
            self.id = kwargs['id']

        myDB = database.DBConnection()
        controlValueDict = {'AuthorID': self.id}
        newValueDict = {'Status': 'Active'}
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
        refresh = False
        if 'refresh' in kwargs:
            refresh = True
        if 'name' not in kwargs:
            self.data = 'Missing parameter: name'
            return
        else:
            self.id = kwargs['name']

        try:
            addAuthorToDB(self.id, refresh=refresh)
        except Exception as e:
            self.data = "%s %s" % (type(e).__name__, str(e))

    def _forceActiveAuthorsUpdate(self, **kwargs):
        refresh = False
        if 'refresh' in kwargs:
            refresh = True
        if 'wait' in kwargs:
            self.data = aaUpdate(refresh=refresh)
        else:
            threading.Thread(target=aaUpdate, name='API-AAUPDATE', args=[refresh]).start()

    def _forceMagSearch(self, **kwargs):
        if lazylibrarian.USE_NZB() or lazylibrarian.USE_TOR() or lazylibrarian.USE_RSS() or lazylibrarian.USE_DIRECT():
            if 'wait' in kwargs:
                search_magazines(None, True)
            else:
                threading.Thread(target=search_magazines, name='API-SEARCHMAGS', args=[None, True]).start()
        else:
            self.data = 'No search methods set, check config'

    def _forceRSSSearch(self, **kwargs):
        if lazylibrarian.USE_RSS():
            if 'wait' in kwargs:
                search_rss_book()
            else:
                threading.Thread(target=search_rss_book, name='API-SEARCHRSS', args=[]).start()
        else:
            self.data = 'No rss wishlists set, check config'

    def _forceBookSearch(self, **kwargs):
        if 'type' in kwargs:
            library = kwargs['type']
        else:
            library = None
        if lazylibrarian.USE_NZB() or lazylibrarian.USE_TOR() or lazylibrarian.USE_RSS() or lazylibrarian.USE_DIRECT():
            if 'wait' in kwargs:
                search_book(library=library)
            else:
                threading.Thread(target=search_book, name='API-SEARCHBOOK', args=[None, library]).start()
        else:
            self.data = "No search methods set, check config"

    @staticmethod
    def _forceProcess(**kwargs):
        startdir = None
        if 'dir' in kwargs:
            startdir = kwargs['dir']
        iks = False
        if 'ignorekeepseeding' in kwargs:
            iks = True
        processDir(startdir=startdir, ignorekeepseeding=iks)

    @staticmethod
    def _forceLibraryScan(**kwargs):
        startdir = None
        authid = None
        remove = False
        if 'remove' in kwargs:
            remove = True
        if 'dir' in kwargs:
            startdir = kwargs['dir']
        if 'id' in kwargs:
            authid = kwargs['id']
        if 'wait' in kwargs:
            LibraryScan(startdir=startdir, library='eBook', authid=authid, remove=remove)
        else:
            threading.Thread(target=LibraryScan, name='API-LIBRARYSCAN',
                             args=[startdir, 'eBook', authid, remove]).start()

    @staticmethod
    def _forceAudioBookScan(**kwargs):
        startdir = None
        authid = None
        remove = False
        if 'remove' in kwargs:
            remove = True
        if 'dir' in kwargs:
            startdir = kwargs['dir']
        if 'id' in kwargs:
            authid = kwargs['id']
        if 'wait' in kwargs:
            LibraryScan(startdir=startdir, library='audio', authid=authid, remove=remove)
        else:
            threading.Thread(target=LibraryScan, name='API-LIBRARYSCAN',
                             args=[startdir, 'audio', authid, remove]).start()

    @staticmethod
    def _forceMagazineScan(**kwargs):
        if 'wait' in kwargs:
            magazineScan()
        else:
            threading.Thread(target=magazineScan, name='API-MAGSCAN', args=[]).start()

    def _deleteEmptySeries(self):
        self.data = deleteEmptySeries()

    def _cleanCache(self, **kwargs):
        if 'wait' in kwargs:
            self.data = cleanCache()
        else:
            threading.Thread(target=cleanCache, name='API-CLEANCACHE', args=[]).start()

    def _setWorkPages(self, **kwargs):
        if 'wait' in kwargs:
            self.data = setWorkPages()
        else:
            threading.Thread(target=setWorkPages, name='API-SETWORKPAGES', args=[]).start()

    def _setAllBookSeries(self, **kwargs):
        if 'wait' in kwargs:
            self.data = setAllBookSeries()
        else:
            threading.Thread(target=setAllBookSeries, name='API-SETALLBOOKSERIES', args=[]).start()

    def _setAllBookAuthors(self, **kwargs):
        if 'wait' in kwargs:
            self.data = setAllBookAuthors()
        else:
            threading.Thread(target=setAllBookAuthors, name='API-SETALLBOOKAUTHORS', args=[]).start()

    def _getBookCovers(self, **kwargs):
        if 'wait' in kwargs:
            self.data = getBookCovers()
        else:
            threading.Thread(target=getBookCovers, name='API-GETBOOKCOVERS', args=[]).start()

    def _getAuthorImages(self, **kwargs):
        if 'wait' in kwargs:
            self.data = getAuthorImages()
        else:
            threading.Thread(target=getAuthorImages, name='API-GETAUTHORIMAGES', args=[]).start()

    def _getVersion(self):
        self.data = {
            'install_type': lazylibrarian.CONFIG['INSTALL_TYPE'],
            'current_version': lazylibrarian.CONFIG['CURRENT_VERSION'],
            'latest_version': lazylibrarian.CONFIG['LATEST_VERSION'],
            'commits_behind': lazylibrarian.CONFIG['COMMITS_BEHIND'],
        }

    @staticmethod
    def _shutdown():
        lazylibrarian.SIGNAL = 'shutdown'

    @staticmethod
    def _restart():
        lazylibrarian.SIGNAL = 'restart'

    @staticmethod
    def _update():
        lazylibrarian.SIGNAL = 'update'

    def _findAuthor(self, **kwargs):
        if 'name' not in kwargs:
            self.data = 'Missing parameter: name'
            return

        authorname = formatAuthorName(kwargs['name'])
        if lazylibrarian.CONFIG['BOOK_API'] == "GoogleBooks":
            GB = GoogleBooks(authorname)
            myqueue = queue.Queue()
            search_api = threading.Thread(target=GB.find_results, name='API-GBRESULTS', args=[authorname, myqueue])
            search_api.start()
        else:  # lazylibrarian.CONFIG['BOOK_API'] == "GoodReads":
            GR = GoodReads(authorname)
            myqueue = queue.Queue()
            search_api = threading.Thread(target=GR.find_results, name='API-GRRESULTS', args=[authorname, myqueue])
            search_api.start()

        search_api.join()
        self.data = myqueue.get()

    def _findBook(self, **kwargs):
        if 'name' not in kwargs:
            self.data = 'Missing parameter: name'
            return

        if lazylibrarian.CONFIG['BOOK_API'] == "GoogleBooks":
            GB = GoogleBooks(kwargs['name'])
            myqueue = queue.Queue()
            search_api = threading.Thread(target=GB.find_results, name='API-GBRESULTS', args=[kwargs['name'], myqueue])
            search_api.start()
        else:  # lazylibrarian.CONFIG['BOOK_API'] == "GoodReads":
            GR = GoodReads(kwargs['name'])
            myqueue = queue.Queue()
            search_api = threading.Thread(target=GR.find_results, name='API-GRRESULTS', args=[kwargs['name'], myqueue])
            search_api.start()

        search_api.join()
        self.data = myqueue.get()

    def _addBook(self, **kwargs):
        if 'id' not in kwargs:
            self.data = 'Missing parameter: id'
            return

        if lazylibrarian.CONFIG['BOOK_API'] == "GoogleBooks":
            GB = GoogleBooks(kwargs['id'])
            threading.Thread(target=GB.find_book, name='API-GBRESULTS', args=[kwargs['id']]).start()
        else:  # lazylibrarian.CONFIG['BOOK_API'] == "GoodReads":
            GR = GoodReads(kwargs['id'])
            threading.Thread(target=GR.find_book, name='API-GRRESULTS', args=[kwargs['id']]).start()

    def _moveBook(self, **kwargs):
        if 'id' not in kwargs:
            self.data = 'Missing parameter: id'
            return
        if 'toid' not in kwargs:
            self.data = 'Missing parameter: toid'
            return
        try:
            myDB = database.DBConnection()
            authordata = myDB.match('SELECT AuthorName from authors WHERE AuthorID=?', (kwargs['toid'],))
            if not authordata:
                self.data = "No destination author [%s] in the database" % kwargs['toid']
            else:
                bookdata = myDB.match('SELECT AuthorID, BookName from books where BookID=?', (kwargs['id'],))
                if not bookdata:
                    self.data = "No bookid [%s] in the database" % kwargs['id']
                else:
                    controlValueDict = {'BookID': kwargs['id']}
                    newValueDict = {'AuthorID': kwargs['toid']}
                    myDB.upsert("books", newValueDict, controlValueDict)
                    update_totals(bookdata[0])  # we moved from here
                    update_totals(kwargs['toid'])  # to here
                    self.data = "Moved book [%s] to [%s]" % (bookdata[1], authordata[0])
            logger.debug(self.data)
        except Exception as e:
            self.data = "%s %s" % (type(e).__name__, str(e))

    def _moveBooks(self, **kwargs):
        if 'fromname' not in kwargs:
            self.data = 'Missing parameter: fromname'
            return
        if 'toname' not in kwargs:
            self.data = 'Missing parameter: toname'
            return
        try:
            myDB = database.DBConnection()
            q = 'SELECT bookid,books.authorid from books,authors where books.AuthorID = authors.AuthorID'
            q += ' and authorname=?'
            fromhere = myDB.select(q, (kwargs['fromname'],))

            tohere = myDB.match('SELECT authorid from authors where authorname=?', (kwargs['toname'],))
            if not len(fromhere):
                self.data = "No books by [%s] in the database" % kwargs['fromname']
            else:
                if not tohere:
                    self.data = "No destination author [%s] in the database" % kwargs['toname']
                else:
                    myDB.action('UPDATE books SET authorid=?, where authorname=?', (tohere[0], kwargs['fromname']))
                    self.data = "Moved %s books from %s to %s" % (len(fromhere), kwargs['fromname'], kwargs['toname'])
                    update_totals(fromhere[0][1])  # we moved from here
                    update_totals(tohere[0])  # to here

            logger.debug(self.data)
        except Exception as e:
            self.data = "%s %s" % (type(e).__name__, str(e))

    def _addAuthor(self, **kwargs):
        if 'name' not in kwargs:
            self.data = 'Missing parameter: name'
            return
        else:
            self.id = kwargs['name']
        try:
            self.data = addAuthorNameToDB(author=self.id, refresh=False)
        except Exception as e:
            self.data = "%s %s" % (type(e).__name__, str(e))

    def _addAuthorID(self, **kwargs):
        if 'id' not in kwargs:
            self.data = 'Missing parameter: id'
            return
        else:
            self.id = kwargs['id']
        try:
            self.data = addAuthorToDB(refresh=False, authorid=self.id)
        except Exception as e:
            self.data = "%s %s" % (type(e).__name__, str(e))

    def _grFollowAll(self):
        myDB = database.DBConnection()
        cmd = 'SELECT AuthorName,AuthorID,GRfollow FROM authors where '
        cmd += 'Status="Active" or Status="Wanted" or Status="Loading"'
        authors = myDB.select(cmd)
        count = 0
        for author in authors:
            followid = check_int(author['GRfollow'], 0)
            if followid > 0:
                logger.debug('%s is already followed' % author['AuthorName'])
            elif author['GRfollow'] == "0":
                logger.debug('%s is manually unfollowed' % author['AuthorName'])
            else:
                res = grfollow(author['AuthorID'], True)
                if res.startswith('Unable'):
                    logger.warn(res)
                try:
                    followid = res.split("followid=")[1]
                    logger.debug('%s marked followed' % author['AuthorName'])
                    count += 1
                except IndexError:
                    followid = ''
                myDB.action('UPDATE authors SET GRfollow=? WHERE AuthorID=?', (followid, author['AuthorID']))
        self.data = "Added follow to %s author%s" % (count, plural(count))

    def _grSync(self, **kwargs):
        if 'shelf' not in kwargs:
            self.data = 'Missing parameter: shelf'
            return
        if 'status' not in kwargs:
            self.data = 'Missing parameter: status'
            return
        try:
            self.data = grsync(kwargs['status'], kwargs['shelf'])
        except Exception as e:
            self.data = "%s %s" % (type(e).__name__, str(e))

    def _grFollow(self, **kwargs):
        if 'id' not in kwargs:
            self.data = 'Missing parameter: id'
            return
        try:
            self.data = grfollow(authorid=kwargs['id'], follow=True)
        except Exception as e:
            self.data = "%s %s" % (type(e).__name__, str(e))

    def _grUnfollow(self, **kwargs):
        if 'id' not in kwargs:
            self.data = 'Missing parameter: id'
            return
        try:
            self.data = grfollow(authorid=kwargs['id'], follow=False)
        except Exception as e:
            self.data = "%s %s" % (type(e).__name__, str(e))

    def _searchItem(self, **kwargs):
        if 'item' not in kwargs:
            self.data = 'Missing parameter: item'
            return
        else:
            self.data = searchItem(kwargs['item'])

    def _searchBook(self, **kwargs):
        if 'id' not in kwargs:
            self.data = 'Missing parameter: id'
            return

        books = [{"bookid": kwargs['id']}]
        if 'type' in kwargs:
            library = kwargs['type']
        else:
            library = None

        if lazylibrarian.USE_NZB() or lazylibrarian.USE_TOR() or lazylibrarian.USE_RSS() or lazylibrarian.USE_DIRECT():
            if 'wait' in kwargs:
                search_book(books=books, library=library)
            else:
                threading.Thread(target=search_book, name='API-SEARCHBOOK', args=[books, library]).start()
        else:
            self.data = "No search methods set, check config"

    def _removeAuthor(self, **kwargs):
        if 'id' not in kwargs:
            self.data = 'Missing parameter: id'
            return
        else:
            self.id = kwargs['id']

        myDB = database.DBConnection()
        authorsearch = myDB.select('SELECT AuthorName from authors WHERE AuthorID=?', (kwargs['id'],))
        if len(authorsearch):  # to stop error if try to remove an author while they are still loading
            AuthorName = authorsearch[0]['AuthorName']
            logger.debug("Removing all references to author: %s" % AuthorName)
            myDB.action('DELETE from authors WHERE AuthorID=?', (kwargs['id'],))
            myDB.action('DELETE from books WHERE AuthorID=?', (kwargs['id'],))

    def _writeCFG(self, **kwargs):
        if 'name' not in kwargs:
            self.data = 'Missing parameter: name'
            return
        if 'value' not in kwargs:
            self.data = 'Missing parameter: value'
            return
        if 'group' not in kwargs:
            self.data = 'Missing parameter: group'
            return
        try:
            self.data = '["%s"]' % lazylibrarian.CFG.get(kwargs['group'], kwargs['name'])
            lazylibrarian.CFG.set(kwargs['group'], kwargs['name'], kwargs['value'])
            if PY2:
                fmode = 'wb'
            else:
                fmode = 'w'
            with open(lazylibrarian.CONFIGFILE, fmode) as configfile:
                lazylibrarian.CFG.write(configfile)
            lazylibrarian.config_read(reloaded=True)
        except Exception as e:
            self.data = 'Unable to update CFG entry for %s: %s, %s' % (kwargs['group'], kwargs['name'], str(e))

    def _readCFG(self, **kwargs):
        if 'name' not in kwargs:
            self.data = 'Missing parameter: name'
            return
        if 'group' not in kwargs:
            self.data = 'Missing parameter: group'
            return
        try:
            self.data = '["%s"]' % lazylibrarian.CFG.get(kwargs['group'], kwargs['name'])
        except configparser.Error:
            self.data = 'No CFG entry for %s: %s' % (kwargs['group'], kwargs['name'])

    @staticmethod
    def _loadCFG():
        lazylibrarian.config_read(reloaded=True)

    def _getSeriesAuthors(self, **kwargs):
        if 'id' not in kwargs:
            self.data = 'Missing parameter: id'
        else:
            self.id = kwargs['id']
            count = getSeriesAuthors(self.id)
            self.data = "Added %s" % count

    def _getSeriesMembers(self, **kwargs):
        if 'id' not in kwargs:
            self.data = 'Missing parameter: id'
            return
        else:
            self.id = kwargs['id']
        self.data = getSeriesMembers(self.id)

    def _getBookAuthors(self, **kwargs):
        if 'id' not in kwargs:
            self.data = 'Missing parameter: id'
            return
        else:
            self.id = kwargs['id']
        self.data = getBookAuthors(self.id)

    def _getWorkSeries(self, **kwargs):
        if 'id' not in kwargs:
            self.data = 'Missing parameter: id'
            return
        else:
            self.id = kwargs['id']
        self.data = getWorkSeries(self.id)

    def _getWorkPage(self, **kwargs):
        if 'id' not in kwargs:
            self.data = 'Missing parameter: id'
            return
        else:
            self.id = kwargs['id']
        self.data = getWorkPage(self.id)

    def _getBookCover(self, **kwargs):
        if 'id' not in kwargs:
            self.data = 'Missing parameter: id'
            return
        else:
            self.id = kwargs['id']
        if 'src' in kwargs:
            self.data = getBookCover(self.id, kwargs['src'])
        else:
            self.data = getBookCover(self.id)

    def _getAuthorImage(self, **kwargs):
        if 'id' not in kwargs:
            self.data = 'Missing parameter: id'
            return
        else:
            self.id = kwargs['id']
        self.data = getAuthorImage(self.id)

    def _lock(self, table, itemid, state):
        myDB = database.DBConnection()
        dbentry = myDB.match('SELECT %sID from %ss WHERE %sID=%s' % (table, table, table, itemid))
        if dbentry:
            myDB.action('UPDATE %ss SET Manual="%s" WHERE %sID=%s' % (table, state, table, itemid))
        else:
            self.data = "%sID %s not found" % (table, itemid)

    def _setAuthorLock(self, **kwargs):
        if 'id' not in kwargs:
            self.data = 'Missing parameter: id'
            return
        else:
            self._lock("author", kwargs['id'], "1")

    def _setAuthorUnlock(self, **kwargs):
        if 'id' not in kwargs:
            self.data = 'Missing parameter: id'
            return
        else:
            self._lock("author", kwargs['id'], "0")

    def _setAuthorImage(self, **kwargs):
        if 'id' not in kwargs:
            self.data = 'Missing parameter: id'
            return
        else:
            self.id = kwargs['id']
        if 'img' not in kwargs:
            self.data = 'Missing parameter: img'
            return
        else:
            self._setimage("author", kwargs['id'], kwargs['img'])

    def _setBookImage(self, **kwargs):
        if 'id' not in kwargs:
            self.data = 'Missing parameter: id'
            return
        else:
            self.id = kwargs['id']
        if 'img' not in kwargs:
            self.data = 'Missing parameter: img'
            return
        else:
            self._setimage("book", kwargs['id'], kwargs['img'])

    def _setimage(self, table, itemid, img):
        msg = "%s Image [%s] rejected" % (table, img)
        # Cache file image
        if os.path.isfile(img):
            extn = os.path.splitext(img)[1].lower()
            if extn and extn in ['.jpg', '.jpeg', '.png']:
                destfile = os.path.join(lazylibrarian.CACHEDIR, table, itemid + '.jpg')
                try:
                    shutil.copy(img, destfile)
                    setperm(destfile)
                    msg = ''
                except Exception as why:
                    msg += " Failed to copy file: %s %s" % (type(why).__name__, str(why))
            else:
                msg += " invalid extension"

        if img.startswith('http'):
            # cache image from url
            extn = os.path.splitext(img)[1].lower()
            if extn and extn in ['.jpg', '.jpeg', '.png']:
                cachedimg, success = cache_img(table, itemid, img)
                if success:
                    msg = ''
                else:
                    msg += " Failed to cache file"
            else:
                msg += " invalid extension"
        elif msg:
            msg += " Not found"

        if msg:
            self.data = msg
            return

        myDB = database.DBConnection()
        dbentry = myDB.match('SELECT %sID from %ss WHERE %sID=%s' % (table, table, table, itemid))
        if dbentry:
            myDB.action('UPDATE %ss SET %sImg="%s" WHERE %sID=%s' %
                        (table, table, 'cache' + os.sep + itemid + '.jpg', table, itemid))
        else:
            self.data = "%sID %s not found" % (table, itemid)

    def _setBookLock(self, **kwargs):
        if 'id' not in kwargs:
            self.data = 'Missing parameter: id'
            return
        else:
            self._lock("book", kwargs['id'], "1")

    def _setBookUnlock(self, **kwargs):
        if 'id' not in kwargs:
            self.data = 'Missing parameter: id'
            return
        else:
            self._lock("book", kwargs['id'], "0")

    @staticmethod
    def _restartJobs():
        restartJobs(start='Restart')

    @staticmethod
    def _checkRunningJobs():
        checkRunningJobs()

    def _showJobs(self):
        self.data = showJobs()

    def _importAlternate(self, **kwargs):
        if 'dir' in kwargs:
            usedir = kwargs['dir']
        else:
            usedir = lazylibrarian.CONFIG['ALTERNATE_DIR']
        if 'wait' in kwargs:
            self.data = processAlternate(usedir)
        else:
            threading.Thread(target=processAlternate, name='API-IMPORTALT', args=[usedir]).start()

    def _importCSVwishlist(self, **kwargs):
        if 'dir' in kwargs:
            usedir = kwargs['dir']
        else:
            usedir = lazylibrarian.CONFIG['ALTERNATE_DIR']
        if 'wait' in kwargs:
            self.data = import_CSV(usedir)
        else:
            threading.Thread(target=import_CSV, name='API-IMPORTCSV', args=[usedir]).start()

    def _exportCSVwishlist(self, **kwargs):
        if 'dir' in kwargs:
            usedir = kwargs['dir']
        else:
            usedir = lazylibrarian.CONFIG['ALTERNATE_DIR']
        if 'wait' in kwargs:
            self.data = export_CSV(usedir)
        else:
            threading.Thread(target=export_CSV, name='API-EXPORTCSV', args=[usedir]).start()
