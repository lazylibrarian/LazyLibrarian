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

import ConfigParser
import calendar
import json
import locale
import os
import platform
import subprocess
import sys
import threading
import time
import webbrowser
import sqlite3

import cherrypy
from lazylibrarian import logger, postprocess, searchbook, searchrss, librarysync, versioncheck, database, \
    searchmag, magazinescan, bookwork, importer, grsync
from lazylibrarian.cache import fetchURL
from lazylibrarian.common import restartJobs, logHeader
from lazylibrarian.formatter import getList, bookSeries, plural, unaccented, check_int
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
LOGTOGGLE = 2  # normal debug

# These are transient globals
UPDATE_MSG = ''
AUTHORUPDATE_MSG = 0
IGNORED_AUTHORS = 0
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
PROVIDER_BLOCKLIST = []
USER_BLOCKLIST = []
SHOW_MAGS = 1
SHOW_SERIES = 1
SHOW_AUDIO = 0
MAG_UPDATE = 0
EBOOK_UPDATE = 0
AUDIO_UPDATE = 0
AUTHORS_UPDATE = 0
LOGIN_MSG = ''
GROUP_CONCAT = 0

# user permissions
perm_config = 1 << 0  # 1 access to config page
perm_logs = 1 << 1  # 2 access to logs
perm_history = 1 << 2  # 4 access to history
perm_managebooks = 1 << 3  # 8 access to manage page
perm_magazines = 1 << 4  # 16 access to magazines/issues/pastissues
perm_audio = 1 << 5  # 32 access to audiobooks page
perm_ebook = 1 << 6  # 64 can access ebooks page
perm_series = 1 << 7  # 128 access to series/seriesmembers
perm_edit = 1 << 8  # 256 can edit book or author details
perm_search = 1 << 9  # 512 can search goodreads/googlebooks for books/authors
perm_status = 1 << 10  # 1024 can change book status (wanted/skipped etc)
perm_force = 1 << 11  # 2048 can use background tasks (refresh authors/libraryscan/postprocess/searchtasks)
perm_download = 1 << 12  # 4096 can download existing books/mags

perm_authorbooks = perm_audio + perm_ebook
perm_guest = perm_download + perm_series + perm_ebook + perm_audio + perm_magazines
perm_friend = perm_guest + perm_search + perm_status
perm_admin = 65535

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
CONFIG_GIT = ['GIT_REPO', 'GIT_USER', 'GIT_BRANCH', 'LATEST_VERSION', 'GIT_UPDATED', 'CURRENT_VERSION',
              'COMMITS_BEHIND', 'INSTALL_TYPE']
CONFIG_NONWEB = ['LOGFILES', 'LOGSIZE', 'NAME_POSTFIX', 'DIR_PERM', 'FILE_PERM', 'BLOCKLIST_TIMER',
                 'WALL_COLUMNS', 'ADMIN_EMAIL']
# default interface does not know about these items, so leave them unchanged
CONFIG_NONDEFAULT = ['BOOKSTRAP_THEME', 'AUDIOBOOK_TYPE', 'AUDIO_DIR', 'AUDIO_TAB', 'REJECT_AUDIO',
                     'REJECT_MAXAUDIO', 'REJECT_MINAUDIO', 'NEWAUDIO_STATUS', 'TOGGLES', 'AUDIO_TAB',
                     'USER_ACCOUNTS', 'GR_SYNC', 'GR_SECRET', 'GR_OAUTH_TOKEN', 'GR_OAUTH_SECRET',
                     'GR_OWNED', 'GR_WANTED', 'GR_FOLLOW', 'GR_FOLLOWNEW', 'GOODREADS_INTERVAL',
                     'AUDIOBOOK_DEST_FILE']
