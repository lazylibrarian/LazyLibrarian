import urllib2
import socket
import os
import re
import threading
import lazylibrarian
from . import request

from lazylibrarian import logger, database, providers, nzbget, sabnzbd, notifiers, classes, postprocess
from lib.fuzzywuzzy import fuzz
from lazylibrarian.common import USER_AGENT, scheduleJob
from lazylibrarian.formatter import plural, unaccented_str, replace_all, getList, nzbdate2format, now, check_int

# new to support torrents
from lazylibrarian.searchtorrents import TORDownloadMethod

def cron_search_nzb_book():
    threading.currentThread().name = "CRON-SEARCHNZB"
    search_nzb_book()

def search_nzb_book(books=None, reset=False):
    threadname = threading.currentThread().name
    if "Thread-" in threadname:
        threading.currentThread().name = "SEARCHNZB"

    if not lazylibrarian.USE_NZB():
        logger.warn('No NEWZNAB/TORZNAB providers set, check config')
        return
    myDB = database.DBConnection()
    searchlist = []

    if books is None:
        # We are performing a backlog search
        searchbooks = myDB.select('SELECT BookID, AuthorName, Bookname, BookSub, BookAdded from books WHERE Status="Wanted" order by BookAdded desc')
    else:
        # The user has added a new book
        searchbooks = []
        for book in books:
            searchbook = myDB.select('SELECT BookID, AuthorName, BookName, BookSub from books WHERE BookID="%s" \
                                     AND Status="Wanted"' % book['bookid'])
            for terms in searchbook:
                searchbooks.append(terms)

    if len(searchbooks) == 0:
        logger.debug("NZB search requested for no books or invalid BookID")
        return
    else:
        logger.info('NZB Searching for %i book%s' % (len(searchbooks), plural(len(searchbooks))))

    for searchbook in searchbooks:
        # searchterm is only used for display purposes
        searchterm = searchbook['AuthorName'] + ' ' + searchbook['BookName']
        if searchbook['BookSub']:
            searchterm = searchterm + ': ' + searchbook['BookSub']

        searchlist.append({"bookid": searchbook['BookID'], "bookName": searchbook['BookName'], "bookSub": searchbook['BookSub'], "authorName": searchbook['AuthorName'], "searchterm": searchterm})

    if not lazylibrarian.SAB_HOST and not lazylibrarian.NZB_DOWNLOADER_BLACKHOLE and not lazylibrarian.NZBGET_HOST:
        logger.warn('No download method is set, use SABnzbd/NZBGet or blackhole, check config')

    nzb_count = 0
    for book in searchlist:
        # first attempt, try author/title in category "book"
        resultlist, nproviders = providers.IterateOverNewzNabSites(book, 'book')

        if not nproviders:
            logger.warn('No NewzNab or TorzNab providers are set, check config')
            return  # no point in continuing

        found = processResultList(resultlist, book, "book")

        # if you can't find the book, try author/title without any "(extended details, series etc)"
        if not found and '(' in book['bookName']:
            resultlist, nproviders = providers.IterateOverNewzNabSites(book, 'shortbook')
            found = processResultList(resultlist, book, "shortbook")

        # if you can't find the book under "books", you might find under general search
        if not found:
            resultlist, nproviders = providers.IterateOverNewzNabSites(book, 'general')
            found = processResultList(resultlist, book, "general")

        if not found:
            logger.debug("NZB Searches for %s returned no results." % book['searchterm'])
        if found > True:
            nzb_count = nzb_count + 1  # we found it

    logger.info("NZBSearch for Wanted items complete, found %s book%s" % (nzb_count, plural(nzb_count)))

    if reset:
        scheduleJob(action='Restart', target='search_nzb_book')


