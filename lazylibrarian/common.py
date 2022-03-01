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

import datetime
import os
import glob
import sys
import platform
import string
import random
import shutil
import threading
import time
import traceback
from lib.six import PY2
from subprocess import Popen, PIPE

try:
    import zipfile
except ImportError:
    if PY2:
        import lib.zipfile as zipfile
    else:
        import lib3.zipfile as zipfile

import re
import ssl
import sqlite3
import cherrypy

# some mac versions include requests _without_ urllib3, our copy bundles it
try:
    # noinspection PyUnresolvedReferences
    import urllib3
    import requests
except ImportError:
    import lib.requests as requests

import lazylibrarian
from lazylibrarian import logger, database
from lazylibrarian.formatter import plural, next_run, is_valid_booktype, datecompare, check_int, \
    getList, makeUnicode, makeBytestr, unaccented, replace_all

# Notification Types
NOTIFY_SNATCH = 1
NOTIFY_DOWNLOAD = 2

notifyStrings = {NOTIFY_SNATCH: "Started Download", NOTIFY_DOWNLOAD: "Added to Library"}

# dict to remove/replace characters we don't want in a filename - this might be too strict?
__dic__ = {'<': '', '>': '', '...': '', ' & ': ' ', ' = ': ' ', '?': '', '$': 's', '|': '',
           ' + ': ' ', '"': '', ',': '', '*': '', ':': '', ';': '', '\'': '', '//': '/', '\\\\': '\\'}


def getUserAgent():
    # Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/52.0.2743.116 Safari/537.36
    if lazylibrarian.CONFIG['USER_AGENT']:
        return lazylibrarian.CONFIG['USER_AGENT']
    else:
        return 'LazyLibrarian' + ' (' + platform.system() + ' ' + platform.release() + ')'


def mymakedirs(dest_path):
    """ os.makedirs only seems to set the right permission on the final leaf directory
        not any intermediate parents it creates on the way, so we'll try to do it ourselves
        setting permissions as we go. Could use recursion but probably aren't many levels to do...
        Build a list of missing intermediate directories in reverse order, exit when we encounter
        an existing directory or hit root level. Set permission on any directories we create.
        return True or False """

    to_make = []
    while not os.path.isdir(dest_path):
        # noinspection PyUnresolvedReferences
        to_make.insert(0, dest_path)
        parent = os.path.dirname(dest_path)
        if parent == dest_path:
            break
        else:
            dest_path = parent

    for entry in to_make:
        if lazylibrarian.LOGLEVEL & lazylibrarian.log_fileperms:
            logger.debug("mkdir: [%s]" % repr(entry))
        try:
            os.mkdir(entry)  # mkdir uses umask, so set perm ourselves
            _ = setperm(entry)  # failing to set perm might not be fatal
        except OSError as why:
            # os.path.isdir() has some odd behaviour on windows, says the directory does NOT exist
            # then when you try to mkdir complains it already exists.
            # Ignoring the error might just move the problem further on?
            # Something similar seems to occur on google drive filestream
            # but that returns Error 5 Access is denied
            # Trap errno 17 (linux file exists) and 183 (windows already exists)
            if why.errno in [17, 183]:
                if lazylibrarian.LOGLEVEL & lazylibrarian.log_fileperms:
                    logger.debug("Ignoring mkdir already exists errno %s: [%s]" % (why.errno, repr(entry)))
                pass
            elif 'exists' in str(why):
                if lazylibrarian.LOGLEVEL & lazylibrarian.log_fileperms:
                    logger.debug("Ignoring %s: [%s]" % (why, repr(entry)))
                pass
            else:
                logger.error('Unable to create directory %s: [%s]' % (why, repr(entry)))
                return False
    return True


def safe_move(src, dst, action='move'):
    """ Move or copy src to dst
        Retry without accents if unicode error as some file systems can't handle (some) accents
        Retry with some characters stripped if bad filename
        eg windows can't handle <>?":| (and maybe others) in filenames
        Return (new) dst if success """

    while action:  # might have more than one problem...
        try:
            if action == 'copy':
                shutil.copy(src, dst)
            elif os.path.isdir(src) and dst.startswith(src):
                shutil.copytree(src, dst)
            else:
                shutil.move(src, dst)
            return dst

        except UnicodeEncodeError:
            newdst = unaccented(dst)
            if newdst != dst:
                dst = newdst
            else:
                raise

        except IOError as e:
            if e.errno == 22:  # bad mode or filename
                drive, path = os.path.splitdrive(dst)
                # strip some characters windows can't handle
                newpath = replace_all(path, __dic__)
                # windows filenames can't end in space or dot
                while newpath and newpath[-1] in '. ':
                    newpath = newpath[:-1]
                # anything left? has it changed?
                if newpath and newpath != path:
                    dst = os.path.join(drive, newpath)
                else:
                    raise
            else:
                raise
        except Exception:
            raise
    return dst


def safe_copy(src, dst):
    return safe_move(src, dst, action='copy')


def proxyList():
    proxies = None
    if lazylibrarian.CONFIG['PROXY_HOST']:
        proxies = {}
        for item in getList(lazylibrarian.CONFIG['PROXY_TYPE']):
            if item in ['http', 'https']:
                proxies.update({item: lazylibrarian.CONFIG['PROXY_HOST']})
    return proxies


def isValidEmail(email):
    if len(email) > 7:
        # noinspection PyBroadException
        try:
            if re.match("^[_a-z0-9-]+(\.[_a-z0-9-]+)*@[a-z0-9-]+(\.[a-z0-9-]+)*(\.[a-z]{2,4})$", email) is not None:
                return True
        except Exception:
            return False
    return False


def pwd_generator(size=10, chars=string.ascii_letters + string.digits):
    return ''.join(random.choice(chars) for _ in range(size))


def pwd_check(password):
    # password rules:
    # At least 8 digits long
    # with no spaces
    # we don't enforce mix of alnum as longer passwords
    # made of random words are more secure
    if len(password) < 8:
        return False
    # if not any(char.isdigit() for char in password):
    #    return False
    # if not any(char.isalpha() for char in password):
    #    return False
    if any(char.isspace() for char in password):
        return False
    return True


