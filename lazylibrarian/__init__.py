from __future__ import with_statement

import os, sys, subprocess, threading, cherrypy, webbrowser, sqlite3

import datetime

from lib.configobj import ConfigObj
from lib.apscheduler.scheduler import Scheduler

import threading

from lazylibrarian import logger, postprocess, searchnzb, SimpleCache

FULL_PATH = None
PROG_DIR = None

ARGS = None
SIGNAL = None

DAEMON = False
PIDFILE = None

SYS_ENCODING = None

SCHED = Scheduler()

INIT_LOCK = threading.Lock()
__INITIALIZED__ = False
started = False

GIT_USER = None
GIT_REPO = None
GIT_BRANCH = None
INSTALL_TYPE = None
CURRENT_VERSION = None
LATEST_VERSION = None
COMMITS_BEHIND = None

DATADIR = None
DBFILE=None
CONFIGFILE = None
CFG = None

LOGDIR = None
LOGLIST = []
#Info 1, Debug 2 - Really should be in the config files.
LOGLEVEL = 2

HTTP_HOST = None
HTTP_PORT = None
HTTP_USER = None
HTTP_PASS = None
HTTP_ROOT = None
HTTP_LOOK = None
LAUNCH_BROWSER = False

SAB_HOST = None
SAB_PORT = None
SAB_SUBDIR=None
SAB_USER = None
SAB_PASS = None
SAB_API = None
SAB_CAT = None

DESTINATION_COPY = False
DESTINATION_DIR = None
DOWNLOAD_DIR = None
BLACKHOLE = False
BLACKHOLEDIR = None
USENET_RETENTION = None

IMP_PREFLANG = None
IMP_ONLYISBN = False
IMP_AUTOADD = None

BOOK_API = None
GR_API = None
GB_API = None

NZBMATRIX = False
NZBMATRIX_USER = None
NZBMATRIX_API = None

NEWZNAB = False
NEWZNAB_HOST = None
NEWZNAB_API = None

NEWZNAB2 = False
NEWZNAB_HOST2 = None
NEWZNAB_API2 = None

NEWZBIN = False
NEWZBIN_UID = None
NEWZBIN_PASSWORD = None
EBOOK_TYPE = None

USENETCRAWLER = False
USENETCRAWLER_API = None
USENETCRAWLER_HOST = None

LATEST_VERSION = None
CURRENT_VERSION = None

VERSIONCHECK_INTERVAL = 24 #Every 2 hours
SEARCH_INTERVAL = 720 #Every 12 hours
SCAN_INTERVAL = 10 #Every 10 minutes

EBOOK_DEST_FOLDER = None
EBOOK_DEST_FILE = None
MAG_DEST_FOLDER = None
MAG_DEST_FILE = None

USE_TWITTER = False
TWITTER_NOTIFY_ONSNATCH = False
TWITTER_NOTIFY_ONDOWNLOAD = False
TWITTER_USERNAME = None
TWITTER_PASSWORD = None
TWITTER_PREFIX = 'LazyLibrarian'

USE_BOXCAR = False
BOXCAR_TOKEN = None
BOXCAR_NOTIFY_ONSNATCH = False
BOXCAR_NOTIFY_ONDOWNLOAD = False
def CheckSection(sec):
    """ Check if INI section exists, if not create it """
    try:
        CFG[sec]
        return True
    except:
        CFG[sec] = {}
        return False

#################################################################################
## Check_setting_int                                                            #
#################################################################################
#def minimax(val, low, high):
#    """ Return value forced within range """
#    try:
#        val = int(val)
#    except:
#        val = 0
#    if val < low:
#        return low
#    if val > high:
#        return high
#    return val

################################################################################
# Check_setting_int                                                            #
################################################################################
def check_setting_int(config, cfg_name, item_name, def_val):
    try:
        my_val = int(config[cfg_name][item_name])
    except:
        my_val = def_val
        try:
            config[cfg_name][item_name] = my_val
        except:
            config[cfg_name] = {}
            config[cfg_name][item_name] = my_val
    logger.debug(item_name + " -> " + str(my_val))
    return my_val

