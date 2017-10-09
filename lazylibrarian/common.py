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
import sys
import platform
import string
import random
import shutil
import threading
import time
import traceback
import lib.zipfile as zipfile
import re

import lazylibrarian
from lazylibrarian import logger, database
from lazylibrarian.formatter import plural, next_run, is_valid_booktype, datecompare, check_int

USER_AGENT = 'LazyLibrarian' + ' (' + platform.system() + ' ' + platform.release() + ')'
# Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/52.0.2743.116 Safari/537.36

# Notification Types
NOTIFY_SNATCH = 1
NOTIFY_DOWNLOAD = 2

notifyStrings = {NOTIFY_SNATCH: "Started Download", NOTIFY_DOWNLOAD: "Added to Library"}


def isValidEmail(email):
    if len(email) > 7:
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


def setperm(file_or_dir):
    """
    Force newly created directories to rwxr-xr-x and files to rw-r--r--
    """
    if not file_or_dir:
        return

    if os.path.isdir(file_or_dir):
        value = lazylibrarian.CONFIG['DIR_PERM']
        if value and value.startswith('0o') and len(value) == 5:
            perm = int(value, 8)
        else:
            perm = 0o755
            value = '0o755'
    elif os.path.isfile(file_or_dir):
        value = lazylibrarian.CONFIG['FILE_PERM']
        if value and value.startswith('0o') and len(value) == 5:
            perm = int(lazylibrarian.CONFIG['FILE_PERM'], 8)
        else:
            perm = 0o644
            value = '0o644'
    else:
        return False
    try:
        os.chmod(file_or_dir, perm)
        return True
    except Exception as e:
        if int(lazylibrarian.LOGLEVEL) > 2:
            logger.debug("Failed to set permission %s for %s: %s %s" % (value, file_or_dir, type(e).__name__, str(e)))
        return False


def any_file(search_dir=None, extn=None):
    # find a file with specified extension in a directory, any will do
    # return full pathname of file, or empty string if none found
    if search_dir is None or extn is None:
        return ""
    # ensure directory is unicode so we get unicode results from listdir
    if isinstance(search_dir, str):
        search_dir = search_dir.decode(lazylibrarian.SYS_ENCODING)
    if os.path.isdir(search_dir):
        for fname in os.listdir(search_dir):
            if fname.endswith(extn):
                return os.path.join(search_dir, fname)
    return ""


def opf_file(search_dir=None):
    return any_file(search_dir, '.opf')


def bts_file(search_dir=None):
    return any_file(search_dir, '.bts')


def csv_file(search_dir=None):
    return any_file(search_dir, '.csv')


def jpg_file(search_dir=None):
    return any_file(search_dir, '.jpg')


def book_file(search_dir=None, booktype=None):
    # find a book/mag file in this directory, any book will do
    # return full pathname of book/mag, or empty string if none found
    if search_dir is None or booktype is None:
        return ""
    # ensure directory is unicode so we get unicode results from listdir
    if isinstance(search_dir, str):
        search_dir = search_dir.decode(lazylibrarian.SYS_ENCODING)
    if search_dir and os.path.isdir(search_dir):
        try:
            for fname in os.listdir(search_dir):
                if is_valid_booktype(fname, booktype=booktype):
                    return os.path.join(search_dir, fname)
        except Exception as e:
            logger.warn('Listdir error [%s]: %s %s' % (search_dir, type(e).__name__, str(e)))
    return ""


