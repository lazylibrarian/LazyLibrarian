import os
import shutil
import cherrypy
from cherrypy.lib.static import serve_file
from mako.lookup import TemplateLookup
from mako import exceptions
from operator import itemgetter

import threading
import Queue
import hashlib

import lazylibrarian

from lazylibrarian import logger, importer, database, postprocess, formatter, \
                          notifiers, librarysync, versioncheck, magazinescan, common
from lazylibrarian.searchnzb import search_nzb_book, NZBDownloadMethod
from lazylibrarian.searchtorrents import search_tor_book, TORDownloadMethod
from lazylibrarian.searchmag import search_magazines
from lazylibrarian.gr import GoodReads
from lazylibrarian.gb import GoogleBooks

import lib.simplejson as simplejson


def serve_template(templatename, **kwargs):

    interface_dir = os.path.join(str(lazylibrarian.PROG_DIR), 'data/interfaces/')
    template_dir = os.path.join(str(interface_dir), lazylibrarian.HTTP_LOOK)

    _hplookup = TemplateLookup(directories=[template_dir])

    try:
        template = _hplookup.get_template(templatename)
        return template.render(**kwargs)
    except:
        return exceptions.html_error_template().render()


class WebInterface(object):

    def index(self):
        raise cherrypy.HTTPRedirect("home")
    index.exposed = True

    def home(self):
        myDB = database.DBConnection()
        authors = myDB.select('SELECT * from authors order by AuthorName COLLATE NOCASE')
        return serve_template(templatename="index.html", title="Home", authors=authors)
    home.exposed = True

