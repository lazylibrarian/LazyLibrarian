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

from __future__ import with_statement

import calendar
import json
import locale
import os
import subprocess
import sys
import threading
import time
import webbrowser

import cherrypy
from lazylibrarian import logger, postprocess, searchnzb, searchtorrents, searchrss, \
    librarysync, versioncheck, database, searchmag, magazinescan, bookwork, dbupgrade
from lazylibrarian.cache import fetchURL
from lazylibrarian.common import restartJobs, internet
from lazylibrarian.formatter import getList, bookSeries, plural, unaccented
from lib.apscheduler.scheduler import Scheduler

FULL_PATH = None
PROG_DIR = None

ARGS = None
SIGNAL = None
DAEMON = False
PIDFILE = ''

SYS_ENCODING = ''
SCHED = Scheduler()
INIT_LOCK = threading.Lock()
__INITIALIZED__ = False
CFG = ''
started = False

COMMIT_LIST = None
DATADIR = None
DBFILE = None
UPDATE_MSG = ''
CONFIGFILE = ''
CURRENT_TAB = '1'
# Bits after surname that we need to keep at the end...
NAME_POSTFIX = 'snr, jnr, jr, sr, phd'
CACHEDIR = None
LOGLIST = []
# Info 1, Debug 2, >2 don't toggle console/file
LOGLEVEL = 2
LOGFULL = False  # include debug on screen if true
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


def check_setting(cfg_type, cfg_name, item_name, def_val, log=True):
    """ Check option exists, coerce to correct type, or return default"""
    if cfg_type == 'int':
        try:
            my_val = CFG.getint(cfg_name, item_name)
        except Exception:
            my_val = int(def_val)

    elif cfg_type == 'bool':
        try:
            my_val = CFG.getboolean(cfg_name, item_name)
        except Exception:
            my_val = bool(def_val)

    elif cfg_type == 'str':
        try:
            my_val = CFG.get(cfg_name, item_name)
            # Old config file format had strings in quotes. ConfigParser doesn't.
            if my_val.startswith('"') and my_val.endswith('"'):
                my_val = my_val[1:-1]
            my_val = my_val.decode(SYS_ENCODING)
        except Exception:
            my_val = str(def_val)
    else:
        my_val = def_val

    check_section(cfg_name)
    CFG.set(cfg_name, item_name, my_val)
    if log:
        logger.debug("%s : %s -> %s" % (cfg_name, item_name, my_val))

    return my_val


def initialize():
    with INIT_LOCK:
        global __INITIALIZED__, LOGDIR, LOGLIMIT, LOGFILES, LOGSIZE, CFG, CFGLOGLEVEL, LOGLEVEL, \
            LOGFULL, CACHEDIR, DATADIR, LAST_LIBRARYTHING, LAST_GOODREADS, \
            BOOKSTRAP_THEMELIST, MONTHNAMES, CURRENT_TAB, UPDATE_MSG, NAME_POSTFIX

        if __INITIALIZED__:
            return False

        check_section('General')

        LOGDIR = check_setting('str', 'General', 'logdir', '')
        LOGLIMIT = check_setting('int', 'General', 'loglimit', 500)
        LOGFILES = check_setting('int', 'General', 'logfiles', 10)
        LOGSIZE = check_setting('int', 'General', 'logsize', 204800)

        if not LOGDIR:
            LOGDIR = os.path.join(DATADIR, 'Logs')
        # Create logdir
        if not os.path.exists(LOGDIR):
            try:
                os.makedirs(LOGDIR)
            except OSError as e:
                if LOGLEVEL:
                    print '%s : Unable to create folder for logs: %s. Only logging to console.' % (LOGDIR, str(e))

        # Start the logger, silence console logging if we need to
        CFGLOGLEVEL = check_setting('int', 'General', 'loglevel', 9)
        if LOGLEVEL == 1:  # default if no debug or quiet on cmdline
            if CFGLOGLEVEL == 9:  # default value if none in config
                LOGLEVEL = 2  # If not set in Config or cmdline, then lets set to DEBUG
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
        logger.info('SYS_ENCODING is %s' % SYS_ENCODING)

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

        # Initialize the database
        try:
            curr_ver = db_needs_upgrade()
            if curr_ver:
                threading.Thread(target=dbupgrade.dbupgrade, name="DB_UPGRADE", args=[curr_ver]).start()
            else:
                myDB = database.DBConnection()
                result = myDB.match('PRAGMA user_version')
                check = myDB.match('PRAGMA integrity_check')
                if result:
                    version = result[0]
                else:
                    version = 0
                logger.info("Database is version %s, integrity check: %s" % (version, check[0]))

        except Exception as e:
            logger.error("Can't connect to the database: %s" % str(e))

        MONTHNAMES = build_monthtable()
        BOOKSTRAP_THEMELIST = build_bookstrap_themes()

        __INITIALIZED__ = True
        return True


