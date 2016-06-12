# Author: Nic Wolfe <nic@wolfeden.ca>
# URL: http://code.google.com/p/sickbeard/
#
# This file is part of Sick Beard.
#
# Sick Beard is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# Sick Beard is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with Sick Beard.  If not, see <http://www.gnu.org/licenses/>.

import platform
import re
import lazylibrarian
import unicodedata
import string
import os
import shutil
import time
from lazylibrarian import logger, database, formatter

USER_AGENT = 'LazyLibrarian' + ' (' + platform.system() + ' ' + platform.release() + ')'

# Notification Types
NOTIFY_SNATCH = 1
NOTIFY_DOWNLOAD = 2

notifyStrings = {}
notifyStrings[NOTIFY_SNATCH] = "Started Download"
notifyStrings[NOTIFY_DOWNLOAD] = "Download Finished"


def schedule_job(action='Start', target=None):
    """ Start or stop or restart a cron job by name eg
        target=search_magazines, target=processDir, target=search_tor_book """
    if target is None:
        return

    if action == 'Stop' or action == 'Restart':
        for job in lazylibrarian.SCHED.get_jobs():
            if target in str(job):
                lazylibrarian.SCHED.unschedule_job(job)
                logger.debug("Stop %s job" % (target))

    if action == 'Start' or action == 'Restart':
        for job in lazylibrarian.SCHED.get_jobs():
            if target in str(job):
                logger.debug("%s %s job, already scheduled" % (action, target))
                return  # return if already running, if not, start a new one
        if 'processDir' in target and int(lazylibrarian.SCAN_INTERVAL):
            lazylibrarian.SCHED.add_interval_job(
                lazylibrarian.postprocess.processDir,
                minutes=int(lazylibrarian.SCAN_INTERVAL))
            logger.debug("%s %s job" % (action, target))
        elif 'search_magazines' in target and int(lazylibrarian.SEARCH_INTERVAL):
            if lazylibrarian.USE_TOR() or lazylibrarian.USE_NZB():
                lazylibrarian.SCHED.add_interval_job(
                    lazylibrarian.searchmag.search_magazines,
                    minutes=int(lazylibrarian.SEARCH_INTERVAL))
                logger.debug("%s %s job" % (action, target))
        elif 'search_nzb_book' in target and int(lazylibrarian.SEARCH_INTERVAL):
            if lazylibrarian.USE_NZB():
                lazylibrarian.SCHED.add_interval_job(
                    lazylibrarian.searchnzb.search_nzb_book,
                    minutes=int(lazylibrarian.SEARCH_INTERVAL))
                logger.debug("%s %s job" % (action, target))
        elif 'search_tor_book' in target and int(lazylibrarian.SEARCH_INTERVAL):
            if lazylibrarian.USE_TOR():
                lazylibrarian.SCHED.add_interval_job(
                    lazylibrarian.searchtorrents.search_tor_book,
                    minutes=int(lazylibrarian.SEARCH_INTERVAL))
                logger.debug("%s %s job" % (action, target))
        elif 'search_rss_book' in target and int(lazylibrarian.SEARCHRSS_INTERVAL):
            if lazylibrarian.USE_RSS():
                lazylibrarian.SCHED.add_interval_job(
                    lazylibrarian.searchrss.search_rss_book,
                    minutes=int(lazylibrarian.SEARCHRSS_INTERVAL))
                logger.debug("%s %s job" % (action, target))
        elif 'checkForUpdates' in target and int(lazylibrarian.VERSIONCHECK_INTERVAL):
            lazylibrarian.SCHED.add_interval_job(
                lazylibrarian.versioncheck.checkForUpdates,
                hours=int(lazylibrarian.VERSIONCHECK_INTERVAL))
            logger.debug("%s %s job" % (action, target))

def restartJobs(start='Restart'):
    schedule_job(start, 'processDir')
    schedule_job(start, 'search_nzb_book')
    schedule_job(start, 'search_tor_book')
    schedule_job(start, 'search_rss_book')
    schedule_job(start, 'search_magazines')
    schedule_job(start, 'checkForUpdates')