CONFIG_DEFINITIONS = {
    # Name      Type   Section   Default
    'USER_ACCOUNTS': ('bool', 'General', 0),
    'ADMIN_EMAIL': ('str', 'General', ''),
    'LOGDIR': ('str', 'General', ''),
    'LOGLIMIT': ('int', 'General', 500),
    'LOGFILES': ('int', 'General', 10),
    'LOGSIZE': ('int', 'General', 204800),
    'LOGLEVEL': ('int', 'General', 1),
    'WALL_COLUMNS': ('int', 'General', 6),
    'FILE_PERM': ('str', 'General', '0o644'),
    'DIR_PERM': ('str', 'General', '0o755'),
    'BLOCKLIST_TIMER': ('int', 'General', 3600),
    'MAX_PAGES': ('int', 'General', 0),
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
    'AUTHOR_IMG': ('bool', 'General', 1),
    'BOOK_IMG': ('bool', 'General', 1),
    'MAG_IMG': ('bool', 'General', 1),
    'SERIES_TAB': ('bool', 'General', 1),
    'MAG_TAB': ('bool', 'General', 1),
    'AUDIO_TAB': ('bool', 'General', 1),
    'TOGGLES': ('bool', 'General', 1),
    'SORT_DEFINITE': ('bool', 'General', 0),
    'SORT_SURNAME': ('bool', 'General', 0),
    'LAUNCH_BROWSER': ('bool', 'General', 1),
    'API_ENABLED': ('bool', 'General', 0),
    'API_KEY': ('str', 'General', ''),
    'PROXY_HOST': ('str', 'General', ''),
    'PROXY_TYPE': ('str', 'General', ''),
    'NAME_POSTFIX': ('str', 'General', 'snr, jnr, jr, sr, phd'),
    'IMP_PREFLANG': ('str', 'General', 'en, eng, en-US, en-GB'),
    'IMP_MONTHLANG': ('str', 'General', ''),
    'IMP_AUTOADD': ('str', 'General', ''),
    'IMP_AUTOADD_BOOKONLY': ('bool', 'General', 0),
    'IMP_AUTOSEARCH': ('bool', 'General', 0),
    'IMP_CALIBREDB': ('str', 'General', ''),
    'CALIBRE_USE_SERVER': ('bool', 'General', 0),
    'CALIBRE_SERVER': ('str', 'General', ''),
    'CALIBRE_USER': ('str', 'General', ''),
    'CALIBRE_PASS': ('str', 'General', ''),
    'IMP_ONLYISBN': ('bool', 'General', 0),
    'IMP_SINGLEBOOK': ('bool', 'General', 0),
    'IMP_RENAME': ('bool', 'General', 0),
    'IMP_CONVERT': ('str', 'General', ''),
    'GIT_PROGRAM': ('str', 'General', ''),
    'CACHE_AGE': ('int', 'General', 30),
    'TASK_AGE': ('int', 'General', 2),
    'GIT_USER': ('str', 'Git', 'dobytang'),
    'GIT_REPO': ('str', 'Git', 'lazylibrarian'),
    'GIT_BRANCH': ('str', 'Git', 'master'),
    'GIT_UPDATED': ('str', 'Git', ''),
    'INSTALL_TYPE': ('str', 'Git', ''),
    'CURRENT_VERSION': ('str', 'Git', ''),
    'LATEST_VERSION': ('str', 'Git', ''),
    'COMMITS_BEHIND': ('int', 'Git', 0),
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
    'EBOOK_DIR': ('str', 'General', ''),
    'AUDIO_DIR': ('str', 'General', ''),
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
    'KAT_DLPRIORITY': ('int', 'KAT', 0),
    'WWT_HOST': ('str', 'WWT', 'https://worldwidetorrents.eu'),
    'WWT': ('bool', 'WWT', 0),
    'WWT_DLPRIORITY': ('int', 'WWT', 0),
    'TPB_HOST': ('str', 'TPB', 'https://pirateproxy.cc'),
    'TPB': ('bool', 'TPB', 0),
    'TPB_DLPRIORITY': ('int', 'TPB', 0),
    'ZOO_HOST': ('str', 'ZOO', 'https://zooqle.com'),
    'ZOO': ('bool', 'ZOO', 0),
    'ZOO_DLPRIORITY': ('int', 'ZOO', 0),
    # 'EXTRA_HOST': ('str', 'EXTRA', 'extratorrent.cc'),
    # 'EXTRA': ('bool', 'EXTRA', 0),
    # 'EXTRA_DLPRIORITY': ('int', 'EXTRA', 0),
    'TDL_HOST': ('str', 'TDL', 'torrentdownloads.me'),
    'TDL': ('bool', 'TDL', 0),
    'TDL_DLPRIORITY': ('int', 'TDL', 0),
    'GEN_HOST': ('str', 'GEN', 'libgen.io'),
    'GEN_SEARCH': ('str', 'GEN', 'search.php'),
    'GEN': ('bool', 'GEN', 0),
    'GEN_DLPRIORITY': ('int', 'GEN', 0),
    'GEN2_HOST': ('str', 'GEN', 'libgen.io'),
    'GEN2_SEARCH': ('str', 'GEN', 'foreignfiction/index.php'),
    'GEN2': ('bool', 'GEN', 0),
    'GEN2_DLPRIORITY': ('int', 'GEN', 0),
    'LIME_HOST': ('str', 'LIME', 'https://www.limetorrents.cc'),
    'LIME': ('bool', 'LIME', 0),
    'LIME_DLPRIORITY': ('int', 'LIME', 0),
    'NEWZBIN_UID': ('str', 'Newzbin', ''),
    'NEWZBIN_PASS': ('str', 'Newzbin', ''),
    'NEWZBIN': ('bool', 'Newzbin', 0),
    'EBOOK_TYPE': ('str', 'General', 'epub, mobi, pdf'),
    'AUDIOBOOK_TYPE': ('str', 'General', 'mp3'),
    'MAG_TYPE': ('str', 'General', 'pdf'),
    'REJECT_WORDS': ('str', 'General', 'audiobook, mp3'),
    'REJECT_AUDIO': ('str', 'General', 'epub, mobi'),
    'REJECT_MAXSIZE': ('int', 'General', 0),
    'REJECT_MINSIZE': ('int', 'General', 0),
    'REJECT_MAXAUDIO': ('int', 'General', 0),
    'REJECT_MINAUDIO': ('int', 'General', 0),
    'REJECT_MAGSIZE': ('int', 'General', 0),
    'REJECT_MAGMIN': ('int', 'General', 0),
    'MAG_AGE': ('int', 'General', 31),
    'SEARCH_INTERVAL': ('int', 'SearchScan', '360'),
    'SCAN_INTERVAL': ('int', 'SearchScan', '10'),
    'SEARCHRSS_INTERVAL': ('int', 'SearchScan', '20'),
    'VERSIONCHECK_INTERVAL': ('int', 'SearchScan', '24'),
    'GOODREADS_INTERVAL': ('int', 'SearchScan', '48'),
    'FULL_SCAN': ('bool', 'LibraryScan', 0),
    'ADD_AUTHOR': ('bool', 'LibraryScan', 1),
    'ADD_SERIES': ('bool', 'LibraryScan', 1),
    'NOTFOUND_STATUS': ('str', 'LibraryScan', 'Skipped'),
    'NEWBOOK_STATUS': ('str', 'LibraryScan', 'Skipped'),
    'NEWAUDIO_STATUS': ('str', 'LibraryScan', 'Skipped'),
    'NEWAUTHOR_STATUS': ('str', 'LibraryScan', 'Skipped'),
    'NEWAUTHOR_BOOKS': ('bool', 'LibraryScan', 0),
    'NO_FUTURE': ('bool', 'LibraryScan', 0),
    'EBOOK_DEST_FOLDER': ('str', 'PostProcess', '$Author/$Title'),
    'EBOOK_DEST_FILE': ('str', 'PostProcess', '$Title - $Author'),
    'AUDIOBOOK_DEST_FILE': ('str', 'PostProcess', '$Author - $Title: Part $Part of $Total'),
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
    'USE_TELEGRAM': ('bool', 'Telegram', 0),
    'TELEGRAM_TOKEN': ('str', 'Telegram', ''),
    'TELEGRAM_USERID': ('str', 'Telegram', ''),
    'TELEGRAM_ONSNATCH': ('bool', 'Telegram', 0),
    'TELEGRAM_ONDOWNLOAD': ('bool', 'Telegram', 0),
    'USE_PROWL': ('bool', 'Prowl', 0),
    'PROWL_APIKEY': ('str', 'Prowl', ''),
    'PROWL_PRIORITY': ('int', 'Prowl', 0),
    'PROWL_ONSNATCH': ('bool', 'Prowl', 0),
    'PROWL_ONDOWNLOAD': ('bool', 'Prowl', 0),
    'USE_NMA': ('bool', 'NMA', 0),
    'NMA_APIKEY': ('str', 'NMA', ''),
    'NMA_PRIORITY': ('int', 'NMA', 0),
    'NMA_ONSNATCH': ('bool', 'NMA', 0),
    'NMA_ONDOWNLOAD': ('bool', 'NMA', 0),
    'USE_SLACK': ('bool', 'Slack', 0),
    'SLACK_NOTIFY_ONSNATCH': ('bool', 'Slack', 0),
    'SLACK_NOTIFY_ONDOWNLOAD': ('bool', 'Slack', 0),
    'SLACK_TOKEN': ('str', 'Slack', ''),
    'USE_CUSTOM': ('bool', 'Custom', 0),
    'CUSTOM_NOTIFY_ONSNATCH': ('bool', 'Custom', 0),
    'CUSTOM_NOTIFY_ONDOWNLOAD': ('bool', 'Custom', 0),
    'CUSTOM_SCRIPT': ('str', 'Custom', ''),
    'USE_EMAIL': ('bool', 'Email', 0),
    'EMAIL_NOTIFY_ONSNATCH': ('bool', 'Email', 0),
    'EMAIL_NOTIFY_ONDOWNLOAD': ('bool', 'Email', 0),
    'EMAIL_SENDFILE_ONDOWNLOAD': ('bool', 'Email', 0),
    'EMAIL_FROM': ('str', 'Email', ''),
    'EMAIL_TO': ('str', 'Email', ''),
    'EMAIL_SSL': ('bool', 'Email', 0),
    'EMAIL_SMTP_SERVER': ('str', 'Email', ''),
    'EMAIL_SMTP_PORT': ('int', 'Email', 25),
    'EMAIL_TLS': ('bool', 'Email', 0),
    'EMAIL_SMTP_USER': ('str', 'Email', ''),
    'EMAIL_SMTP_PASSWORD': ('str', 'Email', ''),
    'BOOK_API': ('str', 'API', 'GoodReads'),
    'GR_API': ('str', 'API', 'ckvsiSDsuqh7omh74ZZ6Q'),
    'GR_SYNC': ('bool', 'API', 0),
    'GR_SECRET': ('str', 'API', ''),  # tied to users own api key
    'GR_OAUTH_TOKEN': ('str', 'API', ''),  # gives access to users bookshelves
    'GR_OAUTH_SECRET': ('str', 'API', ''),  # gives access to users bookshelves
    'GR_WANTED': ('str', 'API', ''),  # sync wanted to this shelf
    'GR_OWNED': ('str', 'API', ''),  # sync open/have to this shelf
    'GR_FOLLOW': ('bool', 'API', 0),  # follow authors on goodreads
    'GR_FOLLOWNEW': ('bool', 'API', 0),  # follow new authors on goodreads
    'GB_API': ('str', 'API', '')  # API key has daily limits, each user needs their own
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
    my_val = def_val
    if cfg_type == 'int':
        try:
            my_val = CFG.getint(cfg_name, item_name)
        except ConfigParser.Error:
            # no such item, might be a new entry
            my_val = int(def_val)
        except Exception as e:
            logger.warn('Invalid int for %s: %s, using default %s' % (cfg_name, item_name, int(def_val)))
            logger.debug(str(e))
            my_val = int(def_val)

    elif cfg_type == 'bool':
        try:
            my_val = CFG.getboolean(cfg_name, item_name)
        except ConfigParser.Error:
            my_val = bool(def_val)
        except Exception as e:
            logger.warn('Invalid bool for %s: %s, using default %s' % (cfg_name, item_name, bool(def_val)))
            logger.debug(str(e))
            my_val = bool(def_val)

    elif cfg_type == 'str':
        try:
            my_val = CFG.get(cfg_name, item_name)
            # Old config file format had strings in quotes. ConfigParser doesn't.
            if my_val.startswith('"') and my_val.endswith('"'):
                my_val = my_val[1:-1]
            if not len(my_val):
                my_val = def_val
            if isinstance(my_val, str) and hasattr(my_val, "decode"):
                my_val = my_val.decode(SYS_ENCODING)
        except ConfigParser.Error:
            my_val = str(def_val)
        except Exception as e:
            logger.warn('Invalid str for %s: %s, using default %s' % (cfg_name, item_name, str(def_val)))
            logger.debug(str(e))
            my_val = str(def_val)

    check_section(cfg_name)
    CFG.set(cfg_name, item_name, my_val)
    if log:
        logger.debug("%s : %s -> %s" % (cfg_name, item_name, my_val))

    return my_val


def initialize():
    global FULL_PATH, PROG_DIR, ARGS, DAEMON, SIGNAL, PIDFILE, DATADIR, CONFIGFILE, SYS_ENCODING, LOGLEVEL, \
        CONFIG, CFG, DBFILE, COMMIT_LIST, SCHED, INIT_LOCK, __INITIALIZED__, started, LOGLIST, LOGTOGGLE, \
        UPDATE_MSG, CURRENT_TAB, CACHE_HIT, CACHE_MISS, LAST_LIBRARYTHING, LAST_GOODREADS, SHOW_SERIES, SHOW_MAGS, \
        SHOW_AUDIO, CACHEDIR, BOOKSTRAP_THEMELIST, MONTHNAMES, CONFIG_DEFINITIONS, isbn_979_dict, isbn_978_dict, \
        AUTHORUPDATE_MSG, CONFIG_NONWEB, CONFIG_NONDEFAULT, CONFIG_GIT, MAG_UPDATE, AUDIO_UPDATE, EBOOK_UPDATE, \
        GROUP_CONCAT

    with INIT_LOCK:

        if __INITIALIZED__:
            return False

        check_section('General')
        # False to silence logging until logger initialised
        for key in ['LOGLIMIT', 'LOGFILES', 'LOGSIZE']:
            item_type, section, default = CONFIG_DEFINITIONS[key]
            CONFIG[key.upper()] = check_setting(item_type, section, key.lower(), default, log=False)
        CONFIG['LOGDIR'] = os.path.join(DATADIR, 'Logs')

        # Create logdir
        if not os.path.exists(CONFIG['LOGDIR']):
            try:
                os.makedirs(CONFIG['LOGDIR'])
            except OSError as e:
                if LOGLEVEL:
                    print '%s : Unable to create folder for logs: %s' % (
                        CONFIG['LOGDIR'], str(e))

        # Start the logger, silence console logging if we need to
        CFGLOGLEVEL = check_int(check_setting('int', 'General', 'loglevel', 1, log=False), 9)
        if LOGLEVEL == 1:  # default if no debug or quiet on cmdline
            if CFGLOGLEVEL == 9:  # default value if none in config
                LOGLEVEL = 1  # If not set in Config or cmdline, then lets set to NORMAL
            else:
                LOGLEVEL = CFGLOGLEVEL  # Config setting picked up

        CONFIG['LOGLEVEL'] = LOGLEVEL
        logger.lazylibrarian_log.initLogger(loglevel=CONFIG['LOGLEVEL'])
        logger.info("Log level set to [%s]- Log Directory is [%s] - Config level is [%s]" % (
            CONFIG['LOGLEVEL'], CONFIG['LOGDIR'], CFGLOGLEVEL))
        if CONFIG['LOGLEVEL'] > 2:
            logger.info("Screen Log set to FULL DEBUG")
        elif CONFIG['LOGLEVEL'] == 2:
            logger.info("Screen Log set to DEBUG")
        else:
            logger.info("Screen Log set to INFO/WARN/ERROR")

        config_read()
        logger.info('SYS_ENCODING is %s' % SYS_ENCODING)

        # Put the cache dir in the data dir for now
        CACHEDIR = os.path.join(DATADIR, 'cache')
        try:
            os.makedirs(CACHEDIR)
        except OSError as e:
            if not os.path.isdir(CACHEDIR):
                logger.error('Could not create cachedir; %s' % e.strerror)

        for item in ['book', 'author', 'SeriesCache', 'JSONCache', 'XMLCache', 'WorkCache', 'magazine']:
            cachelocation = os.path.join(CACHEDIR, item)
            try:
                os.makedirs(cachelocation)
            except OSError as e:
                if not os.path.isdir(cachelocation):
                    logger.error('Could not create %s: %s' % (cachelocation, e.strerror))

        # keep track of last api calls so we don't call more than once per second
        # to respect api terms, but don't wait un-necessarily either
        time_now = int(time.time())
        LAST_LIBRARYTHING = time_now
        LAST_GOODREADS = time_now

        # Initialize the database
        try:
            myDB = database.DBConnection()
            result = myDB.match('PRAGMA user_version')
            check = myDB.match('PRAGMA integrity_check')
            if result:
                version = result[0]
            else:
                version = 0
            logger.info("Database is version %s, integrity check: %s" % (version, check[0]))

        except Exception as e:
            logger.error("Can't connect to the database: %s %s" % (type(e).__name__, str(e)))

        # group_concat needs sqlite3 >= 3.5.4
        GROUP_CONCAT = False
        try:
            sqlv = getattr(sqlite3, 'sqlite_version', None)
            parts = sqlv.split('.')
            if int(parts[0]) == 3:
                if int(parts[1]) > 5 or int(parts[1]) == 5 and int(parts[2]) >= 4:
                    GROUP_CONCAT = True
        except Exception as e:
            logger.warn("Unable to parse sqlite3 version: %s %s" % (type(e).__name__, str(e)))

        debuginfo = logHeader()
        for item in debuginfo.splitlines():
            if 'missing' in item:
                logger.warn(item)

        MONTHNAMES = build_monthtable()
        BOOKSTRAP_THEMELIST = build_bookstrap_themes()

        __INITIALIZED__ = True
        return True


def config_read(reloaded=False):
    global CONFIG, CONFIG_DEFINITIONS, CONFIG_NONWEB, CONFIG_NONDEFAULT, NEWZNAB_PROV, TORZNAB_PROV, RSS_PROV, \
        CONFIG_GIT, SHOW_SERIES, SHOW_MAGS, SHOW_AUDIO
    # legacy name conversion
    if not CFG.has_option('General', 'ebook_dir'):
        ebook_dir = check_setting('str', 'General', 'destination_dir', '')
        CFG.set('General', 'ebook_dir', ebook_dir)
        CFG.remove_option('General', 'destination_dir')
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
                             "AUDIOSEARCH": check_setting('str', newz_name, 'audiosearch', ''),
                             "BOOKCAT": check_setting('str', newz_name, 'bookcat', '7000,7020'),
                             "MAGCAT": check_setting('str', newz_name, 'magcat', '7010'),
                             "AUDIOCAT": check_setting('str', newz_name, 'audiocat', '3030'),
                             "EXTENDED": check_setting('str', newz_name, 'extended', '1'),
                             "UPDATED": check_setting('str', newz_name, 'updated', ''),
                             "MANUAL": check_setting('bool', newz_name, 'manual', 0),
                             "DLPRIORITY": check_setting('int', newz_name, 'dlpriority', 0)
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
                             "AUDIOSEARCH": check_setting('str', torz_name, 'audiosearch', ''),
                             "BOOKCAT": check_setting('str', torz_name, 'bookcat', '8000,8010'),
                             "MAGCAT": check_setting('str', torz_name, 'magcat', '8030'),
                             "AUDIOCAT": check_setting('str', torz_name, 'audiocat', '3030'),
                             "EXTENDED": check_setting('str', torz_name, 'extended', '1'),
                             "UPDATED": check_setting('str', torz_name, 'updated', ''),
                             "MANUAL": check_setting('bool', torz_name, 'manual', 0),
                             "DLPRIORITY": check_setting('int', torz_name, 'dlpriority', 0)
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
                         "HOST": check_setting('str', rss_name, 'HOST', ''),
                         "DLPRIORITY": check_setting('int', rss_name, 'DLPRIORITY', 0)
                         })
        count += 1
    # if the last slot is full, add an empty one on the end
    add_rss_slot()

    for key in CONFIG_DEFINITIONS.keys():
        item_type, section, default = CONFIG_DEFINITIONS[key]
        CONFIG[key.upper()] = check_setting(item_type, section, key.lower(), default)
    if not CONFIG['LOGDIR']:
        CONFIG['LOGDIR'] = os.path.join(DATADIR, 'Logs')
    if CONFIG['HTTP_PORT'] < 21 or CONFIG['HTTP_PORT'] > 65535:
        CONFIG['HTTP_PORT'] = 5299

    # to make extension matching easier
    CONFIG['EBOOK_TYPE'] = CONFIG['EBOOK_TYPE'].lower()
    CONFIG['AUDIOBOOK_TYPE'] = CONFIG['AUDIOBOOK_TYPE'].lower()
    CONFIG['MAG_TYPE'] = CONFIG['MAG_TYPE'].lower()
    CONFIG['REJECT_WORDS'] = CONFIG['REJECT_WORDS'].lower()
    CONFIG['REJECT_AUDIO'] = CONFIG['REJECT_AUDIO'].lower()

    myDB = database.DBConnection()
    # check if we have an active database yet, not a fresh install
    result = myDB.match('PRAGMA user_version')
    if result:
        version = result[0]
    else:
        version = 0

    ###################################################################
    # ensure all these are boolean 1 0, not True False for javascript #
    ###################################################################
    # Suppress series tab if there are none and user doesn't want to add any
    series_list = ''
    if version:  # if zero, there is no series table yet
        series_list = myDB.select('SELECT SeriesID from series')

    SHOW_SERIES = len(series_list)
    if CONFIG['ADD_SERIES']:
        SHOW_SERIES = 1
    # Or suppress if tab is disabled
    if not CONFIG['SERIES_TAB']:
        SHOW_SERIES = 0
    # Suppress magazine tab if disabled
    if CONFIG['MAG_TAB']:
        SHOW_MAGS = 1
    else:
        SHOW_MAGS = 0
    # Suppress audio tab if on default interface
    if CONFIG['HTTP_LOOK'] == 'default':
        SHOW_AUDIO = 0
    # or if disabled
    elif CONFIG['AUDIO_TAB']:
        SHOW_AUDIO = 1
    else:
        SHOW_AUDIO = 0

    for item in ['BOOK_IMG', 'MAG_IMG', 'AUTHOR_IMG', 'TOGGLES']:
        if CONFIG[item]:
            CONFIG[item] = 1
        else:
            CONFIG[item] = 0

    if reloaded:
        logger.info('Config file reloaded')
    else:
        logger.info('Config file loaded')


