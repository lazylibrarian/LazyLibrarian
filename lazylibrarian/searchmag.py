#  This file is part of Lazylibrarian.
#  Lazylibrarian is free software':'you can redistribute it and/or modify
#  it under the terms of the GNU General Public License as published by
#  the Free Software Foundation, either version 3 of the License, or
#  (at your option) any later version.
#  Lazylibrarian is distributed in the hope that it will be useful,
#  but WITHOUT ANY WARRANTY; without even the implied warranty of
#  MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
#  GNU General Public License for more details.
#  You should have received a copy of the GNU General Public License
#  along with Lazylibrarian.  If not, see <http://www.gnu.org/licenses/>.


import datetime
import re
import threading
import time
import traceback
from lib.six import PY2

import lazylibrarian
from lazylibrarian import logger, database
from lazylibrarian.common import scheduleJob
from lazylibrarian.downloadmethods import NZBDownloadMethod, TORDownloadMethod, DirectDownloadMethod
from lazylibrarian.formatter import plural, now, unaccented_str, replace_all, unaccented, \
    nzbdate2format, getList, month2num, datecompare, check_int, check_year
from lazylibrarian.notifiers import notify_snatch, custom_notify_snatch
from lazylibrarian.providers import IterateOverNewzNabSites, IterateOverTorrentSites, IterateOverRSSSites, \
    IterateOverDirectSites


def cron_search_magazines():
    if 'SEARCHALLMAG' not in [n.name for n in [t for t in threading.enumerate()]]:
        search_magazines()


