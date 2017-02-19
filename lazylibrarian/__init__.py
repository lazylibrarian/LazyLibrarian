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

# Transient globals NOT stored in config
# These are used/modified by LazyLibrarian.py before config.ini is read
FULL_PATH = None
PROG_DIR = None
ARGS = None
DAEMON = False
SIGNAL = None
PIDFILE = ''
DATADIR = ''
CONFIGFILE = ''
SYS_ENCODING = ''
LOGLEVEL = 1
CONFIG = {}
CFG = ''
DBFILE = None
COMMIT_LIST = None

# These are only used in startup
SCHED = Scheduler()
INIT_LOCK = threading.Lock()
__INITIALIZED__ = False
started = False

# Transients used by logger process
LOGLIST = []
LOGFULL = True

# These are transient globals
UPDATE_MSG = ''
CURRENT_TAB = '1'
CACHE_HIT = 0
CACHE_MISS = 0
LAST_GOODREADS = 0
LAST_LIBRARYTHING = 0
MONTHNAMES = []
CACHEDIR = ''
NEWZNAB_PROV = []
TORZNAB_PROV = []
RSS_PROV = []
BOOKSTRAP_THEMELIST = []
# Shared dictionaries
isbn_979_dict = {
    "10": "fre",
    "11": "kor",
    "12": "ita"
}
isbn_978_dict = {
    "0": "eng",
    "1": "eng",
    "2": "fre",
    "3": "ger",
    "4": "jap",
    "5": "rus",
    "7": "chi",
    "80": "cze",
    "82": "pol",
    "83": "nor",
    "84": "spa",
    "85": "bra",
    "87": "den",
    "88": "ita",
    "89": "kor",
    "91": "swe",
    "93": "ind"
}
# These are the items in config.ini
# Not all are accessible from the web ui
# Any undefined on startup will be set to the default value
# Any _NOT_ in the web ui will remain unchanged on config save
CONFIG_DEFINITIONS = {
    # Name      Type   Section   Default
    'LOGDIR': ('str', 'General', ''),
    'LOGLIMIT': ('int', 'General', 500),
    'LOGFILES': ('int', 'General', 10),
    'LOGSIZE': ('int', 'General', 204800),
    'LOGLEVEL': ('int', 'General', 1),
    'MATCH_RATIO': ('int', 'General', 80),
    'DLOAD_RATIO': ('int', 'General', 90),
    'DISPLAYLENGTH': ('int', 'General', 10),
    'HTTP_PORT': ('int', 'General', 5299),
    'HTTP_HOST': ('str', 'General', '0.0.0.0'),
    'HTTP_USER': ('str', 'General', ''),
    'HTTP_PASS': ('str', 'General', ''),
    'HTTP_PROXY': ('bool', 'General', 0),
    'HTTP_ROOT': ('str', 'General', ''),
    'HTTP_LOOK': ('str', 'General', 'default'),
    'HTTPS_ENABLED': ('bool', 'General', 0),
    'HTTPS_CERT': ('str', 'General', ''),
    'HTTPS_KEY': ('str', 'General', ''),
    'BOOKSTRAP_THEME': ('str', 'General', 'slate'),
    'MAG_SINGLE': ('bool', 'General', 1),
    'LAUNCH_BROWSER': ('bool', 'General', 1),
    'API_ENABLED': ('bool', 'General', 0),
    'API_KEY': ('str', 'General', ''),
    'PROXY_HOST': ('str', 'General', ''),
    'PROXY_TYPE': ('str', 'General', ''),
    'NAME_POSTFIX':('str', 'General', 'snr, jnr, jr, sr, phd'),
    'IMP_PREFLANG': ('str', 'General', 'en, eng, en-US, en-GB'),
    'IMP_MONTHLANG': ('str', 'General', ''),
    'IMP_AUTOADD': ('str', 'General', ''),
    'IMP_AUTOSEARCH': ('bool', 'General', 0),
    'IMP_CALIBREDB': ('str', 'General', ''),
    'IMP_ONLYISBN': ('bool', 'General', 0),
    'IMP_SINGLEBOOK': ('bool', 'General', 0),
    'IMP_CONVERT': ('str', 'General', ''),
    'GIT_PROGRAM': ('str', 'General', ''),
    'CACHE_AGE': ('int', 'General', 30),
    'TASK_AGE': ('int', 'General', 0),
    'GIT_USER': ('str', 'Git', 'dobytang'),
    'GIT_REPO': ('str', 'Git', 'lazylibrarian'),
    'GIT_BRANCH': ('str', 'Git', 'master'),
    'INSTALL_TYPE': ('str', 'Git', ''),
    'CURRENT_VERSION': ('str', 'Git', ''),
    'LATEST_VERSION': ('str', 'Git', ''),
    'COMMITS_BEHIND': ('str', 'Git', ''),
    'SAB_HOST': ('str', 'SABnzbd', ''),
    'SAB_PORT': ('int', 'SABnzbd', 0),
    'SAB_SUBDIR': ('str', 'SABnzbd', ''),
    'SAB_USER': ('str', 'SABnzbd', ''),
    'SAB_PASS': ('str', 'SABnzbd', ''),
    'SAB_API': ('str', 'SABnzbd', ''),
    'SAB_CAT': ('str', 'SABnzbd', ''),
    'NZBGET_HOST': ('str', 'NZBGet', ''),
    'NZBGET_PORT': ('int', 'NZBGet', '0'),
    'NZBGET_USER': ('str', 'NZBGet', ''),
    'NZBGET_PASS': ('str', 'NZBGet', ''),
    'NZBGET_CATEGORY': ('str', 'NZBGet', ''),
    'NZBGET_PRIORITY': ('int', 'NZBGet', '0'),
    'DESTINATION_COPY': ('bool', 'General', 0),
    'DESTINATION_DIR': ('str', 'General', ''),
    'ALTERNATE_DIR': ('str', 'General', ''),
    'DOWNLOAD_DIR': ('str', 'General', ''),
    'NZB_DOWNLOADER_SABNZBD': ('bool', 'USENET', 0),
    'NZB_DOWNLOADER_NZBGET': ('bool', 'USENET', 0),
    'NZB_DOWNLOADER_SYNOLOGY': ('bool', 'USENET', 0),
    'NZB_DOWNLOADER_BLACKHOLE': ('bool', 'USENET', 0),
    'NZB_BLACKHOLEDIR': ('str', 'USENET', ''),
    'USENET_RETENTION': ('int', 'USENET', 0),
    'NZBMATRIX_USER': ('str', 'NZBMatrix', ''),
    'NZBMATRIX_API': ('str', 'NZBMatrix', ''),
    'NZBMATRIX': ('bool', 'NZBMatrix', 0),
    'TOR_DOWNLOADER_BLACKHOLE': ('bool', 'TORRENT', 0),
    'TOR_CONVERT_MAGNET': ('bool', 'TORRENT', 0),
    'TOR_DOWNLOADER_UTORRENT': ('bool', 'TORRENT', 0),
    'TOR_DOWNLOADER_RTORRENT': ('bool', 'TORRENT', 0),
    'TOR_DOWNLOADER_QBITTORRENT': ('bool', 'TORRENT', 0),
    'TOR_DOWNLOADER_TRANSMISSION': ('bool', 'TORRENT', 0),
    'TOR_DOWNLOADER_SYNOLOGY': ('bool', 'TORRENT', 0),
    'TOR_DOWNLOADER_DELUGE': ('bool', 'TORRENT', 0),
    'NUMBEROFSEEDERS': ('int', 'TORRENT', 10),
    'KEEP_SEEDING': ('bool', 'TORRENT', 1),
    'PREFER_MAGNET': ('bool', 'TORRENT', 1),
    'TORRENT_DIR': ('str', 'TORRENT', ''),
    'RTORRENT_HOST': ('str', 'RTORRENT', ''),
    'RTORRENT_USER': ('str', 'RTORRENT', ''),
    'RTORRENT_PASS': ('str', 'RTORRENT', ''),
    'RTORRENT_LABEL': ('str', 'RTORRENT', ''),
    'RTORRENT_DIR': ('str', 'RTORRENT', ''),
    'UTORRENT_HOST': ('str', 'UTORRENT', ''),
    'UTORRENT_PORT': ('int', 'UTORRENT', 0),
    'UTORRENT_USER': ('str', 'UTORRENT', ''),
    'UTORRENT_PASS': ('str', 'UTORRENT', ''),
    'UTORRENT_LABEL': ('str', 'UTORRENT', ''),
    'QBITTORRENT_HOST': ('str', 'QBITTORRENT', ''),
    'QBITTORRENT_PORT': ('int', 'QBITTORRENT', 0),
    'QBITTORRENT_USER': ('str', 'QBITTORRENT', ''),
    'QBITTORRENT_PASS': ('str', 'QBITTORRENT', ''),
    'QBITTORRENT_LABEL': ('str', 'QBITTORRENT', ''),
    'TRANSMISSION_HOST': ('str', 'TRANSMISSION', ''),
    'TRANSMISSION_PORT': ('int', 'TRANSMISSION', 0),
    'TRANSMISSION_USER': ('str', 'TRANSMISSION', ''),
    'TRANSMISSION_PASS': ('str', 'TRANSMISSION', ''),
    'DELUGE_HOST': ('str', 'DELUGE', ''),
    'DELUGE_PORT': ('int', 'DELUGE', 0),
    'DELUGE_USER': ('str', 'DELUGE', ''),
    'DELUGE_PASS': ('str', 'DELUGE', ''),
    'DELUGE_LABEL': ('str', 'DELUGE', ''),
    'SYNOLOGY_HOST': ('str', 'SYNOLOGY', ''),
    'SYNOLOGY_PORT': ('int', 'SYNOLOGY', 0),
    'SYNOLOGY_USER': ('str', 'SYNOLOGY', ''),
    'SYNOLOGY_PASS': ('str', 'SYNOLOGY', ''),
    'SYNOLOGY_DIR': ('str', 'SYNOLOGY', 'Multimedia/Download'),
    'USE_SYNOLOGY': ('bool', 'SYNOLOGY', 0),
    'KAT_HOST': ('str', 'KAT', 'kickass.cd'),
    'KAT': ('bool', 'KAT', 0),
    'TPB_HOST': ('str', 'TPB', 'https://piratebays.co'),
    'TPB': ('bool', 'TPB', 0),
    'ZOO_HOST': ('str', 'ZOO', 'https://zooqle.com'),
    'ZOO': ('bool', 'ZOO', 0),
    'EXTRA_HOST': ('str', 'EXTRA', 'extratorrent.cc'),
    'EXTRA': ('bool', 'EXTRA', 0),
    'TDL_HOST': ('str', 'TDL', 'torrentdownloads.me'),
    'TDL': ('bool', 'TDL', 0),
    'GEN_HOST': ('str', 'GEN', 'libgen.io'),
    'GEN': ('bool', 'GEN', 0),
    'LIME_HOST': ('str', 'LIME', 'https://www.limetorrents.cc'),
    'LIME': ('bool', 'LIME', 0),
    'NEWZBIN_UID': ('str', 'Newzbin', ''),
    'NEWZBIN_PASS': ('str', 'Newzbin', ''),
    'NEWZBIN': ('bool', 'Newzbin', 0),
    'EBOOK_TYPE': ('str', 'General', 'epub, mobi, pdf'),
    'MAG_TYPE': ('str', 'General', 'pdf'),
    'REJECT_WORDS': ('str', 'General', 'audiobook, mp3'),
    'REJECT_MAXSIZE': ('int', 'General', 0),
    'REJECT_MAGSIZE': ('int', 'General', 0),
    'MAG_AGE': ('int', 'General', 31),
    'SEARCH_INTERVAL': ('int', 'SearchScan', '360'),
    'SCAN_INTERVAL': ('int', 'SearchScan', '10'),
    'SEARCHRSS_INTERVAL': ('int', 'SearchScan', '20'),
    'VERSIONCHECK_INTERVAL': ('int', 'SearchScan', '24'),
    'FULL_SCAN': ('bool', 'LibraryScan', 0),
    'ADD_AUTHOR': ('bool', 'LibraryScan', 1),
    'NOTFOUND_STATUS': ('str', 'LibraryScan', 'Skipped'),
    'NEWBOOK_STATUS': ('str', 'LibraryScan', 'Skipped'),
    'NEWAUTHOR_STATUS': ('str', 'LibraryScan', 'Skipped'),
    'EBOOK_DEST_FOLDER': ('str', 'PostProcess', '$Author/$Title'),
    'EBOOK_DEST_FILE': ('str', 'PostProcess', '$Title - $Author'),
    'ONE_FORMAT': ('bool', 'PostProcess', 0),
    'MAG_DEST_FOLDER': ('str', 'PostProcess', '_Magazines/$Title/$IssueDate'),
    'MAG_DEST_FILE': ('str', 'PostProcess', '$IssueDate - $Title'),
    'MAG_RELATIVE': ('bool', 'PostProcess', 1),
    'USE_TWITTER': ('bool', 'Twitter', 0),
    'TWITTER_NOTIFY_ONSNATCH': ('bool', 'Twitter', 0),
    'TWITTER_NOTIFY_ONDOWNLOAD': ('bool', 'Twitter', 0),
    'TWITTER_USERNAME': ('str', 'Twitter', ''),
    'TWITTER_PASSWORD': ('str', 'Twitter', ''),
    'TWITTER_PREFIX': ('str', 'Twitter', 'LazyLibrarian'),
    'USE_BOXCAR': ('bool', 'Boxcar', 0),
    'BOXCAR_NOTIFY_ONSNATCH': ('bool', 'Boxcar', 0),
    'BOXCAR_NOTIFY_ONDOWNLOAD': ('bool', 'Boxcar', 0),
    'BOXCAR_TOKEN': ('str', 'Boxcar', ''),
    'USE_PUSHBULLET': ('bool', 'Pushbullet', 0),
    'PUSHBULLET_NOTIFY_ONSNATCH': ('bool', 'Pushbullet', 0),
    'PUSHBULLET_NOTIFY_ONDOWNLOAD': ('bool', 'Pushbullet', 0),
    'PUSHBULLET_TOKEN': ('str', 'Pushbullet', ''),
    'PUSHBULLET_DEVICEID': ('str', 'Pushbullet', ''),
    'USE_PUSHOVER': ('bool', 'Pushover', 0),
    'PUSHOVER_ONSNATCH': ('bool', 'Pushover', 0),
    'PUSHOVER_ONDOWNLOAD': ('bool', 'Pushover', 0),
    'PUSHOVER_KEYS': ('str', 'Pushover', ''),
    'PUSHOVER_APITOKEN': ('str', 'Pushover', ''),
    'PUSHOVER_PRIORITY': ('int', 'Pushover', 0),
    'PUSHOVER_DEVICE': ('str', 'Pushover', ''),
    'USE_ANDROIDPN': ('bool', 'AndroidPN', 0),
    'ANDROIDPN_NOTIFY_ONSNATCH': ('bool', 'AndroidPN', 0),
    'ANDROIDPN_NOTIFY_ONDOWNLOAD': ('bool', 'AndroidPN', 0),
    'ANDROIDPN_URL': ('str', 'AndroidPN', ''),
    'ANDROIDPN_USERNAME': ('str', 'AndroidPN', ''),
    'ANDROIDPN_BROADCAST': ('bool', 'AndroidPN', 0),
    'USE_NMA': ('bool', 'NMA', 0),
    'NMA_APIKEY': ('str', 'NMA', ''),
    'NMA_PRIORITY': ('int', 'NMA', 0),
    'NMA_ONSNATCH': ('bool', 'NMA', 0),
    'NMA_ONDOWNLOAD': ('bool', 'NMA', 0),
    'USE_SLACK': ('bool', 'Slack', 0),
    'SLACK_NOTIFY_ONSNATCH': ('bool', 'Slack', 0),
    'SLACK_NOTIFY_ONDOWNLOAD': ('bool', 'Slack', 0),
    'SLACK_TOKEN': ('str', 'Slack', ''),
    'USE_EMAIL': ('bool', 'Email', 0),
    'EMAIL_NOTIFY_ONSNATCH': ('bool', 'Email', 0),
    'EMAIL_NOTIFY_ONDOWNLOAD': ('bool', 'Email', 0),
    'EMAIL_FROM': ('str', 'Email', ''),
    'EMAIL_TO': ('str', 'Email',''),
    'EMAIL_SSL': ('bool', 'Email', 0),
    'EMAIL_SMTP_SERVER': ('str', 'Email', ''),
    'EMAIL_SMTP_PORT': ('int', 'Email', 25),
    'EMAIL_TLS': ('bool', 'Email', 0),
    'EMAIL_SMTP_USER': ('str', 'Email', ''),
    'EMAIL_SMTP_PASSWORD': ('str', 'Email', ''),
    'BOOK_API': ('str', 'API', 'GoodReads'),
    'GR_API': ('str', 'API', 'ckvsiSDsuqh7omh74ZZ6Q'),
    'GB_API': ('str', 'API', '')
}


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
    global FULL_PATH, PROG_DIR, ARGS, DAEMON, SIGNAL, PIDFILE, DATADIR, CONFIGFILE, SYS_ENCODING, LOGLEVEL, \
            CONFIG, CFG, DBFILE, COMMIT_LIST, SCHED, INIT_LOCK, __INITIALIZED__, started, LOGLIST, LOGFULL, \
            UPDATE_MSG, CURRENT_TAB, CACHE_HIT, CACHE_MISS, LAST_LIBRARYTHING, LAST_GOODREADS, \
            CACHEDIR, BOOKSTRAP_THEMELIST, MONTHNAMES, CONFIG_DEFINITIONS, isbn_979_dict, isbn_978_dict

    with INIT_LOCK:

        if __INITIALIZED__:
            return False

        check_section('General')
        # False to silence logging until logger initialised
        CONFIG = {'LOGDIR': check_setting('str', 'General', 'logdir', '', False),
                  'LOGLIMIT': check_setting('int', 'General', 'loglimit', 500, False),
                  'LOGFILES': check_setting('int', 'General', 'logfiles', 10, False),
                  'LOGSIZE': check_setting('int', 'General', 'logsize', 204800, False), 'DATADIR': DATADIR}

        if not CONFIG['LOGDIR']:
            CONFIG['LOGDIR'] = os.path.join(CONFIG['DATADIR'], 'Logs')
        # Create logdir
        if not os.path.exists(CONFIG['LOGDIR']):
            try:
                os.makedirs(CONFIG['LOGDIR'])
            except OSError as e:
                if LOGLEVEL:
                    print '%s : Unable to create folder for logs: %s. Only logging to console.' % (CONFIG['LOGDIR'], str(e))

        # Start the logger, silence console logging if we need to
        CFGLOGLEVEL = check_setting('int', 'General', 'loglevel', 9)
        if LOGLEVEL == 1:  # default if no debug or quiet on cmdline
            if CFGLOGLEVEL == 9:  # default value if none in config
                LOGLEVEL = 2  # If not set in Config or cmdline, then lets set to DEBUG
            else:
                LOGLEVEL = CFGLOGLEVEL  # Config setting picked up

        CONFIG['LOGLEVEL'] = LOGLEVEL
        logger.lazylibrarian_log.initLogger(loglevel=CONFIG['LOGLEVEL'])
        logger.info("Log level set to [%s]- Log Directory is [%s] - Config level is [%s]" % (
            CONFIG['LOGLEVEL'], CONFIG['LOGDIR'], CFGLOGLEVEL))
        if CONFIG['LOGLEVEL'] > 2:
            LOGFULL = True
            logger.info("Screen Log set to DEBUG")
        else:
            LOGFULL = False
            logger.info("Screen Log set to INFO/WARN/ERROR")

        config_read()
        logger.info('SYS_ENCODING is %s' % SYS_ENCODING)

        # Put the cache dir in the data dir for now
        CACHEDIR = os.path.join(CONFIG['DATADIR'], 'cache')
        if not os.path.exists(CACHEDIR):
            try:
                os.makedirs(CACHEDIR)
            except OSError:
                logger.error('Could not create cachedir. Check permissions of: ' + CONFIG['DATADIR'])

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
    global CONFIG, CONFIG_DEFINITIONS, NEWZNAB_PROV, TORZNAB_PROV, RSS_PROV

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

    for key in CONFIG_DEFINITIONS.keys():
        item_type, section, default = CONFIG_DEFINITIONS[key]
        CONFIG[key.upper()] = check_setting(item_type, section, key.lower(), default)

    if CONFIG['HTTP_PORT'] < 21 or CONFIG ['HTTP_PORT'] > 65535:
        CONFIG['HTTP_PORT'] = 5299

    # to make extension matching easier
    CONFIG['EBOOK_TYPE'] = CONFIG['EBOOK_TYPE'].lower()
    CONFIG['MAG_TYPE'] = CONFIG['MAG_TYPE'].lower()
    CONFIG['REJECT_WORDS'] = CONFIG['REJECT_WORDS'].lower()

    if reloaded:
        logger.info('Config file reloaded')
    else:
        logger.info('Config file loaded')