def config_write():
    global SHOW_SERIES, SHOW_MAGS, SHOW_AUDIO, CONFIG_NONWEB, CONFIG_NONDEFAULT, CONFIG_GIT, LOGLEVEL, NEWZNAB_PROV, \
        TORZNAB_PROV, RSS_PROV

    threading.currentThread().name = "CONFIG_WRITE"
    myDB = database.DBConnection()

    interface = CFG.get('General', 'http_look')

    for key in CONFIG_DEFINITIONS.keys():
        item_type, section, default = CONFIG_DEFINITIONS[key]
        if key == 'WALL_COLUMNS':  # may be modified by user interface but not on config page
            value = CONFIG[key]
        elif key not in CONFIG_NONWEB and not (interface == 'default' and key in CONFIG_NONDEFAULT):
            check_section(section)
            value = CONFIG[key]
            if key == 'LOGLEVEL':
                LOGLEVEL = check_int(value, 1)
            elif key in ['LOGDIR', 'EBOOK_DIR', 'AUDIO_DIR', 'ALTERNATE_DIR', 'DOWLOAD_DIR',
                         'EBOOK_DEST_FILE', 'EBOOK_DEST_FOLDER', 'MAG_DEST_FILE', 'MAG_DEST_FOLDER']:
                value = value.encode(SYS_ENCODING)
            elif key in ['REJECT_WORDS', 'REJECT_AUDIO', 'MAG_TYPE', 'EBOOK_TYPE', 'AUDIOBOOK_TYPE']:
                value = value.encode(SYS_ENCODING).lower()
        else:
            # keep the old value
            value = CFG.get(section, key.lower())
            # if CONFIG['LOGLEVEL'] > 2:
            #     logger.debug("Leaving %s unchanged (%s)" % (key, value))
            CONFIG[key] = value
        CFG.set(section, key.lower(), value)

    # sanity check for typos...
    for key in CONFIG.keys():
        if key not in CONFIG_DEFINITIONS.keys():
            logger.warn('Unsaved config key: %s' % key)

    for entry in [[NEWZNAB_PROV, 'Newznab'], [TORZNAB_PROV, 'Torznab']]:
        new_list = []
        # strip out any empty slots
        for provider in entry[0]:
            if provider['HOST']:
                new_list.append(provider)

        # renumber the items
        for index, item in enumerate(new_list):
            item['NAME'] = '%s%i' % (entry[1], index)

        # delete the old entries
        sections = CFG.sections()
        for item in sections:
            if item.startswith(entry[1]):
                CFG.remove_section(item)

        for provider in new_list:
            check_section(provider['NAME'])
            CFG.set(provider['NAME'], 'ENABLED', provider['ENABLED'])
            CFG.set(provider['NAME'], 'HOST', provider['HOST'])
            CFG.set(provider['NAME'], 'API', provider['API'])
            CFG.set(provider['NAME'], 'GENERALSEARCH', provider['GENERALSEARCH'])
            CFG.set(provider['NAME'], 'BOOKSEARCH', provider['BOOKSEARCH'])
            CFG.set(provider['NAME'], 'MAGSEARCH', provider['MAGSEARCH'])
            CFG.set(provider['NAME'], 'AUDIOSEARCH', provider['AUDIOSEARCH'])
            CFG.set(provider['NAME'], 'BOOKCAT', provider['BOOKCAT'])
            CFG.set(provider['NAME'], 'MAGCAT', provider['MAGCAT'])
            CFG.set(provider['NAME'], 'AUDIOCAT', provider['AUDIOCAT'])
            CFG.set(provider['NAME'], 'EXTENDED', provider['EXTENDED'])
            CFG.set(provider['NAME'], 'DLPRIORITY', check_int(provider['DLPRIORITY'], 0))
            CFG.set(provider['NAME'], 'UPDATED', provider['UPDATED'])
            CFG.set(provider['NAME'], 'MANUAL', provider['MANUAL'])

        if entry[1] == 'Newznab':
            NEWZNAB_PROV = new_list
            add_newz_slot()
        else:
            TORZNAB_PROV = new_list
            add_torz_slot()

    new_list = []
    # strip out any empty slots
    for provider in RSS_PROV:
        if provider['HOST']:
            new_list.append(provider)

    # renumber the items
    for index, item in enumerate(new_list):
        item['NAME'] = 'RSS_%i' % index

    # strip out the old config entries
    sections = CFG.sections()
    for item in sections:
        if item.startswith('RSS_'):
            CFG.remove_section(item)

    for provider in new_list:
        check_section(provider['NAME'])
        CFG.set(provider['NAME'], 'ENABLED', provider['ENABLED'])
        CFG.set(provider['NAME'], 'HOST', provider['HOST'])
        CFG.set(provider['NAME'], 'DLPRIORITY', check_int(provider['DLPRIORITY'], 0))

    RSS_PROV = new_list
    add_rss_slot()
    #
    series_list = myDB.select('SELECT SeriesID from series')
    SHOW_SERIES = len(series_list)
    if CONFIG['ADD_SERIES']:
        SHOW_SERIES = 1
    if not CONFIG['SERIES_TAB']:
        SHOW_SERIES = 0

    SHOW_MAGS = len(CONFIG['MAG_DEST_FOLDER'])
    if not CONFIG['MAG_TAB']:
        SHOW_MAGS = 0

    if CONFIG['HTTP_LOOK'] == 'default':
        SHOW_AUDIO = 0
    elif CONFIG['AUDIO_TAB']:
        SHOW_AUDIO = 1
    else:
        SHOW_AUDIO = 0

    msg = None
    try:
        with open(CONFIGFILE + '.new', 'wb') as configfile:
            CFG.write(configfile)
    except Exception as e:
        msg = '{} {} {} {}'.format('Unable to create new config file:', CONFIGFILE, type(e).__name__, str(e))
        logger.warn(msg)
        return
    try:
        os.remove(CONFIGFILE + '.bak')
    except OSError as e:
        if e.errno is not 2:  # doesn't exist is ok
            msg = '{} {}{} {} {}'.format(type(e).__name__, 'deleting backup file:', CONFIGFILE, '.bak', e.strerror)
            logger.warn(msg)
    try:
        os.rename(CONFIGFILE, CONFIGFILE + '.bak')
    except OSError as e:
        if e.errno is not 2:  # doesn't exist is ok as wouldn't exist until first save
            msg = '{} {} {} {}'.format('Unable to backup config file:', CONFIGFILE, type(e).__name__, e.strerror)
            logger.warn(msg)
    try:
        os.rename(CONFIGFILE + '.new', CONFIGFILE)
    except OSError as e:
        msg = '{} {} {} {}'.format('Unable to rename new config file:', CONFIGFILE, type(e).__name__, e.strerror)
        logger.warn(msg)

    if not msg:
        msg = 'Config file [%s] has been updated' % CONFIGFILE
        logger.info(msg)


