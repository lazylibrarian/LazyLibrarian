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

import ConfigParser
from lib.apscheduler.scheduler import Scheduler

import threading

from lazylibrarian import logger, postprocess, searchnzb, searchtorrents, librarysync, versioncheck, database, searchmag, magazinescan, common

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
DBFILE = None
CONFIGFILE = None
CFG = None

LOGDIR = None
LOGLIST = []
# Info 1, Debug 2, >2 don't toggle console/file
LOGLEVEL = 2
LOGFULL = False # include debug on screen if true

MATCH_RATIO = 80

HTTP_HOST = None
HTTP_PORT = None
HTTP_USER = None
HTTP_PASS = None
HTTP_ROOT = None
HTTP_LOOK = None
LAUNCH_BROWSER = 0

PROXY_HOST = None
PROXY_TYPE = None

SAB_HOST = None
SAB_PORT = None
SAB_SUBDIR = None
SAB_USER = None
SAB_PASS = None
SAB_API = None
SAB_CAT = None

NZBGET_HOST = None
NZBGET_USER = None
NZBGET_PASS = None
NZBGET_CATEGORY = None
NZBGET_PRIORITY = None

DESTINATION_COPY = 0
DESTINATION_DIR = None
ALTERNATE_DIR = None
DOWNLOAD_DIR = None

IMP_PREFLANG = None
IMP_MONTHLANG = None
IMP_ONLYISBN = 0
IMP_SINGLEBOOK = 1
IMP_AUTOADD = None

BOOK_API = None
GR_API = None
GB_API = None

NZBMATRIX = 0
NZBMATRIX_USER = None
NZBMATRIX_API = None

NEWZNAB0 = 0
NEWZNAB_HOST0 = None
NEWZNAB_API0 = None

NEWZNAB1 = 0
NEWZNAB_HOST1 = None
NEWZNAB_API1 = None

NEWZNAB2 = 0
NEWZNAB_HOST2 = None
NEWZNAB_API2 = None

NEWZNAB3 = 0
NEWZNAB_HOST3 = None
NEWZNAB_API3 = None

NEWZNAB4 = 0
NEWZNAB_HOST4 = None
NEWZNAB_API4 = None

TORZNAB0 = 0
TORZNAB_HOST0 = None
TORZNAB_API0 = None

TORZNAB1 = 0
TORZNAB_HOST1 = None
TORZNAB_API1 = None

TORZNAB2 = 0
TORZNAB_HOST2 = None
TORZNAB_API2 = None

TORZNAB3 = 0
TORZNAB_HOST3 = None
TORZNAB_API3 = None

TORZNAB4 = 0
TORZNAB_HOST4 = None
TORZNAB_API4 = None

NEWZBIN = 0
NEWZBIN_UID = None
NEWZBIN_PASSWORD = None
EBOOK_TYPE = None

TOR_DOWNLOADER_BLACKHOLE = 0
TOR_DOWNLOADER_UTORRENT = 0
TOR_DOWNLOADER_TRANSMISSION = 0
TOR_DOWNLOADER_DELUGE = 0
NUMBEROFSEEDERS = 10
TORRENT_DIR = None

UTORRENT_HOST = None
UTORRENT_USER = None
UTORRENT_PASS = None
UTORRENT_LABEL = None

TRANSMISSION_HOST = None
TRANSMISSION_USER = None
TRANSMISSION_PASS = None

DELUGE_PORT = None
DELUGE_HOST = None
DELUGE_USER = None
DELUGE_PASS = None

KAT = 0
KAT_HOST = None

USE_NZB = 0
USE_TOR = 0

NZB_DOWNLOADER_SABNZBD = 0
NZB_DOWNLOADER_NZBGET = 0
NZB_DOWNLOADER_BLACKHOLE = 0
NZB_BLACKHOLEDIR = None
USENET_RETENTION = None

VERSIONCHECK_INTERVAL = 24  # Every 2 hours
SEARCH_INTERVAL = 720  # Every 12 hours
SCAN_INTERVAL = 10  # Every 10 minutes
FULL_SCAN = 0  # full scan would remove books from db
ADD_AUTHOR = 1  # auto add authors not found in db from goodreads
NOTFOUND_STATUS = 'Skipped'  # value to mark missing books (deleted/removed) in db, can be 'Open', 'Ignored',' 'Wanted','Skipped'
NEWBOOK_STATUS = 'Skipped'  # value to mark new books (when importing a new author) in db, can be 'Open', 'Ignored',' 'Wanted','Skipped'
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
PUSHOVER_PRIORITY = None

USE_ANDROIDPN = 0
ANDROIDPN_NOTIFY_ONSNATCH = 0
ANDROIDPN_NOTIFY_ONDOWNLOAD = 0
ANDROIDPN_URL = None
ANDROIDPN_BROADCAST = 1 
ANDROIDPN_USERNAME = None

USE_NMA = 0
NMA_APIKEY = None
NMA_PRIORITY = None
NMA_ONSNATCH = None
NMA_ONDOWNLOAD = None

# Month names table to hold long/short month names for multiple languages
# which we can match against magazine issues
# Defined as global and initialised early, because locale changes are not thread safe
# This means changes to languages require a restart
MONTH0 = []  # This holds the language code
MONTH1 = []  # multiple names for first month
MONTH2 = []  # etc...
MONTH3 = []
MONTH4 = []
MONTH5 = []
MONTH6 = []
MONTH7 = []
MONTH8 = []
MONTH9 = []
MONTH10 = []
MONTH11 = []
MONTH12 = []
MONTHNAMES = [MONTH0, MONTH1, MONTH2, MONTH3, MONTH4, MONTH5, MONTH6, MONTH7, MONTH8, MONTH9, MONTH10, MONTH11, MONTH12]
CACHE_HIT = 0
CACHE_MISS = 0
LAST_GOODREADS = 0
LAST_LIBRARYTHING = 0

