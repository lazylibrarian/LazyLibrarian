from __future__ import with_statement

import os
import sys
import subprocess
import threading
import cherrypy
import webbrowser
import sqlite3
import re

import datetime
import locale
import calendar
import time
import subprocess
import ConfigParser
from lib.apscheduler.scheduler import Scheduler

import urllib2
import socket
import json

from lazylibrarian import logger, postprocess, searchnzb, searchtorrents, searchrss, formatter, \
    librarysync, versioncheck, database, searchmag, magazinescan, common, bookwork

try:
    from wand.image import Image
    MAGICK = "wand"
except ImportError:
    try:
        import PythonMagick
        MAGICK = "pythonmagick"
    except:
        MAGICK = 'convert'  # may have external, don't know yet

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
COMMIT_LIST = None

DATADIR = None
DBFILE = None
CONFIGFILE = None
CFG = None

LOGDIR = None
LOGLIST = []
# Info 1, Debug 2, >2 don't toggle console/file
LOGLEVEL = 2
LOGLIMIT = 500
LOGFULL = False  # include debug on screen if true
LOGFILES = 10  # 10 log files
LOGSIZE = 204800  # each up to 200K

MATCH_RATIO = 80

HTTP_HOST = None
HTTP_PORT = 5299
HTTP_USER = None
HTTP_PASS = None
HTTP_PROXY = None
HTTP_ROOT = None
HTTP_LOOK = None
HTTPS_ENABLED = 0
HTTPS_CERT = None
HTTPS_KEY = None
LAUNCH_BROWSER = 0
API_ENABLED = 0
API_KEY = None

PROXY_HOST = None
PROXY_TYPE = None

SAB_HOST = None
SAB_PORT = 0
SAB_SUBDIR = None
SAB_USER = None
SAB_PASS = None
SAB_API = None
SAB_CAT = None

NZBGET_HOST = None
NZBGET_PORT = 0
NZBGET_USER = None
NZBGET_PASS = None
NZBGET_CATEGORY = None
NZBGET_PRIORITY = 0

DESTINATION_COPY = 0
DESTINATION_DIR = None
ALTERNATE_DIR = None
DOWNLOAD_DIR = None

IMP_PREFLANG = None
IMP_MONTHLANG = None
IMP_ONLYISBN = 0
IMP_SINGLEBOOK = 1
IMP_AUTOADD = None
IMP_CONVERT = None
GIT_PROGRAM = None

BOOK_API = None
GR_API = None
GB_API = None

NZBMATRIX = 0
NZBMATRIX_USER = None
NZBMATRIX_API = None

NEWZBIN = 0
NEWZBIN_UID = None
NEWZBIN_PASSWORD = None
EBOOK_TYPE = None
MAG_TYPE = None
REJECT_WORDS = None
REJECT_MAXSIZE = 0

TOR_DOWNLOADER_BLACKHOLE = 0
TOR_DOWNLOADER_UTORRENT = 0
TOR_DOWNLOADER_QBITTORRENT = 0
TOR_DOWNLOADER_TRANSMISSION = 0
TOR_DOWNLOADER_DELUGE = 0
NUMBEROFSEEDERS = 10
TORRENT_DIR = None

UTORRENT_HOST = None
UTORRENT_PORT = 0
UTORRENT_USER = None
UTORRENT_PASS = None
UTORRENT_LABEL = None

QBITTORRENT_HOST = None
QBITTORRENT_PORT = 0
QBITTORRENT_USER = None
QBITTORRENT_PASS = None
QBITTORRENT_LABEL = None

TRANSMISSION_HOST = None
TRANSMISSION_PORT = 0
TRANSMISSION_USER = None
TRANSMISSION_PASS = None

DELUGE_PORT = 0
DELUGE_HOST = None
DELUGE_USER = None
DELUGE_PASS = None
DELUGE_LABEL = None

KAT = 0
KAT_HOST = None

NZB_DOWNLOADER_SABNZBD = 0
NZB_DOWNLOADER_NZBGET = 0
NZB_DOWNLOADER_BLACKHOLE = 0
NZB_BLACKHOLEDIR = None
USENET_RETENTION = 0

VERSIONCHECK_INTERVAL = 24  # Every 2 hours
SEARCH_INTERVAL = 720  # Every 12 hours
SCAN_INTERVAL = 10  # Every 10 minutes
SEARCHRSS_INTERVAL = 20  # Every 20 minutes
FULL_SCAN = 0  # full scan would remove books from db
ADD_AUTHOR = 1  # auto add authors not found in db from goodreads
# value to mark missing books (deleted/removed) in db, can be 'Open', 'Ignored', 'Wanted','Skipped'
NOTFOUND_STATUS = 'Skipped'
# value to mark new books (when importing a new author), can be 'Open', 'Ignored', 'Wanted','Skipped'
NEWBOOK_STATUS = 'Skipped'
EBOOK_DEST_FOLDER = None
EBOOK_DEST_FILE = None
MAG_DEST_FOLDER = None
MAG_DEST_FILE = None
MAG_RELATIVE = 1

USE_TWITTER = 0
TWITTER_NOTIFY_ONSNATCH = 0
TWITTER_NOTIFY_ONDOWNLOAD = 0
TWITTER_USERNAME = None
TWITTER_PASSWORD = None
TWITTER_PREFIX = 'LazyLibrarian'

USE_BOXCAR = 0
BOXCAR_TOKEN = None
BOXCAR_NOTIFY_ONSNATCH = 0
BOXCAR_NOTIFY_ONDOWNLOAD = 0

USE_PUSHBULLET = 0
PUSHBULLET_TOKEN = None
PUSHBULLET_DEVICEID = None
PUSHBULLET_NOTIFY_ONSNATCH = 0
PUSHBULLET_NOTIFY_ONDOWNLOAD = 0

USE_PUSHOVER = 0
PUSHOVER_APITOKEN = None
PUSHOVER_KEYS = None
PUSHOVER_DEVICE = None
PUSHOVER_ONSNATCH = 0
PUSHOVER_ONDOWNLOAD = 0
PUSHOVER_PRIORITY = 0

USE_ANDROIDPN = 0
ANDROIDPN_NOTIFY_ONSNATCH = 0
ANDROIDPN_NOTIFY_ONDOWNLOAD = 0
ANDROIDPN_URL = None
ANDROIDPN_BROADCAST = 0
ANDROIDPN_USERNAME = None

USE_NMA = 0
NMA_APIKEY = None
NMA_PRIORITY = 0
NMA_ONSNATCH = None
NMA_ONDOWNLOAD = None

# Month names table to hold long/short month names for multiple languages
# which we can match against magazine issues
# Defined as global and initialised early, because locale changes are not thread safe
# This means changes to languages require a restart
MONTH0 = ['en_GB.UTF-8', 'en_GB.UTF-8']  # This holds the language code
MONTH1 = [u'january', u'jan']  # multiple names for first month
MONTH2 = [u'february', u'feb']  # etc...
MONTH3 = [u'march', u'mar']
MONTH4 = [u'april', u'apr']
MONTH5 = [u'may', u'may']
MONTH6 = [u'june', u'jun']
MONTH7 = [u'july', u'jul']
MONTH8 = [u'august', u'aug']
MONTH9 = [u'september', u'sep']
MONTH10 = [u'october', u'oct']
MONTH11 = [u'november', u'nov']
MONTH12 = [u'december', u'dec']
MONTHNAMES = [MONTH0, MONTH1, MONTH2, MONTH3, MONTH4, MONTH5, MONTH6,
              MONTH7, MONTH8, MONTH9, MONTH10, MONTH11, MONTH12]
CACHE_HIT = 0
CACHE_MISS = 0
LAST_GOODREADS = 0
LAST_LIBRARYTHING = 0
CACHE_AGE = 30

BOOKSTRAP_THEME = ''
BOOKSTRAP_THEMELIST = []


def check_section(sec):
    """ Check if INI section exists, if not create it """
    if CFG.has_section(sec):
        return True
    else:
        CFG.add_section(sec)
        return False


def check_setting_bool(config, cfg_name, item_name, def_val, log=True):
    """ Check if option exists and coerce to boolean, if not create it """
    try:
        my_val = config.getboolean(cfg_name, item_name)
    except:
        my_val = def_val
        check_section(cfg_name)
        config.set(cfg_name, item_name, my_val)
    if log:
        logger.debug(cfg_name + ":" + item_name + " -> " + str(my_val))
    return my_val


def check_setting_int(config, cfg_name, item_name, def_val, log=True):
    """ Check if option exists and coerce to int, if not create it """
    try:
        my_val = config.getint(cfg_name, item_name)
    except:
        my_val = def_val
        check_section(cfg_name)
        config.set(cfg_name, item_name, my_val)
    if log:
        logger.debug(cfg_name + ":" + item_name + " -> " + str(my_val))
    return my_val


def check_setting_str(config, cfg_name, item_name, def_val, log=True):
    """ Check if option exists and coerce to string, if not create it """
    try:
        my_val = config.get(cfg_name, item_name)
        # Old config file format had strings in quotes. ConfigParser doesn't.
        if my_val.startswith('"'):
            my_val = my_val[1:]
        if my_val.endswith('"'):
            my_val = my_val[:-1]
    except:
        my_val = def_val
        check_section(cfg_name)
        config.set(cfg_name, item_name, my_val)
    if log:
        logger.debug(cfg_name + ":" + item_name + " -> " + my_val)

    return my_val.decode('utf-8')

