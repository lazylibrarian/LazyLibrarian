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

import Queue
import hashlib
import os
import random
import threading
import urllib
import datetime
from operator import itemgetter
from shutil import copyfile, rmtree

import cherrypy
import lazylibrarian
import lib.simplejson as simplejson
from cherrypy.lib.static import serve_file
from lazylibrarian import logger, database, notifiers, versioncheck, magazinescan, \
    qbittorrent, utorrent, rtorrent, transmission, sabnzbd, nzbget, deluge, synology
from lazylibrarian.common import showJobs, restartJobs, clearLog, scheduleJob, checkRunningJobs, setperm, dbUpdate
from lazylibrarian.csvfile import import_CSV, export_CSV
from lazylibrarian.formatter import plural, now, today, check_int, replace_all, safe_unicode, unaccented
from lazylibrarian.gb import GoogleBooks
from lazylibrarian.gr import GoodReads
from lazylibrarian.importer import addAuthorToDB, update_totals
from lazylibrarian.librarysync import LibraryScan
from lazylibrarian.postprocess import processAlternate, processDir
from lazylibrarian.searchmag import search_magazines
from lazylibrarian.searchnzb import search_nzb_book, NZBDownloadMethod
from lazylibrarian.searchrss import search_rss_book
from lazylibrarian.searchtorrents import search_tor_book, TORDownloadMethod
from lazylibrarian.cache import cache_img
from lazylibrarian.notifiers import notify_snatch
from lazylibrarian.manualbook import searchItem
from lazylibrarian.bookwork import getWorkSeries, setSeries
from lib.deluge_client import DelugeRPCClient
from mako import exceptions
from mako.lookup import TemplateLookup


def serve_template(templatename, **kwargs):
    interface_dir = os.path.join(
        str(lazylibrarian.PROG_DIR),
        'data/interfaces/')
    template_dir = os.path.join(str(interface_dir), lazylibrarian.CONFIG['HTTP_LOOK'])
    if not os.path.isdir(template_dir):
        logger.error("Unable to locate template [%s], reverting to default" % template_dir)
        lazylibrarian.CONFIG['HTTP_LOOK'] = 'default'
        template_dir = os.path.join(str(interface_dir), lazylibrarian.CONFIG['HTTP_LOOK'])

    _hplookup = TemplateLookup(directories=[template_dir])

    try:
        template = _hplookup.get_template(templatename)
        return template.render(**kwargs)
    except Exception:
        return exceptions.html_error_template().render()