def add_newz_slot():
    count = len(NEWZNAB_PROV)
    if count == 0 or len(CFG.get('Newznab%i' % int(count - 1), 'HOST')):
        prov_name = 'Newznab%i' % count
        empty = {"NAME": prov_name,
                 "ENABLED": 0,
                 "HOST": '',
                 "API": '',
                 "GENERALSEARCH": 'search',
                 "BOOKSEARCH": 'book',
                 "MAGSEARCH": '',
                 "AUDIOSEARCH": '',
                 "BOOKCAT": '7000,7020',
                 "MAGCAT": '7010',
                 "AUDIOCAT": '3030',
                 "EXTENDED": '1',
                 "UPDATED": '',
                 "MANUAL": 0,
                 "DLPRIORITY": 0
                 }
        NEWZNAB_PROV.append(empty)

        check_section(prov_name)
        for item in empty:
            if item != 'NAME':
                CFG.set(prov_name, item, empty[item])


def add_torz_slot():
    count = len(TORZNAB_PROV)
    if count == 0 or len(CFG.get('Torznab%i' % int(count - 1), 'HOST')):
        prov_name = 'Torznab%i' % count
        empty = {"NAME": prov_name,
                 "ENABLED": 0,
                 "HOST": '',
                 "API": '',
                 "GENERALSEARCH": 'search',
                 "BOOKSEARCH": 'book',
                 "MAGSEARCH": '',
                 "AUDIOSEARCH": '',
                 "BOOKCAT": '8000,8010',
                 "MAGCAT": '8030',
                 "AUDIOCAT": '8030',
                 "EXTENDED": '1',
                 "UPDATED": '',
                 "MANUAL": 0,
                 "DLPRIORITY": 0
                 }
        TORZNAB_PROV.append(empty)

        check_section(prov_name)
        for item in empty:
            if item != 'NAME':
                CFG.set(prov_name, item, empty[item])