def scheduleJob(action='Start', target=None):
    """ Start or stop or restart a cron job by name eg
        target=search_magazines, target=processDir, target=search_book """
    if target is None:
        return

    if action == 'Stop' or action == 'Restart':
        for job in lazylibrarian.SCHED.get_jobs():
            if target in str(job):
                lazylibrarian.SCHED.unschedule_job(job)
                logger.debug("Stop %s job" % target)

    if action == 'Start' or action == 'Restart':
        for job in lazylibrarian.SCHED.get_jobs():
            if target in str(job):
                logger.debug("%s %s job, already scheduled" % (action, target))
                return  # return if already running, if not, start a new one
        if 'processDir' in target and check_int(lazylibrarian.CONFIG['SCAN_INTERVAL'], 0):
            lazylibrarian.SCHED.add_interval_job(
                lazylibrarian.postprocess.cron_processDir,
                minutes=check_int(lazylibrarian.CONFIG['SCAN_INTERVAL'], 0))
            logger.debug("%s %s job in %s minutes" % (action, target, lazylibrarian.CONFIG['SCAN_INTERVAL']))
        elif 'search_magazines' in target and check_int(lazylibrarian.CONFIG['SEARCH_INTERVAL'], 0):
            if lazylibrarian.USE_TOR() or lazylibrarian.USE_NZB() \
                    or lazylibrarian.USE_RSS() or lazylibrarian.USE_DIRECT():
                lazylibrarian.SCHED.add_interval_job(
                    lazylibrarian.searchmag.cron_search_magazines,
                    minutes=check_int(lazylibrarian.CONFIG['SEARCH_INTERVAL'], 0))
                logger.debug("%s %s job in %s minutes" % (action, target, lazylibrarian.CONFIG['SEARCH_INTERVAL']))
        elif 'search_book' in target and check_int(lazylibrarian.CONFIG['SEARCH_INTERVAL'], 0):
            if lazylibrarian.USE_NZB() or lazylibrarian.USE_TOR() or lazylibrarian.USE_DIRECT():
                lazylibrarian.SCHED.add_interval_job(
                    lazylibrarian.searchbook.cron_search_book,
                    minutes=check_int(lazylibrarian.CONFIG['SEARCH_INTERVAL'], 0))
                logger.debug("%s %s job in %s minutes" % (action, target, lazylibrarian.CONFIG['SEARCH_INTERVAL']))
        elif 'search_rss_book' in target and check_int(lazylibrarian.CONFIG['SEARCHRSS_INTERVAL'], 0):
            if lazylibrarian.USE_RSS():
                lazylibrarian.SCHED.add_interval_job(
                    lazylibrarian.searchrss.search_rss_book,
                    minutes=check_int(lazylibrarian.CONFIG['SEARCHRSS_INTERVAL'], 0))
                logger.debug("%s %s job in %s minutes" % (action, target, lazylibrarian.CONFIG['SEARCHRSS_INTERVAL']))
        elif 'checkForUpdates' in target and check_int(lazylibrarian.CONFIG['VERSIONCHECK_INTERVAL'], 0):
            lazylibrarian.SCHED.add_interval_job(
                lazylibrarian.versioncheck.checkForUpdates,
                hours=check_int(lazylibrarian.CONFIG['VERSIONCHECK_INTERVAL'], 0))
            logger.debug("%s %s job in %s hours" % (action, target, lazylibrarian.CONFIG['VERSIONCHECK_INTERVAL']))
        elif 'syncToGoodreads' in target and lazylibrarian.CONFIG['GR_SYNC']:
            if check_int(lazylibrarian.CONFIG['GOODREADS_INTERVAL'], 0):
                lazylibrarian.SCHED.add_interval_job(
                    lazylibrarian.grsync.cron_sync_to_gr,
                    hours=check_int(lazylibrarian.CONFIG['GOODREADS_INTERVAL'], 0))
                logger.debug("%s %s job in %s hours" % (action, target, lazylibrarian.CONFIG['GOODREADS_INTERVAL']))
        elif 'authorUpdate' in target and check_int(lazylibrarian.CONFIG['CACHE_AGE'], 0):
            # Try to get all authors scanned evenly inside the cache age
            minutes = check_int(lazylibrarian.CONFIG['CACHE_AGE'], 0) * 24 * 60
            myDB = database.DBConnection()
            cmd = "select count('AuthorID') as counter from Authors where Status='Active' or Status='Wanted'"
            cmd += " or Status='Loading'"
            authors = myDB.match(cmd)
            authcount = authors['counter']
            if not authcount:
                minutes = 60
            else:
                minutes = int(minutes / authcount)

            if minutes < 10:  # set a minimum interval of 10 minutes so we don't upset goodreads/librarything api
                minutes = 10
            if minutes <= 600:  # for bigger intervals switch to hours
                lazylibrarian.SCHED.add_interval_job(authorUpdate, minutes=minutes)
                logger.debug("%s %s job in %s minutes" % (action, target, minutes))
            else:
                hours = int(minutes / 60)
                lazylibrarian.SCHED.add_interval_job(authorUpdate, hours=hours)
                logger.debug("%s %s job in %s hours" % (action, target, hours))


def authorUpdate():
    threadname = threading.currentThread().name
    if "Thread-" in threadname:
        threading.currentThread().name = "AUTHORUPDATE"
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
                logger.info('Starting update for %s' % author['AuthorName'])
                authorid = author['AuthorID']
                logger.debug(msg)
                # noinspection PyUnresolvedReferences
                lazylibrarian.importer.addAuthorToDB(refresh=True, authorid=authorid)
            else:
                # don't nag. Show info message no more than every 12 hrs, debug message otherwise
                timenow = int(time.time())
                if check_int(lazylibrarian.AUTHORUPDATE_MSG, 0) + 43200 < timenow:
                    logger.info(msg)
                    lazylibrarian.AUTHORUPDATE_MSG = timenow
                else:
                    logger.debug(msg)

    except Exception:
        logger.error('Unhandled exception in AuthorUpdate: %s' % traceback.format_exc())


