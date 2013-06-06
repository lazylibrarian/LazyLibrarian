import os, cherrypy, urllib
from cherrypy.lib.static import serve_file
from mako.template import Template
from mako.lookup import TemplateLookup
from mako import exceptions

import threading, time

import lazylibrarian

from lazylibrarian import logger, importer, database, postprocess, formatter
from lazylibrarian.searchnzb import searchbook
from lazylibrarian.formatter import checked
from lazylibrarian.gr import GoodReads

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

        languages = myDB.select('SELECT DISTINCT BookLang from books WHERE NOT STATUS="Skipped"')

        if BookLang:
            books = myDB.select('SELECT * from books WHERE BookLang=? AND NOT Status="Skipped"', [BookLang])
        else:
            books = myDB.select('SELECT * from books WHERE NOT STATUS="Skipped"')

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
                    "sab_host":         lazylibrarian.SAB_HOST,
                    "sab_port":         lazylibrarian.SAB_PORT,
                    "sab_api":          lazylibrarian.SAB_API,
                    "sab_user":         lazylibrarian.SAB_USER,
                    "sab_pass":         lazylibrarian.SAB_PASS,
                    "use_destination_copy": checked(lazylibrarian.DESTINATION_COPY),
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
                    "ebook_type" :		lazylibrarian.EBOOK_TYPE,
                    "gr_api" :		lazylibrarian.GR_API,
                }
        return serve_template(templatename="config.html", title="Settings", config=config)    
    config.exposed = True

    def configUpdate(self, http_host='0.0.0.0', http_user=None, http_port=5299, http_pass=None, http_look=None, launch_browser=0, logdir=None, imp_onlyisbn=0, imp_preflang=None,
        sab_host=None, sab_port=None, sab_api=None, sab_user=None, sab_pass=None, destination_copy=0, destination_dir=None, download_dir=None, sab_cat=None, usenet_retention=None, blackhole=0, blackholedir=None,
        newznab=0, newznab_host=None, newznab_api=None, newznab2=0, newznab_host2=None, newznab_api2=None,newzbin=0, newzbin_uid=None, newzbin_pass=None, ebook_type=None, gr_api=None):

        lazylibrarian.HTTP_HOST = http_host
        lazylibrarian.HTTP_PORT = http_port
        lazylibrarian.HTTP_USER = http_user
        lazylibrarian.HTTP_PASS = http_pass
        lazylibrarian.HTTP_LOOK = http_look
        lazylibrarian.LAUNCH_BROWSER = launch_browser
        lazylibrarian.LOGDIR = logdir

        lazylibrarian.IMP_ONLYISBN = imp_onlyisbn
        lazylibrarian.IMP_PREFLANG = imp_preflang

        lazylibrarian.SAB_HOST = sab_host
        lazylibrarian.SAB_PORT = sab_port
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
        lazylibrarian.EBOOK_TYPE = ebook_type
        lazylibrarian.GR_API = gr_api

        lazylibrarian.config_write()

        raise cherrypy.HTTPRedirect("config")

    configUpdate.exposed = True

    def update(self):
        lazylibrarian.SIGNAL = 'update'
        message = 'Updating...'
        return serve_template(templatename="shutdown.html", title="Updating", message=message, timer=120)
        return page
    update.exposed = True

#SEARCH
    def search(self, name, type):
        GR = GoodReads(name, type)
        if len(name) == 0:
            raise cherrypy.HTTPRedirect("config")
        else:
            searchresults = GR.find_results(name)
        return serve_template(templatename="searchresults.html", title='Search Results for: "' + name + '"', searchresults=searchresults, type=type)
    search.exposed = True

#AUTHOR
    def authorPage(self, AuthorName, BookLang=None):
        myDB = database.DBConnection()

        languages = myDB.select('SELECT DISTINCT BookLang from books WHERE AuthorName LIKE ?', [AuthorName.replace("'","''")])
        if BookLang:
            querybooks = "SELECT * from books WHERE AuthorName LIKE '%s' AND BookLang = '%s' order by BookDate DESC, BookRate DESC" % (AuthorName.replace("'","''"), BookLang)
        else:
            querybooks = "SELECT * from books WHERE AuthorName LIKE '%s' AND (BookLang = '%s' OR BookLang = 'Unknown') order by BookDate DESC, BookRate DESC" % (AuthorName.replace("'","''"), lazylibrarian.IMP_PREFLANG)

        queryauthors = "SELECT * from authors WHERE AuthorName LIKE '%s'" % AuthorName.replace("'","''")

        author = myDB.action(queryauthors).fetchone()
        books = myDB.select(querybooks)
        if author is None:
            raise cherrypy.HTTPRedirect("home")
        return serve_template(templatename="author.html", title=author['AuthorName'], author=author, books=books, languages=languages)
    authorPage.exposed = True

    def pauseAuthor(self, AuthorID):
        logger.info(u"Pausing author: " + AuthorID)
        myDB = database.DBConnection()
        controlValueDict = {'AuthorID': AuthorID}
        newValueDict = {'Status': 'Paused'}
        myDB.upsert("authors", newValueDict, controlValueDict)
        raise cherrypy.HTTPRedirect("authorPage?AuthorID=%s" % AuthorID)
    pauseAuthor.exposed = True

    def resumeAuthor(self, AuthorID):
        logger.info(u"Resuming author: " + AuthorID)
        myDB = database.DBConnection()
        controlValueDict = {'AuthorID': AuthorID}
        newValueDict = {'Status': 'Active'}
        myDB.upsert("authors", newValueDict, controlValueDict)
        raise cherrypy.HTTPRedirect("authorPage?AuthorID=%s" % AuthorID)
    resumeAuthor.exposed = True

    def deleteAuthor(self, AuthorID):
        logger.info(u"Removing author: " + AuthorID)
        myDB = database.DBConnection()
        myDB.action('DELETE from authors WHERE AuthorID=?', [AuthorID])
        myDB.action('DELETE from books WHERE AuthorID=?', [AuthorID])
        raise cherrypy.HTTPRedirect("home")
    deleteAuthor.exposed = True

    def refreshAuthor(self, AuthorID):
        importer.addAuthorToDB(AuthorID)
        raise cherrypy.HTTPRedirect("authorPage?AuthorID=%s" % AuthorID)
    refreshAuthor.exposed=True

    def addResults(self, authorname):
        args = None;
        threading.Thread(target=importer.addAuthorToDB, args=[authorname]).start()
        raise cherrypy.HTTPRedirect("authorPage?AuthorName=%s" % authorname)
    addResults.exposed = True