def check_section(sec):
    """ Check if INI section exists, if not create it """
    if CFG.has_section(sec):
        return True
    else:
        CFG.add_section(sec)
        return False

def check_setting_boolean(config, cfg_name, item_name, def_val):
    """ Check if option exists and coerce to boolean, if not create it """
    try:
        my_val = config.getboolean(cfg_name, item_name)
    except:
        my_val = def_val
        check_section(cfg_name)
        config.set(cfg_name, item_name, my_val)
    logger.debug(item_name + " -> " + str(my_val))
    return my_val


def check_setting_int(config, cfg_name, item_name, def_val):
    try:
        my_val = config.getint(cfg_name, item_name)
    except:
        my_val = def_val
        check_section(cfg_name)
        config.set(cfg_name, item_name, my_val)
    logger.debug(item_name + " -> " + str(my_val))
    return my_val

def check_setting_str(config, cfg_name, item_name, def_val, log=True):
    try:
        my_val = config.get(cfg_name, item_name)
        if my_val.startswith('"'):
            my_val = my_val[1:]
        if my_val.endswith('"'):
            my_val = my_val[:-1]
    except:
        my_val = def_val
        check_section(cfg_name)
        config.set(cfg_name, item_name, my_val)
    if log:
        logger.debug(item_name + " -> " + my_val)
    else:
        logger.debug(item_name + " -> ******")

    return my_val