# noinspection PyShadowingNames,PyUnusedLocal
def error_page_401(status, message, traceback, version):
    """ Custom handler for 401 error """
    title = "I'm not getting out of bed"
    body = 'Error %s: You need to provide a valid username and password.' % status
    return r'''
<html>
    <head>
    <STYLE type="text/css">
      H1 { text-align: center}
      H2 { text-align: center}
      H3 { text-align: center}
    </STYLE>
    <h1>LazyLibrarian<br><br></h1>
    <h3><img src="data:image/png;base64,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
OjAwC98hhgAAAABJRU5ErkJggg==" alt="embedded icon" align="middle"><br><br>
    %s</h3>
    </head>
    <body>
    <br>
    <h2><font color="#0000FF">%s</font></h2>
    </body>
</html>
''' % (title, body)


def octal(value, default):
    if not value:
        return default
    try:
        value = int(str(value), 8)
        return value
    except ValueError:
        return default


def setperm(file_or_dir):
    """
    Force newly created directories to rwxr-xr-x and files to rw-r--r--
    or other value as set in config
    """
    if not file_or_dir:
        return False

    if os.path.isdir(file_or_dir):
        perm = octal(lazylibrarian.CONFIG['DIR_PERM'], 0o755)
    elif os.path.isfile(file_or_dir):
        perm = octal(lazylibrarian.CONFIG['FILE_PERM'], 0o644)
    else:
        # not a file or a directory (symlink?)
        return False

    want_perm = oct(perm)[-3:].zfill(3)
    st = os.stat(file_or_dir)
    old_perm = oct(st.st_mode)[-3:].zfill(3)
    if old_perm == want_perm:
        if lazylibrarian.LOGLEVEL & lazylibrarian.log_fileperms:
            logger.debug("Permission for %s is already %s" % (file_or_dir, want_perm))
        return True

    try:
        os.chmod(file_or_dir, perm)
    except Exception as e:
        logger.debug("Error setting permission %s for %s: %s %s" % (want_perm, file_or_dir, type(e).__name__, str(e)))
        return False

    st = os.stat(file_or_dir)
    new_perm = oct(st.st_mode)[-3:].zfill(3)

    if new_perm == want_perm:
        if lazylibrarian.LOGLEVEL & lazylibrarian.log_fileperms:
            logger.debug("Set permission %s for %s, was %s" % (want_perm, file_or_dir, old_perm))
        return True
    else:
        logger.debug("Failed to set permission %s for %s, got %s" % (want_perm, file_or_dir, new_perm))
    return False


def any_file(search_dir=None, extn=None):
    # find a file with specified extension in a directory, any will do
    # return full pathname of file, or empty string if none found
    if search_dir is None or extn is None:
        return ""
    if os.path.isdir(search_dir):
        for fname in os.listdir(makeBytestr(search_dir)):
            fname = makeUnicode(fname)
            if fname.endswith(extn):
                return os.path.join(search_dir, fname)
    return ""


def opf_file(search_dir=None):
    if search_dir is None:
        return ""
    cnt = 0
    res = ''
    meta = ''
    if os.path.isdir(search_dir):
        for fname in os.listdir(makeBytestr(search_dir)):
            fname = makeUnicode(fname)
            if fname.endswith('.opf'):
                if fname == 'metadata.opf':
                    meta = os.path.join(search_dir, fname)
                else:
                    res = os.path.join(search_dir, fname)
                cnt += 1
        if cnt > 2 or cnt == 2 and not meta:
            logger.debug("Found %d conflicting opf in %s" % (cnt, search_dir))
            res = ''
        elif res:  # prefer bookname.opf over metadata.opf
            return res
        elif meta:
            return meta
    return res


def bts_file(search_dir=None):
    if 'bts' not in getList(lazylibrarian.CONFIG['SKIPPED_EXT']):
        return ''
    return any_file(search_dir, '.bts')


def csv_file(search_dir=None, library=None):
    if search_dir and os.path.isdir(search_dir):
        try:
            for fname in os.listdir(makeBytestr(search_dir)):
                fname = makeUnicode(fname)
                if fname.endswith('.csv'):
                    if not library or library in fname:
                        return os.path.join(search_dir, fname)
        except Exception as e:
            logger.warn('Listdir error [%s]: %s %s' % (search_dir, type(e).__name__, str(e)))
    return ''


def jpg_file(search_dir=None):
    return any_file(search_dir, '.jpg')


def book_file(search_dir=None, booktype=None):
    # find a book/mag file in this directory, any book will do
    # return full pathname of book/mag, or empty string if none found
    if search_dir is None or booktype is None:
        return ""
    if search_dir and os.path.isdir(search_dir):
        try:
            for fname in os.listdir(makeBytestr(search_dir)):
                fname = makeUnicode(fname)
                if is_valid_booktype(fname, booktype=booktype):
                    return os.path.join(search_dir, fname)
        except Exception as e:
            logger.warn('Listdir error [%s]: %s %s' % (search_dir, type(e).__name__, str(e)))
    return ""


def mimeType(filename):
    name = filename.lower()
    if name.endswith('.epub'):
        return 'application/epub+zip'
    elif name.endswith('.mobi') or name.endswith('.azw'):
        return 'application/x-mobipocket-ebook'
    elif name.endswith('.azw3'):
        return 'application/x-mobi8-ebook'
    elif name.endswith('.pdf'):
        return 'application/pdf'
    elif name.endswith('.mp3'):
        return 'audio/mpeg3'
    elif name.endswith('.zip'):
        return 'application/x-zip-compressed'
    elif name.endswith('.xml'):
        return 'application/rss+xml'
    return "application/x-download"


def is_overdue():
    overdue = 0
    total = 0
    name = ''
    days = 0
    maxage = check_int(lazylibrarian.CONFIG['CACHE_AGE'], 0)
    if maxage:
        myDB = database.DBConnection()
        cmd = 'SELECT AuthorName,DateAdded from authors WHERE Status="Active" or Status="Loading"'
        cmd += ' or Status="Wanted" and DateAdded is not null order by DateAdded ASC'
        authors = myDB.select(cmd)
        total = len(authors)
        if total:
            name = authors[0]['AuthorName']
            dtnow = datetime.datetime.now()
            days = datecompare(dtnow.strftime("%Y-%m-%d"), authors[0]['DateAdded'])
            for author in authors:
                diff = datecompare(dtnow.strftime("%Y-%m-%d"), author['DateAdded'])
                if diff <= maxage:
                    break
                overdue += 1
    return overdue, total, name, days