#################################################################################
## Check_setting_float                                                          #
#################################################################################
##def check_setting_float(config, cfg_name, item_name, def_val):
##    try:
##        my_val = float(config[cfg_name][item_name])
##    except:
##        my_val = def_val
##        try:
##            config[cfg_name][item_name] = my_val
##        except:
##            config[cfg_name] = {}
##            config[cfg_name][item_name] = my_val

##    return my_val

################################################################################
# Check_setting_str                                                            #
################################################################################
def check_setting_str(config, cfg_name, item_name, def_val, log=True):
    try:
        my_val = config[cfg_name][item_name]
    except:
        my_val = def_val
        try:
            config[cfg_name][item_name] = my_val
        except:
            config[cfg_name] = {}
            config[cfg_name][item_name] = my_val

    if log:
        logger.debug(item_name + " -> " + my_val)
    else:
        logger.debug(item_name + " -> ******")

    return my_val

def initialize():

    with INIT_LOCK:

        global __INITIALIZED__, FULL_PATH, PROG_DIR, LOGLEVEL, DAEMON, DATADIR, CONFIGFILE, CFG, LOGDIR, HTTP_HOST, HTTP_PORT, HTTP_USER, HTTP_PASS, HTTP_ROOT, HTTP_LOOK, LAUNCH_BROWSER, LOGDIR, CACHEDIR, \
            IMP_ONLYISBN, IMP_PREFLANG, IMP_AUTOADD, SAB_HOST, SAB_PORT, SAB_SUBDIR, SAB_API, SAB_USER, SAB_PASS, DESTINATION_DIR, DESTINATION_COPY, DOWNLOAD_DIR, SAB_CAT, USENET_RETENTION, BLACKHOLE, BLACKHOLEDIR, GR_API, GB_API, BOOK_API, \
            NZBMATRIX, NZBMATRIX_USER, NZBMATRIX_API, NEWZNAB, NEWZNAB_HOST, NEWZNAB_API, NEWZBIN, NEWZBIN_UID, NEWZBIN_PASS, NEWZNAB2, NEWZNAB_HOST2, NEWZNAB_API2, EBOOK_TYPE, USENETCRAWLER, USENETCRAWLER_HOST, USENETCRAWLER_API, \
            VERSIONCHECK_INTERVAL, SEARCH_INTERVAL, SCAN_INTERVAL, EBOOK_DEST_FOLDER, EBOOK_DEST_FILE, MAG_DEST_FOLDER, MAG_DEST_FILE, USE_TWITTER, TWITTER_NOTIFY_ONSNATCH, TWITTER_NOTIFY_ONDOWNLOAD, TWITTER_USERNAME, TWITTER_PASSWORD, TWITTER_PREFIX, \
	    USE_BOXCAR, BOXCAR_NOTIFY_ONSNATCH, BOXCAR_NOTIFY_ONDOWNLOAD, BOXCAR_TOKEN, \
            GIT_USER, GIT_REPO, GIT_BRANCH, INSTALL_TYPE, CURRENT_VERSION, LATEST_VERSION, COMMITS_BEHIND

        if __INITIALIZED__:
            return False

        CheckSection('General')
        CheckSection('SABnzbd')
        CheckSection('Version')

        try:
            HTTP_PORT = check_setting_int(CFG, 'General', 'http_port', 5299)
        except:
            HTTP_PORT = 5299

        if HTTP_PORT < 21 or HTTP_PORT > 65535:
            HTTP_PORT = 5299

        LOGDIR = check_setting_str(CFG, 'General', 'logdir', '')
        if not LOGDIR:
            LOGDIR = os.path.join(DATADIR, 'Logs')
        # Create logdir
        if not os.path.exists(LOGDIR):
            try:
                os.makedirs(LOGDIR)
            except OSError:
                if LOGLEVEL:
                    print LOGDIR + ":"
                    print ' Unable to create folder for logs. Only logging to console.'

        # Start the logger, silence console logging if we need to
        CFGLOGLEVEL = check_setting_int(CFG, 'General', 'loglevel', 3)
        if CFGLOGLEVEL == 3:    #default value if none in config
            LOGLEVEL=2    #If not set in Config, then lets set to DEBUG
        else:
            LOGLEVEL = CFGLOGLEVEL  #Config setting picked up
            
            
            
        logger.lazylibrarian_log.initLogger(loglevel=LOGLEVEL)
        logger.info("Log level set to [%s]- Log Directory is [%s] - Config level is [%s]" % (LOGLEVEL,LOGDIR,CFGLOGLEVEL))


        HTTP_HOST = check_setting_str(CFG, 'General', 'http_host', '0.0.0.0')
        HTTP_USER = check_setting_str(CFG, 'General', 'http_user', '')
        HTTP_PASS = check_setting_str(CFG, 'General', 'http_pass', '')
        HTTP_ROOT = check_setting_str(CFG, 'General', 'http_root', '')
        HTTP_LOOK = check_setting_str(CFG, 'General', 'http_look', 'default')



        LAUNCH_BROWSER = bool(check_setting_int(CFG, 'General', 'launch_browser', 1))
        LOGDIR = check_setting_str(CFG, 'General', 'logdir', '')

        IMP_PREFLANG = check_setting_str(CFG, 'General', 'imp_preflang', 'en, eng, en-US')
        IMP_AUTOADD = check_setting_str(CFG, 'General', 'imp_autoadd', '')
        IMP_ONLYISBN = bool(check_setting_int(CFG, 'General', 'imp_onlyisbn', 0))
        #TODO - investigate this for future users
        #Something funny here - putting IMP_AUTOADD after IMP_ONLYISBN resulted in it not working
        #Couldn't see it
            
        GIT_USER = check_setting_str(CFG, 'Git', 'git_user', 'dobytang')
        GIT_REPO = check_setting_str(CFG, 'Git', 'git_repo', 'lazylibrarian')
        GIT_BRANCH = check_setting_str(CFG, 'Git', 'git_branch', 'master')
        INSTALL_TYPE = check_setting_str(CFG, 'Git', 'install_type', '')
        CURRENT_VERSION = check_setting_str(CFG, 'Git', 'current_version', '')
        LATEST_VERSION = check_setting_str(CFG, 'Git', 'latest_version', '')
        COMMITS_BEHIND = check_setting_str(CFG, 'Git', 'commits_behind', '')

        SAB_HOST = check_setting_str(CFG, 'SABnzbd', 'sab_host', '')
        SAB_PORT = check_setting_str(CFG, 'SABnzbd', 'sab_port', '')
        SAB_SUBDIR = check_setting_str(CFG, 'SABnzbd', 'sab_subdir', '')
        SAB_USER = check_setting_str(CFG, 'SABnzbd', 'sab_user', '')
        SAB_PASS = check_setting_str(CFG, 'SABnzbd', 'sab_pass', '')
        SAB_API = check_setting_str(CFG, 'SABnzbd', 'sab_api', '')
        SAB_CAT = check_setting_str(CFG, 'SABnzbd', 'sab_cat', '')


        DESTINATION_COPY = bool(check_setting_int(CFG, 'General', 'destination_copy', 0))
        DESTINATION_DIR = check_setting_str(CFG, 'General','destination_dir', '')
        DOWNLOAD_DIR = check_setting_str(CFG, 'General', 'download_dir', '')
        BLACKHOLE = bool(check_setting_int(CFG, 'General', 'blackhole', 0))
        BLACKHOLEDIR = check_setting_str(CFG, 'General', 'blackholedir', '')
        USENET_RETENTION = check_setting_str(CFG, 'General', 'usenet_retention', '')

        NZBMATRIX = bool(check_setting_int(CFG, 'NZBMatrix', 'nzbmatrix', 0))
        NZBMATRIX_USER = check_setting_str(CFG, 'NZBMatrix', 'nzbmatrix_user', '')
        NZBMATRIX_API = check_setting_str(CFG, 'NZBMatrix', 'nzbmatrix_api', '')
        
        NEWZNAB = bool(check_setting_int(CFG, 'Newznab', 'newznab', 0))
        NEWZNAB_HOST = check_setting_str(CFG, 'Newznab', 'newznab_host', '')
        NEWZNAB_API = check_setting_str(CFG, 'Newznab', 'newznab_api', '')
        NEWZNAB2 = bool(check_setting_int(CFG, 'Newznab2', 'newznab2', 0))
        NEWZNAB_HOST2 = check_setting_str(CFG, 'Newznab2', 'newznab_host2', '')
        NEWZNAB_API2 = check_setting_str(CFG, 'Newznab2', 'newznab_api2', '')

        USENETCRAWLER = bool(check_setting_int(CFG, 'UsenetCrawler', 'usenetcrawler', 0))
        USENETCRAWLER_HOST = check_setting_str(CFG, 'UsenetCrawler', 'usenetcrawler_host', '')
        USENETCRAWLER_API = check_setting_str(CFG, 'UsenetCrawler', 'usenetcrawler_api', '')

        NEWZBIN = bool(check_setting_int(CFG, 'Newzbin', 'newzbin', 0))
        NEWZBIN_UID = check_setting_str(CFG, 'Newzbin', 'newzbin_uid', '')
        NEWZBIN_PASS = check_setting_str(CFG, 'Newzbin', 'newzbin_pass', '')
        EBOOK_TYPE = check_setting_str(CFG, 'General', 'ebook_type', 'epub, mobi, pdf')

        SEARCH_INTERVAL = int(check_setting_str(CFG, 'SearchScan', 'search_interval', '360'))
        SCAN_INTERVAL = int(check_setting_str(CFG, 'SearchScan', 'scan_interval', '10'))
        VERSIONCHECK_INTERVAL = int(check_setting_str(CFG, 'SearchScan', 'versioncheck_interval', '24'))

        EBOOK_DEST_FOLDER = check_setting_str(CFG, 'PostProcess', 'ebook_dest_folder', '$Author/$Title')
        EBOOK_DEST_FILE = check_setting_str(CFG, 'PostProcess', 'ebook_dest_file', '$Title - $Author')
        MAG_DEST_FOLDER = check_setting_str(CFG, 'PostProcess', 'mag_dest_folder', '_Magazines/$Title/$IssueDate')
        MAG_DEST_FILE = check_setting_str(CFG, 'PostProcess', 'mag_dest_file', '$IssueDate - $Title')

        USE_TWITTER = bool(check_setting_int(CFG, 'Twitter', 'use_twitter', 0))
        TWITTER_NOTIFY_ONSNATCH = bool(check_setting_int(CFG, 'Twitter', 'twitter_notify_onsnatch', 0))
        TWITTER_NOTIFY_ONDOWNLOAD = bool(check_setting_int(CFG, 'Twitter', 'twitter_notify_ondownload', 0))
        TWITTER_USERNAME = check_setting_str(CFG, 'Twitter', 'twitter_username', '')
        TWITTER_PASSWORD = check_setting_str(CFG, 'Twitter', 'twitter_password', '')
        TWITTER_PREFIX = check_setting_str(CFG, 'Twitter', 'twitter_prefix', 'LazyLibrarian')

	USE_BOXCAR = bool(check_setting_int(CFG, 'Boxcar', 'use_boxcar',0))
	BOXCAR_NOTIFY_ONSNATCH = bool(check_setting_int(CFG, 'Boxcar', 'boxcar_notify_onsnatch', 0))
	BOXCAR_NOTIFY_ONDOWNLOAD = bool(check_setting_int(CFG, 'Boxcar', 'boxcar_notify_ondownload', 0))
	BOXCAR_TOKEN = check_setting_str(CFG, 'Boxcar', 'boxcar_token', '')


        BOOK_API = check_setting_str(CFG, 'API', 'book_api', 'GoodReads')
        GR_API = check_setting_str(CFG, 'API', 'gr_api', 'ckvsiSDsuqh7omh74ZZ6Q')
        GB_API = check_setting_str(CFG, 'API', 'gb_api', '')

        if not LOGDIR:
            LOGDIR = os.path.join(DATADIR, 'Logs')

        # Put the cache dir in the data dir for now
        CACHEDIR = os.path.join(DATADIR, 'cache')
        if not os.path.exists(CACHEDIR):
            try:
                os.makedirs(CACHEDIR)
            except OSError:
                logger.error('Could not create cachedir. Check permissions of: ' + DATADIR)

        # Initialize the database
        try:
            dbcheck()
        except Exception, e:
            logger.error("Can't connect to the database: %s" % e)

        __INITIALIZED__ = True
        return True