def initialize():

    with INIT_LOCK:

        global __INITIALIZED__, FULL_PATH, PROG_DIR, LOGLEVEL, LOGFULL, DAEMON, DATADIR, CONFIGFILE, CFG, LOGDIR, HTTP_HOST, HTTP_PORT, HTTP_USER, HTTP_PASS, HTTP_ROOT, \
            HTTP_LOOK, LAUNCH_BROWSER, LOGDIR, CACHEDIR, MATCH_RATIO, PROXY_HOST, PROXY_TYPE, IMP_ONLYISBN, IMP_SINGLEBOOK, IMP_PREFLANG, IMP_MONTHLANG, IMP_AUTOADD, \
            MONTHNAMES, MONTH0, MONTH1, MONTH2, MONTH3, MONTH4, MONTH5, MONTH6, MONTH7, MONTH8, MONTH9, MONTH10, MONTH11, MONTH12, \
            SAB_HOST, SAB_PORT, SAB_SUBDIR, SAB_API, SAB_USER, SAB_PASS, DESTINATION_DIR, DESTINATION_COPY, DOWNLOAD_DIR, SAB_CAT, USENET_RETENTION, NZB_BLACKHOLEDIR, \
            ALTERNATE_DIR, GR_API, GB_API, BOOK_API, NZBGET_HOST, NZBGET_USER, NZBGET_PASS, NZBGET_CATEGORY, NZBGET_PRIORITY, NZB_DOWNLOADER_NZBGET, \
            NZBMATRIX, NZBMATRIX_USER, NZBMATRIX_API, NEWZBIN, NEWZBIN_UID, NEWZBIN_PASS, NEWZNAB0, NEWZNAB_HOST0, NEWZNAB_API0, \
            NEWZNAB1, NEWZNAB_HOST1, NEWZNAB_API1, NEWZNAB2, NEWZNAB_HOST2, NEWZNAB_API2, NEWZNAB3, NEWZNAB_HOST3, NEWZNAB_API3, NEWZNAB4, NEWZNAB_HOST4, NEWZNAB_API4, \
            TORZNAB0, TORZNAB_HOST0, TORZNAB_API0, TORZNAB1, TORZNAB_HOST1, TORZNAB_API1, TORZNAB2, TORZNAB_HOST2, TORZNAB_API2, \
            TORZNAB3, TORZNAB_HOST3, TORZNAB_API3, TORZNAB4, TORZNAB_HOST4, TORZNAB_API4, EBOOK_TYPE, KAT, KAT_HOST, \
            VERSIONCHECK_INTERVAL, SEARCH_INTERVAL, SCAN_INTERVAL, EBOOK_DEST_FOLDER, EBOOK_DEST_FILE, MAG_RELATIVE, MAG_DEST_FOLDER, MAG_DEST_FILE, \
            USE_TWITTER, TWITTER_NOTIFY_ONSNATCH, TWITTER_NOTIFY_ONDOWNLOAD, TWITTER_USERNAME, TWITTER_PASSWORD, TWITTER_PREFIX, \
            USE_BOXCAR, BOXCAR_NOTIFY_ONSNATCH, BOXCAR_NOTIFY_ONDOWNLOAD, BOXCAR_TOKEN, TORRENT_DIR, TOR_DOWNLOADER_BLACKHOLE, TOR_DOWNLOADER_UTORRENT, \
            USE_TOR, USE_NZB, NZB_DOWNLOADER_SABNZBD, NZB_DOWNLOADER_BLACKHOLE, USE_PUSHBULLET, \
            PUSHBULLET_NOTIFY_ONSNATCH, PUSHBULLET_NOTIFY_ONDOWNLOAD, PUSHBULLET_TOKEN, PUSHBULLET_DEVICEID, \
            UTORRENT_HOST, UTORRENT_USER, UTORRENT_PASS, UTORRENT_LABEL, \
            USE_PUSHOVER, PUSHOVER_ONSNATCH, PUSHOVER_KEYS, PUSHOVER_APITOKEN, PUSHOVER_PRIORITY, PUSHOVER_ONDOWNLOAD, PUSHOVER_DEVICE, \
            USE_ANDROIDPN, ANDROIDPN_NOTIFY_ONSNATCH, ANDROIDPN_NOTIFY_ONDOWNLOAD, ANDROIDPN_URL, ANDROIDPN_USERNAME, ANDROIDPN_BROADCAST, \
            TOR_DOWNLOADER_TRANSMISSION, TRANSMISSION_HOST, TRANSMISSION_PASS, TRANSMISSION_USER, \
            TOR_DOWNLOADER_DELUGE, DELUGE_HOST, DELUGE_USER, DELUGE_PASS, DELUGE_PORT, \
            FULL_SCAN, ADD_AUTHOR, NOTFOUND_STATUS, NEWBOOK_STATUS, USE_NMA, NMA_APIKEY, NMA_PRIORITY, NMA_ONSNATCH, NMA_ONDOWNLOAD, \
            GIT_USER, GIT_REPO, GIT_BRANCH, INSTALL_TYPE, CURRENT_VERSION, LATEST_VERSION, COMMITS_BEHIND, NUMBEROFSEEDERS, SCHED, \
            CACHE_HIT, CACHE_MISS, LAST_GOODREADS, LAST_LIBRARYTHING

        if __INITIALIZED__:
            return False

        check_section('General')
        
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
                    print '%s : Unable to create folder for logs. Only logging to console.' % LOGDIR

        # Start the logger, silence console logging if we need to
        CFGLOGLEVEL = check_setting_int(CFG, 'General', 'loglevel', 3)
        if CFGLOGLEVEL == 3:  # default value if none in config
            LOGLEVEL = 2  # If not set in Config, then lets set to DEBUG
        else:
            LOGLEVEL = CFGLOGLEVEL  # Config setting picked up

        logger.lazylibrarian_log.initLogger(loglevel=LOGLEVEL)
        logger.info("Log level set to [%s]- Log Directory is [%s] - Config level is [%s]" % (LOGLEVEL, LOGDIR, CFGLOGLEVEL))
        if LOGLEVEL > 2:
            LOGFULL = True
            logger.info("Screen Log is DEBUG")
        else:
            LOGFULL = False
            logger.info("Screen Log is INFO/WARN/ERROR")
        
        # keep track of last api calls so we don't call more than once per second
        # to respect api terms, but don't wait un-necessarily either
        time_now = int(time.time())
        LAST_LIBRARYTHING = time_now 
        LAST_GOODREADS = time_now

        MATCH_RATIO = check_setting_int(CFG, 'General', 'match_ratio', 80)
        HTTP_HOST = check_setting_str(CFG, 'General', 'http_host', '0.0.0.0')
        HTTP_USER = check_setting_str(CFG, 'General', 'http_user', '')
        HTTP_PASS = check_setting_str(CFG, 'General', 'http_pass', '')
        HTTP_ROOT = check_setting_str(CFG, 'General', 'http_root', '')
        HTTP_LOOK = check_setting_str(CFG, 'General', 'http_look', 'default')

        LAUNCH_BROWSER = check_setting_int(CFG, 'General', 'launch_browser', 1)

        PROXY_HOST = check_setting_str(CFG, 'General', 'proxy_host', '')
        PROXY_TYPE = check_setting_str(CFG, 'General', 'proxy_type', '')

        LOGDIR = check_setting_str(CFG, 'General', 'logdir', '')

        IMP_PREFLANG = check_setting_str(CFG, 'General', 'imp_preflang', 'en, eng, en-US')
        IMP_MONTHLANG = check_setting_str(CFG, 'General', 'imp_monthlang', 'en_US.utf8')
        IMP_AUTOADD = check_setting_str(CFG, 'General', 'imp_autoadd', '')
        IMP_ONLYISBN = check_setting_int(CFG, 'General', 'imp_onlyisbn', 0)
        IMP_SINGLEBOOK = check_setting_int(CFG, 'General', 'imp_singlebook', 0)

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

        NZBGET_HOST = check_setting_str(CFG, 'NZBGet', 'nzbget_host', '')
        NZBGET_USER = check_setting_str(CFG, 'NZBGet', 'nzbget_user', '')
        NZBGET_PASS = check_setting_str(CFG, 'NZBGet', 'nzbget_pass', '')
        NZBGET_CATEGORY = check_setting_str(CFG, 'NZBGet', 'nzbget_cat', '')
        NZBGET_PRIORITY = check_setting_int(CFG, 'NZBGet', 'nzbget_priority', '0')

        DESTINATION_COPY = check_setting_int(CFG, 'General', 'destination_copy', 0)
        DESTINATION_DIR = check_setting_str(CFG, 'General', 'destination_dir', '')
        ALTERNATE_DIR = check_setting_str(CFG, 'General', 'alternate_dir', '')
        DOWNLOAD_DIR = check_setting_str(CFG, 'General', 'download_dir', '')

        USE_NZB = check_setting_int(CFG, 'DLMethod', 'use_nzb', 0)
        USE_TOR = check_setting_int(CFG, 'DLMethod', 'use_tor', 0)

        NZB_DOWNLOADER_SABNZBD = check_setting_int(CFG, 'USENET', 'nzb_downloader_sabnzbd', 0)
        NZB_DOWNLOADER_NZBGET = check_setting_int(CFG, 'USENET', 'nzb_downloader_nzbget', 0)
        NZB_DOWNLOADER_BLACKHOLE = check_setting_int(CFG, 'USENET', 'nzb_downloader_blackhole', 0)
        NZB_BLACKHOLEDIR = check_setting_str(CFG, 'USENET', 'nzb_blackholedir', '')
        USENET_RETENTION = check_setting_str(CFG, 'USENET', 'usenet_retention', '')

        NZBMATRIX = check_setting_int(CFG, 'NZBMatrix', 'nzbmatrix', 0)
        NZBMATRIX_USER = check_setting_str(CFG, 'NZBMatrix', 'nzbmatrix_user', '')
        NZBMATRIX_API = check_setting_str(CFG, 'NZBMatrix', 'nzbmatrix_api', '')