# CONFIG ############################################################

    def config(self):
        http_look_dir = os.path.join(lazylibrarian.PROG_DIR, 'data/interfaces/')
        http_look_list = [name for name in os.listdir(http_look_dir)
                          if os.path.isdir(os.path.join(http_look_dir, name))]
        status_list = ['Skipped', 'Wanted', 'Open', 'Ignored']
        # Don't pass the whole config, no need to pass the lazylibrarian.globals
        config = {
            "http_look_list":   http_look_list,
            "status_list":	    status_list
        }
        return serve_template(templatename="config.html", title="Settings", config=config)
    config.exposed = True

    def configUpdate(self, http_host='0.0.0.0', http_root=None, http_user=None, http_port=5299,
                     http_pass=None, http_look=None, launch_browser=0, logdir=None, loglevel=2,
                     imp_onlyisbn=0, imp_singlebook=0, imp_preflang=None, imp_monthlang=None,
                     imp_autoadd=None, match_ratio=80, nzb_downloader_sabnzbd=0, nzb_downloader_nzbget=0,
                     nzb_downloader_blackhole=0, use_nzb=0, use_tor=0, proxy_host=None, proxy_type=None,
                     sab_host=None, sab_port=0, sab_subdir=None, sab_api=None, sab_user=None, sab_pass=None,
                     destination_copy=0, destination_dir=None, download_dir=None, sab_cat=None, usenet_retention=0,
                     nzb_blackholedir=None, alternate_dir=None, torrent_dir=None, numberofseeders=0,
                     tor_downloader_blackhole=0, tor_downloader_utorrent=0, nzbget_host=None, nzbget_user=None,
                     nzbget_pass=None, nzbget_cat=None, nzbget_priority=0, newznab0=0, newznab_host0=None,
                     newznab_api0=None, newznab1=0, newznab_host1=None, newznab_api1=None, newznab2=0,
                     newznab_host2=None, newznab_api2=None, newznab3=0, newznab_host3=None, newznab_api3=None,
                     newznab4=0, newznab_host4=None, newznab_api4=None, newzbin=0, newzbin_uid=None,
                     newzbin_pass=None, kat=0, kat_host=None, ebook_type=None, book_api=None,
                     torznab0=0, torznab_host0=None, torznab_api0=None, torznab1=0, torznab_host1=None,
                     torznab_api1=None, torznab2=0, torznab_host2=None, torznab_api2=None,
                     torznab3=0, torznab_host3=None, torznab_api3=None, torznab4=0, torznab_host4=None,
                     torznab_api4=None, gr_api=None, gb_api=None, versioncheck_interval=None, search_interval=None,
                     scan_interval=None, ebook_dest_folder=None, ebook_dest_file=None, mag_relative=0,
                     mag_dest_folder=None, mag_dest_file=None,
                     use_twitter=0, twitter_notify_onsnatch=0, twitter_notify_ondownload=0,
                     utorrent_host=None, utorrent_user=None, utorrent_pass=None,
                     notfound_status='Skipped', newbook_status='Skipped', full_scan=0, add_author=0,
                     tor_downloader_transmission=0, transmission_host=None, transmission_user=None,
                     transmission_pass=None, tor_downloader_deluge=0, deluge_host=None, deluge_user=None,
                     deluge_pass=None, deluge_port=0, utorrent_label=None, use_boxcar=0, boxcar_notify_onsnatch=0,
                     boxcar_notify_ondownload=0, boxcar_token=None, use_pushbullet=0, pushbullet_notify_onsnatch=0,
                     pushbullet_notify_ondownload=0, pushbullet_token=None, pushbullet_deviceid=None,
                     use_pushover=0, pushover_onsnatch=0, pushover_priority=0, pushover_keys=None,
                     pushover_apitoken=None, pushover_ondownload=0, pushover_device=None,
                     use_androidpn=0, androidpn_notify_onsnatch=0, androidpn_notify_ondownload=0,
                     androidpn_url=None, androidpn_username=None, androidpn_broadcast=1,
                     use_nma=0, nma_apikey=None, nma_priority=0, nma_onsnatch=0, nma_ondownload=0):

        lazylibrarian.HTTP_HOST = http_host
        lazylibrarian.HTTP_ROOT = http_root
        lazylibrarian.HTTP_PORT = formatter.check_int(http_port, 5299)
        lazylibrarian.HTTP_USER = http_user
        lazylibrarian.HTTP_PASS = http_pass
        lazylibrarian.HTTP_LOOK = http_look
        lazylibrarian.LAUNCH_BROWSER = bool(launch_browser)
        lazylibrarian.PROXY_HOST = proxy_host
        lazylibrarian.PROXY_TYPE = proxy_type
        lazylibrarian.LOGDIR = logdir
        lazylibrarian.LOGLEVEL = formatter.check_int(loglevel, 2)
        lazylibrarian.MATCH_RATIO = formatter.check_int(match_ratio, 80)

        lazylibrarian.IMP_ONLYISBN = bool(imp_onlyisbn)
        lazylibrarian.IMP_SINGLEBOOK = bool(imp_singlebook)
        lazylibrarian.IMP_PREFLANG = imp_preflang
        lazylibrarian.IMP_MONTHLANG = imp_monthlang
        lazylibrarian.IMP_AUTOADD = imp_autoadd

        lazylibrarian.SAB_HOST = sab_host
        lazylibrarian.SAB_PORT = formatter.check_int(sab_port, 0)
        lazylibrarian.SAB_SUBDIR = sab_subdir
        lazylibrarian.SAB_API = sab_api
        lazylibrarian.SAB_USER = sab_user
        lazylibrarian.SAB_PASS = sab_pass
        lazylibrarian.SAB_CAT = sab_cat

        lazylibrarian.NZBGET_HOST = nzbget_host
        lazylibrarian.NZBGET_USER = nzbget_user
        lazylibrarian.NZBGET_PASS = nzbget_pass
        lazylibrarian.NZBGET_CATEGORY = nzbget_cat
        lazylibrarian.NZBGET_PRIORITY = formatter.check_int(nzbget_priority, 0)

        lazylibrarian.DESTINATION_COPY = bool(destination_copy)
        lazylibrarian.DESTINATION_DIR = destination_dir
        lazylibrarian.ALTERNATE_DIR = alternate_dir
        lazylibrarian.DOWNLOAD_DIR = download_dir
        lazylibrarian.USENET_RETENTION = formatter.check_int(usenet_retention, 0)
        lazylibrarian.NZB_BLACKHOLEDIR = nzb_blackholedir
        lazylibrarian.NZB_DOWNLOADER_SABNZBD = bool(nzb_downloader_sabnzbd)
        lazylibrarian.NZB_DOWNLOADER_NZBGET = bool(nzb_downloader_nzbget)
        lazylibrarian.NZB_DOWNLOADER_BLACKHOLE = bool(nzb_downloader_blackhole)
        lazylibrarian.TORRENT_DIR = torrent_dir
        lazylibrarian.NUMBEROFSEEDERS = formatter.check_int(numberofseeders, 0)
        lazylibrarian.TOR_DOWNLOADER_BLACKHOLE = bool(tor_downloader_blackhole)
        lazylibrarian.TOR_DOWNLOADER_UTORRENT = bool(tor_downloader_utorrent)
        lazylibrarian.TOR_DOWNLOADER_TRANSMISSION = bool(tor_downloader_transmission)
        lazylibrarian.TOR_DOWNLOADER_DELUGE = bool(tor_downloader_deluge)

        lazylibrarian.NEWZNAB0 = bool(newznab0)
        lazylibrarian.NEWZNAB_HOST0 = newznab_host0
        lazylibrarian.NEWZNAB_API0 = newznab_api0

        lazylibrarian.NEWZNAB1 = bool(newznab1)
        lazylibrarian.NEWZNAB_HOST1 = newznab_host1
        lazylibrarian.NEWZNAB_API1 = newznab_api1

        lazylibrarian.NEWZNAB2 = bool(newznab2)
        lazylibrarian.NEWZNAB_HOST2 = newznab_host2
        lazylibrarian.NEWZNAB_API2 = newznab_api2

        lazylibrarian.NEWZNAB3 = bool(newznab3)
        lazylibrarian.NEWZNAB_HOST3 = newznab_host3
        lazylibrarian.NEWZNAB_API3 = newznab_api3

        lazylibrarian.NEWZNAB4 = bool(newznab4)
        lazylibrarian.NEWZNAB_HOST4 = newznab_host4
        lazylibrarian.NEWZNAB_API4 = newznab_api4

        lazylibrarian.TORZNAB0 = bool(torznab0)
        lazylibrarian.TORZNAB_HOST0 = torznab_host0
        lazylibrarian.TORZNAB_API0 = torznab_api0

        lazylibrarian.TORZNAB1 = bool(torznab1)
        lazylibrarian.TORZNAB_HOST1 = torznab_host1
        lazylibrarian.TORZNAB_API1 = torznab_api1

        lazylibrarian.TORZNAB2 = bool(torznab2)
        lazylibrarian.TORZNAB_HOST2 = torznab_host2
        lazylibrarian.TORZNAB_API2 = torznab_api2

        lazylibrarian.TORZNAB3 = bool(torznab3)
        lazylibrarian.TORZNAB_HOST3 = torznab_host3
        lazylibrarian.TORZNAB_API3 = torznab_api3

        lazylibrarian.TORZNAB4 = bool(torznab4)
        lazylibrarian.TORZNAB_HOST4 = torznab_host4
        lazylibrarian.TORZNAB_API4 = torznab_api4

        lazylibrarian.NEWZBIN = bool(newzbin)
        lazylibrarian.NEWZBIN_UID = newzbin_uid
        lazylibrarian.NEWZBIN_PASS = newzbin_pass

        lazylibrarian.UTORRENT_HOST = utorrent_host
        lazylibrarian.UTORRENT_USER = utorrent_user
        lazylibrarian.UTORRENT_PASS = utorrent_pass
        lazylibrarian.UTORRENT_LABEL = utorrent_label

        lazylibrarian.TRANSMISSION_HOST = transmission_host
        lazylibrarian.TRANSMISSION_USER = transmission_user
        lazylibrarian.TRANSMISSION_PASS = transmission_pass

        lazylibrarian.DELUGE_HOST = deluge_host
        lazylibrarian.DELUGE_PORT = formatter.check_int(deluge_port, 0)
        lazylibrarian.DELUGE_USER = deluge_user
        lazylibrarian.DELUGE_PASS = deluge_pass

        lazylibrarian.KAT = bool(kat)
        lazylibrarian.KAT_HOST = kat_host

        lazylibrarian.USE_NZB = bool(use_nzb)
        lazylibrarian.USE_TOR = bool(use_tor)

        lazylibrarian.EBOOK_TYPE = ebook_type
        lazylibrarian.BOOK_API = book_api
        lazylibrarian.GR_API = gr_api
        lazylibrarian.GB_API = gb_api

        lazylibrarian.SEARCH_INTERVAL = formatter.check_int(search_interval, 360)
        lazylibrarian.SCAN_INTERVAL = formatter.check_int(scan_interval, 10)
        lazylibrarian.VERSIONCHECK_INTERVAL = formatter.check_int(versioncheck_interval, 24)

        lazylibrarian.FULL_SCAN = bool(full_scan)
        lazylibrarian.NOTFOUND_STATUS = notfound_status
        lazylibrarian.NEWBOOK_STATUS = newbook_status
        lazylibrarian.ADD_AUTHOR = bool(add_author)

        lazylibrarian.EBOOK_DEST_FOLDER = ebook_dest_folder
        lazylibrarian.EBOOK_DEST_FILE = ebook_dest_file
        lazylibrarian.MAG_DEST_FOLDER = mag_dest_folder
        lazylibrarian.MAG_DEST_FILE = mag_dest_file
        lazylibrarian.MAG_RELATIVE = bool(mag_relative)

        lazylibrarian.USE_TWITTER = bool(use_twitter)
        lazylibrarian.TWITTER_NOTIFY_ONSNATCH = bool(twitter_notify_onsnatch)
        lazylibrarian.TWITTER_NOTIFY_ONDOWNLOAD = bool(twitter_notify_ondownload)

        lazylibrarian.USE_BOXCAR = bool(use_boxcar)
        lazylibrarian.BOXCAR_NOTIFY_ONSNATCH = bool(boxcar_notify_onsnatch)
        lazylibrarian.BOXCAR_NOTIFY_ONDOWNLOAD = bool(boxcar_notify_ondownload)
        lazylibrarian.BOXCAR_TOKEN = boxcar_token

        lazylibrarian.USE_PUSHBULLET = bool(use_pushbullet)
        lazylibrarian.PUSHBULLET_NOTIFY_ONSNATCH = bool(pushbullet_notify_onsnatch)
        lazylibrarian.PUSHBULLET_NOTIFY_ONDOWNLOAD = bool(pushbullet_notify_ondownload)
        lazylibrarian.PUSHBULLET_TOKEN = pushbullet_token
        lazylibrarian.PUSHBULLET_DEVICEID = pushbullet_deviceid

        lazylibrarian.USE_PUSHOVER = bool(use_pushover)
        lazylibrarian.PUSHOVER_ONSNATCH = bool(pushover_onsnatch)
        lazylibrarian.PUSHOVER_ONDOWNLOAD = bool(pushover_ondownload)
        lazylibrarian.PUSHOVER_KEYS = pushover_keys
        lazylibrarian.PUSHOVER_APITOKEN = pushover_apitoken
        lazylibrarian.PUSHOVER_PRIORITY = formatter.check_int(pushover_priority, 0)
        lazylibrarian.PUSHOVER_DEVICE = pushover_device

        lazylibrarian.USE_ANDROIDPN = bool(use_androidpn)
        lazylibrarian.ANDROIDPN_NOTIFY_ONSNATCH = bool(androidpn_notify_onsnatch)
        lazylibrarian.ANDROIDPN_NOTIFY_ONDOWNLOAD = bool(androidpn_notify_ondownload)
        lazylibrarian.ANDROIDPN_URL = androidpn_url
        lazylibrarian.ANDROIDPN_USERNAME = androidpn_username
        lazylibrarian.ANDROIDPN_BROADCAST = bool(androidpn_broadcast)

        lazylibrarian.USE_NMA = bool(use_nma)
        lazylibrarian.NMA_APIKEY = nma_apikey
        lazylibrarian.NMA_PRIORITY = formatter.check_int(nma_priority, 0)
        lazylibrarian.NMA_ONSNATCH = bool(nma_onsnatch)
        lazylibrarian.NMA_ONDOWNLOAD = bool(nma_ondownload)

        lazylibrarian.config_write()

        logger.info('Config file has been updated')
        raise cherrypy.HTTPRedirect("config")

    configUpdate.exposed = True

