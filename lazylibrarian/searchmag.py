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

import time
import urllib2
import re
import datetime
import os
import lazylibrarian
import threading
from lazylibrarian import logger, database

from lib.fuzzywuzzy import fuzz
from lazylibrarian.searchtorrents import TORDownloadMethod
from lazylibrarian.searchnzb import NZBDownloadMethod
from lazylibrarian.formatter import plural, now, unaccented_str, replace_all, unaccented, \
    nzbdate2format, getList, month2num, datecompare, check_int
from lazylibrarian.common import scheduleJob
from lazylibrarian.notifiers import notify_snatch
from lazylibrarian.providers import IterateOverNewzNabSites, IterateOverTorrentSites, IterateOverRSSSites


def cron_search_magazines():
    threading.currentThread().name = "CRON-SEARCHMAG"
    search_magazines()


def search_magazines(mags=None, reset=False):
    # produce a list of magazines to search for, tor, nzb, torznab, rss

    threadname = threading.currentThread().name
    if "Thread-" in threadname:
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
                                          WHERE Title="%s" AND Status="Active"' % (magazine['bookid']))
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
            searchterm = re.sub('[\.\-\/]', ' ', searchterm).encode(lazylibrarian.SYS_ENCODING)

        searchlist.append({"bookid": bookid, "searchterm": searchterm})

    if searchlist == []:
        logger.warn('There is nothing to search for.  Mark some magazines as active.')

    for book in searchlist:

        resultlist = []
        tor_resultlist = []
        if lazylibrarian.USE_NZB():
            resultlist, nproviders = IterateOverNewzNabSites(book, 'mag')
            if not nproviders:
                logger.warn('No nzb providers are set. Check config for NEWZNAB or TORZNAB providers')

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
            rss_resultlist, nproviders = IterateOverRSSSites(book, 'mag')
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
            logger.debug("Adding magazine %s to queue." % book['searchterm'])

        else:
            bad_name = 0
            bad_date = 0
            old_date = 0
            total_nzbs = 0
            new_date = 0
            maglist = []
            issues = []

            for nzb in resultlist:
                total_nzbs = total_nzbs + 1
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

                results = myDB.match('SELECT * from magazines WHERE Title="%s"' % bookid)
                if not results:
                    logger.debug('Magazine [%s] does not match search term [%s].' % (nzbtitle, bookid))
                    bad_name = bad_name + 1
                else:
                    control_date = results['IssueDate']
                    reject_list = getList(results['Reject'])

                    dic = {'.': ' ', '-': ' ', '/': ' ', '+': ' ', '_': ' ', '(': '', ')': ''}
                    nzbtitle_formatted = replace_all(nzbtitle, dic).strip()

                    # Need to make sure that substrings of magazine titles don't get found
                    # (e.g. Maxim USA will find Maximum PC USA) - token_set_ratio takes care of this
                    # remove extra spaces if they're in a row
                    nzbtitle_exploded_temp = " ".join(nzbtitle_formatted.split())
                    nzbtitle_exploded = nzbtitle_exploded_temp.split(' ')

                    if ' ' in bookid:
                        bookid_exploded = bookid.split(' ')
                    else:
                        bookid_exploded = [bookid]

                    # check nzb starts with magazine title followed by a date
                    # eg The MagPI Issue 22 - July 2015

                    rejected = False
                    if len(nzbtitle_exploded) > len(bookid_exploded):
                        # needs to be longer as it has to include a date
                        # check (nearly) all the words in the mag title are in the nzbtitle - allow some fuzz
                        mag_title_match = fuzz.token_set_ratio(
                            unaccented(bookid),
                            unaccented(nzbtitle_formatted))

                        if mag_title_match < lazylibrarian.MATCH_RATIO:
                            logger.debug(
                                u"Magazine token set Match failed: " + str(
                                    mag_title_match) + "% for " + nzbtitle_formatted)
                            rejected = True
                        else:
                            logger.debug(
                                u"Magazine matched: " + str(
                                    mag_title_match) + "% " + bookid + " for " + nzbtitle_formatted)
                    else:
                        rejected = True

                    if not rejected:
                        already_failed = myDB.match('SELECT * from wanted WHERE NZBurl="%s" and Status="Failed"' %
                                                    nzburl)
                        if already_failed:
                            logger.debug("Rejecting %s, blacklisted at %s" %
                                         (nzbtitle_formatted, already_failed['NZBprov']))
                            rejected = True

                    if not rejected:
                        lower_title = unaccented(nzbtitle_formatted).lower()
                        lower_bookid = unaccented(bookid).lower()
                        for word in reject_list:
                            if word in lower_title and word not in lower_bookid:
                                rejected = True
                                logger.debug("Rejecting %s, contains %s" % (nzbtitle_formatted, word))
                                break

                    if not rejected:
                        # some magazine torrent uploaders add their sig in [] or {}
                        # Fortunately for us, they always seem to add it at the end
                        # also some magazine torrent titles are "magazine_name some_form_of_date pdf"
                        # or other words we don't want. Should make the word list configurable.
                        # so strip all the trailing junk...
                        strip_list = ['pdf', 'true', 'truepdf', 'german', 'ebooks']
                        while nzbtitle_exploded[len(nzbtitle_exploded) - 1][0] in '[{' or \
                                nzbtitle_exploded[len(nzbtitle_exploded) - 1].lower() in strip_list:
                                nzbtitle_exploded.pop()  # gotta love the function names

                        # need at least one word magazine title and two date components
                        if len(nzbtitle_exploded) > 2:
                            # regexA = DD MonthName YYYY OR MonthName YYYY or Issue nn, MonthName YYYY
                            regexA_year = nzbtitle_exploded[len(nzbtitle_exploded) - 1]
                            regexA_month_temp = nzbtitle_exploded[len(nzbtitle_exploded) - 2]
                            regexA_month = month2num(unaccented(regexA_month_temp))
                            if not regexA_year.isdigit() or int(regexA_year) < 1900 or int(regexA_year) > 2100:
                                regexA_year = 'fail'  # force date failure

                            # if frequency == "Weekly" or frequency == "BiWeekly":
                            regexA_day = nzbtitle_exploded[len(nzbtitle_exploded) - 3].rstrip(',').zfill(2)
                            if regexA_day.isdigit():
                                if int(regexA_day) > 31:  # probably issue number nn
                                    regexA_day = '01'
                            else:
                                regexA_day = '01'  # just MonthName YYYY
                            # else:
                            # regexA_day = '01'  # monthly, or less frequent
                            try:
                                newdatish = regexA_year + '-' + regexA_month + '-' + regexA_day
                                # try to make sure the year/month/day are valid, exception if not
                                # ie don't accept day > 31, or 30 in some months, or month <1 or >12
                                # also handles multiple date format named issues eg Jan 2014, 01 2014
                                # datetime will give a ValueError if not a good date or a param is not int
                                date1 = datetime.date(int(regexA_year), int(regexA_month), int(regexA_day))
                            except ValueError:
                                # regexB = MonthName DD YYYY or MonthName DD, YYYY
                                regexB_year = nzbtitle_exploded[len(nzbtitle_exploded) - 1]
                                regexB_month_temp = nzbtitle_exploded[len(nzbtitle_exploded) - 3]
                                regexB_month = month2num(unaccented(regexB_month_temp))
                                regexB_day = nzbtitle_exploded[len(nzbtitle_exploded) - 2].rstrip(',').zfill(2)
                                if not regexB_year.isdigit() or int(regexB_year) < 1900 or int(regexB_year) > 2100:
                                    regexB_year = 'fail'
                                try:
                                    newdatish = regexB_year + '-' + regexB_month + '-' + regexB_day
                                    # datetime will give a ValueError if not a good date or a param is not int
                                    date1 = datetime.date(int(regexB_year), int(regexB_month), int(regexB_day))
                                except ValueError:
                                    # regexC = YYYY MM or YYYY MM DD
                                    # (can't get MM/DD if named YYYY Issue nn)
                                    # First try  YYYY MM
                                    regexC_year = nzbtitle_exploded[len(nzbtitle_exploded) - 2]
                                    if regexC_year.isdigit() and int(regexC_year) > 1900 and int(regexC_year) < 2100:
                                        regexC_month = nzbtitle_exploded[len(nzbtitle_exploded) - 1].zfill(2)
                                        regexC_day = '01'
                                    else:  # try YYYY MM DD
                                        regexC_year = nzbtitle_exploded[len(nzbtitle_exploded) - 3]
                                        regexC_month = 0
                                        regexC_day = 0
                                        if regexC_year.isdigit() and int(regexC_year) > 1900 and int(regexC_year) < 2100:
                                            regexC_month = nzbtitle_exploded[len(nzbtitle_exploded) - 2].zfill(2)
                                            regexC_day = nzbtitle_exploded[len(nzbtitle_exploded) - 1].zfill(2)
                                        else:
                                            regexC_year = 'fail'
                                    try:
                                        newdatish = regexC_year + '-' + regexC_month + '-' + regexC_day
                                        # datetime will give a ValueError if not a good date or a param is not int
                                        date1 = datetime.date(int(regexC_year), int(regexC_month), int(regexC_day))
                                    except Exception:
                                        # regexD Issue/No/Nr/Vol nn, YYYY or Issue/No/Nr/Vol nn
                                        try:
                                            IssueLabel = nzbtitle_exploded[len(nzbtitle_exploded) - 2]
                                            if IssueLabel.lower() in ["issue", "no", "nr", "vol"]:
                                                # issue nn
                                                regexD_issue = nzbtitle_exploded[len(nzbtitle_exploded) - 1]
                                                if regexD_issue.isdigit():
                                                    newdatish = str(int(regexD_issue))  # 4 == 04 == 004
                                            else:
                                                IssueLabel = nzbtitle_exploded[len(nzbtitle_exploded) - 3]
                                                if IssueLabel.lower() in ["issue", "no", "nr", "vol"]:
                                                    # issue nn, YYYY
                                                    regexD_issue = nzbtitle_exploded[len(nzbtitle_exploded) - 2]
                                                    regexD_issue = regexD_issue.strip(',')
                                                    if regexD_issue.isdigit():
                                                        newdatish = str(int(regexD_issue))  # 4 == 04 == 004
                                                    else:
                                                        raise ValueError
                                                    regexD_year = nzbtitle_exploded[len(nzbtitle_exploded) - 1]
                                                    if regexD_year.isdigit():
                                                        if int(regexD_year) < int(datetime.date.today().year):
                                                            newdatish = 0  # it's old
                                                else:
                                                    raise ValueError
                                        except Exception:
                                            # regexE nn YYYY issue number without "Nr" before it
                                            # nn is assumed not to be a month as they are normally names not digits
                                            try:
                                                regexE_year = nzbtitle_exploded[len(nzbtitle_exploded) - 1]
                                                regexE_issue = nzbtitle_exploded[len(nzbtitle_exploded) - 2]
                                                print "[%s][%s]" % (regexE_year, regexE_issue)
                                                if regexE_issue.isdigit():
                                                    newdatish = int(regexE_issue)
                                                    if int(regexE_year) < int(datetime.date.today().year):
                                                        newdatish = 0  # it's old
                                                else:
                                                    raise ValueError
                                            except Exception:
                                                # regexF issue and year as a single 6 digit string eg 222015
                                                try:
                                                    regexF = nzbtitle_exploded[len(nzbtitle_exploded) - 1]
                                                    if regexF.isdigit() and len(regexF) == 6:
                                                        regexF_issue = regexF[:2]
                                                        regexF_year = regexF[2:]
                                                        newdatish = str(int(regexF_issue))  # 4 == 04 == 004
                                                        if int(regexF_year) < int(datetime.date.today().year):
                                                            newdatish = 0  # it's old
                                                    else:
                                                        raise ValueError

                                                except Exception:
                                                    logger.debug('Magazine %s not in a recognised date format.' %
                                                                 nzbtitle_formatted)
                                                    bad_date = bad_date + 1
                                                    # allow issues with good name but bad date to be included
                                                    # so user can manually select them, incl those with issue numbers
                                                    newdatish = "1970-01-01"  # provide a fake date for bad-date issues
                                                    # continue
                        else:
                            logger.debug('Magazine [%s] does not match the search term [%s].' % (
                                nzbtitle_formatted, bookid))
                            bad_name = bad_name + 1
                            continue

                        #  wanted issues go into wanted table marked "Wanted"
                        #  the rest into pastissues table marked "Skipped"
                        insert_table = "pastissues"
                        insert_status = "Skipped"

                        if control_date is None:  # we haven't got any copies of this magazine yet
                            # get a rough time just over a month ago to compare to, in format yyyy-mm-dd
                            # could perhaps calc differently for weekly, biweekly etc
                            # or for magazines with only an issue number, use zero

                            if '-' in str(newdatish):
                                start_time = time.time()
                                start_time -= int(lazylibrarian.MAG_AGE) * 24 * 60 * 60  # number of seconds in days
                                if start_time < 0:  # limit of unixtime (1st Jan 1970)
                                    start_time = 0
                                control_date = time.strftime("%Y-%m-%d", time.localtime(start_time))
                                logger.debug('Magazine date comparing to %s' % control_date)
                            else:
                                control_date = 0

                        if '-' in str(control_date) and '-' in str(newdatish):
                            # only grab a copy if it's newer than the most recent we have,
                            # or newer than a month ago if we have none
                            comp_date = datecompare(newdatish, control_date)
                        elif '-' not in str(control_date) and '-' not in str(newdatish):
                            # for issue numbers, check if later than last one we have
                            comp_date = int(newdatish) - int(control_date)
                            newdatish = "%s" % newdatish
                            newdatish = newdatish.zfill(4)  # pad so we sort correctly
                        else:
                            # invalid comparison of date and issue number
                            logger.debug('Magazine %s incorrect date or issue format.' % nzbtitle_formatted)
                            bad_date = bad_date + 1
                            newdatish = "1970-01-01"  # this is our fake date for ones we can't decipher
                            comp_date = 0

                        if comp_date > 0:
                            # keep track of what we're going to download so we don't download dupes
                            new_date = new_date + 1
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
                                insert_table = "wanted"
                                insert_status = "Wanted"
                                nzbdate = now()  # when we asked for it
                            else:
                                logger.debug('This issue of %s is already flagged for download' % issue)
                        else:
                            if newdatish != "1970-01-01":  # this is our fake date for ones we can't decipher
                                logger.debug('This issue of %s is old; skipping.' % nzbtitle_formatted)
                                old_date = old_date + 1

                        #  store only the _new_ matching results
                        #  Don't add a new entry if this issue has been found on an earlier search
                        #  and status has been user-set ( we only delete the "Skipped" ones )
                        #  In "wanted" table it might be already snatched/downloading/processing

                        mag_entry = myDB.select('SELECT * from %s WHERE NZBtitle="%s" and NZBprov="%s"' % (
                                                insert_table, nzbtitle, nzbprov))
                        if not mag_entry:
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

                    else:
                        # logger.debug('Magazine [%s] was rejected.' % nzbtitle_formatted)
                        bad_name = bad_name + 1

            logger.info('Found %i result%s for %s. %i new, %i old, %i fail date, %i fail name: %i to download' % (
                        total_nzbs, plural(total_nzbs), bookid, new_date, old_date, bad_date, bad_name, len(maglist)))

            for magazine in maglist:
                if magazine['nzbmode'] in ["torznab", "torrent", "magnet"]:
                    snatch = TORDownloadMethod(
                        magazine['bookid'],
                        magazine['nzbprov'],
                        magazine['nzbtitle'],
                        magazine['nzburl'])
                else:
                    snatch = NZBDownloadMethod(
                        magazine['bookid'],
                        magazine['nzbprov'],
                        magazine['nzbtitle'],
                        magazine['nzburl'])
                if snatch:
                    logger.info('Downloading %s from %s' % (magazine['nzbtitle'], magazine["nzbprov"]))
                    notify_snatch("%s from %s at %s" %
                                  (unaccented(magazine['nzbtitle']), magazine["nzbprov"], now()))
                    scheduleJob(action='Start', target='processDir')
            maglist = []

    if reset:
        scheduleJob(action='Restart', target='search_magazines')

    logger.info("Search for magazines complete")