def config_read(reloaded=False):
    global FULL_PATH, PROG_DIR, DAEMON, DISPLAYLENGTH, \
        HTTP_HOST, HTTP_PORT, HTTP_USER, HTTP_PASS, HTTP_PROXY, HTTP_ROOT, HTTP_LOOK, API_KEY, API_ENABLED, \
        LAUNCH_BROWSER, LOGDIR, CACHE_AGE, MATCH_RATIO, DLOAD_RATIO, PROXY_HOST, PROXY_TYPE, GIT_PROGRAM, \
        IMP_ONLYISBN, IMP_SINGLEBOOK, IMP_PREFLANG, IMP_MONTHLANG, IMP_AUTOADD, IMP_CONVERT, IMP_CALIBREDB, \
        IMP_AUTOSEARCH, MONTHNAMES, MONTH0, MONTH1, MONTH2, MONTH3, MONTH4, MONTH5, MONTH6, MONTH7, \
        MONTH8, MONTH9, MONTH10, MONTH11, MONTH12, CONFIGFILE, CFG, LOGLIMIT, TASK_AGE, \
        SAB_HOST, SAB_PORT, SAB_SUBDIR, SAB_API, SAB_USER, SAB_PASS, SAB_CAT, \
        DESTINATION_DIR, DESTINATION_COPY, DOWNLOAD_DIR, USENET_RETENTION, NZB_BLACKHOLEDIR, \
        ALTERNATE_DIR, GR_API, GB_API, BOOK_API, \
        NZBGET_HOST, NZBGET_USER, NZBGET_PASS, NZBGET_CATEGORY, NZBGET_PRIORITY, \
        NZBGET_PORT, NZB_DOWNLOADER_NZBGET, NZBMATRIX, NZBMATRIX_USER, NZBMATRIX_API, \
        NEWZBIN, NEWZBIN_UID, NEWZBIN_PASS, EBOOK_TYPE, MAG_TYPE, \
        KAT, KAT_HOST, TPB, TPB_HOST, ZOO, ZOO_HOST, TDL, TDL_HOST, GEN, GEN_HOST, EXTRA, EXTRA_HOST, \
        LIME, LIME_HOST, NEWZNAB_PROV, TORZNAB_PROV, RSS_PROV, REJECT_WORDS, REJECT_MAXSIZE, REJECT_MAGSIZE, \
        VERSIONCHECK_INTERVAL, SEARCH_INTERVAL, SCAN_INTERVAL, SEARCHRSS_INTERVAL, MAG_AGE, \
        EBOOK_DEST_FOLDER, EBOOK_DEST_FILE, ONE_FORMAT, MAG_RELATIVE, MAG_DEST_FOLDER, MAG_DEST_FILE, MAG_SINGLE, \
        USE_TWITTER, TWITTER_NOTIFY_ONSNATCH, TWITTER_NOTIFY_ONDOWNLOAD, \
        TWITTER_USERNAME, TWITTER_PASSWORD, TWITTER_PREFIX, TOR_CONVERT_MAGNET, \
        USE_BOXCAR, BOXCAR_NOTIFY_ONSNATCH, BOXCAR_NOTIFY_ONDOWNLOAD, BOXCAR_TOKEN, \
        TORRENT_DIR, TOR_DOWNLOADER_BLACKHOLE, TOR_DOWNLOADER_UTORRENT, TOR_DOWNLOADER_RTORRENT, \
        TOR_DOWNLOADER_QBITTORRENT, NZB_DOWNLOADER_SABNZBD, NZB_DOWNLOADER_SYNOLOGY, NZB_DOWNLOADER_BLACKHOLE, \
        SYNOLOGY_DIR, USE_SYNOLOGY, USE_PUSHBULLET, PUSHBULLET_NOTIFY_ONSNATCH, PUSHBULLET_NOTIFY_ONDOWNLOAD, \
        PUSHBULLET_TOKEN, PUSHBULLET_DEVICEID, RTORRENT_HOST, RTORRENT_USER, RTORRENT_PASS, RTORRENT_DIR, \
        RTORRENT_LABEL, UTORRENT_HOST, UTORRENT_PORT, UTORRENT_USER, UTORRENT_PASS, UTORRENT_LABEL, \
        QBITTORRENT_HOST, QBITTORRENT_PORT, QBITTORRENT_USER, QBITTORRENT_PASS, QBITTORRENT_LABEL, \
        SYNOLOGY_PORT, SYNOLOGY_HOST, SYNOLOGY_USER, SYNOLOGY_PASS, USE_PUSHOVER, PUSHOVER_ONSNATCH, \
        PUSHOVER_KEYS, PUSHOVER_APITOKEN, PUSHOVER_PRIORITY, PUSHOVER_ONDOWNLOAD, PUSHOVER_DEVICE, \
        USE_ANDROIDPN, ANDROIDPN_NOTIFY_ONSNATCH, ANDROIDPN_NOTIFY_ONDOWNLOAD, \
        ANDROIDPN_URL, ANDROIDPN_USERNAME, ANDROIDPN_BROADCAST, \
        USE_SLACK, SLACK_NOTIFY_ONSNATCH, SLACK_NOTIFY_ONDOWNLOAD, SLACK_TOKEN, \
        USE_EMAIL, EMAIL_NOTIFY_ONSNATCH, EMAIL_NOTIFY_ONDOWNLOAD, EMAIL_FROM, EMAIL_TO, \
        EMAIL_SSL, EMAIL_SMTP_SERVER, EMAIL_SMTP_PORT, EMAIL_TLS, EMAIL_SMTP_USER, EMAIL_SMTP_PASSWORD, \
        TOR_DOWNLOADER_TRANSMISSION, TRANSMISSION_HOST, TRANSMISSION_PORT, TRANSMISSION_PASS, TRANSMISSION_USER, \
        TOR_DOWNLOADER_SYNOLOGY, TOR_DOWNLOADER_DELUGE, DELUGE_HOST, DELUGE_USER, DELUGE_PASS, DELUGE_PORT, \
        DELUGE_LABEL, FULL_SCAN, ADD_AUTHOR, NOTFOUND_STATUS, NEWBOOK_STATUS, NEWAUTHOR_STATUS, \
        USE_NMA, NMA_APIKEY, NMA_PRIORITY, NMA_ONSNATCH, NMA_ONDOWNLOAD, \
        GIT_USER, GIT_REPO, GIT_BRANCH, INSTALL_TYPE, CURRENT_VERSION, COMMIT_LIST, PREFER_MAGNET, \
        LATEST_VERSION, COMMITS_BEHIND, NUMBEROFSEEDERS, KEEP_SEEDING, SCHED, CACHE_HIT, CACHE_MISS, \
        BOOKSTRAP_THEME, LOGFILES, LOGSIZE, HTTPS_ENABLED, HTTPS_CERT, HTTPS_KEY

    # legacy name conversions, separate out host/port
    for provider in ['NZBGet', 'UTORRENT', 'QBITTORRENT', 'TRANSMISSION']:
        if not CFG.has_option(provider, '%s_port' % provider.lower()):
            port = 0
            host = check_setting('str', provider, '%s_host' % provider.lower(), '')
            if host.startswith('http'):
                hostpart = 2
            else:
                hostpart = 1
            words = host.split(':')
            if len(words) > hostpart:
                host = ':'.join(words[:hostpart])
                port = ':'.join(words[hostpart:])
            CFG.set(provider, '%s_port' % provider.lower(), port)
            CFG.set(provider, '%s_host' % provider.lower(), host)


    # we read the log details earlier for starting the logger process,
    # but read them again here so they get listed in the debug log
    LOGDIR = check_setting('str', 'General', 'logdir', '')
    LOGLIMIT = check_setting('int', 'General', 'loglimit', 500)
    LOGFILES = check_setting('int', 'General', 'logfiles', 10)
    LOGSIZE = check_setting('int', 'General', 'logsize', 204800)
    HTTP_PORT = check_setting('int', 'General', 'http_port', 5299)

    MATCH_RATIO = check_setting('int', 'General', 'match_ratio', 80)
    DLOAD_RATIO = check_setting('int', 'General', 'dload_ratio', 90)
    DISPLAYLENGTH = check_setting('int', 'General', 'displaylength', 10)
    HTTP_HOST = check_setting('str', 'General', 'http_host', '0.0.0.0')
    HTTP_USER = check_setting('str', 'General', 'http_user', '')
    HTTP_PASS = check_setting('str', 'General', 'http_pass', '')
    HTTP_PROXY = check_setting('bool', 'General', 'http_proxy', 0)
    HTTP_ROOT = check_setting('str', 'General', 'http_root', '')
    HTTP_LOOK = check_setting('str', 'General', 'http_look', 'default')
    HTTPS_ENABLED = check_setting('bool', 'General', 'https_enabled', 0)
    HTTPS_CERT = check_setting('str', 'General', 'https_cert', '')
    HTTPS_KEY = check_setting('str', 'General', 'https_key', '')
    BOOKSTRAP_THEME = check_setting('str', 'General', 'bookstrap_theme', 'slate')
    MAG_SINGLE = check_setting('bool', 'General', 'mag_single', 1)

    LAUNCH_BROWSER = check_setting('bool', 'General', 'launch_browser', 1)
    API_ENABLED = check_setting('bool', 'General', 'api_enabled', 0)
    API_KEY = check_setting('str', 'General', 'api_key', '')

    PROXY_HOST = check_setting('str', 'General', 'proxy_host', '')
    PROXY_TYPE = check_setting('str', 'General', 'proxy_type', '')

    IMP_PREFLANG = check_setting('str', 'General', 'imp_preflang', 'en, eng, en-US, en-GB')
    IMP_MONTHLANG = check_setting('str', 'General', 'imp_monthlang', '')
    IMP_AUTOADD = check_setting('str', 'General', 'imp_autoadd', '')
    IMP_AUTOSEARCH = check_setting('bool', 'General', 'imp_autosearch', 0)
    IMP_CALIBREDB = check_setting('str', 'General', 'imp_calibredb', '')
    IMP_ONLYISBN = check_setting('bool', 'General', 'imp_onlyisbn', 0)
    IMP_SINGLEBOOK = check_setting('bool', 'General', 'imp_singlebook', 0)
    IMP_CONVERT = check_setting('str', 'General', 'imp_convert', '')
    GIT_PROGRAM = check_setting('str', 'General', 'git_program', '')
    CACHE_AGE = check_setting('int', 'General', 'cache_age', 30)
    TASK_AGE = check_setting('int', 'General', 'task_age', 0)

    GIT_USER = check_setting('str', 'Git', 'git_user', 'dobytang')
    GIT_REPO = check_setting('str', 'Git', 'git_repo', 'lazylibrarian')
    GIT_BRANCH = check_setting('str', 'Git', 'git_branch', 'master')
    INSTALL_TYPE = check_setting('str', 'Git', 'install_type', '')
    CURRENT_VERSION = check_setting('str', 'Git', 'current_version', '')
    LATEST_VERSION = check_setting('str', 'Git', 'latest_version', '')
    COMMITS_BEHIND = check_setting('str', 'Git', 'commits_behind', '')

    SAB_HOST = check_setting('str', 'SABnzbd', 'sab_host', '')
    SAB_PORT = check_setting('int', 'SABnzbd', 'sab_port', 0)
    SAB_SUBDIR = check_setting('str', 'SABnzbd', 'sab_subdir', '')
    SAB_USER = check_setting('str', 'SABnzbd', 'sab_user', '')
    SAB_PASS = check_setting('str', 'SABnzbd', 'sab_pass', '')
    SAB_API = check_setting('str', 'SABnzbd', 'sab_api', '')
    SAB_CAT = check_setting('str', 'SABnzbd', 'sab_cat', '')

    NZBGET_HOST = check_setting('str', 'NZBGet', 'nzbget_host', '')
    NZBGET_PORT = check_setting('int', 'NZBGet', 'nzbget_port', '0')
    NZBGET_USER = check_setting('str', 'NZBGet', 'nzbget_user', '')
    NZBGET_PASS = check_setting('str', 'NZBGet', 'nzbget_pass', '')
    NZBGET_CATEGORY = check_setting('str', 'NZBGet', 'nzbget_cat', '')
    NZBGET_PRIORITY = check_setting('int', 'NZBGet', 'nzbget_priority', '0')

    DESTINATION_COPY = check_setting('bool', 'General', 'destination_copy', 0)
    DESTINATION_DIR = check_setting('str', 'General', 'destination_dir', '')
    ALTERNATE_DIR = check_setting('str', 'General', 'alternate_dir', '')
    DOWNLOAD_DIR = check_setting('str', 'General', 'download_dir', '')

    NZB_DOWNLOADER_SABNZBD = check_setting('bool', 'USENET', 'nzb_downloader_sabnzbd', 0)
    NZB_DOWNLOADER_NZBGET = check_setting('bool', 'USENET', 'nzb_downloader_nzbget', 0)
    NZB_DOWNLOADER_SYNOLOGY = check_setting('bool', 'USENET', 'nzb_downloader_synology', 0)
    NZB_DOWNLOADER_BLACKHOLE = check_setting('bool', 'USENET', 'nzb_downloader_blackhole', 0)
    NZB_BLACKHOLEDIR = check_setting('str', 'USENET', 'nzb_blackholedir', '')
    USENET_RETENTION = check_setting('int', 'USENET', 'usenet_retention', 0)

    NZBMATRIX = check_setting('bool', 'NZBMatrix', 'nzbmatrix', 0)
    NZBMATRIX_USER = check_setting('str', 'NZBMatrix', 'nzbmatrix_user', '')
    NZBMATRIX_API = check_setting('str', 'NZBMatrix', 'nzbmatrix_api', '')

    TOR_DOWNLOADER_BLACKHOLE = check_setting('bool', 'TORRENT', 'tor_downloader_blackhole', 0)
    TOR_CONVERT_MAGNET = check_setting('bool', 'TORRENT', 'tor_convert_magnet', 0)
    TOR_DOWNLOADER_UTORRENT = check_setting('bool', 'TORRENT', 'tor_downloader_utorrent', 0)
    TOR_DOWNLOADER_RTORRENT = check_setting('bool', 'TORRENT', 'tor_downloader_rtorrent', 0)
    TOR_DOWNLOADER_QBITTORRENT = check_setting('bool', 'TORRENT', 'tor_downloader_qbittorrent', 0)
    TOR_DOWNLOADER_TRANSMISSION = check_setting('bool', 'TORRENT', 'tor_downloader_transmission', 0)
    TOR_DOWNLOADER_SYNOLOGY = check_setting('bool', 'TORRENT', 'tor_downloader_synology', 0)
    TOR_DOWNLOADER_DELUGE = check_setting('bool', 'TORRENT', 'tor_downloader_deluge', 0)
    NUMBEROFSEEDERS = check_setting('int', 'TORRENT', 'numberofseeders', 10)
    KEEP_SEEDING = check_setting('bool', 'TORRENT', 'keep_seeding', 1)
    PREFER_MAGNET = check_setting('bool', 'TORRENT', 'prefer_magnet', 1)
    TORRENT_DIR = check_setting('str', 'TORRENT', 'torrent_dir', '')

    RTORRENT_HOST = check_setting('str', 'RTORRENT', 'rtorrent_host', '')
    RTORRENT_USER = check_setting('str', 'RTORRENT', 'rtorrent_user', '')
    RTORRENT_PASS = check_setting('str', 'RTORRENT', 'rtorrent_pass', '')
    RTORRENT_LABEL = check_setting('str', 'RTORRENT', 'rtorrent_label', '')
    RTORRENT_DIR = check_setting('str', 'RTORRENT', 'rtorrent_dir', '')

    UTORRENT_HOST = check_setting('str', 'UTORRENT', 'utorrent_host', '')
    UTORRENT_PORT = check_setting('int', 'UTORRENT', 'utorrent_port', 0)
    UTORRENT_USER = check_setting('str', 'UTORRENT', 'utorrent_user', '')
    UTORRENT_PASS = check_setting('str', 'UTORRENT', 'utorrent_pass', '')
    UTORRENT_LABEL = check_setting('str', 'UTORRENT', 'utorrent_label', '')

    QBITTORRENT_HOST = check_setting('str', 'QBITTORRENT', 'qbittorrent_host', '')
    QBITTORRENT_PORT = check_setting('int', 'QBITTORRENT', 'qbittorrent_port', 0)
    QBITTORRENT_USER = check_setting('str', 'QBITTORRENT', 'qbittorrent_user', '')
    QBITTORRENT_PASS = check_setting('str', 'QBITTORRENT', 'qbittorrent_pass', '')
    QBITTORRENT_LABEL = check_setting('str', 'QBITTORRENT', 'qbittorrent_label', '')

    TRANSMISSION_HOST = check_setting('str', 'TRANSMISSION', 'transmission_host', '')
    TRANSMISSION_PORT = check_setting('int', 'TRANSMISSION', 'transmission_port', 0)
    TRANSMISSION_USER = check_setting('str', 'TRANSMISSION', 'transmission_user', '')
    TRANSMISSION_PASS = check_setting('str', 'TRANSMISSION', 'transmission_pass', '')

    DELUGE_HOST = check_setting('str', 'DELUGE', 'deluge_host', '')
    DELUGE_PORT = check_setting('int', 'DELUGE', 'deluge_port', 0)
    DELUGE_USER = check_setting('str', 'DELUGE', 'deluge_user', '')
    DELUGE_PASS = check_setting('str', 'DELUGE', 'deluge_pass', '')
    DELUGE_LABEL = check_setting('str', 'DELUGE', 'deluge_label', '')

    SYNOLOGY_HOST = check_setting('str', 'SYNOLOGY', 'synology_host', '')
    SYNOLOGY_PORT = check_setting('int', 'SYNOLOGY', 'synology_port', 0)
    SYNOLOGY_USER = check_setting('str', 'SYNOLOGY', 'synology_user', '')
    SYNOLOGY_PASS = check_setting('str', 'SYNOLOGY', 'synology_pass', '')
    SYNOLOGY_DIR = check_setting('str', 'SYNOLOGY', 'synology_dir', 'Multimedia/Download')
    USE_SYNOLOGY = check_setting('bool', 'SYNOLOGY', 'use_synology', 0)

    KAT = check_setting('bool', 'KAT', 'kat', 0)
    KAT_HOST = check_setting('str', 'KAT', 'kat_host', 'kickass.cd')
    TPB = check_setting('bool', 'TPB', 'tpb', 0)
    TPB_HOST = check_setting('str', 'TPB', 'tpb_host', 'https://piratebays.co')
    ZOO = check_setting('bool', 'ZOO', 'zoo', 0)
    ZOO_HOST = check_setting('str', 'ZOO', 'zoo_host', 'https://zooqle.com')
    EXTRA = check_setting('bool', 'EXTRA', 'extra', 0)
    EXTRA_HOST = check_setting('str', 'EXTRA', 'extra_host', 'extratorrent.cc')
    TDL = check_setting('bool', 'TDL', 'tdl', 0)
    TDL_HOST = check_setting('str', 'TDL', 'tdl_host', 'torrentdownloads.me')
    GEN = check_setting('bool', 'GEN', 'gen', 0)
    GEN_HOST = check_setting('str', 'GEN', 'gen_host', 'libgen.io')
    LIME = check_setting('bool', 'LIME', 'lime', 0)
    LIME_HOST = check_setting('str', 'LIME', 'lime_host', 'https://www.limetorrents.cc')

    NEWZBIN = check_setting('bool', 'Newzbin', 'newzbin', 0)
    NEWZBIN_UID = check_setting('str', 'Newzbin', 'newzbin_uid', '')
    NEWZBIN_PASS = check_setting('str', 'Newzbin', 'newzbin_pass', '')
    EBOOK_TYPE = check_setting('str', 'General', 'ebook_type', 'epub, mobi, pdf')
    MAG_TYPE = check_setting('str', 'General', 'mag_type', 'pdf')
    REJECT_WORDS = check_setting('str', 'General', 'reject_words', 'audiobook, mp3')
    REJECT_MAXSIZE = check_setting('int', 'General', 'reject_maxsize', 0)
    REJECT_MAGSIZE = check_setting('int', 'General', 'reject_magsize', 0)
    MAG_AGE = check_setting('int', 'General', 'mag_age', 31)

    SEARCH_INTERVAL = check_setting('int', 'SearchScan', 'search_interval', '360')
    SCAN_INTERVAL = check_setting('int', 'SearchScan', 'scan_interval', '10')
    SEARCHRSS_INTERVAL = check_setting('int', 'SearchScan', 'searchrss_interval', '20')
    VERSIONCHECK_INTERVAL = check_setting('int', 'SearchScan', 'versioncheck_interval', '24')

    FULL_SCAN = check_setting('bool', 'LibraryScan', 'full_scan', 0)
    ADD_AUTHOR = check_setting('bool', 'LibraryScan', 'add_author', 1)
    NOTFOUND_STATUS = check_setting('str', 'LibraryScan', 'notfound_status', 'Skipped')
    NEWBOOK_STATUS = check_setting('str', 'LibraryScan', 'newbook_status', 'Skipped')
    NEWAUTHOR_STATUS = check_setting('str', 'LibraryScan', 'newauthor_status', 'Skipped')

    EBOOK_DEST_FOLDER = check_setting('str', 'PostProcess', 'ebook_dest_folder', '$Author/$Title')
    EBOOK_DEST_FILE = check_setting('str', 'PostProcess', 'ebook_dest_file', '$Title - $Author')
    ONE_FORMAT = check_setting('bool', 'PostProcess', 'one_format', 0)
    MAG_DEST_FOLDER = check_setting('str', 'PostProcess', 'mag_dest_folder', '_Magazines/$Title/$IssueDate')
    MAG_DEST_FILE = check_setting('str', 'PostProcess', 'mag_dest_file', '$IssueDate - $Title')
    MAG_RELATIVE = check_setting('bool', 'PostProcess', 'mag_relative', 1)

    USE_TWITTER = check_setting('bool', 'Twitter', 'use_twitter', 0)
    TWITTER_NOTIFY_ONSNATCH = check_setting('bool', 'Twitter', 'twitter_notify_onsnatch', 0)
    TWITTER_NOTIFY_ONDOWNLOAD = check_setting('bool', 'Twitter', 'twitter_notify_ondownload', 0)
    TWITTER_USERNAME = check_setting('str', 'Twitter', 'twitter_username', '')
    TWITTER_PASSWORD = check_setting('str', 'Twitter', 'twitter_password', '')
    TWITTER_PREFIX = check_setting('str', 'Twitter', 'twitter_prefix', 'LazyLibrarian')

    USE_BOXCAR = check_setting('bool', 'Boxcar', 'use_boxcar', 0)
    BOXCAR_NOTIFY_ONSNATCH = check_setting('bool', 'Boxcar', 'boxcar_notify_onsnatch', 0)
    BOXCAR_NOTIFY_ONDOWNLOAD = check_setting('bool', 'Boxcar', 'boxcar_notify_ondownload', 0)
    BOXCAR_TOKEN = check_setting('str', 'Boxcar', 'boxcar_token', '')

    USE_PUSHBULLET = check_setting('bool', 'Pushbullet', 'use_pushbullet', 0)
    PUSHBULLET_NOTIFY_ONSNATCH = check_setting('bool', 'Pushbullet', 'pushbullet_notify_onsnatch', 0)
    PUSHBULLET_NOTIFY_ONDOWNLOAD = check_setting('bool', 'Pushbullet', 'pushbullet_notify_ondownload', 0)
    PUSHBULLET_TOKEN = check_setting('str', 'Pushbullet', 'pushbullet_token', '')
    PUSHBULLET_DEVICEID = check_setting('str', 'Pushbullet', 'pushbullet_deviceid', '')

    USE_PUSHOVER = check_setting('bool', 'Pushover', 'use_pushover', 0)
    PUSHOVER_ONSNATCH = check_setting('bool', 'Pushover', 'pushover_onsnatch', 0)
    PUSHOVER_ONDOWNLOAD = check_setting('bool', 'Pushover', 'pushover_ondownload', 0)
    PUSHOVER_KEYS = check_setting('str', 'Pushover', 'pushover_keys', '')
    PUSHOVER_APITOKEN = check_setting('str', 'Pushover', 'pushover_apitoken', '')
    PUSHOVER_PRIORITY = check_setting('int', 'Pushover', 'pushover_priority', 0)
    PUSHOVER_DEVICE = check_setting('str', 'Pushover', 'pushover_device', '')

    USE_ANDROIDPN = check_setting('bool', 'AndroidPN', 'use_androidpn', 0)
    ANDROIDPN_NOTIFY_ONSNATCH = check_setting('bool', 'AndroidPN', 'androidpn_notify_onsnatch', 0)
    ANDROIDPN_NOTIFY_ONDOWNLOAD = check_setting('bool', 'AndroidPN', 'androidpn_notify_ondownload', 0)
    ANDROIDPN_URL = check_setting('str', 'AndroidPN', 'androidpn_url', '')
    ANDROIDPN_USERNAME = check_setting('str', 'AndroidPN', 'androidpn_username', '')
    ANDROIDPN_BROADCAST = check_setting('bool', 'AndroidPN', 'androidpn_broadcast', 0)

    USE_NMA = check_setting('bool', 'NMA', 'use_nma', 0)
    NMA_APIKEY = check_setting('str', 'NMA', 'nma_apikey', '')
    NMA_PRIORITY = check_setting('int', 'NMA', 'nma_priority', 0)
    NMA_ONSNATCH = check_setting('bool', 'NMA', 'nma_onsnatch', 0)
    NMA_ONDOWNLOAD = check_setting('bool', 'NMA', 'nma_ondownload', 0)

    USE_SLACK = check_setting('bool', 'Slack', 'use_slack', 0)
    SLACK_NOTIFY_ONSNATCH = check_setting('bool', 'Slack', 'slack_notify_onsnatch', 0)
    SLACK_NOTIFY_ONDOWNLOAD = check_setting('bool', 'Slack', 'slack_notify_ondownload', 0)
    SLACK_TOKEN = check_setting('str', 'Slack', 'slack_token', '')

    USE_EMAIL = check_setting('bool', 'Email', 'use_email', 0)
    EMAIL_NOTIFY_ONSNATCH = check_setting('bool', 'Email', 'email_notify_onsnatch', 0)
    EMAIL_NOTIFY_ONDOWNLOAD = check_setting('bool', 'Email', 'email_notify_ondownload', 0)
    EMAIL_FROM = check_setting('str', 'Email', 'email_from', '')
    EMAIL_TO = check_setting('str', 'Email', 'email_to', '')
    EMAIL_SSL = check_setting('bool', 'Email', 'email_ssl', 0)
    EMAIL_SMTP_SERVER = check_setting('str', 'Email', 'email_smtp_server', '')
    EMAIL_SMTP_PORT = check_setting('int', 'Email', 'email_smtp_port', 25)
    EMAIL_TLS = check_setting('bool', 'Email', 'email_tls', 0)
    EMAIL_SMTP_USER = check_setting('str', 'Email', 'email_smtp_user', '')
    EMAIL_SMTP_PASSWORD = check_setting('str', 'Email', 'email_smtp_password', '')

    BOOK_API = check_setting('str', 'API', 'book_api', 'GoodReads')
    GR_API = check_setting('str', 'API', 'gr_api', 'ckvsiSDsuqh7omh74ZZ6Q')
    GB_API = check_setting('str', 'API', 'gb_api', '')


    NEWZNAB_PROV = []
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
                             "ENABLED": check_setting('bool', newz_name, 'enabled', 0),
                             "HOST": check_setting('str', newz_name, 'host', ''),
                             "API": check_setting('str', newz_name, 'api', ''),
                             "GENERALSEARCH": check_setting('str', newz_name, 'generalsearch', 'search'),
                             "BOOKSEARCH": check_setting('str', newz_name, 'booksearch', 'book'),
                             "MAGSEARCH": check_setting('str', newz_name, 'magsearch', ''),
                             "BOOKCAT": check_setting('str', newz_name, 'bookcat', '7000,7020'),
                             "MAGCAT": check_setting('str', newz_name, 'magcat', '7010'),
                             "EXTENDED": check_setting('str', newz_name, 'extended', '1'),
                             "UPDATED": check_setting('str', newz_name, 'updated', ''),
                             "MANUAL": check_setting('bool', newz_name, 'manual', 0)
                             })
        count += 1
    # if the last slot is full, add an empty one on the end
    add_newz_slot()

    TORZNAB_PROV = []
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
                             "ENABLED": check_setting('bool', torz_name, 'enabled', 0),
                             "HOST": check_setting('str', torz_name, 'host', ''),
                             "API": check_setting('str', torz_name, 'api', ''),
                             "GENERALSEARCH": check_setting('str', torz_name, 'generalsearch', 'search'),
                             "BOOKSEARCH": check_setting('str', torz_name, 'booksearch', 'book'),
                             "MAGSEARCH": check_setting('str', torz_name, 'magsearch', ''),
                             "BOOKCAT": check_setting('str', torz_name, 'bookcat', '8000,8010'),
                             "MAGCAT": check_setting('str', torz_name, 'magcat', '8030'),
                             "EXTENDED": check_setting('str', torz_name, 'extended', '1'),
                             "UPDATED": check_setting('str', torz_name, 'updated', ''),
                             "MANUAL": check_setting('bool', torz_name, 'manual', 0)
                             })
        count += 1
    # if the last slot is full, add an empty one on the end
    add_torz_slot()

    RSS_PROV = []
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
            # CFG.set(rss_name, 'USER', CFG.get(rss_name, 'rss_user%i' % count))
            CFG.remove_option(rss_name, 'rss_user%i' % count)
        if CFG.has_option(rss_name, 'rss_pass%i' % count):
            # CFG.set(rss_name, 'PASS', CFG.get(rss_name, 'rss_pass%i' % count))
            CFG.remove_option(rss_name, 'rss_pass%i' % count)
        if CFG.has_option(rss_name, 'PASS'):
            CFG.remove_option(rss_name, 'PASS')
        if CFG.has_option(rss_name, 'USER'):
            CFG.remove_option(rss_name, 'USER')

        RSS_PROV.append({"NAME": rss_name,
                         "ENABLED": check_setting('bool', rss_name, 'ENABLED', 0),
                         "HOST": check_setting('str', rss_name, 'HOST', '')
                         })
        count += 1
    # if the last slot is full, add an empty one on the end
    add_rss_slot()

    if HTTP_PORT < 21 or HTTP_PORT > 65535:
        HTTP_PORT = 5299

    # to make extension matching easier
    EBOOK_TYPE = EBOOK_TYPE.lower()
    MAG_TYPE = MAG_TYPE.lower()
    REJECT_WORDS = REJECT_WORDS.lower()

    if reloaded:
        logger.info('Config file reloaded')
    else:
        logger.info('Config file loaded')