def config_write():

    for key in CONFIG_DEFINITIONS.keys():
        item_type, section, default = CONFIG_DEFINITIONS[key]
        check_section(section)
        value =  CONFIG[key]
        if key in ['LOGDIR', 'DESTINATION_DIR', 'ALTERNATE_DIR', 'DOWLOAD_DIR',
                    'EBOOK_DEST_FILE', 'EBOOK_DEST_FOLDER', 'MAG_DEST_FILE', 'MAG_DEST_FOLDER']:
            value = value.encode(SYS_ENCODING)
        if key == 'REJECT_WORDS':
            value = value.encode(SYS_ENCODING).lower()

        CFG.set(section, key.lower(), value)

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
        usedir = CONFIG['DESTINATION_DIR']
    elif dirname == "Download":
        usedir = CONFIG['DOWNLOAD_DIR']
    elif dirname == "Alternate":
        usedir = CONFIG['ALTERNATE_DIR']
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
    for provider in [CONFIG['KAT'], CONFIG['TPB'], CONFIG['ZOO'], CONFIG['EXTRA'], CONFIG['LIME'],
                    CONFIG['TDL'], CONFIG['GEN']]:
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
    json_file = os.path.join(CONFIG['DATADIR'], 'monthnames.json')
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

    if len(getList(CONFIG['IMP_MONTHLANG'])) == 0:  # any extra languages wanted?
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

    for lang in getList(CONFIG['IMP_MONTHLANG']):
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