# SEARCH ############################################################

    def search(self, name):
        myDB = database.DBConnection()
        if lazylibrarian.BOOK_API == "GoogleBooks":
            GB = GoogleBooks(name)
            queue = Queue.Queue()
            search_api = threading.Thread(target=GB.find_results, args=[name, queue])
            search_api.start()
        elif lazylibrarian.BOOK_API == "GoodReads":
            queue = Queue.Queue()
            GR = GoodReads(name)
            search_api = threading.Thread(target=GR.find_results, args=[name, queue])
            search_api.start()
        if len(name) == 0:
            raise cherrypy.HTTPRedirect("config")

        search_api.join()
        searchresults = queue.get()

        authorsearch = myDB.select("SELECT * from authors")
        authorlist = []
        for item in authorsearch:
            authorlist.append(item['AuthorName'])

        booksearch = myDB.select("SELECT * from books")
        booklist = []
        for item in booksearch:
            booklist.append(item['BookID'])

        sortedlist_final = sorted(searchresults, key=itemgetter('highest_fuzz', 'num_reviews'), reverse=True)
        return serve_template(templatename="searchresults.html", title='Search Results for: "' +
                              name + '"', searchresults=sortedlist_final, authorlist=authorlist,
                              booklist=booklist, booksearch=booksearch, type=type)
    search.exposed = True