def initialize():

    with INIT_LOCK:
        global __INITIALIZED__, LOGDIR, LOGLIMIT, LOGFILES, LOGSIZE, CFG, CFGLOGLEVEL, LOGLEVEL, \
            LOGFULL, CACHEDIR, DATADIR, LAST_LIBRARYTHING, LAST_GOODREADS, BOOKLANGFILTER, MANAGEFILTER, \
            ISSUEFILTER, IMP_MONTHLANG, BOOKSTRAP_THEMELIST

        if __INITIALIZED__:
            return False

        check_section('General')

        LOGDIR = check_setting_str(CFG, 'General', 'logdir', '')
        LOGLIMIT = check_setting_int(CFG, 'General', 'loglimit', 500)
        LOGFILES = check_setting_int(CFG, 'General', 'logfiles', 10)
        LOGSIZE = check_setting_int(CFG, 'General', 'logsize', 204800)

        if not LOGDIR:
            LOGDIR = os.path.join(DATADIR, 'Logs')
        # Create logdir
        if not os.path.exists(LOGDIR):
            try:
                os.makedirs(LOGDIR)
            except OSError:
                if LOGLEVEL:
                    print '%s : Unable to create folder for logs. Only logging to console.' % LOGDIR

        # Start the logger, silence console logging if we need to
        CFGLOGLEVEL = check_setting_int(CFG, 'General', 'loglevel', 3)
        if CFGLOGLEVEL == 3:  # default value if none in config
            LOGLEVEL = 2  # If not set in Config, then lets set to DEBUG
        else:
            LOGLEVEL = CFGLOGLEVEL  # Config setting picked up

        logger.lazylibrarian_log.initLogger(loglevel=LOGLEVEL)
        logger.info("Log level set to [%s]- Log Directory is [%s] - Config level is [%s]" % (
            LOGLEVEL, LOGDIR, CFGLOGLEVEL))
        if LOGLEVEL > 2:
            LOGFULL = True
            logger.info("Screen Log set to DEBUG")
        else:
            LOGFULL = False
            logger.info("Screen Log set to INFO/WARN/ERROR")

        config_read()

        # Put the cache dir in the data dir for now
        CACHEDIR = os.path.join(DATADIR, 'cache')
        if not os.path.exists(CACHEDIR):
            try:
                os.makedirs(CACHEDIR)
            except OSError:
                logger.error('Could not create cachedir. Check permissions of: ' + DATADIR)

        # keep track of last api calls so we don't call more than once per second
        # to respect api terms, but don't wait un-necessarily either
        time_now = int(time.time())
        LAST_LIBRARYTHING = time_now
        LAST_GOODREADS = time_now

        MANAGEFILTER = "Skipped"
        ISSUEFILTER = "Skipped"
        BOOKLANGFILTER = "eng"

        # Initialize the database
        try:
            dbcheck()
        except Exception as e:
            logger.error("Can't connect to the database: %s" % e)

        build_monthtable()
        BOOKSTRAP_THEMELIST = build_bookstrap_themes()

        __INITIALIZED__ = True
        return True