def DIRECTORY(dirname):
    usedir = ''
    if dirname == "eBook":
        usedir = CONFIG['EBOOK_DIR']
    elif dirname == "Audio":
        usedir = CONFIG['AUDIO_DIR']
    elif dirname == "Download":
        try:
            usedir = getList(CONFIG['DOWNLOAD_DIR'], ',')[0]
        except IndexError:
            usedir = ''
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
    if isinstance(usedir, str) and hasattr(usedir, "decode"):
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
                         "HOST": '',
                         "DLPRIORITY": 0
                         })


def USE_NZB():
    # Count how many nzb providers are active
    count = 0
    for provider in NEWZNAB_PROV:
        if bool(provider['ENABLED']):
            count += 1
    for provider in TORZNAB_PROV:
        if bool(provider['ENABLED']):
            count += 1
    return count


def USE_RSS():
    count = 0
    for provider in RSS_PROV:
        if bool(provider['ENABLED']):
            count += 1
    return count


def USE_TOR():
    count = 0
    for provider in [CONFIG['KAT'], CONFIG['TPB'], CONFIG['ZOO'], CONFIG['LIME'], CONFIG['TDL'], CONFIG['WWT']]:
        if bool(provider):
            count += 1
    return count


def USE_DIRECT():
    count = 0
    for provider in [CONFIG['GEN'], CONFIG['GEN2']]:
        if bool(provider):
            count += 1
    return count