class WebInterface(object):
    @cherrypy.expose
    def index(self):
        raise cherrypy.HTTPRedirect("home")

    @cherrypy.expose
    def home(self):
        if lazylibrarian.UPDATE_MSG:
            message = "Upgrading database, please wait"
            return serve_template(templatename="dbupdate.html", title="Database Upgrade", message=message, timer=5)
        else:
            myDB = database.DBConnection()
            authors = myDB.select(
                'SELECT * from authors where Status != "Ignored" order by AuthorName COLLATE NOCASE')
            return serve_template(templatename="index.html", title="Authors", authors=authors)

    @staticmethod
    def label_thread(name=None):
        threadname = threading.currentThread().name
        if "Thread-" in threadname:
            if name:
                threading.currentThread().name = name
            else:
                threading.currentThread().name = "WEBSERVER"

    # SERIES ############################################################
    @cherrypy.expose
    def series(self, AuthorID=None):
        myDB = database.DBConnection()
        title = "Series"
        cmd = 'SELECT SeriesID,series.AuthorID,SeriesName,series.Status,AuthorName from series,authors'
        cmd += ' where authors.AuthorID=series.AuthorID'
        if AuthorID:
            match = myDB.match('SELECT AuthorName from authors WHERE AuthorID=%s' % AuthorID)
            if match:
                title = "%s Series" % match['AuthorName']
            cmd += ' and series.AuthorID=' + AuthorID
        cmd += ' order by AuthorName,SeriesName'
        series = myDB.select(cmd)
        return serve_template(templatename="series.html", title=title, authorid=AuthorID, series=series)

    @cherrypy.expose
    def seriesMembers(self, seriesid):
        myDB = database.DBConnection()
        cmd = 'SELECT SeriesName,SeriesID,AuthorName,authors.AuthorID from series,authors'
        cmd += ' where authors.AuthorID=series.AuthorID and SeriesID=%s' % seriesid
        series = myDB.match(cmd)
        cmd = 'SELECT member.BookID,BookName,SeriesNum,BookImg,books.Status from member,series,books'
        cmd += ' where series.SeriesID=member.SeriesID and books.BookID=member.BookID'
        cmd += ' and series.SeriesID=%s order by SeriesName' % seriesid
        members = myDB.select(cmd)
        return serve_template(templatename="members.html", title=series['AuthorName'] + ": " + series['SeriesName'],
                                members=members, series=series)

    @cherrypy.expose
    def markMembers(self, action=None, **args):
        return self.markBooks(self, action=action, **args)

    @cherrypy.expose
    def markSeries(self, action=None, **args):
        self.label_thread()
        myDB = database.DBConnection()
        if action:
            for seriesid in args:
                # ouch dirty workaround...
                if not seriesid == 'book_table_length':
                    if action in ["Wanted", "Active", "Skipped"]:
                        match = myDB.match('SELECT SeriesName from series WHERE SeriesID = "%s"' % seriesid)
                        if match:
                            myDB.upsert("series", {'Status': action}, {'SeriesID': seriesid})
                            logger.debug(u'Status set to "%s" for "%s"' % (action, match['SeriesName']))
            if "redirect" in args:
                if not args['redirect'] == 'None':
                    raise cherrypy.HTTPRedirect("series?AuthorID=%s" % args['redirect'])
            raise cherrypy.HTTPRedirect("series")

    # CONFIG ############################################################

    @cherrypy.expose
    def config(self):
        self.label_thread()
        http_look_dir = os.path.join(lazylibrarian.PROG_DIR, 'data' + os.sep + 'interfaces')
        http_look_list = [name for name in os.listdir(http_look_dir)
                          if os.path.isdir(os.path.join(http_look_dir, name))]
        status_list = ['Skipped', 'Wanted', 'Have', 'Ignored']

        myDB = database.DBConnection()
        mags_list = []

        magazines = myDB.select('SELECT Title,Reject,Regex from magazines ORDER by Title COLLATE NOCASE')

        if magazines:
            for mag in magazines:
                title = mag['Title']
                regex = mag['Regex']
                if regex is None:
                    regex = ""
                reject = mag['Reject']
                if reject is None:
                    reject = ""
                mags_list.append({
                    'Title': title,
                    'Reject': reject,
                    'Regex': regex
                })

        # Don't pass the whole config, no need to pass the
        # lazylibrarian.globals
        config = {
            "http_look_list": http_look_list,
            "status_list": status_list,
            "magazines_list": mags_list
        }
        return serve_template(templatename="config.html", title="Settings", config=config)

    @cherrypy.expose
    def configUpdate(self, **kwargs):
        # print len(kwargs)
        # for arg in kwargs:
        #    print arg
        self.label_thread()

        # first the non-config options
        if 'current_tab' in kwargs:
            lazylibrarian.CURRENT_TAB = kwargs['current_tab']

        # now the config file entries
        for key in lazylibrarian.CONFIG_DEFINITIONS.keys():
            item_type, section, default = lazylibrarian.CONFIG_DEFINITIONS[key]
            if key.lower() in kwargs:
                value = kwargs[key.lower()]
                if item_type == 'bool':
                    if not value or value == 'False' or value == '0':
                        value = 0
                    else:
                        value = 1
                elif item_type == 'int':
                    value = check_int(value, default)
                lazylibrarian.CONFIG[key] = value
            else:
                # no key returned for empty tickboxes...
                if item_type == 'bool':
                    lazylibrarian.CONFIG[key] = 0
                else:
                    # or for strings not available in config html page
                    if key not in ['LOGFILES', 'LOGSIZE', 'NAME_POSTFIX', 'GIT_REPO', 'GIT_USER', 'GIT_BRANCH',
                                    'LATEST_VERSION', 'CURRENT_VERSION', 'COMMITS_BEHIND', 'INSTALL_TYPE']:
                        # or for an empty string
                        lazylibrarian.CONFIG[key] = ''


        myDB = database.DBConnection()
        magazines = myDB.select('SELECT Title,Reject,Regex from magazines ORDER by upper(Title)')

        if magazines:
            for mag in magazines:
                title = mag['Title']
                reject = mag['Reject']
                regex = mag['Regex']
                # seems kwargs parameters are passed as latin-1, can't see how to
                # configure it, so we need to correct it on accented magazine names
                # eg "Elle Quebec" where we might have e-acute
                # otherwise the comparison fails
                new_reject = kwargs.get('reject_list[%s]' % title.encode('latin-1'), None)
                if not new_reject == reject:
                    controlValueDict = {'Title': title}
                    newValueDict = {'Reject': new_reject}
                    myDB.upsert("magazines", newValueDict, controlValueDict)
                new_regex = kwargs.get('regex[%s]' % title.encode('latin-1'), None)
                if not new_regex == regex:
                    controlValueDict = {'Title': title}
                    newValueDict = {'Regex': new_regex}
                    myDB.upsert("magazines", newValueDict, controlValueDict)

        count = 0
        while count < len(lazylibrarian.NEWZNAB_PROV):
            lazylibrarian.NEWZNAB_PROV[count]['ENABLED'] = bool(kwargs.get(
                'newznab[%i][enabled]' % count, False))
            lazylibrarian.NEWZNAB_PROV[count]['HOST'] = kwargs.get(
                'newznab[%i][host]' % count, '')
            lazylibrarian.NEWZNAB_PROV[count]['API'] = kwargs.get(
                'newznab[%i][api]' % count, '')
            lazylibrarian.NEWZNAB_PROV[count]['GENERALSEARCH'] = kwargs.get(
                'newznab[%i][generalsearch]' % count, '')
            lazylibrarian.NEWZNAB_PROV[count]['BOOKSEARCH'] = kwargs.get(
                'newznab[%i][booksearch]' % count, '')
            lazylibrarian.NEWZNAB_PROV[count]['MAGSEARCH'] = kwargs.get(
                'newznab[%i][magsearch]' % count, '')
            lazylibrarian.NEWZNAB_PROV[count]['BOOKCAT'] = kwargs.get(
                'newznab[%i][bookcat]' % count, '')
            lazylibrarian.NEWZNAB_PROV[count]['MAGCAT'] = kwargs.get(
                'newznab[%i][magcat]' % count, '')
            lazylibrarian.NEWZNAB_PROV[count]['EXTENDED'] = kwargs.get(
                'newznab[%i][extended]' % count, '')
            lazylibrarian.NEWZNAB_PROV[count]['UPDATED'] = kwargs.get(
                'newznab[%i][updated]' % count, '')
            lazylibrarian.NEWZNAB_PROV[count]['MANUAL'] = bool(kwargs.get(
                'newznab[%i][manual]' % count, False))
            count += 1

        count = 0
        while count < len(lazylibrarian.TORZNAB_PROV):
            lazylibrarian.TORZNAB_PROV[count]['ENABLED'] = bool(kwargs.get(
                'torznab[%i][enabled]' % count, False))
            lazylibrarian.TORZNAB_PROV[count]['HOST'] = kwargs.get(
                'torznab[%i][host]' % count, '')
            lazylibrarian.TORZNAB_PROV[count]['API'] = kwargs.get(
                'torznab[%i][api]' % count, '')
            lazylibrarian.TORZNAB_PROV[count]['GENERALSEARCH'] = kwargs.get(
                'torznab[%i][generalsearch]' % count, '')
            lazylibrarian.TORZNAB_PROV[count]['BOOKSEARCH'] = kwargs.get(
                'torznab[%i][booksearch]' % count, '')
            lazylibrarian.TORZNAB_PROV[count]['MAGSEARCH'] = kwargs.get(
                'torznab[%i][magsearch]' % count, '')
            lazylibrarian.TORZNAB_PROV[count]['BOOKCAT'] = kwargs.get(
                'torznab[%i][bookcat]' % count, '')
            lazylibrarian.TORZNAB_PROV[count]['MAGCAT'] = kwargs.get(
                'torznab[%i][magcat]' % count, '')
            lazylibrarian.TORZNAB_PROV[count]['EXTENDED'] = kwargs.get(
                'torznab[%i][extended]' % count, '')
            lazylibrarian.TORZNAB_PROV[count]['UPDATED'] = kwargs.get(
                'torznab[%i][updated]' % count, '')
            lazylibrarian.TORZNAB_PROV[count]['MANUAL'] = bool(kwargs.get(
                'torznab[%i][manual]' % count, False))
            count += 1

        count = 0
        while count < len(lazylibrarian.RSS_PROV):
            lazylibrarian.RSS_PROV[count]['ENABLED'] = bool(
                kwargs.get('rss[%i][enabled]' % count, False))
            lazylibrarian.RSS_PROV[count]['HOST'] = kwargs.get('rss[%i][host]' % count, '')
            # lazylibrarian.RSS_PROV[count]['USER'] = kwargs.get('rss[%i][user]' % count, '')
            # lazylibrarian.RSS_PROV[count]['PASS'] = kwargs.get('rss[%i][pass]' % count, '')
            count += 1

        lazylibrarian.config_write()
        checkRunningJobs()

        logger.info('Config file [%s] has been updated' % lazylibrarian.CONFIGFILE)

        raise cherrypy.HTTPRedirect("config")

    # SEARCH ############################################################

    @cherrypy.expose
    def search(self, name):
        if name is None or not name:
            raise cherrypy.HTTPRedirect("home")

        myDB = database.DBConnection()
        if lazylibrarian.CONFIG['BOOK_API'] == "GoogleBooks":
            GB = GoogleBooks(name)
            queue = Queue.Queue()
            search_api = threading.Thread(
                target=GB.find_results, name='GB-RESULTS', args=[name, queue])
            search_api.start()
        else:  # lazylibrarian.CONFIG['BOOK_API'] == "GoodReads":
            queue = Queue.Queue()
            GR = GoodReads(name)
            search_api = threading.Thread(
                target=GR.find_results, name='GR-RESULTS', args=[name, queue])
            search_api.start()

        search_api.join()
        searchresults = queue.get()

        authorsearch = myDB.select("SELECT AuthorName from authors")
        authorlist = []
        for item in authorsearch:
            authorlist.append(item['AuthorName'])

        booksearch = myDB.select("SELECT Status,BookID from books")
        booklist = []
        for item in booksearch:
            booklist.append(item['BookID'])

        # need a url safe version of authorname for passing to
        # searchresults.html as it might be a new author with no authorid yet
        resultlist = []
        for result in searchresults:
            result['safeauthorname'] = urllib.quote_plus(
                result['authorname'].encode(lazylibrarian.SYS_ENCODING))
            resultlist.append(result)

        sortedlist_final = sorted(
            searchresults, key=itemgetter('highest_fuzz', 'num_reviews'), reverse=True)
        return serve_template(templatename="searchresults.html", title='Search Results: "' +
                              name + '"', searchresults=sortedlist_final,
                              authorlist=authorlist,
                              booklist=booklist, booksearch=booksearch)

    # AUTHOR ############################################################

    @cherrypy.expose
    def authorPage(self, AuthorID, BookLang=None, Ignored=False):
        myDB = database.DBConnection()

        if Ignored:
            languages = myDB.select("SELECT DISTINCT BookLang from books WHERE AuthorID = '%s' \
                                    AND Status ='Ignored'" % AuthorID)
            if BookLang:
                querybooks = "SELECT * from books WHERE AuthorID = '%s' AND BookLang = '%s' \
                              AND Status ='Ignored' order by BookDate DESC, BookRate DESC" % (
                    AuthorID, BookLang)
            else:
                querybooks = "SELECT * from books WHERE AuthorID = '%s' and Status ='Ignored' \
                              order by BookDate DESC, BookRate DESC" % AuthorID
        else:
            languages = myDB.select(
                "SELECT DISTINCT BookLang from books WHERE AuthorID = '%s' AND Status !='Ignored'" % AuthorID)
            if BookLang:
                querybooks = "SELECT * from books WHERE AuthorID = '%s' AND BookLang = '%s' \
                              AND Status !='Ignored' order by BookDate DESC, BookRate DESC" % (
                    AuthorID, BookLang)
            else:
                querybooks = "SELECT * from books WHERE AuthorID = '%s' and Status !='Ignored' \
                              order by BookDate DESC, BookRate DESC" % AuthorID

        queryauthors = "SELECT * from authors WHERE AuthorID = '%s'" % AuthorID

        author = myDB.match(queryauthors)
        books = myDB.select(querybooks)
        if not author:
            raise cherrypy.HTTPRedirect("home")
        authorname = author['AuthorName'].encode(lazylibrarian.SYS_ENCODING)
        return serve_template(
            templatename="author.html", title=urllib.quote_plus(authorname),
            author=author, books=books, languages=languages)

    @cherrypy.expose
    def pauseAuthor(self, AuthorID):
        self.label_thread()

        myDB = database.DBConnection()
        authorsearch = myDB.match(
            'SELECT AuthorName from authors WHERE AuthorID="%s"' % AuthorID)
        if authorsearch:
            AuthorName = authorsearch['AuthorName']
            logger.info(u"Pausing author: %s" % AuthorName)

            controlValueDict = {'AuthorID': AuthorID}
            newValueDict = {'Status': 'Paused'}
            myDB.upsert("authors", newValueDict, controlValueDict)
            logger.debug(
                u'AuthorID [%s]-[%s] Paused - redirecting to Author home page' % (AuthorID, AuthorName))
            raise cherrypy.HTTPRedirect("authorPage?AuthorID=%s" % AuthorID)
        else:
            logger.debug('pauseAuthor Invalid authorid [%s]' % AuthorID)
            raise cherrypy.HTTPRedirect("home")

    @cherrypy.expose
    def resumeAuthor(self, AuthorID):
        self.label_thread()

        myDB = database.DBConnection()
        authorsearch = myDB.match(
            'SELECT AuthorName from authors WHERE AuthorID="%s"' % AuthorID)
        if authorsearch:
            AuthorName = authorsearch['AuthorName']
            logger.info(u"Resuming author: %s" % AuthorName)

            controlValueDict = {'AuthorID': AuthorID}
            newValueDict = {'Status': 'Active'}
            myDB.upsert("authors", newValueDict, controlValueDict)
            logger.debug(
                u'AuthorID [%s]-[%s] Restarted - redirecting to Author home page' % (AuthorID, AuthorName))
            raise cherrypy.HTTPRedirect("authorPage?AuthorID=%s" % AuthorID)
        else:
            logger.debug('resumeAuthor Invalid authorid [%s]' % AuthorID)
            raise cherrypy.HTTPRedirect("home")

    @cherrypy.expose
    def ignoreAuthor(self, AuthorID):
        self.label_thread()

        myDB = database.DBConnection()
        authorsearch = myDB.match(
            'SELECT AuthorName from authors WHERE AuthorID="%s"' % AuthorID)
        if authorsearch:
            AuthorName = authorsearch['AuthorName']
            logger.info(u"Ignoring author: %s" % AuthorName)

            controlValueDict = {'AuthorID': AuthorID}
            newValueDict = {'Status': 'Ignored'}
            myDB.upsert("authors", newValueDict, controlValueDict)
            logger.debug(
                u'AuthorID [%s]-[%s] Ignored - redirecting to home page' % (AuthorID, AuthorName))
        else:
            logger.debug('ignoreAuthor Invalid authorid [%s]' % AuthorID)
        raise cherrypy.HTTPRedirect("home")

    @cherrypy.expose
    def removeAuthor(self, AuthorID):
        self.label_thread()

        myDB = database.DBConnection()
        authorsearch = myDB.match(
            'SELECT AuthorName from authors WHERE AuthorID="%s"' % AuthorID)
        if authorsearch:  # to stop error if try to remove an author while they are still loading
            AuthorName = authorsearch['AuthorName']
            logger.info(u"Removing all references to author: %s" % AuthorName)
            myDB.action('DELETE from authors WHERE AuthorID="%s"' % AuthorID)
            myDB.action('DELETE from books WHERE AuthorID="%s"' % AuthorID)
        raise cherrypy.HTTPRedirect("home")

    @cherrypy.expose
    def refreshAuthor(self, AuthorID):
        self.label_thread()

        myDB = database.DBConnection()
        authorsearch = myDB.match('SELECT AuthorName from authors WHERE AuthorID="%s"' % AuthorID)
        if authorsearch:  # to stop error if try to refresh an author while they are still loading
            threading.Thread(target=addAuthorToDB, name='REFRESHAUTHOR', args=[None, True, AuthorID]).start()
            raise cherrypy.HTTPRedirect("authorPage?AuthorID=%s" % AuthorID)
        else:
            logger.debug('refreshAuthor Invalid authorid [%s]' % AuthorID)
            raise cherrypy.HTTPRedirect("home")

    @cherrypy.expose
    def libraryScanAuthor(self, AuthorID):
        self.label_thread()

        myDB = database.DBConnection()
        authorsearch = myDB.match('SELECT AuthorName from authors WHERE AuthorID="%s"' % AuthorID)
        if authorsearch:  # to stop error if try to refresh an author while they are still loading
            AuthorName = authorsearch['AuthorName']
            authordir = safe_unicode(os.path.join(lazylibrarian.DIRECTORY('Destination'), AuthorName))
            if not os.path.isdir(authordir):
                # books might not be in exact same authorname folder
                # eg Calibre puts books into folder "Eric van Lustbader", but
                # goodreads told lazylibrarian he's "Eric Van Lustbader", note the capital 'V'
                cmd = 'SELECT BookFile from books,authors where books.AuthorID = authors.AuthorID'
                cmd += '  and AuthorName="%s" and BookFile <> ""' % AuthorName
                anybook = myDB.match(cmd)
                if anybook:
                    authordir = safe_unicode(os.path.dirname(os.path.dirname(anybook['BookFile'])))
            if os.path.isdir(authordir):
                try:
                    threading.Thread(target=LibraryScan, name='SCANAUTHOR', args=[authordir]).start()
                except Exception as e:
                    logger.error(u'Unable to complete the scan: %s' % str(e))
            else:
                # maybe we don't have any of their books
                logger.warn(u'Unable to find author directory: %s' % authordir)
            raise cherrypy.HTTPRedirect("authorPage?AuthorID=%s" % AuthorID)
        else:
            logger.debug('scanAuthor Invalid authorid [%s]' % AuthorID)
            raise cherrypy.HTTPRedirect("home")

    @cherrypy.expose
    def addAuthor(self, AuthorName):
        threading.Thread(target=addAuthorToDB, name='ADDAUTHOR', args=[AuthorName, False]).start()
        raise cherrypy.HTTPRedirect("home")

    @cherrypy.expose
    def addAuthorID(self, AuthorID, AuthorName):
        threading.Thread(target=addAuthorToDB, name='ADDAUTHOR', args=[AuthorName, False, AuthorID]).start()
        raise cherrypy.HTTPRedirect("home")

    # BOOKS #############################################################
    LANGFILTER = ''

    @cherrypy.expose
    def booksearch(self, bookid=None, title="", author=""):
        self.label_thread()
        searchterm = '%s %s' % (author, title)
        searchterm.strip()
        results = searchItem(searchterm, bookid)
        return serve_template(templatename="manualsearch.html", title='Search Results: "' +
                              searchterm + '"', bookid=bookid, results=results)


    @cherrypy.expose
    def countProviders(self):
        cherrypy.response.headers['Cache-Control'] = "max-age=0,no-cache,no-store"
        count = lazylibrarian.USE_NZB() + lazylibrarian.USE_TOR() + lazylibrarian.USE_RSS()
        return "Searching %s providers, please wait..." % count


    @cherrypy.expose
    def snatchBook(self, bookid=None, mode=None, provider=None, url=None):
        self.label_thread()
        logger.debug("snatch bookid %s mode=%s from %s url=[%s]" % (bookid, mode, provider, url))
        myDB = database.DBConnection()
        bookdata = myDB.match('SELECT AuthorID, BookName from books WHERE BookID="%s"' % bookid)
        if bookdata:
            AuthorID = bookdata["AuthorID"]
            url = urllib.unquote_plus(url)
            url = url.replace(' ', '+')
            bookname = '%s LL.(%s)' % (bookdata["BookName"], bookid)
            if mode in ["torznab", "torrent", "magnet"]:
                snatch = TORDownloadMethod(bookid, bookname, url)
            else:
                snatch = NZBDownloadMethod(bookid, bookname, url)
            if snatch:
                logger.info('Downloading %s from %s' % (bookdata["BookName"], provider))
                notify_snatch("%s from %s at %s" % (unaccented(bookdata["BookName"]), provider, now()))
                scheduleJob(action='Start', target='processDir')
            raise cherrypy.HTTPRedirect("authorPage?AuthorID=%s" % AuthorID)
        else:
            logger.debug('snatchBook Invalid bookid [%s]' % bookid)
            raise cherrypy.HTTPRedirect("home")

    @cherrypy.expose
    def books(self, BookLang=None):
        global LANGFILTER
        myDB = database.DBConnection()
        languages = myDB.select('SELECT DISTINCT BookLang from books WHERE STATUS !="Skipped" AND STATUS !="Ignored"')
        LANGFILTER = BookLang
        return serve_template(templatename="books.html", title='Books', books=[], languages=languages)

    # noinspection PyUnusedLocal
    @cherrypy.expose
    def getBooks(self, iDisplayStart=0, iDisplayLength=100, iSortCol_0=0, sSortDir_0="desc", sSearch="", **kwargs):
        # kwargs is used by datatables to pass params
        #for arg in kwargs:
        #    print arg, kwargs[arg]

        global LANGFILTER
        myDB = database.DBConnection()
        iDisplayStart = int(iDisplayStart)
        iDisplayLength = int(iDisplayLength)
        lazylibrarian.CONFIG['DISPLAYLENGTH'] = iDisplayLength

        cmd = 'SELECT bookimg,authorname,bookname,bookrate,bookdate,books.status,bookid,'
        cmd += 'booksub,booklink,workpage,books.authorid from books,authors where books.AuthorID = authors.AuthorID'

        if kwargs['source'] == "Manage":
            cmd += ' and books.STATUS="%s"' % kwargs['whichStatus']
        elif kwargs['source'] == "Books":
            cmd += ' and books.STATUS !="Skipped" AND books.STATUS !="Ignored"'
            # for "books" need to check and filter on BookLang if set
            if LANGFILTER is not None and len(LANGFILTER):
                cmd += ' and BOOKLANG="' + LANGFILTER + '"'
        elif kwargs['source'] == "Author":
            cmd += ' and AuthorID=%s' % kwargs['AuthorID']

        rowlist = myDB.select(cmd)
        # turn the sqlite rowlist into a list of lists
        d = []
        filtered = []
        if len(rowlist):
            # the masterlist to be filled with the row data
            for i, row in enumerate(rowlist):  # iterate through the sqlite3.Row objects
                l = []  # for each Row use a separate list
                for column in row:
                    l.append(column)
                d.append(l)  # add the rowlist to the masterlist

            if sSearch:
                filtered = filter(lambda x: sSearch in str(x), d)
            else:
                filtered = d

            sortcolumn = int(iSortCol_0)
            sortcolumn -= 1  # indexed from 0
            filtered.sort(key=lambda x: x[sortcolumn], reverse=sSortDir_0 == "desc")

            if iDisplayLength < 0:  # display = all
                rows = filtered
            else:
                rows = filtered[iDisplayStart:(iDisplayStart + iDisplayLength)]

            # now add html to the ones we want to display
            d = []  # the masterlist to be filled with the html data
            for row in rows:
                cmd = 'SELECT SeriesName,SeriesNum from series,member '
                cmd += 'WHERE series.SeriesID = member.SeriesID and member.BookID=%s' % row[6]
                whichseries = myDB.select(cmd)
                series = ''
                for item in whichseries:
                    newseries = "%s %s" % (item['SeriesName'], item['SeriesNum'])
                    newseries.strip()
                    if series and newseries:
                        series += '<br>'
                    series += newseries

                l = []  # for each Row use a separate list
                bookrate = float(row[3])
                if bookrate < 0.5:
                    starimg = '0-stars.png'
                elif 0.5 <= bookrate < 1.5:
                    starimg = '1-stars.png'
                elif 1.5 <= bookrate < 2.5:
                    starimg = '2-stars.png'
                elif 2.5 <= bookrate < 3.5:
                    starimg = '3-stars.png'
                elif 3.5 <= bookrate < 4.5:
                    starimg = '4-stars.png'
                elif bookrate >= 4.5:
                    starimg = '5-stars.png'
                else:
                    starimg = '0-stars.png'

                worklink = ''

                if lazylibrarian.CONFIG['HTTP_LOOK'] == 'bookstrap':
                    if row[9]:  # is there a workpage link
                        if len(row[9]) > 4:
                            worklink = '<td><a href="' + \
                                       row[9] + '" target="_new"><small><i>LibraryThing</i></small></a></td>'

                    editpage = '<a href="editBook?bookid=' + row[6] + '" target="_new"><small><i>Manual</i></a>'

                    sitelink = ''
                    if 'goodreads' in row[8]:
                        sitelink = '<td><a href="' + \
                                   row[8] + '" target="_new"><small><i>GoodReads</i></small></a></td>'
                    if 'google' in row[8]:
                        sitelink = '<td><a href="' + \
                                   row[8] + '" target="_new"><small><i>GoogleBooks</i></small></a></td>'

                    l.append(
                        '<td class="select"><input type="checkbox" name="%s" class="checkbox" /></td>' % row[6])
                    lref = '<td class="bookart text-center"><a href="%s' % row[0]
                    lref += '" target="_blank" rel="noreferrer"><img src="%s' % row[0]
                    lref += '" alt="Cover" class="bookcover-sm img-responsive"></a></td>'
                    l.append(lref)

                    # Don't show author column on author page, we know which author!
                    if not kwargs['source'] == "Author":
                        l.append(
                            '<td class="authorname"><a href="authorPage?AuthorID=%s">%s</a></td>' % (row[10], row[1]))
                    if row[7]:  # is there a sub-title
                        title = '<td class="bookname">%s<br><small><i>%s</i></small></td>' % (row[2], row[7])
                    else:
                        title = '<td class="bookname">%s</td>' % row[2]
                    l.append(title + '<br>' + sitelink + '&nbsp;' + worklink + '&nbsp;' + editpage)

                    # is the book part of a series
                    l.append('<td class="series">%s</td>' % series)

                    l.append('<td class="stars text-center"><img src="images/' + starimg + '" alt="Rating"></td>')

                    l.append('<td class="date text-center">%s</td>' % row[4])

                    # Do not show status column in MANAGE page as we are only showing one status
                    if not kwargs['source'] == "Manage":
                        if row[5] == 'Open':
                            btn = '<td class="status text-center"><a class="button green btn btn-xs btn-warning"'
                            btn += ' href="openBook?bookid=%s' % row[6]
                            btn += '" target="_self"><i class="fa fa-book"></i>%s</a></td>' % row[5]
                        elif row[5] == 'Wanted':
                            btn = '<td class="status text-center"><p><a class="a btn btn-xs btn-danger">%s' % row[5]
                            btn += '</a></p><p><a class="b btn btn-xs btn-success" '
                            btn += 'href="searchForBook?bookid=%s' % row[6]
                            btn += '" target="_self"><i class="fa fa-search"></i> Search</a></p></td>'
                        elif row[5] == 'Snatched' or row[5] == 'Have':
                            btn = '<td class="status text-center"><a class="button btn btn-xs btn-info">%s' % row[5]
                            btn += '</a></td>'
                        else:
                            btn = '<td class="status text-center"><a class="button btn btn-xs btn-default grey">%s' % row[5]
                            btn += '</a></td>'
                        l.append(btn)

                else:  # lazylibrarian.CONFIG['HTTP_LOOK'] == 'default':
                    if row[9]:  # is there a workpage link
                        if len(row[9]) > 4:
                            worklink = '<td><a href="' + \
                                       row[9] + '" target="_new"><i class="smalltext">LibraryThing</i></a></td>'

                    editpage = '<a href="editBook?bookid=' + row[6] + \
                                '" target="_new"><i class="smalltext">Manual</i></a>'

                    sitelink = ''
                    if 'goodreads' in row[8]:
                        sitelink = '<td><a href="' + \
                                   row[8] + '" target="_new"><i class="smalltext">GoodReads</i></a></td>'
                    if 'google' in row[8]:
                        sitelink = '<td><a href="' + \
                                   row[8] + '" target="_new"><i class="smalltext">GoogleBooks</i></a></td>'

                    l.append(
                        '<td id="select"><input type="checkbox" name="%s" class="checkbox" /></td>' % row[6])
                    lref = '<td id="bookart"><a href="%s" target="_new"><img src="%s' % (row[0], row[0])
                    lref += '" height="75" width="50"></a></td>'
                    l.append(lref)
                    # Don't show author column on author page, we know which author!
                    if not kwargs['source'] == "Author":
                        l.append(
                            '<td id="authorname"><a href="authorPage?AuthorID=%s">%s</a></td>' % (row[10], row[1]))
                    if row[7]:  # is there a sub-title
                        title = '<td id="bookname">%s<br><i class="smalltext">%s</i></td>' % (row[2], row[7])
                    else:
                        title = '<td id="bookname">%s</td>' % row[2]
                    l.append(title + '<br>' + sitelink + '&nbsp;' + worklink + '&nbsp;' + editpage)

                    # is the book part of a series
                    l.append('<td id="series">%s</td>' % series)

                    l.append('<td id="stars"><img src="images/' + starimg + '" width="50" height="10"></td>')

                    l.append('<td id="date">%s</td>' % row[4])

                    # Do not show status column in MANAGE page
                    if not kwargs['source'] == "Manage":
                        if row[5] == 'Open':
                            btn = '<td id="status"><a class="button green" href="openBook?bookid=%s' % row[6]
                            btn += '" target="_self">Open</a></td>'
                        elif row[5] == 'Wanted':
                            btn = '<td id="status"><a class="button red" href="searchForBook?bookid=%s' % row[6]
                            btn += '" target="_self"><span class="a">Wanted</span>'
                            btn += '<span class="b">Search</span></a></td>'
                        elif row[5] == 'Snatched' or row[5] == 'Have':
                            btn = '<td id="status"><a class="button">%s</a></td>' % row[5]
                        else:
                            btn = '<td id="status"><a class="button grey">%s</a></td>' % row[5]
                        l.append(btn)

                d.append(l)  # add the rowlist to the masterlist

        mydict = {'iTotalDisplayRecords': len(filtered),
                  'iTotalRecords': len(rowlist),
                  'aaData': d,
                  }
        s = simplejson.dumps(mydict)
        # print ("Getbooks returning %s to %s" % (iDisplayStart, iDisplayStart
        # + iDisplayLength))
        return s

    @cherrypy.expose
    def addBook(self, bookid=None):
        myDB = database.DBConnection()
        AuthorID = ""
        booksearch = myDB.select('SELECT AuthorID from books WHERE BookID="%s"' % bookid)
        if len(booksearch):
            myDB.upsert("books", {'Status': 'Wanted'}, {'BookID': bookid})
            for book in booksearch:
                AuthorID = book['AuthorID']
                update_totals(AuthorID)
        else:
            if lazylibrarian.CONFIG['BOOK_API'] == "GoogleBooks":
                GB = GoogleBooks(bookid)
                queue = Queue.Queue()
                find_book = threading.Thread(
                    target=GB.find_book, name='GB-BOOK', args=[bookid, queue])
                find_book.start()
            else:  # lazylibrarian.CONFIG['BOOK_API'] == "GoodReads":
                queue = Queue.Queue()
                GR = GoodReads(bookid)
                find_book = threading.Thread(
                    target=GR.find_book, name='GR-BOOK', args=[bookid, queue])
                find_book.start()
            if len(bookid) == 0:
                raise cherrypy.HTTPRedirect("config")

            find_book.join()

        if lazylibrarian.CONFIG['IMP_AUTOSEARCH']:
            books = [{"bookid": bookid}]
            self.startBookSearch(books)

        if AuthorID:
            raise cherrypy.HTTPRedirect("authorPage?AuthorID=%s" % AuthorID)
        else:
            raise cherrypy.HTTPRedirect("books")

    @cherrypy.expose
    def startBookSearch(self, books=None):
        if books:
            if lazylibrarian.USE_RSS():
                threading.Thread(target=search_rss_book, name='SEARCHRSS', args=[books]).start()
            if lazylibrarian.USE_NZB():
                threading.Thread(target=search_nzb_book, name='SEARCHNZB', args=[books]).start()
            if lazylibrarian.USE_TOR():
                threading.Thread(target=search_tor_book, name='SEARCHTOR', args=[books]).start()
            if lazylibrarian.USE_RSS() or lazylibrarian.USE_NZB() or lazylibrarian.USE_TOR():
                logger.debug(u"Searching for book with id: " + books[0]["bookid"])
            else:
                logger.warn(u"Not searching for book, no search methods set, check config.")
        else:
            logger.debug(u"BookSearch called with no books")

    @cherrypy.expose
    def searchForBook(self, bookid=None):
        myDB = database.DBConnection()
        AuthorID = ''
        bookdata = myDB.match('SELECT AuthorID from books WHERE BookID="%s"' % bookid)
        if bookdata:
            AuthorID = bookdata["AuthorID"]

            # start searchthreads
            books = [{"bookid": bookid}]
            self.startBookSearch(books)

        if AuthorID:
            raise cherrypy.HTTPRedirect("authorPage?AuthorID=%s" % AuthorID)
        else:
            raise cherrypy.HTTPRedirect("books")

    @cherrypy.expose
    def openBook(self, bookid=None):
        self.label_thread()

        myDB = database.DBConnection()
        cmd = 'SELECT BookFile,AuthorName,BookName from books,authors WHERE BookID="%s"' % bookid
        cmd += ' and books.AuthorID = authors.AuthorID'
        bookdata = myDB.match(cmd)
        if bookdata:
            bookfile = bookdata["BookFile"]
            if bookfile and os.path.isfile(bookfile):
                logger.info(u'Opening file %s' % bookfile)
                return serve_file(bookfile, "application/x-download", "attachment")
            else:
                authorName = bookdata["AuthorName"]
                bookName = bookdata["BookName"]
                logger.info(u'Missing book %s,%s' % (authorName, bookName))

    @cherrypy.expose
    def editAuthor(self, authorid=None):

        myDB = database.DBConnection()

        data = myDB.match('SELECT * from authors WHERE AuthorID="%s"' % authorid)
        if data:
            return serve_template(templatename="editauthor.html", title="Edit Author", config=data)
        else:
            logger.info(u'Missing author %s:' % authorid)

    @cherrypy.expose
    def authorUpdate(self, authorid='', authorname='', authorborn='', authordeath='', authorimg='', manual='0'):
        self.label_thread()

        myDB = database.DBConnection()
        if authorid:
            authdata = myDB.match('SELECT * from authors WHERE AuthorID="%s"' % authorid)
            if authdata:
                edited = ""
                moved = False
                if authorborn == 'None':
                    authorborn = ''
                if authordeath == 'None':
                    authordeath = ''
                if authorimg == 'None':
                    authorimg = ''
                manual = bool(check_int(manual, 0))

                if not (authdata["AuthorName"] == authorname):
                    edited += "Name "
                if not (authdata["AuthorBorn"] == authorborn):
                    edited += "Born "
                if not (authdata["AuthorDeath"] == authordeath):
                    edited += "Died "
                if not (authdata["AuthorImg"] == authorimg):
                    edited += "Image "
                if not (bool(check_int(authdata["Manual"], 0)) == manual):
                    edited += "Manual "

                if not (authdata["AuthorName"] == authorname):
                    match = myDB.match('SELECT AuthorName from authors where AuthorName="%s"' % authorname)
                    if match:
                        logger.debug("Unable to rename, new author name %s already exists" % authorname)
                        authorname = authdata["AuthorName"]
                    else:
                        moved = True

                if edited:
                    # Check dates in format yyyy/mm/dd, or unchanged if fails datecheck
                    ab = authorborn
                    authorborn = authdata["AuthorBorn"]  # assume fail, leave unchanged
                    if ab:
                        rejected = True
                        if len(ab) == 10:
                            try:
                                _ = datetime.date(int(ab[:4]), int(ab[5:7]), int(ab[8:]))
                                authorborn = ab
                                rejected = False
                            except ValueError:
                                authorborn = authdata["AuthorBorn"]
                        if rejected:
                            logger.warn("Author Born date [%s] rejected" % ab)
                            edited = edited.replace('Born ', '')

                    ab = authordeath
                    authordeath = authdata["AuthorDeath"]  # assume fail, leave unchanged
                    if ab:
                        rejected = True
                        if len(ab) == 10:
                            try:
                                _ = datetime.date(int(ab[:4]), int(ab[5:7]), int(ab[8:]))
                                authordeath = ab
                                rejected = False
                            except ValueError:
                                authordeath = authdata["AuthorDeath"]
                        if rejected:
                            logger.warn("Author Died date [%s] rejected" % ab)
                            edited = edited.replace('Died ', '')

                    if not authorimg:
                        authorimg = authdata["AuthorImg"]
                    else:
                        rejected = True
                        # Cache file image
                        if os.path.isfile(authorimg):
                            extn = os.path.splitext(authorimg)[1].lower()
                            if extn and extn in ['.jpg', '.jpeg', '.png']:
                                destfile = os.path.join(lazylibrarian.CACHEDIR, authorid + '.jpg')
                                try:
                                    copyfile(authorimg, destfile)
                                    setperm(destfile)
                                    authorimg = 'cache' + os.sep + authorid + '.jpg'
                                    rejected = False
                                except Exception as why:
                                    logger.debug("Failed to copy file %s, %s" % (authorimg, str(why)))

                        if authorimg.startswith('http'):
                            # cache image from url
                            extn = os.path.splitext(authorimg)[1].lower()
                            if extn and extn in ['.jpg', '.jpeg', '.png']:
                                authorimg, success = cache_img("author", authorid, authorimg)
                                if success:
                                    rejected = False

                        if rejected:
                            logger.warn("Author Image [%s] rejected" % authorimg)
                            authorimg = authdata["AuthorImg"]
                            edited = edited.replace('Image ', '')

                    controlValueDict = {'AuthorID': authorid}
                    newValueDict = {
                        'AuthorName': authorname,
                        'AuthorBorn': authorborn,
                        'AuthorDeath': authordeath,
                        'AuthorImg': authorimg,
                        'Manual': bool(manual)
                    }
                    myDB.upsert("authors", newValueDict, controlValueDict)
                    logger.info('Updated [ %s] for %s' % (edited, authorname))

                    if moved:
                        # move all books by this author to new name unless book is set to manual
                        myDB.action('UPDATE books SET AuthorName="%s" where AuthorID=%s and Manual is not "1"' %
                                    (authorname, authorid))
                else:
                    logger.debug('Author [%s] has not been changed' % authorname)

            raise cherrypy.HTTPRedirect("authorPage?AuthorID=%s" % authorid)
        else:
            raise cherrypy.HTTPRedirect("authors")

    @cherrypy.expose
    def editBook(self, bookid=None):

        myDB = database.DBConnection()
        authors = myDB.select(
            "SELECT AuthorName from authors WHERE Status !='Ignored' ORDER by AuthorName COLLATE NOCASE")
        cmd = 'SELECT BookName,BookSub,BookGenre,BookLang,Manual,AuthorName,books.AuthorID from books,authors '
        cmd += 'WHERE books.AuthorID = authors.AuthorID and BookID="%s"' % bookid
        bookdata = myDB.match(cmd)
        cmd ='SELECT SeriesName, SeriesNum from member,series '
        cmd += 'where series.SeriesID=member.SeriesID and BookID=%s' % bookid
        seriesdict = myDB.select(cmd)
        if bookdata:
            return serve_template(templatename="editbook.html", title="Edit Book",
                                    config=bookdata, seriesdict=seriesdict, authors=authors)
        else:
            logger.info(u'Missing book %s' % bookid)

    @cherrypy.expose
    def bookUpdate(self, bookname='', bookid='', booksub='', bookgenre='', booklang='',
                   series='', manual='0', authorname='', **kwargs):
        myDB = database.DBConnection()
        if bookid:
            cmd = 'SELECT BookName,BookSub,BookGenre,BookLang,Manual,AuthorName,books.AuthorID from books,authors '
            cmd += 'WHERE books.AuthorID = authors.AuthorID and BookID="%s"' % bookid
            bookdata = myDB.match(cmd)
            if bookdata:
                edited = ''
                moved = False
                if bookgenre == 'None':
                    bookgenre = ''
                manual = bool(check_int(manual, 0))
                if not (bookdata["BookName"] == bookname):
                    edited += "Title "
                if not (bookdata["BookSub"] == booksub):
                    edited += "Subtitle "
                if not (bookdata["BookGenre"] == bookgenre):
                    edited += "Genre "
                if not (bookdata["BookLang"] == booklang):
                    edited += "Language "
                if not (bool(check_int(bookdata["Manual"], 0)) == manual):
                    edited += "Manual "
                if not (bookdata["AuthorName"] == authorname):
                    moved = True

                if edited:
                    controlValueDict = {'BookID': bookid}
                    newValueDict = {
                        'BookName': bookname,
                        'BookSub': booksub,
                        'BookGenre': bookgenre,
                        'BookLang': booklang,
                        'Manual': bool(manual)
                    }
                    myDB.upsert("books", newValueDict, controlValueDict)

                cmd ='SELECT SeriesName, SeriesNum from member,series '
                cmd += 'where series.SeriesID=member.SeriesID and BookID=%s' % bookid
                old_series = myDB.select(cmd)
                old_dict = {}
                new_dict = {}
                dict_counter = 0
                while "series[%s][name]" % dict_counter in kwargs:
                    new_dict[kwargs["series[%s][name]" % dict_counter]] = kwargs["series[%s][number]" % dict_counter]
                    dict_counter += 1
                if 'series[new][name]' in kwargs and 'series[new][number]' in kwargs:
                    if kwargs['series[new][name]']:
                        new_dict[kwargs['series[new][name]']] = kwargs['series[new][number]']
                for item in old_series:
                    old_dict[item['SeriesName']] = item['SeriesNum']

                series_changed= False
                for item in old_dict:
                    if not item in new_dict:
                        series_changed = True
                for item in new_dict:
                    if not item in old_dict:
                        series_changed = True
                    else:
                        if new_dict[item] != old_dict[item]:
                            series_changed = True
                if series_changed:
                    setSeries(new_dict, bookid)
                    edited += "Series "

                if edited:
                    logger.info('Updated [ %s] for %s' % (edited, bookname))
                else:
                    logger.debug('Book [%s] has not been changed' % bookname)

                if moved:
                    authordata = myDB.match(
                        'SELECT AuthorID,AuthorLink from authors WHERE AuthorName="%s"' % authorname)
                    if authordata:
                        controlValueDict = {'BookID': bookid}
                        newValueDict = {
                            'AuthorName': authorname,
                            'AuthorID': authordata['AuthorID'],
                            'AuthorLink': authordata['AuthorLink']
                        }
                        myDB.upsert("books", newValueDict, controlValueDict)
                        update_totals(bookdata["AuthorID"])  # we moved from here
                        update_totals(authordata['AuthorID'])  # to here

                    logger.info('Book [%s] has been moved' % bookname)
                else:
                    logger.debug('Book [%s] has not been moved' % bookname)
                #if edited or moved:
                raise cherrypy.HTTPRedirect("editBook?BookID=%s" % bookid)

        raise cherrypy.HTTPRedirect("books")

    @cherrypy.expose
    def markBooks(self, AuthorID=None, seriesid=None, action=None, redirect=None, **args):
        self.label_thread()

        myDB = database.DBConnection()
        if not redirect:
            redirect = "books"
        authorcheck = []
        if action:
            for bookid in args:
                # ouch dirty workaround...
                if not bookid == 'book_table_length':
                    if action in ["Wanted", "Have", "Ignored", "Skipped"]:
                        title = myDB.match('SELECT BookName from books WHERE BookID = "%s"' % bookid)
                        if title:
                            bookname = title['BookName']
                            myDB.upsert("books", {'Status': action}, {'BookID': bookid})
                            logger.debug(u'Status set to "%s" for "%s"' % (action, bookname))
                    if action in ["Remove", "Delete"]:
                        bookdata = myDB.match(
                            'SELECT AuthorID,Bookname,BookFile from books WHERE BookID = "%s"' %
                            bookid)
                        if bookdata:
                            AuthorID = bookdata['AuthorID']
                            bookname = bookdata['BookName']
                            bookfile = bookdata['BookFile']
                            if action == "Delete":
                                if bookfile and os.path.isfile(bookfile):
                                    try:
                                        rmtree(os.path.dirname(bookfile), ignore_errors=True)
                                        logger.info(u'Book %s deleted from disc' % bookname)
                                    except Exception as e:
                                        logger.debug('rmtree failed on %s, %s' % (bookfile, str(e)))

                            authorcheck = myDB.match('SELECT AuthorID from authors WHERE AuthorID = "%s"' % AuthorID)
                            if authorcheck:
                                myDB.upsert("books", {"Status": "Ignored"}, {"BookID": bookid})
                                logger.debug(u'Status set to Ignored for "%s"' % bookname)
                            else:
                                logger.info(u'Removed "%s" from database' % bookname)

        if redirect == "author" or len(authorcheck):
            update_totals(AuthorID)

        # start searchthreads
        if action == 'Wanted':
            books = []
            for bookid in args:
                # ouch dirty workaround...
                if not bookid == 'book_table_length':
                    books.append({"bookid": bookid})

            if lazylibrarian.USE_RSS():
                threading.Thread(target=search_rss_book, name='SEARCHRSS', args=[books]).start()
            if lazylibrarian.USE_NZB():
                threading.Thread(target=search_nzb_book, name='SEARCHNZB', args=[books]).start()
            if lazylibrarian.USE_TOR():
                threading.Thread(target=search_tor_book, name='SEARCHTOR', args=[books]).start()

        if redirect == "author":
            raise cherrypy.HTTPRedirect("authorPage?AuthorID=%s" % AuthorID)
        elif redirect == "books":
            raise cherrypy.HTTPRedirect("books")
        elif redirect == "members":
            raise cherrypy.HTTPRedirect("seriesMembers?seriesid=%s" % seriesid)
        else:
            raise cherrypy.HTTPRedirect("manage")

    # MAGAZINES #########################################################

    @cherrypy.expose
    def magazines(self):
        myDB = database.DBConnection()

        magazines = myDB.select('SELECT * from magazines ORDER by Title')
        mags = []
        covercount = 0
        if magazines:
            for mag in magazines:
                title = mag['Title']
                count = myDB.match(
                    'SELECT COUNT(Title) as counter FROM issues WHERE Title="%s"' % title)
                if count:
                    issues = count['counter']
                else:
                    issues = 0
                magimg = mag['LatestCover']
                if not magimg or not os.path.isfile(magimg):
                    magimg = 'images/nocover.jpg'
                else:
                    myhash = hashlib.md5(magimg).hexdigest()
                    hashname = os.path.join(lazylibrarian.CACHEDIR, myhash + ".jpg")
                    copyfile(magimg, hashname)
                    setperm(hashname)
                    magimg = 'cache/' + myhash + '.jpg'
                    covercount += 1

                this_mag = dict(mag)
                this_mag['Count'] = issues
                this_mag['Cover'] = magimg
                this_mag['safetitle'] = urllib.quote_plus(mag['Title'].encode(lazylibrarian.SYS_ENCODING))
                mags.append(this_mag)

        if lazylibrarian.CONFIG['IMP_CONVERT'] == 'None':  # special flag to say "no covers required"
            covercount = 0

        return serve_template(templatename="magazines.html", title="Magazines", magazines=mags, covercount=covercount)

    @cherrypy.expose
    def issuePage(self, title):
        myDB = database.DBConnection()

        issues = myDB.select('SELECT * from issues WHERE Title="%s" order by IssueDate DESC' % title)

        if not len(issues):
            raise cherrypy.HTTPRedirect("magazines")
        else:
            mod_issues = []
            covercount = 0
            for issue in issues:
                magfile = issue['IssueFile']
                extn = os.path.splitext(magfile)[1]
                if extn:
                    magimg = magfile.replace(extn, '.jpg')
                    if not magimg or not os.path.isfile(magimg):
                        magimg = 'images/nocover.jpg'
                    else:
                        myhash = hashlib.md5(magimg).hexdigest()
                        hashname = os.path.join(lazylibrarian.CACHEDIR, myhash + ".jpg")
                        copyfile(magimg, hashname)
                        setperm(hashname)
                        magimg = 'cache/' + myhash + '.jpg'
                        covercount += 1
                else:
                    logger.debug('No extension found on %s' % magfile)
                    magimg = 'images/nocover.jpg'

                this_issue = dict(issue)
                this_issue['Cover'] = magimg
                mod_issues.append(this_issue)
            logger.debug("Found %s cover%s" % (covercount, plural(covercount)))

        if lazylibrarian.CONFIG['IMP_CONVERT'] == 'None':  # special flag to say "no covers required"
            covercount = 0

        return serve_template(templatename="issues.html", title=title, issues=mod_issues, covercount=covercount)


    @cherrypy.expose
    def pastIssues(self, whichStatus=None):
        if whichStatus is None:
            whichStatus = "Skipped"
        return serve_template(
            templatename="manageissues.html", title="Manage Past Issues", issues=[], whichStatus=whichStatus)

    # noinspection PyUnusedLocal
    @cherrypy.expose
    def getPastIssues(self, iDisplayStart=0, iDisplayLength=100, iSortCol_0=0, sSortDir_0="desc", sSearch="", **kwargs):
        # kwargs is used by datatables to pass params
        myDB = database.DBConnection()
        iDisplayStart = int(iDisplayStart)
        iDisplayLength = int(iDisplayLength)
        lazylibrarian.CONFIG['DISPLAYLENGTH'] = iDisplayLength
        # need to filter on whichStatus
        rowlist = myDB.select(
            'SELECT NZBurl, NZBtitle, NZBdate, Auxinfo, NZBprov from pastissues WHERE Status=' + kwargs['whichStatus'])
        d = []
        filtered = []
        if len(rowlist):
            # the masterlist to be filled with the row data
            for i, row in enumerate(rowlist):  # iterate through the sqlite3.Row objects
                l = []  # for each Row use a separate list
                for column in row:
                    l.append(column)
                d.append(l)  # add the rowlist to the masterlist

            if sSearch:
                filtered = filter(lambda x: sSearch in str(x), d)
            else:
                filtered = d

            sortcolumn = int(iSortCol_0)
            filtered.sort(key=lambda x: x[sortcolumn], reverse=sSortDir_0 == "desc")

            if iDisplayLength < 0:  # display = all
                rows = filtered
            else:
                rows = filtered[iDisplayStart:(iDisplayStart + iDisplayLength)]

            # now add html to the ones we want to display
            d = []  # the masterlist to be filled with the html data
            for row in rows:
                l = ['<td id="select"><input type="checkbox" name="%s" class="checkbox" /></td>' % row[0],
                     '<td id="magtitle">%s</td>' % row[1],
                     '<td id="lastacquired">%s</td>' % row[2],
                     '<td id="issuedate">%s</td>' % row[3],
                     '<td id="provider">%s</td>' % row[4]]  # for each Row use a separate list
                d.append(l)  # add the rowlist to the masterlist

        mydict = {'iTotalDisplayRecords': len(filtered),
                  'iTotalRecords': len(rowlist),
                  'aaData': d,
                  }
        s = simplejson.dumps(mydict)
        return s

    @cherrypy.expose
    def openMag(self, bookid=None):
        self.label_thread()

        bookid = urllib.unquote_plus(bookid)
        myDB = database.DBConnection()
        # we may want to open an issue with a hashed bookid
        mag_data = myDB.match('SELECT * from issues WHERE IssueID="%s"' % bookid)
        if mag_data:
            IssueFile = mag_data["IssueFile"]
            if IssueFile and os.path.isfile(IssueFile):
                logger.info(u'Opening file %s' % IssueFile)
                return serve_file(IssueFile, "application/x-download", "attachment")

        # or we may just have a title to find magazine in issues table
        mag_data = myDB.select('SELECT * from issues WHERE Title="%s"' % bookid)
        if len(mag_data) <= 0:  # no issues!
            raise cherrypy.HTTPRedirect("magazines")
        elif len(mag_data) == 1 and lazylibrarian.CONFIG['MAG_SINGLE']:  # we only have one issue, get it
            IssueDate = mag_data[0]["IssueDate"]
            IssueFile = mag_data[0]["IssueFile"]
            logger.info(u'Opening %s - %s' % (bookid, IssueDate))
            return serve_file(IssueFile, "application/x-download", "attachment")
        else:  # multiple issues, show a list
            logger.debug(u"%s has %s issue%s" % (bookid, len(mag_data), plural(len(mag_data))))
            raise cherrypy.HTTPRedirect(
                "issuePage?title=%s" %
                urllib.quote_plus(bookid.encode(lazylibrarian.SYS_ENCODING)))

    @cherrypy.expose
    def markPastIssues(self, action=None, **args):
        self.label_thread()

        myDB = database.DBConnection()
        maglist = []
        for nzburl in args:
            if isinstance(nzburl, str):
                nzburl = nzburl.decode(lazylibrarian.SYS_ENCODING)
            # ouch dirty workaround...
            if not nzburl == 'book_table_length':
                # some NZBurl have &amp;  some have just & so need to try both forms
                if '&' in nzburl and '&amp;' not in nzburl:
                    nzburl2 = nzburl.replace('&', '&amp;')
                elif '&amp;' in nzburl:
                    nzburl2 = nzburl.replace('&amp;', '&')
                else:
                    nzburl2 = ''

                if not nzburl2:
                    title = myDB.select('SELECT * from pastissues WHERE NZBurl="%s"' % nzburl)
                else:
                    title = myDB.select('SELECT * from pastissues WHERE NZBurl="%s" OR NZBurl="%s"' % (nzburl, nzburl2))

                for item in title:
                    nzburl = item['NZBurl']
                    if action == 'Remove':
                        myDB.action('DELETE from pastissues WHERE NZBurl="%s"' % nzburl)
                        logger.debug(u'Item %s removed from past issues' % nzburl)
                        maglist.append({'nzburl': nzburl})
                    elif action in ['Have', 'Ignored', 'Skipped']:
                        myDB.action('UPDATE pastissues set status=%s WHERE NZBurl="%s"' % (action, nzburl))
                        logger.debug(u'Item %s removed from past issues' % nzburl)
                        maglist.append({'nzburl': nzburl})
                    elif action == 'Wanted':
                        bookid = item['BookID']
                        nzbprov = item['NZBprov']
                        nzbtitle = item['NZBtitle']
                        nzbmode = item['NZBmode']
                        nzbsize = item['NZBsize']
                        auxinfo = item['AuxInfo']
                        maglist.append({
                            'bookid': bookid,
                            'nzbprov': nzbprov,
                            'nzbtitle': nzbtitle,
                            'nzburl': nzburl,
                            'nzbmode': nzbmode
                        })
                        # copy into wanted table
                        controlValueDict = {'NZBurl': nzburl}
                        newValueDict = {
                            'BookID': bookid,
                            'NZBtitle': nzbtitle,
                            'NZBdate': now(),
                            'NZBprov': nzbprov,
                            'Status': action,
                            'NZBsize': nzbsize,
                            'AuxInfo': auxinfo,
                            'NZBmode': nzbmode
                        }
                        myDB.upsert("wanted", newValueDict, controlValueDict)

        if action == 'Remove':
            logger.info(u'Removed %s item%s from past issues' % (len(maglist), plural(len(maglist))))
        else:
            logger.info(u'Status set to %s for %s past issue%s' % (action, len(maglist), plural(len(maglist))))
        # start searchthreads
        if action == 'Wanted':
            for items in maglist:
                logger.debug(u'Snatching %s' % items['nzbtitle'])
                if items['nzbmode'] in ['torznab', 'torrent', 'magnet']:
                    snatch = TORDownloadMethod(
                        items['bookid'],
                        items['nzbtitle'],
                        items['nzburl'])
                else:
                    snatch = NZBDownloadMethod(
                        items['bookid'],
                        items['nzbtitle'],
                        items['nzburl'])
                if snatch:  # if snatch fails, downloadmethods already report it
                    logger.info('Downloading %s from %s' % (items['nzbtitle'], items['nzbprov']))
                    notifiers.notify_snatch(items['nzbtitle'] + ' at ' + now())
                    scheduleJob(action='Start', target='processDir')
        raise cherrypy.HTTPRedirect("pastIssues")

    @cherrypy.expose
    def markIssues(self, action=None, **args):
        self.label_thread()

        myDB = database.DBConnection()
        for item in args:
            # ouch dirty workaround...
            if not item == 'book_table_length':
                issue = myDB.match('SELECT IssueFile,Title,IssueDate from issues WHERE IssueID="%s"' % item)
                if issue:
                    if action == "Delete":
                        try:
                            rmtree(os.path.dirname(issue['IssueFile']), ignore_errors=True)
                            logger.info(u'Issue %s of %s deleted from disc' % (issue['IssueDate'], issue['Title']))
                        except Exception as e:
                            logger.debug('rmtree failed on %s, %s' % (issue['IssueFile'], str(e)))
                    if action == "Remove" or action == "Delete":
                        myDB.action('DELETE from issues WHERE IssueID="%s"' % item)
                        logger.info(u'Issue %s of %s removed from database' % (issue['IssueDate'], issue['Title']))
        raise cherrypy.HTTPRedirect("magazines")

    @cherrypy.expose
    def markMagazines(self, action=None, **args):
        self.label_thread()

        myDB = database.DBConnection()
        for item in args:
            if isinstance(item, str):
                item = item.decode(lazylibrarian.SYS_ENCODING)
            # ouch dirty workaround...
            if not item == 'book_table_length':
                if action == "Paused" or action == "Active":
                    controlValueDict = {"Title": item}
                    newValueDict = {"Status": action}
                    myDB.upsert("magazines", newValueDict, controlValueDict)
                    logger.info(u'Status of magazine %s changed to %s' % (item, action))
                if action == "Delete":
                    issues = myDB.select('SELECT IssueFile from issues WHERE Title="%s"' % item)
                    logger.debug(u'Deleting magazine %s from disc' % item)
                    issuedir = ''
                    for issue in issues:  # delete all issues of this magazine
                        try:
                            issuedir = os.path.dirname(issue['IssueFile'])
                            rmtree(issuedir, ignore_errors=True)
                            logger.debug(u'Issue directory %s deleted from disc' % issuedir)
                        except Exception as e:
                            logger.debug('rmtree failed on %s, %s' % (issuedir, str(e)))
                    if issuedir:
                        magdir = os.path.dirname(issuedir)
                        if not os.listdir(magdir):  # this magazines directory is now empty
                            try:
                                rmtree(magdir, ignore_errors=True)
                                logger.debug(u'Magazine directory %s deleted from disc' % magdir)
                            except Exception as e:
                                logger.debug('rmtree failed on %s, %s' % (magdir, str(e)))
                        else:
                            logger.debug(u'Magazine directory %s is not empty' % magdir)
                    logger.info(u'Magazine %s deleted from disc' % item)
                if action == "Remove" or action == "Delete":
                    myDB.action('DELETE from magazines WHERE Title="%s"' % item)
                    myDB.action('DELETE from pastissues WHERE BookID="%s"' % item)
                    myDB.action('DELETE from issues WHERE Title="%s"' % item)
                    logger.info(u'Magazine %s removed from database' % item)
                if action == "Reset":
                    controlValueDict = {"Title": item}
                    newValueDict = {
                        "LastAcquired": None,
                        "IssueDate": None,
                        "LatestCover": None,
                        "IssueStatus": "Wanted"
                    }
                    myDB.upsert("magazines", newValueDict, controlValueDict)
                    logger.info(u'Magazine %s details reset' % item)

        raise cherrypy.HTTPRedirect("magazines")

    @cherrypy.expose
    def searchForMag(self, bookid=None):
        myDB = database.DBConnection()
        bookid = urllib.unquote_plus(bookid)
        bookdata = myDB.match('SELECT * from magazines WHERE Title="%s"' % bookid)
        if bookdata:
            # start searchthreads
            mags = [{"bookid": bookid}]
            self.startMagazineSearch(mags)
            raise cherrypy.HTTPRedirect("magazines")

    @cherrypy.expose
    def startMagazineSearch(self, mags=None):
        if mags:
            if lazylibrarian.USE_NZB() or lazylibrarian.USE_TOR() or lazylibrarian.USE_RSS():
                threading.Thread(target=search_magazines, name='SEARCHMAG', args=[mags, False]).start()
                logger.debug(u"Searching for magazine with title: %s" % mags[0]["bookid"])
            else:
                logger.warn(u"Not searching for magazine, no download methods set, check config")
        else:
            logger.debug(u"MagazineSearch called with no magazines")

    @cherrypy.expose
    def addMagazine(self, title=None):
        self.label_thread()
        myDB = database.DBConnection()
        if title is None or not title:
            raise cherrypy.HTTPRedirect("magazines")
        else:
            reject = None
            if '~' in title:  # separate out the "reject words" list
                reject = title.split('~', 1)[1].strip()
                title = title.split('~', 1)[0].strip()

            # replace any non-ascii quotes/apostrophes with ascii ones eg "Collector's"
            dic = {u'\u2018': u"'", u'\u2019': u"'", u'\u201c': u'"', u'\u201d': u'"'}
            title = replace_all(title, dic)
            exists = myDB.match('SELECT Title from magazines WHERE Title="%s"' % title)
            if exists:
                logger.debug("Magazine %s already exists (%s)" % (title, exists['Title']))
            else:
                controlValueDict = {"Title": title}
                newValueDict = {
                    "Regex": None,
                    "Reject": reject,
                    "Status": "Active",
                    "MagazineAdded": today(),
                    "IssueStatus": "Wanted"
                }
                myDB.upsert("magazines", newValueDict, controlValueDict)
                mags = [{"bookid": title}]
                if lazylibrarian.CONFIG['IMP_AUTOSEARCH']:
                    self.startMagazineSearch(mags)
            raise cherrypy.HTTPRedirect("magazines")

    # UPDATES ###########################################################

    @cherrypy.expose
    def checkForUpdates(self):
        self.label_thread()
        versioncheck.checkForUpdates()
        if lazylibrarian.CONFIG['COMMITS_BEHIND'] == 0:
            if lazylibrarian.COMMIT_LIST:
                message = "unknown status"
                messages = lazylibrarian.COMMIT_LIST.replace('\n', '<br>')
                message = message + '<br><small>' + messages
            else:
                message = "up to date"
            return serve_template(templatename="shutdown.html", title="Version Check", message=message, timer=5)

        elif lazylibrarian.CONFIG['COMMITS_BEHIND'] > 0:
            message = "behind by %s commit%s" % (lazylibrarian.CONFIG['COMMITS_BEHIND'], plural(lazylibrarian.CONFIG['COMMITS_BEHIND']))
            messages = lazylibrarian.COMMIT_LIST.replace('\n', '<br>')
            message = message + '<br><small>' + messages
            return serve_template(templatename="shutdown.html", title="Commits", message=message, timer=15)

        else:
            message = "unknown version"
            messages = "Your version is not recognised at<br>https://github.com/%s/%s  Branch: %s" % (
                lazylibrarian.CONFIG['GIT_USER'], lazylibrarian.CONFIG['GIT_REPO'], lazylibrarian.CONFIG['GIT_BRANCH'])
            message = message + '<br><small>' + messages
            return serve_template(templatename="shutdown.html", title="Commits", message=message, timer=15)

            # raise cherrypy.HTTPRedirect("config")

    @cherrypy.expose
    def forceUpdate(self):
        if 'DBUPDATE' not in [n.name for n in [t for t in threading.enumerate()]]:
            threading.Thread(target=dbUpdate, name='DBUPDATE', args=[False]).start()
        else:
            logger.debug('DBUPDATE already running')
        raise cherrypy.HTTPRedirect("home")

    @cherrypy.expose
    def update(self):
        logger.debug('(webServe-Update) - Performing update')
        lazylibrarian.SIGNAL = 'update'
        message = 'Updating...'
        return serve_template(templatename="shutdown.html", title="Updating", message=message, timer=30)

    # IMPORT/EXPORT #####################################################

    @cherrypy.expose
    def libraryScan(self):
        if 'LIBRARYSYNC' not in [n.name for n in [t for t in threading.enumerate()]]:
            try:
                threading.Thread(target=LibraryScan, name='LIBRARYSYNC', args=[]).start()
            except Exception as e:
                logger.error(u'Unable to complete the scan: %s' % str(e))
        else:
            logger.debug('LIBRARYSYNC already running')
        raise cherrypy.HTTPRedirect("home")

    @cherrypy.expose
    def magazineScan(self):
        if 'LIBRARYSYNC' not in [n.name for n in [t for t in threading.enumerate()]]:
            try:
                threading.Thread(target=magazinescan.magazineScan, name='MAGAZINESCAN', args=[]).start()
            except Exception as e:
                logger.error(u'Unable to complete the scan: %s' % str(e))
        else:
            logger.debug('MAGAZINESCAN already running')
        raise cherrypy.HTTPRedirect("magazines")

    @cherrypy.expose
    def importAlternate(self):
        if 'IMPORTALT' not in [n.name for n in [t for t in threading.enumerate()]]:
            try:
                threading.Thread(target=processAlternate, name='IMPORTALT',
                                args=[lazylibrarian.CONFIG['ALTERNATE_DIR']]).start()
            except Exception as e:
                logger.error(u'Unable to complete the import: %s' % str(e))
        else:
            logger.debug('IMPORTALT already running')
        raise cherrypy.HTTPRedirect("manage")

    @cherrypy.expose
    def importCSV(self):
        if 'IMPORTCSV' not in [n.name for n in [t for t in threading.enumerate()]]:
            try:
                threading.Thread(target=import_CSV, name='IMPORTCSV',
                                args=[lazylibrarian.CONFIG['ALTERNATE_DIR']]).start()
            except Exception as e:
                logger.error(u'Unable to complete the import: %s' % str(e))
        else:
            logger.debug('IMPORTCSV already running')
        raise cherrypy.HTTPRedirect("manage")

    @cherrypy.expose
    def exportCSV(self):
        if 'EXPORTCSV' not in [n.name for n in [t for t in threading.enumerate()]]:
            try:
                threading.Thread(target=export_CSV, name='EXPORTCSV',
                                args=[lazylibrarian.CONFIG['ALTERNATE_DIR']]).start()
            except Exception as e:
                logger.error(u'Unable to complete the export: %s' % str(e))
        else:
            logger.debug('EXPORTCSV already running')
        raise cherrypy.HTTPRedirect("manage")

    # JOB CONTROL #######################################################

    @cherrypy.expose
    def shutdown(self):
        lazylibrarian.config_write()
        lazylibrarian.SIGNAL = 'shutdown'
        message = 'closing ...'
        return serve_template(templatename="shutdown.html", title="Close library", message=message, timer=15)

    @cherrypy.expose
    def restart(self):
        lazylibrarian.SIGNAL = 'restart'
        message = 'reopening ...'
        return serve_template(templatename="shutdown.html", title="Reopen library", message=message, timer=30)

    @cherrypy.expose
    def show_Jobs(self):
        cherrypy.response.headers[
            'Cache-Control'] = "max-age=0,no-cache,no-store"
        # show the current status of LL cron jobs in the log
        resultlist = showJobs()
        result = ''
        for line in resultlist:
            result = result + line + '\n'
        return result

    @cherrypy.expose
    def restart_Jobs(self):
        restartJobs(start='Restart')
        # and list the new run-times in the log
        return self.show_Jobs()

    # LOGGING ###########################################################

    @cherrypy.expose
    def clearLog(self):
        # Clear the log
        self.label_thread()

        result = clearLog()
        logger.info(result)
        raise cherrypy.HTTPRedirect("logs")

    @cherrypy.expose
    def toggleLog(self):
        # Toggle the debug log
        # LOGLEVEL 0, quiet
        # 1 normal
        # 2 debug
        # >2 do not turn off file/console log
        self.label_thread()

        if lazylibrarian.LOGFULL:  # if LOGLIST logging on, turn off
            lazylibrarian.LOGFULL = False
            if lazylibrarian.LOGLEVEL < 3:
                lazylibrarian.LOGLEVEL = 1
            logger.info(u'Debug log display OFF, loglevel is %s' % lazylibrarian.LOGLEVEL)
        else:
            lazylibrarian.LOGFULL = True
            if lazylibrarian.LOGLEVEL < 2:
                lazylibrarian.LOGLEVEL = 2  # Make sure debug ON
            logger.info(u'Debug log display ON, loglevel is %s' % lazylibrarian.LOGLEVEL)
        raise cherrypy.HTTPRedirect("logs")

    @cherrypy.expose
    def logs(self):
        return serve_template(templatename="logs.html", title="Log", lineList=[])  # lazylibrarian.LOGLIST)

    # noinspection PyUnusedLocal
    @cherrypy.expose
    def getLog(self, iDisplayStart=0, iDisplayLength=100, iSortCol_0=0, sSortDir_0="desc", sSearch="", **kwargs):
        # kwargs is used by datatables to pass params
        iDisplayStart = int(iDisplayStart)
        iDisplayLength = int(iDisplayLength)
        lazylibrarian.CONFIG['DISPLAYLENGTH'] = iDisplayLength

        if sSearch:
            filtered = filter(lambda x: sSearch in str(x), lazylibrarian.LOGLIST[::])
        else:
            filtered = lazylibrarian.LOGLIST[::]

        sortcolumn = int(iSortCol_0)
        filtered.sort(key=lambda x: x[sortcolumn], reverse=sSortDir_0 == "desc")
        if iDisplayLength < 0:  # display = all
            rows = filtered
        else:
            rows = filtered[iDisplayStart:(iDisplayStart + iDisplayLength)]

        mydict = {'iTotalDisplayRecords': len(filtered),
                  'iTotalRecords': len(lazylibrarian.LOGLIST),
                  'aaData': rows,
                  }
        s = simplejson.dumps(mydict)
        return s

    # HISTORY ###########################################################

    @cherrypy.expose
    def history(self, source=None):
        self.label_thread()
        myDB = database.DBConnection()
        if not source:
            # wanted status holds snatched processed for all, plus skipped and
            # ignored for magazine back issues
            history = myDB.select("SELECT * from wanted WHERE Status != 'Skipped' and Status != 'Ignored'")
            return serve_template(templatename="history.html", title="History", history=history)

    @cherrypy.expose
    def clearhistory(self, status=None):
        self.label_thread()
        myDB = database.DBConnection()
        if status == 'all':
            logger.info(u"Clearing all history")
            myDB.action("DELETE from wanted WHERE Status != 'Skipped' and Status != 'Ignored'")
        else:
            logger.info(u"Clearing history where status is %s" % status)
            myDB.action('DELETE from wanted WHERE Status="%s"' % status)
        raise cherrypy.HTTPRedirect("history")

    # NOTIFIERS #########################################################

    @cherrypy.expose
    def twitterStep1(self):
        cherrypy.response.headers[
            'Cache-Control'] = "max-age=0,no-cache,no-store"

        return notifiers.twitter_notifier._get_authorization()

    @cherrypy.expose
    def twitterStep2(self, key):
        cherrypy.response.headers[
            'Cache-Control'] = "max-age=0,no-cache,no-store"

        result = notifiers.twitter_notifier._get_credentials(key)
        logger.info(u"result: " + str(result))
        if result:
            return "Key verification successful"
        else:
            return "Unable to verify key"

    @cherrypy.expose
    def testTwitter(self):
        cherrypy.response.headers[
            'Cache-Control'] = "max-age=0,no-cache,no-store"

        result = notifiers.twitter_notifier.test_notify()
        if result:
            return "Tweet successful, check your twitter to make sure it worked"
        else:
            return "Error sending tweet"

    @cherrypy.expose
    def testAndroidPN(self, url=None, username=None, broadcast=None):
        cherrypy.response.headers[
            'Cache-Control'] = "max-age=0,no-cache,no-store"

        result = notifiers.androidpn_notifier.test_notify(
            url, username, broadcast)
        if result:
            return "Test AndroidPN notice sent successfully"
        else:
            return "Test AndroidPN notice failed"

    @cherrypy.expose
    def testBoxcar(self):
        cherrypy.response.headers['Cache-Control'] = "max-age=0,no-cache,no-store"
        result = notifiers.boxcar_notifier.test_notify()
        if result:
            return "Boxcar notification successful,\n%s" % result
        else:
            return "Boxcar notification failed"

    @cherrypy.expose
    def testPushbullet(self):
        cherrypy.response.headers['Cache-Control'] = "max-age=0,no-cache,no-store"

        result = notifiers.pushbullet_notifier.test_notify()
        if result:
            return "Pushbullet notification successful,\n%s" % result
        else:
            return "Pushbullet notification failed"

    @cherrypy.expose
    def testPushover(self):
        cherrypy.response.headers['Cache-Control'] = "max-age=0,no-cache,no-store"

        result = notifiers.pushover_notifier.test_notify()
        if result:
            return "Pushover notification successful,\n%s" % result
        else:
            return "Pushover notification failed"

    @cherrypy.expose
    def testNMA(self):
        cherrypy.response.headers['Cache-Control'] = "max-age=0,no-cache,no-store"

        result = notifiers.nma_notifier.test_notify()
        if result:
            return "Test NMA notice sent successfully"
        else:
            return "Test NMA notice failed"

    @cherrypy.expose
    def testSlack(self):
        cherrypy.response.headers['Cache-Control'] = "max-age=0,no-cache,no-store"

        result = notifiers.slack_notifier.test_notify()
        if result != "ok":
            return "Slack notification failed,\n%s" % result
        else:
            return "Slack notification successful"

    @cherrypy.expose
    def testEmail(self):
        cherrypy.response.headers['Cache-Control'] = "max-age=0,no-cache,no-store"

        result = notifiers.email_notifier.test_notify()
        if not result:
            return "Email notification failed"
        else:
            return "Email notification successful, check your email"

    # API ###############################################################

    @cherrypy.expose
    def api(self, **kwargs):
        from lazylibrarian.api import Api
        a = Api()
        a.checkParams(**kwargs)
        return a.fetchData()

    @cherrypy.expose
    def generateAPI(self):
        api_key = hashlib.sha224(str(random.getrandbits(256))).hexdigest()[0:32]
        lazylibrarian.CONFIG['API_KEY'] = api_key
        logger.info("New API generated")
        raise cherrypy.HTTPRedirect("config")

    # ALL ELSE ##########################################################

    @cherrypy.expose
    def forceProcess(self, source=None):
        if 'POSTPROCESS' not in [n.name for n in [t for t in threading.enumerate()]]:
            threading.Thread(target=processDir, name='POSTPROCESS', args=[True]).start()
        else:
            logger.debug('POSTPROCESS already running')
        raise cherrypy.HTTPRedirect(source)

    @cherrypy.expose
    def forceSearch(self, source=None):
        if source == "magazines":
            if lazylibrarian.USE_NZB() or lazylibrarian.USE_TOR() or lazylibrarian.USE_RSS():
                if 'SEARCHALLMAG' not in [n.name for n in [t for t in threading.enumerate()]]:
                    threading.Thread(target=search_magazines, name='SEARCHALLMAG', args=[]).start()
        elif source == "books":
            if lazylibrarian.USE_NZB():
                if 'SEARCHALLNZB' not in [n.name for n in [t for t in threading.enumerate()]]:
                    threading.Thread(target=search_nzb_book, name='SEARCHALLNZB', args=[]).start()
            if lazylibrarian.USE_TOR():
                if 'SEARCHALLTOR' not in [n.name for n in [t for t in threading.enumerate()]]:
                    threading.Thread(target=search_tor_book, name='SEARCHALLTOR', args=[]).start()
            if lazylibrarian.USE_RSS():
                if 'SEARCHALLRSS' not in [n.name for n in [t for t in threading.enumerate()]]:
                    threading.Thread(target=search_rss_book, name='SEARCHALLRSS', args=[]).start()
        else:
            logger.debug(u"forceSearch called with bad source")
        raise cherrypy.HTTPRedirect(source)


    @cherrypy.expose
    def manage(self, whichStatus=None):
        if whichStatus is None:
            whichStatus = "Wanted"
        return serve_template(templatename="managebooks.html", title="Manage Books",
                              books=[], whichStatus=whichStatus)


    @cherrypy.expose
    def testDeluge(self):
        cherrypy.response.headers['Cache-Control'] = "max-age=0,no-cache,no-store"
        try:
            if not lazylibrarian.CONFIG['DELUGE_USER']:
                # no username, talk to the webui
                return deluge.checkLink()

            # if there's a username, talk to the daemon directly
            client = DelugeRPCClient(lazylibrarian.CONFIG['DELUGE_HOST'],
                                     int(lazylibrarian.CONFIG['DELUGE_PORT']),
                                     lazylibrarian.CONFIG['DELUGE_USER'],
                                     lazylibrarian.CONFIG['DELUGE_PASS'])
            client.connect()
            if lazylibrarian.CONFIG['DELUGE_LABEL']:
                labels = client.call('label.get_labels')
                if lazylibrarian.CONFIG['DELUGE_LABEL'] not in labels:
                    msg = "Deluge: Unknown label [%s]\n" % lazylibrarian.CONFIG['DELUGE_LABEL']
                    if labels:
                        msg += "Valid labels:\n"
                        for label in labels:
                            msg += '%s\n' % label
                    else:
                        msg += "Deluge daemon seems to have no labels set"
                    return msg
            return "Deluge: Daemon connection Successful"
        except Exception as e:
            msg = "Deluge: Daemon connection FAILED\n"
            if 'Connection refused' in str(e):
                msg += str(e)
                msg += "Check Deluge daemon HOST and PORT settings"
            elif 'need more than 1 value' in str(e):
                msg += "Invalid USERNAME or PASSWORD"
            else:
                msg += str(e)
            return msg

    @cherrypy.expose
    def testSABnzbd(self):
        cherrypy.response.headers['Cache-Control'] = "max-age=0,no-cache,no-store"
        return sabnzbd.checkLink()

    @cherrypy.expose
    def testNZBget(self):
        cherrypy.response.headers['Cache-Control'] = "max-age=0,no-cache,no-store"
        return nzbget.checkLink()

    @cherrypy.expose
    def testTransmission(self):
        cherrypy.response.headers['Cache-Control'] = "max-age=0,no-cache,no-store"
        return transmission.checkLink()

    @cherrypy.expose
    def testqBittorrent(self):
        cherrypy.response.headers['Cache-Control'] = "max-age=0,no-cache,no-store"
        return qbittorrent.checkLink()

    @cherrypy.expose
    def testuTorrent(self):
        cherrypy.response.headers['Cache-Control'] = "max-age=0,no-cache,no-store"
        return utorrent.checkLink()

    @cherrypy.expose
    def testrTorrent(self):
        cherrypy.response.headers['Cache-Control'] = "max-age=0,no-cache,no-store"
        return rtorrent.checkLink()

    @cherrypy.expose
    def testSynology(self):
        cherrypy.response.headers['Cache-Control'] = "max-age=0,no-cache,no-store"
        return synology.checkLink()
