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
    
   