def daemonize():
    """
    Fork off as a daemon
    """

    # Make a non-session-leader child process
    try:
        pid = os.fork() #@UndefinedVariable - only available in UNIX
        if pid != 0:
            sys.exit(0)
    except OSError, e:
        raise RuntimeError("1st fork failed: %s [%d]" %
                   (e.strerror, e.errno))

    os.setsid() #@UndefinedVariable - only available in UNIX

    # Make sure I can read my own files and shut out others
    prev = os.umask(0)
    os.umask(prev and int('077', 8))

    # Make the child a session-leader by detaching from the terminal
    try:
        pid = os.fork() #@UndefinedVariable - only available in UNIX
        if pid != 0:
            sys.exit(0)
    except OSError, e:
        raise RuntimeError("2st fork failed: %s [%d]" %
                   (e.strerror, e.errno))

    dev_null = file('/dev/null', 'r')
    os.dup2(dev_null.fileno(), sys.stdin.fileno())

    if PIDFILE:
        pid = str(os.getpid())
        logger.debug(u"Writing PID " + pid + " to " + str(PIDFILE))
        file(PIDFILE, 'w').write("%s\n" % pid)

def launch_browser(host, port, root):
    if host == '0.0.0.0':
        host = 'localhost'

    try:
        webbrowser.open('http://%s:%i%s' % (host, port, root))
    except Exception, e:
        logger.error('Could not launch browser: %s' % e)