def scheduleJob(action='Start', target=None):
    """ Start or stop or restart a cron job by name eg
        target=search_magazines, target=processDir, target=search_book """
    if target is None:
        return

    if target == 'PostProcessor':  # more readable
        target = 'processDir'

    if action in ['Stop', 'Restart']:
        for job in lazylibrarian.SCHED.get_jobs():
            if target in str(job):
                lazylibrarian.SCHED.unschedule_job(job)
                logger.debug("Stop %s job" % target)

    if action in ['Start', 'Restart']:
        for job in lazylibrarian.SCHED.get_jobs():
            if target in str(job):
                logger.debug("%s %s job, already scheduled" % (action, target))
                return  # return if already running, if not, start a new one
        if 'processDir' in target and check_int(lazylibrarian.CONFIG['SCAN_INTERVAL'], 0):
            minutes = check_int(lazylibrarian.CONFIG['SCAN_INTERVAL'], 0)
            lazylibrarian.SCHED.add_interval_job(lazylibrarian.postprocess.cron_processDir, minutes=minutes)
            logger.debug("%s %s job in %s minute%s" % (action, target, minutes, plural(minutes)))
        elif 'search_magazines' in target and check_int(lazylibrarian.CONFIG['SEARCH_MAGINTERVAL'], 0):
            minutes = check_int(lazylibrarian.CONFIG['SEARCH_MAGINTERVAL'], 0)
            if lazylibrarian.USE_TOR() or lazylibrarian.USE_NZB() \
                    or lazylibrarian.USE_RSS() or lazylibrarian.USE_DIRECT():
                lazylibrarian.SCHED.add_interval_job(lazylibrarian.searchmag.cron_search_magazines, minutes=minutes)
                logger.debug("%s %s job in %s minute%s" % (action, target, minutes, plural(minutes)))
        elif 'search_book' in target and check_int(lazylibrarian.CONFIG['SEARCH_BOOKINTERVAL'], 0):
            minutes = check_int(lazylibrarian.CONFIG['SEARCH_BOOKINTERVAL'], 0)
            if lazylibrarian.USE_NZB() or lazylibrarian.USE_TOR() or lazylibrarian.USE_DIRECT():
                lazylibrarian.SCHED.add_interval_job(lazylibrarian.searchbook.cron_search_book, minutes=minutes)
                logger.debug("%s %s job in %s minute%s" % (action, target, minutes, plural(minutes)))
        elif 'search_rss_book' in target and check_int(lazylibrarian.CONFIG['SEARCHRSS_INTERVAL'], 0):
            if lazylibrarian.USE_RSS():
                minutes = check_int(lazylibrarian.CONFIG['SEARCHRSS_INTERVAL'], 0)
                lazylibrarian.SCHED.add_interval_job(lazylibrarian.searchrss.cron_search_rss_book, minutes=minutes)
                logger.debug("%s %s job in %s minute%s" % (action, target, minutes, plural(minutes)))
        elif 'search_wishlist' in target and check_int(lazylibrarian.CONFIG['WISHLIST_INTERVAL'], 0):
            if lazylibrarian.USE_WISHLIST():
                hours = check_int(lazylibrarian.CONFIG['WISHLIST_INTERVAL'], 0)
                lazylibrarian.SCHED.add_interval_job(lazylibrarian.searchrss.cron_search_wishlist, hours=hours)
                logger.debug("%s %s job in %s hour%s" % (action, target, hours, plural(hours)))
        elif 'checkForUpdates' in target and check_int(lazylibrarian.CONFIG['VERSIONCHECK_INTERVAL'], 0):
            hours = check_int(lazylibrarian.CONFIG['VERSIONCHECK_INTERVAL'], 0)
            lazylibrarian.SCHED.add_interval_job(
                lazylibrarian.versioncheck.checkForUpdates, hours=hours)
            logger.debug("%s %s job in %s hour%s" % (action, target, hours, plural(hours)))
        elif 'syncToGoodreads' in target and lazylibrarian.CONFIG['GR_SYNC']:
            if check_int(lazylibrarian.CONFIG['GOODREADS_INTERVAL'], 0):
                hours = check_int(lazylibrarian.CONFIG['GOODREADS_INTERVAL'], 0)
                lazylibrarian.SCHED.add_interval_job(lazylibrarian.grsync.cron_sync_to_gr, hours=hours)
                logger.debug("%s %s job in %s hour%s" % (action, target, hours, plural(hours)))
        elif 'authorUpdate' in target and check_int(lazylibrarian.CONFIG['CACHE_AGE'], 0):
            # Try to get all authors scanned evenly inside the cache age
            maxage = check_int(lazylibrarian.CONFIG['CACHE_AGE'], 0)
            if maxage:
                overdue, total, _, days = is_overdue()
                if not overdue:
                    logger.debug("There are no authors to update")
                    if days > maxage:
                        minutes = 60 * 24  # nothing today, check again in 24hrs
                    else:
                        minutes = 60
                else:
                    logger.debug("Found %s author%s from %s overdue update" % (
                                 overdue, plural(overdue), total))
                    minutes = maxage * 60 * 24
                    minutes = int(minutes / total)
                    minutes -= 5  # average update time

                if minutes < 10:  # set a minimum interval of 10 minutes so we don't upset goodreads/librarything api
                    minutes = 10
                if minutes <= 600:  # for bigger intervals switch to hours
                    lazylibrarian.SCHED.add_interval_job(authorUpdate, minutes=minutes)
                    logger.debug("%s %s job in %s minute%s" % (action, target, minutes, plural(minutes)))
                else:
                    hours = int(minutes / 60)
                    lazylibrarian.SCHED.add_interval_job(authorUpdate, hours=hours)
                    logger.debug("%s %s job in %s hour%s" % (action, target, hours, plural(hours)))
            else:
                logger.debug("No authorupdate scheduled")