#BOOKS
    def openBook(self, bookLink=None, action=None, **args):
        myDB = database.DBConnection()

        # find book
        bookdata = myDB.select('SELECT * from books WHERE BookLink=\'' + bookLink + '\'')
        logger.debug(('SELECT * from books WHERE BookLink=\'' + bookLink + '\''))
        if bookdata:
            authorName = bookdata[0]["AuthorName"];
            bookName = bookdata[0]["BookName"];

            dic = {'<':'', '>':'', '=':'', '?':'', '"':'', ',':'', '*':'', ':':'', ';':'', '\'':''}
            bookName = formatter.latinToAscii(formatter.replace_all(bookName, dic))
            if (lazylibrarian.INSTALL_TYPE == 'win'):
                dest_dir = lazylibrarian.DESTINATION_DIR + '\\' + authorName + '\\' + bookName
            else:
                dest_dir = lazylibrarian.DESTINATION_DIR + '//' + authorName + '//' + bookName

            logger.debug('bookdir ' + dest_dir);
            if os.path.isdir(dest_dir):
                for file2 in os.listdir(dest_dir):	
                    if ((file2.lower().find(".jpg") <= 0) & (file2.lower().find(".opf") <= 0)):
                        logger.info('Openning file ' + str(file2))
                        return serve_file(os.path.join(dest_dir, file2), "application/x-download", "attachment")
    openBook.exposed = True

    def searchForBook(self, bookLink=None, action=None, **args):
        myDB = database.DBConnection()

        # find book
        bookdata = myDB.select('SELECT * from books WHERE BookLink=\'' + bookLink + '\'')
        logger.debug(('SELECT * from books WHERE BookLink=\'' + bookLink + '\''))
        if bookdata:
            bookid = bookdata[0]["BookID"];
            AuthorName = bookdata[0]["AuthorName"];

            # start searchthreads
            books = []
            books.append({"bookid": bookid})

            threading.Thread(target=searchbook, args=[books]).start()
            logger.info("Searching for book with id: " + str(bookid));
        if AuthorName:
            raise cherrypy.HTTPRedirect("authorPage?AuthorName=%s" % AuthorName)
    searchForBook.exposed = True

    def markBooks(self, AuthorName=None, action=None, **args):
        myDB = database.DBConnection()
        for bookid in args:
            # ouch dirty workaround...
            if not bookid == 'book_table_length':

                controlValueDict = {'BookID': bookid}
                newValueDict = {'Status': action}
                myDB.upsert("books", newValueDict, controlValueDict)
                logger.debug('Status set to %s for BookID: %s' % (action, bookid))

                #update authors needs to be updated every time a book is marked differently
                query = 'SELECT COUNT(*) FROM books WHERE AuthorName="%s" AND (Status="Have" OR Status="Open")' % AuthorName
                countbooks = myDB.action(query).fetchone()
                havebooks = int(countbooks[0])
                controlValueDict = {"AuthorName": AuthorName}
                newValueDict = {"HaveBooks": havebooks}
                myDB.upsert("authors", newValueDict, controlValueDict)

        # start searchthreads
        books = []
        for bookid in args:
            # ouch dirty workaround...
            if not bookid == 'book_table_length':
                if action == 'Wanted':
                    books.append({"bookid": bookid})

        threading.Thread(target=searchbook, args=[books]).start()

        if AuthorName:
            raise cherrypy.HTTPRedirect("authorPage?AuthorName=%s" % AuthorName)
    markBooks.exposed = True

    def manProcess(self):
        threading.Thread(target=postprocess.processDir).start()
        raise cherrypy.HTTPRedirect("books")
    manProcess.exposed = True

    def checkForUpdates(self):
        #check the version when the application starts
        from lazylibrarian import versioncheck
        lazylibrarian.CURRENT_VERSION = versioncheck.getVersion()
        versioncheck.checkGithub()
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

    def logs(self):
        return serve_template(templatename="logs.html", title="Log", lineList=lazylibrarian.LOGLIST)
    logs.exposed = True

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