def processResultList(resultlist, book, searchtype):
    myDB = database.DBConnection()
    dictrepl = {'...': '', '.': ' ', ' & ': ' ', ' = ': ' ', '?': '', '$': 's', ' + ': ' ', '"': '',
                ',': ' ', '*': '', '(': '', ')': '', '[': '', ']': '', '#': '', '0': '', '1': '',
                '2': '', '3': '', '4': '', '5': '', '6': '', '7': '', '8': '', '9': '', '\'': '',
                ':': '', '!': '', '-': ' ', '\s\s': ' '}
                # ' the ': ' ', ' a ': ' ', ' and ': ' ',
                # ' to ': ' ', ' of ': ' ', ' for ': ' ', ' my ': ' ', ' in ': ' ', ' at ': ' ', ' with ': ' '}

    dic = {'...': '', '.': ' ', ' & ': ' ', ' = ': ' ', '?': '', '$': 's', ' + ': ' ', '"': '',
           ',': '', '*': '', ':': '', ';': '', '\'': ''}

    match_ratio = int(lazylibrarian.MATCH_RATIO)
    reject_list = getList(lazylibrarian.REJECT_WORDS)
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

        already_failed = myDB.action('SELECT * from wanted WHERE NZBurl="%s" and Status="Failed"' %
                                    nzburl).fetchone()
        if already_failed:
            logger.debug("Rejecting %s, blacklisted at %s" % (nzb_Title, already_failed['NZBprov']))
            rejected = True

        if not rejected:
            for word in reject_list:
                if word in nzb_Title.lower() and not word in author.lower() and not word in title.lower():
                    rejected = True
                    logger.debug("Rejecting %s, contains %s" % (nzb_Title, word))
                    break

        nzbsize_temp = nzb['nzbsize']  # Need to cater for when this is NONE (Issue 35)
        if nzbsize_temp is None:
            nzbsize_temp = 1000
        nzbsize = round(float(nzbsize_temp) / 1048576, 2)

        maxsize = check_int(lazylibrarian.REJECT_MAXSIZE, 0)
        if not rejected:
            if maxsize and nzbsize > maxsize:
                rejected = True
                logger.debug("Rejecting %s, too large" % nzb_Title)

        if not rejected:
            #if nzbAuthor_match >= match_ratio and nzbBook_match >= match_ratio:
            bookid = book['bookid']
            nzbTitle = (author + ' - ' + title + ' LL.(' + book['bookid'] + ')').strip()
            nzbprov = nzb['nzbprov']
            nzbdate_temp = nzb['nzbdate']
            nzbdate = nzbdate2format(nzbdate_temp)
            nzbmode = nzb['nzbmode']
            controlValueDict = {"NZBurl": nzburl}
            newValueDict = {
                "NZBprov": nzbprov,
                "BookID": bookid,
                "NZBdate": now(),  # when we asked for it
                "NZBsize": nzbsize,
                "NZBtitle": nzbTitle,
                "NZBmode": nzbmode,
                "Status": "Skipped"
            }

            score = (nzbBook_match + nzbAuthor_match)/2  # as a percentage
            # lose a point for each extra word in the title so we get the closest match
            words = len(getList(nzb_Title))
            words -= len(getList(author))
            words -= len(getList(title))
            score -= abs(words)
            matches.append([score, nzb_Title, newValueDict, controlValueDict])

    if matches:
        highest = max(matches, key=lambda x: x[0])
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

        snatchedbooks = myDB.action('SELECT * from books WHERE BookID="%s" and Status="Snatched"' %
                                    newValueDict["BookID"]).fetchone()
        if snatchedbooks:
            logger.debug('%s already marked snatched' % nzb_Title)
            return True  # someone else found it
        else:
            logger.debug('%s adding to wanted' % nzb_Title)
            myDB.upsert("wanted", newValueDict, controlValueDict)
            if nzbmode == "torznab":
                snatch = TORDownloadMethod(newValueDict["BookID"], newValueDict["NZBprov"],
                                           newValueDict["NZBtitle"], controlValueDict["NZBurl"])
            else:
                snatch = NZBDownloadMethod(newValueDict["BookID"], newValueDict["NZBprov"],
                                           newValueDict["NZBtitle"], controlValueDict["NZBurl"])
            if snatch:
                notifiers.notify_snatch(newValueDict["NZBtitle"] + ' at ' + now())
                scheduleJob(action='Start', target='processDir')
                return True + True  # we found it
    else:
        logger.debug("No nzb's found for [%s] using searchtype %s" % (book["searchterm"], searchtype))
    return False


def NZBDownloadMethod(bookid=None, nzbprov=None, nzbtitle=None, nzburl=None):

    myDB = database.DBConnection()
    if (lazylibrarian.NZB_DOWNLOADER_SABNZBD and lazylibrarian.SAB_HOST) and not lazylibrarian.NZB_DOWNLOADER_BLACKHOLE:
        download = sabnzbd.SABnzbd(nzbtitle, nzburl)
    elif (lazylibrarian.NZB_DOWNLOADER_NZBGET and lazylibrarian.NZBGET_HOST) and not lazylibrarian.NZB_DOWNLOADER_BLACKHOLE:
        headers = {'User-Agent': USER_AGENT}
        data = request.request_content(url=nzburl, headers=headers)
        nzb = classes.NZBDataSearchResult()
        nzb.extraInfo.append(data)
        nzb.name = nzbtitle
        nzb.url = nzburl
        download = nzbget.sendNZB(nzb)

    elif lazylibrarian.NZB_DOWNLOADER_BLACKHOLE:

        try:
            req = urllib2.Request(nzburl)
            if lazylibrarian.PROXY_HOST:
                req.set_proxy(lazylibrarian.PROXY_HOST, lazylibrarian.PROXY_TYPE)
            req.add_header('User-Agent', USER_AGENT)
            nzbfile = urllib2.urlopen(req, timeout=90).read()

        except (urllib2.URLError, socket.timeout) as e:
            logger.warn('Error fetching nzb from url: %s, %s' % (nzburl, e))
            nzbfile = False

        if nzbfile:

            nzbname = str(nzbtitle) + '.nzb'
            nzbpath = os.path.join(lazylibrarian.NZB_BLACKHOLEDIR, nzbname)

            try:
                with open(nzbpath, 'w') as f:
                    f.write(nzbfile)
                logger.debug('NZB file saved to: ' + nzbpath)
                download = True

            except Exception as e:
                logger.error('%s not writable, NZB not saved. Error: %s' % (nzbpath, e))
                download = False

    else:
        logger.warn('No NZB download method is enabled, check config.')
        return False

    if download:
        logger.debug('Nzbfile has been downloaded from ' + str(nzburl))
        myDB.action('UPDATE books SET status = "Snatched" WHERE BookID="%s"' % bookid)
        myDB.action('UPDATE wanted SET status = "Snatched" WHERE NZBurl="%s"' % nzburl)
        return True
    else:
        logger.error(u'Failed to download nzb @ <a href="%s">%s</a>' % (nzburl, nzbprov))
        myDB.action('UPDATE wanted SET status = "Failed" WHERE NZBurl="%s"' % nzburl)
        return False
