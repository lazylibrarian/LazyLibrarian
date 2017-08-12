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
import re
import threading
import time
import traceback

import lazylibrarian
from lazylibrarian import logger, database
from lazylibrarian.common import scheduleJob
from lazylibrarian.downloadmethods import NZBDownloadMethod, TORDownloadMethod
from lazylibrarian.formatter import plural, now, unaccented_str, replace_all, unaccented, \
    nzbdate2format, getList, month2num, datecompare, check_int, check_year
from lazylibrarian.notifiers import notify_snatch, custom_notify_snatch
from lazylibrarian.providers import IterateOverNewzNabSites, IterateOverTorrentSites, IterateOverRSSSites, \
    IterateOverDirectSites
from lib.fuzzywuzzy import fuzz


def cron_search_magazines():
    if 'SEARCHALLMAG' not in [n.name for n in [t for t in threading.enumerate()]]:
        search_magazines()


def search_magazines(mags=None, reset=False):
    # produce a list of magazines to search for, tor, nzb, torznab, rss
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
            return

        # should clear old search results as might not be available any more
        # ie torrent not available, changed providers, out of news server retention etc.
        # Only delete the "skipped" ones, not wanted/snatched/processed/ignored
        logger.debug(u"Removing old magazine search results")
        myDB.action('DELETE from pastissues WHERE Status="Skipped"')

        logger.info('Searching for %i magazine%s' % (len(searchmags), plural(len(searchmags))))

        for searchmag in searchmags:
            bookid = searchmag['Title']
            searchterm = searchmag['Regex']

            if not searchterm:
                searchterm = searchmag['Title']
                dic = {'...': '', ' & ': ' ', ' = ': ' ', '?': '', '$': 's', ' + ': ' ', '"': '', ',': '', '*': ''}
                searchterm = unaccented_str(replace_all(searchterm, dic))
                searchterm = re.sub('[.\-/]', ' ', searchterm).encode(lazylibrarian.SYS_ENCODING)

            searchlist.append({"bookid": bookid, "searchterm": searchterm})

        if not searchlist:
            logger.warn('There is nothing to search for.  Mark some magazines as active.')

        for book in searchlist:

            resultlist = []

            if lazylibrarian.USE_NZB():
                resultlist, nproviders = IterateOverNewzNabSites(book, 'mag')
                if not nproviders:
                    logger.warn('No nzb providers are set. Check config for NEWZNAB or TORZNAB providers')

            if lazylibrarian.USE_DIRECT():
                dir_resultlist, nproviders = IterateOverDirectSites(book, 'mag')
                if not nproviders:
                    logger.warn('No direct providers are set. Check config for DIRECT providers')

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
                    logger.warn('No torrent providers are set. Check config for TORRENT providers')

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
                    logger.warn('No rss providers are set. Check config for RSS providers')

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
                    nzbtitle = unaccented_str(nzb['nzbtitle'])
                    nzbtitle = nzbtitle.replace('"', '').replace("'", "")  # suppress " in titles
                    nzburl = nzb['nzburl']
                    nzbprov = nzb['nzbprov']
                    nzbdate_temp = nzb['nzbdate']
                    nzbsize_temp = nzb['nzbsize']
                    nzbsize_temp = check_int(nzbsize_temp, 1000)  # not all torrents returned by torznab have a size
                    nzbsize = round(float(nzbsize_temp) / 1048576, 2)
                    nzbdate = nzbdate2format(nzbdate_temp)
                    nzbmode = nzb['nzbmode']

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
                            dic = {'.': ' ', '-': ' ', '/': ' ', '+': ' ', '_': ' ', '(': '', ')': ''}
                            nzbtitle_formatted = replace_all(nzbtitle, dic).strip()
                            # Need to make sure that substrings of magazine titles don't get found
                            # (e.g. Maxim USA will find Maximum PC USA) - token_set_ratio takes care of this
                            # remove extra spaces if they're in a row
                            if nzbtitle_formatted[0] == '[' and nzbtitle_formatted[-1] == ']':
                                nzbtitle_formatted = nzbtitle_formatted[1:-1]
                            nzbtitle_exploded_temp = " ".join(nzbtitle_formatted.split())
                            nzbtitle_exploded = nzbtitle_exploded_temp.split(' ')

                            if ' ' in bookid:
                                bookid_exploded = bookid.split(' ')
                            else:
                                bookid_exploded = [bookid]

                            # check nzb has magazine title and a date/issue nr
                            # eg The MagPI July 2015

                            if len(nzbtitle_exploded) > len(bookid_exploded):
                                # needs to be longer as it has to include a date
                                # check (nearly) all the words in the mag title are in the nzbtitle - allow some fuzz
                                mag_title_match = fuzz.token_set_ratio(
                                    unaccented(bookid),
                                    unaccented(nzbtitle_formatted))

                                if mag_title_match < lazylibrarian.CONFIG['MATCH_RATIO']:
                                    logger.debug(
                                        u"Magazine token set Match failed: " + str(
                                            mag_title_match) + "% for " + nzbtitle_formatted)
                                    rejected = True
                                else:
                                    logger.debug(
                                        u"Magazine matched: " + str(
                                            mag_title_match) + "% " + bookid + " for " + nzbtitle_formatted)
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

                        regex_pass = 0
                        if not rejected:
                            # Magazine names have many different styles of date
                            # DD MonthName YYYY OR MonthName YYYY or Issue nn, MonthName YYYY
                            # MonthName DD YYYY or MonthName DD, YYYY
                            # YYYY MM or YYYY MM DD
                            # Issue/No/Nr/Vol nn, YYYY or Issue/No/Nr/Vol nn
                            # nn YYYY issue number without "Nr" before it
                            # issue and year as a single 6 digit string eg 222015
                            newdatish = "none"
                            # DD MonthName YYYY OR MonthName YYYY or Issue nn, MonthName YYYY
                            pos = 0
                            while pos < len(nzbtitle_exploded):
                                year = check_year(nzbtitle_exploded[pos])
                                if year and pos:
                                    month = month2num(nzbtitle_exploded[pos - 1])
                                    if month:
                                        if pos - 1:
                                            day = check_int(nzbtitle_exploded[pos - 2], 1)
                                            if day > 31:  # probably issue number nn
                                                day = 1
                                        else:
                                            day = 1
                                        newdatish = "%04d-%02d-%02d" % (year, month, day)
                                        try:
                                            _ = datetime.date(year, month, day)
                                            regex_pass = 1
                                            break
                                        except ValueError:
                                            regex_pass = 0
                                pos += 1

                            # MonthName DD YYYY or MonthName DD, YYYY
                            if not regex_pass:
                                pos = 0
                                while pos < len(nzbtitle_exploded):
                                    year = check_year(nzbtitle_exploded[pos])
                                    if year and (pos - 1):
                                        month = month2num(nzbtitle_exploded[pos - 2])
                                        if month:
                                            day = check_int(nzbtitle_exploded[pos - 1].rstrip(','), 1)
                                            try:
                                                _ = datetime.date(year, month, day)
                                                newdatish = "%04d-%02d-%02d" % (year, month, day)
                                                regex_pass = 2
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
                                            else:
                                                day = 1
                                            try:
                                                _ = datetime.date(year, month, day)
                                                newdatish = "%04d-%02d-%02d" % (year, month, day)
                                                regex_pass = 3
                                                break
                                            except ValueError:
                                                regex_pass = 0
                                    pos += 1

                            # Issue/No/Nr/Vol nn, YYYY or Issue/No/Nr/Vol nn
                            if not regex_pass:
                                pos = 0
                                while pos < len(nzbtitle_exploded):
                                    if nzbtitle_exploded[pos].lower() in ["issue", "no", "nr", "vol"]:
                                        if pos + 1 < len(nzbtitle_exploded):
                                            issue = check_int(nzbtitle_exploded[pos + 1], 0)
                                            if issue:
                                                newdatish = str(issue)  # 4 == 04 == 004
                                                if pos + 2 < len(nzbtitle_exploded):
                                                    year = check_year(nzbtitle_exploded[pos + 2])
                                                    if year and year < int(datetime.date.today().year):
                                                        newdatish = '0'  # it's old
                                                    regex_pass = 4  # Issue/No/Nr/Vol nn, YYYY
                                                else:
                                                    regex_pass = 5  # Issue/No/Nr/Vol nn
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
                                            newdatish = str(issue)  # 4 == 04 == 004
                                            regex_pass = 6
                                            if year < int(datetime.date.today().year):
                                                newdatish = '0'  # it's old
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
                                        newdatish = str(issue)  # 4 == 04 == 004
                                        regex_pass = 7
                                        if year < int(datetime.date.today().year):
                                            newdatish = '0'  # it's old
                                        break
                                    pos += 1

                            if not regex_pass:
                                logger.debug('Magazine %s not in a recognised date format.' % nzbtitle_formatted)
                                bad_date += 1
                                # allow issues with good name but bad date to be included
                                # so user can manually select them, incl those with issue numbers
                                newdatish = "1970-01-01"  # provide a fake date for bad-date issues
                                regex_pass = 99

                        if rejected:
                            rejects += 1
                        else:
                            if lazylibrarian.LOGLEVEL > 2:
                                logger.debug("regex %s [%s] %s" % (regex_pass, nzbtitle_formatted, newdatish))
                            # wanted issues go into wanted table marked "Wanted"
                            #  the rest into pastissues table marked "Skipped"
                            insert_table = "pastissues"
                            insert_status = "Skipped"

                            control_date = results['IssueDate']
                            if control_date is None:  # we haven't got any copies of this magazine yet
                                # get a rough time just over a month ago to compare to, in format yyyy-mm-dd
                                # could perhaps calc differently for weekly, biweekly etc
                                # or for magazines with only an issue number, use zero

                                if str(newdatish).isdigit():
                                    logger.debug('Magazine comparing issue numbers (%s)' % newdatish)
                                    control_date = 0
                                elif re.match('\d+-\d\d-\d\d', str(newdatish)):
                                    start_time = time.time()
                                    start_time -= int(
                                        lazylibrarian.CONFIG['MAG_AGE']) * 24 * 60 * 60  # number of seconds in days
                                    if start_time < 0:  # limit of unixtime (1st Jan 1970)
                                        start_time = 0
                                    control_date = time.strftime("%Y-%m-%d", time.localtime(start_time))
                                    logger.debug('Magazine date comparing to %s' % control_date)
                                else:
                                    logger.debug('Magazine unable to find comparison type [%s]' % newdatish)
                                    control_date = 0

                            if str(control_date).isdigit() and str(newdatish).isdigit():
                                # for issue numbers, check if later than last one we have
                                comp_date = int(newdatish) - int(control_date)
                                newdatish = "%s" % newdatish
                                newdatish = newdatish.zfill(4)  # pad so we sort correctly
                            elif re.match('\d+-\d\d-\d\d', str(control_date)) and \
                                    re.match('\d+-\d\d-\d\d', str(newdatish)):
                                # only grab a copy if it's newer than the most recent we have,
                                # or newer than a month ago if we have none
                                comp_date = datecompare(newdatish, control_date)
                            else:
                                # invalid comparison of date and issue number
                                if re.match('\d+-\d\d-\d\d', str(control_date)):
                                    logger.debug('Magazine %s failed: Expecting a date' % nzbtitle_formatted)
                                else:
                                    logger.debug('Magazine %s failed: Expecting issue number' % nzbtitle_formatted)
                                bad_date += 1
                                newdatish = "1970-01-01"  # this is our fake date for ones we can't decipher
                                comp_date = 0

                            if comp_date > 0:
                                # keep track of what we're going to download so we don't download dupes
                                new_date += 1
                                issue = bookid + ',' + newdatish
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
                                    insert_status = "Wanted"
                                    nzbdate = now()  # when we asked for it
                                else:
                                    logger.debug('This issue of %s is already flagged for download' % issue)
                            else:
                                if newdatish != "1970-01-01":  # this is our fake date for ones we can't decipher
                                    logger.debug('This issue of %s is old; skipping.' % nzbtitle_formatted)
                                    old_date += 1

                            # store only the _new_ matching results
                            #  Don't add a new entry if this issue has been found on an earlier search
                            #  and status has been user-set ( we only delete the "Skipped" ones )
                            #  In "wanted" table it might be already snatched/downloading/processing

                            mag_entry = myDB.match('SELECT * from %s WHERE NZBtitle=? and NZBprov=?' % insert_table,
                                                   (nzbtitle, nzbprov))
                            if mag_entry:
                                if lazylibrarian.LOGLEVEL > 2:
                                    logger.debug('%s is already in %s marked %s' %
                                                 (nzbtitle, insert_table, insert_status))
                            else:
                                controlValueDict = {
                                    "NZBtitle": nzbtitle,
                                    "NZBprov": nzbprov
                                }
                                newValueDict = {
                                    "NZBurl": nzburl,
                                    "BookID": bookid,
                                    "NZBdate": nzbdate,
                                    "AuxInfo": newdatish,
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
                        custom_notify_snatch(magazine['bookid'])
                        scheduleJob(action='Start', target='processDir')

        if reset:
            scheduleJob(action='Restart', target='search_magazines')

        logger.info("Search for magazines complete")

    except Exception:
        logger.error('Unhandled exception in search_magazines: %s' % traceback.format_exc())