def config_read(reloaded=False):
        global FULL_PATH, PROG_DIR, DAEMON, \
            HTTP_HOST, HTTP_PORT, HTTP_USER, HTTP_PASS, HTTP_PROXY, HTTP_ROOT, HTTP_LOOK, API_KEY, API_ENABLED, \
            LAUNCH_BROWSER, LOGDIR, CACHE_AGE, MATCH_RATIO, PROXY_HOST, PROXY_TYPE, GIT_PROGRAM, \
            IMP_ONLYISBN, IMP_SINGLEBOOK, IMP_PREFLANG, IMP_MONTHLANG, IMP_AUTOADD, IMP_CONVERT, \
            MONTHNAMES, MONTH0, MONTH1, MONTH2, MONTH3, MONTH4, MONTH5, MONTH6, MONTH7, \
            MONTH8, MONTH9, MONTH10, MONTH11, MONTH12, CONFIGFILE, CFG, LOGLIMIT, \
            SAB_HOST, SAB_PORT, SAB_SUBDIR, SAB_API, SAB_USER, SAB_PASS, SAB_CAT, \
            DESTINATION_DIR, DESTINATION_COPY, DOWNLOAD_DIR, USENET_RETENTION, NZB_BLACKHOLEDIR, \
            ALTERNATE_DIR, GR_API, GB_API, BOOK_API, MAGICK, \
            NZBGET_HOST, NZBGET_USER, NZBGET_PASS, NZBGET_CATEGORY, NZBGET_PRIORITY, \
            NZBGET_PORT, NZB_DOWNLOADER_NZBGET, NZBMATRIX, NZBMATRIX_USER, NZBMATRIX_API, \
            NEWZBIN, NEWZBIN_UID, NEWZBIN_PASS, EBOOK_TYPE, MAG_TYPE, KAT, KAT_HOST, \
            NEWZNAB_PROV, TORZNAB_PROV, RSS_PROV, REJECT_WORDS, REJECT_MAXSIZE, \
            VERSIONCHECK_INTERVAL, SEARCH_INTERVAL, SCAN_INTERVAL, SEARCHRSS_INTERVAL, \
            EBOOK_DEST_FOLDER, EBOOK_DEST_FILE, MAG_RELATIVE, MAG_DEST_FOLDER, MAG_DEST_FILE, \
            USE_TWITTER, TWITTER_NOTIFY_ONSNATCH, TWITTER_NOTIFY_ONDOWNLOAD, \
            TWITTER_USERNAME, TWITTER_PASSWORD, TWITTER_PREFIX, \
            USE_BOXCAR, BOXCAR_NOTIFY_ONSNATCH, BOXCAR_NOTIFY_ONDOWNLOAD, BOXCAR_TOKEN, \
            TORRENT_DIR, TOR_DOWNLOADER_BLACKHOLE, TOR_DOWNLOADER_UTORRENT, \
            TOR_DOWNLOADER_QBITTORRENT, NZB_DOWNLOADER_SABNZBD, NZB_DOWNLOADER_BLACKHOLE, \
            USE_PUSHBULLET, PUSHBULLET_NOTIFY_ONSNATCH, PUSHBULLET_NOTIFY_ONDOWNLOAD, \
            PUSHBULLET_TOKEN, PUSHBULLET_DEVICEID, \
            UTORRENT_HOST, UTORRENT_PORT, UTORRENT_USER, UTORRENT_PASS, UTORRENT_LABEL, \
            QBITTORRENT_HOST, QBITTORRENT_PORT, QBITTORRENT_USER, QBITTORRENT_PASS, QBITTORRENT_LABEL, \
            USE_PUSHOVER, PUSHOVER_ONSNATCH, PUSHOVER_KEYS, PUSHOVER_APITOKEN, \
            PUSHOVER_PRIORITY, PUSHOVER_ONDOWNLOAD, PUSHOVER_DEVICE, \
            USE_ANDROIDPN, ANDROIDPN_NOTIFY_ONSNATCH, ANDROIDPN_NOTIFY_ONDOWNLOAD, \
            ANDROIDPN_URL, ANDROIDPN_USERNAME, ANDROIDPN_BROADCAST, \
            TOR_DOWNLOADER_TRANSMISSION, TRANSMISSION_HOST, TRANSMISSION_PORT, TRANSMISSION_PASS, TRANSMISSION_USER, \
            TOR_DOWNLOADER_DELUGE, DELUGE_HOST, DELUGE_USER, DELUGE_PASS, DELUGE_PORT, DELUGE_LABEL, \
            FULL_SCAN, ADD_AUTHOR, NOTFOUND_STATUS, NEWBOOK_STATUS, \
            USE_NMA, NMA_APIKEY, NMA_PRIORITY, NMA_ONSNATCH, NMA_ONDOWNLOAD, \
            GIT_USER, GIT_REPO, GIT_BRANCH, INSTALL_TYPE, CURRENT_VERSION, COMMIT_LIST, \
            LATEST_VERSION, COMMITS_BEHIND, NUMBEROFSEEDERS, SCHED, CACHE_HIT, CACHE_MISS, \
            BOOKSTRAP_THEME, LOGFILES, LOGSIZE, HTTPS_ENABLED, HTTPS_CERT, HTTPS_KEY

        NEWZNAB_PROV = []
        TORZNAB_PROV = []
        RSS_PROV = []

        # we read the log details earlier for starting the logger process,
        # but read them again here so they get listed in the debug log
        LOGDIR = check_setting_str(CFG, 'General', 'logdir', '')
        LOGLIMIT = check_setting_int(CFG, 'General', 'loglimit', 500)
        LOGFILES = check_setting_int(CFG, 'General', 'logfiles', 10)
        LOGSIZE = check_setting_int(CFG, 'General', 'logsize', 204800)

        try:
            HTTP_PORT = check_setting_int(CFG, 'General', 'http_port', 5299)
        except:
            HTTP_PORT = 5299

        if HTTP_PORT < 21 or HTTP_PORT > 65535:
            HTTP_PORT = 5299

        MATCH_RATIO = check_setting_int(CFG, 'General', 'match_ratio', 80)
        HTTP_HOST = check_setting_str(CFG, 'General', 'http_host', '0.0.0.0')
        HTTP_USER = check_setting_str(CFG, 'General', 'http_user', '')
        HTTP_PASS = check_setting_str(CFG, 'General', 'http_pass', '')
        HTTP_PROXY = check_setting_bool(CFG, 'General', 'http_proxy', 0)
        HTTP_ROOT = check_setting_str(CFG, 'General', 'http_root', '')
        HTTP_LOOK = check_setting_str(CFG, 'General', 'http_look', 'default')
        HTTPS_ENABLED = check_setting_bool(CFG, 'General', 'https_enabled', 0)
        HTTPS_CERT = check_setting_str(CFG, 'General', 'https_cert', '')
        HTTPS_KEY = check_setting_str(CFG, 'General', 'https_key', '')
        BOOKSTRAP_THEME = check_setting_str(CFG, 'General', 'bookstrap_theme', 'slate')

        LAUNCH_BROWSER = check_setting_bool(CFG, 'General', 'launch_browser', 1)
        API_ENABLED = check_setting_bool(CFG, 'General', 'api_enabled', 0)
        API_KEY = check_setting_str(CFG, 'General', 'api_key', '')

        PROXY_HOST = check_setting_str(CFG, 'General', 'proxy_host', '')
        PROXY_TYPE = check_setting_str(CFG, 'General', 'proxy_type', '')

        IMP_PREFLANG = check_setting_str(CFG, 'General', 'imp_preflang', 'en, eng, en-US, en-GB')
        IMP_MONTHLANG = check_setting_str(CFG, 'General', 'imp_monthlang', '')
        IMP_AUTOADD = check_setting_str(CFG, 'General', 'imp_autoadd', '')
        IMP_ONLYISBN = check_setting_bool(CFG, 'General', 'imp_onlyisbn', 0)
        IMP_SINGLEBOOK = check_setting_bool(CFG, 'General', 'imp_singlebook', 0)
        IMP_CONVERT = check_setting_str(CFG, 'General', 'imp_convert', '')
        GIT_PROGRAM = check_setting_str(CFG, 'General', 'git_program','')
        CACHE_AGE = check_setting_int(CFG, 'General', 'cache_age', 30)

        GIT_USER = check_setting_str(CFG, 'Git', 'git_user', 'dobytang')
        GIT_REPO = check_setting_str(CFG, 'Git', 'git_repo', 'lazylibrarian')
        GIT_BRANCH = check_setting_str(CFG, 'Git', 'git_branch', 'master')
        INSTALL_TYPE = check_setting_str(CFG, 'Git', 'install_type', '')
        CURRENT_VERSION = check_setting_str(CFG, 'Git', 'current_version', '')
        LATEST_VERSION = check_setting_str(CFG, 'Git', 'latest_version', '')
        COMMITS_BEHIND = check_setting_str(CFG, 'Git', 'commits_behind', '')

        SAB_HOST = check_setting_str(CFG, 'SABnzbd', 'sab_host', '')
        SAB_PORT = check_setting_int(CFG, 'SABnzbd', 'sab_port', 0)
        SAB_SUBDIR = check_setting_str(CFG, 'SABnzbd', 'sab_subdir', '')
        SAB_USER = check_setting_str(CFG, 'SABnzbd', 'sab_user', '')
        SAB_PASS = check_setting_str(CFG, 'SABnzbd', 'sab_pass', '')
        SAB_API = check_setting_str(CFG, 'SABnzbd', 'sab_api', '')
        SAB_CAT = check_setting_str(CFG, 'SABnzbd', 'sab_cat', '')

        # legacy name conversion, separate out nzbget host/port
        if not CFG.has_option('NZBGet', 'nzbget_port'):
            port = 0
            host = check_setting_str(CFG, 'NZBGet', 'nzbget_host', '')
            if host.startswith('http'):
                hostpart = 2
            else:
                hostpart = 1
            words = host.split(':')
            if len(words) > hostpart:
                host = ':'.join(words[:hostpart])
                port = ':'.join(words[hostpart:])
            CFG.set('NZBGet', 'nzbget_port', port)
            CFG.set('NZBGet', 'nzbget_host', host)

        NZBGET_HOST = check_setting_str(CFG, 'NZBGet', 'nzbget_host', '')
        NZBGET_PORT = check_setting_int(CFG, 'NZBGet', 'nzbget_port', '0')
        NZBGET_USER = check_setting_str(CFG, 'NZBGet', 'nzbget_user', '')
        NZBGET_PASS = check_setting_str(CFG, 'NZBGet', 'nzbget_pass', '')
        NZBGET_CATEGORY = check_setting_str(CFG, 'NZBGet', 'nzbget_cat', '')
        NZBGET_PRIORITY = check_setting_int(CFG, 'NZBGet', 'nzbget_priority', '0')

        DESTINATION_COPY = check_setting_bool(CFG, 'General', 'destination_copy', 0)
        DESTINATION_DIR = check_setting_str(CFG, 'General', 'destination_dir', '')
        ALTERNATE_DIR = check_setting_str(CFG, 'General', 'alternate_dir', '')
        DOWNLOAD_DIR = check_setting_str(CFG, 'General', 'download_dir', '')
        if not DOWNLOAD_DIR:
            logger.warn("Download dir not found, books will be downloaded to %s" % os.getcwd())
        elif not os.path.isdir(DOWNLOAD_DIR):
            logger.warn("Download dir [%s] not found, books will be downloaded to %s" % (repr(DOWNLOAD_DIR), os.getcwd()))
        elif not os.access(DOWNLOAD_DIR, os.W_OK | os.X_OK):
            logger.warn("Download dir [%s] not writeable, books will be downloaded to %s" % (repr(DOWNLOAD_DIR), os.getcwd()))

        NZB_DOWNLOADER_SABNZBD = check_setting_bool(CFG, 'USENET', 'nzb_downloader_sabnzbd', 0)
        NZB_DOWNLOADER_NZBGET = check_setting_bool(CFG, 'USENET', 'nzb_downloader_nzbget', 0)
        NZB_DOWNLOADER_BLACKHOLE = check_setting_bool(CFG, 'USENET', 'nzb_downloader_blackhole', 0)
        NZB_BLACKHOLEDIR = check_setting_str(CFG, 'USENET', 'nzb_blackholedir', '')
        USENET_RETENTION = check_setting_int(CFG, 'USENET', 'usenet_retention', 0)

        NZBMATRIX = check_setting_bool(CFG, 'NZBMatrix', 'nzbmatrix', 0)
        NZBMATRIX_USER = check_setting_str(CFG, 'NZBMatrix', 'nzbmatrix_user', '')
        NZBMATRIX_API = check_setting_str(CFG, 'NZBMatrix', 'nzbmatrix_api', '')

        count = 0
        while CFG.has_section('Newznab%i' % count):
            newz_name = 'Newznab%i' % count
            # legacy name conversions
            if CFG.has_option(newz_name, 'newznab%i' % count):
                CFG.set(newz_name, 'ENABLED', CFG.getboolean(newz_name, 'newznab%i' % count))
                CFG.remove_option(newz_name, 'newznab%i' % count)
            if CFG.has_option(newz_name, 'newznab_host%i' % count):
                CFG.set(newz_name, 'HOST', CFG.get(newz_name, 'newznab_host%i' % count))
                CFG.remove_option(newz_name, 'newznab_host%i' % count)
            if CFG.has_option(newz_name, 'newznab_api%i' % count):
                CFG.set(newz_name, 'API', CFG.get(newz_name, 'newznab_api%i' % count))
                CFG.remove_option(newz_name, 'newznab_api%i' % count)
            if CFG.has_option(newz_name, 'nzedb'):
                CFG.remove_option(newz_name, 'nzedb')

            NEWZNAB_PROV.append({"NAME": newz_name,
                                 "ENABLED": check_setting_bool(CFG, newz_name, 'enabled', 0),
                                 "HOST": check_setting_str(CFG, newz_name, 'host', ''),
                                 "API": check_setting_str(CFG, newz_name, 'api', ''),
                                 "GENERALSEARCH": check_setting_str(CFG, newz_name, 'generalsearch', 'search'),
                                 "BOOKSEARCH": check_setting_str(CFG, newz_name, 'booksearch', 'book'),
                                 "MAGSEARCH": check_setting_str(CFG, newz_name, 'magsearch', ''),
                                 "BOOKCAT": check_setting_str(CFG, newz_name, 'bookcat', '7000,7020'),
                                 "MAGCAT": check_setting_str(CFG, newz_name, 'magcat', '7010'),
                                 "EXTENDED": check_setting_str(CFG, newz_name, 'extended', '1'),
                                 "UPDATED": check_setting_str(CFG, newz_name, 'updated', ''),
                                 "MANUAL": check_setting_bool(CFG, newz_name, 'manual', 0)
                                 })
            count = count + 1
        # if the last slot is full, add an empty one on the end
        add_newz_slot()

        count = 0
        while CFG.has_section('Torznab%i' % count):
            torz_name = 'Torznab%i' % count
            # legacy name conversions
            if CFG.has_option(torz_name, 'torznab%i' % count):
                CFG.set(torz_name, 'ENABLED', CFG.getboolean(torz_name, 'torznab%i' % count))
                CFG.remove_option(torz_name, 'torznab%i' % count)
            if CFG.has_option(torz_name, 'torznab_host%i' % count):
                CFG.set(torz_name, 'HOST', CFG.get(torz_name, 'torznab_host%i' % count))
                CFG.remove_option(torz_name, 'torznab_host%i' % count)
            if CFG.has_option(torz_name, 'torznab_api%i' % count):
                CFG.set(torz_name, 'API', CFG.get(torz_name, 'torznab_api%i' % count))
                CFG.remove_option(torz_name, 'torznab_api%i' % count)
            if CFG.has_option(torz_name, 'nzedb'):
                CFG.remove_option(torz_name, 'nzedb')

            TORZNAB_PROV.append({"NAME": torz_name,
                                 "ENABLED": check_setting_bool(CFG, torz_name, 'enabled', 0),
                                 "HOST": check_setting_str(CFG, torz_name, 'host', ''),
                                 "API": check_setting_str(CFG, torz_name, 'api', ''),
                                 "GENERALSEARCH": check_setting_str(CFG, torz_name, 'generalsearch', 'search'),
                                 "BOOKSEARCH": check_setting_str(CFG, torz_name, 'booksearch', 'book'),
                                 "MAGSEARCH": check_setting_str(CFG, torz_name, 'magsearch', ''),
                                 "BOOKCAT": check_setting_str(CFG, torz_name, 'bookcat', '8000,8010'),
                                 "MAGCAT": check_setting_str(CFG, torz_name, 'magcat', '8030'),
                                 "EXTENDED": check_setting_str(CFG, torz_name, 'extended', '1'),
                                 "UPDATED": check_setting_str(CFG, torz_name, 'updated', ''),
                                 "MANUAL": check_setting_bool(CFG, torz_name, 'manual', 0)
                                 })
            count = count + 1
        # if the last slot is full, add an empty one on the end
        add_torz_slot()

        count = 0
        while CFG.has_section('RSS_%i' % count):
            rss_name = 'RSS_%i' % count
            # legacy name conversions
            if CFG.has_option(rss_name, 'rss%i' % count):
                CFG.set(rss_name, 'ENABLED', CFG.getboolean(rss_name, 'rss%i' % count))
                CFG.remove_option(rss_name, 'rss%i' % count)
            if CFG.has_option(rss_name, 'rss_host%i' % count):
                CFG.set(rss_name, 'HOST', CFG.get(rss_name, 'rss_host%i' % count))
                CFG.remove_option(rss_name, 'rss_host%i' % count)
            if CFG.has_option(rss_name, 'rss_user%i' % count):
                CFG.set(rss_name, 'USER', CFG.get(rss_name, 'rss_user%i' % count))
                CFG.remove_option(rss_name, 'rss_user%i' % count)
            if CFG.has_option(rss_name, 'rss_pass%i' % count):
                CFG.set(rss_name, 'PASS', CFG.get(rss_name, 'rss_pass%i' % count))
                CFG.remove_option(rss_name, 'rss_pass%i' % count)

            RSS_PROV.append({"NAME": rss_name,
                             "ENABLED": check_setting_bool(CFG, rss_name, 'ENABLED', 0),
                             "HOST": check_setting_str(CFG, rss_name, 'HOST', ''),
                             "USER": check_setting_str(CFG, rss_name, 'USER', ''),
                             "PASS": check_setting_str(CFG, rss_name, 'PASS', '')
                             })
            count = count + 1
        # if the last slot is full, add an empty one on the end
        add_rss_slot()

        TOR_DOWNLOADER_BLACKHOLE = check_setting_bool(CFG, 'TORRENT', 'tor_downloader_blackhole', 0)
        TOR_DOWNLOADER_UTORRENT = check_setting_bool(CFG, 'TORRENT', 'tor_downloader_utorrent', 0)
        TOR_DOWNLOADER_QBITTORRENT = check_setting_bool(CFG, 'TORRENT', 'tor_downloader_qbittorrent', 0)
        TOR_DOWNLOADER_TRANSMISSION = check_setting_bool(CFG, 'TORRENT', 'tor_downloader_transmission', 0)
        TOR_DOWNLOADER_DELUGE = check_setting_bool(CFG, 'TORRENT', 'tor_downloader_deluge', 0)
        NUMBEROFSEEDERS = check_setting_int(CFG, 'TORRENT', 'numberofseeders', 10)
        TORRENT_DIR = check_setting_str(CFG, 'TORRENT', 'torrent_dir', '')

        # legacy name conversion, separate out utorrent host/port
        if not CFG.has_option('UTORRENT', 'utorrent_port'):
            port = 0
            host = check_setting_str(CFG, 'UTORRENT', 'utorrent_host', '')
            if host.startswith('http'):
                hostpart = 2
            else:
                hostpart = 1
            words = host.split(':')
            if len(words) > hostpart:
                host = ':'.join(words[:hostpart])
                port = ':'.join(words[hostpart:])
            CFG.set('UTORRENT', 'utorrent_port', port)
            CFG.set('UTORRENT', 'utorrent_host', host)

        UTORRENT_HOST = check_setting_str(CFG, 'UTORRENT', 'utorrent_host', '')
        UTORRENT_PORT = check_setting_int(CFG, 'UTORRENT', 'utorrent_port', 0)
        UTORRENT_USER = check_setting_str(CFG, 'UTORRENT', 'utorrent_user', '')
        UTORRENT_PASS = check_setting_str(CFG, 'UTORRENT', 'utorrent_pass', '')
        UTORRENT_LABEL = check_setting_str(CFG, 'UTORRENT', 'utorrent_label', '')

        # legacy name conversion, separate out qbittorrent host/port
        if not CFG.has_option('QBITTORRENT', 'qbittorrent_port'):
            port = 0
            host = check_setting_str(CFG, 'QBITTORRENT', 'qbittorrent_host', '')
            if host.startswith('http'):
                hostpart = 2
            else:
                hostpart = 1
            words = host.split(':')
            if len(words) > hostpart:
                host = ':'.join(words[:hostpart])
                port = ':'.join(words[hostpart:])
            CFG.set('QBITTORRENT', 'qbittorrent_port', port)
            CFG.set('QBITTORRENT', 'qbittorrent_host', host)

        QBITTORRENT_HOST = check_setting_str(CFG, 'QBITTORRENT', 'qbittorrent_host', '')
        QBITTORRENT_PORT = check_setting_int(CFG, 'QBITTORRENT', 'qbittorrent_port', 0)
        QBITTORRENT_USER = check_setting_str(CFG, 'QBITTORRENT', 'qbittorrent_user', '')
        QBITTORRENT_PASS = check_setting_str(CFG, 'QBITTORRENT', 'qbittorrent_pass', '')
        QBITTORRENT_LABEL = check_setting_str(CFG, 'QBITTORRENT', 'qbittorrent_label', '')

        # legacy name conversion, separate out transmission host/port
        if not CFG.has_option('TRANSMISSION', 'transmission_port'):
            port = 0
            host = check_setting_str(CFG, 'TRANSMISSION', 'transmission_host', '')
            if host.startswith('http'):
                hostpart = 2
            else:
                hostpart = 1
            words = host.split(':')
            if len(words) > hostpart:
                host = ':'.join(words[:hostpart])
                port = ':'.join(words[hostpart:])
            CFG.set('TRANSMISSION', 'transmission_port', port)
            CFG.set('TRANSMISSION', 'transmission_host', host)

        TRANSMISSION_HOST = check_setting_str(CFG, 'TRANSMISSION', 'transmission_host', '')
        TRANSMISSION_PORT = check_setting_int(CFG, 'TRANSMISSION', 'transmission_port', 0)
        TRANSMISSION_USER = check_setting_str(CFG, 'TRANSMISSION', 'transmission_user', '')
        TRANSMISSION_PASS = check_setting_str(CFG, 'TRANSMISSION', 'transmission_pass', '')

        DELUGE_HOST = check_setting_str(CFG, 'DELUGE', 'deluge_host', '')
        DELUGE_PORT = check_setting_int(CFG, 'DELUGE', 'deluge_port', 0)
        DELUGE_USER = check_setting_str(CFG, 'DELUGE', 'deluge_user', '')
        DELUGE_PASS = check_setting_str(CFG, 'DELUGE', 'deluge_pass', '')
        DELUGE_LABEL = check_setting_str(CFG, 'DELUGE', 'deluge_label', '')

        KAT = check_setting_bool(CFG, 'KAT', 'kat', 0)
        KAT_HOST = check_setting_str(CFG, 'KAT', 'kat_host', 'kat.cr')

        NEWZBIN = check_setting_bool(CFG, 'Newzbin', 'newzbin', 0)
        NEWZBIN_UID = check_setting_str(CFG, 'Newzbin', 'newzbin_uid', '')
        NEWZBIN_PASS = check_setting_str(CFG, 'Newzbin', 'newzbin_pass', '')
        EBOOK_TYPE = check_setting_str(CFG, 'General', 'ebook_type', 'epub, mobi, pdf')
        EBOOK_TYPE = EBOOK_TYPE.lower()  # to make extension matching easier
        MAG_TYPE = check_setting_str(CFG, 'General', 'mag_type', 'pdf')
        MAG_TYPE = MAG_TYPE.lower()  # to make extension matching easier
        REJECT_WORDS = check_setting_str(CFG, 'General', 'reject_words', 'audiobook, mp3')
        REJECT_WORDS = REJECT_WORDS.lower()
        REJECT_MAXSIZE = check_setting_int(CFG, 'General', 'reject_maxsize', 0)

        SEARCH_INTERVAL = check_setting_int(CFG, 'SearchScan', 'search_interval', '360')
        SCAN_INTERVAL = check_setting_int(CFG, 'SearchScan', 'scan_interval', '10')
        SEARCHRSS_INTERVAL = check_setting_int(CFG, 'SearchScan', 'searchrss_interval', '20')
        VERSIONCHECK_INTERVAL = check_setting_int(CFG, 'SearchScan', 'versioncheck_interval', '24')

        FULL_SCAN = check_setting_bool(CFG, 'LibraryScan', 'full_scan', 0)
        ADD_AUTHOR = check_setting_bool(CFG, 'LibraryScan', 'add_author', 1)
        NOTFOUND_STATUS = check_setting_str(CFG, 'LibraryScan', 'notfound_status', 'Skipped')
        NEWBOOK_STATUS = check_setting_str(CFG, 'LibraryScan', 'newbook_status', 'Skipped')

        EBOOK_DEST_FOLDER = check_setting_str(CFG, 'PostProcess', 'ebook_dest_folder', '$Author/$Title')
        EBOOK_DEST_FILE = check_setting_str(CFG, 'PostProcess', 'ebook_dest_file', '$Title - $Author')
        MAG_DEST_FOLDER = check_setting_str(CFG, 'PostProcess', 'mag_dest_folder', '_Magazines/$Title/$IssueDate')
        MAG_DEST_FILE = check_setting_str(CFG, 'PostProcess', 'mag_dest_file', '$IssueDate - $Title')
        MAG_RELATIVE = check_setting_bool(CFG, 'PostProcess', 'mag_relative', 1)

        USE_TWITTER = check_setting_bool(CFG, 'Twitter', 'use_twitter', 0)
        TWITTER_NOTIFY_ONSNATCH = check_setting_bool(CFG, 'Twitter', 'twitter_notify_onsnatch', 0)
        TWITTER_NOTIFY_ONDOWNLOAD = check_setting_bool(CFG, 'Twitter', 'twitter_notify_ondownload', 0)
        TWITTER_USERNAME = check_setting_str(CFG, 'Twitter', 'twitter_username', '')
        TWITTER_PASSWORD = check_setting_str(CFG, 'Twitter', 'twitter_password', '')
        TWITTER_PREFIX = check_setting_str(CFG, 'Twitter', 'twitter_prefix', 'LazyLibrarian')

        USE_BOXCAR = check_setting_bool(CFG, 'Boxcar', 'use_boxcar', 0)
        BOXCAR_NOTIFY_ONSNATCH = check_setting_bool(CFG, 'Boxcar', 'boxcar_notify_onsnatch', 0)
        BOXCAR_NOTIFY_ONDOWNLOAD = check_setting_bool(CFG, 'Boxcar', 'boxcar_notify_ondownload', 0)
        BOXCAR_TOKEN = check_setting_str(CFG, 'Boxcar', 'boxcar_token', '')

        USE_PUSHBULLET = check_setting_bool(CFG, 'Pushbullet', 'use_pushbullet', 0)
        PUSHBULLET_NOTIFY_ONSNATCH = check_setting_bool(CFG, 'Pushbullet', 'pushbullet_notify_onsnatch', 0)
        PUSHBULLET_NOTIFY_ONDOWNLOAD = check_setting_bool(CFG, 'Pushbullet', 'pushbullet_notify_ondownload', 0)
        PUSHBULLET_TOKEN = check_setting_str(CFG, 'Pushbullet', 'pushbullet_token', '')
        PUSHBULLET_DEVICEID = check_setting_str(CFG, 'Pushbullet', 'pushbullet_deviceid', '')

        USE_PUSHOVER = check_setting_bool(CFG, 'Pushover', 'use_pushover', 0)
        PUSHOVER_ONSNATCH = check_setting_bool(CFG, 'Pushover', 'pushover_onsnatch', 0)
        PUSHOVER_ONDOWNLOAD = check_setting_bool(CFG, 'Pushover', 'pushover_ondownload', 0)
        PUSHOVER_KEYS = check_setting_str(CFG, 'Pushover', 'pushover_keys', '')
        PUSHOVER_APITOKEN = check_setting_str(CFG, 'Pushover', 'pushover_apitoken', '')
        PUSHOVER_PRIORITY = check_setting_int(CFG, 'Pushover', 'pushover_priority', 0)
        PUSHOVER_DEVICE = check_setting_str(CFG, 'Pushover', 'pushover_device', '')

        USE_ANDROIDPN = check_setting_bool(CFG, 'AndroidPN', 'use_androidpn', 0)
        ANDROIDPN_NOTIFY_ONSNATCH = check_setting_bool(CFG, 'AndroidPN', 'androidpn_notify_onsnatch', 0)
        ANDROIDPN_NOTIFY_ONDOWNLOAD = check_setting_bool(CFG, 'AndroidPN', 'androidpn_notify_ondownload', 0)
        ANDROIDPN_URL = check_setting_str(CFG, 'AndroidPN', 'androidpn_url', '')
        ANDROIDPN_USERNAME = check_setting_str(CFG, 'AndroidPN', 'androidpn_username', '')
        ANDROIDPN_BROADCAST = check_setting_bool(CFG, 'AndroidPN', 'androidpn_broadcast', 0)

        USE_NMA = check_setting_bool(CFG, 'NMA', 'use_nma', 0)
        NMA_APIKEY = check_setting_str(CFG, 'NMA', 'nma_apikey', '')
        NMA_PRIORITY = check_setting_int(CFG, 'NMA', 'nma_priority', 0)
        NMA_ONSNATCH = check_setting_bool(CFG, 'NMA', 'nma_onsnatch', 0)
        NMA_ONDOWNLOAD = check_setting_bool(CFG, 'NMA', 'nma_ondownload', 0)

        BOOK_API = check_setting_str(CFG, 'API', 'book_api', 'GoodReads')
        GR_API = check_setting_str(CFG, 'API', 'gr_api', 'ckvsiSDsuqh7omh74ZZ6Q')
        GB_API = check_setting_str(CFG, 'API', 'gb_api', '')

        if reloaded:
            logger.info('Config file reloaded')
        else:
            logger.info('Config file loaded')