# legacy names here - have changed some config names for consistency
# these entries convert the old name to the new one so we don't break existing configs
        if CFG.has_section('UsenetCrawler'):
            NEWZNAB0 = check_setting_int(CFG, 'UsenetCrawler', 'usenetcrawler', 0)
            NEWZNAB_HOST0 = check_setting_str(CFG, 'UsenetCrawler', 'usenetcrawler_host', '')
            NEWZNAB_API0 = check_setting_str(CFG, 'UsenetCrawler', 'usenetcrawler_api', '')
            CFG.remove_option('UsenetCrawler', 'usenetcrawler')
            CFG.remove_option('UsenetCrawler', 'usenetcrawler_host')
            CFG.remove_option('UsenetCrawler', 'usenetcrawler_api')
            CFG.remove_section('UsenetCrawler')
            check_section('Newznab0')
            CFG.set('Newznab0', 'newznab0', NEWZNAB0)
            CFG.set('Newznab0', 'newznab_host0', NEWZNAB_HOST0)
            CFG.set('Newznab0', 'newznab_api0', NEWZNAB_API0)            
        if CFG.has_section('Newznab'):    
            NEWZNAB1 = check_setting_int(CFG, 'Newznab', 'newznab', 0)
            NEWZNAB_HOST1 = check_setting_str(CFG, 'Newznab', 'newznab_host', '')
            NEWZNAB_API1 = check_setting_str(CFG, 'Newznab', 'newznab_api', '')
            CFG.remove_option('Newznab', 'newznab')
            CFG.remove_option('Newznab', 'newznab_host')
            CFG.remove_option('Newznab', 'newznab_api')
            CFG.remove_section('Newznab')
            check_section('Newznab1')
            CFG.set('Newznab1', 'newznab1', NEWZNAB1)
            CFG.set('Newznab1', 'newznab_host1', NEWZNAB_HOST1)
            CFG.set('Newznab1', 'newznab_api1', NEWZNAB_API1)            
        if not NEWZNAB_HOST0:  # did we pick up anything under the old name
            NEWZNAB0 = check_setting_int(CFG, 'Newznab0', 'newznab0', 0)
            NEWZNAB_HOST0 = check_setting_str(CFG, 'Newznab0', 'newznab_host0', '')
            NEWZNAB_API0 = check_setting_str(CFG, 'Newznab0', 'newznab_api0', '')
        if not NEWZNAB_HOST1:
            NEWZNAB1 = check_setting_int(CFG, 'Newznab1', 'newznab1', 0)
            NEWZNAB_HOST1 = check_setting_str(CFG, 'Newznab1', 'newznab_host1', '')
            NEWZNAB_API1 = check_setting_str(CFG, 'Newznab1', 'newznab_api1', '')