def authorUpdate(restart=True):
    threadname = threading.currentThread().name
    if "Thread-" in threadname:
        threading.currentThread().name = "AUTHORUPDATE"
    # noinspection PyBroadException
    try:
        myDB = database.DBConnection()
        cmd = 'SELECT AuthorID, AuthorName, DateAdded from authors WHERE Status="Active" or Status="Loading"'
        cmd += ' or Status="Wanted" and DateAdded is not null order by DateAdded ASC'
        author = myDB.match(cmd)
        if author and check_int(lazylibrarian.CONFIG['CACHE_AGE'], 0):
            dtnow = datetime.datetime.now()
            diff = datecompare(dtnow.strftime("%Y-%m-%d"), author['DateAdded'])
            msg = 'Oldest author info (%s) is %s day%s old' % (author['AuthorName'], diff, plural(diff))
            if diff > check_int(lazylibrarian.CONFIG['CACHE_AGE'], 0):
                msg = 'Starting update for %s' % author['AuthorName']
                logger.info(msg)
                lazylibrarian.importer.addAuthorToDB(refresh=True, authorid=author['AuthorID'])
                msg = 'Updated author %s' % author['AuthorName']
            else:
                logger.debug(msg)
            if restart:
                scheduleJob("Restart", "authorUpdate")
            return msg
    except Exception:
        logger.error('Unhandled exception in AuthorUpdate: %s' % traceback.format_exc())
        return "Unhandled exception in AuthorUpdate"


def aaUpdate(refresh=False):
    # noinspection PyBroadException
    try:
        myDB = database.DBConnection()
        cmd = 'SELECT AuthorID from authors WHERE Status="Active" or Status="Loading" or Status="Wanted"'
        cmd += ' order by DateAdded ASC'
        activeauthors = myDB.select(cmd)
        lazylibrarian.AUTHORS_UPDATE = True
        logger.info('Starting update for %i active author%s' % (len(activeauthors), plural(len(activeauthors))))
        for author in activeauthors:
            lazylibrarian.importer.addAuthorToDB(refresh=refresh, authorid=author['AuthorID'])
        logger.info('Active author update complete')
        lazylibrarian.AUTHORS_UPDATE = False
        msg = 'Updated %i active author%s' % (len(activeauthors), plural(len(activeauthors)))
        logger.debug(msg)
    except Exception:
        lazylibrarian.AUTHORS_UPDATE = False
        msg = 'Unhandled exception in aaUpdate: %s' % traceback.format_exc()
        logger.error(msg)
    return msg


def restartJobs(start='Restart'):
    scheduleJob(start, 'PostProcessor')
    scheduleJob(start, 'search_book')
    scheduleJob(start, 'search_rss_book')
    scheduleJob(start, 'search_wishlist')
    scheduleJob(start, 'search_magazines')
    scheduleJob(start, 'checkForUpdates')
    scheduleJob(start, 'authorUpdate')
    scheduleJob(start, 'syncToGoodreads')


def ensureRunning(jobname):
    found = False
    for job in lazylibrarian.SCHED.get_jobs():
        if jobname in str(job):
            found = True
            break
    if not found:
        scheduleJob('Start', jobname)


def checkRunningJobs():
    # make sure the relevant jobs are running
    # search jobs start when something gets marked "wanted" but are
    # not aware of any config changes that happen later, ie enable or disable providers,
    # so we check whenever config is saved
    # postprocessor is started when something gets marked "snatched"
    # and cancels itself once everything is processed so should be ok
    # but check anyway for completeness...

    myDB = database.DBConnection()
    snatched = myDB.match("SELECT count(*) as counter from wanted WHERE Status = 'Snatched'")
    wanted = myDB.match("SELECT count(*) as counter FROM books WHERE Status = 'Wanted'")
    if snatched:
        ensureRunning('PostProcessor')
    if wanted:
        if lazylibrarian.USE_NZB() or lazylibrarian.USE_TOR() or lazylibrarian.USE_DIRECT():
            ensureRunning('search_book')
        if lazylibrarian.USE_RSS():
            ensureRunning('search_rss_book')
    else:
        scheduleJob('Stop', 'search_book')
        scheduleJob('Stop', 'search_rss_book')
    if lazylibrarian.USE_WISHLIST():
        ensureRunning('search_wishlist')
    else:
        scheduleJob('Stop', 'search_wishlist')

    if lazylibrarian.USE_NZB() or lazylibrarian.USE_TOR() or lazylibrarian.USE_RSS() or lazylibrarian.USE_DIRECT():
        ensureRunning('search_magazines')
    else:
        scheduleJob('Stop', 'search_magazines')

    ensureRunning('authorUpdate')