def config_write():
    new_config = ConfigObj()
    new_config.filename = CONFIGFILE

    new_config['General'] = {}
    new_config['General']['http_port'] = HTTP_PORT
    new_config['General']['http_host'] = HTTP_HOST
    new_config['General']['http_user'] = HTTP_USER
    new_config['General']['http_pass'] = HTTP_PASS
    new_config['General']['http_root'] = HTTP_ROOT
    new_config['General']['http_look'] = HTTP_LOOK
    new_config['General']['launch_browser'] = int(LAUNCH_BROWSER)
    new_config['General']['logdir'] = LOGDIR
    new_config['General']['loglevel'] = int(LOGLEVEL)

    new_config['General']['imp_onlyisbn'] = int(IMP_ONLYISBN)
    new_config['General']['imp_preflang'] = IMP_PREFLANG
    new_config['General']['imp_autoadd'] =  IMP_AUTOADD

    new_config['General']['ebook_type'] = EBOOK_TYPE

    new_config['Git'] = {}
    new_config['Git']['git_user'] = GIT_USER
    new_config['Git']['git_repo'] = GIT_REPO
    new_config['Git']['git_branch'] = GIT_BRANCH
    new_config['Git']['install_type'] = INSTALL_TYPE
    new_config['Git']['current_version'] = CURRENT_VERSION
    new_config['Git']['latest_version'] = LATEST_VERSION
    new_config['Git']['commits_behind'] = COMMITS_BEHIND

    new_config['SABnzbd'] = {}
    new_config['SABnzbd']['sab_host'] = SAB_HOST
    new_config['SABnzbd']['sab_port'] = SAB_PORT
    new_config['SABnzbd']['sab_subdir'] = SAB_SUBDIR
    new_config['SABnzbd']['sab_user'] = SAB_USER
    new_config['SABnzbd']['sab_pass'] = SAB_PASS
    new_config['SABnzbd']['sab_api'] = SAB_API
    new_config['SABnzbd']['sab_cat'] = SAB_CAT

    new_config['General']['destination_dir'] = DESTINATION_DIR
    new_config['General']['destination_copy'] = int(DESTINATION_COPY)
    new_config['General']['download_dir'] = DOWNLOAD_DIR
    new_config['General']['blackhole'] = int(BLACKHOLE)
    new_config['General']['blackholedir'] = BLACKHOLEDIR
    new_config['General']['usenet_retention'] = USENET_RETENTION
    
    new_config['API'] = {}
    new_config['API']['book_api'] = BOOK_API
    new_config['API']['gr_api'] = GR_API
    new_config['API']['gb_api'] = GB_API

    new_config['NZBMatrix'] = {}
    new_config['NZBMatrix']['nzbmatrix'] = int(NZBMATRIX)
    new_config['NZBMatrix']['nzbmatrix_user'] = NZBMATRIX_USER
    new_config['NZBMatrix']['nzbmatrix_api'] = NZBMATRIX_API

    new_config['Newznab'] = {}
    new_config['Newznab']['newznab'] = int(NEWZNAB)
    new_config['Newznab']['newznab_host'] = NEWZNAB_HOST
    new_config['Newznab']['newznab_api'] = NEWZNAB_API

    new_config['Newznab2'] = {}
    new_config['Newznab2']['newznab2'] = int(NEWZNAB2)
    new_config['Newznab2']['newznab_host2'] = NEWZNAB_HOST2
    new_config['Newznab2']['newznab_api2'] = NEWZNAB_API2

    new_config['Newzbin'] = {}
    new_config['Newzbin']['newzbin'] = int(NEWZBIN)
    new_config['Newzbin']['newzbin_uid'] = NEWZBIN_UID
    new_config['Newzbin']['newzbin_pass'] = NEWZBIN_PASS

    new_config['UsenetCrawler'] = {}
    new_config['UsenetCrawler']['usenetcrawler'] = int(USENETCRAWLER)
    new_config['UsenetCrawler']['usenetcrawler_host'] = USENETCRAWLER_HOST
    new_config['UsenetCrawler']['usenetcrawler_api'] = USENETCRAWLER_API

    new_config['SearchScan'] = {}
    new_config['SearchScan']['search_interval'] = SEARCH_INTERVAL
    new_config['SearchScan']['scan_interval'] = SCAN_INTERVAL
    new_config['SearchScan']['versioncheck_interval'] = VERSIONCHECK_INTERVAL

    new_config['PostProcess'] = {}
    new_config['PostProcess']['ebook_dest_folder'] = EBOOK_DEST_FOLDER
    new_config['PostProcess']['ebook_dest_file'] = EBOOK_DEST_FILE
    new_config['PostProcess']['mag_dest_folder'] = MAG_DEST_FOLDER
    new_config['PostProcess']['mag_dest_file'] = MAG_DEST_FILE

    new_config['Twitter'] = {}
    new_config['Twitter']['use_twitter'] = int(USE_TWITTER)
    new_config['Twitter']['twitter_notify_onsnatch'] = int(TWITTER_NOTIFY_ONSNATCH)
    new_config['Twitter']['twitter_notify_ondownload'] = int(TWITTER_NOTIFY_ONDOWNLOAD)
    new_config['Twitter']['twitter_username'] = TWITTER_USERNAME
    new_config['Twitter']['twitter_password'] = TWITTER_PASSWORD
    new_config['Twitter']['twitter_prefix'] = TWITTER_PREFIX

    new_config['Boxcar'] = {}
    new_config['Boxcar']['use_boxcar'] = int(USE_BOXCAR)
    new_config['Boxcar']['boxcar_notify_onsnatch'] = int(BOXCAR_NOTIFY_ONSNATCH)
    new_config['Boxcar']['boxcar_notify_ondownload'] = int(BOXCAR_NOTIFY_ONDOWNLOAD)
    new_config['Boxcar']['boxcar_token'] = BOXCAR_TOKEN

    new_config.write()