def aaUpdate(refresh=False):
    try:
        myDB = database.DBConnection()
        cmd = 'SELECT AuthorID from authors WHERE Status="Active" or Status="Loading" or Status="Wanted"'
        cmd += ' order by DateAdded ASC'
        activeauthors = myDB.select(cmd)
        lazylibrarian.AUTHORS_UPDATE = True
        logger.info('Starting update for %i active author%s' % (len(activeauthors), plural(len(activeauthors))))
        for author in activeauthors:
            authorid = author['AuthorID']
            # noinspection PyUnresolvedReferences
            lazylibrarian.importer.addAuthorToDB(refresh=refresh, authorid=authorid)
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
    scheduleJob(start, 'processDir')
    scheduleJob(start, 'search_book')
    scheduleJob(start, 'search_rss_book')
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
    # processdir is started when something gets marked "snatched"
    # and cancels itself once everything is processed so should be ok
    # but check anyway for completeness...

    myDB = database.DBConnection()
    snatched = myDB.match("SELECT count('Status') as counter from wanted WHERE Status = 'Snatched'")
    wanted = myDB.match("SELECT count('Status') as counter FROM books WHERE Status = 'Wanted'")
    if snatched:
        ensureRunning('processDir')
    if wanted:
        if lazylibrarian.USE_NZB() or lazylibrarian.USE_TOR() or lazylibrarian.USE_DIRECT():
            ensureRunning('search_book')
        if lazylibrarian.USE_RSS():
            ensureRunning('search_rss_book')
    else:
        scheduleJob('Stop', 'search_book')
        scheduleJob('Stop', 'search_rss_book')

    if lazylibrarian.USE_NZB() or lazylibrarian.USE_TOR() or lazylibrarian.USE_RSS() or lazylibrarian.USE_DIRECT():
        ensureRunning('search_magazines')
    else:
        scheduleJob('Stop', 'search_magazines')

    ensureRunning('authorUpdate')


def showJobs():
    result = ["Cache %i hit%s, %i miss" % (check_int(lazylibrarian.CACHE_HIT, 0),
                                           plural(check_int(lazylibrarian.CACHE_HIT, 0)),
                                           check_int(lazylibrarian.CACHE_MISS, 0))]
    myDB = database.DBConnection()
    snatched = myDB.match("SELECT count('Status') as counter from wanted WHERE Status = 'Snatched'")
    wanted = myDB.match("SELECT count('Status') as counter FROM books WHERE Status = 'Wanted'")
    result.append("%i item%s marked as Snatched" % (snatched['counter'], plural(snatched['counter'])))
    result.append("%i item%s marked as Wanted" % (wanted['counter'], plural(wanted['counter'])))
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
        elif "processDir" in job:
            jobname = "Process downloads"
        elif "authorUpdate" in job:
            jobname = "Update authors"
        elif "sync_to_gr" in job:
            jobname = "Goodreads Sync"
        else:
            jobname = job.split(' ')[0].split('.')[2]

        # jobinterval = job.split('[')[1].split(']')[0]
        jobtime = job.split('at: ')[1].split('.')[0]
        jobtime = next_run(jobtime)
        jobinfo = "%s: Next run in %s" % (jobname, jobtime)
        result.append(jobinfo)

    cmd = 'SELECT AuthorID, AuthorName, DateAdded from authors WHERE Status="Active" or Status="Loading"'
    cmd += 'or Status="Wanted" order by DateAdded ASC'
    author = myDB.match(cmd)
    dtnow = datetime.datetime.now()
    diff = datecompare(dtnow.strftime("%Y-%m-%d"), author['DateAdded'])
    result.append('Oldest author info (%s) is %s day%s old' % (author['AuthorName'], diff, plural(diff)))

    return result


def clearLog():
    logger.lazylibrarian_log.stopLogger()
    error = False
    if os.path.exists(lazylibrarian.CONFIG['LOGDIR']):
        try:
            shutil.rmtree(lazylibrarian.CONFIG['LOGDIR'])
            os.mkdir(lazylibrarian.CONFIG['LOGDIR'])
        except OSError as e:
            error = e.strerror
    logger.lazylibrarian_log.initLogger(loglevel=lazylibrarian.LOGLEVEL)

    if error:
        return 'Failed to clear log: %s' % error
    else:
        lazylibrarian.LOGLIST = []
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
                if buf[-1] is not '\n':
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