# noinspection PyUnresolvedReferences,PyTypeChecker,PyTypeChecker
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
    CFG.set('General', 'logdir', LOGDIR.encode(SYS_ENCODING))
    CFG.set('General', 'loglimit', LOGLIMIT)
    CFG.set('General', 'loglevel', LOGLEVEL)
    CFG.set('General', 'logsize', LOGSIZE)
    CFG.set('General', 'logfiles', LOGFILES)
    CFG.set('General', 'match_ratio', MATCH_RATIO)
    CFG.set('General', 'dload_ratio', DLOAD_RATIO)
    CFG.set('General', 'imp_onlyisbn', IMP_ONLYISBN)
    CFG.set('General', 'imp_singlebook', IMP_SINGLEBOOK)
    CFG.set('General', 'imp_preflang', IMP_PREFLANG)
    CFG.set('General', 'imp_monthlang', IMP_MONTHLANG)
    CFG.set('General', 'imp_autoadd', IMP_AUTOADD)
    CFG.set('General', 'imp_autosearch', IMP_AUTOSEARCH)
    CFG.set('General', 'imp_calibredb', IMP_CALIBREDB)
    CFG.set('General', 'imp_convert', IMP_CONVERT.strip())
    CFG.set('General', 'git_program', GIT_PROGRAM.strip())
    CFG.set('General', 'ebook_type', EBOOK_TYPE.lower())
    CFG.set('General', 'mag_type', MAG_TYPE.lower())
    CFG.set('General', 'reject_words', REJECT_WORDS.encode(SYS_ENCODING).lower())
    CFG.set('General', 'reject_maxsize', REJECT_MAXSIZE)
    CFG.set('General', 'reject_magsize', REJECT_MAGSIZE)
    CFG.set('General', 'mag_age', MAG_AGE)
    CFG.set('General', 'destination_dir', DESTINATION_DIR.encode(SYS_ENCODING))
    CFG.set('General', 'alternate_dir', ALTERNATE_DIR.encode(SYS_ENCODING))
    CFG.set('General', 'download_dir', DOWNLOAD_DIR.encode(SYS_ENCODING))
    CFG.set('General', 'cache_age', CACHE_AGE)
    CFG.set('General', 'task_age', TASK_AGE)
    CFG.set('General', 'destination_copy', DESTINATION_COPY)
    CFG.set('General', 'mag_single', MAG_SINGLE)
    #
    CFG.set('General', 'displaylength', DISPLAYLENGTH)
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
    CFG.set('USENET', 'nzb_downloader_synology', NZB_DOWNLOADER_SYNOLOGY)
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
    check_section('Newzbin')
    CFG.set('Newzbin', 'newzbin', NEWZBIN)
    CFG.set('Newzbin', 'newzbin_uid', NEWZBIN_UID)
    CFG.set('Newzbin', 'newzbin_pass', NEWZBIN_PASS)
    #
    check_section('TORRENT')
    CFG.set('TORRENT', 'tor_downloader_blackhole', TOR_DOWNLOADER_BLACKHOLE)
    CFG.set('TORRENT', 'tor_convert_magnet', TOR_CONVERT_MAGNET)
    CFG.set('TORRENT', 'tor_downloader_utorrent', TOR_DOWNLOADER_UTORRENT)
    CFG.set('TORRENT', 'tor_downloader_rtorrent', TOR_DOWNLOADER_RTORRENT)
    CFG.set('TORRENT', 'tor_downloader_qbittorrent', TOR_DOWNLOADER_QBITTORRENT)
    CFG.set('TORRENT', 'tor_downloader_transmission', TOR_DOWNLOADER_TRANSMISSION)
    CFG.set('TORRENT', 'tor_downloader_synology', TOR_DOWNLOADER_SYNOLOGY)
    CFG.set('TORRENT', 'tor_downloader_deluge', TOR_DOWNLOADER_DELUGE)
    CFG.set('TORRENT', 'numberofseeders', NUMBEROFSEEDERS)
    CFG.set('TORRENT', 'torrent_dir', TORRENT_DIR)
    CFG.set('TORRENT', 'keep_seeding', KEEP_SEEDING)
    CFG.set('TORRENT', 'prefer_magnet', PREFER_MAGNET)
    #
    check_section('RTORRENT')
    CFG.set('RTORRENT', 'rtorrent_host', RTORRENT_HOST)
    CFG.set('RTORRENT', 'rtorrent_user', RTORRENT_USER)
    CFG.set('RTORRENT', 'rtorrent_pass', RTORRENT_PASS)
    CFG.set('RTORRENT', 'rtorrent_label', RTORRENT_LABEL)
    CFG.set('RTORRENT', 'rtorrent_dir', RTORRENT_DIR)
    #
    check_section('UTORRENT')
    CFG.set('UTORRENT', 'utorrent_host', UTORRENT_HOST)
    CFG.set('UTORRENT', 'utorrent_port', UTORRENT_PORT)
    CFG.set('UTORRENT', 'utorrent_user', UTORRENT_USER)
    CFG.set('UTORRENT', 'utorrent_pass', UTORRENT_PASS)
    CFG.set('UTORRENT', 'utorrent_label', UTORRENT_LABEL)
    #
    check_section('SYNOLOGY')
    CFG.set('SYNOLOGY', 'synology_host', SYNOLOGY_HOST)
    CFG.set('SYNOLOGY', 'synology_port', SYNOLOGY_PORT)
    CFG.set('SYNOLOGY', 'synology_user', SYNOLOGY_USER)
    CFG.set('SYNOLOGY', 'synology_pass', SYNOLOGY_PASS)
    CFG.set('SYNOLOGY', 'synology_dir', SYNOLOGY_DIR)
    CFG.set('SYNOLOGY', 'use_synology', USE_SYNOLOGY)
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
    check_section('TPB')
    CFG.set('TPB', 'tpb', TPB)
    CFG.set('TPB', 'tpb_host', TPB_HOST)
    #
    check_section('ZOO')
    CFG.set('ZOO', 'zoo', ZOO)
    CFG.set('ZOO', 'zoo_host', ZOO_HOST)
    #
    check_section('EXTRA')
    CFG.set('EXTRA', 'extra', EXTRA)
    CFG.set('EXTRA', 'extra_host', EXTRA_HOST)
    #
    check_section('LIME')
    CFG.set('LIME', 'lime', LIME)
    CFG.set('LIME', 'lime_host', LIME_HOST)
    #
    check_section('GEN')
    CFG.set('GEN', 'gen', GEN)
    CFG.set('GEN', 'gen_host', GEN_HOST)
    #
    check_section('TDL')
    CFG.set('TDL', 'tdl', TDL)
    CFG.set('TDL', 'tdl_host', TDL_HOST)
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
    CFG.set('LibraryScan', 'newauthor_status', NEWAUTHOR_STATUS)
    #
    check_section('PostProcess')
    CFG.set('PostProcess', 'ebook_dest_folder', EBOOK_DEST_FOLDER.encode(SYS_ENCODING))
    CFG.set('PostProcess', 'ebook_dest_file', EBOOK_DEST_FILE.encode(SYS_ENCODING))
    CFG.set('PostProcess', 'one_format', ONE_FORMAT)
    CFG.set('PostProcess', 'mag_dest_folder', MAG_DEST_FOLDER.encode(SYS_ENCODING))
    CFG.set('PostProcess', 'mag_dest_file', MAG_DEST_FILE.encode(SYS_ENCODING))
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
    #
    check_section('Slack')
    CFG.set('Slack', 'use_slack', USE_SLACK)
    CFG.set('Slack', 'slack_notify_onsnatch', SLACK_NOTIFY_ONSNATCH)
    CFG.set('Slack', 'slack_notify_ondownload', SLACK_NOTIFY_ONDOWNLOAD)
    CFG.set('Slack', 'slack_token', SLACK_TOKEN)
    #
    check_section('Email')
    CFG.set('Email', 'use_email', USE_EMAIL)
    CFG.set('Email', 'email_notify_onsnatch', EMAIL_NOTIFY_ONSNATCH)
    CFG.set('Email', 'email_notify_ondownload', EMAIL_NOTIFY_ONDOWNLOAD)
    CFG.set('Email', 'email_from', EMAIL_FROM)
    CFG.set('Email', 'email_to', EMAIL_TO)
    CFG.set('Email', 'email_ssl', EMAIL_SSL)
    CFG.set('Email', 'email_smtp_server', EMAIL_SMTP_SERVER)
    CFG.set('Email', 'email_smtp_port', EMAIL_SMTP_PORT)
    CFG.set('Email', 'email_tls', EMAIL_TLS)
    CFG.set('Email', 'email_smtp_user', EMAIL_SMTP_USER)
    CFG.set('Email', 'email_smtp_password', EMAIL_SMTP_PASSWORD)
    #
    for provider in NEWZNAB_PROV:
        check_section(provider['NAME'])
        CFG.set(provider['NAME'], 'ENABLED', provider['ENABLED'])
        oldprovider = check_setting('str', provider['NAME'], 'HOST', '', log=False)
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
        oldprovider = check_setting('str', provider['NAME'], 'HOST', '', log=False)
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
    add_rss_slot()

    with open(CONFIGFILE + '.new', 'wb') as configfile:
        CFG.write(configfile)

    try:
        os.remove(CONFIGFILE + '.bak')
    except OSError as e:
        if e.errno is not 2:  # doesn't exist is ok
            logger.debug('{} {}{} {}'.format('Error deleting backup file:', CONFIGFILE, '.bak', e.strerror))

    try:
        os.rename(CONFIGFILE, CONFIGFILE + '.bak')
    except OSError as e:
        if e.errno is not 2:  # doesn't exist is ok as wouldn't exist until first save
            logger.debug('{} {} {}'.format('Unable to backup config file:', CONFIGFILE, e.strerror))

    try:
        os.rename(CONFIGFILE + '.new', CONFIGFILE)
    except OSError as e:
        logger.debug('{} {} {}'.format('Unable to create new config file:', CONFIGFILE, e.strerror))


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