# AUTHOR ############################################################

    def authorPage(self, AuthorName, BookLang=None, Ignored=False):
        myDB = database.DBConnection()

        if Ignored:
            languages = myDB.select("SELECT DISTINCT BookLang from books WHERE AuthorName LIKE ? \
                                    AND Status ='Ignored'", [AuthorName.replace("'", "''")])
            if BookLang:
                querybooks = "SELECT * from books WHERE AuthorName LIKE '%s' AND BookLang = '%s' \
                              AND Status ='Ignored' order by BookDate DESC, BookRate DESC" % (
                              AuthorName.replace("'", "''"), BookLang)
            else:
                querybooks = "SELECT * from books WHERE AuthorName LIKE '%s' and Status ='Ignored' \
                              order by BookDate DESC, BookRate DESC" % (AuthorName.replace("'", "''"))
        else:
            languages = myDB.select("SELECT DISTINCT BookLang from books WHERE AuthorName LIKE ? \
                                    AND Status !='Ignored'", [AuthorName.replace("'", "''")])
            if BookLang:
                querybooks = "SELECT * from books WHERE AuthorName LIKE '%s' AND BookLang = '%s' \
                              AND Status !='Ignored' order by BookDate DESC, BookRate DESC" % (
                              AuthorName.replace("'", "''"), BookLang)
            else:
                querybooks = "SELECT * from books WHERE AuthorName LIKE '%s' and Status !='Ignored' \
                              order by BookDate DESC, BookRate DESC" % (AuthorName.replace("'", "''"))

        queryauthors = "SELECT * from authors WHERE AuthorName LIKE '%s'" % AuthorName.replace("'", "''")

        author = myDB.action(queryauthors).fetchone()
        books = myDB.select(querybooks)
        if author is None:
            raise cherrypy.HTTPRedirect("home")
        return serve_template(templatename="author.html", title=author['AuthorName'],
                              author=author, books=books, languages=languages)
    authorPage.exposed = True

    def pauseAuthor(self, AuthorID):
        myDB = database.DBConnection()
        authorsearch = myDB.select('SELECT AuthorName from authors WHERE AuthorID="%s"' % AuthorID)
        AuthorName = authorsearch[0]['AuthorName']
        logger.info(u"Pausing author: %s" % AuthorName)

        controlValueDict = {'AuthorID': AuthorID}
        newValueDict = {'Status': 'Paused'}
        myDB.upsert("authors", newValueDict, controlValueDict)
        logger.debug(u'AuthorID [%s]-[%s] Paused - redirecting to Author home page' % (AuthorID, AuthorName))
        raise cherrypy.HTTPRedirect("authorPage?AuthorName=%s" % AuthorName)
    pauseAuthor.exposed = True

    def resumeAuthor(self, AuthorID):
        myDB = database.DBConnection()
        authorsearch = myDB.select('SELECT AuthorName from authors WHERE AuthorID="%s"' % AuthorID)
        AuthorName = authorsearch[0]['AuthorName']
        logger.info(u"Resuming author: %s" % AuthorName)

        controlValueDict = {'AuthorID': AuthorID}
        newValueDict = {'Status': 'Active'}
        myDB.upsert("authors", newValueDict, controlValueDict)
        logger.debug(u'AuthorID [%s]-[%s] Restarted - redirecting to Author home page' % (AuthorID, AuthorName))
        raise cherrypy.HTTPRedirect("authorPage?AuthorName=%s" % AuthorName)
    resumeAuthor.exposed = True

    def deleteAuthor(self, AuthorID):
        myDB = database.DBConnection()
        authorsearch = myDB.select('SELECT AuthorName from authors WHERE AuthorID="%s"' % AuthorID)
        AuthorName = authorsearch[0]['AuthorName']
        logger.info(u"Removing all references to author: %s" % AuthorName)

        myDB.action('DELETE from authors WHERE AuthorID="%s"' % AuthorID)
        myDB.action('DELETE from books WHERE AuthorID="%s"' % AuthorID)
        raise cherrypy.HTTPRedirect("home")
    deleteAuthor.exposed = True

    def refreshAuthor(self, AuthorName):
        refresh = True
        threading.Thread(target=importer.addAuthorToDB, args=(AuthorName, refresh)).start()
        raise cherrypy.HTTPRedirect("authorPage?AuthorName=%s" % AuthorName)
    refreshAuthor.exposed = True

    def addAuthor(self, AuthorName):
        args = None
        threading.Thread(target=importer.addAuthorToDB, args=[AuthorName]).start()
        raise cherrypy.HTTPRedirect("authorPage?AuthorName=%s" % AuthorName)
    addAuthor.exposed = True