def config_write():
    check_section('General')
    CFG.set('General', 'http_port', HTTP_PORT)
    CFG.set('General', 'http_host', HTTP_HOST)
    CFG.set('General', 'http_user', HTTP_USER)
    CFG.set('General', 'http_pass', HTTP_PASS)
    CFG.set('General', 'http_proxy', HTTP_PROXY)
    CFG.set('General', 'http_root', HTTP_ROOT)
    CFG.set('General', 'http_look', HTTP_LOOK)
    CFG.set('General', 'https_enabled', HTTPS_ENABLED)
    CFG.set('General', 'https_cert', HTTPS_CERT)
    CFG.set('General', 'https_key', HTTPS_KEY)
    CFG.set('General', 'bookstrap_theme', BOOKSTRAP_THEME)
    CFG.set('General', 'launch_browser', LAUNCH_BROWSER)
    CFG.set('General', 'api_enabled', API_ENABLED)
    CFG.set('General', 'api_key', API_KEY)
    CFG.set('General', 'proxy_host', PROXY_HOST)
    CFG.set('General', 'proxy_type', PROXY_TYPE)
    CFG.set('General', 'logdir', LOGDIR.encode('utf-8'))
    CFG.set('General', 'loglimit', LOGLIMIT)
    CFG.set('General', 'loglevel', LOGLEVEL)
    CFG.set('General', 'logsize', LOGSIZE)
    CFG.set('General', 'logfiles', LOGFILES)
    CFG.set('General', 'match_ratio', MATCH_RATIO)
    CFG.set('General', 'imp_onlyisbn', IMP_ONLYISBN)
    CFG.set('General', 'imp_singlebook', IMP_SINGLEBOOK)
    CFG.set('General', 'imp_preflang', IMP_PREFLANG)
    CFG.set('General', 'imp_monthlang', IMP_MONTHLANG)
    CFG.set('General', 'imp_autoadd', IMP_AUTOADD)
    CFG.set('General', 'imp_convert', IMP_CONVERT.strip())
    CFG.set('General', 'git_program', GIT_PROGRAM.strip())
    CFG.set('General', 'ebook_type', EBOOK_TYPE.lower())
    CFG.set('General', 'mag_type', MAG_TYPE.lower())
    CFG.set('General', 'reject_words', REJECT_WORDS.encode('utf-8').lower())
    CFG.set('General', 'reject_maxsize', REJECT_MAXSIZE)
    CFG.set('General', 'destination_dir', DESTINATION_DIR.encode('utf-8'))
    CFG.set('General', 'alternate_dir', ALTERNATE_DIR.encode('utf-8'))
    CFG.set('General', 'destination_copy', DESTINATION_COPY)
    CFG.set('General', 'download_dir', DOWNLOAD_DIR.encode('utf-8'))
    CFG.set('General', 'cache_age', CACHE_AGE)