def search_magazines(mags=None, reset=False):
    # produce a list of magazines to search for, tor, nzb, torznab, rss
    # noinspection PyBroadException
    try:
        threadname = threading.currentThread().name
        if "Thread-" in threadname:
            if mags is None:
                threading.currentThread().name = "SEARCHALLMAG"
            else:
                threading.currentThread().name = "SEARCHMAG"

        myDB = database.DBConnection()
        searchlist = []

        if mags is None:  # backlog search
            searchmags = myDB.select('SELECT Title, Regex, LastAcquired, \
                                 IssueDate from magazines WHERE Status="Active"')
        else:
            searchmags = []
            for magazine in mags:
                searchmags_temp = myDB.select('SELECT Title, Regex, LastAcquired, IssueDate from magazines \
                                          WHERE Title=? AND Status="Active"', (magazine['bookid'],))
                for terms in searchmags_temp:
                    searchmags.append(terms)

        if len(searchmags) == 0:
            threading.currentThread().name = "WEBSERVER"
            return

        # should clear old search results as might not be available any more
        # ie torrent not available, changed providers, out of news server retention etc.
        # Only delete the "skipped" ones, not wanted/snatched/processed/ignored
        logger.debug("Removing old magazine search results")
        myDB.action('DELETE from pastissues WHERE Status="Skipped"')

        logger.info('Searching for %i magazine%s' % (len(searchmags), plural(len(searchmags))))

        for searchmag in searchmags:
            bookid = searchmag['Title']
            searchterm = searchmag['Regex']

            if not searchterm:
                dic = {'...': '', ' & ': ' ', ' = ': ' ', '?': '', '$': 's', ' + ': ' ', '"': '', ',': '', '*': ''}
                # strip accents from the magazine title for easier name-matching
                searchterm = unaccented_str(searchmag['Title'])
                if not searchterm:
                    # unless there are no ascii characters left
                    searchterm = searchmag['Title']
                searchterm = replace_all(searchterm, dic)

                searchterm = re.sub('[.\-/]', ' ', searchterm)
                if PY2:
                    searchterm = searchterm.encode(lazylibrarian.SYS_ENCODING)

            searchlist.append({"bookid": bookid, "searchterm": searchterm})

        if not searchlist:
            logger.warn('There is nothing to search for.  Mark some magazines as active.')

        for book in searchlist:

            resultlist = []

            if lazylibrarian.USE_NZB():
                resultlist, nproviders = IterateOverNewzNabSites(book, 'mag')
                if not nproviders:
                    # don't nag. Show warning message no more than every 20 mins
                    timenow = int(time.time())
                    if check_int(lazylibrarian.NO_NZB_MSG, 0) + 1200 < timenow:
                        logger.warn('No nzb providers are available. Check config and blocklist')
                        lazylibrarian.NO_NZB_MSG = timenow

            if lazylibrarian.USE_DIRECT():
                dir_resultlist, nproviders = IterateOverDirectSites(book, 'mag')
                if not nproviders:
                    # don't nag. Show warning message no more than every 20 mins
                    timenow = int(time.time())
                    if check_int(lazylibrarian.NO_DIRECT_MSG, 0) + 1200 < timenow:
                        logger.warn('No direct providers are available. Check config and blocklist')
                        lazylibrarian.NO_DIRECT_MSG = timenow

                if dir_resultlist:
                    for item in dir_resultlist:  # reformat the results so they look like nzbs
                        resultlist.append({
                            'bookid': item['bookid'],
                            'nzbprov': item['tor_prov'],
                            'nzbtitle': item['tor_title'],
                            'nzburl': item['tor_url'],
                            'nzbdate': 'Fri, 01 Jan 1970 00:00:00 +0100',  # fake date as none returned
                            'nzbsize': item['tor_size'],
                            'nzbmode': 'torrent'
                        })

            if lazylibrarian.USE_TOR():
                tor_resultlist, nproviders = IterateOverTorrentSites(book, 'mag')
                if not nproviders:
                    # don't nag. Show warning message no more than every 20 mins
                    timenow = int(time.time())
                    if check_int(lazylibrarian.NO_TOR_MSG, 0) + 1200 < timenow:
                        logger.warn('No tor providers are available. Check config and blocklist')
                        lazylibrarian.NO_TOR_MSG = timenow

                if tor_resultlist:
                    for item in tor_resultlist:  # reformat the torrent results so they look like nzbs
                        resultlist.append({
                            'bookid': item['bookid'],
                            'nzbprov': item['tor_prov'],
                            'nzbtitle': item['tor_title'],
                            'nzburl': item['tor_url'],
                            'nzbdate': 'Fri, 01 Jan 1970 00:00:00 +0100',  # fake date as none returned from torrents
                            'nzbsize': item['tor_size'],
                            'nzbmode': 'torrent'
                        })

            if lazylibrarian.USE_RSS():
                rss_resultlist, nproviders = IterateOverRSSSites()
                if not nproviders:
                    # don't nag. Show warning message no more than every 20 mins
                    timenow = int(time.time())
                    if check_int(lazylibrarian.NO_RSS_MSG, 0) + 1200 < timenow:
                        logger.warn('No rss providers are available. Check config and blocklist')
                        lazylibrarian.NO_RSS_MSG = timenow

                if rss_resultlist:
                    for item in rss_resultlist:  # reformat the rss results so they look like nzbs
                        resultlist.append({
                            'bookid': book['bookid'],
                            'nzbprov': item['tor_prov'],
                            'nzbtitle': item['tor_title'],
                            'nzburl': item['tor_url'],
                            'nzbdate':
                                item['tor_date'],  # may be fake date as none returned from rss torrents, only rss nzb
                            'nzbsize': item['tor_size'],
                            'nzbmode': item['tor_type']
                        })

            if not resultlist:
                logger.debug("No results for magazine %s" % book['searchterm'])
            else:
                bad_name = 0
                bad_date = 0
                old_date = 0
                rejects = 0
                total_nzbs = 0
                new_date = 0
                maglist = []
                issues = []
                bookid = ''
                for nzb in resultlist:
                    total_nzbs += 1
                    bookid = nzb['bookid']
                    # strip accents from the magazine title for easier name-matching
                    nzbtitle = unaccented_str(nzb['nzbtitle'])
                    if not nzbtitle:
                        # unless it's not a latin-1 encodable name
                        nzbtitle = nzb['nzbtitle']
                    nzbtitle = nzbtitle.replace('"', '').replace("'", "")  # suppress " in titles
                    nzburl = nzb['nzburl']
                    nzbprov = nzb['nzbprov']
                    nzbdate_temp = nzb['nzbdate']
                    nzbsize_temp = nzb['nzbsize']
                    nzbsize_temp = check_int(nzbsize_temp, 1000)  # not all torrents returned by torznab have a size
                    nzbsize = round(float(nzbsize_temp) / 1048576, 2)
                    nzbdate = nzbdate2format(nzbdate_temp)
                    nzbmode = nzb['nzbmode']

                    # Need to make sure that substrings of magazine titles don't get found
                    # (e.g. Maxim USA will find Maximum PC USA) so split into "words"
                    dic = {'.': ' ', '-': ' ', '/': ' ', '+': ' ', '_': ' ', '(': '', ')': '', '[': ' ', ']': ' ',
                           '#': '# '}
                    nzbtitle_formatted = replace_all(nzbtitle, dic).strip()
                    # remove extra spaces if they're in a row
                    nzbtitle_formatted = " ".join(nzbtitle_formatted.split())
                    nzbtitle_exploded = nzbtitle_formatted.split(' ')

                    results = myDB.match('SELECT * from magazines WHERE Title=?', (bookid,))
                    if not results:
                        logger.debug('Magazine [%s] does not match search term [%s].' % (nzbtitle, bookid))
                        bad_name += 1
                    else:
                        rejected = False
                        maxsize = check_int(lazylibrarian.CONFIG['REJECT_MAGSIZE'], 0)
                        if maxsize and nzbsize > maxsize:
                            logger.debug("Rejecting %s, too large" % nzbtitle)
                            rejected = True

                        if not rejected:
                            minsize = check_int(lazylibrarian.CONFIG['REJECT_MAGMIN'], 0)
                            if minsize and nzbsize < minsize:
                                logger.debug("Rejecting %s, too small" % nzbtitle)
                                rejected = True

                        if not rejected:
                            if ' ' in bookid:
                                bookid_exploded = bookid.split(' ')
                            else:
                                bookid_exploded = [bookid]

                            # Check nzb has magazine title and a date/issue nr
                            # eg The MagPI July 2015

                            if len(nzbtitle_exploded) > len(bookid_exploded):
                                # needs to be longer as it has to include a date
                                # check all the words in the mag title are in the nzbtitle
                                rejected = False
                                wlist = []
                                for word in nzbtitle_exploded:
                                    wlist.append(unaccented(word).lower())
                                for word in bookid_exploded:
                                    if unaccented(word).lower() not in wlist:
                                        rejected = True
                                        break

                                if rejected:
                                    logger.debug(
                                        "Magazine title match failed " + bookid + " for " + nzbtitle_formatted)
                                else:
                                    logger.debug(
                                        "Magazine title matched " + bookid + " for " + nzbtitle_formatted)
                            else:
                                logger.debug("Magazine name too short (%s)" % len(nzbtitle_exploded))
                                rejected = True

                        if not rejected:
                            blocked = myDB.match('SELECT * from wanted WHERE NZBurl=? and Status="Failed"', (nzburl,))
                            if blocked:
                                logger.debug("Rejecting %s, blacklisted at %s" %
                                             (nzbtitle_formatted, blocked['NZBprov']))
                                rejected = True

                        if not rejected:
                            reject_list = getList(str(results['Reject']).lower())
                            reject_list += getList(lazylibrarian.CONFIG['REJECT_MAGS'])
                            lower_title = unaccented(nzbtitle_formatted).lower()
                            lower_bookid = unaccented(bookid).lower()
                            if reject_list:
                                if lazylibrarian.LOGLEVEL > 2:
                                    logger.debug('Reject: %s' % str(reject_list))
                                    logger.debug('Title: %s' % lower_title)
                                    logger.debug('Bookid: %s' % lower_bookid)
                            for word in reject_list:
                                if word in lower_title and word not in lower_bookid:
                                    rejected = True
                                    logger.debug("Rejecting %s, contains %s" % (nzbtitle_formatted, word))
                                    break

                        if rejected:
                            rejects += 1
                        else:
                            regex_pass, issuedate, year = get_issue_date(nzbtitle_exploded)
                            if regex_pass:
                                logger.debug('Issue %s (regex %s) for %s ' %
                                             (issuedate, regex_pass, nzbtitle_formatted))
                            else:
                                logger.debug('Magazine %s not in a recognised date format.' % nzbtitle_formatted)
                                bad_date += 1
                                # allow issues with good name but bad date to be included
                                # so user can manually select them, incl those with issue numbers
                                issuedate = "1970-01-01"  # provide a fake date for bad-date issues

                            # wanted issues go into wanted table marked "Wanted"
                            #  the rest into pastissues table marked "Skipped" or "Have"
                            insert_table = "pastissues"
                            comp_date = 0
                            control_date = results['IssueDate']
                            if control_date is None:  # we haven't got any copies of this magazine yet
                                # get a rough time just over MAX_AGE days ago to compare to, in format yyyy-mm-dd
                                # could perhaps calc differently for weekly, biweekly etc
                                # For magazines with only an issue number use zero as we can't tell age

                                if str(issuedate).isdigit():
                                    logger.debug('Magazine comparing issue numbers (%s)' % issuedate)
                                    control_date = 0
                                elif re.match('\d+-\d\d-\d\d', str(issuedate)):
                                    start_time = time.time()
                                    start_time -= int(
                                        lazylibrarian.CONFIG['MAG_AGE']) * 24 * 60 * 60  # number of seconds in days
                                    if start_time < 0:  # limit of unixtime (1st Jan 1970)
                                        start_time = 0
                                    control_date = time.strftime("%Y-%m-%d", time.localtime(start_time))
                                    logger.debug('Magazine date comparing to %s' % control_date)
                                else:
                                    logger.debug('Magazine unable to find comparison type [%s]' % issuedate)
                                    control_date = 0

                            if str(control_date).isdigit() and str(issuedate).isdigit():
                                # for issue numbers, check if later than last one we have
                                if not control_date:
                                    comp_date = issuedate
                                elif not year:
                                    comp_date = int(issuedate) - int(control_date)
                                else:
                                    # if it's last year's issue 3, not this years issue 3...
                                    if year < int(datetime.date.today().year):
                                        comp_date = 0
                                issuedate = "%s" % issuedate
                                issuedate = issuedate.zfill(4)  # pad so we sort correctly
                            elif re.match('\d+-\d\d-\d\d', str(control_date)) and \
                                    re.match('\d+-\d\d-\d\d', str(issuedate)):
                                # only grab a copy if it's newer than the most recent we have,
                                # or newer than a month ago if we have none
                                comp_date = datecompare(issuedate, control_date)
                            else:
                                # invalid comparison of date and issue number
                                comp_date = 0
                                if re.match('\d+-\d\d-\d\d', str(control_date)):
                                    if regex_pass > 7 and year:
                                        # we think it was an issue number, but could be a date
                                        year = check_int(year, 0)
                                        issuenum = check_int(issuedate, 0)
                                        if year and 1 <= issuenum <= 12:
                                            issuedate = "%04d-%02d-01" % (year, issuenum)
                                            comp_date = datecompare(issuedate, control_date)
                                    if not comp_date:
                                        logger.debug('Magazine %s failed: Expecting a date' % nzbtitle_formatted)
                                else:
                                    logger.debug('Magazine %s failed: Expecting issue number' % nzbtitle_formatted)
                                if not comp_date:
                                    bad_date += 1
                                    issuedate = "1970-01-01"  # this is our fake date for ones we can't decipher

                            if comp_date > 0:
                                # keep track of what we're going to download so we don't download dupes
                                new_date += 1
                                issue = bookid + ',' + issuedate
                                if issue not in issues:
                                    maglist.append({
                                        'bookid': bookid,
                                        'nzbprov': nzbprov,
                                        'nzbtitle': nzbtitle,
                                        'nzburl': nzburl,
                                        'nzbmode': nzbmode
                                    })
                                    logger.debug('This issue of %s is new, downloading' % nzbtitle_formatted)
                                    issues.append(issue)
                                    logger.debug('Magazine request number %s' % len(issues))
                                    if lazylibrarian.LOGLEVEL > 2:
                                        logger.debug(str(issues))
                                    insert_table = "wanted"
                                    nzbdate = now()  # when we asked for it
                                else:
                                    logger.debug('This issue of %s is already flagged for download' % issue)
                            else:
                                if issuedate != "1970-01-01":  # this is our fake date for ones we can't decipher
                                    logger.debug('This issue of %s is unknown age; skipping.' % nzbtitle_formatted)
                                else:
                                    logger.debug('This issue of %s is old; skipping.' % nzbtitle_formatted)
                                    old_date += 1

                            # store only the _new_ matching results
                            #  Don't add a new entry if this issue has been found on an earlier search
                            #  and status has been user-set ( we only delete the "Skipped" ones )
                            #  In "wanted" table it might be already snatched/downloading/processing

                            mag_entry = myDB.match('SELECT Status from %s WHERE NZBtitle=? and NZBprov=?' %
                                                   insert_table, (nzbtitle, nzbprov))
                            if mag_entry:
                                if lazylibrarian.LOGLEVEL > 2:
                                    logger.debug('%s is already in %s marked %s' %
                                                 (nzbtitle, insert_table, mag_entry['Status']))
                            else:
                                controlValueDict = {
                                    "NZBtitle": nzbtitle,
                                    "NZBprov": nzbprov
                                }
                                if insert_table == 'pastissues':
                                    # try to mark ones we've already got
                                    match = myDB.match("SELECT * from issues WHERE Title=? AND IssueDate=?",
                                                       (bookid, issuedate))
                                    if match:
                                        insert_status = "Have"
                                    else:
                                        insert_status = "Skipped"
                                else:
                                    insert_status = "Wanted"
                                newValueDict = {
                                    "NZBurl": nzburl,
                                    "BookID": bookid,
                                    "NZBdate": nzbdate,
                                    "AuxInfo": issuedate,
                                    "Status": insert_status,
                                    "NZBsize": nzbsize,
                                    "NZBmode": nzbmode
                                }
                                myDB.upsert(insert_table, newValueDict, controlValueDict)
                                if lazylibrarian.LOGLEVEL > 2:
                                    logger.debug('Added %s to %s marked %s' % (nzbtitle, insert_table, insert_status))

                msg = 'Found %i result%s for %s. %i new,' % (total_nzbs, plural(total_nzbs), bookid, new_date)
                msg += ' %i old, %i fail date, %i fail name,' % (old_date, bad_date, bad_name)
                msg += ' %i rejected: %i to download' % (rejects, len(maglist))
                logger.info(msg)

                for magazine in maglist:
                    if magazine['nzbmode'] in ["torznab", "torrent", "magnet"]:
                        snatch = TORDownloadMethod(
                            magazine['bookid'],
                            magazine['nzbtitle'],
                            magazine['nzburl'],
                            'magazine')
                    elif 'libgen' in magazine['nzbprov']:
                        snatch = DirectDownloadMethod(
                            magazine['bookid'],
                            magazine['nzbtitle'],
                            magazine['nzburl'],
                            bookid,
                            'magazine')
                    else:
                        snatch = NZBDownloadMethod(
                            magazine['bookid'],
                            magazine['nzbtitle'],
                            magazine['nzburl'],
                            'magazine')
                    if snatch:
                        logger.info('Downloading %s from %s' % (magazine['nzbtitle'], magazine["nzbprov"]))
                        notify_snatch("Magazine %s from %s at %s" %
                                      (unaccented(magazine['nzbtitle']), magazine["nzbprov"], now()))
                        custom_notify_snatch("%s %s" % (magazine['bookid'], magazine['nzburl']))
                        scheduleJob(action='Start', target='processDir')

        if reset:
            scheduleJob(action='Restart', target='search_magazines')

        logger.info("Search for magazines complete")

    except Exception:
        logger.error('Unhandled exception in search_magazines: %s' % traceback.format_exc())
    finally:
        threading.currentThread().name = "WEBSERVER"