# BOOKS #############################################################

    def books(self, BookLang=None):
        myDB = database.DBConnection()

        languages = myDB.select('SELECT DISTINCT BookLang from books WHERE NOT \
                                STATUS="Skipped" AND NOT STATUS="Ignored"')

        if BookLang:
            books = myDB.select('SELECT * from books WHERE BookLang="%s" AND NOT \
                                Status="Skipped" AND NOT STATUS="Ignored"' % BookLang)
        else:
            books = myDB.select('SELECT * from books WHERE NOT STATUS="Skipped" AND NOT STATUS="Ignored"')

        if books is None:
            raise cherrypy.HTTPRedirect("books")
        return serve_template(templatename="books.html", title='Books', books=books, languages=languages)
    books.exposed = True

    def addBook(self, bookid=None):
        myDB = database.DBConnection()

        booksearch = myDB.select('SELECT * from books WHERE BookID="%s"' % bookid)
        if booksearch:
            myDB.upsert("books", {'Status': 'Wanted'}, {'BookID': bookid})
            for book in booksearch:
                AuthorName = book['AuthorName']
                authorsearch = myDB.select('SELECT * from authors WHERE AuthorName="%s"' % AuthorName)
                if authorsearch:
                    # update authors needs to be updated every time a book is marked differently
                    lastbook = myDB.action('SELECT BookName, BookLink, BookDate from books WHERE \
                                           AuthorName="%s" AND Status != "Ignored" order by BookDate DESC' %
                                           AuthorName).fetchone()
                    unignoredbooks = myDB.select('SELECT COUNT(BookName) as unignored FROM books WHERE \
                                                 AuthorName="%s" AND Status != "Ignored"' % AuthorName)
                    bookCount = myDB.select('SELECT COUNT(BookName) as counter FROM books WHERE \
                                            AuthorName="%s"' % AuthorName)
                    countbooks = myDB.action('SELECT COUNT(*) FROM books WHERE AuthorName="%s" AND \
                                             (Status="Have" OR Status="Open")' % AuthorName).fetchone()
                    havebooks = int(countbooks[0])

                    controlValueDict = {"AuthorName": AuthorName}
                    newValueDict = {
                        "TotalBooks": bookCount[0]['counter'],
                        "UnignoredBooks": unignoredbooks[0]['unignored'],
                        "HaveBooks": havebooks,
                        "LastBook": lastbook['BookName'],
                        "LastLink": lastbook['BookLink'],
                        "LastDate": lastbook['BookDate']
                    }
                    myDB.upsert("authors", newValueDict, controlValueDict)
        else:
            if lazylibrarian.BOOK_API == "GoogleBooks":
                GB = GoogleBooks(bookid)
                queue = Queue.Queue()
                find_book = threading.Thread(target=GB.find_book, args=[bookid, queue])
                find_book.start()
            elif lazylibrarian.BOOK_API == "GoodReads":
                queue = Queue.Queue()
                GR = GoodReads(bookid)
                find_book = threading.Thread(target=GR.find_book, args=[bookid, queue])
                find_book.start()
            if len(bookid) == 0:
                raise cherrypy.HTTPRedirect("config")

            find_book.join()

        books = []
        mags = False
        books.append({"bookid": bookid})

        if (lazylibrarian.USE_NZB):
            threading.Thread(target=search_nzb_book, args=[books, mags]).start()
        if (lazylibrarian.USE_TOR):
            threading.Thread(target=search_tor_book, args=[books, mags]).start()

        raise cherrypy.HTTPRedirect("books")
    addBook.exposed = True

    def openBook(self, bookid=None, **args):
        myDB = database.DBConnection()

        bookdata = myDB.select('SELECT * from books WHERE BookID="%s"' % bookid)
        if bookdata:
            bookfile = bookdata[0]["BookFile"]
            if bookfile and os.path.isfile(bookfile):
                logger.info(u'Opening file ' + bookfile)
                return serve_file(bookfile, "application/x-download", "attachment")
            else:
                authorName = bookdata[0]["AuthorName"]
                bookName = bookdata[0]["BookName"]
                logger.info(u'Missing book %s,%s' % (authorName, bookName))
    openBook.exposed = True

    def searchForBook(self, bookid=None, action=None, **args):
        myDB = database.DBConnection()

        bookdata = myDB.select('SELECT * from books WHERE BookID="%s"' % bookid)
        if bookdata:
            AuthorName = bookdata[0]["AuthorName"]

            # start searchthreads
            books = []
            books.append({"bookid": bookid})

            mags = False
            if (lazylibrarian.USE_NZB):
                threading.Thread(target=search_nzb_book, args=[books, mags]).start()
            if (lazylibrarian.USE_TOR):
                threading.Thread(target=search_tor_book, args=[books, mags]).start()

            logger.debug(u"Searching for book with id: " + bookid)
        if AuthorName:
            raise cherrypy.HTTPRedirect("authorPage?AuthorName=%s" % AuthorName)
    searchForBook.exposed = True

    def markBooks(self, AuthorName=None, action=None, redirect=None, **args):
        myDB = database.DBConnection()
        if not redirect:
            redirect = "books"
        authorcheck = None
        for bookid in args:
            # ouch dirty workaround...
            if not bookid == 'book_table_length':
                if action != "Remove":
                    controlValueDict = {'BookID': bookid}
                    newValueDict = {'Status': action}
                    myDB.upsert("books", newValueDict, controlValueDict)
                    title = myDB.select('SELECT * from books WHERE BookID = "%s"' % bookid)
                    for item in title:
                        bookname = item['BookName']
                        logger.info(u'Status set to "%s" for "%s"' % (action, bookname))

                else:
                    authorsearch = myDB.select('SELECT * from books WHERE BookID = "%s"' % bookid)
                    for item in authorsearch:
                        AuthorName = item['AuthorName']
                        bookname = item['BookName']
                    authorcheck = myDB.select('SELECT * from authors WHERE AuthorName = "%s"' % AuthorName)
                    if authorcheck:
                        myDB.upsert("books", {"Status": "Skipped"}, {"BookID": bookid})
                        logger.info(u'Status set to Skipped for "%s"' % bookname)
                    else:
                        myDB.action('DELETE from books WHERE BookID = "%s"' % bookid)
                        logger.info(u'Removed "%s" from database' % bookname)

        if redirect == "author" or authorcheck:
            # update authors needs to be updated every time a book is marked differently
            lastbook = myDB.action('SELECT BookName, BookLink, BookDate from books WHERE AuthorName="%s" \
                                   AND Status != "Ignored" order by BookDate DESC' % AuthorName).fetchone()
            unignoredbooks = myDB.select('SELECT COUNT(BookName) as unignored FROM books WHERE AuthorName="%s" \
                                         AND Status != "Ignored"' % AuthorName)
            bookCount = myDB.select('SELECT COUNT(BookName) as counter FROM books WHERE AuthorName="%s"' % AuthorName)
            countbooks = myDB.action('SELECT COUNT(*) FROM books WHERE AuthorName="%s" AND \
                                     (Status="Have" OR Status="Open")' % AuthorName).fetchone()
            havebooks = int(countbooks[0])

            controlValueDict = {"AuthorName": AuthorName}
            newValueDict = {
                "TotalBooks": bookCount[0]['counter'],
                "UnignoredBooks": unignoredbooks[0]['unignored'],
                "HaveBooks": havebooks,
                "LastBook": lastbook['BookName'],
                "LastLink": lastbook['BookLink'],
                "LastDate": lastbook['BookDate']
            }
            myDB.upsert("authors", newValueDict, controlValueDict)

        # start searchthreads
        if action == 'Wanted':
            books = []
            for bookid in args:
                # ouch dirty workaround...
                if not bookid == 'book_table_length':
                    books.append({"bookid": bookid})
            mags = False
            if (lazylibrarian.USE_NZB):
                threading.Thread(target=search_nzb_book, args=[books, mags]).start()
            if (lazylibrarian.USE_TOR):
                threading.Thread(target=search_tor_book, args=[books, mags]).start()

        if redirect == "author":
            raise cherrypy.HTTPRedirect("authorPage?AuthorName=%s" % AuthorName)
        elif redirect == "books":
            raise cherrypy.HTTPRedirect("books")
        else:
            raise cherrypy.HTTPRedirect("manage")
    markBooks.exposed = True

