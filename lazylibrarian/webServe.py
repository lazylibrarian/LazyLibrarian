import os, cherrypy, urllib
from cherrypy.lib.static import serve_file
from mako.template import Template
from mako.lookup import TemplateLookup
from mako import exceptions
from operator import itemgetter

import thread, threading, time, Queue

import lazylibrarian

from lazylibrarian import logger, importer, database, postprocess, formatter, notifiers
from lazylibrarian.searchnzb import searchbook
from lazylibrarian.searchmag import searchmagazines
from lazylibrarian.formatter import checked
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
    index.exposed=True

    def home(self):
        myDB = database.DBConnection()
        authors = myDB.select('SELECT * from authors order by AuthorName COLLATE NOCASE')
        return serve_template(templatename="index.html", title="Home", authors=authors)
    home.exposed = True

    def books(self, BookLang=None):
        myDB = database.DBConnection()

        languages = myDB.select('SELECT DISTINCT BookLang from books WHERE NOT STATUS="Skipped" AND NOT STATUS="Ignored"')

        if BookLang:
            books = myDB.select('SELECT * from books WHERE BookLang=? AND NOT Status="Skipped" AND NOT STATUS="Ignored"', [BookLang])
        else:
            books = myDB.select('SELECT * from books WHERE NOT STATUS="Skipped" AND NOT STATUS="Ignored"')

        if books is None:
            raise cherrypy.HTTPRedirect("books")
        return serve_template(templatename="books.html", title='Books', books=books, languages=languages)
    books.exposed = True

    def config(self):
        http_look_dir = os.path.join(lazylibrarian.PROG_DIR, 'data/interfaces/')
        http_look_list = [ name for name in os.listdir(http_look_dir) if os.path.isdir(os.path.join(http_look_dir, name)) ]

        config = {
                    "http_host":        lazylibrarian.HTTP_HOST,
                    "http_user":        lazylibrarian.HTTP_USER,
                    "http_port":        lazylibrarian.HTTP_PORT,
                    "http_pass":        lazylibrarian.HTTP_PASS,
                    "http_look":        lazylibrarian.HTTP_LOOK,
                    "http_look_list":   http_look_list,
                    "launch_browser":   checked(lazylibrarian.LAUNCH_BROWSER),
                    "logdir" :          lazylibrarian.LOGDIR,
                    "use_imp_onlyisbn": checked(lazylibrarian.IMP_ONLYISBN),
                    "imp_preflang":     lazylibrarian.IMP_PREFLANG,
                    "imp_autoadd":      lazylibrarian.IMP_AUTOADD,
                    "sab_host":         lazylibrarian.SAB_HOST,
                    "sab_port":         lazylibrarian.SAB_PORT,
                    "sab_subdir":         lazylibrarian.SAB_SUBDIR,                    
                    "sab_api":          lazylibrarian.SAB_API,
                    "sab_user":         lazylibrarian.SAB_USER,
                    "sab_pass":         lazylibrarian.SAB_PASS,
                    "destination_copy": checked(lazylibrarian.DESTINATION_COPY),
                    "destination_dir":  lazylibrarian.DESTINATION_DIR,
                    "download_dir":     lazylibrarian.DOWNLOAD_DIR,
                    "sab_cat":          lazylibrarian.SAB_CAT,
                    "usenet_retention": lazylibrarian.USENET_RETENTION,
                    "use_blackhole":    checked(lazylibrarian.BLACKHOLE),
                    "blackholedir":     lazylibrarian.BLACKHOLEDIR,
                    "use_newznab" :     checked(lazylibrarian.NEWZNAB),
                    "newznab_host" :    lazylibrarian.NEWZNAB_HOST,
                    "newznab_api" :     lazylibrarian.NEWZNAB_API,
                    "use_newznab2" :     checked(lazylibrarian.NEWZNAB2),
                    "newznab_host2" :    lazylibrarian.NEWZNAB_HOST2,
                    "newznab_api2" :     lazylibrarian.NEWZNAB_API2,
                    "use_newzbin" :     checked(lazylibrarian.NEWZBIN),
                    "newzbin_uid" :     lazylibrarian.NEWZBIN_UID,
                    "newzbin_pass" :    lazylibrarian.NEWZBIN_PASS,

                    "use_usenetcrawler" :     checked(lazylibrarian.USENETCRAWLER),
                    "usenetcrawler_host" :     lazylibrarian.USENETCRAWLER_HOST,
                    "usenetcrawler_api" :    lazylibrarian.USENETCRAWLER_API,
                    "search_interval" :    int(lazylibrarian.SEARCH_INTERVAL),
                    "scan_interval" :    int(lazylibrarian.SCAN_INTERVAL),
                    "versioncheck_interval" :    int(lazylibrarian.VERSIONCHECK_INTERVAL),
                    "ebook_dest_folder": lazylibrarian.EBOOK_DEST_FOLDER,
                    "ebook_dest_file": lazylibrarian.EBOOK_DEST_FILE,
                    "mag_dest_folder": lazylibrarian.MAG_DEST_FOLDER,
                    "mag_dest_file": lazylibrarian.MAG_DEST_FILE,
                    "use_twitter" :     checked(lazylibrarian.USE_TWITTER),
                    "twitter_notify_onsnatch" :     checked(lazylibrarian.TWITTER_NOTIFY_ONSNATCH),
                    "twitter_notify_ondownload" :     checked(lazylibrarian.TWITTER_NOTIFY_ONDOWNLOAD), 
		    "use_boxcar" : 	checked(lazylibrarian.USE_BOXCAR),
		    "boxcar_notify_onsnatch" :     checked(lazylibrarian.BOXCAR_NOTIFY_ONSNATCH),
		    "boxcar_notify_ondownload" :     checked(lazylibrarian.BOXCAR_NOTIFY_ONDOWNLOAD),
		    "boxcar_token" :		lazylibrarian.BOXCAR_TOKEN,

                    "ebook_type" :		lazylibrarian.EBOOK_TYPE,
                    "gr_api" :		lazylibrarian.GR_API,
                    "gb_api" :      lazylibrarian.GB_API,
                    "book_api" :    lazylibrarian.BOOK_API
                }
        return serve_template(templatename="config.html", title="Settings", config=config)    
    config.exposed = True

    def configUpdate(self, http_host='0.0.0.0', http_user=None, http_port=5299, http_pass=None, http_look=None, launch_browser=0, logdir=None, imp_onlyisbn=0, imp_preflang=None, imp_autoadd=None,
        sab_host=None, sab_port=None, sab_subdir=None, sab_api=None, sab_user=None, sab_pass=None, destination_copy=0, destination_dir=None, download_dir=None, sab_cat=None, usenet_retention=None, blackhole=0, blackholedir=None,
        newznab=0, newznab_host=None, newznab_api=None, newznab2=0, newznab_host2=None, newznab_api2=None,newzbin=0, newzbin_uid=None, newzbin_pass=None, ebook_type=None, book_api=None, gr_api=None, gb_api=None, usenetcrawler = 0, usenetcrawler_host=None, usenetcrawler_api = None, 
        versioncheck_interval=None, search_interval=None, scan_interval=None, ebook_dest_folder=None, ebook_dest_file=None, mag_dest_folder=None, mag_dest_file=None, use_twitter=0, twitter_notify_onsnatch=0, twitter_notify_ondownload=0,
	use_boxcar=0, boxcar_notify_onsnatch=0, boxcar_notify_ondownload=0, boxcar_token=None):

        lazylibrarian.HTTP_HOST = http_host
        lazylibrarian.HTTP_PORT = http_port
        lazylibrarian.HTTP_USER = http_user
        lazylibrarian.HTTP_PASS = http_pass
        lazylibrarian.HTTP_LOOK = http_look
        lazylibrarian.LAUNCH_BROWSER = launch_browser
        lazylibrarian.LOGDIR = logdir

        lazylibrarian.IMP_ONLYISBN = imp_onlyisbn
        lazylibrarian.IMP_PREFLANG = imp_preflang
        lazylibrarian.IMP_AUTOADD  = imp_autoadd

        lazylibrarian.SAB_HOST = sab_host
        lazylibrarian.SAB_PORT = sab_port
        lazylibrarian.SAB_SUBDIR = sab_subdir
        lazylibrarian.SAB_API = sab_api
        lazylibrarian.SAB_USER = sab_user
        lazylibrarian.SAB_PASS = sab_pass
        lazylibrarian.SAB_CAT = sab_cat

        lazylibrarian.DESTINATION_COPY = destination_copy
        lazylibrarian.DESTINATION_DIR = destination_dir
        lazylibrarian.DOWNLOAD_DIR = download_dir
        lazylibrarian.USENET_RETENTION = usenet_retention
        lazylibrarian.BLACKHOLE = blackhole
        lazylibrarian.BLACKHOLEDIR = blackholedir

        lazylibrarian.NEWZNAB = newznab
        lazylibrarian.NEWZNAB_HOST = newznab_host
        lazylibrarian.NEWZNAB_API = newznab_api

        lazylibrarian.NEWZNAB2 = newznab2
        lazylibrarian.NEWZNAB_HOST2 = newznab_host2
        lazylibrarian.NEWZNAB_API2 = newznab_api2

        lazylibrarian.NEWZBIN = newzbin
        lazylibrarian.NEWZBIN_UID = newzbin_uid
        lazylibrarian.NEWZBIN_PASS = newzbin_pass

        lazylibrarian.USENETCRAWLER = usenetcrawler
        lazylibrarian.USENETCRAWLER_HOST = usenetcrawler_host
        lazylibrarian.USENETCRAWLER_API = usenetcrawler_api

        lazylibrarian.EBOOK_TYPE = ebook_type
        lazylibrarian.BOOK_API = book_api
        lazylibrarian.GR_API = gr_api
        lazylibrarian.GB_API = gb_api

        lazylibrarian.SEARCH_INTERVAL = search_interval
        lazylibrarian.SCAN_INTERVAL = scan_interval
        lazylibrarian.VERSIONCHECK_INTERVAL = versioncheck_interval

        lazylibrarian.EBOOK_DEST_FOLDER = ebook_dest_folder
        lazylibrarian.EBOOK_DEST_FILE = ebook_dest_file
        lazylibrarian.MAG_DEST_FOLDER = mag_dest_folder
        lazylibrarian.MAG_DEST_FILE = mag_dest_file

        lazylibrarian.USE_TWITTER = use_twitter
        lazylibrarian.TWITTER_NOTIFY_ONSNATCH = twitter_notify_onsnatch
        lazylibrarian.TWITTER_NOTIFY_ONDOWNLOAD = twitter_notify_ondownload

	lazylibrarian.USE_BOXCAR = use_boxcar
	lazylibrarian.BOXCAR_NOTIFY_ONSNATCH = boxcar_notify_onsnatch
	lazylibrarian.BOXCAR_NOTIFY_ONDOWNLOAD = boxcar_notify_ondownload
	lazylibrarian.BOXCAR_TOKEN = boxcar_token

        lazylibrarian.config_write()

        logger.debug('Config file has been updated')
        raise cherrypy.HTTPRedirect("config")

    configUpdate.exposed = True

    def update(self):
        logger.debug('(webServe-Update) - Performing update')
        lazylibrarian.SIGNAL = 'update'
        message = 'Updating...'
        return serve_template(templatename="shutdown.html", title="Updating", message=message, timer=120)
        return page
    update.exposed = True