# end of legacy conversions
        NEWZNAB2 = check_setting_int(CFG, 'Newznab2', 'newznab2', 0)
        NEWZNAB_HOST2 = check_setting_str(CFG, 'Newznab2', 'newznab_host2', '')
        NEWZNAB_API2 = check_setting_str(CFG, 'Newznab2', 'newznab_api2', '')
        NEWZNAB3 = check_setting_int(CFG, 'Newznab3', 'newznab3', 0)
        NEWZNAB_HOST3 = check_setting_str(CFG, 'Newznab3', 'newznab_host3', '')
        NEWZNAB_API3 = check_setting_str(CFG, 'Newznab3', 'newznab_api3', '')
        NEWZNAB4 = check_setting_int(CFG, 'Newznab4', 'newznab4', 0)
        NEWZNAB_HOST4 = check_setting_str(CFG, 'Newznab4', 'newznab_host4', '')
        NEWZNAB_API4 = check_setting_str(CFG, 'Newznab4', 'newznab_api4', '')

        TORZNAB0 = check_setting_int(CFG, 'Torznab0', 'torznab0', 0)
        TORZNAB_HOST0 = check_setting_str(CFG, 'Torznab0', 'torznab_host0', '')
        TORZNAB_API0 = check_setting_str(CFG, 'Torznab0', 'torznab_api0', '')
        TORZNAB1 = check_setting_int(CFG, 'Torznab1', 'torznab1', 0)
        TORZNAB_HOST1 = check_setting_str(CFG, 'Torznab1', 'torznab_host1', '')
        TORZNAB_API1 = check_setting_str(CFG, 'Torznab1', 'torznab_api1', '')
        TORZNAB2 = check_setting_int(CFG, 'Torznab2', 'torznab2', 0)
        TORZNAB_HOST2 = check_setting_str(CFG, 'Torznab2', 'torznab_host2', '')
        TORZNAB_API2 = check_setting_str(CFG, 'Torznab2', 'torznab_api2', '')
        TORZNAB3 = check_setting_int(CFG, 'Torznab3', 'torznab3', 0)
        TORZNAB_HOST3 = check_setting_str(CFG, 'Torznab3', 'torznab_host3', '')
        TORZNAB_API3 = check_setting_str(CFG, 'Torznab3', 'torznab_api3', '')
        TORZNAB4 = check_setting_int(CFG, 'Torznab4', 'torznab4', 0)
        TORZNAB_HOST4 = check_setting_str(CFG, 'Torznab4', 'torznab_host4', '')
        TORZNAB_API4 = check_setting_str(CFG, 'Torznab4', 'torznab_api4', '')

        TOR_DOWNLOADER_BLACKHOLE = check_setting_int(CFG, 'TORRENT', 'tor_downloader_blackhole', 0)
        TOR_DOWNLOADER_UTORRENT = check_setting_int(CFG, 'TORRENT', 'tor_downloader_utorrent', 0)
        TOR_DOWNLOADER_TRANSMISSION = check_setting_int(CFG, 'TORRENT', 'tor_downloader_transmission', 0)
        TOR_DOWNLOADER_DELUGE = check_setting_int(CFG, 'TORRENT', 'tor_downloader_deluge', 0)
        NUMBEROFSEEDERS = check_setting_int(CFG, 'TORRENT', 'numberofseeders', 10)
        TORRENT_DIR = check_setting_str(CFG, 'TORRENT', 'torrent_dir', '')

        UTORRENT_HOST = check_setting_str(CFG, 'UTORRENT', 'utorrent_host', '')
        UTORRENT_USER = check_setting_str(CFG, 'UTORRENT', 'utorrent_user', '')
        UTORRENT_PASS = check_setting_str(CFG, 'UTORRENT', 'utorrent_pass', '')
        UTORRENT_LABEL = check_setting_str(CFG, 'UTORRENT', 'utorrent_label', '')

        TRANSMISSION_HOST = check_setting_str(CFG, 'TRANSMISSION', 'transmission_host', '')
        TRANSMISSION_USER = check_setting_str(CFG, 'TRANSMISSION', 'transmission_user', '')
        TRANSMISSION_PASS = check_setting_str(CFG, 'TRANSMISSION', 'transmission_pass', '')

        DELUGE_HOST = check_setting_str(CFG, 'DELUGE', 'deluge_host', '')
        DELUGE_PORT = check_setting_int(CFG, 'DELUGE', 'deluge_port', '')
        DELUGE_USER = check_setting_str(CFG, 'DELUGE', 'deluge_user', '')
        DELUGE_PASS = check_setting_str(CFG, 'DELUGE', 'deluge_pass', '')

        KAT = check_setting_int(CFG, 'KAT', 'kat', 0)
        KAT_HOST = check_setting_str(CFG, 'KAT', 'kat_host', 'kat.cr')

        NEWZBIN = check_setting_int(CFG, 'Newzbin', 'newzbin', 0)
        NEWZBIN_UID = check_setting_str(CFG, 'Newzbin', 'newzbin_uid', '')
        NEWZBIN_PASS = check_setting_str(CFG, 'Newzbin', 'newzbin_pass', '')
        EBOOK_TYPE = check_setting_str(CFG, 'General', 'ebook_type', 'epub, mobi, pdf')

        SEARCH_INTERVAL = check_setting_int(CFG, 'SearchScan', 'search_interval', '360')
        SCAN_INTERVAL = check_setting_int(CFG, 'SearchScan', 'scan_interval', '10')
        VERSIONCHECK_INTERVAL = check_setting_int(CFG, 'SearchScan', 'versioncheck_interval', '24')

        FULL_SCAN = check_setting_int(CFG, 'LibraryScan', 'full_scan', 0)
        ADD_AUTHOR = check_setting_int(CFG, 'LibraryScan', 'add_author', 1)
        NOTFOUND_STATUS = check_setting_str(CFG, 'LibraryScan', 'notfound_status', 'Skipped')
        NEWBOOK_STATUS = check_setting_str(CFG, 'LibraryScan', 'newbook_status', 'Skipped')

        EBOOK_DEST_FOLDER = check_setting_str(CFG, 'PostProcess', 'ebook_dest_folder', '$Author/$Title')
        EBOOK_DEST_FILE = check_setting_str(CFG, 'PostProcess', 'ebook_dest_file', '$Title - $Author')
        MAG_DEST_FOLDER = check_setting_str(CFG, 'PostProcess', 'mag_dest_folder', '_Magazines/$Title/$IssueDate')
        MAG_DEST_FILE = check_setting_str(CFG, 'PostProcess', 'mag_dest_file', '$IssueDate - $Title')
        MAG_RELATIVE = check_setting_int(CFG, 'PostProcess', 'mag_relative', 1)

        USE_TWITTER = check_setting_int(CFG, 'Twitter', 'use_twitter', 0)
        TWITTER_NOTIFY_ONSNATCH = check_setting_int(CFG, 'Twitter', 'twitter_notify_onsnatch', 0)
        TWITTER_NOTIFY_ONDOWNLOAD = check_setting_int(CFG, 'Twitter', 'twitter_notify_ondownload', 0)
        TWITTER_USERNAME = check_setting_str(CFG, 'Twitter', 'twitter_username', '')
        TWITTER_PASSWORD = check_setting_str(CFG, 'Twitter', 'twitter_password', '')
        TWITTER_PREFIX = check_setting_str(CFG, 'Twitter', 'twitter_prefix', 'LazyLibrarian')

        USE_BOXCAR = check_setting_int(CFG, 'Boxcar', 'use_boxcar', 0)
        BOXCAR_NOTIFY_ONSNATCH = check_setting_int(CFG, 'Boxcar', 'boxcar_notify_onsnatch', 0)
        BOXCAR_NOTIFY_ONDOWNLOAD = check_setting_int(CFG, 'Boxcar', 'boxcar_notify_ondownload', 0)
        BOXCAR_TOKEN = check_setting_str(CFG, 'Boxcar', 'boxcar_token', '')

        USE_PUSHBULLET = check_setting_int(CFG, 'Pushbullet', 'use_pushbullet', 0)
        PUSHBULLET_NOTIFY_ONSNATCH = check_setting_int(CFG, 'Pushbullet', 'pushbullet_notify_onsnatch', 0)
        PUSHBULLET_NOTIFY_ONDOWNLOAD = check_setting_int(CFG, 'Pushbullet', 'pushbullet_notify_ondownload', 0)
        PUSHBULLET_TOKEN = check_setting_str(CFG, 'Pushbullet', 'pushbullet_token', '')
        PUSHBULLET_DEVICEID = check_setting_str(CFG, 'Pushbullet', 'pushbullet_deviceid', '')

        USE_PUSHOVER = check_setting_int(CFG, 'Pushover', 'use_pushover', 0)
        PUSHOVER_ONSNATCH = check_setting_int(CFG, 'Pushover', 'pushover_onsnatch', 0)
        PUSHOVER_ONDOWNLOAD = check_setting_int(CFG, 'Pushover', 'pushover_ondownload', 0)
        PUSHOVER_KEYS = check_setting_str(CFG, 'Pushover', 'pushover_keys', '')
        PUSHOVER_APITOKEN = check_setting_str(CFG, 'Pushover', 'pushover_apitoken', '')
        PUSHOVER_PRIORITY = check_setting_int(CFG, 'Pushover', 'pushover_priority', 0)
        PUSHOVER_DEVICE = check_setting_str(CFG, 'Pushover', 'pushover_device', '')

        USE_ANDROIDPN = check_setting_int(CFG, 'AndroidPN', 'use_androidpn', 0)
        ANDROIDPN_NOTIFY_ONSNATCH = check_setting_int(CFG, 'AndroidPN', 'androidpn_notify_onsnatch', 0)
        ANDROIDPN_NOTIFY_ONDOWNLOAD = check_setting_int(CFG, 'AndroidPN', 'androidpn_notify_ondownload', 0)
        ANDROIDPN_URL = check_setting_str(CFG, 'AndroidPN', 'androidpn_url', '')
        ANDROIDPN_USERNAME = check_setting_str(CFG, 'AndroidPN', 'androidpn_username', '')
        ANDROIDPN_BROADCAST = check_setting_int(CFG, 'AndroidPN', 'androidpn_broadcast', 1)

        USE_NMA = check_setting_int(CFG, 'NMA', 'use_nma', 0)
        NMA_APIKEY = check_setting_str(CFG, 'NMA', 'nma_apikey', '')
        NMA_PRIORITY = check_setting_int(CFG, 'NMA', 'nma_priority', 0)
        NMA_ONSNATCH = check_setting_int(CFG, 'NMA', 'nma_onsnatch', 0)
        NMA_ONDOWNLOAD = check_setting_int(CFG, 'NMA', 'nma_ondownload', 0)

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

        build_monthtable()

        __INITIALIZED__ = True
        return True


