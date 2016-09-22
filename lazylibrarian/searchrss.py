import urllib2
import os
import re
import threading
import lazylibrarian

from lazylibrarian import logger, database

from lib.fuzzywuzzy import fuzz
from lazylibrarian.providers import IterateOverRSSSites, get_searchterm
from lazylibrarian.common import scheduleJob
from lazylibrarian.formatter import plural, unaccented_str, replace_all, getList, check_int, now
from lazylibrarian.searchtorrents import TORDownloadMethod
from lazylibrarian.searchnzb import NZBDownloadMethod
from lazylibrarian.notifiers import notify_snatch


def cron_search_rss_book():
    threading.currentThread().name = "CRON-SEARCHRSS"
    search_rss_book()


def search_rss_book(books=None, reset=False):
    threadname = threading.currentThread().name
    if "Thread-" in threadname:
        threading.currentThread().name = "SEARCHRSS"

    if not(lazylibrarian.USE_RSS()):
        logger.warn('RSS search is disabled')
        scheduleJob(action='Stop', target='search_rss_book')
        return

    myDB = database.DBConnection()
    searchlist = []

    if books is None:
        # We are performing a backlog search
        searchbooks = myDB.select(
            'SELECT BookID, AuthorName, Bookname, BookSub, BookAdded from books WHERE Status="Wanted" order by BookAdded desc')
    else:
        # The user has added a new book
        searchbooks = []
        for book in books:
            searchbook = myDB.select('SELECT BookID, AuthorName, BookName, BookSub from books WHERE BookID="%s" \
                                     AND Status="Wanted"' % book['bookid'])
            for terms in searchbook:
                searchbooks.append(terms)

    if len(searchbooks) == 0:
        return

    logger.info('RSS Searching for %i book%s' % (len(searchbooks), plural(len(searchbooks))))

    resultlist, nproviders = IterateOverRSSSites()
    if not nproviders:
        logger.warn('No rss providers are set, check config')
        return  # No point in continuing

    dic = {'...': '', '.': ' ', ' & ': ' ', ' = ': ' ', '?': '', '$': 's', ' + ': ' ', '"': '',
           ',': '', '*': '', ':': '', ';': ''}

    rss_count = 0
    for book in searchbooks:
        authorname, bookname = get_searchterm(book, "book")
        found = processResultList(resultlist, authorname, bookname, book, 'book')

        # if you can't find the book, try title without any "(extended details, series etc)"
        if not found:
            if '(' in bookname:  # anything to shorten?
                authorname, bookname = get_searchterm(book, "shortbook")
                found = processResultList(resultlist, authorname, bookname, book, 'shortbook')

        if not found:
            logger.debug("Searches returned no results. Adding book %s - %s to queue." % (authorname, bookname))
        if found > True:
            rss_count = rss_count + 1

    logger.info("RSS Search for Wanted items complete, found %s book%s" % (rss_count, plural(rss_count)))

    if reset:
        scheduleJob(action='Restart', target='search_rss_book')