# MAGAZINES #########################################################

    def magazines(self):
        myDB = database.DBConnection()

        magazines = myDB.select('SELECT * from magazines ORDER by Title')

        if magazines is None:
            raise cherrypy.HTTPRedirect("magazines")
        else:
            mags = []
            for mag in magazines:
                title = mag['Title']
                count = myDB.select('SELECT COUNT(Title) as counter FROM issues WHERE Title="%s"' % title)
                if count:
                    issues = count[0]['counter']
                else:
                    issues = 0
                this_mag = dict(mag)
                this_mag['Count'] = issues
                mags.append(this_mag)

        return serve_template(templatename="magazines.html", title="Magazines", magazines=mags)
    magazines.exposed = True

    def issuePage(self, title):
        myDB = database.DBConnection()

        issues = myDB.select('SELECT * from issues WHERE Title="%s" order by IssueDate DESC' % (title))

        if issues is None:
            raise cherrypy.HTTPRedirect("magazines")
        else:
            mod_issues = []
            for issue in issues:
                magfile = issue['IssueFile']
                magimg = magfile.replace('.pdf', '.jpg')
                if not os.path.isfile(magimg):
                    magimg = 'images/nocover.png'
                else:
                    myhash = hashlib.md5(magimg).hexdigest()
                    cachedir = os.path.join(str(lazylibrarian.PROG_DIR),
                                            'data' + os.sep + 'images' + os.sep + 'cache')
                    if not os.path.isdir(cachedir):
                        os.makedirs(cachedir)
                    hashname = os.path.join(cachedir, myhash + ".jpg")
                    shutil.copyfile(magimg, hashname)
                    magimg = 'images/cache/' + myhash + '.jpg'

                this_issue = dict(issue)
                this_issue['Cover'] = magimg
                mod_issues.append(this_issue)

        return serve_template(templatename="issues.html", title=title, issues=mod_issues)
    issuePage.exposed = True

    def pastIssues(self, whichStatus=None):
        myDB = database.DBConnection()
        if whichStatus is None:
            whichStatus = "Skipped"
        issues = myDB.select('SELECT * from wanted WHERE Status="%s"' % (whichStatus))
        return serve_template(templatename="manageissues.html", title="Magazine Status Management",
                              issues=issues, whichStatus=whichStatus)
    pastIssues.exposed = True
    
    def openMag(self, bookid=None, **args):
        # we may want to open an issue with the full filename
        if bookid and os.path.isfile(bookid):
            logger.info(u'Opening file ' + bookid)
            return serve_file(bookid, "application/x-download", "attachment")

        # or we may just have a title to find magazine in issues table
        myDB = database.DBConnection()
        mag_data = myDB.select('SELECT * from issues WHERE Title="%s"' % bookid)
        if len(mag_data) == 1:  # we only have one issue, get it
            IssueDate = mag_data[0]["IssueDate"]
            IssueFile = mag_data[0]["IssueFile"]
            logger.info(u'Opening %s - %s' % (bookid, IssueDate))
            return serve_file(IssueFile, "application/x-download", "attachment")
        if len(mag_data) > 1:  # multiple issues, show a list
            logger.debug(u"%s has %s issues" % (bookid, len(mag_data)))
            raise cherrypy.HTTPRedirect("issuePage?title=%s" % bookid)
    openMag.exposed = True

    def markIssues(self, AuthorName=None, action=None, redirect=None, **args):
        myDB = database.DBConnection()
        if not redirect:
            redirect = "magazines"
        authorcheck = None
        maglist = []
        for nzburl in args:
            if hasattr(nzburl, 'decode'):
                    nzburl = nzburl.decode('utf-8')
            # ouch dirty workaround...
            if not nzburl == 'book_table_length':
                controlValueDict = {'NZBurl': nzburl}
                newValueDict = {'Status': action, 'NZBdate': formatter.today()}
                myDB.upsert("wanted", newValueDict, controlValueDict)
                title = myDB.select("SELECT * from wanted WHERE NZBurl = ?", [nzburl])
                for item in title:
                    nzburl = item['NZBurl']
                    if action == 'Delete':
                        myDB.action('DELETE from wanted WHERE NZBurl="%s"' % nzburl)
                        logger.debug(u'Item %s deleted from past issues' % nzburl)
                        maglist.append({'nzburl': nzburl})
                    else:
                        bookid = item['BookID']
                        nzbprov = item['NZBprov']
                        nzbtitle = item['NZBtitle']
                        nzbmode = item['NZBmode']
                        maglist.append({
                            'bookid': bookid,
                            'nzbprov': nzbprov,
                            'nzbtitle': nzbtitle,
                            'nzburl': nzburl,
                            'nzbmode': nzbmode
                        })

        if action == 'Delete':
            logger.info(u'Deleted %s items from past issues' % (len(maglist)))
        else:            
            logger.info(u'Status set to %s for %s past issues' % (action, len(maglist)))
        # start searchthreads
        if action == 'Wanted':
            for items in maglist:
                logger.debug(u'Snatching %s' % items['nzbtitle'])
                if items['nzbmode'] == 'torznab':
                    snatch = TORDownloadMethod(items['bookid'], items['nzbprov'], items['nzbtitle'], items['nzburl'])
                elif items['nzbmode'] == "torrent":
                    snatch = TORDownloadMethod(items['bookid'], items['nzbprov'], items['nzbtitle'], items['nzburl'])
                else:
                    snatch = NZBDownloadMethod(items['bookid'], items['nzbprov'], items['nzbtitle'], items['nzburl'])
                notifiers.notify_snatch(items['nzbtitle'] + ' at ' + formatter.now())
        raise cherrypy.HTTPRedirect("pastIssues")
    markIssues.exposed = True

    def markMagazines(self, action=None, **args):
        myDB = database.DBConnection()
        for item in args:
            # ouch dirty workaround...
            if not item == 'book_table_length':
                if (action == "Paused" or action == "Active"):
                    controlValueDict = {"Title": item}
                    newValueDict = {
                        "Status":       action,
                    }
                    myDB.upsert("magazines", newValueDict, controlValueDict)
                    logger.info(u'Status of magazine %s changed to %s' % (item, action))
                elif (action == "Delete"):
                    myDB.action('DELETE from magazines WHERE Title="%s"' % item)
                    myDB.action('DELETE from wanted WHERE BookID="%s"' % item)
                    myDB.action('DELETE from issues WHERE Title="%s"' % item)
                    logger.info(u'Magazine %s removed from database' % item)
                elif (action == "Reset"):
                    controlValueDict = {"Title": item}
                    newValueDict = {
                        "LastAcquired": None,
                        "IssueDate":    None,
                        "IssueStatus":  "Wanted"
                    }
                    myDB.upsert("magazines", newValueDict, controlValueDict)
                    logger.info(u'Magazine %s details reset' % item)

        raise cherrypy.HTTPRedirect("magazines")
    markMagazines.exposed = True

    def searchForMag(self, bookid=None, action=None, **args):
        myDB = database.DBConnection()

        bookdata = myDB.select('SELECT * from magazines WHERE Title="%s"' % bookid)
        if bookdata:
            # start searchthreads
            mags = []
            mags.append({"bookid": bookid})

            books = False
            if lazylibrarian.USE_NZB or lazylibrarian.USE_TOR:
                threading.Thread(target=search_magazines, args=[mags]).start()
                logger.debug(u"Searching for magazine with title: " + bookid)
            else:
                logger.debug("Not searching for magazine, no download methods set")
            raise cherrypy.HTTPRedirect("magazines")
    searchForMag.exposed = True

    def addMagazine(self, type=None, title=None, frequency=None, **args):
        myDB = database.DBConnection()
        if type == 'magazine':
            if len(title) == 0:
                raise cherrypy.HTTPRedirect("config")
            else:
                controlValueDict = {"Title": title}
                newValueDict = {
                    "Frequency":   frequency,
                    "Regex":   None,
                    "Status":       "Active",
                    "MagazineAdded":    formatter.today(),
                    "IssueStatus": "Wanted"
                }
                myDB.upsert("magazines", newValueDict, controlValueDict)

                mags = []
                mags.append({"bookid": title})
                books = False
                if lazylibrarian.USE_NZB or lazylibrarian.USE_TOR:
                    threading.Thread(target=search_magazines, args=[mags]).start()
                    logger.debug(u"Searching for magazine with title: " + title)
                else:
                    logger.debug(u"Not searching for magazine, no download methods set")
                raise cherrypy.HTTPRedirect("magazines")
    addMagazine.exposed = True