def showStats():
    gb_status = "Active"
    for entry in lazylibrarian.PROVIDER_BLOCKLIST:
        if entry["name"] == 'googleapis':
            if int(time.time()) < int(entry['resume']):
                gb_status = "Blocked"
            break

    result = ["Cache %i hit%s, %i miss, " % (check_int(lazylibrarian.CACHE_HIT, 0),
                                             plural(check_int(lazylibrarian.CACHE_HIT, 0)),
                                             check_int(lazylibrarian.CACHE_MISS, 0)),
              "Sleep %.3f goodreads, %.3f librarything" % (lazylibrarian.GR_SLEEP, lazylibrarian.LT_SLEEP),
              "GoogleBooks API %i calls, %s" % (lazylibrarian.GB_CALLS, gb_status)]

    myDB = database.DBConnection()
    snatched = myDB.match("SELECT count(*) as counter from wanted WHERE Status = 'Snatched'")
    if snatched['counter']:
        result.append("%i Snatched item%s" % (snatched['counter'], plural(snatched['counter'])))
    else:
        result.append("No Snatched items")

    series_stats = []
    res = myDB.match("SELECT count(*) as counter FROM series")
    series_stats.append(['Series', res['counter']])
    res = myDB.match("SELECT count(*) as counter FROM series WHERE Total>0 and Have=0")
    series_stats.append(['Empty', res['counter']])
    res = myDB.match("SELECT count(*) as counter FROM series WHERE Total>0 AND Have=Total")
    series_stats.append(['Full', res['counter']])
    res = myDB.match('SELECT count(*) as counter FROM series WHERE Status="Ignored"')
    series_stats.append(['Ignored', res['counter']])
    res = myDB.match("SELECT count(*) as counter FROM series WHERE Total=0")
    series_stats.append(['Blank', res['counter']])

    mag_stats = []
    res = myDB.match("SELECT count(*) as counter FROM magazines")
    mag_stats.append(['Magazine', res['counter']])
    res = myDB.match("SELECT count(*) as counter FROM issues")
    mag_stats.append(['Issues', res['counter']])
    cmd = 'select (select count(*) as counter from issues where magazines.title = issues.title) '
    cmd += 'as counter from magazines where counter=0'
    res = myDB.match(cmd)
    mag_stats.append(['Empty', len(res)])

    book_stats = []
    audio_stats = []
    res = myDB.match("SELECT count(*) as counter FROM books")
    book_stats.append(['eBooks', res['counter']])
    audio_stats.append(['Audio', res['counter']])
    for status in ['Have', 'Open', 'Wanted', 'Ignored']:
        res = myDB.match('SELECT count(*) as counter FROM books WHERE Status="%s"' % status)
        book_stats.append([status, res['counter']])
        res = myDB.match('SELECT count(*) as counter FROM books WHERE AudioStatus="%s"' % status)
        audio_stats.append([status, res['counter']])
    for column in ['BookISBN', 'BookDesc', 'BookLang']:
        res = myDB.match("SELECT count(*) as counter FROM books WHERE %s is null or %s = '' or %s = 'Unknown'" % (
            column, column, column))
        book_stats.append([column.replace('Book', 'No-'), res['counter']])

    author_stats = []
    res = myDB.match("SELECT count(*) as counter FROM authors")
    author_stats.append(['Authors', res['counter']])
    for status in ['Active', 'Wanted', 'Ignored', 'Paused']:
        res = myDB.match('SELECT count(*) as counter FROM authors WHERE Status="%s"' % status)
        author_stats.append([status, res['counter']])
    res = myDB.match("SELECT count(*) as counter FROM authors WHERE HaveBooks=0")
    author_stats.append(['Empty', res['counter']])
    res = myDB.match("SELECT count(*) as counter FROM authors WHERE TotalBooks=0")
    author_stats.append(['Blank', res['counter']])
    overdue, _, _, _ = is_overdue()
    author_stats.append(['Overdue', overdue])
    for stats in [author_stats, book_stats, series_stats, audio_stats, mag_stats]:
        header = ''
        data = ''
        for item in stats:
            header += "%8s" % item[0]
            data += "%8i" % item[1]
        result.append('')
        result.append(header)
        result.append(data)
    return result


def showJobs():
    result = []

    for job in lazylibrarian.SCHED.get_jobs():
        job = str(job)
        if "search_magazines" in job:
            jobname = "Magazine search"
        elif "checkForUpdates" in job:
            jobname = "Check LazyLibrarian version"
        elif "search_book" in job:
            jobname = "Book search"
        elif "search_rss_book" in job:
            jobname = "RSS book search"
        elif "search_wishlist" in job:
            jobname = "Wishlist search"
        elif "PostProcessor" in job:
            jobname = "PostProcessor"
        elif "cron_processDir" in job:
            jobname = "PostProcessor"
        elif "authorUpdate" in job:
            jobname = "Update authors"
        elif "sync_to_gr" in job:
            jobname = "Goodreads Sync"
        else:
            jobname = job.split(' ')[0].split('.')[2]

        # jobinterval = job.split('[')[1].split(']')[0]
        jobtime = job.split('at: ')[1].split('.')[0].strip(')')
        jobtime = next_run(jobtime)
        timeparts = jobtime.split(' ')
        if timeparts[0] == '1' and timeparts[1].endswith('s'):
            timeparts[1] = timeparts[1][:-1]
        jobinfo = "%s: Next run in %s %s" % (jobname, timeparts[0], timeparts[1])
        result.append(jobinfo)

    overdue, total, name, days = is_overdue()
    result.append('Oldest author info (%s) is %s day%s old' % (name, days, plural(days)))
    if not overdue:
        result.append("There are no authors overdue update")
    else:
        result.append("Found %s author%s from %s overdue update" % (overdue, plural(overdue), total))
    return result


def clearLog():
    lazylibrarian.LOGLIST = []
    error = False
    if 'windows' in platform.system().lower():
        return "Screen log cleared"

    logger.lazylibrarian_log.stopLogger()
    for f in glob.glob(lazylibrarian.CONFIG['LOGDIR'] + "/*.log*"):
        try:
            os.remove(f)
        except OSError as e:
            error = e.strerror
            logger.debug("Failed to remove %s : %s" % (f, error))

    logger.lazylibrarian_log.initLogger(loglevel=lazylibrarian.LOGLEVEL)

    if error:
        return 'Failed to clear logfiles: %s' % error
    else:
        return "Log cleared, level set to [%s]- Log Directory is [%s]" % (
            lazylibrarian.LOGLEVEL, lazylibrarian.CONFIG['LOGDIR'])


def reverse_readline(filename, buf_size=8192):
    """a generator that returns the lines of a file in reverse order"""
    with open(filename) as fh:
        segment = None
        offset = 0
        fh.seek(0, os.SEEK_END)
        file_size = remaining_size = fh.tell()
        while remaining_size > 0:
            offset = min(file_size, offset + buf_size)
            fh.seek(file_size - offset)
            buf = fh.read(min(remaining_size, buf_size))
            remaining_size -= buf_size
            lines = buf.split('\n')
            # the first line of the buffer is probably not a complete line so
            # we'll save it and append it to the last line of the next buffer
            # we read
            if segment is not None:
                # if the previous chunk starts right from the beginning of line
                # do not concact the segment to the last line of new chunk
                # instead, yield the segment first
                if buf[-1] != '\n':
                    lines[-1] += segment
                else:
                    yield segment
            segment = lines[0]
            for index in range(len(lines) - 1, 0, -1):
                if len(lines[index]):
                    yield lines[index]
        # Don't yield None if the file was empty
        if segment is not None:
            yield segment