def dbcheck():

    conn=sqlite3.connect(DBFILE)
    c=conn.cursor()
    c.execute('CREATE TABLE IF NOT EXISTS authors (AuthorID TEXT, AuthorName TEXT UNIQUE, AuthorImg TEXT, AuthorLink TEXT, DateAdded TEXT, Status TEXT, LastBook TEXT, LastLink Text, LastDate TEXT, HaveBooks INTEGER, TotalBooks INTEGER, AuthorBorn TEXT, AuthorDeath TEXT, UnignoredBooks INTEGER)')
    c.execute('CREATE TABLE IF NOT EXISTS books (AuthorID TEXT, AuthorName TEXT, AuthorLink TEXT, BookName TEXT, BookSub TEXT, BookDesc TEXT, BookGenre TEXT, BookIsbn TEXT, BookPub TEXT, BookRate INTEGER, BookImg TEXT, BookPages INTEGER, BookLink TEXT, BookID TEXT UNIQUE, BookDate TEXT, BookLang TEXT, BookAdded TEXT, Status TEXT)')
    c.execute('CREATE TABLE IF NOT EXISTS wanted (BookID TEXT, NZBurl TEXT, NZBtitle TEXT, NZBdate TEXT, NZBprov TEXT, Status TEXT, NZBsize TEXT, AuxInfo TEXT)')
    c.execute('CREATE TABLE IF NOT EXISTS magazines (Title TEXT, Frequency TEXT, Regex TEXT, Status TEXT, MagazineAdded TEXT, LastAcquired TEXT, IssueDate TEXT, IssueStatus TEXT)')

    try:
        logger.info('Checking database')
        c.execute('SELECT BookSub from books')
    except sqlite3.OperationalError:
        logger.info('Updating database to hold book subtitles.')
        c.execute('ALTER TABLE books ADD COLUMN BookSub TEXT')

    try:
        c.execute('SELECT BookPub from books')
    except sqlite3.OperationalError:
        logger.info('Updating database to hold book publisher')
        c.execute('ALTER TABLE books ADD COLUMN BookPub TEXT')

    try:
        c.execute('SELECT BookGenre from books')
    except sqlite3.OperationalError:
        logger.info('Updating database to hold bookgenre')
        c.execute('ALTER TABLE books ADD COLUMN BookGenre TEXT')

    try:
        c.execute('SELECT AuxInfo from wanted')
    except sqlite3.OperationalError:
        logger.info('Updating database to hold AuxInfo')
        c.execute('ALTER TABLE wanted ADD COLUMN AuxInfo TEXT')

    try:
        c.execute('SELECT NZBsize from wanted')
    except sqlite3.OperationalError:
        logger.info('Updating database to hold NZBside')
        c.execute('ALTER TABLE wanted ADD COLUMN NZBsize TEXT')

    try:
        c.execute('SELECT UnignoredBooks from authors')
    except sqlite3.OperationalError:
        logger.info('Updating database to hold UnignoredBooks')
        c.execute('ALTER TABLE authors ADD COLUMN UnignoredBooks INTEGER')

    try:
        c.execute('SELECT IssueStatus from magazines')
    except sqlite3.OperationalError:
        logger.info('Updating database to hold IssueStatus')
        c.execute('ALTER TABLE magazines ADD COLUMN IssueStatus TEXT')

    conn.commit()
    c.close()

    try:
        myDB = database.DBConnection()
        author = myDB.select('SELECT AuthorID FROM authors WHERE AuthorName IS NULL')
        if author:
            logger.info('Removing un-named author from database')
            authorid = author[0]["AuthorID"];
            myDB.action('DELETE from authors WHERE AuthorID=?', [authorid])
            myDB.action('DELETE from books WHERE AuthorID=?', [authorid])
    except Exception, z:
        logger.info('Error: ' + str(z))