#
    check_section('Git')
    CFG.set('Git', 'git_user', GIT_USER)
    CFG.set('Git', 'git_repo', GIT_REPO)
    CFG.set('Git', 'git_branch', GIT_BRANCH)
    CFG.set('Git', 'install_type', INSTALL_TYPE)
    CFG.set('Git', 'current_version', CURRENT_VERSION)
    CFG.set('Git', 'latest_version', LATEST_VERSION)
    CFG.set('Git', 'commits_behind', COMMITS_BEHIND)
#
    check_section('USENET')
    CFG.set('USENET', 'nzb_downloader_sabnzbd', NZB_DOWNLOADER_SABNZBD)
    CFG.set('USENET', 'nzb_downloader_nzbget', NZB_DOWNLOADER_NZBGET)
    CFG.set('USENET', 'nzb_downloader_blackhole', NZB_DOWNLOADER_BLACKHOLE)
    CFG.set('USENET', 'nzb_blackholedir', NZB_BLACKHOLEDIR)
    CFG.set('USENET', 'usenet_retention', USENET_RETENTION)
#
    check_section('SABnzbd')
    CFG.set('SABnzbd', 'sab_host', SAB_HOST)
    CFG.set('SABnzbd', 'sab_port', SAB_PORT)
    CFG.set('SABnzbd', 'sab_subdir', SAB_SUBDIR)
    CFG.set('SABnzbd', 'sab_user', SAB_USER)
    CFG.set('SABnzbd', 'sab_pass', SAB_PASS)
    CFG.set('SABnzbd', 'sab_api', SAB_API)
    CFG.set('SABnzbd', 'sab_cat', SAB_CAT)
#
    check_section('NZBGet')
    CFG.set('NZBGet', 'nzbget_host', NZBGET_HOST)
    CFG.set('NZBGet', 'nzbget_port', NZBGET_PORT)
    CFG.set('NZBGet', 'nzbget_user', NZBGET_USER)
    CFG.set('NZBGet', 'nzbget_pass', NZBGET_PASS)
    CFG.set('NZBGet', 'nzbget_cat', NZBGET_CATEGORY)
    CFG.set('NZBGet', 'nzbget_priority', NZBGET_PRIORITY)
#
    check_section('API')
    CFG.set('API', 'book_api', BOOK_API)
    CFG.set('API', 'gr_api', GR_API)
    CFG.set('API', 'gb_api', GB_API)
#
    check_section('NZBMatrix')
    CFG.set('NZBMatrix', 'nzbmatrix', NZBMATRIX)
    CFG.set('NZBMatrix', 'nzbmatrix_user', NZBMATRIX_USER)
    CFG.set('NZBMatrix', 'nzbmatrix_api', NZBMATRIX_API)