# noinspection PyUnresolvedReferences
def logHeader():
    popen_list = [sys.executable, lazylibrarian.FULL_PATH]
    popen_list += lazylibrarian.ARGS
    header = "Startup cmd: %s\n" % str(popen_list)
    header += 'Interface: %s\n' % lazylibrarian.CONFIG['HTTP_LOOK']
    header += 'Loglevel: %s\n' % lazylibrarian.LOGLEVEL
    header += 'Sys_Encoding: %s\n' % lazylibrarian.SYS_ENCODING
    for item in lazylibrarian.CONFIG_GIT:
        if item == 'GIT_UPDATED':
            timestamp = check_int(lazylibrarian.CONFIG[item], 0)
            header += '%s: %s\n' % (item.lower(), time.ctime(timestamp))
        else:
            header += '%s: %s\n' % (item.lower(), lazylibrarian.CONFIG[item])
    header += "Python version: %s\n" % sys.version.split('\n')
    # noinspection PyDeprecation
    if sys.version_info<=(3,7):
        header += "Distribution: %s\n" % str(platform.dist())
    header += "System: %s\n" % str(platform.system())
    header += "Machine: %s\n" % str(platform.machine())
    header += "Platform: %s\n" % str(platform.platform())
    header += "uname: %s\n" % str(platform.uname())
    header += "version: %s\n" % str(platform.version())
    header += "mac_ver: %s\n" % str(platform.mac_ver())
    if 'urllib3' in globals():
        header += "urllib3: %s\n" % getattr(urllib3, '__version__', None)
    else:
        header += "urllib3: missing\n"
    header += "requests: %s\n" % getattr(requests, '__version__', None)
    logger.info('Checking TLS version, you can ignore any "InsecureRequestWarning" message')
    try:
        tls_version = requests.get('https://www.howsmyssl.com/a/check', timeout=30, verify=False).json()['tls_version']
        if '1.2' not in tls_version and '1.3' not in tls_version:
            header += 'tls: missing required functionality. Try upgrading to v1.2 or newer. You have '
    except Exception as e:
        tls_version = str(e)
    header += "tls: %s\n" % tls_version
    header += "cherrypy: %s\n" % getattr(cherrypy, '__version__', None)

    if not lazylibrarian.GROUP_CONCAT:
        # 3.5.4 is the earliest version with GROUP_CONCAT which we use, but is not essential
        header += 'sqlite3: missing required functionality. Try upgrading to v3.5.4 or newer. You have '
    header += "sqlite3: %s\n" % getattr(sqlite3, 'sqlite_version', None)
    try:
        from lib.unrar import rarfile
        version = rarfile.unrarlib.RARGetDllVersion()
        header += "unrar: DLL version %s\n" % version
    except Exception as e:
        header += "unrar: missing: %s\n" % str(e)

    header += "openssl: %s\n" % getattr(ssl, 'OPENSSL_VERSION', None)
    X509 = None
    cryptography = None
    try:
        # pyOpenSSL 0.14 and above use cryptography for OpenSSL bindings. The _x509
        # attribute is only present on those versions.
        # noinspection PyUnresolvedReferences
        import OpenSSL
    except ImportError:
        header += "pyOpenSSL: module missing\n"
        OpenSSL = None

    if OpenSSL:
        try:
            # noinspection PyUnresolvedReferences
            from OpenSSL.crypto import X509
        except ImportError:
            header += "pyOpenSSL.crypto X509: module missing\n"

    if X509:
        # noinspection PyCallingNonCallable
        x509 = X509()
        if getattr(x509, "_x509", None) is None:
            header += "pyOpenSSL: module missing required functionality. Try upgrading to v0.14 or newer. You have "
        header += "pyOpenSSL: %s\n" % getattr(OpenSSL, '__version__', None)

    if OpenSSL:
        try:
            import OpenSSL.SSL
        except (ImportError, AttributeError) as e:
            header += 'pyOpenSSL missing SSL module/attribute: %s\n' % e

    if OpenSSL:
        try:
            # get_extension_for_class method added in `cryptography==1.1`; not available in older versions
            # but need cryptography >= 1.3.4 for access from pyopenssl >= 0.14
            # noinspection PyUnresolvedReferences
            import cryptography
        except ImportError:
            header += "cryptography: module missing\n"

    if cryptography:
        try:
            # noinspection PyUnresolvedReferences
            from cryptography.x509.extensions import Extensions
            if getattr(Extensions, "get_extension_for_class", None) is None:
                header += "cryptography: module missing required functionality."
                header += " Try upgrading to v1.3.4 or newer. You have "
            header += "cryptography: %s\n" % getattr(cryptography, '__version__', None)
        except ImportError:
            header += "cryptography Extensions: module missing\n"

    # noinspection PyBroadException
    try:
        import magic
    except Exception:
        # noinspection PyBroadException
        try:
            import lib.magic as magic
        except Exception:
            magic = None

    if magic:
        try:
            # noinspection PyProtectedMember
            ver = magic.libmagic._name
        except AttributeError:
            ver = 'missing'
        header += "magic: %s\n" % ver
    else:
        header += "magic: missing\n"

    return header