def build_monthtable():
    current_locale = locale.setlocale(locale.LC_ALL, '')  # read current state.
# getdefaultlocale() doesnt seem to work as expected on windows, returns 'None'
# ensure current locale is in the list...
# actually I'm not sure if this is a good idea. I Added this as my Raspberry Pi
# defaults to en_GB and does not have en_US loaded, but it's probably better in
# this case for the user to put en_GB in the config setting instead of en_US??
# Or have an empty config setting?
# Or at least remove en_US from the config list so we don't check the same names twice?
#
    lang = str(current_locale)
    MONTHNAMES[0].append(lang)
    for f in range(1, 13):
        MONTHNAMES[f].append(common.remove_accents(calendar.month_name[f]).lower())
    MONTHNAMES[0].append(lang)
    for f in range(1, 13):
        MONTHNAMES[f].append(common.remove_accents(calendar.month_abbr[f]).lower().strip('.'))
    logger.info("Added month names for locale [%s], %s, %s ..." % (
        lang, MONTHNAMES[1][len(MONTHNAMES[1]) - 2], MONTHNAMES[1][len(MONTHNAMES[1]) - 1]))

    for lang in IMP_MONTHLANG.split(','):
        try:
            lang = str(lang).strip()
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
            logger.info("Set locale back to entry state %s" % current_locale)
    # quick sanity check, warn if no english names in table
    eng = 0
    for lang in MONTHNAMES[0]:
        if lang.startswith('en_'):
            eng = 1
    if not eng:
        logger.warn("No English language loaded - Magazine name matching will probably fail")


def daemonize():
    """
    Fork off as a daemon
    """

    # Make a non-session-leader child process
    try:
        pid = os.fork()  # @UndefinedVariable - only available in UNIX
        if pid != 0:
            sys.exit(0)
    except OSError, e:
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
    check_section('General')
    CFG.set('General', 'http_port', HTTP_PORT)
    CFG.set('General', 'http_host', HTTP_HOST)
    CFG.set('General', 'http_user', HTTP_USER)
    CFG.set('General', 'http_pass', HTTP_PASS)
    CFG.set('General', 'http_root', HTTP_ROOT)
    CFG.set('General', 'http_look', HTTP_LOOK)
    CFG.set('General', 'launch_browser', LAUNCH_BROWSER)
    CFG.set('General', 'proxy_host', PROXY_HOST)
    CFG.set('General', 'proxy_type', PROXY_TYPE)
    CFG.set('General', 'logdir', LOGDIR)
    CFG.set('General', 'loglevel', LOGLEVEL)
    CFG.set('General', 'match_ratio', MATCH_RATIO)
    CFG.set('General', 'imp_onlyisbn', IMP_ONLYISBN)
    CFG.set('General', 'imp_singlebook', IMP_SINGLEBOOK)
    CFG.set('General', 'imp_preflang', IMP_PREFLANG)
    CFG.set('General', 'imp_monthlang', IMP_MONTHLANG)
    CFG.set('General', 'imp_autoadd', IMP_AUTOADD)
    CFG.set('General', 'ebook_type', EBOOK_TYPE)
    CFG.set('General', 'destination_dir', DESTINATION_DIR)
    CFG.set('General', 'alternate_dir', ALTERNATE_DIR)
    CFG.set('General', 'destination_copy', DESTINATION_COPY)
    CFG.set('General', 'download_dir', DOWNLOAD_DIR)
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
    CFG.set('NZBGet', 'nzbget_user', NZBGET_USER)
    CFG.set('NZBGet', 'nzbget_pass', NZBGET_PASS)
    CFG.set('NZBGet', 'nzbget_cat', NZBGET_CATEGORY)
    CFG.set('NZBGet', 'nzbget_priority', NZBGET_PRIORITY)
