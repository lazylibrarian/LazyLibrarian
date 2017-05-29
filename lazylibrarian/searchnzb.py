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

import os
import re
import threading
import traceback

import lazylibrarian
from lazylibrarian import logger, database, providers, nzbget, sabnzbd, classes, synology
from lazylibrarian.cache import fetchURL
from lazylibrarian.common import scheduleJob, setperm
from lazylibrarian.formatter import plural, unaccented_str, replace_all, getList, now, check_int
from lazylibrarian.notifiers import notify_snatch, custom_notify_snatch
from lazylibrarian.searchtorrents import TORDownloadMethod
from lib.fuzzywuzzy import fuzz


def cron_search_nzb_book():
    if 'SEARCHALLNZB' not in [n.name for n in [t for t in threading.enumerate()]]:
        search_nzb_book()


def search_nzb_book(books=None, library=None):
    """
    books is a list of new books to add, or None for backlog search
    library is "eBook" or "AudioBook" or None to search all book types
    """
    try:
        threadname = threading.currentThread().name
        if "Thread-" in threadname:
            if books is None:
                threading.currentThread().name = "SEARCHALLNZB"
            else:
                threading.currentThread().name = "SEARCHNZB"

        if not lazylibrarian.USE_NZB():
            logger.warn('No NEWZNAB/TORZNAB providers set, check config')
            return

        myDB = database.DBConnection()
        searchlist = []

        if books is None:
            # We are performing a backlog search
            searchbooks = []
            cmd = 'SELECT BookID, AuthorName, Bookname, BookSub, BookAdded, books.Status, AudioStatus '
            cmd += 'from books,authors WHERE (books.Status="Wanted" OR AudioStatus="Wanted") '
            cmd += 'and books.AuthorID = authors.AuthorID order by BookAdded desc'
            results = myDB.select(cmd)
            for terms in results:
                searchbooks.append(terms)
        else:
            # The user has added a new book
            searchbooks = []
            for book in books:
                cmd = 'SELECT BookID, AuthorName, BookName, BookSub, books.Status, AudioStatus '
                cmd += 'from books,authors WHERE BookID="%s" ' % book['bookid']
                cmd += 'AND books.AuthorID = authors.AuthorID'
                results = myDB.select(cmd)
                for terms in results:
                    searchbooks.append(terms)

        if len(searchbooks) == 0:
            return

        logger.info('NZB Searching for %i book%s' % (len(searchbooks), plural(len(searchbooks))))

        for searchbook in searchbooks:
            # searchterm is only used for display purposes
            searchterm = searchbook['AuthorName'] + ' ' + searchbook['BookName']
            if searchbook['BookSub']:
                searchterm = searchterm + ': ' + searchbook['BookSub']

            if library is None or library == 'eBook':
                if searchbook['Status'] == "Wanted":
                    searchlist.append(
                        {"bookid": searchbook['BookID'],
                         "bookName": searchbook['BookName'],
                         "bookSub": searchbook['BookSub'],
                         "authorName": searchbook['AuthorName'],
                         "library": "eBook",
                         "searchterm": searchterm})

            if library is None or library == 'AudioBook':
                if searchbook['AudioStatus'] == "Wanted":
                    searchlist.append(
                        {"bookid": searchbook['BookID'],
                         "bookName": searchbook['BookName'],
                         "bookSub": searchbook['BookSub'],
                         "authorName": searchbook['AuthorName'],
                         "library": "AudioBook",
                         "searchterm": searchterm})

        nzb_count = 0
        for book in searchlist:
            # first attempt, try author/title in category "book"
            if book['library'] == 'AudioBook':
                searchtype = 'audio'
            else:
                searchtype = 'book'
            resultlist, nproviders = providers.IterateOverNewzNabSites(book, searchtype)

            if not nproviders:
                logger.warn('No NewzNab or TorzNab providers are set, check config')
                return  # no point in continuing

            found = processResultList(resultlist, book, searchtype)

            # if you can't find the book, try author/title without any "(extended details, series etc)"
            if not found and '(' in book['bookName']:
                searchtype = 'short' + searchtype
                resultlist, nproviders = providers.IterateOverNewzNabSites(book, searchtype)
                found = processResultList(resultlist, book, searchtype)

            # if you can't find the book under "books", you might find under general search
            if not found:
                resultlist, nproviders = providers.IterateOverNewzNabSites(book, 'general')
                found = processResultList(resultlist, book, "general")

            # if still not found, try general search again without any "(extended details, series etc)"
            if not found and '(' in book['bookName']:
                resultlist, nproviders = providers.IterateOverNewzNabSites(book, 'shortgeneral')
                found = processResultList(resultlist, book, "shortgeneral")

            if not found:
                logger.info("NZB Searches for %s %s returned no results." % (book['library'], book['searchterm']))
            if found > True:
                nzb_count += 1  # we found it

        logger.info("NZBSearch for Wanted items complete, found %s book%s" % (nzb_count, plural(nzb_count)))

    except Exception:
        logger.error('Unhandled exception in search_nzb_book: %s' % traceback.format_exc())