def DIRECTORY(dirname):
    usedir = ''
    if dirname == "Destination":
        usedir = DESTINATION_DIR
    elif dirname == "Download":
        usedir = DOWNLOAD_DIR
    # elif dirname == "Alternate":
    #    usedir = ALTERNATE_DIR
    else:
        return usedir

    if usedir and os.path.isdir(usedir):
        try:
            with open(os.path.join(usedir, 'll_temp'), 'w') as f:
                f.write('test')
            os.remove(os.path.join(usedir, 'll_temp'))
        except Exception as why:
            logger.warn("%s dir [%s] not usable, using %s: %s" % (dirname, usedir, os.getcwd(), str(why)))
            usedir = os.getcwd()
    else:
        logger.warn("%s dir [%s] not found, using %s" % (dirname, usedir, os.getcwd()))
        usedir = os.getcwd()

    # return directory as unicode so we get unicode results from listdir
    if isinstance(usedir, str):
        usedir = usedir.decode(SYS_ENCODING)
    return usedir


def add_rss_slot():
    count = len(RSS_PROV)
    if count == 0 or len(CFG.get('RSS_%i' % int(count - 1), 'HOST')):
        rss_name = 'RSS_%i' % count
        check_section(rss_name)
        CFG.set(rss_name, 'ENABLED', False)
        CFG.set(rss_name, 'HOST', '')
        # CFG.set(rss_name, 'USER', '')
        # CFG.set(rss_name, 'PASS', '')
        RSS_PROV.append({"NAME": rss_name,
                         "ENABLED": 0,
                         "HOST": ''
                         })