#
    for provider in NEWZNAB_PROV:
        check_section(provider['NAME'])
        CFG.set(provider['NAME'], 'ENABLED', provider['ENABLED'])
        oldprovider = check_setting_str(CFG, provider['NAME'], 'HOST', '', log=False)
        CFG.set(provider['NAME'], 'HOST', provider['HOST'])
        CFG.set(provider['NAME'], 'API', provider['API'])
        CFG.set(provider['NAME'], 'GENERALSEARCH', provider['GENERALSEARCH'])
        CFG.set(provider['NAME'], 'BOOKSEARCH', provider['BOOKSEARCH'])
        CFG.set(provider['NAME'], 'MAGSEARCH', provider['MAGSEARCH'])
        CFG.set(provider['NAME'], 'BOOKCAT', provider['BOOKCAT'])
        CFG.set(provider['NAME'], 'MAGCAT', provider['MAGCAT'])
        CFG.set(provider['NAME'], 'EXTENDED', provider['EXTENDED'])
        if provider['HOST'] == oldprovider:
            CFG.set(provider['NAME'], 'UPDATED', provider['UPDATED'])
            CFG.set(provider['NAME'], 'MANUAL', provider['MANUAL'])
        else:
            logger.debug('Reset %s as provider changed' % provider['NAME'])
            CFG.set(provider['NAME'], 'UPDATED', '')
            CFG.set(provider['NAME'], 'MANUAL', False)
    add_newz_slot()
#
    for provider in TORZNAB_PROV:
        check_section(provider['NAME'])
        CFG.set(provider['NAME'], 'ENABLED', provider['ENABLED'])
        oldprovider = check_setting_str(CFG, provider['NAME'], 'HOST', '', log=False)
        CFG.set(provider['NAME'], 'HOST', provider['HOST'])
        CFG.set(provider['NAME'], 'API', provider['API'])
        CFG.set(provider['NAME'], 'GENERALSEARCH', provider['GENERALSEARCH'])
        CFG.set(provider['NAME'], 'BOOKSEARCH', provider['BOOKSEARCH'])
        CFG.set(provider['NAME'], 'MAGSEARCH', provider['MAGSEARCH'])
        CFG.set(provider['NAME'], 'BOOKCAT', provider['BOOKCAT'])
        CFG.set(provider['NAME'], 'MAGCAT', provider['MAGCAT'])
        CFG.set(provider['NAME'], 'EXTENDED', provider['EXTENDED'])
        if provider['HOST'] == oldprovider:
            CFG.set(provider['NAME'], 'UPDATED', provider['UPDATED'])
            CFG.set(provider['NAME'], 'MANUAL', provider['MANUAL'])
        else:
            logger.debug('Reset %s as provider changed' % provider['NAME'])
            CFG.set(provider['NAME'], 'UPDATED', '')
            CFG.set(provider['NAME'], 'MANUAL', False)

    add_torz_slot()
#
    for provider in RSS_PROV:
        check_section(provider['NAME'])
        CFG.set(provider['NAME'], 'ENABLED', provider['ENABLED'])
        CFG.set(provider['NAME'], 'HOST', provider['HOST'])
        CFG.set(provider['NAME'], 'USER', provider['USER'])
        CFG.set(provider['NAME'], 'PASS', provider['PASS'])
    add_rss_slot()
#
    check_section('Newzbin')
    CFG.set('Newzbin', 'newzbin', NEWZBIN)
    CFG.set('Newzbin', 'newzbin_uid', NEWZBIN_UID)
    CFG.set('Newzbin', 'newzbin_pass', NEWZBIN_PASS)
#
    check_section('TORRENT')
    CFG.set('TORRENT', 'tor_downloader_blackhole', TOR_DOWNLOADER_BLACKHOLE)
    CFG.set('TORRENT', 'tor_downloader_utorrent', TOR_DOWNLOADER_UTORRENT)
    CFG.set('TORRENT', 'tor_downloader_qbittorrent', TOR_DOWNLOADER_QBITTORRENT)
    CFG.set('TORRENT', 'tor_downloader_transmission', TOR_DOWNLOADER_TRANSMISSION)
    CFG.set('TORRENT', 'tor_downloader_deluge', TOR_DOWNLOADER_DELUGE)
    CFG.set('TORRENT', 'numberofseeders', NUMBEROFSEEDERS)
    CFG.set('TORRENT', 'torrent_dir', TORRENT_DIR)
#
    check_section('UTORRENT')
    CFG.set('UTORRENT', 'utorrent_host', UTORRENT_HOST)
    CFG.set('UTORRENT', 'utorrent_port', UTORRENT_PORT)
    CFG.set('UTORRENT', 'utorrent_user', UTORRENT_USER)
    CFG.set('UTORRENT', 'utorrent_pass', UTORRENT_PASS)
    CFG.set('UTORRENT', 'utorrent_label', UTORRENT_LABEL)
#
    check_section('QBITTORRENT')
    CFG.set('QBITTORRENT', 'qbittorrent_host', QBITTORRENT_HOST)
    CFG.set('QBITTORRENT', 'qbittorrent_port', QBITTORRENT_PORT)
    CFG.set('QBITTORRENT', 'qbittorrent_user', QBITTORRENT_USER)
    CFG.set('QBITTORRENT', 'qbittorrent_pass', QBITTORRENT_PASS)
    CFG.set('QBITTORRENT', 'qbittorrent_label', QBITTORRENT_LABEL)
#
    check_section('TRANSMISSION')
    CFG.set('TRANSMISSION', 'transmission_host', TRANSMISSION_HOST)
    CFG.set('TRANSMISSION', 'transmission_port', TRANSMISSION_PORT)
    CFG.set('TRANSMISSION', 'transmission_user', TRANSMISSION_USER)
    CFG.set('TRANSMISSION', 'transmission_pass', TRANSMISSION_PASS)
#
    check_section('DELUGE')
    CFG.set('DELUGE', 'deluge_host', DELUGE_HOST)
    CFG.set('DELUGE', 'deluge_port', DELUGE_PORT)
    CFG.set('DELUGE', 'deluge_user', DELUGE_USER)
    CFG.set('DELUGE', 'deluge_pass', DELUGE_PASS)
    CFG.set('DELUGE', 'deluge_label', DELUGE_LABEL)
#
    check_section('KAT')
    CFG.set('KAT', 'kat', KAT)
    CFG.set('KAT', 'kat_host', KAT_HOST)
#
    check_section('SearchScan')
    CFG.set('SearchScan', 'search_interval', SEARCH_INTERVAL)
    CFG.set('SearchScan', 'scan_interval', SCAN_INTERVAL)
    CFG.set('SearchScan', 'searchrss_interval', SEARCHRSS_INTERVAL)
    CFG.set('SearchScan', 'versioncheck_interval', VERSIONCHECK_INTERVAL)
#
    check_section('LibraryScan')
    CFG.set('LibraryScan', 'full_scan', FULL_SCAN)
    CFG.set('LibraryScan', 'add_author', ADD_AUTHOR)
    CFG.set('LibraryScan', 'notfound_status', NOTFOUND_STATUS)
    CFG.set('LibraryScan', 'newbook_status', NEWBOOK_STATUS)
#
    check_section('PostProcess')
    CFG.set('PostProcess', 'ebook_dest_folder', EBOOK_DEST_FOLDER.encode('utf-8'))
    CFG.set('PostProcess', 'ebook_dest_file', EBOOK_DEST_FILE.encode('utf-8'))
    CFG.set('PostProcess', 'mag_dest_folder', MAG_DEST_FOLDER.encode('utf-8'))
    CFG.set('PostProcess', 'mag_dest_file', MAG_DEST_FILE.encode('utf-8'))
    CFG.set('PostProcess', 'mag_relative', MAG_RELATIVE)
#
    check_section('Twitter')
    CFG.set('Twitter', 'use_twitter', USE_TWITTER)
    CFG.set('Twitter', 'twitter_notify_onsnatch', TWITTER_NOTIFY_ONSNATCH)
    CFG.set('Twitter', 'twitter_notify_ondownload', TWITTER_NOTIFY_ONDOWNLOAD)
    CFG.set('Twitter', 'twitter_username', TWITTER_USERNAME)
    CFG.set('Twitter', 'twitter_password', TWITTER_PASSWORD)
    CFG.set('Twitter', 'twitter_prefix', TWITTER_PREFIX)
#
    check_section('Boxcar')
    CFG.set('Boxcar', 'use_boxcar', USE_BOXCAR)
    CFG.set('Boxcar', 'boxcar_notify_onsnatch', BOXCAR_NOTIFY_ONSNATCH)
    CFG.set('Boxcar', 'boxcar_notify_ondownload', BOXCAR_NOTIFY_ONDOWNLOAD)
    CFG.set('Boxcar', 'boxcar_token', BOXCAR_TOKEN)
#
    check_section('Pushbullet')
    CFG.set('Pushbullet', 'use_pushbullet', USE_PUSHBULLET)
    CFG.set('Pushbullet', 'pushbullet_notify_onsnatch', PUSHBULLET_NOTIFY_ONSNATCH)
    CFG.set('Pushbullet', 'pushbullet_notify_ondownload', PUSHBULLET_NOTIFY_ONDOWNLOAD)
    CFG.set('Pushbullet', 'pushbullet_token', PUSHBULLET_TOKEN)
    CFG.set('Pushbullet', 'pushbullet_deviceid', PUSHBULLET_DEVICEID)
#
    check_section('Pushover')
    CFG.set('Pushover', 'use_pushover', USE_PUSHOVER)
    CFG.set('Pushover', 'pushover_onsnatch', PUSHOVER_ONSNATCH)
    CFG.set('Pushover', 'pushover_ondownload', PUSHOVER_ONDOWNLOAD)
    CFG.set('Pushover', 'pushover_priority', PUSHOVER_PRIORITY)
    CFG.set('Pushover', 'pushover_keys', PUSHOVER_KEYS)
    CFG.set('Pushover', 'pushover_apitoken', PUSHOVER_APITOKEN)
    CFG.set('Pushover', 'pushover_device', PUSHOVER_DEVICE)