#
    check_section('DLMethod')
    CFG.set('DLMethod', 'use_tor', USE_TOR)
    CFG.set('DLMethod', 'use_nzb', USE_NZB)
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
    check_section('Newznab0')
    CFG.set('Newznab0', 'newznab0', NEWZNAB0)
    CFG.set('Newznab0', 'newznab_host0', NEWZNAB_HOST0)
    CFG.set('Newznab0', 'newznab_api0', NEWZNAB_API0)
#
    check_section('Newznab1')
    CFG.set('Newznab1', 'newznab1', NEWZNAB1)
    CFG.set('Newznab1', 'newznab_host1', NEWZNAB_HOST1)
    CFG.set('Newznab1', 'newznab_api1', NEWZNAB_API1)
#
    check_section('Newznab2')
    CFG.set('Newznab2', 'newznab2', NEWZNAB2)
    CFG.set('Newznab2', 'newznab_host2', NEWZNAB_HOST2)
    CFG.set('Newznab2', 'newznab_api2', NEWZNAB_API2)
#
    check_section('Newznab3')
    CFG.set('Newznab3', 'newznab3', NEWZNAB3)
    CFG.set('Newznab3', 'newznab_host3', NEWZNAB_HOST3)
    CFG.set('Newznab3', 'newznab_api3', NEWZNAB_API3)
#
    check_section('Newznab4')
    CFG.set('Newznab4', 'newznab4', NEWZNAB4)
    CFG.set('Newznab4', 'newznab_host4', NEWZNAB_HOST4)
    CFG.set('Newznab4', 'newznab_api4', NEWZNAB_API4)
#
    check_section('Torznab0')
    CFG.set('Torznab0', 'torznab0', TORZNAB0)
    CFG.set('Torznab0', 'torznab_host0', TORZNAB_HOST0)
    CFG.set('Torznab0', 'torznab_api0', TORZNAB_API0)
#
    check_section('Torznab1')
    CFG.set('Torznab1', 'torznab1', TORZNAB1)
    CFG.set('Torznab1', 'torznab_host1', TORZNAB_HOST1)
    CFG.set('Torznab1', 'torznab_api1', TORZNAB_API1)
#
    check_section('Torznab2')
    CFG.set('Torznab2', 'torznab2', TORZNAB2)
    CFG.set('Torznab2', 'torznab_host2', TORZNAB_HOST2)
    CFG.set('Torznab2', 'torznab_api2', TORZNAB_API2)
#
    check_section('Torznab3')
    CFG.set('Torznab3', 'torznab3', TORZNAB3)
    CFG.set('Torznab3', 'torznab_host3', TORZNAB_HOST3)
    CFG.set('Torznab3', 'torznab_api3', TORZNAB_API3)
#
    check_section('Torznab4')
    CFG.set('Torznab4', 'torznab4', TORZNAB4)
    CFG.set('Torznab4', 'torznab_host4', TORZNAB_HOST4)
    CFG.set('Torznab4', 'torznab_api4', TORZNAB_API4)
#
    check_section('Newzbin')
    CFG.set('Newzbin', 'newzbin', NEWZBIN)
    CFG.set('Newzbin', 'newzbin_uid', NEWZBIN_UID)
    CFG.set('Newzbin', 'newzbin_pass', NEWZBIN_PASS)
#
    check_section('TORRENT')
    CFG.set('TORRENT', 'tor_downloader_blackhole', TOR_DOWNLOADER_BLACKHOLE)
    CFG.set('TORRENT', 'tor_downloader_utorrent', TOR_DOWNLOADER_UTORRENT)
    CFG.set('TORRENT', 'tor_downloader_transmission', TOR_DOWNLOADER_TRANSMISSION)
    CFG.set('TORRENT', 'tor_downloader_deluge', TOR_DOWNLOADER_DELUGE)
    CFG.set('TORRENT', 'numberofseeders', NUMBEROFSEEDERS)
    CFG.set('TORRENT', 'torrent_dir', TORRENT_DIR)
#
    check_section('UTORRENT')
    CFG.set('UTORRENT', 'utorrent_host', UTORRENT_HOST)
    CFG.set('UTORRENT', 'utorrent_user', UTORRENT_USER)
    CFG.set('UTORRENT', 'utorrent_pass', UTORRENT_PASS)
    CFG.set('UTORRENT', 'utorrent_label', UTORRENT_LABEL)
#
    check_section('TRANSMISSION')
    CFG.set('TRANSMISSION', 'transmission_host', TRANSMISSION_HOST)
    CFG.set('TRANSMISSION', 'transmission_user', TRANSMISSION_USER)
    CFG.set('TRANSMISSION', 'transmission_pass', TRANSMISSION_PASS)
#
    check_section('DELUGE')
    CFG.set('DELUGE', 'deluge_host', DELUGE_HOST)
    CFG.set('DELUGE', 'deluge_port', DELUGE_PORT)
    CFG.set('DELUGE', 'deluge_user', DELUGE_USER)
    CFG.set('DELUGE', 'deluge_pass', DELUGE_PASS)
#
    check_section('KAT')
    CFG.set('KAT', 'kat', KAT)
    CFG.set('KAT', 'kat_host', KAT_HOST)
#
    check_section('SearchScan')
    CFG.set('SearchScan', 'search_interval', SEARCH_INTERVAL)
    CFG.set('SearchScan', 'scan_interval', SCAN_INTERVAL)
    CFG.set('SearchScan', 'versioncheck_interval', VERSIONCHECK_INTERVAL)
#
    check_section('LibraryScan')
    CFG.set('LibraryScan', 'full_scan', FULL_SCAN)
    CFG.set('LibraryScan', 'add_author', ADD_AUTHOR)
    CFG.set('LibraryScan', 'notfound_status', NOTFOUND_STATUS)
    CFG.set('LibraryScan', 'newbook_status', NEWBOOK_STATUS)