#SEARCH
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
        return serve_template(templatename="searchresults.html", title='Search Results for: "' + name + '"', searchresults=sortedlist_final, authorlist=authorlist, booklist=booklist, booksearch=booksearch, type=type)
    search.exposed = True

#AUTHOR
    def authorPage(self, AuthorName, BookLang=None, Ignored=False):
        myDB = database.DBConnection()

        if Ignored:
            languages = myDB.select("SELECT DISTINCT BookLang from books WHERE AuthorName LIKE ? AND Status ='Ignored'", [AuthorName.replace("'","''")])
            if BookLang:
                querybooks = "SELECT * from books WHERE AuthorName LIKE '%s' AND BookLang = '%s' AND Status ='Ignored' order by BookDate DESC, BookRate DESC" % (AuthorName.replace("'","''"), BookLang)
            else:
                querybooks = "SELECT * from books WHERE AuthorName LIKE '%s' and Status ='Ignored' order by BookDate DESC, BookRate DESC" % (AuthorName.replace("'","''"))
        else:
            languages = myDB.select("SELECT DISTINCT BookLang from books WHERE AuthorName LIKE ? AND Status !='Ignored'", [AuthorName.replace("'","''")])
            if BookLang:
                querybooks = "SELECT * from books WHERE AuthorName LIKE '%s' AND BookLang = '%s' AND Status !='Ignored' order by BookDate DESC, BookRate DESC" % (AuthorName.replace("'","''"), BookLang)
            else:
                querybooks = "SELECT * from books WHERE AuthorName LIKE '%s' and Status !='Ignored' order by BookDate DESC, BookRate DESC" % (AuthorName.replace("'","''"))

        queryauthors = "SELECT * from authors WHERE AuthorName LIKE '%s'" % AuthorName.replace("'","''")

        author = myDB.action(queryauthors).fetchone()
        books = myDB.select(querybooks)
        if author is None:
            raise cherrypy.HTTPRedirect("home")
        return serve_template(templatename="author.html", title=author['AuthorName'], author=author, books=books, languages=languages)
    authorPage.exposed = True

    def pauseAuthor(self, AuthorID):
        myDB = database.DBConnection()
        authorsearch = myDB.select('SELECT AuthorName from authors WHERE AuthorID=?', [AuthorID])
        AuthorName = authorsearch[0]['AuthorName']
        logger.info("Pausing author: %s" % AuthorName)

        controlValueDict = {'AuthorID': AuthorID}
        newValueDict = {'Status': 'Paused'}
        myDB.upsert("authors", newValueDict, controlValueDict)
        logger.debug('AuthorID [%s]-[%s] Paused - redirecting to Author home page' % (AuthorID,AuthorName))
        raise cherrypy.HTTPRedirect("authorPage?AuthorName=%s" % AuthorName)
    pauseAuthor.exposed = True

    def resumeAuthor(self, AuthorID):
        myDB = database.DBConnection()
        authorsearch = myDB.select('SELECT AuthorName from authors WHERE AuthorID=?', [AuthorID])
        AuthorName = authorsearch[0]['AuthorName']
        logger.info("Resuming author: %s" % AuthorName)

        controlValueDict = {'AuthorID': AuthorID}
        newValueDict = {'Status': 'Active'}
        myDB.upsert("authors", newValueDict, controlValueDict)
        logger.debug('AuthorID [%s]-[%s] Restarted - redirecting to Author home page' % (AuthorID,AuthorName))
        raise cherrypy.HTTPRedirect("authorPage?AuthorName=%s" % AuthorName)
    resumeAuthor.exposed = True

    def deleteAuthor(self, AuthorID):
        myDB = database.DBConnection()
        authorsearch = myDB.select('SELECT AuthorName from authors WHERE AuthorID=?', [AuthorID])
        AuthorName = authorsearch[0]['AuthorName']
        logger.info("Removing all references to author: %s" % AuthorName)

        myDB.action('DELETE from authors WHERE AuthorID=?', [AuthorID])
        myDB.action('DELETE from books WHERE AuthorID=?', [AuthorID])
        raise cherrypy.HTTPRedirect("home")
    deleteAuthor.exposed = True

    def refreshAuthor(self, AuthorName):
        refresh = True
        threading.Thread(target=importer.addAuthorToDB, args=(AuthorName, refresh)).start()
        raise cherrypy.HTTPRedirect("authorPage?AuthorName=%s" % AuthorName)
    refreshAuthor.exposed=True

    def addResults(self, authorname):
        args = None;
        threading.Thread(target=importer.addAuthorToDB, args=[authorname]).start()
        raise cherrypy.HTTPRedirect("authorPage?AuthorName=%s" % authorname)
    addResults.exposed = True

    def addBook(self, bookid=None):
        myDB = database.DBConnection()

        booksearch = myDB.select("SELECT * from books WHERE BookID=?", [bookid])
        if booksearch:
            myDB.upsert("books", {'Status': 'Wanted'}, {'BookID': bookid})
            for book in booksearch:
                AuthorName = book['AuthorName']
                authorsearch = myDB.select("SELECT * from authors WHERE AuthorName=?", [AuthorName])
                if authorsearch:
                    #update authors needs to be updated every time a book is marked differently
                    lastbook = myDB.action("SELECT BookName, BookLink, BookDate from books WHERE AuthorName='%s' AND Status != 'Ignored' order by BookDate DESC" % AuthorName).fetchone()
                    unignoredbooks = myDB.select("SELECT COUNT(BookName) as unignored FROM books WHERE AuthorName='%s' AND Status != 'Ignored'" % AuthorName)
                    bookCount = myDB.select("SELECT COUNT(BookName) as counter FROM books WHERE AuthorName='%s'" % AuthorName)  
                    countbooks = myDB.action('SELECT COUNT(*) FROM books WHERE AuthorName="%s" AND (Status="Have" OR Status="Open")' % AuthorName).fetchone()
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
        threading.Thread(target=searchbook, args=[books, mags]).start()

        raise cherrypy.HTTPRedirect("books")
    addBook.exposed = True

