import time
import threading
#import urllib
import urllib2
#import os
import re

#from xml.etree import ElementTree
#from xml.etree.ElementTree import Element, SubElement

import lazylibrarian

from lazylibrarian import logger, database, formatter, providers, SimpleCache, common

#import lib.fuzzywuzzy as fuzzywuzzy
from lib.fuzzywuzzy import fuzz
#from lib.unidecode import unidecode


def searchmagazines(mags=None):
    maglist = []
    myDB = database.DBConnection()
    searchlist = []

    threading.currentThread().name = "SEARCHMAGS"

    if mags is None:  # backlog search
        searchmags = myDB.select('SELECT Title, Frequency, LastAcquired, IssueDate from magazines WHERE Status="Active"')
    else:
        searchmags = []
        for magazine in mags:
            searchmags_temp = myDB.select('SELECT Title, Frequency, LastAcquired, IssueDate from magazines WHERE Title="%s" AND Status="Active"' % (magazine['bookid']))
            for terms in searchmags_temp:
                searchmags.append(terms)

    if len(searchmags) == 1:
        logger.info('Searching for one magazine')
    else:
        logger.info('Searching for %i magazines'  % len(searchmags))

    for searchmag in searchmags:
        bookid = searchmag[0]
        searchterm = searchmag[0]
        frequency = searchmag[1]
        #last_acquired = searchmag[2]
        #issue_date = searchmag[3]

        dic = {'...': '', ' & ': ' ', ' = ': ' ', '?': '', '$': 's', ' + ': ' ', '"': '', ',': '', '*': ''}

        searchterm = formatter.latinToAscii(formatter.replace_all(searchterm, dic))
        searchterm = re.sub('[\.\-\/]', ' ', searchterm).encode('utf-8')
        searchlist.append({"bookid": bookid, "searchterm": searchterm})

    if searchlist == []:
        logger.info('There is nothing to search for.  Mark some magazines as active.')

    for book in searchlist:

        if lazylibrarian.USE_NZB:
            resultlist, nproviders = providers.IterateOverNewzNabSites(book, 'mag')
            if not nproviders:
                logger.info('No nzb providers are set. Check config for NEWZNAB or TORZNAB providers')

        if lazylibrarian.USE_TOR:
            tor_resultlist, nproviders = providers.IterateOverTorrentSites(book, 'mag')
            if not nproviders:
                logger.info('No torrent providers are set. Check config for TORRENT providers')

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

        if not resultlist:
            logger.debug("Adding magazine %s to queue." % book['searchterm'])

        else:
            bad_regex = 0
            bad_date = 0
            old_date = 0
            total_nzbs = 0
            new_date = 0
            for nzb in resultlist:
                total_nzbs = total_nzbs + 1
                bookid = nzb['bookid']
                nzbtitle = (u'%s' % nzb['nzbtitle'])
                nzbtitle = nzbtitle.replace('"', '').replace("'", "")  # suppress " in titles
                nzburl = nzb['nzburl']
                nzbprov = nzb['nzbprov']
                nzbdate_temp = nzb['nzbdate']
                nzbsize_temp = nzb['nzbsize']
                if nzbsize_temp is None:  # not all torrents returned by torznab have a size
                    nzbsize_temp = 1000
                nzbsize = str(round(float(nzbsize_temp) / 1048576, 2)) + ' MB'
                nzbdate = formatter.nzbdate2format(nzbdate_temp)
                nzbmode = nzb['nzbmode']
                checkifmag = myDB.select('SELECT * from magazines WHERE Title="%s"' % bookid)
                if checkifmag:
                    for results in checkifmag:
                        control_date = results['IssueDate']
                        frequency = results['Frequency']
                        #regex = results['Regex']

                    nzbtitle_formatted = nzbtitle.replace('.', ' ').replace('-', ' ').replace('/', ' ').replace('+', ' ').replace('_', ' ').replace('(', '').replace(')', '').strip()
                    # Need to make sure that substrings of magazine titles don't get found (e.g. Maxim USA will find Maximum PC USA)
                    #keyword_check = nzbtitle_formatted.replace(bookid, '')
                    # remove extra spaces if they're in a row
                    nzbtitle_exploded_temp = " ".join(nzbtitle_formatted.split())
                    nzbtitle_exploded = nzbtitle_exploded_temp.split(' ')

                    bookid_exploded = bookid.split(' ')

                    # check nzb starts with magazine title, and ends with a date
                    # eg The MagPI Issue 22 - July 2015
                    # do something like check left n words match title
                    # then check last n words are a date

                    name_match = 1  # assume name matches for now
                    name_len = len(bookid_exploded)
                    if len(nzbtitle_exploded) > name_len:  # needs to be longer as it should include a date
                        while name_len:
                            name_len = name_len - 1
                            # fuzzy check on each word in the magazine name with any accents stripped
                            ratio = fuzz.ratio(common.remove_accents(nzbtitle_exploded[name_len]).lower(), common.remove_accents(bookid_exploded[name_len]).lower())
                            if ratio < 80:  # hard coded fuzz ratio for now, works for close matches
                                logger.debug("Magazine fuzz ratio failed [%d] [%s] [%s]" % (ratio, bookid, nzbtitle_formatted))
                                name_match = 0  # name match failed
                    if name_match:
                            # some magazine torrent titles are "magazine name some form of date .pdf"
                        if nzbtitle_exploded[len(nzbtitle_exploded) - 1].lower() == 'pdf':
                            nzbtitle_exploded.pop()  # gotta love the function names
                        if len(nzbtitle_exploded) > 1:
                            # regexA = DD MonthName YYYY OR MonthName YYYY or nn MonthName YYYY
                            regexA_year = nzbtitle_exploded[len(nzbtitle_exploded) - 1]
                            regexA_month_temp = nzbtitle_exploded[len(nzbtitle_exploded) - 2]
                            regexA_month = formatter.month2num(common.remove_accents(regexA_month_temp))

                            if frequency == "Weekly" or frequency == "BiWeekly":
                                regexA_day = nzbtitle_exploded[len(nzbtitle_exploded) - 3].zfill(2)
                                if regexA_day.isdigit():
                                    if int(regexA_day) > 31:  # probably issue number nn
                                        regexA_day = '01'
                                else:
                                    regexA_day = '01'  # just MonthName YYYY
                            else:
                                regexA_day = '01'  # monthly, or less frequent

                            newdatish_regexA = regexA_year + regexA_month + regexA_day

                            try:
                                int(newdatish_regexA)
                                newdatish = regexA_year + '-' + regexA_month + '-' + regexA_day
                            except:
                                # regexB = MonthName DD YYYY
                                regexB_year = nzbtitle_exploded[len(nzbtitle_exploded) - 1]
                                regexB_day = nzbtitle_exploded[len(nzbtitle_exploded) - 2].zfill(2)
                                regexB_month_temp = nzbtitle_exploded[len(nzbtitle_exploded) - 3]
                                regexB_month = formatter.month2num(common.remove_accents(regexB_month_temp))
                                newdatish_regexB = regexB_year + regexB_month + regexB_day

                                try:
                                    int(newdatish_regexB)
                                    newdatish = regexB_year + '-' + regexB_month + '-' + regexB_day
                                except:
                                    # regexC = YYYY MM or YYYY MM DD or Issue nn YYYY (can't get MM/DD if named Issue nn)
                                    newdatish_regexC = 'Invalid'  # invalid unless works out otherwise
                                    regexC_temp = nzbtitle_exploded[len(nzbtitle_exploded) - 2]
                                    if regexC_temp.isdigit():
                                        if int(regexC_temp) > 1900:  # YYYY MM  or YYYY nn
                                            regexC_year = regexC_temp
                                            regexC_month = nzbtitle_exploded[len(nzbtitle_exploded) - 1].zfill(2)
                                            regexC_day = '01'
                                            if regexC_month.isdigit():  # could be YYYY nn where nn is issue number
                                                if int(regexC_month) < 13:  # if issue number > 12 date matching will fail
                                                    newdatish_regexC = regexC_year + regexC_month + regexC_day
                                        else:
                                            regexC_year = nzbtitle_exploded[len(nzbtitle_exploded) - 3]
                                            if regexC_year.isdigit():
                                                if int(regexC_year) > 1900:  # YYYY MM DD or YYYY nn-nn
                                                    regexC_month = regexC_temp.zfill(2)
                                                    if int(regexC_month) < 13:  # if issue number > 12 date matching will fail
                                                        regexC_day = nzbtitle_exploded[len(nzbtitle_exploded) - 1].zfill(2)
                                                        newdatish_regexC = regexC_year + regexC_month + regexC_day

                                    try:
                                        int(newdatish_regexC)
                                        newdatish = regexC_year + '-' + regexC_month + '-' + regexC_day
                                    except:
                                        logger.debug('Magazine %s not in proper date format.' % nzbtitle_formatted)
                                        bad_date = bad_date + 1
                                        # allow issues with good name but bad date to be included so user can manually select them
                                        newdatish = "1970-01-01"  # provide a fake date for bad-date issues
                                        # continue

                        else:
                            continue

                        # Don't want to overwrite status = Skipped for NZBs that have been previously found
                        wanted_status = myDB.select('SELECT * from wanted WHERE NZBtitle="%s"' % nzbtitle)
                        if wanted_status:
                            for results in wanted_status:
                                status = results['Status']
                        else:
                            status = "Skipped"

                        controlValueDict = {"NZBurl": nzburl}
                        newValueDict = {
                            "NZBprov": nzbprov,
                                "BookID": bookid,
                                "NZBdate": nzbdate,
                                "NZBtitle": nzbtitle,
                                "AuxInfo": newdatish,
                                "Status": status,
                                "NZBsize": nzbsize,
                                "NZBmode": nzbmode
                        }
                        myDB.upsert("wanted", newValueDict, controlValueDict)

                        if control_date is None:  # we haven't got any copies of this magazine yet
                            # get a rough time just over a month ago to compare to, in format yyyy-mm-dd
                            # could perhaps calc differently for weekly, biweekly etc
                            start_time = time.time()
                            start_time -= 31 * 24 * 60 * 60  # number of seconds in 31 days
                            control_date = time.strftime("%Y-%m-%d", time.localtime(start_time))

                        # only grab a copy if it's newer than the most recent we have, or newer than a month ago if we have none
                        # TODO we should maybe store frequency in the table too - would allow us to recreate the table on a scan
                        # similar to importing a book library. Also need number of seeders collecting and storing for torznab
                        comp_date = formatter.datecompare(newdatish, control_date)
                        if comp_date > 0:
                            myDB.upsert("magazines", {"LastAcquired": nzbdate, "IssueDate": newdatish}, {"Title": bookid})
                            maglist.append({
                                'bookid': bookid,
                                    'nzbprov': nzbprov,
                                    'nzbtitle': nzbtitle,
                                    'nzburl': nzburl,
                                    'nzbmode': nzbmode
                            })
                            logger.debug('This issue of %s is new, downloading' % nzbtitle_formatted)
                            new_date = new_date + 1
                        else:
                            if newdatish != "1970-01-01":  # this is our fake date for ones we can't decipher
                                logger.debug('This issue of %s is old; skipping.' % nzbtitle_formatted)
                                old_date = old_date + 1
                    else:
                        logger.debug('Magazine [%s] does not completely match search term [%s].' % (nzbtitle_formatted, bookid))
                        bad_regex = bad_regex + 1

            logger.info('Found %s results for %s.  %s are new, %s are old, %s fail date, %s fail name matching' % (total_nzbs, bookid, new_date, old_date, bad_date, bad_regex))
    return maglist