def processResultList(resultlist, book, searchtype):
    myDB = database.DBConnection()
    dictrepl = {'...': '', '.': ' ', ' & ': ' ', ' = ': ' ', '?': '', '$': 's', ' + ': ' ', '"': '',
                ',': ' ', '*': '', '(': '', ')': '', '[': '', ']': '', '#': '', '0': '', '1': '',
                '2': '', '3': '', '4': '', '5': '', '6': '', '7': '', '8': '', '9': '', '\'': '',
                ':': '', '!': '', '-': ' ', '\s\s': ' '}

    dic = {'...': '', '.': ' ', ' & ': ' ', ' = ': ' ', '?': '', '$': 's', ' + ': ' ', '"': '',
           ',': '', '*': '', ':': '.', ';': '', '\'': ''}

    match_ratio = int(lazylibrarian.CONFIG['MATCH_RATIO'])
    if book['library'] == 'eBook':
        reject_list = getList(lazylibrarian.CONFIG['REJECT_WORDS'])
        maxsize = check_int(lazylibrarian.CONFIG['REJECT_MAXSIZE'], 0)
        minsize = check_int(lazylibrarian.CONFIG['REJECT_MINSIZE'], 0)
        auxinfo = 'eBook'

    else:   #if book['library'] == 'AudioBook':
        reject_list = getList(lazylibrarian.CONFIG['REJECT_AUDIO'])
        maxsize = check_int(lazylibrarian.CONFIG['REJECT_MAXAUDIO'], 0)
        minsize = check_int(lazylibrarian.CONFIG['REJECT_MINAUDIO'], 0)
        auxinfo = 'AudioBook'

    author = unaccented_str(replace_all(book['authorName'], dic))
    title = unaccented_str(replace_all(book['bookName'], dic))

    matches = []
    for nzb in resultlist:
        nzb_Title = unaccented_str(replace_all(nzb['nzbtitle'], dictrepl)).strip()
        nzb_Title = re.sub(r"\s\s+", " ", nzb_Title)  # remove extra whitespace

        nzbAuthor_match = fuzz.token_set_ratio(author, nzb_Title)
        nzbBook_match = fuzz.token_set_ratio(title, nzb_Title)
        logger.debug(u"NZB author/book Match: %s/%s for %s" % (nzbAuthor_match, nzbBook_match, nzb_Title))
        nzburl = nzb['nzburl']

        rejected = False

        already_failed = myDB.match('SELECT * from wanted WHERE NZBurl="%s" and Status="Failed"' % nzburl)
        if already_failed:
            logger.debug("Rejecting %s, blacklisted at %s" % (nzb_Title, already_failed['NZBprov']))
            rejected = True

        if not rejected:
            for word in reject_list:
                if word in nzb_Title.lower() and word not in author.lower() and word not in title.lower():
                    rejected = True
                    logger.debug("Rejecting %s, contains %s" % (nzb_Title, word))
                    break

        nzbsize_temp = nzb['nzbsize']  # Need to cater for when this is NONE (Issue 35)
        nzbsize_temp = check_int(nzbsize_temp, 1000)
        nzbsize = round(float(nzbsize_temp) / 1048576, 2)

        if not rejected:
            if maxsize and nzbsize > maxsize:
                rejected = True
                logger.debug("Rejecting %s, too large" % nzb_Title)

        if not rejected:
            if minsize and nzbsize < minsize:
                rejected = True
                logger.debug("Rejecting %s, too small" % nzb_Title)

        if not rejected:
            bookid = book['bookid']
            nzbTitle = (author + ' - ' + title + ' LL.(' + book['bookid'] + ')').strip()
            nzbprov = nzb['nzbprov']
            nzbmode = nzb['nzbmode']
            controlValueDict = {"NZBurl": nzburl}
            newValueDict = {
                "NZBprov": nzbprov,
                "BookID": bookid,
                "NZBdate": now(),  # when we asked for it
                "NZBsize": nzbsize,
                "NZBtitle": nzbTitle,
                "NZBmode": nzbmode,
                "AuxInfo": auxinfo,
                "Status": "Skipped"
            }

            score = (nzbBook_match + nzbAuthor_match) / 2  # as a percentage
            # lose a point for each unwanted word in the title so we get the closest match
            wordlist = getList(nzb_Title.lower())
            words = [x for x in wordlist if x not in getList(author.lower())]
            words = [x for x in words if x not in getList(title.lower())]
            booktypes = ''
            if newValueDict['AuxInfo'] == 'eBook':
                words = [x for x in words if x not in getList(lazylibrarian.CONFIG['EBOOK_TYPE'])]
                booktypes = [x for x in wordlist if x in getList(lazylibrarian.CONFIG['EBOOK_TYPE'])]
            if newValueDict['AuxInfo'] == 'AudioBook':
                words = [x for x in words if x not in getList(lazylibrarian.CONFIG['AUDIOBOOK_TYPE'])]
                booktypes = [x for x in wordlist if x in getList(lazylibrarian.CONFIG['AUDIOBOOK_TYPE'])]
            score -= len(words)
            # prioritise titles that include the ebook types we want
            if len(booktypes):
                score += 1
            matches.append([score, nzb_Title, newValueDict, controlValueDict])

    if matches:
        highest = max(matches, key=lambda s: s[0])
        score = highest[0]
        nzb_Title = highest[1]
        newValueDict = highest[2]
        controlValueDict = highest[3]

        if score < match_ratio:
            logger.info(u'Nearest NZB match (%s%%): %s using %s search for %s %s' %
                        (score, nzb_Title, searchtype, author, title))
            return False

        logger.info(u'Best NZB match (%s%%): %s using %s search' %
                    (score, nzb_Title, searchtype))

        snatchedbooks = myDB.match('SELECT BookID from books WHERE BookID="%s" and Status="Snatched"' %
                                   newValueDict["BookID"])
        if snatchedbooks:
            logger.debug('%s already marked snatched' % nzb_Title)
            return True  # someone else found it
        else:
            logger.debug('%s adding to wanted' % nzb_Title)
            myDB.upsert("wanted", newValueDict, controlValueDict)
            if newValueDict['NZBmode'] == "torznab":
                snatch = TORDownloadMethod(newValueDict["BookID"], newValueDict["NZBtitle"], controlValueDict["NZBurl"])
            else:
                snatch = NZBDownloadMethod(newValueDict["BookID"], newValueDict["NZBtitle"], controlValueDict["NZBurl"])
            if snatch:
                logger.info('Downloading %s %s from %s' %
                            (newValueDict["AuxInfo"], newValueDict["NZBtitle"], newValueDict["NZBprov"]))
                notify_snatch("%s %s from %s at %s" %
                              (newValueDict["AuxInfo"], newValueDict["NZBtitle"], newValueDict["NZBprov"], now()))
                custom_notify_snatch(newValueDict["BookID"])
                scheduleJob(action='Start', target='processDir')
                return True + True  # we found it
    else:
        logger.debug("No nzb's found for [%s] using searchtype %s" % (book["searchterm"], searchtype))
    return False