def showJobs():
        result = []
        result.append("Cache %i hits, %i miss" % (
            int(lazylibrarian.CACHE_HIT),
            int(lazylibrarian.CACHE_MISS)))
        myDB = database.DBConnection()
        snatched = myDB.action(
            "SELECT count('Status') as counter from wanted WHERE Status = 'Snatched'").fetchone()
        wanted = myDB.action(
            "SELECT count('Status') as counter FROM books WHERE Status = 'Wanted'").fetchone()
        result.append("%i items marked as Snatched" % snatched['counter'])
        result.append("%i items marked as Wanted" % wanted['counter'])
        for job in lazylibrarian.SCHED.get_jobs():
            job = str(job)
            if "search_magazines" in job:
                jobname = "Magazine search"
            elif "checkForUpdates" in job:
                jobname = "Check LazyLibrarian version"
            elif "search_tor_book" in job:
                jobname = "TOR book search"
            elif "search_nzb_book" in job:
                jobname = "NZB book search"
            elif "search_rss_book" in job:
                jobname = "RSS book search"
            elif "processDir" in job:
                jobname = "Process downloads"
            else:
                jobname = job.split(' ')[0].split('.')[2]

            jobinterval = job.split('[')[1].split(']')[0]
            jobtime = job.split('at: ')[1].split('.')[0]
            jobtime = formatter.next_run(jobtime)
            jobinfo = "%s: Next run in %s" % (jobname, jobtime)
            result.append(jobinfo)
        return result

def clearLog():
        logger.lazylibrarian_log.stopLogger()
        error = False
        if os.path.exists(lazylibrarian.LOGDIR):
            try:
                shutil.rmtree(lazylibrarian.LOGDIR)
                os.mkdir(lazylibrarian.LOGDIR)
            except OSError as e:
                error = e
        logger.lazylibrarian_log.initLogger(loglevel=lazylibrarian.LOGLEVEL)

        if error:
            return 'Failed to clear log: %s' % e.strerror
        else:
            lazylibrarian.LOGLIST = []
            return "Log cleared, level set to [%s]- Log Directory is [%s]" % (
                lazylibrarian.LOGLEVEL, lazylibrarian.LOGDIR)

def remove_accents(str_or_unicode):
    try:
        nfkd_form = unicodedata.normalize('NFKD', str_or_unicode)
    except TypeError:
        nfkd_form = unicodedata.normalize('NFKD', str_or_unicode.decode(lazylibrarian.SYS_ENCODING, 'replace'))
    # turn accented chars into non-accented
    stripped = u''.join([c for c in nfkd_form if not unicodedata.combining(c)])
    # now get rid of any other non-ascii
    return stripped.encode('ASCII', 'ignore').decode(lazylibrarian.SYS_ENCODING)
    # returns unicode


def removeDisallowedFilenameChars(filename):
    validFilenameChars = u"-_.() %s%s" % (string.ascii_letters, string.digits)
    try:
        cleanedFilename = unicodedata.normalize('NFKD', filename).encode('ASCII', 'ignore')
    except TypeError:
        cleanedFilename = unicodedata.normalize('NFKD', filename.decode('utf-8')).encode('ASCII', 'ignore')
    # return u''.join(c for c in cleanedFilename if c in validFilenameChars)
    #  does not work on python3, complains c is int
    # if you coerce c to str it fails to match, returns empty string.
    # re.sub works on python2 and 3
    return u'' + re.sub(validFilenameChars, "", str(cleanedFilename))
    # returns unicode