def USE_RSS():
    for provider in RSS_PROV:
        if bool(provider['ENABLED']):
            return True
    return False


def USE_TOR():
    for provider in [KAT, TPB, ZOO, EXTRA, LIME, TDL, GEN]:
        if bool(provider):
            return True
    return False


def build_bookstrap_themes():
    themelist = []
    if not os.path.isdir(os.path.join(PROG_DIR, 'data', 'interfaces', 'bookstrap')):
        return themelist  # return empty if bookstrap interface not installed

    if not internet():
        logger.warn('Build Bookstrap Themes: No internet connection')
        return themelist

    URL = 'http://bootswatch.com/api/3.json'
    result, success = fetchURL(URL, None, False)  # use default headers, no retry

    if not success:
        logger.debug("Error getting bookstrap themes : %s" % result)
        return themelist

    try:
        results = json.loads(result)
        for theme in results['themes']:
            themelist.append(theme['name'].lower())
    except Exception as e:
        # error reading results
        logger.debug('JSON Error reading bookstrap themes, %s' % str(e))

    logger.debug("Bookstrap found %i themes" % len(themelist))
    return themelist


def build_monthtable():
    table = []
    json_file = os.path.join(DATADIR, 'monthnames.json')
    if os.path.isfile(json_file):
        try:
            with open(json_file) as json_data:
                table = json.load(json_data)
            mlist = ''
            # list alternate entries as each language is in twice (long and short month names)
            for item in table[0][::2]:
                mlist += item + ' '
            logger.debug('Loaded monthnames.json : %s' % mlist)
        except Exception as e:
            logger.error('Failed to load monthnames.json, %s' % str(e))

    if not table:
        # Default Month names table to hold long/short month names for multiple languages
        # which we can match against magazine issues
        table = [
                ['en_GB.UTF-8', 'en_GB.UTF-8'],
                ['january', 'jan'],
                ['february', 'feb'],
                ['march', 'mar'],
                ['april', 'apr'],
                ['may', 'may'],
                ['june', 'jun'],
                ['july', 'jul'],
                ['august', 'aug'],
                ['september', 'sep'],
                ['october', 'oct'],
                ['november', 'nov'],
                ['december', 'dec']
                ]

    if len(getList(IMP_MONTHLANG)) == 0:  # any extra languages wanted?
        return table
    try:
        current_locale = locale.setlocale(locale.LC_ALL, '')  # read current state.
        # getdefaultlocale() doesnt seem to work as expected on windows, returns 'None'
        logger.debug('Current locale is %s' % current_locale)
    except locale.Error as e:
        logger.debug("Error getting current locale : %s" % str(e))
        return table

    lang = str(current_locale)
    # check not already loaded, also all english variants and 'C' use the same month names
    if lang in table[0] or ((lang.startswith('en_') or lang == 'C') and 'en_' in str(table[0])):
        logger.debug('Month names for %s already loaded' % lang)
    else:
        logger.debug('Loading month names for %s' % lang)
        table[0].append(lang)
        for f in range(1, 13):
            table[f].append(unaccented(calendar.month_name[f]).lower())
        table[0].append(lang)
        for f in range(1, 13):
            table[f].append(unaccented(calendar.month_abbr[f]).lower().strip('.'))
        logger.info("Added month names for locale [%s], %s, %s ..." % (
            lang, table[1][len(table[1]) - 2], table[1][len(table[1]) - 1]))

    for lang in getList(IMP_MONTHLANG):
        try:
            if lang in table[0] or ((lang.startswith('en_') or lang == 'C') and 'en_' in str(table[0])):
                logger.debug('Month names for %s already loaded' % lang)
            else:
                locale.setlocale(locale.LC_ALL, lang)
                logger.debug('Loading month names for %s' % lang)
                table[0].append(lang)
                for f in range(1, 13):
                    table[f].append(unaccented(calendar.month_name[f]).lower())
                table[0].append(lang)
                for f in range(1, 13):
                    table[f].append(unaccented(calendar.month_abbr[f]).lower().strip('.'))
                locale.setlocale(locale.LC_ALL, current_locale)  # restore entry state
                logger.info("Added month names for locale [%s], %s, %s ..." % (
                    lang, table[1][len(table[1]) - 2], table[1][len(table[1]) - 1]))
        except Exception as e:
            locale.setlocale(locale.LC_ALL, current_locale)  # restore entry state
            logger.warn("Unable to load requested locale [%s] %s" % (lang, str(e)))
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
            except Exception as e:
                logger.warn("Unable to get a list of alternatives, %s" % str(e))
            logger.info("Set locale back to entry state %s" % current_locale)

    #with open(json_file, 'w') as f:
    #    json.dump(table, f)
    return table


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
        logger.error('Could not launch browser: %s' % str(e))