def NZBDownloadMethod(bookid=None, nzbtitle=None, nzburl=None):
    myDB = database.DBConnection()
    Source = ''
    downloadID = ''
    if lazylibrarian.CONFIG['NZB_DOWNLOADER_SABNZBD'] and lazylibrarian.CONFIG['SAB_HOST']:
        Source = "SABNZBD"
        downloadID = sabnzbd.SABnzbd(nzbtitle, nzburl, False)  # returns nzb_ids or False

    if lazylibrarian.CONFIG['NZB_DOWNLOADER_NZBGET'] and lazylibrarian.CONFIG['NZBGET_HOST']:
        Source = "NZBGET"
        # headers = {'User-Agent': USER_AGENT}
        # data = request.request_content(url=nzburl, headers=headers)
        data, success = fetchURL(nzburl)
        if not success:
            logger.debug('Failed to read nzb data for nzbget: %s' % data)
            downloadID = ''
        else:
            nzb = classes.NZBDataSearchResult()
            nzb.extraInfo.append(data)
            nzb.name = nzbtitle
            nzb.url = nzburl
            downloadID = nzbget.sendNZB(nzb)

    if lazylibrarian.CONFIG['NZB_DOWNLOADER_SYNOLOGY'] and lazylibrarian.CONFIG['USE_SYNOLOGY'] and lazylibrarian.CONFIG['SYNOLOGY_HOST']:
        Source = "SYNOLOGY_NZB"
        downloadID = synology.addTorrent(nzburl)  # returns nzb_ids or False

    if lazylibrarian.CONFIG['NZB_DOWNLOADER_BLACKHOLE']:
        Source = "BLACKHOLE"
        nzbfile, success = fetchURL(nzburl)
        if not success:
            logger.warn('Error fetching nzb from url [%s]: %s' % (nzburl, nzbfile))
            nzbfile = ''

        if nzbfile:
            nzbname = str(nzbtitle) + '.nzb'
            nzbpath = os.path.join(lazylibrarian.CONFIG['NZB_BLACKHOLEDIR'], nzbname)
            try:
                with open(nzbpath, 'w') as f:
                    f.write(nzbfile)
                logger.debug('NZB file saved to: ' + nzbpath)
                setperm(nzbpath)
                downloadID = nzbname

            except Exception as e:
                logger.error('%s not writable, NZB not saved. Error: %s' % (nzbpath, str(e)))
                downloadID = ''

    if not Source:
        logger.warn('No NZB download method is enabled, check config.')
        return False

    if downloadID:
        logger.debug('Nzbfile has been downloaded from ' + str(nzburl))
        myDB.action('UPDATE books SET status = "Snatched" WHERE BookID="%s"' % bookid)
        myDB.action('UPDATE wanted SET status = "Snatched", Source = "%s", DownloadID = "%s" WHERE NZBurl="%s"' %
                    (Source, downloadID, nzburl))
        return True
    else:
        logger.error(u'Failed to download nzb @ <a href="%s">%s</a>' % (nzburl, Source))
        myDB.action('UPDATE wanted SET status = "Failed" WHERE NZBurl="%s"' % nzburl)
        return False