def cleanCache():
    """ Remove unused files from the cache - delete if expired or unused.
        Check JSONCache  WorkCache  XMLCache data/images/cache
        Check covers referenced in the database exist and change if missing """

    myDB = database.DBConnection()

    cache = os.path.join(lazylibrarian.CACHEDIR, "JSONCache")
    cleaned = 0
    kept = 0
    for r, d, f in os.walk(cache):
        for cached_file in f:
            target = os.path.join(r, cached_file)
            cache_modified_time = os.stat(target).st_mtime
            time_now = time.time()
            if cache_modified_time < time_now - (lazylibrarian.CACHE_AGE * 24 * 60 * 60):  # expire after this many seconds
                # Cache is old, delete entry
                os.remove(target)
                cleaned += 1
            else:
                kept += 1
        logger.debug("Cleaned %i files from JSONCache, kept %i" % (cleaned, kept))

    cache = os.path.join(lazylibrarian.CACHEDIR, "XMLCache")
    cleaned = 0
    kept = 0
    for r, d, f in os.walk(cache):
        for cached_file in f:
            target = os.path.join(r, cached_file)
            cache_modified_time = os.stat(target).st_mtime
            time_now = time.time()
            if cache_modified_time < time_now - (lazylibrarian.CACHE_AGE * 24 * 60 * 60):  # expire after this many seconds
                # Cache is old, delete entry
                os.remove(target)
                cleaned += 1
            else:
                kept += 1
        logger.debug("Cleaned %i files from XMLCache, kept %i" % (cleaned, kept))

    cache = os.path.join(lazylibrarian.CACHEDIR, "WorkCache")
    cleaned = 0
    kept = 0
    for r, d, f in os.walk(cache):
        for cached_file in f:
            target = os.path.join(r, cached_file)
            try:
                bookid = cached_file.split('.')[0]
            except IndexError:
                logger.error('Clean Cache: Error splitting %s' % cached_file)
                continue
            item = myDB.action('select BookID from books where BookID="%s"' % bookid).fetchone()
            if not item:
                # WorkPage no longer referenced in database, delete cached_file
                os.remove(target)
                cleaned += 1
            else:
                kept += 1
        logger.debug("Cleaned %i files from WorkCache, kept %i" % (cleaned, kept))

    cache = os.path.join(lazylibrarian.PROG_DIR, 'data' + os.sep + 'images' + os.sep + 'cache')
    cleaned = 0
    kept = 0
    for r, d, f in os.walk(cache):
        for cached_file in f:
            target = os.path.join(r, cached_file)
            try:
                bookid = cached_file.split('.')[0].rsplit(os.sep)[-1]
            except IndexError:
                logger.error('Clean Cache: Error splitting %s' % cached_file)
                continue
            item = myDB.action('select BookID from books where BookID="%s"' % bookid).fetchone()
            if not item:
                # Image no longer referenced in database, delete cached_file
                os.remove(target)
                cleaned += 1
            else:
                kept += 1
        logger.debug("Cleaned %i files from ImageCache, kept %i" % (cleaned, kept))

        # correct any '\' separators in the BookImg links
        cleaned = 0
        covers = myDB.action('select BookImg from books where BookImg like "images\cache\%"')
        for item in covers:
            oldname = item['BookImg']
            newname = oldname.replace('\\', '/')
            myDB.action('update books set BookImg="%s" where BookImg="%s"' % (newname, oldname))
            cleaned += 1
        logger.debug("Corrected %i filenames in ImageCache" % cleaned)

        # verify the cover images referenced in the database are present
        covers = myDB.action('select BookImg,BookName,BookID from books')
        cachedir = os.path.join(lazylibrarian.PROG_DIR, 'data' + os.sep + 'images' + os.sep + 'cache' + os.sep)

        cleaned = 0
        kept = 0
        for item in covers:
            # html uses '/' as separator, but os might not
            imgname = item['BookImg'].rsplit('/')[-1]
            imgfile = cachedir + imgname
            if not os.path.isfile(imgfile) and not item['BookImg'].startswith('http'):
                cleaned += 1
                logger.debug('Cover missing for %s %s' % (item['BookName'], imgfile))
                myDB.action('update books set BookImg="images/nocover.png" where Bookid="%s"' % item['BookID'])
            else:
                kept += 1
        logger.debug("Cleaned %i missing cover files, kept %i" % (cleaned, kept))