def saveLog():
    if not os.path.exists(lazylibrarian.CONFIG['LOGDIR']):
        return 'LOGDIR does not exist'

    popen_list = [sys.executable, lazylibrarian.FULL_PATH]
    popen_list += lazylibrarian.ARGS
    header = "Startup cmd: %s\n" % str(popen_list)
    header += 'Interface: %s\n' % lazylibrarian.CONFIG['HTTP_LOOK']
    header += 'Loglevel: %s\n' % lazylibrarian.LOGLEVEL
    for item in lazylibrarian.CONFIG_GIT:
        header += '%s: %s\n' % (item.lower(), lazylibrarian.CONFIG[item])
    header += "Python version: %s\n" % sys.version.split('\n')
    header += "Distribution: %s\n" % str(platform.dist())
    header += "System: %s\n" % str(platform.system())
    header += "Machine: %s\n" % str(platform.machine())
    header += "Platform: %s\n" % str(platform.platform())
    header += "uname: %s\n" % str(platform.uname())
    header += "version: %s\n" % str(platform.version())
    header += "mac_ver: %s\n" % str(platform.mac_ver())
    header += "sqlite3: %s\n" % lazylibrarian.SQLITEVERSION

    basename = os.path.join(lazylibrarian.CONFIG['LOGDIR'], 'lazylibrarian.log')
    outfile = os.path.join(lazylibrarian.CONFIG['LOGDIR'], 'debug')
    passchars = string.ascii_letters + string.digits + '_/'  # _/ used by slack and googlebooks
    redactlist = ['api -> ', 'apikey -> ', 'pass -> ', 'password -> ', 'token -> ', 'using api [',
                  'apikey=', 'key=', 'apikey%3D', "apikey': u'", "apikey': ', 'keys ->'"]
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

    with open(outfile + '.log', 'w') as logfile:
        logfile.write(header)
        lines = 0  # len(header.split('\n'))
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
    cache = os.path.join(lazylibrarian.CACHEDIR, "JSONCache")
    # ensure directory is unicode so we get unicode results from listdir
    if isinstance(cache, str):
        cache = cache.decode(lazylibrarian.SYS_ENCODING)
    cleaned = 0
    kept = 0
    if os.path.isdir(cache):
        for cached_file in os.listdir(cache):
            target = os.path.join(cache, cached_file)
            cache_modified_time = os.stat(target).st_mtime
            time_now = time.time()
            if cache_modified_time < time_now - (
                                lazylibrarian.CONFIG['CACHE_AGE'] * 24 * 60 * 60):  # expire after this many seconds
                # Cache is old, delete entry
                os.remove(target)
                cleaned += 1
            else:
                kept += 1
    msg = "Cleaned %i file%s from JSONCache, kept %i" % (cleaned, plural(cleaned), kept)
    result.append(msg)
    logger.debug(msg)

    cache = os.path.join(lazylibrarian.CACHEDIR, "XMLCache")
    # ensure directory is unicode so we get unicode results from listdir
    if isinstance(cache, str):
        cache = cache.decode(lazylibrarian.SYS_ENCODING)
    cleaned = 0
    kept = 0
    if os.path.isdir(cache):
        for cached_file in os.listdir(cache):
            target = os.path.join(cache, cached_file)
            cache_modified_time = os.stat(target).st_mtime
            time_now = time.time()
            if cache_modified_time < time_now - (
                                lazylibrarian.CONFIG['CACHE_AGE'] * 24 * 60 * 60):  # expire after this many seconds
                # Cache is old, delete entry
                os.remove(target)
                cleaned += 1
            else:
                kept += 1
    msg = "Cleaned %i file%s from XMLCache, kept %i" % (cleaned, plural(cleaned), kept)
    result.append(msg)
    logger.debug(msg)

    cache = os.path.join(lazylibrarian.CACHEDIR, "WorkCache")
    # ensure directory is unicode so we get unicode results from listdir
    if isinstance(cache, str):
        cache = cache.decode(lazylibrarian.SYS_ENCODING)
    cleaned = 0
    kept = 0
    if os.path.isdir(cache):
        for cached_file in os.listdir(cache):
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
    # ensure directory is unicode so we get unicode results from listdir
    if isinstance(cache, str):
        cache = cache.decode(lazylibrarian.SYS_ENCODING)
    cleaned = 0
    kept = 0
    if os.path.isdir(cache):
        for cached_file in os.listdir(cache):
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
    # ensure directory is unicode so we get unicode results from listdir
    if isinstance(cache, str):
        cache = cache.decode(lazylibrarian.SYS_ENCODING)
    cleaned = 0
    kept = 0
    if os.path.isdir(cache):
        # we can clear the magazine cache, it gets rebuilt as required
        for cached_file in os.listdir(cache):
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
        for cached_file in os.listdir(cachedir):
            target = os.path.join(cachedir, cached_file)
            if os.path.isfile(target):
                try:
                    imgid = cached_file.split('.')[0].rsplit(os.sep)[-1]
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
        for cached_file in os.listdir(cachedir):
            target = os.path.join(cachedir, cached_file)
            if os.path.isfile(target):
                try:
                    imgid = cached_file.split('.')[0].rsplit(os.sep)[-1]
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
    for cached_file in os.listdir(cache):
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