#
    check_section('AndroidPN')
    CFG.set('AndroidPN', 'use_androidpn', USE_ANDROIDPN)
    CFG.set('AndroidPN', 'androidpn_notify_onsnatch', ANDROIDPN_NOTIFY_ONSNATCH)
    CFG.set('AndroidPN', 'androidpn_notify_ondownload', ANDROIDPN_NOTIFY_ONDOWNLOAD)
    CFG.set('AndroidPN', 'androidpn_url', ANDROIDPN_URL)
    CFG.set('AndroidPN', 'androidpn_username', ANDROIDPN_USERNAME)
    CFG.set('AndroidPN', 'androidpn_broadcast', ANDROIDPN_BROADCAST)
#
    check_section('NMA')
    CFG.set('NMA', 'use_nma', USE_NMA)
    CFG.set('NMA', 'nma_apikey', NMA_APIKEY)
    CFG.set('NMA', 'nma_priority', NMA_PRIORITY)
    CFG.set('NMA', 'nma_onsnatch', NMA_ONSNATCH)
    CFG.set('NMA', 'nma_ondownload', NMA_ONDOWNLOAD)

    with open(CONFIGFILE, 'wb') as configfile:
        CFG.write(configfile)


def add_newz_slot():
    count = len(NEWZNAB_PROV)
    if count == 0 or len(CFG.get('Newznab%i' % int(count - 1), 'HOST')):
        newz_name = 'Newznab%i' % count
        check_section(newz_name)
        CFG.set(newz_name, 'ENABLED', False)
        CFG.set(newz_name, 'HOST', '')
        CFG.set(newz_name, 'API', '')
        CFG.set(newz_name, 'GENERALSEARCH', 'search')
        CFG.set(newz_name, 'BOOKSEARCH', 'book')
        CFG.set(newz_name, 'MAGSEARCH', '')
        CFG.set(newz_name, 'BOOKCAT', '7000,7020')
        CFG.set(newz_name, 'MAGCAT', '7010')
        CFG.set(newz_name, 'EXTENDED', '1')
        CFG.set(newz_name, 'UPDATED', '')
        CFG.set(newz_name, 'MANUAL', False)

        NEWZNAB_PROV.append({"NAME": newz_name,
                             "ENABLED": 0,
                             "HOST": '',
                             "API": '',
                             "GENERALSEARCH": 'search',
                             "BOOKSEARCH": 'book',
                             "MAGSEARCH": '',
                             "BOOKCAT": '7000,7020',
                             "MAGCAT": '7010',
                             "EXTENDED": '1',
                             "UPDATED": '',
                             "MANUAL": 0
                             })

def add_torz_slot():
    count = len(TORZNAB_PROV)
    if count == 0 or len(CFG.get('Torznab%i' % int(count - 1), 'HOST')):
        torz_name = 'Torznab%i' % count
        check_section(torz_name)
        CFG.set(torz_name, 'ENABLED', False)
        CFG.set(torz_name, 'HOST', '')
        CFG.set(torz_name, 'API', '')
        CFG.set(torz_name, 'GENERALSEARCH', 'search')
        CFG.set(torz_name, 'BOOKSEARCH', 'book')
        CFG.set(torz_name, 'MAGSEARCH', '')
        CFG.set(torz_name, 'BOOKCAT', '7000,7020')
        CFG.set(torz_name, 'MAGCAT', '7010')
        CFG.set(torz_name, 'EXTENDED', '1')
        CFG.set(torz_name, 'UPDATED', '')
        CFG.set(torz_name, 'MANUAL', False)
        TORZNAB_PROV.append({"NAME": torz_name,
                             "ENABLED": 0,
                             "HOST": '',
                             "API": '',
                             "GENERALSEARCH": 'search',
                             "BOOKSEARCH": 'book',
                             "MAGSEARCH": '',
                             "BOOKCAT": '8000,8010',
                             "MAGCAT": '8030',
                             "EXTENDED": '1',
                             "UPDATED": '',
                             "MANUAL": 0
                             })

def USE_NZB():
    for provider in NEWZNAB_PROV:
        if bool(provider['ENABLED']):
            return True
    for provider in TORZNAB_PROV:
        if bool(provider['ENABLED']):
            return True
    return False


def add_rss_slot():
    count = len(RSS_PROV)
    if count == 0 or len(CFG.get('RSS_%i' % int(count - 1), 'HOST')):
        rss_name = 'RSS_%i' % count
        check_section(rss_name)
        CFG.set(rss_name, 'ENABLED', False)
        CFG.set(rss_name, 'HOST', '')
        CFG.set(rss_name, 'USER', '')
        CFG.set(rss_name, 'PASS', '')
        RSS_PROV.append({"NAME": rss_name,
                         "ENABLED": 0,
                         "HOST": '',
                         "USER": '',
                         "PASS": ''
                         })


def USE_RSS():
    for provider in RSS_PROV:
        if bool(provider['ENABLED']):
            return True
    return False


def USE_TOR():
    if bool(KAT):
        return True
    return False


def build_bookstrap_themes():
    themelist = []
    if not os.path.isdir(os.path.join(PROG_DIR, 'data/interfaces/bookstrap/')):
        return themelist  # return empty if bookstrap interface not installed

    URL = 'http://bootswatch.com/api/3.json'
    request = urllib2.Request(URL)

    if PROXY_HOST:
        request.set_proxy(PROXY_HOST, PROXY_TYPE)

    # bootswatch insists on having a user-agent
    request.add_header('User-Agent', common.USER_AGENT)

    try:
        resp = urllib2.urlopen(request, timeout=30)
    except (urllib2.HTTPError, urllib2.URLError, socket.timeout) as e:
        logger.debug("Error getting bookstrap themes : %s" % e)
        return themelist

    if str(resp.getcode()).startswith("2"):
        # (200 OK etc)
        try:
            results = json.JSONDecoder().decode(resp.read())
            for theme in results['themes']:
                themelist.append(theme['name'].lower())
        except:
            # error reading results
            logger.debug('JSON Error reading bookstrap themes')

    logger.debug("Bookstrap found %i themes" % len(themelist))
    return themelist


def build_monthtable():
    if len(formatter.getList(IMP_MONTHLANG)) == 0:  # any extra languages wanted?
        return
    try:
        current_locale = locale.setlocale(locale.LC_ALL, '')  # read current state.
        # getdefaultlocale() doesnt seem to work as expected on windows, returns 'None'
    except locale.Error as e:
        logger.debug("Error getting current locale : %s" % str(e))
        return

    lang = str(current_locale)
    if not lang.startswith('en_'):  # en_ is preloaded
        MONTHNAMES[0].append(lang)
        for f in range(1, 13):
            MONTHNAMES[f].append(common.remove_accents(calendar.month_name[f]).lower())
        MONTHNAMES[0].append(lang)
        for f in range(1, 13):
            MONTHNAMES[f].append(common.remove_accents(calendar.month_abbr[f]).lower().strip('.'))
            logger.info("Added month names for locale [%s], %s, %s ..." % (
                        lang, MONTHNAMES[1][len(MONTHNAMES[1]) - 2], MONTHNAMES[1][len(MONTHNAMES[1]) - 1]))

    for lang in formatter.getList(IMP_MONTHLANG):
        try:
            if len(lang) > 1:
                locale.setlocale(locale.LC_ALL, lang)
                MONTHNAMES[0].append(lang)
                for f in range(1, 13):
                    MONTHNAMES[f].append(common.remove_accents(calendar.month_name[f]).lower())
                MONTHNAMES[0].append(lang)
                for f in range(1, 13):
                    MONTHNAMES[f].append(common.remove_accents(calendar.month_abbr[f]).lower().strip('.'))
                locale.setlocale(locale.LC_ALL, current_locale)  # restore entry state
                logger.info("Added month names for locale [%s], %s, %s ..." % (
                    lang, MONTHNAMES[1][len(MONTHNAMES[1]) - 2], MONTHNAMES[1][len(MONTHNAMES[1]) - 1]))
        except:
            locale.setlocale(locale.LC_ALL, current_locale)  # restore entry state
            logger.warn("Unable to load requested locale [%s]" % lang)
            try:
                if '_' in lang:
                    wanted_lang = lang.split('_')[0]
                else:
                    wanted_lang = lang
                params = ['locale', '-a']
                all_locales = subprocess.check_output(params).split()
                locale_list = []
                for a_locale in all_locales:
                    if a_locale.startswith(wanted_lang):
                        locale_list.append(a_locale)
                if locale_list:
                    logger.warn("Found these alternatives: " + str(locale_list))
                else:
                    logger.warn("Unable to find an alternative")
            except:
                logger.warn("Unable to get a list of alternatives")
            logger.info("Set locale back to entry state %s" % current_locale)


def daemonize():
    """
    Fork off as a daemon
    """

    # Make a non-session-leader child process
    try:
        pid = os.fork()  # @UndefinedVariable - only available in UNIX
        if pid != 0:
            sys.exit(0)
    except OSError as e:
        raise RuntimeError("1st fork failed: %s [%d]" %
                           (e.strerror, e.errno))

    os.setsid()  # @UndefinedVariable - only available in UNIX

    # Make sure I can read my own files and shut out others
    prev = os.umask(0)
    os.umask(prev and int('077', 8))

    # Make the child a session-leader by detaching from the terminal
    try:
        pid = os.fork()  # @UndefinedVariable - only available in UNIX
        if pid != 0:
            sys.exit(0)
    except OSError as e:
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
    except Exception as e:
        logger.error('Could not launch browser: %s' % e)