def start():
    global __INITIALIZED__, started

    if __INITIALIZED__:

        # Crons and scheduled jobs go here
        starttime = datetime.datetime.now()
        SCHED.add_interval_job(postprocess.processDir, minutes=SCAN_INTERVAL)
        SCHED.add_interval_job(searchnzb.searchbook, minutes=SEARCH_INTERVAL)
        SCHED.add_interval_job(versioncheck.checkForUpdates, hours=VERSIONCHECK_INTERVAL)

        SCHED.start()
#        for job in SCHED.get_jobs():
#            print job
        started = True

def shutdown(restart=False, update=False):

    cherrypy.engine.exit()
    SCHED.shutdown(wait=False)
    config_write()

    if not restart and not update:
        logger.info('LazyLibrarian is shutting down...')
    if update:
        logger.info('LazyLibrarian is updating...')
        try:
            versioncheck.update()
        except Exception, e:
            logger.warn('LazyLibrarian failed to update: %s. Restarting.' % e) 

    if PIDFILE :
        logger.info('Removing pidfile %s' % PIDFILE)
        os.remove(PIDFILE)

    if restart:
        logger.info('LazyLibrarian is restarting ...')
        popen_list = [sys.executable, FULL_PATH]
        popen_list += ARGS
        if '--nolaunch' not in popen_list:
            popen_list += ['--nolaunch']
            logger.info('Restarting LazyLibrarian with ' + str(popen_list))
        subprocess.Popen(popen_list, cwd=os.getcwd())

    os._exit(0)