def processResultList(resultlist, authorname, bookname, book, searchtype):
    myDB = database.DBConnection()
    dictrepl = {'...': '', '.': ' ', ' & ': ' ', ' = ': ' ', '?': '', '$': 's', ' + ': ' ', '"': '',
                ',': ' ', '*': '', '(': '', ')': '', '[': '', ']': '', '#': '', '0': '', '1': '', '2': '',
                '3': '', '4': '', '5': '', '6': '', '7': '', '8': '', '9': '', '\'': '', ':': '', '!': '',
                '-': ' ', '\s\s': ' '}

    match_ratio = int(lazylibrarian.MATCH_RATIO)
    reject_list = getList(lazylibrarian.REJECT_WORDS)

    matches = []

    # bit of a misnomer now, rss can search both tor and nzb rss feeds
    for tor in resultlist:
        torTitle = unaccented_str(replace_all(tor['tor_title'], dictrepl)).strip()
        torTitle = re.sub(r"\s\s+", " ", torTitle)  # remove extra whitespace

        tor_Author_match = fuzz.token_set_ratio(authorname, torTitle)
        tor_Title_match = fuzz.token_set_ratio(bookname, torTitle)
        logger.debug("RSS Author/Title Match: %s/%s for %s" % (tor_Author_match, tor_Title_match, torTitle))
        tor_url = tor['tor_url']

        rejected = False

        already_failed = myDB.action('SELECT * from wanted WHERE NZBurl="%s" and Status="Failed"' %
                                     tor_url).fetchone()
        if already_failed:
            logger.debug("Rejecting %s, blacklisted at %s" % (torTitle, already_failed['NZBprov']))
            rejected = True

        if not rejected:
            for word in reject_list:
                if word in torTitle.lower() and word not in authorname.lower() and word not in bookname.lower():
                    rejected = True
                    logger.debug("Rejecting %s, contains %s" % (torTitle, word))
                    break

        tor_size_temp = tor['tor_size']  # Need to cater for when this is NONE (Issue 35)
        if tor_size_temp is None:
            tor_size_temp = 1000
        tor_size = round(float(tor_size_temp) / 1048576, 2)
        maxsize = check_int(lazylibrarian.REJECT_MAXSIZE, 0)

        if not rejected:
            if maxsize and tor_size > maxsize:
                rejected = True
                logger.debug("Rejecting %s, too large" % torTitle)

        if not rejected:
            bookid = book['bookid']
            tor_Title = (book["authorName"] + ' - ' + book['bookName'] +
                         ' LL.(' + book['bookid'] + ')').strip()
            tor_prov = tor['tor_prov']
            tor_feed = tor['tor_feed']

            controlValueDict = {"NZBurl": tor_url}
            newValueDict = {
                "NZBprov": tor_prov,
                "BookID": bookid,
                "NZBdate": now(),  # when we asked for it
                "NZBsize": tor_size,
                "NZBtitle": tor_Title,
                "NZBmode": "torrent",
                "Status": "Skipped"
            }

            score = (tor_Title_match + tor_Author_match) / 2  # as a percentage
            # lose a point for each extra word in the title so we get the closest match
            words = len(getList(torTitle))
            words -= len(getList(authorname))
            words -= len(getList(bookname))
            score -= abs(words)
            matches.append([score, torTitle, newValueDict, controlValueDict])

    if matches:
        highest = max(matches, key=lambda x: x[0])
        score = highest[0]
        nzb_Title = highest[1]
        newValueDict = highest[2]
        controlValueDict = highest[3]

        if score < match_ratio:
            logger.debug(u'Nearest RSS match (%s%%): %s using %s search for %s %s' %
                         (score, nzb_Title, searchtype, authorname, bookname))
            return False

        logger.info(u'Best RSS match (%s%%): %s using %s search' %
                    (score, nzb_Title, searchtype))

        snatchedbooks = myDB.action('SELECT * from books WHERE BookID="%s" and Status="Snatched"' %
                                    newValueDict["BookID"]).fetchone()

        if snatchedbooks:  # check if one of the other downloaders got there first
            logger.info('%s already marked snatched' % nzb_Title)
            return True
        else:
            myDB.upsert("wanted", newValueDict, controlValueDict)
            tor_url = controlValueDict["NZBurl"]
            if '.nzb' in tor_url:
                snatch = NZBDownloadMethod(newValueDict["BookID"], newValueDict["NZBprov"],
                                           newValueDict["NZBtitle"], controlValueDict["NZBurl"])
            else:
                """
                #  http://baconbits.org/torrents.php?action=download&authkey=<authkey>&torrent_pass=<password.hashed>&id=185398
                if not tor_url.startswith('magnet'):  # magnets don't use auth
                    pwd = lazylibrarian.RSS_PROV[tor_feed]['PASS']
                    auth = lazylibrarian.RSS_PROV[tor_feed]['AUTH']
                    # don't know what form of password hash is required, try sha1
                    tor_url = tor_url.replace('<authkey>', auth).replace('<password.hashed>', sha1(pwd))
                """
                snatch = TORDownloadMethod(newValueDict["BookID"], newValueDict["NZBprov"],
                                           newValueDict["NZBtitle"], tor_url)

            if snatch:
                logger.info('Downloading %s from %s' % (newValueDict["NZBtitle"], newValueDict["NZBprov"]))
                notify_snatch("%s from %s at %s" %
                             (newValueDict["NZBtitle"], newValueDict["NZBprov"], now()))
                scheduleJob(action='Start', target='processDir')
                return True + True  # we found it
    else:
        logger.debug("No RSS found for " + (book["authorName"] + ' ' +
                                            book['bookName']).strip())
    return False