#
    check_section('PostProcess')
    CFG.set('PostProcess', 'ebook_dest_folder', EBOOK_DEST_FOLDER)
    CFG.set('PostProcess', 'ebook_dest_file', EBOOK_DEST_FILE)
    CFG.set('PostProcess', 'mag_dest_folder', MAG_DEST_FOLDER)
    CFG.set('PostProcess', 'mag_dest_file', MAG_DEST_FILE)
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

    with open(CONFIGFILE, 'w') as configfile:
        CFG.write(configfile)


def dbcheck():

    conn = sqlite3.connect(DBFILE)
    c = conn.cursor()
    c.execute('CREATE TABLE IF NOT EXISTS authors (AuthorID TEXT, AuthorName TEXT UNIQUE, AuthorImg TEXT, AuthorLink TEXT, DateAdded TEXT, Status TEXT, LastBook TEXT, LastLink Text, LastDate TEXT, HaveBooks INTEGER, TotalBooks INTEGER, AuthorBorn TEXT, AuthorDeath TEXT, UnignoredBooks INTEGER)')
    c.execute('CREATE TABLE IF NOT EXISTS books (AuthorID TEXT, AuthorName TEXT, AuthorLink TEXT, BookName TEXT, BookSub TEXT, BookDesc TEXT, BookGenre TEXT, BookIsbn TEXT, BookPub TEXT, BookRate INTEGER, BookImg TEXT, BookPages INTEGER, BookLink TEXT, BookID TEXT UNIQUE, BookDate TEXT, BookLang TEXT, BookAdded TEXT, Status TEXT, Series TEXT, SeriesOrder INTEGER)')
    c.execute('CREATE TABLE IF NOT EXISTS wanted (BookID TEXT, NZBurl TEXT, NZBtitle TEXT, NZBdate TEXT, NZBprov TEXT, Status TEXT, NZBsize TEXT, AuxInfo TEXT)')
    c.execute('CREATE TABLE IF NOT EXISTS magazines (Title TEXT, Frequency TEXT, Regex TEXT, Status TEXT, MagazineAdded TEXT, LastAcquired TEXT, IssueDate TEXT, IssueStatus TEXT)')
    c.execute('CREATE TABLE IF NOT EXISTS languages ( isbn TEXT, lang TEXT )')
    c.execute('CREATE TABLE IF NOT EXISTS stats ( authorname text, GR_book_hits int, GR_lang_hits int, LT_lang_hits int, GB_lang_change, cache_hits int, bad_lang int, bad_char int, uncached int )')

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
        logger.info('Updating database to hold NZBside')
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

    addedSeries = False
    try:
        c.execute('SELECT Series from books')
    except sqlite3.OperationalError:
        logger.info('Updating database to hold Series')
        c.execute('ALTER TABLE books ADD COLUMN Series TEXT')
        addedSeries = True

    try:
        c.execute('SELECT SeriesOrder from books')
    except sqlite3.OperationalError:
        logger.info('Updating database to hold SeriesOrder')
        c.execute('ALTER TABLE books ADD COLUMN SeriesOrder INTEGER')

    addedIssues = False
    try:
        c.execute('SELECT Title from issues')
    except sqlite3.OperationalError:
        logger.info('Updating database to hold Issues')
        c.execute('CREATE TABLE issues ( Title TEXT, IssueAcquired TEXT, IssueDate TEXT, IssueFile TEXT )')
        addedIssues = True
            
    conn.commit()
    c.close()

    if addedIssues:
        try:
            magazinescan.magazineScan(thread='MAIN')
        except:
            logger.debug("Failed to scan magazines")
        
    if addedSeries:
        try:
            myDB = database.DBConnection()
            books = myDB.select('SELECT BookID, BookName FROM books')
            if books:
                logger.info('Adding series to existing books')
                for book in books:
                    result = re.search(r"\(([\S\s]+)\, #(\d+)|\(([\S\s]+) #(\d+)", book["BookName"])
                    if result:
                        if result.group(1) == None:
                            series = result.group(3)
                            seriesOrder = result.group(4)
                        else:
                            series = result.group(1)
                            seriesOrder = result.group(2)

                        controlValueDict = {"BookID": book["BookID"]}
                        newValueDict = {
                            "series":   series,
                            "seriesOrder": seriesOrder
                        }
                        myDB.upsert("books", newValueDict, controlValueDict)
        except Exception, z:
            logger.info('Error: ' + str(z))

    try:
        myDB = database.DBConnection()
        author = myDB.select('SELECT AuthorID FROM authors WHERE AuthorName IS NULL')
        if author:
            logger.info('Removing un-named author from database')
            authorid = author[0]["AuthorID"]
            myDB.action('DELETE from authors WHERE AuthorID="%s"' % authorid)
            myDB.action('DELETE from books WHERE AuthorID="%s"' % authorid)
    except Exception, z:
        logger.info('Error: ' + str(z))


def start():
    global __INITIALIZED__, started

    if __INITIALIZED__:

        # Crons and scheduled jobs go here
        # list is duplicated in webServe so we can reschedule them
        SCHED.add_interval_job(postprocess.processDir, minutes=int(SCAN_INTERVAL))

        if USE_NZB:
            SCHED.add_interval_job(searchnzb.search_nzb_book, minutes=int(SEARCH_INTERVAL))
        if USE_TOR:
            SCHED.add_interval_job(searchtorrents.search_tor_book, minutes=int(SEARCH_INTERVAL))
        SCHED.add_interval_job(versioncheck.checkForUpdates, hours=int(VERSIONCHECK_INTERVAL))
        if USE_TOR or USE_NZB:
            SCHED.add_interval_job(searchmag.search_magazines, minutes=int(SEARCH_INTERVAL))
            
        SCHED.start()
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