def get_issue_date(nzbtitle_exploded):
    regex_pass = 0
    issuedate = ''
    year = 0
    # Magazine names have many different styles of date
    # These are the ones we can currently match...
    # 1 MonthName MonthName YYYY for bimonthly
    # 2 Issue nn, MonthName YYYY
    # 3 DD MonthName YYYY
    # 4 MonthName YYYY
    # 5 MonthName DD YYYY or MonthName DD, YYYY
    # 6 YYYY MM DD
    # 7 YYYY MM
    # 8 Issue/No/Nr/Vol/# nn, YYYY
    # 9 Issue/No/Nr/Vol/# nn
    # 10 nn YYYY issue number without Issue/No/Nr/Vol/# in front
    # 11 issue and year as a single 6 digit string eg 222015
    # 12 3 or more digit zero padded issue number eg 0063
    #
    pos = 0
    while pos < len(nzbtitle_exploded):
        year = check_year(nzbtitle_exploded[pos])
        if year and pos:
            month = month2num(nzbtitle_exploded[pos - 1])
            if month:
                if pos > 1:
                    month2 = month2num(nzbtitle_exploded[pos - 2])
                    if month2:
                        # bimonthly, for now just use first month
                        month = min(month, month2)
                        day = 1
                        regex_pass = 1
                    else:
                        day = check_int(nzbtitle_exploded[pos - 2], 1)
                        if day > 31:  # probably issue number nn
                            regex_pass = 2
                            day = 1
                        else:
                            regex_pass = 3
                else:
                    regex_pass = 4
                    day = 1

                issuedate = "%04d-%02d-%02d" % (year, month, day)
                try:
                    _ = datetime.date(year, month, day)
                    break
                except ValueError:
                    regex_pass = 0
        pos += 1

    # MonthName DD YYYY or MonthName DD, YYYY
    if not regex_pass:
        pos = 0
        while pos < len(nzbtitle_exploded):
            year = check_year(nzbtitle_exploded[pos])
            if year and (pos > 1):
                month = month2num(nzbtitle_exploded[pos - 2])
                if month:
                    day = check_int(nzbtitle_exploded[pos - 1].rstrip(','), 1)
                    try:
                        _ = datetime.date(year, month, day)
                        issuedate = "%04d-%02d-%02d" % (year, month, day)
                        regex_pass = 5
                        break
                    except ValueError:
                        regex_pass = 0
            pos += 1

    # YYYY MM or YYYY MM DD
    if not regex_pass:
        pos = 0
        while pos < len(nzbtitle_exploded):
            year = check_year(nzbtitle_exploded[pos])
            if year and pos + 1 < len(nzbtitle_exploded):
                month = check_int(nzbtitle_exploded[pos + 1], 0)
                if month:
                    if pos + 2 < len(nzbtitle_exploded):
                        day = check_int(nzbtitle_exploded[pos + 2], 1)
                        regex_pass = 6
                    else:
                        regex_pass = 7
                        day = 1
                    try:
                        _ = datetime.date(year, month, day)
                        issuedate = "%04d-%02d-%02d" % (year, month, day)
                        break
                    except ValueError:
                        regex_pass = 0
            pos += 1

    # Issue/No/Nr/Vol/# nn, YYYY or Issue/No/Nr/Vol/# nn
    if not regex_pass:
        nouns = ["issue", "iss", "no", "nr", "vol", "volume", '#']
        pos = 0
        while pos < len(nzbtitle_exploded):
            if nzbtitle_exploded[pos].lower().strip('.') in nouns:
                if pos + 1 < len(nzbtitle_exploded):
                    issue = check_int(nzbtitle_exploded[pos + 1], 0)
                    if issue:
                        issuedate = str(issue)  # 4 == 04 == 004
                        if pos + 2 < len(nzbtitle_exploded):
                            year = check_year(nzbtitle_exploded[pos + 2])
                            regex_pass = 8  # Issue/No/Nr/Vol nn, YYYY
                        else:
                            # year = 0
                            regex_pass = 9  # Issue/No/Nr/Vol nn
                        break
            pos += 1

    # nn YYYY issue number without "Nr" before it
    if not regex_pass:
        pos = 1
        while pos < len(nzbtitle_exploded):
            year = check_year(nzbtitle_exploded[pos])
            if year:
                issue = check_int(nzbtitle_exploded[pos - 1], 0)
                if issue:
                    issuedate = str(issue)  # 4 == 04 == 004
                    regex_pass = 10
                    # if year < int(datetime.date.today().year):
                    #     issuedate = '0'  # it's old
                    break
            pos += 1

    # issue and year as a single 6 digit string eg 222015
    if not regex_pass:
        pos = 0
        while pos < len(nzbtitle_exploded):
            issue = nzbtitle_exploded[pos]
            if issue.isdigit() and len(issue) == 6:
                year = int(issue[2:])
                issue = int(issue[:2])
                issuedate = str(issue)  # 4 == 04 == 004
                regex_pass = 11
                if year < int(datetime.date.today().year):
                    issuedate = '0'  # it's old
                break
            pos += 1

    # issue as a 3 or more digit string with leading zero eg 0063
    if not regex_pass:
        pos = 0
        while pos < len(nzbtitle_exploded):
            issue = nzbtitle_exploded[pos]
            if issue.isdigit() and len(issue) > 2 and issue[0] == '0':
                issuedate = issue
                year = 0
                regex_pass = 12
                break
            pos += 1

    return regex_pass, issuedate, year