def saveLog():
    if not os.path.exists(lazylibrarian.CONFIG['LOGDIR']):
        return 'LOGDIR does not exist'

    basename = os.path.join(lazylibrarian.CONFIG['LOGDIR'], 'lazylibrarian.log')
    outfile = os.path.join(lazylibrarian.CONFIG['LOGDIR'], 'debug')
    passchars = string.ascii_letters + string.digits + ':_/'  # used by slack, telegram and googlebooks
    redactlist = ['api -> ', 'key -> ', 'secret -> ', 'pass -> ', 'password -> ', 'token -> ', 'keys -> ',
                  'apitoken -> ', 'username -> ', '&r=', 'using api [', 'apikey=', 'key=', 'apikey%3D', "apikey': ",
                  "'--password', u'", "'--password', '", "api:", "keys:", "token:", "secret=", "email_from -> ",
                  "email_to -> ", "email_smtp_user -> "]
    with open(outfile + '.tmp', 'w') as out:
        nextfile = True
        extn = 0
        redacts = 0
        while nextfile:
            fname = basename
            if extn > 0:
                fname = fname + '.' + str(extn)
            if not os.path.exists(fname):
                logger.debug("logfile [%s] does not exist" % fname)
                nextfile = False
            else:
                logger.debug('Processing logfile [%s]' % fname)
                linecount = 0
                for line in reverse_readline(fname):
                    for item in redactlist:
                        startpos = line.find(item)
                        if startpos >= 0:
                            startpos += len(item)
                            endpos = startpos
                            while endpos < len(line) and not line[endpos] in passchars:
                                endpos += 1
                            while endpos < len(line) and line[endpos] in passchars:
                                endpos += 1
                            if endpos != startpos:
                                line = line[:startpos] + '<redacted>' + line[endpos:]
                                redacts += 1

                    out.write("%s\n" % line)
                    if "Debug log ON" in line:
                        logger.debug('Found "Debug log ON" line %s in %s' % (linecount, fname))
                        nextfile = False
                        break
                    linecount += 1
                extn += 1

        if os.path.exists(lazylibrarian.CONFIGFILE):
            out.write('---END-CONFIG---------------------------------\n')
            for line in reverse_readline(lazylibrarian.CONFIGFILE):
                for item in redactlist:
                    item = item.replace('->', '=')
                    startpos = line.find(item)
                    if startpos >= 0:
                        startpos += len(item)
                        endpos = startpos
                        while endpos < len(line) and not line[endpos] in passchars:
                            endpos += 1
                        while endpos < len(line) and line[endpos] in passchars:
                            endpos += 1
                        if endpos != startpos:
                            line = line[:startpos] + '<redacted>' + line[endpos:]
                            redacts += 1
                out.write("%s\n" % line)
            out.write('---CONFIG-------------------------------------\n')

    with open(outfile + '.log', 'w') as logfile:
        logfile.write(logHeader())
        lines = 0
        for line in reverse_readline(outfile + '.tmp'):
            logfile.write("%s\n" % line)
            lines += 1
    os.remove(outfile + '.tmp')
    logger.debug("Redacted %s passwords/apikeys" % redacts)
    logger.debug("%s log lines written to %s" % (lines, outfile + '.log'))
    with zipfile.ZipFile(outfile + '.zip', 'w') as myzip:
        myzip.write(outfile + '.log', 'debug.log')
    os.remove(outfile + '.log')
    return "Debug log saved as %s" % (outfile + '.zip')