# UPDATES ###########################################################

    def checkForUpdates(self):
        # check the version when the application starts
        # Set the install type (win,git,source) &
        # check the version when the application starts
        versioncheck.getInstallType()
        lazylibrarian.CURRENT_VERSION = versioncheck.getCurrentVersion()
        lazylibrarian.LATEST_VERSION = versioncheck.getLatestVersion()
        lazylibrarian.COMMITS_BEHIND = versioncheck.getCommitDifferenceFromGit()
        raise cherrypy.HTTPRedirect("config")
    checkForUpdates.exposed = True

    def forceUpdate(self):
        from lazylibrarian import updater
        threading.Thread(target=updater.dbUpdate, args=[False]).start()
        raise cherrypy.HTTPRedirect("home")
    forceUpdate.exposed = True

    def update(self):
        logger.debug('(webServe-Update) - Performing update')
        lazylibrarian.SIGNAL = 'update'
        message = 'Updating...'
        return serve_template(templatename="shutdown.html", title="Updating", message=message, timer=120)
    update.exposed = True

# IMPORT/EXPORT #####################################################

    def libraryScan(self):
        try:
            threading.Thread(target=librarysync.LibraryScan(lazylibrarian.DESTINATION_DIR)).start()
        except Exception, e:
            logger.error(u'Unable to complete the scan: %s' % e)
        raise cherrypy.HTTPRedirect("home")
    libraryScan.exposed = True

    def magazineScan(self):
        try:
            threading.Thread(target=magazinescan.magazineScan()).start()
        except Exception, e:
            logger.error(u'Unable to complete the scan: %s' % e)
        raise cherrypy.HTTPRedirect("magazines")
    magazineScan.exposed = True

    def importAlternate(self):
        try:
            threading.Thread(target=postprocess.processAlternate(lazylibrarian.ALTERNATE_DIR)).start()
        except Exception, e:
            logger.error(u'Unable to complete the import: %s' % e)
        raise cherrypy.HTTPRedirect("manage")
    importAlternate.exposed = True

    def importCSV(self):
        try:
            threading.Thread(target=postprocess.processCSV(lazylibrarian.ALTERNATE_DIR)).start()
        except Exception, e:
            logger.error(u'Unable to complete the import: %s' % e)
        raise cherrypy.HTTPRedirect("manage")
    importCSV.exposed = True

    def exportCSV(self):
        try:
            threading.Thread(target=postprocess.exportCSV(lazylibrarian.ALTERNATE_DIR)).start()
        except Exception, e:
            logger.error(u'Unable to complete the export: %s' % e)
        raise cherrypy.HTTPRedirect("manage")
    exportCSV.exposed = True

# JOB CONTROL #######################################################

    def shutdown(self):
        lazylibrarian.config_write()
        lazylibrarian.SIGNAL = 'shutdown'
        message = 'closing ...'
        return serve_template(templatename="shutdown.html", title="Close library", message=message, timer=15)
    shutdown.exposed = True

    def restart(self):
        lazylibrarian.SIGNAL = 'restart'
        message = 'reopening ...'
        return serve_template(templatename="shutdown.html", title="Reopen library", message=message, timer=30)
    restart.exposed = True

    def showJobs(self):
        # show the current status of LL cron jobs in the log
        for job in lazylibrarian.SCHED.get_jobs():
            jobname = str(job).split(' ')[0].split('.')[2]
            if jobname == "search_magazines":
                jobname = "[CRON] - Check for new magazine issues"
            elif jobname == "checkForUpdates":
                jobname = "[CRON] - Check for LazyLibrarian update"
            elif jobname == "search_tor_book":
                jobname = "[CRON] - TOR book search"
            elif jobname == "search_nzb_book":
                jobname = "[CRON] - NZB book search"
            elif jobname == "processDir":
                jobname = "[CRON] - Process download directory"
            jobtime = str(job).split('[')[1].split('.')[0]
            logger.info(u"%s [%s" % (jobname, jobtime))
        logger.info(u"XMLCache %s hits, %s miss" % (int(lazylibrarian.CACHE_HIT), int(lazylibrarian.CACHE_MISS)))
        raise cherrypy.HTTPRedirect("logs")
    showJobs.exposed = True

    def restartJobs(self):
        # stop all of the LL cron jobs
        for job in lazylibrarian.SCHED.get_jobs():
            lazylibrarian.SCHED.unschedule_job(job)
        # and now restart them
        lazylibrarian.SCHED.add_interval_job(postprocess.processDir, minutes=int(lazylibrarian.SCAN_INTERVAL))

        if lazylibrarian.USE_NZB:
            lazylibrarian.SCHED.add_interval_job(search_nzb_book, minutes=int(lazylibrarian.SEARCH_INTERVAL))
        if lazylibrarian.USE_TOR:
            lazylibrarian.SCHED.add_interval_job(search_tor_book, minutes=int(lazylibrarian.SEARCH_INTERVAL))
        lazylibrarian.SCHED.add_interval_job(versioncheck.checkForUpdates,
                                             hours=int(lazylibrarian.VERSIONCHECK_INTERVAL))
        if lazylibrarian.USE_TOR or lazylibrarian.USE_NZB:
            lazylibrarian.SCHED.add_interval_job(search_magazines, minutes=int(lazylibrarian.SEARCH_INTERVAL))
        # and list the new run-times in the log
        self.showJobs()
    restartJobs.exposed = True