def dbcheck():

    conn = sqlite3.connect(DBFILE)
    c = conn.cursor()

    c.execute('PRAGMA user_version')
    result = c.fetchone()
    db_version = result[0]
    
    # database version history:
    # 0 original version or new empty database
    # 1 changes up to June 2016
    # 2 removed " MB" from nzbsize field in wanted table
    # 3 removed SeriesOrder column from ooks table as redundant
    db_current_version = 3

    if db_version < db_current_version:
        logger.info('Updating database to version %s, current version is %s' % (db_current_version, db_version))
    
        if db_version < 1:
            c.execute('CREATE TABLE IF NOT EXISTS authors (AuthorID TEXT, AuthorName TEXT UNIQUE, AuthorImg TEXT, \
                 AuthorLink TEXT, DateAdded TEXT, Status TEXT, LastBook TEXT, LastLink Text, LastDate TEXT, \
                 HaveBooks INTEGER, TotalBooks INTEGER, AuthorBorn TEXT, AuthorDeath TEXT, UnignoredBooks INTEGER)')
            c.execute('CREATE TABLE IF NOT EXISTS books (AuthorID TEXT, AuthorName TEXT, AuthorLink TEXT, \
                BookName TEXT, BookSub TEXT, BookDesc TEXT, BookGenre TEXT, BookIsbn TEXT, BookPub TEXT, \
                BookRate INTEGER, BookImg TEXT, BookPages INTEGER, BookLink TEXT, BookID TEXT UNIQUE, BookFile TEXT, \
                BookDate TEXT, BookLang TEXT, BookAdded TEXT, Status TEXT, Series TEXT, SeriesNum TEXT, \
                WorkPage TEXT)')
            c.execute('CREATE TABLE IF NOT EXISTS wanted (BookID TEXT, NZBurl TEXT, NZBtitle TEXT, NZBdate TEXT, \
                NZBprov TEXT, Status TEXT, NZBsize TEXT, AuxInfo TEXT, NZBmode TEXT)')
            c.execute('CREATE TABLE IF NOT EXISTS pastissues AS SELECT * FROM wanted')  # same columns
            c.execute('CREATE TABLE IF NOT EXISTS magazines (Title TEXT, Frequency TEXT, Regex TEXT, Status TEXT, \
                MagazineAdded TEXT, LastAcquired TEXT, IssueDate TEXT, IssueStatus TEXT)')
            c.execute('CREATE TABLE IF NOT EXISTS languages (isbn TEXT, lang TEXT)')
            c.execute('CREATE TABLE IF NOT EXISTS issues (Title TEXT, IssueID TEXT, IssueAcquired TEXT, IssueDate TEXT, \
                IssueFile TEXT)')
            c.execute('CREATE TABLE IF NOT EXISTS stats (authorname text, GR_book_hits int, GR_lang_hits int, \
                LT_lang_hits int, GB_lang_change, cache_hits int, bad_lang int, bad_char int, uncached int)')
    
        # These are the incremental changes before database versioning was introduced. 
        # New database tables already have these incorporated so we need to check first...
            try:
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
                c.execute('SELECT BookFile from books')
            except sqlite3.OperationalError:
                logger.info('Updating database to hold book filename')
                c.execute('ALTER TABLE books ADD COLUMN BookFile TEXT')
    
            try:
                c.execute('SELECT AuxInfo from wanted')
            except sqlite3.OperationalError:
                logger.info('Updating database to hold AuxInfo')
                c.execute('ALTER TABLE wanted ADD COLUMN AuxInfo TEXT')
    
            try:
                c.execute('SELECT NZBsize from wanted')
            except sqlite3.OperationalError:
                logger.info('Updating database to hold NZBsize')
                c.execute('ALTER TABLE wanted ADD COLUMN NZBsize TEXT')
    
            try:
                c.execute('SELECT NZBmode from wanted')
            except sqlite3.OperationalError:
                logger.info('Updating database to hold NZBmode')
                c.execute('ALTER TABLE wanted ADD COLUMN NZBmode TEXT')
    
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
    
            addedWorkPage = False
            try:
                c.execute('SELECT WorkPage from books')
            except sqlite3.OperationalError:
                logger.info('Updating database to hold WorkPage')
                c.execute('ALTER TABLE books ADD COLUMN WorkPage TEXT')
                addedWorkPage = True
    
            addedSeries = False
            try:
                c.execute('SELECT Series from books')
            except sqlite3.OperationalError:
                logger.info('Updating database to hold Series')
                c.execute('ALTER TABLE books ADD COLUMN Series TEXT')
                addedSeries = True
        
            # SeriesOrder shouldn't be an integer, some later written books
            # and novellas logically go inbetween books of the main series,
            # and their SeriesOrder is not an integer, eg 1.5
            # so we need to update SeriesOrder to store as text.
            # Because sqlite can't drop columns we create a new column SeriesNum,
            # inherit the old column values, and use SeriesNum instead
            try:
                c.execute('SELECT SeriesNum from books')
            except sqlite3.OperationalError:
                # no SeriesNum column, so create one
                logger.info('Updating books to hold SeriesNum')
                c.execute('ALTER TABLE books ADD COLUMN SeriesNum TEXT')
                c.execute('UPDATE books SET SeriesNum = SeriesOrder')
                c.execute('UPDATE books SET SeriesOrder = Null')
        
            addedIssues = False
            try:
                c.execute('SELECT Title from issues')
            except sqlite3.OperationalError:
                logger.info('Updating database to hold Issues table')
                c.execute('CREATE TABLE issues (Title TEXT, IssueID TEXT, IssueAcquired TEXT, IssueDate TEXT, IssueFile TEXT)')
                addedIssues = True
            try:
                c.execute('SELECT IssueID from issues')
            except sqlite3.OperationalError:
                logger.info('Updating Issues table to hold IssueID')
                c.execute('ALTER TABLE issues ADD COLUMN IssueID TEXT')
                addedIssues = True
        
            c.execute('DROP TABLE if exists capabilities')
        
            conn.commit()
        
            if addedIssues:
                try:
                    magazinescan.magazineScan(thread='MAIN')
                except:
                    logger.debug("Failed to scan magazines")
        
            if addedWorkPage:
                try:
                    logger.info('Adding WorkPage to existing books')
                    threading.Thread(target=bookwork.setWorkPages, args=[]).start()
                except:
                    logger.debug("Failed to update WorkPages")
        
            myDB = database.DBConnection()
        
            if addedSeries:
                try:
                    books = myDB.select('SELECT BookID, BookName FROM books')
                    if books:
                        logger.info('Adding series to existing books')
                        for book in books:
                            series,seriesNum = formatter.bookSeries(book["BookName"])
                            if series:
                                controlValueDict = {"BookID": book["BookID"]}
                                newValueDict = {
                                    "series": series,
                                    "seriesNum": seriesNum
                                }
                                myDB.upsert("books", newValueDict, controlValueDict)
                except Exception as z:
                    logger.info('Error: ' + str(z))
        
        if db_version < 2:
            try:
                results = myDB.select('SELECT BookID,NZBsize FROM wanted WHERE NZBsize LIKE "% MB"')
                if results:
                    logger.info('Removing %s units from wanted table' % len(results))
                    for units in results:
                        nzbsize = units["NZBsize"]
                        nzbsize = nzbsize.split(' ')[0]
                        myDB.action('UPDATE wanted SET NZBsize = "%s" WHERE BookID = "%s"' % (nzbsize, units["BookID"]))
                        
            except Exception as z:
                logger.info('Error: ' + str(z))

        if db_version < 3:
            try:
                c.execute('SELECT SeriesOrder from books')
                logger.info('Removing SeriesOrder from books table')
                try:
                    c.execute('CREATE TABLE IF NOT EXISTS temp_books (AuthorID TEXT, AuthorName TEXT, AuthorLink TEXT, \
                        BookName TEXT, BookSub TEXT, BookDesc TEXT, BookGenre TEXT, BookIsbn TEXT, BookPub TEXT, \
                        BookRate INTEGER, BookImg TEXT, BookPages INTEGER, BookLink TEXT, BookID TEXT UNIQUE, BookFile TEXT, \
                        BookDate TEXT, BookLang TEXT, BookAdded TEXT, Status TEXT, Series TEXT, SeriesNum TEXT, \
                        WorkPage TEXT)')
                    c.execute('INSERT INTO temp_books SELECT AuthorID,AuthorName,AuthorLink,BookName,BookSub, \
                        BookDesc,BookGenre,BookIsbn,BookPub,BookRate,BookImg,BookPages,BookLink,BookID, \
                        BookFile,BookDate,BookLang,BookAdded,Status,Series,SeriesNum,WorkPage FROM books')
                    c.execute('DROP TABLE books')
                    c.execute('ALTER TABLE temp_books RENAME TO books')
                    conn.commit()
                except sqlite3.OperationalError:
                    logger.warn('Failed to remove SeriesOrder from books table')
            except sqlite3.OperationalError:
                # no SeriesOrder column, nothing to remove
                # (must be a new install, not an upgrade)
                logger.debug('No SeriesOrder in books table')
            
            try:
                c.execute('SELECT BookID from pastissues')
                logger.debug('pastissues table already exists')  
                # must be a new install,so nothing to move
            except sqlite3.OperationalError:
                logger.info('Moving magazine past issues into new table')
                c.execute('CREATE TABLE pastissues AS SELECT * FROM wanted WHERE Status="Skipped" AND length(AuxInfo) > 0')
                c.execute('DELETE FROM wanted WHERE Status="Skipped" AND length(AuxInfo) > 0')
    
        c.execute('PRAGMA user_version = %s' % db_current_version)       
        conn.commit()
        conn.close()
        logger.info('Database updated to version %s' % db_current_version)

# Now do any non-version-specific tidying

        myDB = database.DBConnection()
        try:
            authors = myDB.select('SELECT AuthorID FROM authors WHERE AuthorName IS NULL')
            if authors:
                logger.info('Removing un-named authors from database')
                for author in authors:
                    authorid = author["AuthorID"]
                    myDB.action('DELETE from authors WHERE AuthorID="%s"' % authorid)
                    myDB.action('DELETE from books WHERE AuthorID="%s"' % authorid)
        except Exception as z:
            logger.info('Error: ' + str(z))
        
        
def start():
    global __INITIALIZED__, started

    if __INITIALIZED__:

        # Crons and scheduled jobs started here
        SCHED.start()
        common.restartJobs(start='Start')
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
        except Exception as e:
            logger.warn('LazyLibrarian failed to update: %s. Restarting.' % e)

    if PIDFILE:
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