def build_bookstrap_themes():
    themelist = []
    if not os.path.isdir(os.path.join(PROG_DIR, 'data', 'interfaces', 'bookstrap')):
        return themelist  # return empty if bookstrap interface not installed

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
        logger.debug('JSON Error reading bookstrap themes, %s %s' % (type(e).__name__, str(e)))

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
            logger.error('Failed to load monthnames.json, %s %s' % (type(e).__name__, str(e)))

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
            logger.warn("Unable to load requested locale [%s] %s %s" % (lang, type(e).__name__, str(e)))
            try:
                wanted_lang = lang.split('_')[0]
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
                logger.warn("Unable to get a list of alternatives, %s %s" % (type(e).__name__, str(e)))
            logger.info("Set locale back to entry state %s" % current_locale)

    # with open(json_file, 'w') as f:
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
        logger.debug("Writing PID " + pid + " to " + str(PIDFILE))
        file(PIDFILE, 'w').write("%s\n" % pid)


def launch_browser(host, port, root):
    if host == '0.0.0.0':
        host = 'localhost'

    try:
        webbrowser.open('http://%s:%i%s' % (host, port, root))
    except Exception as e:
        logger.error('Could not launch browser:%s  %s' % (type(e).__name__, str(e)))


def start():
    global __INITIALIZED__, started, SHOW_SERIES, SHOW_MAGS, SHOW_AUDIO

    if __INITIALIZED__:
        # Crons and scheduled jobs started here
        SCHED.start()
        started = True
        if not UPDATE_MSG:
            myDB = database.DBConnection()
            restartJobs(start='Start')
            series_list = myDB.select('SELECT SeriesID from series')
            SHOW_SERIES = len(series_list)
            if CONFIG['ADD_SERIES']:
                SHOW_SERIES = 1
            SHOW_MAGS = len(CONFIG['MAG_DEST_FOLDER'])

            if CONFIG['HTTP_LOOK'] == 'default':
                SHOW_AUDIO = 0
            elif CONFIG['AUDIO_TAB']:
                SHOW_AUDIO = 1
            else:
                SHOW_AUDIO = 0