#BOOKS
    def openBook(self, bookid=None, **args):
        myDB = database.DBConnection()

        # find book
        bookdata = myDB.select('SELECT * from books WHERE BookID=?', [bookid])
        if bookdata:
            authorName = bookdata[0]["AuthorName"];
            bookName = bookdata[0]["BookName"];

            dic = {'<':'', '>':'', '=':'', '?':'', '"':'', ',':'', '*':'', ':':'', ';':'', '\'':''}
            bookName = formatter.latinToAscii(formatter.replace_all(bookName, dic))
            
            pp_dir = lazylibrarian.DESTINATION_DIR
            ebook_path = lazylibrarian.EBOOK_DEST_FOLDER.replace('$Author', authorName).replace('$Title', bookName)
            dest_dir = os.path.join(pp_dir, ebook_path)

            logger.debug('bookdir ' + dest_dir);
            if os.path.isdir(dest_dir):
                for file2 in os.listdir(dest_dir):	
                    if ((file2.lower().find(".jpg") <= 0) & (file2.lower().find(".opf") <= 0)):
                        logger.info('Opening file ' + str(file2))
                        return serve_file(os.path.join(dest_dir, file2), "application/x-download", "attachment")
    openBook.exposed = True

    def openMag(self, bookid=None, **args):
        myDB = database.DBConnection()

        # find book
        bookdata = myDB.select('SELECT * from magazines WHERE Title=?', [bookid])
        if bookdata:
            Title = bookdata[0]["Title"];
            IssueDate = bookdata[0]["IssueDate"];

            dic = {'<':'', '>':'', '=':'', '?':'', '"':'', ',':'', '*':'', ':':'', ';':'', '\'':''}
            bookName = formatter.latinToAscii(formatter.replace_all(Title, dic))
            
            pp_dir = lazylibrarian.DESTINATION_DIR
            mag_path = lazylibrarian.MAG_DEST_FOLDER.replace('$IssueDate', IssueDate).replace('$Title', Title)
            dest_dir = os.path.join(pp_dir, mag_path)

            logger.debug('bookdir ' + dest_dir);
            if os.path.isdir(dest_dir):
                for file2 in os.listdir(dest_dir):  
                    if ((file2.lower().find(".jpg") <= 0) & (file2.lower().find(".opf") <= 0)):
                        logger.info('Opening file ' + str(file2))
                        return serve_file(os.path.join(dest_dir, file2), "application/x-download", "attachment")
    openMag.exposed = True

    def searchForBook(self, bookid=None, action=None, **args):
        myDB = database.DBConnection()

        # find book
        bookdata = myDB.select("SELECT * from books WHERE BookID='%s'" % bookid)
        if bookdata:
            AuthorName = bookdata[0]["AuthorName"];

            # start searchthreads
            books = []
            books.append({"bookid": bookid})

            mags=False

            threading.Thread(target=searchbook, args=[books, mags]).start()
            logger.debug("Searching for book with id: " + str(bookid));
        if AuthorName:
            raise cherrypy.HTTPRedirect("authorPage?AuthorName=%s" % AuthorName)
    searchForBook.exposed = True

    def markBooks(self, AuthorName=None, action=None, **args):
        myDB = database.DBConnection()
        if AuthorName:
            redirect = "author"
        else:
            redirect = "books"
        authorcheck = None
        for bookid in args:
            # ouch dirty workaround...
            if not bookid == 'book_table_length':
                if action != "Remove":
                    controlValueDict = {'BookID': bookid}
                    newValueDict = {'Status': action}
                    myDB.upsert("books", newValueDict, controlValueDict)
                    title = myDB.select("SELECT * from books WHERE BookID = ?", [bookid])
                    for item in title:
                        bookname = item['BookName']
                    logger.info('Status set to %s for %s' % (action, bookname))
              
                else:
                    authorsearch = myDB.select("SELECT * from books WHERE BookID = ?", [bookid])
                    for item in authorsearch:
                        AuthorName = item['AuthorName']
                        bookname = item['BookName']
                    authorcheck = myDB.select("SELECT * from authors WHERE AuthorName = ?", [AuthorName])
                    if authorcheck:
                        myDB.upsert("books", {"Status": "Skipped"}, {"BookID": bookid})
                        logger.info('Status set to Skipped for %s' % bookname)
                    else:
                        myDB.action('DELETE from books WHERE BookID = ?', [bookid])
                        logger.info('%s removed from database' % bookname)

        if redirect == "author" or authorcheck:
            #update authors needs to be updated every time a book is marked differently
            lastbook = myDB.action("SELECT BookName, BookLink, BookDate from books WHERE AuthorName='%s' AND Status != 'Ignored' order by BookDate DESC" % AuthorName).fetchone()
            unignoredbooks = myDB.select("SELECT COUNT(BookName) as unignored FROM books WHERE AuthorName='%s' AND Status != 'Ignored'" % AuthorName)
            bookCount = myDB.select("SELECT COUNT(BookName) as counter FROM books WHERE AuthorName='%s'" % AuthorName)  
            countbooks = myDB.action('SELECT COUNT(*) FROM books WHERE AuthorName="%s" AND (Status="Have" OR Status="Open")' % AuthorName).fetchone()
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
            mags=False
            threading.Thread(target=searchbook, args=[books, mags]).start()

        if redirect == "author":
            raise cherrypy.HTTPRedirect("authorPage?AuthorName=%s" % AuthorName)
        else:
            raise cherrypy.HTTPRedirect("books")
    markBooks.exposed = True

    #ALL ELSE
    def forceProcess(self, source=None):
        threading.Thread(target=postprocess.processDir).start()
        raise cherrypy.HTTPRedirect(source)
    forceProcess.exposed = True

    def forceSearch(self, source=None):
        threading.Thread(target=searchbook).start()
        raise cherrypy.HTTPRedirect(source)
    forceSearch.exposed = True

    def checkForUpdates(self):
        #check the version when the application starts
        from lazylibrarian import versioncheck
        #Set the install type (win,git,source) & 
        #check the version when the application starts
        versioncheck.getInstallType()
        lazylibrarian.CURRENT_VERSION = versioncheck.getCurrentVersion()
        lazylibrarian.LATEST_VERSION = versioncheck.getLatestVersion()
        lazylibrarian.COMMITS_BEHIND = versioncheck.getCommitDifferenceFromGit()
        raise cherrypy.HTTPRedirect("config")
    checkForUpdates.exposed = True

    def getLog(self,iDisplayStart=0,iDisplayLength=100,iSortCol_0=0,sSortDir_0="desc",sSearch="",**kwargs):
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
        filtered.sort(key=lambda x:x[sortcolumn],reverse=sSortDir_0 == "desc")        

        rows = filtered[iDisplayStart:(iDisplayStart+iDisplayLength)]
        rows = [[row[0],row[2],row[1]] for row in rows]

        dict = {'iTotalDisplayRecords':len(filtered),
                'iTotalRecords':len(lazylibrarian.LOGLIST),
                'aaData':rows,
                }
        s = simplejson.dumps(dict)
        return s
    getLog.exposed = True

    def history(self, source=None):
        myDB = database.DBConnection()
        if not source:
            history = myDB.select("SELECT * from wanted WHERE Status != 'Skipped'")
        elif source == "magazines":
            history = myDB.select("SELECT * from wanted WHERE Status = 'Skipped'")
        return serve_template(templatename="history.html", title="History", history=history)
    history.exposed = True

    def clearhistory(self, type=None):
        myDB = database.DBConnection()
        if type == 'all':
            logger.info(u"Clearing all history")
            myDB.action('DELETE from wanted')
        else:
            logger.info(u"Clearing history where status is %s" % type)
            myDB.action('DELETE from wanted WHERE Status=?', [type])
        raise cherrypy.HTTPRedirect("history")
    clearhistory.exposed = True

    def magazines(self):
        myDB = database.DBConnection()

        magazines = myDB.select('SELECT * from magazines')

        if magazines is None:
            raise cherrypy.HTTPRedirect("magazines")
        return serve_template(templatename="magazines.html", title="Magazines", magazines=magazines)
    magazines.exposed = True

    def addKeyword(self, type=None, title=None, frequency=None, **args):
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
                books=False
                threading.Thread(target=searchbook, args=[books, mags]).start()
                logger.debug("Searching for magazine with title: " + str(title));
                raise cherrypy.HTTPRedirect("magazines")
    addKeyword.exposed = True

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
                    logger.info('Status of magazine %s changed to %s' % (item, action))
                elif (action == "Delete"):
                    myDB.action('DELETE from magazines WHERE Title=?', [item])
                    logger.info('Magazine %s removed from database' % item)
                elif (action == "Reset"):
                    controlValueDict = {"Title": item}
                    newValueDict = {
                        "LastAcquired": None,
                        "IssueDate":    None,
                        "IssueStatus":  "Wanted"
                        }
                    myDB.upsert("magazines", newValueDict, controlValueDict)
                    logger.info('Magazine %s details reset' % item)

        raise cherrypy.HTTPRedirect("magazines")
    markMagazines.exposed = True

    def searchForMag(self, bookid=None, action=None, **args):
        myDB = database.DBConnection()

        # find book
        bookdata = myDB.select("SELECT * from magazines WHERE Title='%s'" % bookid)
        if bookdata:
            # start searchthreads
            mags = []
            mags.append({"bookid": bookid})

            books=False

            threading.Thread(target=searchbook, args=[books, mags]).start()
            logger.debug("Searching for magazine with title: " + str(bookid));
            raise cherrypy.HTTPRedirect("magazines")
    searchForMag.exposed = True

    def markWanted(self, action=None, **args):
        myDB = database.DBConnection()
        #I think I need to consolidate bookid in args to unique values...
        for nzbtitle in args:
            if not nzbtitle == 'book_table_length':
                if action != "Delete":
                    controlValueDict = {"NZBtitle": nzbtitle}
                    newValueDict = {
                        "Status":       action,
                        }
                    myDB.upsert("wanted", newValueDict, controlValueDict)
                    logger.info('Status of wanted item %s changed to %s' % (nzbtitle, action))
                else:
                    myDB.action('DELETE from wanted WHERE NZBtitle=?', [nzbtitle])
                    logger.info('Item %s removed from wanted' % nzbtitle)
                raise cherrypy.HTTPRedirect("wanted")
    markWanted.exposed = True

    def updateRegex(self, action=None, title=None):
        myDB = database.DBConnection()
        controlValueDict = {"Title": title}
        newValueDict = {
            "Regex":       action,
            }
        myDB.upsert("magazines", newValueDict, controlValueDict)
        raise cherrypy.HTTPRedirect("magazines")
    updateRegex.exposed = True

    def forceUpdate(self):
        from lazylibrarian import updater
        threading.Thread(target=updater.dbUpdate, args=[False]).start()
        raise cherrypy.HTTPRedirect("home")
    forceUpdate.exposed = True

    def logs(self):
        return serve_template(templatename="logs.html", title="Log", lineList=lazylibrarian.LOGLIST)
    logs.exposed = True

    @cherrypy.expose
    def twitterStep1(self):
        cherrypy.response.headers['Cache-Control'] = "max-age=0,no-cache,no-store"

        return notifiers.twitter_notifier._get_authorization()

    @cherrypy.expose
    def twitterStep2(self, key):
        cherrypy.response.headers['Cache-Control'] = "max-age=0,no-cache,no-store"

        result = notifiers.twitter_notifier._get_credentials(key)
        logger.info(u"result: "+str(result))
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

    def shutdown(self):
        lazylibrarian.config_write()
        lazylibrarian.SIGNAL = 'shutdown'
        message = 'closing ...'
        return serve_template(templatename="shutdown.html", title="Close library", message=message, timer=15)
        return page
    shutdown.exposed = True

    def restart(self):
        lazylibrarian.SIGNAL = 'restart'
        message = 'reopening ...'
        return serve_template(templatename="shutdown.html", title="Reopen library", message=message, timer=30)
    restart.exposed = True