def cleanCache():
    """ Remove unused files from the cache - delete if expired or unused.
        Check JSONCache  WorkCache  XMLCache  SeriesCache Author  Book  Magazine
        Check covers and authorimages referenced in the database exist and change database entry if missing """

    myDB = database.DBConnection()
    result = []
    expiry = check_int(lazylibrarian.CONFIG['CACHE_AGE'], 0)
    cache = os.path.join(lazylibrarian.CACHEDIR, "JSONCache")
    cleaned = 0
    kept = 0
    if expiry and os.path.isdir(cache):
        for cached_file in os.listdir(makeBytestr(cache)):
            cached_file = makeUnicode(cached_file)
            target = os.path.join(cache, cached_file)
            cache_modified_time = os.stat(target).st_mtime
            time_now = time.time()
            if cache_modified_time < time_now - (expiry * 24 * 60 * 60):  # expire after this many seconds
                # Cache is old, delete entry
                os.remove(target)
                cleaned += 1
            else:
                kept += 1
    msg = "Cleaned %i file%s from JSONCache, kept %i" % (cleaned, plural(cleaned), kept)
    result.append(msg)
    logger.debug(msg)

    cache = os.path.join(lazylibrarian.CACHEDIR, "XMLCache")
    cleaned = 0
    kept = 0
    if expiry and os.path.isdir(cache):
        for cached_file in os.listdir(makeBytestr(cache)):
            cached_file = makeUnicode(cached_file)
            target = os.path.join(cache, cached_file)
            cache_modified_time = os.stat(target).st_mtime
            time_now = time.time()
            if cache_modified_time < time_now - (expiry * 24 * 60 * 60):  # expire after this many seconds
                # Cache is old, delete entry
                os.remove(target)
                cleaned += 1
            else:
                kept += 1
    msg = "Cleaned %i file%s from XMLCache, kept %i" % (cleaned, plural(cleaned), kept)
    result.append(msg)
    logger.debug(msg)

    cache = os.path.join(lazylibrarian.CACHEDIR, "WorkCache")
    cleaned = 0
    kept = 0
    if os.path.isdir(cache):
        for cached_file in os.listdir(makeBytestr(cache)):
            cached_file = makeUnicode(cached_file)
            target = os.path.join(cache, cached_file)
            try:
                bookid = cached_file.split('.')[0]
            except IndexError:
                logger.error('Clean Cache: Error splitting %s' % cached_file)
                continue
            item = myDB.match('select BookID from books where BookID=?', (bookid,))
            if not item:
                # WorkPage no longer referenced in database, delete cached_file
                os.remove(target)
                cleaned += 1
            else:
                kept += 1
    msg = "Cleaned %i file%s from WorkCache, kept %i" % (cleaned, plural(cleaned), kept)
    result.append(msg)
    logger.debug(msg)

    cache = os.path.join(lazylibrarian.CACHEDIR, "SeriesCache")
    cleaned = 0
    kept = 0
    if os.path.isdir(cache):
        for cached_file in os.listdir(makeBytestr(cache)):
            cached_file = makeUnicode(cached_file)
            target = os.path.join(cache, cached_file)
            try:
                seriesid = cached_file.split('.')[0]
            except IndexError:
                logger.error('Clean Cache: Error splitting %s' % cached_file)
                continue
            item = myDB.match('select SeriesID from series where SeriesID=?', (seriesid,))
            if not item:
                # SeriesPage no longer referenced in database, delete cached_file
                os.remove(target)
                cleaned += 1
            else:
                kept += 1
    msg = "Cleaned %i file%s from SeriesCache, kept %i" % (cleaned, plural(cleaned), kept)
    result.append(msg)
    logger.debug(msg)

    cache = os.path.join(lazylibrarian.CACHEDIR, "magazine")
    cleaned = 0
    kept = 0
    if os.path.isdir(cache):
        # we can clear the magazine cache, it gets rebuilt as required
        # this does not delete our magazine cover files, only the small cached copy
        for cached_file in os.listdir(makeBytestr(cache)):
            cached_file = makeUnicode(cached_file)
            target = os.path.join(cache, cached_file)
            if target.endswith('.jpg'):
                os.remove(target)
                cleaned += 1
            else:
                kept += 1
    msg = "Cleaned %i file%s from magazine cache, kept %i" % (cleaned, plural(cleaned), kept)
    result.append(msg)
    logger.debug(msg)

    cache = lazylibrarian.CACHEDIR
    cleaned = 0
    kept = 0
    cachedir = os.path.join(cache, 'author')
    if os.path.isdir(cachedir):
        for cached_file in os.listdir(makeBytestr(cachedir)):
            cached_file = makeUnicode(cached_file)
            target = os.path.join(cachedir, cached_file)
            if os.path.isfile(target):
                try:
                    imgid = cached_file.split('.')[0].rsplit(os.path.sep)[-1]
                except IndexError:
                    logger.error('Clean Cache: Error splitting %s' % cached_file)
                    continue
                item = myDB.match('select AuthorID from authors where AuthorID=?', (imgid,))
                if not item:
                    # Author Image no longer referenced in database, delete cached_file
                    os.remove(target)
                    cleaned += 1
                else:
                    kept += 1
    cachedir = os.path.join(cache, 'book')
    if os.path.isdir(cachedir):
        for cached_file in os.listdir(makeBytestr(cachedir)):
            cached_file = makeUnicode(cached_file)
            target = os.path.join(cachedir, cached_file)
            if os.path.isfile(target):
                try:
                    imgid = cached_file.split('.')[0].rsplit(os.path.sep)[-1]
                except IndexError:
                    logger.error('Clean Cache: Error splitting %s' % cached_file)
                    continue
                item = myDB.match('select BookID from books where BookID=?', (imgid,))
                if not item:
                    # Book Image no longer referenced in database, delete cached_file
                    os.remove(target)
                    cleaned += 1
                else:
                    kept += 1

    # at this point there should be no more .jpg files in the root of the cachedir
    # any that are still there are for books/authors deleted from database
    for cached_file in os.listdir(makeBytestr(cache)):
        cached_file = makeUnicode(cached_file)
        if cached_file.endswith('.jpg'):
            os.remove(os.path.join(cache, cached_file))
            cleaned += 1
    msg = "Cleaned %i file%s from ImageCache, kept %i" % (cleaned, plural(cleaned), kept)
    result.append(msg)
    logger.debug(msg)

    # verify the cover images referenced in the database are present
    images = myDB.action('select BookImg,BookName,BookID from books')
    cachedir = os.path.join(lazylibrarian.CACHEDIR, 'book')
    cleaned = 0
    kept = 0
    for item in images:
        keep = True
        imgfile = ''
        if item['BookImg'] is None or item['BookImg'] == '':
            keep = False
        if keep and not item['BookImg'].startswith('http') and not item['BookImg'] == "images/nocover.png":
            # html uses '/' as separator, but os might not
            imgname = item['BookImg'].rsplit('/')[-1]
            imgfile = os.path.join(cachedir, imgname)
            if not os.path.isfile(imgfile):
                keep = False
        if keep:
            kept += 1
        else:
            cleaned += 1
            logger.debug('Cover missing for %s %s' % (item['BookName'], imgfile))
            myDB.action('update books set BookImg="images/nocover.png" where Bookid=?', (item['BookID'],))

    msg = "Cleaned %i missing cover file%s, kept %i" % (cleaned, plural(cleaned), kept)
    result.append(msg)
    logger.debug(msg)

    # verify the author images referenced in the database are present
    images = myDB.action('select AuthorImg,AuthorName,AuthorID from authors')
    cachedir = os.path.join(lazylibrarian.CACHEDIR, 'author')
    cleaned = 0
    kept = 0
    for item in images:
        keep = True
        imgfile = ''
        if item['AuthorImg'] is None or item['AuthorImg'] == '':
            keep = False
        if keep and not item['AuthorImg'].startswith('http') and not item['AuthorImg'] == "images/nophoto.png":
            # html uses '/' as separator, but os might not
            imgname = item['AuthorImg'].rsplit('/')[-1]
            imgfile = os.path.join(cachedir, imgname)
            if not os.path.isfile(imgfile):
                keep = False
        if keep:
            kept += 1
        else:
            cleaned += 1
            logger.debug('Image missing for %s %s' % (item['AuthorName'], imgfile))
            myDB.action('update authors set AuthorImg="images/nophoto.png" where AuthorID=?', (item['AuthorID'],))

    msg = "Cleaned %i missing author image%s, kept %i" % (cleaned, plural(cleaned), kept)
    result.append(msg)
    logger.debug(msg)
    return result


def zipAudio(source, zipname):
    """ Zip up all the audiobook parts in source folder to zipname
        Check if zipfile already exists, if not create a new one
        Doesn't actually check for audiobook parts, just zips everything
        Return full path to zipfile
    """
    zip_file = os.path.join(source, zipname + '.zip')
    if not os.path.exists(zip_file):
        logger.debug('Zipping up %s' % zipname)
        cnt = 0
        with zipfile.ZipFile(zip_file, 'w', zipfile.ZIP_DEFLATED) as myzip:
            for rootdir, dirs, filenames in os.walk(makeBytestr(source)):
                rootdir = makeUnicode(rootdir)
                filenames = [makeUnicode(item) for item in filenames]
                for filename in filenames:
                    # don't include self or our special index file
                    if not filename.endswith('.zip') and not filename.endswith('.ll'):
                        cnt += 1
                        myzip.write(os.path.join(rootdir, filename), filename)
        logger.debug('Zipped up %s files' % cnt)
    return zip_file


def runScript(params):
    if platform.system() == "Windows" and params[0].endswith('.py'):
        params.insert(0, sys.executable)
    logger.debug(str(params))
    try:
        p = Popen(params, stdout=PIPE, stderr=PIPE)
        res, err = p.communicate()
        return p.returncode, makeUnicode(res), makeUnicode(err)
    except Exception as e:
        err = "runScript exception: %s %s" % (type(e).__name__, str(e))
        logger.error(err)
        return 1, '', err