def logmsg(level, msg):
    # log messages to logger if initialised, or print if not.
    if __INITIALIZED__:
        if level == 'error':
            logger.error(msg)
        elif level == 'debug':
            logger.debug(msg)
        elif level == 'warn':
            logger.warn(msg)
        else:
            logger.info(msg)
    else:
        print level.upper(), msg


def shutdown(restart=False, update=False):
    cherrypy.engine.exit()
    SCHED.shutdown(wait=False)
    # config_write() don't automatically rewrite config on exit

    if not restart and not update:
        logmsg('info', 'LazyLibrarian is shutting down...')

    if update:
        logmsg('info', 'LazyLibrarian is updating...')
        try:
            if versioncheck.update():
                logmsg('info', 'Lazylibrarian version updated')
                config_write()
        except Exception as e:
            logmsg('warn', 'LazyLibrarian failed to update: %s %s. Restarting.' % (type(e).__name__, str(e)))

    if PIDFILE:
        logmsg('info', 'Removing pidfile %s' % PIDFILE)
        os.remove(PIDFILE)

    if restart:
        logmsg('info', 'LazyLibrarian is restarting ...')

        # Try to use the currently running python executable, as it is known to work
        # if not able to determine, sys.executable returns empty string or None
        # and we have to go looking for it...
        executable = sys.executable

        if not executable:
            if platform.system() == "Windows":
                params = ["where", "python2"]
                try:
                    executable = subprocess.check_output(params, stderr=subprocess.STDOUT).strip()
                except Exception as e:
                    logger.debug("where python2 failed: %s %s" % (type(e).__name__, str(e)))
            else:
                params = ["which", "python2"]
                try:
                    executable = subprocess.check_output(params, stderr=subprocess.STDOUT).strip()
                except Exception as e:
                    logger.debug("which python2 failed: %s %s" % (type(e).__name__, str(e)))

        if not executable:
            executable = 'python'  # default if not found, still might not work if points to python3

        popen_list = [executable, FULL_PATH]
        popen_list += ARGS
        if '--update' in popen_list:
            popen_list.remove('--update')
        if LOGLEVEL:
            if '--quiet' in popen_list:
                popen_list.remove('--quiet')
            if '-q' in popen_list:
                popen_list.remove('-q')
        if '--nolaunch' not in popen_list:
            popen_list += ['--nolaunch']

        logmsg('debug', 'Restarting LazyLibrarian with ' + str(popen_list))
        subprocess.Popen(popen_list, cwd=os.getcwd())

    logmsg('info', 'LazyLibrarian is exiting')
    # noinspection PyProtectedMember
    os._exit(0)