# LOGGING ###########################################################

    def clearLog(self):
        # Clear the log
        if os.path.exists(lazylibrarian.LOGDIR):
            try:
                shutil.rmtree(lazylibrarian.LOGDIR)
                os.mkdir(lazylibrarian.LOGDIR)
                lazylibrarian.LOGLIST = []
            except OSError, e:
                logger.info(u'Failed to clear log: ' + str(e))
        raise cherrypy.HTTPRedirect("logs")
    clearLog.exposed = True

    def toggleLog(self):
        # Toggle the debug log
        # LOGLEVEL 0, quiet
        # 1 normal
        # 2 debug
        # >2 do not turn off file/console log
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
    toggleLog.exposed = True

    def logs(self):
        return serve_template(templatename="logs.html", title="Log", lineList=lazylibrarian.LOGLIST)
    logs.exposed = True

    def getLog(self, iDisplayStart=0, iDisplayLength=100, iSortCol_0=0, sSortDir_0="desc", sSearch="", **kwargs):
        iDisplayStart = int(iDisplayStart)
        iDisplayLength = int(iDisplayLength)
        filtered = []
        if sSearch == "":
            filtered = lazylibrarian.LOGLIST[::]
        else:
            filtered = [row for row in lazylibrarian.LOGLIST for column in row if sSearch in column]

        sortcolumn = 0
        if iSortCol_0 == '1':
            sortcolumn = 2
        elif iSortCol_0 == '2':
            sortcolumn = 1
        filtered.sort(key=lambda x: x[sortcolumn], reverse=sSortDir_0 == "desc")
        if iDisplayLength < 0:  # display = all
            rows = filtered
        else:
            rows = filtered[iDisplayStart:(iDisplayStart + iDisplayLength)]
        rows = [[row[0], row[2], row[1]] for row in rows]
        dict = {'iTotalDisplayRecords': len(filtered),
                'iTotalRecords': len(lazylibrarian.LOGLIST),
                'aaData': rows,
                }
        s = simplejson.dumps(dict)
        return s
    getLog.exposed = True

# HISTORY ###########################################################

    def history(self, source=None):
        myDB = database.DBConnection()
        if not source:
            # wanted status holds snatched processed for all, plus skipped and ignored for magazine back issues
            history = myDB.select("SELECT * from wanted WHERE Status != 'Skipped' and Status != 'Ignored'")
            return serve_template(templatename="history.html", title="History", history=history)
    history.exposed = True

    def clearhistory(self, type=None):
        myDB = database.DBConnection()
        if type == 'all':
            logger.info(u"Clearing all history")
            myDB.action("DELETE from wanted WHERE Status != 'Skipped' and Status != 'Ignored'")
        else:
            logger.info(u"Clearing history where status is %s" % type)
            myDB.action('DELETE from wanted WHERE Status="%s"' % type)
        raise cherrypy.HTTPRedirect("history")
    clearhistory.exposed = True

# NOTIFIERS #########################################################

    @cherrypy.expose
    def twitterStep1(self):
        cherrypy.response.headers['Cache-Control'] = "max-age=0,no-cache,no-store"

        return notifiers.twitter_notifier._get_authorization()

    @cherrypy.expose
    def twitterStep2(self, key):
        cherrypy.response.headers['Cache-Control'] = "max-age=0,no-cache,no-store"

        result = notifiers.twitter_notifier._get_credentials(key)
        logger.info(u"result: " + str(result))
        if result:
            return "Key verification successful"
        else:
            return "Unable to verify key"

    @cherrypy.expose
    def testTwitter(self):
        cherrypy.response.headers['Cache-Control'] = "max-age=0,no-cache,no-store"

        result = notifiers.twitter_notifier.test_notify()
        if result:
            return "Tweet successful, check your twitter to make sure it worked"
        else:
            return "Error sending tweet"

    @cherrypy.expose
    def testAndroidPN(self, url=None, username=None, broadcast=None):
        cherrypy.response.headers['Cache-Control'] = "max-age=0,no-cache,no-store"

        result = notifiers.androidpn_notifier.test_notify(url, username, broadcast)
        if result:
            return "Test AndroidPN notice sent successfully"
        else:
            return "Test AndroidPN notice failed"

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

# ALL ELSE ##########################################################

    def forceProcess(self, source=None):
        threading.Thread(target=postprocess.processDir(force=True)).start()
        raise cherrypy.HTTPRedirect(source)
    forceProcess.exposed = True

    def forceSearch(self, source=None):
        if source == "magazines":
            threading.Thread(target=search_magazines).start()
        else:
            if (lazylibrarian.USE_NZB):
                threading.Thread(target=search_nzb_book).start()
            if (lazylibrarian.USE_TOR):
                threading.Thread(target=search_tor_book).start()
        raise cherrypy.HTTPRedirect(source)
    forceSearch.exposed = True

    def manage(self, AuthorName=None, action=None, whichStatus=None, source=None, **args):
        myDB = database.DBConnection()
        # books only holds status [skipped wanted open have ignored]
        # wanted holds status [snatched processed]
        books = myDB.select('SELECT * FROM books WHERE Status = ?', [whichStatus])
        return serve_template(templatename="managebooks.html", title="Book Status Management",
                              books=books, whichStatus=whichStatus)
    manage.exposed = True

#    def markWanted(self, action=None, **args):
#        myDB = database.DBConnection()
#
#        for nzbtitle in args:
#            if not nzbtitle == 'book_table_length':
#                if action != "Delete":
#                    controlValueDict = {"NZBtitle": nzbtitle}
#                    newValueDict = {
#                        "Status": action,
#                        "NZBDate": formatter.today()  # mark when we wanted it
#                    }
#                    myDB.upsert("wanted", newValueDict, controlValueDict)
#                    logger.info(u'Status of wanted item %s changed to %s' % (nzbtitle, action))
#                else:
#                    myDB.action('DELETE from wanted WHERE NZBtitle="%s"' % nzbtitle)
#                    logger.info(u'Item %s removed from wanted' % nzbtitle)
#                raise cherrypy.HTTPRedirect("wanted")
#    markWanted.exposed = True

#    def updateRegex(self, action=None, title=None):
#        myDB = database.DBConnection()
#        controlValueDict = {"Title": title}
#        newValueDict = {
#            "Regex":       action,
#        }
#        myDB.upsert("magazines", newValueDict, controlValueDict)
#        raise cherrypy.HTTPRedirect("magazines")
#    updateRegex.exposed = True