def db_needs_upgrade():
    """
    Check if database needs upgrading
    Return zero if up-to-date
    Return current version if needs upgrade
    """

    myDB = database.DBConnection()
    result = myDB.match('PRAGMA user_version')
    # Had a report of "index out of range", can't replicate it.
    # Maybe on some versions of sqlite an unset user_version
    # or unsupported pragma gives an empty result?
    if result:
        db_version = result[0]
    else:
        db_version = 0

    # database version history:
    # 0 original version or new empty database
    # 1 changes up to June 2016
    # 2 removed " MB" from nzbsize field in wanted table
    # 3 removed SeriesOrder column from books table as redundant
    # 4 added duplicates column to stats table
    # 5 issue numbers padded to 4 digits with leading zeros
    # 6 added Manual field to books table for user editing
    # 7 added Source and DownloadID to wanted table for download monitoring
    # 8 move image cache from data/images/cache into datadir
    # 9 add regex to magazine table
    # 10 check for missing columns in pastissues table
    # 11 Keep most recent book image in author table
    # 12 Keep latest issue cover in magazine table
    # 13 add Manual column to author table for user editing

    db_current_version = 13
    if db_version < db_current_version:
        return db_current_version
    return 0


def start():
    global __INITIALIZED__, started

    if __INITIALIZED__:
        # Crons and scheduled jobs started here
        SCHED.start()
        if not UPDATE_MSG:
            restartJobs(start='Start')
            started = True


def shutdown(restart=False, update=False):
    cherrypy.engine.exit()
    SCHED.shutdown(wait=False)
    # config_write() don't automatically rewrite config on exit

    if not restart and not update:
        logger.info('LazyLibrarian is shutting down...')
    if update:
        logger.info('LazyLibrarian is updating...')
        try:
            versioncheck.update()
        except Exception as e:
            logger.warn('LazyLibrarian failed to update: %s. Restarting.' % str(e))

    if PIDFILE:
        logger.info('Removing pidfile %s' % PIDFILE)
        os.remove(PIDFILE)

    if restart:
        logger.info('LazyLibrarian is restarting ...')
        popen_list = [sys.executable, FULL_PATH]
        popen_list += ARGS
        if '--update' in popen_list:
            popen_list.remove('--update')
        if '--nolaunch' not in popen_list:
            popen_list += ['--nolaunch']
            logger.info('Restarting LazyLibrarian with ' + str(popen_list))
        subprocess.Popen(popen_list, cwd=os.getcwd())

    os._exit(0)
