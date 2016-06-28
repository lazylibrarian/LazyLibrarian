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
import random
import urllib
import lazylibrarian

from lazylibrarian import logger, importer, database, postprocess, formatter, \
    notifiers, librarysync, versioncheck, magazinescan, common, bookwork, \
    qbittorrent, utorrent, transmission, sabnzbd, nzbget, deluge
from lazylibrarian.searchnzb import search_nzb_book, NZBDownloadMethod
from lazylibrarian.searchtorrents import search_tor_book, TORDownloadMethod
from lazylibrarian.searchmag import search_magazines
from lazylibrarian.searchrss import search_rss_book
from lazylibrarian.gr import GoodReads
from lazylibrarian.gb import GoogleBooks
from lib.deluge_client import DelugeRPCClient

import lib.simplejson as simplejson


def serve_template(templatename, **kwargs):

    interface_dir = os.path.join(
        str(lazylibrarian.PROG_DIR),
        'data/interfaces/')
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
        authors = myDB.select(
            'SELECT * from authors order by AuthorName COLLATE NOCASE')
        return serve_template(templatename="index.html", title="Home", authors=authors)
    home.exposed = True

# CONFIG ############################################################

    def config(self):
        http_look_dir = os.path.join(
            str(lazylibrarian.PROG_DIR),
            'data' + os.sep + 'interfaces')
        http_look_list = [name for name in os.listdir(http_look_dir)
                          if os.path.isdir(os.path.join(http_look_dir, name))]
        status_list = ['Skipped', 'Wanted', 'Have', 'Ignored']

        myDB = database.DBConnection()
        mags_list = []

        magazines = myDB.select('SELECT Title,Regex from magazines ORDER by Title')

        if magazines is not None:
            for mag in magazines:
                title = mag['Title']
                regex = mag['Regex']
                if regex is None:
                    regex = ""
                mags_list.append({
                    'Title': title,
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
    config.exposed = True

    def configUpdate(
        self, http_host='0.0.0.0', http_root='', http_user='', http_port=5299,
                     http_pass='', http_look='', launch_browser=0, api_key='', api_enabled=0,
                     logdir='', loglevel=2, loglimit=500, logfiles=10, logsize=204800, git_program='',
                     imp_onlyisbn=0, imp_singlebook=0, imp_preflang='', imp_monthlang='', imp_convert='',
                     imp_autoadd='', match_ratio=80, nzb_downloader_sabnzbd=0, nzb_downloader_nzbget=0,
                     nzb_downloader_blackhole=0, proxy_host='', proxy_type='',
                     sab_host='', sab_port=0, sab_subdir='', sab_api='', sab_user='', sab_pass='',
                     destination_copy=0, destination_dir='', download_dir='', sab_cat='', usenet_retention=0,
                     nzb_blackholedir='', alternate_dir='', torrent_dir='', numberofseeders=0,
                     tor_downloader_blackhole=0, tor_downloader_utorrent=0, tor_downloader_qbittorrent=0,
                     nzbget_host='', nzbget_port=0, nzbget_user='', nzbget_pass='', nzbget_cat='', nzbget_priority=0,
                     newzbin=0, newzbin_uid='', newzbin_pass='', kat=0, kat_host='',
                     ebook_type='', mag_type='', reject_words='', reject_maxsize=0,
                     book_api='', gr_api='', gb_api='',
                     versioncheck_interval='', search_interval='', scan_interval='', searchrss_interval=20,
                     ebook_dest_folder='', ebook_dest_file='',
                     mag_relative=0, mag_dest_folder='', mag_dest_file='', cache_age=30,
                     use_twitter=0, twitter_notify_onsnatch=0, twitter_notify_ondownload=0,
                     utorrent_host='', utorrent_port=0, utorrent_user='', utorrent_pass='', utorrent_label='',
                     qbittorrent_host='', qbittorrent_port=0, qbittorrent_user='', qbittorrent_pass='', qbittorrent_label='',
                     notfound_status='Skipped', newbook_status='Skipped', full_scan=0, add_author=0,
                     tor_downloader_transmission=0, transmission_host='', transmission_port=0, transmission_user='',
                     transmission_pass='', tor_downloader_deluge=0, deluge_host='', deluge_user='',
                     deluge_pass='', deluge_port=0, deluge_label='',
                     use_boxcar=0, boxcar_notify_onsnatch=0,
                     boxcar_notify_ondownload=0, boxcar_token='',
                     use_pushbullet=0, pushbullet_notify_onsnatch=0,
                     pushbullet_notify_ondownload=0, pushbullet_token='', pushbullet_deviceid='',
                     use_pushover=0, pushover_onsnatch=0, pushover_priority=0, pushover_keys='',
                     pushover_apitoken='', pushover_ondownload=0, pushover_device='',
                     use_androidpn=0, androidpn_notify_onsnatch=0, androidpn_notify_ondownload=0,
                     androidpn_url='', androidpn_username='', androidpn_broadcast=0, bookstrap_theme='',
                     use_nma=0, nma_apikey='', nma_priority=0, nma_onsnatch=0, nma_ondownload=0,
                     https_enabled=0, https_cert='', https_key='', **kwargs):
        #  print len(kwargs)
        #  for arg in kwargs:
        #      print arg
        lazylibrarian.HTTP_HOST = http_host
        lazylibrarian.HTTP_ROOT = http_root
        lazylibrarian.HTTP_PORT = formatter.check_int(http_port, 5299)
        lazylibrarian.HTTP_USER = http_user
        lazylibrarian.HTTP_PASS = http_pass
        lazylibrarian.HTTP_LOOK = http_look
        lazylibrarian.HTTPS_ENABLED = bool(https_enabled)
        lazylibrarian.HTTPS_CERT = https_cert
        lazylibrarian.HTTPS_KEY = https_key
        lazylibrarian.BOOKSTRAP_THEME = bookstrap_theme
        lazylibrarian.LAUNCH_BROWSER = bool(launch_browser)
        lazylibrarian.API_ENABLED = bool(api_enabled)
        lazylibrarian.API_KEY = api_key
        lazylibrarian.PROXY_HOST = proxy_host
        lazylibrarian.PROXY_TYPE = proxy_type
        lazylibrarian.LOGDIR = logdir
        lazylibrarian.LOGLIMIT = formatter.check_int(loglimit, 500)
        lazylibrarian.LOGLEVEL = formatter.check_int(loglevel, 2)
        lazylibrarian.LOGFILES = formatter.check_int(logfiles, 10)
        lazylibrarian.LOGSIZE = formatter.check_int(logsize, 204800)
        lazylibrarian.MATCH_RATIO = formatter.check_int(match_ratio, 80)
        lazylibrarian.CACHE_AGE = formatter.check_int(cache_age, 30)

        lazylibrarian.IMP_ONLYISBN = bool(imp_onlyisbn)
        lazylibrarian.IMP_SINGLEBOOK = bool(imp_singlebook)
        lazylibrarian.IMP_PREFLANG = imp_preflang
        lazylibrarian.IMP_MONTHLANG = imp_monthlang
        lazylibrarian.IMP_AUTOADD = imp_autoadd
        lazylibrarian.IMP_CONVERT = imp_convert
        lazylibrarian.GIT_PROGRAM = git_program

        lazylibrarian.SAB_HOST = sab_host
        lazylibrarian.SAB_PORT = formatter.check_int(sab_port, 0)
        lazylibrarian.SAB_SUBDIR = sab_subdir
        lazylibrarian.SAB_API = sab_api
        lazylibrarian.SAB_USER = sab_user
        lazylibrarian.SAB_PASS = sab_pass
        lazylibrarian.SAB_CAT = sab_cat

        lazylibrarian.NZBGET_HOST = nzbget_host
        lazylibrarian.NZBGET_PORT = formatter.check_int(nzbget_port, 0)
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
        lazylibrarian.TOR_DOWNLOADER_QBITTORRENT = bool(
            tor_downloader_qbittorrent)
        lazylibrarian.TOR_DOWNLOADER_TRANSMISSION = bool(
            tor_downloader_transmission)
        lazylibrarian.TOR_DOWNLOADER_DELUGE = bool(tor_downloader_deluge)

        lazylibrarian.NEWZBIN = bool(newzbin)
        lazylibrarian.NEWZBIN_UID = newzbin_uid
        lazylibrarian.NEWZBIN_PASS = newzbin_pass

        lazylibrarian.UTORRENT_HOST = utorrent_host
        lazylibrarian.UTORRENT_PORT = utorrent_port
        lazylibrarian.UTORRENT_USER = utorrent_user
        lazylibrarian.UTORRENT_PASS = utorrent_pass
        lazylibrarian.UTORRENT_LABEL = utorrent_label

        lazylibrarian.QBITTORRENT_HOST = qbittorrent_host
        lazylibrarian.QBITTORRENT_PORT = formatter.check_int(qbittorrent_port, 0)
        lazylibrarian.QBITTORRENT_USER = qbittorrent_user
        lazylibrarian.QBITTORRENT_PASS = qbittorrent_pass
        lazylibrarian.QBITTORRENT_LABEL = qbittorrent_label

        lazylibrarian.TRANSMISSION_HOST = transmission_host
        lazylibrarian.TRANSMISSION_PORT = transmission_port
        lazylibrarian.TRANSMISSION_USER = transmission_user
        lazylibrarian.TRANSMISSION_PASS = transmission_pass

        lazylibrarian.DELUGE_HOST = deluge_host
        lazylibrarian.DELUGE_PORT = formatter.check_int(deluge_port, 0)
        lazylibrarian.DELUGE_USER = deluge_user
        lazylibrarian.DELUGE_PASS = deluge_pass
        lazylibrarian.DELUGE_LABEL = deluge_label

        lazylibrarian.KAT = bool(kat)
        lazylibrarian.KAT_HOST = kat_host

        lazylibrarian.EBOOK_TYPE = ebook_type
        lazylibrarian.MAG_TYPE = mag_type
        lazylibrarian.REJECT_WORDS = reject_words
        lazylibrarian.REJECT_MAXSIZE = reject_maxsize
        lazylibrarian.BOOK_API = book_api
        lazylibrarian.GR_API = gr_api
        lazylibrarian.GB_API = gb_api

        lazylibrarian.SEARCH_INTERVAL = formatter.check_int(
            search_interval, 360)
        lazylibrarian.SCAN_INTERVAL = formatter.check_int(scan_interval, 10)
        lazylibrarian.SEARCHRSS_INTERVAL = formatter.check_int(
            searchrss_interval, 20)
        lazylibrarian.VERSIONCHECK_INTERVAL = formatter.check_int(
            versioncheck_interval, 24)

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
        lazylibrarian.TWITTER_NOTIFY_ONDOWNLOAD = bool(
            twitter_notify_ondownload)

        lazylibrarian.USE_BOXCAR = bool(use_boxcar)
        lazylibrarian.BOXCAR_NOTIFY_ONSNATCH = bool(boxcar_notify_onsnatch)
        lazylibrarian.BOXCAR_NOTIFY_ONDOWNLOAD = bool(boxcar_notify_ondownload)
        lazylibrarian.BOXCAR_TOKEN = boxcar_token

        lazylibrarian.USE_PUSHBULLET = bool(use_pushbullet)
        lazylibrarian.PUSHBULLET_NOTIFY_ONSNATCH = bool(
            pushbullet_notify_onsnatch)
        lazylibrarian.PUSHBULLET_NOTIFY_ONDOWNLOAD = bool(
            pushbullet_notify_ondownload)
        lazylibrarian.PUSHBULLET_TOKEN = pushbullet_token
        lazylibrarian.PUSHBULLET_DEVICEID = pushbullet_deviceid

        lazylibrarian.USE_PUSHOVER = bool(use_pushover)
        lazylibrarian.PUSHOVER_ONSNATCH = bool(pushover_onsnatch)
        lazylibrarian.PUSHOVER_ONDOWNLOAD = bool(pushover_ondownload)
        lazylibrarian.PUSHOVER_KEYS = pushover_keys
        lazylibrarian.PUSHOVER_APITOKEN = pushover_apitoken
        lazylibrarian.PUSHOVER_PRIORITY = formatter.check_int(
            pushover_priority, 0)
        lazylibrarian.PUSHOVER_DEVICE = pushover_device

        lazylibrarian.USE_ANDROIDPN = bool(use_androidpn)
        lazylibrarian.ANDROIDPN_NOTIFY_ONSNATCH = bool(
            androidpn_notify_onsnatch)
        lazylibrarian.ANDROIDPN_NOTIFY_ONDOWNLOAD = bool(
            androidpn_notify_ondownload)
        lazylibrarian.ANDROIDPN_URL = androidpn_url
        lazylibrarian.ANDROIDPN_USERNAME = androidpn_username
        lazylibrarian.ANDROIDPN_BROADCAST = bool(androidpn_broadcast)

        lazylibrarian.USE_NMA = bool(use_nma)
        lazylibrarian.NMA_APIKEY = nma_apikey
        lazylibrarian.NMA_PRIORITY = formatter.check_int(nma_priority, 0)
        lazylibrarian.NMA_ONSNATCH = bool(nma_onsnatch)
        lazylibrarian.NMA_ONDOWNLOAD = bool(nma_ondownload)

        myDB = database.DBConnection()
        magazines = myDB.select('SELECT Title,Regex from magazines ORDER by Title')

        if magazines is not None:
            for mag in magazines:
                title = mag['Title']
                regex = mag['Regex']
                new_regex = kwargs.get('reject_list[%s]' % title, None)
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
            lazylibrarian.RSS_PROV[count]['HOST'] = kwargs.get(
                        'rss[%i][host]' % count, '')
            lazylibrarian.RSS_PROV[count]['USER'] = kwargs.get(
                        'rss[%i][user]' % count, '')
            lazylibrarian.RSS_PROV[count]['PASS'] = kwargs.get(
                        'rss[%i][pass]' % count, '')
            count += 1

        lazylibrarian.config_write()

        logger.info(
            'Config file [%s] has been updated' % lazylibrarian.CONFIGFILE)

        raise cherrypy.HTTPRedirect("config")

    configUpdate.exposed = True

# SEARCH ############################################################

    def search(self, name):
        if name is None or not len(name):
            raise cherrypy.HTTPRedirect("home")

        myDB = database.DBConnection()
        if lazylibrarian.BOOK_API == "GoogleBooks":
            GB = GoogleBooks(name)
            queue = Queue.Queue()
            search_api = threading.Thread(
                target=GB.find_results, args=[name, queue])
            search_api.start()
        elif lazylibrarian.BOOK_API == "GoodReads":
            queue = Queue.Queue()
            GR = GoodReads(name)
            search_api = threading.Thread(
                target=GR.find_results, args=[name, queue])
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

        # need a url safe version of authorname for passing to
        # searchresults.html
        resultlist = []
        for result in searchresults:
            result['safeauthorname'] = urllib.quote_plus(
                result['authorname'].encode('utf-8'))
            resultlist.append(result)

        sortedlist_final = sorted(
            searchresults, key=itemgetter('highest_fuzz', 'num_reviews'), reverse=True)
        return serve_template(templatename="searchresults.html", title='Search Results for: "' +
                              name + '"', searchresults=sortedlist_final, authorlist=authorlist,
                              booklist=booklist, booksearch=booksearch)
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

        queryauthors = "SELECT * from authors WHERE AuthorName LIKE '%s'" % AuthorName.replace(
            "'", "''")

        author = myDB.action(queryauthors).fetchone()
        books = myDB.select(querybooks)
        if author is None:
            raise cherrypy.HTTPRedirect("home")
        return serve_template(
            templatename="author.html", title=urllib.quote(author['AuthorName'].encode('utf-8')),
                              author=author, books=books, languages=languages)
    authorPage.exposed = True

    def pauseAuthor(self, AuthorID):
        myDB = database.DBConnection()
        authorsearch = myDB.select(
            'SELECT AuthorName from authors WHERE AuthorID="%s"' % AuthorID)
        AuthorName = authorsearch[0]['AuthorName']
        logger.info(u"Pausing author: %s" % AuthorName)

        controlValueDict = {'AuthorID': AuthorID}
        newValueDict = {'Status': 'Paused'}
        myDB.upsert("authors", newValueDict, controlValueDict)
        logger.debug(
            u'AuthorID [%s]-[%s] Paused - redirecting to Author home page' % (AuthorID, AuthorName))
        raise cherrypy.HTTPRedirect(
            "authorPage?AuthorName=%s" % urllib.quote(AuthorName.encode('utf-8')))
    pauseAuthor.exposed = True

    def resumeAuthor(self, AuthorID):
        myDB = database.DBConnection()
        authorsearch = myDB.select(
            'SELECT AuthorName from authors WHERE AuthorID="%s"' % AuthorID)
        AuthorName = authorsearch[0]['AuthorName']
        logger.info(u"Resuming author: %s" % AuthorName)

        controlValueDict = {'AuthorID': AuthorID}
        newValueDict = {'Status': 'Active'}
        myDB.upsert("authors", newValueDict, controlValueDict)
        logger.debug(
            u'AuthorID [%s]-[%s] Restarted - redirecting to Author home page' % (AuthorID, AuthorName))
        raise cherrypy.HTTPRedirect(
            "authorPage?AuthorName=%s" % urllib.quote(AuthorName.encode('utf-8')))
    resumeAuthor.exposed = True

    def deleteAuthor(self, AuthorID):
        myDB = database.DBConnection()
        authorsearch = myDB.select(
            'SELECT AuthorName from authors WHERE AuthorID="%s"' % AuthorID)
        if len(authorsearch):  # to stop error if try to delete an author while they are still loading
            AuthorName = authorsearch[0]['AuthorName']
            logger.info(u"Removing all references to author: %s" % AuthorName)
            myDB.action('DELETE from authors WHERE AuthorID="%s"' % AuthorID)
            myDB.action('DELETE from books WHERE AuthorID="%s"' % AuthorID)
        raise cherrypy.HTTPRedirect("home")
    deleteAuthor.exposed = True

    def refreshAuthor(self, AuthorName):
        threading.Thread(target=importer.addAuthorToDB, args=[AuthorName, True]).start()
        raise cherrypy.HTTPRedirect(
            "authorPage?AuthorName=%s" % urllib.quote(AuthorName.encode('utf-8')))
    refreshAuthor.exposed = True

    def addAuthor(self, AuthorName):
        threading.Thread(target=importer.addAuthorToDB, args=[AuthorName, False]).start()
        raise cherrypy.HTTPRedirect(
            "authorPage?AuthorName=%s" % urllib.quote(AuthorName.encode('utf-8')))
    addAuthor.exposed = True

# BOOKS #############################################################

# not very clean here, using a global variable BOOKLANGFILTER to pass booklang from books to getbooks
#
    def books(self, BookLang=None):
        myDB = database.DBConnection()
        languages = myDB.select('SELECT DISTINCT BookLang from books WHERE NOT \
                                STATUS="Skipped" AND NOT STATUS="Ignored"')
        lazylibrarian.BOOKLANGFILTER = BookLang
        return serve_template(templatename="books.html", title='Books', books=[], languages=languages)
    books.exposed = True

    def getBooks(self, iDisplayStart=0, iDisplayLength=100, iSortCol_0=1, sSortDir_0="desc", sSearch="", **kwargs):
        myDB = database.DBConnection()
        iDisplayStart = int(iDisplayStart)
        iDisplayLength = int(iDisplayLength)

        #   need to check and filter on BookLang if set
        if lazylibrarian.BOOKLANGFILTER is None or not len(lazylibrarian.BOOKLANGFILTER):
            rowlist = myDB.action(
                'SELECT bookimg, authorname, bookname, series, seriesnum, bookrate, bookdate, status, bookid, booksub, booklink, workpage from books WHERE NOT STATUS="Skipped" AND NOT STATUS="Ignored"').fetchall()
        else:
            rowlist = myDB.action(
                'SELECT bookimg, authorname, bookname, series, seriesnum, bookrate, bookdate, status, bookid, booksub, booklink, workpage from books WHERE NOT STATUS="Skipped" AND NOT STATUS="Ignored" and BOOKLANG="%s"' %
                lazylibrarian.BOOKLANGFILTER).fetchall()
        # turn the sqlite rowlist into a list of lists
        d = []
        # the masterlist to be filled with the row data and to be returned
        for i, row in enumerate(rowlist):  # iterate through the sqlite3.Row objects
            l = []  # for each Row use a separate list

            bookrate = float(row[5])
            if bookrate < 0.5:
                starimg = '0-stars.png'
            elif bookrate >= 0.5 and bookrate < 1.5:
                starimg = '1-stars.png'
            elif bookrate >= 1.5 and bookrate < 2.5:
                starimg = '2-stars.png'
            elif bookrate >= 2.5 and bookrate < 3.5:
                starimg = '3-stars.png'
            elif bookrate >= 3.5 and bookrate < 4.5:
                starimg = '4-stars.png'
            elif bookrate >= 4.5:
                starimg = '5-stars.png'
            else:
                starimg = '0-stars.png'

            worklink = ''
            if row[11]: # is there a workpage link
                if len(row[11]) > 4:
                    worklink = '<br><td><a href="' + row[11] + '" target="_new">WorkPage</a></td>'

            if lazylibrarian.HTTP_LOOK == 'default':
                l.append(
                    '<td id="select"><input type="checkbox" name="%s" class="checkbox" /></td>' % row[8])
                l.append(
                    '<td id="bookart"><a href="%s" target="_new"><img src="%s" height="75" width="50"></a></td>' % (row[0], row[0]))
                l.append(
                    '<td id="authorname"><a href="authorPage?AuthorName=%s">%s</a></td>' % (row[1], row[1]))
                if row[9]:  # is there a sub-title
                    l.append(
                        '<td id="bookname"><a href="%s" target="_new">%s</a><br><i class="smalltext">%s</i></td>' % (row[10], row[2], row[9]))
                else:
                    l.append(
                        '<td id="bookname"><a href="%s" target="_new">%s</a></td>' % (row[10], row[2]))

                if row[3]:  # is the book part of a series
                    l.append('<td id="series">%s</td>' % row[3])
                else:
                    l.append('<td id="series">None</td>')

                if row[4]:
                    l.append('<td id="seriesNum">%s</td>' % row[4])
                else:
                    l.append('<td id="seriesNum">None</td>')

                l.append(
                    '<td id="stars"><img src="images/' + starimg + '" width="50" height="10"></td>')

                l.append('<td id="date">%s</td>' % row[6])

                if row[7] == 'Open':
                    btn = '<td id="status"><a class="button green" href="openBook?bookid=%s" target="_self">Open</a></td>' % row[8]
                elif row[7] == 'Wanted':
                    btn = '<td id="status"><a class="button red" href="searchForBook?bookid=%s" target="_self"><span class="a">Wanted</span><span class="b">Search</span></a></td>' % row[8]
                elif row[7] == 'Snatched' or row[7] == 'Have':
                    btn = '<td id="status"><a class="button">%s</a></td>' % row[7]
                else:
                    btn = '<td id="status"><a class="button grey">%s</a></td>' % row[7]
                l.append(btn + worklink)

            elif lazylibrarian.HTTP_LOOK == 'bookstrap':
                l.append(
                    '<td class="select"><input type="checkbox" name="%s" class="checkbox" /></td>' % row[8])
                l.append(
                    '<td class="bookart text-center"><a href="%s" target="_blank" rel="noreferrer"><img src="%s" alt="Cover" class="bookcover-sm img-responsive"></a></td>' % (row[0], row[0]))
                l.append(
                    '<td class="authorname"><a href="authorPage?AuthorName=%s">%s</a></td>' % (row[1], row[1]))
                if row[9]:  # is there a sub-title
                    l.append(
                        '<td class="bookname"><a href="%s" target="_blank" rel="noreferrer">%s</a><br><i class="smalltext">%s</i></td>' % (row[10], row[2], row[9]))
                else:
                    l.append(
                        '<td class="bookname"><a href="%s" target="_blank" rel="noreferrer">%s</a></td>' % (row[10], row[2]))

                if row[3]:  # is the book part of a series
                    l.append('<td class="series">%s</td>' % row[3])
                else:
                    l.append('<td class="series">None</td>')

                if row[4]:
                    l.append('<td class="seriesNum text-center">%s</td>' % row[4])
                else:
                    l.append('<td class="seriesNum text-center">None</td>')

                l.append(
                    '<td class="stars text-center"><img src="images/' + starimg + '" alt="Rating"></td>')

                l.append('<td class="date text-center">%s</td>' % row[6])
                if row[7] == 'Open':
                    btn = '<td class="status text-center"><a class="button green btn btn-xs btn-warning" href="openBook?bookid=%s" target="_self"><i class="fa fa-book"></i>%s</a></td>' % (row[8], row[7])
                elif row[7] == 'Wanted':
                    btn = '<td class="status text-center"><p><a class="a btn btn-xs btn-danger">%s</a></p><p><a class="b btn btn-xs btn-success" href="searchForBook?bookid=%s" target="_self"><i class="fa fa-search"></i> Search</a></p></td>' % (row[7], row[8])
                elif row[7] == 'Snatched' or row[7] == 'Have':
                    btn = '<td class="status text-center"><a class="button btn btn-xs btn-info">%s</a></td>' % row[7]
                else:
                    btn = '<td class="status text-center"><a class="button btn btn-xs btn-default grey">%s</a></td>' % row[7]
                l.append(btn + worklink)

            d.append(l)  # add the rowlist to the masterlist
        filtered = d

        if sSearch != "":
            filtered = [row for row in d for column in row if sSearch in column]
        sortcolumn = int(iSortCol_0)

        filtered.sort(key=lambda x: x[sortcolumn], reverse=sSortDir_0 == "desc")
        if iDisplayLength < 0:  # display = all
            rows = filtered
        else:
            rows = filtered[iDisplayStart:(iDisplayStart + iDisplayLength)]

        mydict = {'iTotalDisplayRecords': len(filtered),
                  'iTotalRecords': len(rowlist),
                  'aaData': rows,
                  }
        s = simplejson.dumps(mydict)
        # print ("Getbooks returning %s to %s" % (iDisplayStart, iDisplayStart
        # + iDisplayLength))
        return s
    getBooks.exposed = True

    def addBook(self, bookid=None):
        myDB = database.DBConnection()
        AuthorName = ""
        booksearch = myDB.select(
            'SELECT * from books WHERE BookID="%s"' % bookid)
        if booksearch:
            myDB.upsert("books", {'Status': 'Wanted'}, {'BookID': bookid})
            for book in booksearch:
                AuthorName = book['AuthorName']
                authorsearch = myDB.select(
                    'SELECT * from authors WHERE AuthorName="%s"' % AuthorName)
                if authorsearch:
                    # update authors needs to be updated every time a book is marked differently
                    lastbook = myDB.action('SELECT BookName, BookLink, BookDate from books WHERE \
                                           AuthorName="%s" AND Status != "Ignored" order by BookDate DESC' %
                                           AuthorName).fetchone()
                    unignoredbooks = myDB.action('SELECT count("BookID") as counter FROM books WHERE \
                                                 AuthorName="%s" AND Status != "Ignored"' % AuthorName).fetchone()
                    totalbooks = myDB.action(
                        'SELECT count("BookID") as counter FROM books WHERE AuthorName="%s"' % AuthorName).fetchone()
                    havebooks = myDB.action('SELECT count("BookID") as counter FROM books WHERE AuthorName="%s" AND \
                                             (Status="Have" OR Status="Open")' % AuthorName).fetchone()

                    controlValueDict = {"AuthorName": AuthorName}
                    newValueDict = {
                        "TotalBooks": totalbooks['counter'],
                        "UnignoredBooks": unignoredbooks['counter'],
                        "HaveBooks": havebooks['counter'],
                        "LastBook": lastbook['BookName'],
                        "LastLink": lastbook['BookLink'],
                        "LastDate": lastbook['BookDate']
                    }
                    myDB.upsert("authors", newValueDict, controlValueDict)
        else:
            if lazylibrarian.BOOK_API == "GoogleBooks":
                GB = GoogleBooks(bookid)
                queue = Queue.Queue()
                find_book = threading.Thread(
                    target=GB.find_book, args=[bookid, queue])
                find_book.start()
            elif lazylibrarian.BOOK_API == "GoodReads":
                queue = Queue.Queue()
                GR = GoodReads(bookid)
                find_book = threading.Thread(
                    target=GR.find_book, args=[bookid, queue])
                find_book.start()
            if len(bookid) == 0:
                raise cherrypy.HTTPRedirect("config")

            find_book.join()

        books = [{"bookid": bookid}]
        self.startBookSearch(books)

        if AuthorName:
            raise cherrypy.HTTPRedirect("authorPage?AuthorName=%s" % AuthorName)
        else:
            raise cherrypy.HTTPRedirect("books")
    addBook.exposed = True

    def startBookSearch(self, books=None):
        if books:
            if lazylibrarian.USE_RSS():
                threading.Thread(target=search_rss_book, args=[books]).start()
            if lazylibrarian.USE_NZB():
                threading.Thread(target=search_nzb_book, args=[books]).start()
            if lazylibrarian.USE_TOR():
                threading.Thread(target=search_tor_book, args=[books]).start()
            if lazylibrarian.USE_RSS() or lazylibrarian.USE_NZB() or lazylibrarian.USE_TOR():
                logger.debug(u"Searching for book with id: " + books[0]["bookid"])
            else:
                logger.warn(u"Not searching for book, no search methods set, check config.")
        else:
            logger.debug(u"BookSearch called with no books")
    startBookSearch.exposed = True

    def searchForBook(self, bookid=None, action=None, **args):
        myDB = database.DBConnection()

        bookdata = myDB.select('SELECT * from books WHERE BookID="%s"' % bookid)
        if bookdata:
            AuthorName = bookdata[0]["AuthorName"]

            # start searchthreads
            books = [{"bookid": bookid}]
            self.startBookSearch(books)

        if AuthorName:
            raise cherrypy.HTTPRedirect("authorPage?AuthorName=%s" % AuthorName)
    searchForBook.exposed = True

    def openBook(self, bookid=None, **args):
        myDB = database.DBConnection()

        bookdata = myDB.select(
            'SELECT * from books WHERE BookID="%s"' % bookid)
        if bookdata:
            bookfile = bookdata[0]["BookFile"]
            if bookfile and os.path.isfile(bookfile):
                logger.info(u'Opening file %s' % bookfile)
                return serve_file(bookfile, "application/x-download", "attachment")
            else:
                authorName = bookdata[0]["AuthorName"]
                bookName = bookdata[0]["BookName"]
                logger.info(u'Missing book %s,%s' % (authorName, bookName))
    openBook.exposed = True

    def markBooks(self, AuthorName=None, action=None, redirect=None, **args):
        myDB = database.DBConnection()
        if not redirect:
            redirect = "books"
        authorcheck = None
        if action is not None:
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
            # update authors needs to be updated every time a book is marked
            # differently
            lastbook = myDB.action('SELECT BookName, BookLink, BookDate from books WHERE AuthorName="%s" \
                                   AND Status != "Ignored" order by BookDate DESC' % AuthorName).fetchone()
            unignoredbooks = myDB.action('SELECT count("BookID") as counter FROM books WHERE AuthorName="%s" \
                                         AND Status != "Ignored"' % AuthorName).fetchone()
            totalbooks = myDB.action(
                'SELECT count("BookID") as counter FROM books WHERE AuthorName="%s"' % AuthorName).fetchone()
            havebooks = myDB.action('SELECT count("BookID") as counter FROM books WHERE AuthorName="%s" AND \
                                     (Status="Have" OR Status="Open")' % AuthorName).fetchone()

            controlValueDict = {"AuthorName": AuthorName}
            newValueDict = {
                "TotalBooks": totalbooks['counter'],
                "UnignoredBooks": unignoredbooks['counter'],
                "HaveBooks": havebooks['counter'],
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

            if lazylibrarian.USE_RSS():
                threading.Thread(target=search_rss_book, args=[books]).start()
            if lazylibrarian.USE_NZB():
                threading.Thread(target=search_nzb_book, args=[books]).start()
            if lazylibrarian.USE_TOR():
                threading.Thread(target=search_tor_book, args=[books]).start()

        if redirect == "author":
            raise cherrypy.HTTPRedirect(
                "authorPage?AuthorName=%s" %
                AuthorName)
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
                count = myDB.select(
                    'SELECT COUNT(Title) as counter FROM issues WHERE Title="%s"' %
                    title)
                if count:
                    issues = count[0]['counter']
                else:
                    issues = 0
                this_mag = dict(mag)
                this_mag['Count'] = issues
                this_mag['safetitle'] = urllib.quote_plus(mag['Title'].encode('utf-8'))
                mags.append(this_mag)

        return serve_template(templatename="magazines.html", title="Magazines", magazines=mags)
    magazines.exposed = True

    def issuePage(self, title):
        myDB = database.DBConnection()

        issues = myDB.select('SELECT * from issues WHERE Title="%s" order by IssueDate DESC' % title)

        if issues is None:
            raise cherrypy.HTTPRedirect("magazines")
        else:
            mod_issues = []
            covercount = 0
            for issue in issues:
                magfile = issue['IssueFile']
                extn = os.path.splitext(magfile)[1]
                if extn:
                    magimg = magfile.replace(extn, '.jpg')
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
                        covercount = covercount + 1
                else:
                    logger.debug('No extension found on %s' % magfile)
                    magimg = 'images/nocover.png'

                this_issue = dict(issue)
                this_issue['Cover'] = magimg
                # this_issue['safeissuefile'] =
                # urllib.quote_plus(magfile.encode('utf-8'))
                mod_issues.append(this_issue)
            logger.debug("Found %s covers" % covercount)
        return serve_template(templatename="issues.html", title=title, issues=mod_issues, covercount=covercount)
    issuePage.exposed = True

    def pastIssues(self, whichStatus=None):
        if whichStatus is None:
            whichStatus = "Skipped"
        lazylibrarian.ISSUEFILTER = whichStatus
        return serve_template(
            templatename="manageissues.html", title="Magazine Status Management", issues=[], whichStatus=whichStatus)
    pastIssues.exposed = True

    def getPastIssues(self, iDisplayStart=0, iDisplayLength=100, iSortCol_0=0, sSortDir_0="desc", sSearch="", **kwargs):
        myDB = database.DBConnection()
        iDisplayStart = int(iDisplayStart)
        iDisplayLength = int(iDisplayLength)
        # need to filter on whichStatus
        rowlist = myDB.action(
            'SELECT NZBurl, NZBtitle, NZBdate, Auxinfo, NZBprov, Status from pastissues WHERE Status="%s"' %
            lazylibrarian.ISSUEFILTER).fetchall()

        # turn the sqlite rowlist into a list of lists
        d = []
        # the masterlist to be filled with the row data and to be returned
        for i, row in enumerate(rowlist):  # iterate through the sqlite3.Row objects
            l = []  # for each Row use a separate list

            l.append('<td id="select"><input type="checkbox" name="%s" class="checkbox" /></td>' % row[0])
            l.append('<td id="magtitle">%s</td>' % row[1])
            l.append('<td id="lastacquired">%s</td>' % row[2])
            l.append('<td id="issuedate">%s</td>' % row[3])
            l.append('<td id="provider">%s</td>' % row[4])
            l.append('<td id="status">%s</td>' % row[5])
            d.append(l)  # add the rowlist to the masterlist
        filtered = d

        if sSearch != "":
            filtered = [row for row in d for column in row if sSearch in column]
        sortcolumn = int(iSortCol_0)

        filtered.sort(key=lambda x: x[sortcolumn], reverse=sSortDir_0 == "desc")
        if iDisplayLength < 0:  # display = all
            rows = filtered
        else:
            rows = filtered[iDisplayStart:(iDisplayStart + iDisplayLength)]

        mydict = {'iTotalDisplayRecords': len(filtered),
                  'iTotalRecords': len(rowlist),
                  'aaData': rows,
                  }
        s = simplejson.dumps(mydict)
        return s
    getPastIssues.exposed = True

    def openMag(self, bookid=None, **args):
        bookid = urllib.unquote_plus(bookid)
        myDB = database.DBConnection()
        # we may want to open an issue with a hashed bookid
        mag_data = myDB.select('SELECT * from issues WHERE IssueID="%s"' % bookid)
        if len(mag_data):
            IssueFile = mag_data[0]["IssueFile"]
            if IssueFile and os.path.isfile(IssueFile):
                logger.info(u'Opening file %s' % IssueFile)
                return serve_file(IssueFile, "application/x-download", "attachment")

        # or we may just have a title to find magazine in issues table
        mag_data = myDB.select('SELECT * from issues WHERE Title="%s"' % bookid)
        if len(mag_data) == 0:  # no issues!
            raise cherrypy.HTTPRedirect("magazines")
        elif len(mag_data) == 1:  # we only have one issue, get it
            IssueDate = mag_data[0]["IssueDate"]
            IssueFile = mag_data[0]["IssueFile"]
            logger.info(u'Opening %s - %s' % (bookid, IssueDate))
            return serve_file(IssueFile, "application/x-download", "attachment")
        elif len(mag_data) > 1:  # multiple issues, show a list
            logger.debug(u"%s has %s issues" % (bookid, len(mag_data)))
            raise cherrypy.HTTPRedirect("issuePage?title=%s" % urllib.quote_plus(bookid.encode('utf-8')))
    openMag.exposed = True

    def markPastIssues(self, AuthorName=None, action=None, redirect=None, **args):
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
                title = myDB.select('SELECT * from pastissues WHERE NZBurl="%s"' % nzburl)
                for item in title:
                    nzburl = item['NZBurl']
                    if action == 'Delete':
                        myDB.action('DELETE from pastissues WHERE NZBurl="%s"' % nzburl)
                        logger.debug(u'Item %s deleted from past issues' % nzburl)
                        maglist.append({'nzburl': nzburl})
                    else:
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
                        if action == 'Wanted':
                            # copy into wanted table
                            controlValueDict = {'NZBurl': nzburl}
                            newValueDict = {
                                'BookID': bookid,
                                'NZBtitle': nzbtitle,
                                'NZBdate': formatter.now(),
                                'NZBprov': nzbprov,
                                'Status': action, 
                                'NZBsize': nzbsize,
                                'AuxInfo': auxinfo,
                                'NZBmode': nzbmode
                                }
                            myDB.upsert("wanted", newValueDict, controlValueDict)                            

        if action == 'Delete':
            logger.info(u'Deleted %s items from past issues' % (len(maglist)))
        else:
            logger.info(u'Status set to %s for %s past issues' % (action, len(maglist)))
        # start searchthreads
        if action == 'Wanted':
            for items in maglist:
                logger.debug(u'Snatching %s' % items['nzbtitle'])
                if items['nzbmode'] == 'torznab' or items['nzbmode'] == 'torrent':
                    snatch = TORDownloadMethod(
                        items['bookid'],
                        items['nzbprov'],
                        items['nzbtitle'],
                        items['nzburl'])
                else:
                    snatch = NZBDownloadMethod(
                        items['bookid'],
                        items['nzbprov'],
                        items['nzbtitle'],
                        items['nzburl'])
                if snatch:  # if snatch fails, downloadmethods already report it
                    notifiers.notify_snatch(items['nzbtitle'] + ' at ' + formatter.now())
                    common.schedule_job(action='Start', target='processDir')
        raise cherrypy.HTTPRedirect("pastIssues")
    markPastIssues.exposed = True

    def markIssues(self, action=None, **args):
        myDB = database.DBConnection()
        for item in args:
            # ouch dirty workaround...
            if not item == 'book_table_length':
                if (action == "Delete"):
                    myDB.action('DELETE from issues WHERE IssueID="%s"' % item)
                    logger.info(
                        u'Issue with id %s removed from database' % item)
        raise cherrypy.HTTPRedirect("magazines")
    markIssues.exposed = True

    def markMagazines(self, action=None, **args):
        myDB = database.DBConnection()
        for item in args:
            # ouch dirty workaround...
            if not item == 'book_table_length':
                if (action == "Paused" or action == "Active"):
                    controlValueDict = {"Title": item}
                    newValueDict = {"Status": action}
                    myDB.upsert("magazines", newValueDict, controlValueDict)
                    logger.info(u'Status of magazine %s changed to %s' % (item, action))
                elif (action == "Delete"):
                    myDB.action('DELETE from magazines WHERE Title="%s"' % item)
                    myDB.action('DELETE from pastissues WHERE BookID="%s"' % item)
                    myDB.action('DELETE from issues WHERE Title="%s"' % item)
                    logger.info(u'Magazine %s removed from database' % item)
                elif (action == "Reset"):
                    controlValueDict = {"Title": item}
                    newValueDict = {
                        "LastAcquired": None,
                        "IssueDate": None,
                        "IssueStatus": "Wanted"
                    }
                    myDB.upsert("magazines", newValueDict, controlValueDict)
                    logger.info(u'Magazine %s details reset' % item)

        raise cherrypy.HTTPRedirect("magazines")
    markMagazines.exposed = True

    def searchForMag(self, bookid=None, action=None, **args):
        myDB = database.DBConnection()
        bookid = urllib.unquote_plus(bookid)
        bookdata = myDB.select('SELECT * from magazines WHERE Title="%s"' % bookid)
        if bookdata:
            # start searchthreads
            mags = [{"bookid": bookid}]
            self.startMagazineSearch(mags)
            raise cherrypy.HTTPRedirect("magazines")
    searchForMag.exposed = True

    def startMagazineSearch(self, mags=None):
        if mags:
            if lazylibrarian.USE_NZB() or lazylibrarian.USE_TOR():
                threading.Thread(target=search_magazines, args=[mags, False]).start()
                logger.debug(u"Searching for magazine with title: %s" % mags[0]["bookid"])
            else:
                logger.warn(u"Not searching for magazine, no download methods set, check config")
        else:
            logger.debug(u"MagazineSearch called with no magazines")
    startMagazineSearch.exposed = True

    def addMagazine(self, search=None, title=None, frequency=None, **args):
        myDB = database.DBConnection()
        # if search == 'magazine':  # we never call this unless search ==
        # 'magazine'
        if len(title) == 0:
            raise cherrypy.HTTPRedirect("magazines")
        else:
            regex = None
            if '~' in title:  # separate out the "reject words" list
                regex = title.split('~',1)[1].strip()
                title = title.split('~',1)[0].strip()
            controlValueDict = {"Title": title}
            newValueDict = {
                "Frequency": None,
                "Regex": regex,
                "Status": "Active",
                "MagazineAdded": formatter.today(),
                "IssueStatus": "Wanted"
            }
            myDB.upsert("magazines", newValueDict, controlValueDict)
            mags = [{"bookid": title}]
            self.startMagazineSearch(mags)
            raise cherrypy.HTTPRedirect("magazines")
    addMagazine.exposed = True

# UPDATES ###########################################################

    def checkForUpdates(self):
        # Set the install type (win,git,source) &
        # check the version when the application starts
        versioncheck.getInstallType()
        lazylibrarian.CURRENT_VERSION = versioncheck.getCurrentVersion()
        lazylibrarian.LATEST_VERSION = versioncheck.getLatestVersion()
        lazylibrarian.COMMITS_BEHIND, lazylibrarian.COMMIT_LIST = versioncheck.getCommitDifferenceFromGit()
        if lazylibrarian.COMMITS_BEHIND == 0:
            message = "up to date"
            return serve_template(templatename="shutdown.html", title="Version Check", message=message, timer=5)
        if lazylibrarian.COMMITS_BEHIND > 0:
            multi = ''
            if lazylibrarian.COMMITS_BEHIND > 1:
                multi = 's'
            message = "behind by %s commit%s" % (lazylibrarian.COMMITS_BEHIND, multi)
            messages = lazylibrarian.COMMIT_LIST.replace('\n', '<br>')
            message = message + '<br><small>' + messages
            return serve_template(templatename="shutdown.html", title="Commits", message=message, timer=15)

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
        return serve_template(templatename="shutdown.html", title="Updating", message=message, timer=30)
    update.exposed = True

# IMPORT/EXPORT #####################################################

    def libraryScan(self):
        try:
            threading.Thread(target=librarysync.LibraryScan(lazylibrarian.DESTINATION_DIR)).start()
        except Exception as e:
            logger.error(u'Unable to complete the scan: %s' % e)
        raise cherrypy.HTTPRedirect("home")
    libraryScan.exposed = True

    def magazineScan(self):
        try:
            threading.Thread(target=magazinescan.magazineScan()).start()
        except Exception as e:
            logger.error(u'Unable to complete the scan: %s' % e)
        raise cherrypy.HTTPRedirect("magazines")
    magazineScan.exposed = True

    def importAlternate(self):
        try:
            threading.Thread(target=postprocess.processAlternate(lazylibrarian.ALTERNATE_DIR)).start()
        except Exception as e:
            logger.error(u'Unable to complete the import: %s' % e)
        raise cherrypy.HTTPRedirect("manage")
    importAlternate.exposed = True

    def importCSV(self):
        try:
            threading.Thread(target=postprocess.processCSV(lazylibrarian.ALTERNATE_DIR)).start()
        except Exception as e:
            logger.error(u'Unable to complete the import: %s' % e)
        raise cherrypy.HTTPRedirect("manage")
    importCSV.exposed = True

    def exportCSV(self):
        try:
            threading.Thread(target=postprocess.exportCSV(lazylibrarian.ALTERNATE_DIR)).start()
        except Exception as e:
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

    @cherrypy.expose
    def showJobs(self):
        cherrypy.response.headers[
            'Cache-Control'] = "max-age=0,no-cache,no-store"
        # show the current status of LL cron jobs in the log
        resultlist = common.showJobs()
        result = ''
        for line in resultlist:
            result = result + line + '\n'
        return result

    @cherrypy.expose
    def restartJobs(self):
        common.restartJobs(start='Restart')
        # and list the new run-times in the log
        return self.showJobs()
#    restartJobs.exposed = True

# LOGGING ###########################################################

    def clearLog(self):
        # Clear the log
        result = common.clearLog()
        logger.info(result)
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
            logger.info(
                u'Debug log display OFF, loglevel is %s' %
                lazylibrarian.LOGLEVEL)
        else:
            lazylibrarian.LOGFULL = True
            if lazylibrarian.LOGLEVEL < 2:
                lazylibrarian.LOGLEVEL = 2  # Make sure debug ON
            logger.info(
                u'Debug log display ON, loglevel is %s' %
                lazylibrarian.LOGLEVEL)
        raise cherrypy.HTTPRedirect("logs")
    toggleLog.exposed = True

    def logs(self):
        return serve_template(templatename="logs.html", title="Log", lineList=[])  # lazylibrarian.LOGLIST)
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
        # rows = [[row[0], row[2], row[1]] for row in rows]
        mydict = {'iTotalDisplayRecords': len(filtered),
                'iTotalRecords': len(lazylibrarian.LOGLIST),
                'aaData': rows,
                }
        s = simplejson.dumps(mydict)
        return s
    getLog.exposed = True

# HISTORY ###########################################################

    def history(self, source=None):
        myDB = database.DBConnection()
        if not source:
            # wanted status holds snatched processed for all, plus skipped and
            # ignored for magazine back issues
            history = myDB.select("SELECT * from wanted WHERE Status != 'Skipped' and Status != 'Ignored'")
            return serve_template(templatename="history.html", title="History", history=history)
    history.exposed = True

    def clearhistory(self, status=None):
        myDB = database.DBConnection()
        if status == 'all':
            logger.info(u"Clearing all history")
            myDB.action("DELETE from wanted WHERE Status != 'Skipped' and Status != 'Ignored'")
        else:
            logger.info(u"Clearing history where status is %s" % status)
            myDB.action('DELETE from wanted WHERE Status="%s"' % status)
        raise cherrypy.HTTPRedirect("history")
    clearhistory.exposed = True

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
    def testPushbullet(self):
        cherrypy.response.headers[
            'Cache-Control'] = "max-age=0,no-cache,no-store"

        result = notifiers.pushbullet_notifier.test_notify()
        if result:
            return "Pushbullet notification successful,\n%s" % result
        else:
            return "Pushbullet notification failed"

    @cherrypy.expose
    def testPushover(self):
        cherrypy.response.headers[
            'Cache-Control'] = "max-age=0,no-cache,no-store"

        result = notifiers.pushover_notifier.test_notify()
        if result:
            return "Pushover notification successful,\n%s" % result
        else:
            return "Pushover notification failed"

    @cherrypy.expose
    def testNMA(self):
        cherrypy.response.headers[
            'Cache-Control'] = "max-age=0,no-cache,no-store"

        result = notifiers.nma_notifier.test_notify()
        if result:
            return "Test NMA notice sent successfully"
        else:
            return "Test NMA notice failed"

# API ###############################################################
    @cherrypy.expose
    def api(self, *args, **kwargs):
        from lazylibrarian.api import Api
        a = Api()
        a.checkParams(*args, **kwargs)
        return a.fetchData()

    @cherrypy.expose
    def generateAPI(self):
        api_key = hashlib.sha224(str(random.getrandbits(256))).hexdigest()[0:32]
        lazylibrarian.API_KEY = api_key
        logger.info("New API generated")
        raise cherrypy.HTTPRedirect("config")
    generateAPI.exposed = True

# ALL ELSE ##########################################################

    def forceProcess(self, source=None):
        threading.Thread(target=postprocess.processDir, args=[True, True]).start()
        raise cherrypy.HTTPRedirect(source)
    forceProcess.exposed = True

    def forceSearch(self, source=None):
        if source == "magazines":
            if lazylibrarian.USE_NZB() or lazylibrarian.USE_TOR():
                threading.Thread(target=search_magazines, args=[None, True]).start()
        elif source == "books":
            if lazylibrarian.USE_NZB():
                threading.Thread(target=search_nzb_book).start()
            if lazylibrarian.USE_TOR():
                threading.Thread(target=search_tor_book).start()
            if lazylibrarian.USE_RSS():
                threading.Thread(target=search_rss_book).start()
        else:
            logger.debug(u"forceSearch called with bad source")
        raise cherrypy.HTTPRedirect(source)
    forceSearch.exposed = True

    def manage(self, AuthorName=None, action=None, whichStatus=None, source=None, **args):
        # myDB = database.DBConnection()
        # books only holds status [skipped wanted open have ignored]
        # wanted holds status [snatched processed]
        # books = myDB.select('SELECT * FROM books WHERE Status = ?',
        # [whichStatus])
        if whichStatus is None:
            whichStatus = "Skipped"
        lazylibrarian.MANAGEFILTER = whichStatus
        return serve_template(templatename="managebooks.html", title="Book Status Management",
                              books=[], whichStatus=whichStatus)
    manage.exposed = True

    def getManage(self, iDisplayStart=0, iDisplayLength=100, iSortCol_0=0, sSortDir_0="desc", sSearch="", **kwargs):

        myDB = database.DBConnection()
        iDisplayStart = int(iDisplayStart)
        iDisplayLength = int(iDisplayLength)
        # print "getManage %s" % iDisplayStart
        #   need to filter on whichStatus
        rowlist = myDB.action(
            'SELECT authorname, bookname, series, seriesnum, bookdate, bookid, booklink, booksub from books WHERE STATUS="%s"' %
            lazylibrarian.MANAGEFILTER).fetchall()
        # turn the sqlite rowlist into a list of lists
        d = []
        # the masterlist to be filled with the row data and to be returned
        for i, row in enumerate(rowlist):  # iterate through the sqlite3.Row objects
            l = []  # for each Row use a separate list

            l.append('<td id="select"><input type="checkbox" name="%s" class="checkbox" /></td>' % row[5])
            l.append('<td id="authorname"><a href="authorPage?AuthorName=%s">%s</a></td>' % (row[0], row[0]))

            if row[7]:  # is there a sub-title
                l.append('<td id="bookname"><a href="%s" target="_new">%s</a><br><i class="smalltext">%s</i></td>' % (row[6], row[1], row[7]))
            else:
                l.append('<td id="bookname"><a href="%s" target="_new">%s</a></td>' % (row[6], row[1]))

            if row[2]:  # is the book part of a series
                l.append('<td id="series">%s</td>' % row[2])
            else:
                l.append('<td id="series">None</td>')

            if row[3]:
                l.append('<td id="seriesNum">%s</td>' % row[3])
            else:
                l.append('<td id="seriesNum">None</td>')

            l.append('<td id="date">%s</td>' % row[4])

            d.append(l)  # add the rowlist to the masterlist
        filtered = d

        if sSearch != "":
            filtered = [row for row in d for column in row if sSearch in column]
        sortcolumn = int(iSortCol_0)

        filtered.sort(key=lambda x: x[sortcolumn], reverse=sSortDir_0 == "desc")
        if iDisplayLength < 0:  # display = all
            rows = filtered
        else:
            rows = filtered[iDisplayStart:(iDisplayStart + iDisplayLength)]

        mydict = {'iTotalDisplayRecords': len(filtered),
                  'iTotalRecords': len(rowlist),
                  'aaData': rows,
                  }
        s = simplejson.dumps(mydict)
        # print ("getManage returning %s to %s" % (iDisplayStart, iDisplayStart
        # + iDisplayLength))
        return s
    getManage.exposed = True

    @cherrypy.expose
    def testDeluge(self):
        cherrypy.response.headers['Cache-Control'] = "max-age=0,no-cache,no-store"
        try:
            if not lazylibrarian.DELUGE_USER:
                # no username, talk to the webui
                return deluge.checkLink()

            # if there's a username, talk to the daemon directly
            client = DelugeRPCClient(lazylibrarian.DELUGE_HOST,
                int(lazylibrarian.DELUGE_PORT),
                lazylibrarian.DELUGE_USER,
                lazylibrarian.DELUGE_PASS)
            client.connect()
            if lazylibrarian.DELUGE_LABEL:
                labels = client.call('label.get_labels')
                if not lazylibrarian.DELUGE_LABEL in labels:
                    msg = "Deluge: Unknown label [%s]\n" % lazylibrarian.DELUGE_LABEL
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

