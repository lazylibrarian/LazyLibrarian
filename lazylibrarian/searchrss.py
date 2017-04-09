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

import re
import threading
import traceback

import lazylibrarian
from lazylibrarian import logger, database
from lazylibrarian.common import scheduleJob, internet,  formatAuthorName
from lazylibrarian.formatter import plural, unaccented_str, unaccented, replace_all, getList, check_int, now
from lazylibrarian.notifiers import notify_snatch, custom_notify_snatch
from lazylibrarian.providers import IterateOverRSSSites, IterateOverGoodReads, get_searchterm
from lazylibrarian.searchnzb import NZBDownloadMethod
from lazylibrarian.searchtorrents import TORDownloadMethod
from lazylibrarian.importer import import_book, search_for
from lazylibrarian.csvfile import finditem
from lib.fuzzywuzzy import fuzz


def cron_search_rss_book():
    if 'SEARCHALLRSS' not in [n.name for n in [t for t in threading.enumerate()]]:
        search_rss_book()


def search_rss_book(books=None, reset=False):
    try:
        threadname = threading.currentThread().name
        if "Thread-" in threadname:
            if books is None:
                threading.currentThread().name = "SEARCHALLRSS"
            else:
                threading.currentThread().name = "SEARCHRSS"

        if not(lazylibrarian.USE_RSS()):
            logger.warn('RSS search is disabled')
            scheduleJob(action='Stop', target='search_rss_book')
            return

        if not internet():
            logger.warn('Search RSS Book: No internet connection')
            return

        myDB = database.DBConnection()

        resultlist, wishproviders = IterateOverGoodReads()
        if not wishproviders:
            logger.debug('No rss wishlists are set')
        else:
            # for each item in resultlist, add to database if necessary, and mark as wanted
            for book in resultlist:
                # we get rss_author, rss_title, rss_isbn, rss_bookid (goodreads bookid)
                # we can just use bookid if goodreads, or try isbn and name matching on author/title if googlebooks
                # not sure if anyone would use a goodreads wishlist if not using goodreads interface...
                if book['rss_bookid'] and lazylibrarian.CONFIG['BOOK_API'] == "GoodReads":
                    bookmatch = myDB.match('select Status,BookName from books where bookid="%s"' % book['rss_bookid'])
                    if bookmatch:
                        bookstatus = bookmatch['Status']
                        bookname = bookmatch['BookName']
                        if bookstatus in ['Open', 'Wanted', 'Have']:
                            logger.info(u'Found book %s, already marked as "%s"' % (bookname, bookstatus))
                        else:  # skipped/ignored
                            logger.info(u'Found book %s, marking as "Wanted"' % bookname)
                            controlValueDict = {"BookID": bookid}
                            newValueDict = {"Status": "Wanted"}
                            myDB.upsert("books", newValueDict, controlValueDict)
                    else:
                      import_book(book['rss_bookid'])
                else:
                    item = {}
                    headers = []
                    item['Title'] = book['rss_title']
                    if book['rss_bookid']:
                        item['BookID'] = book['rss_bookid']
                        headers.append('BookID')
                    if book['rss_isbn']:
                        item['ISBN'] = book['rss_isbn']
                        headers.append('ISBN')
                    bookmatch = finditem(item, book['rss_author'], headers)
                    if bookmatch:  # it's already in the database
                        authorname = bookmatch['AuthorName']
                        bookname = bookmatch['BookName']
                        bookid = bookmatch['BookID']
                        bookstatus = bookmatch['Status']
                        if bookstatus in ['Open', 'Wanted', 'Have']:
                            logger.info(u'Found book %s by %s, already marked as "%s"' % (bookname, authorname, bookstatus))
                        else:  # skipped/ignored
                            logger.info(u'Found book %s by %s, marking as "Wanted"' % (bookname, authorname))
                            controlValueDict = {"BookID": bookid}
                            newValueDict = {"Status": "Wanted"}
                            myDB.upsert("books", newValueDict, controlValueDict)
                    else:  # not in database yet
                        results = ''
                        if book['rss_isbn']:
                            results = search_for(book['rss_isbn'])
                        if results:
                            result = results[0]
                            if result['isbn_fuzz'] > lazylibrarian.CONFIG['MATCH_RATIO']:
                                logger.info("Found (%s%%) %s: %s" %
                                            (result['isbn_fuzz'], result['authorname'], result['bookname']))
                                import_book(result['bookid'])
                                bookmatch = True
                        if not results:
                            searchterm = "%s <ll> %s" % (item['Title'], formatAuthorName(book['rss_author']))
                            results = search_for(unaccented(searchterm))
                        if results:
                            result = results[0]
                            if result['author_fuzz'] > lazylibrarian.CONFIG['MATCH_RATIO'] \
                                and result['book_fuzz'] > lazylibrarian.CONFIG['MATCH_RATIO']:
                                logger.info("Found (%s%% %s%%) %s: %s" % (result['author_fuzz'], result['book_fuzz'],
                                                                            result['authorname'], result['bookname']))
                                import_book(result['bookid'])
                                bookmatch = True

                    if not bookmatch:
                        msg = "Skipping book %s by %s" % (item['Title'], book['rss_author'])
                        # noinspection PyUnboundLocalVariable
                        if not results:
                            msg += ', No results returned'
                            logger.warn(msg)
                        else:
                            msg += ', No match found'
                            logger.warn(msg)
                            msg = "Closest match (%s%% %s%%) %s: %s" % (result['author_fuzz'], result['book_fuzz'],
                                                                        result['authorname'], result['bookname'])
                            logger.warn(msg)

        if books is None:
            # We are performing a backlog search
            cmd = 'SELECT BookID, AuthorName, Bookname, BookSub, BookAdded from books,authors '
            cmd += 'WHERE books.AuthorID = authors.AuthorID and books.Status="Wanted" order by BookAdded desc'
            searchbooks = myDB.select(cmd)

        else:
            # The user has added a new book
            searchbooks = []
            for book in books:
                cmd = 'SELECT BookID, AuthorName, BookName, BookSub from books,authors '
                cmd += 'WHERE books.AuthorID = authors.AuthorID and BookID="%s" ' % book['bookid']
                cmd += 'AND books.Status="Wanted"'
                searchbook = myDB.select(cmd)
                for terms in searchbook:
                    searchbooks.append(terms)

        if len(searchbooks) == 0:
            return

        logger.info('RSS Searching for %i book%s' % (len(searchbooks), plural(len(searchbooks))))

        resultlist, nproviders = IterateOverRSSSites()
        if not nproviders:
            if not wishproviders:
                logger.warn('No rss providers are set, check config')
            return  # No point in continuing

        rss_count = 0
        for book in searchbooks:
            authorname, bookname = get_searchterm(book, "book")
            found = processResultList(resultlist, authorname, bookname, book, 'book')

            # if you can't find the book, try title without any "(extended details, series etc)"
            if not found and '(' in bookname:  # anything to shorten?
                authorname, bookname = get_searchterm(book, "shortbook")
                found = processResultList(resultlist, authorname, bookname, book, 'shortbook')

            if not found:
                logger.debug("Searches returned no results. Adding book %s - %s to queue." % (authorname, bookname))
            if found > True:
                rss_count += 1

        logger.info("RSS Search for Wanted items complete, found %s book%s" % (rss_count, plural(rss_count)))

        if reset:
            scheduleJob(action='Restart', target='search_rss_book')

    except Exception:
        logger.error('Unhandled exception in search_rss_book: %s' % traceback.format_exc())


def processResultList(resultlist, authorname, bookname, book, searchtype):
    myDB = database.DBConnection()
    dictrepl = {'...': '', '.': ' ', ' & ': ' ', ' = ': ' ', '?': '', '$': 's', ' + ': ' ', '"': '',
                ',': ' ', '*': '', '(': '', ')': '', '[': '', ']': '', '#': '', '0': '', '1': '', '2': '',
                '3': '', '4': '', '5': '', '6': '', '7': '', '8': '', '9': '', '\'': '', ':': '', '!': '',
                '-': ' ', '\s\s': ' '}

    match_ratio = int(lazylibrarian.CONFIG['MATCH_RATIO'])
    reject_list = getList(lazylibrarian.CONFIG['REJECT_WORDS'])

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

        already_failed = myDB.match('SELECT * from wanted WHERE NZBurl="%s" and Status="Failed"' % tor_url)
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
        tor_size_temp = check_int(tor_size_temp, 1000)
        tor_size = round(float(tor_size_temp) / 1048576, 2)

        maxsize = check_int(lazylibrarian.CONFIG['REJECT_MAXSIZE'], 0)
        if not rejected:
            if maxsize and tor_size > maxsize:
                rejected = True
                logger.debug("Rejecting %s, too large" % torTitle)

        minsize = check_int(lazylibrarian.CONFIG['REJECT_MINSIZE'], 0)
        if not rejected:
            if minsize and tor_size < minsize:
                rejected = True
                logger.debug("Rejecting %s, too small" % torTitle)

        if not rejected:
            bookid = book['bookid']
            tor_Title = (book["authorName"] + ' - ' + book['bookName'] +
                         ' LL.(' + book['bookid'] + ')').strip()
            tor_prov = tor['tor_prov']

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
            # but ignore anything at the end in square braces [keywords, genres etc]
            words = len(getList(torTitle.rsplit('[', 1)[0]))
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

        snatchedbooks = myDB.match('SELECT BookID from books WHERE BookID="%s" and Status="Snatched"' %
                                   newValueDict["BookID"])

        if snatchedbooks:  # check if one of the other downloaders got there first
            logger.info('%s already marked snatched' % nzb_Title)
            return True
        else:
            myDB.upsert("wanted", newValueDict, controlValueDict)
            tor_url = controlValueDict["NZBurl"]
            if '.nzb' in tor_url:
                snatch = NZBDownloadMethod(newValueDict["BookID"], newValueDict["NZBtitle"], controlValueDict["NZBurl"])
            else:
                """
                #  http://baconbits.org/torrents.php?action=download&authkey=<authkey>
                    &torrent_pass=<password.hashed>&id=185398
                if not tor_url.startswith('magnet'):  # magnets don't use auth
                    pwd = lazylibrarian.RSS_PROV[tor_feed]['PASS']
                    auth = lazylibrarian.RSS_PROV[tor_feed]['AUTH']
                    # don't know what form of password hash is required, try sha1
                    tor_url = tor_url.replace('<authkey>', auth).replace('<password.hashed>', sha1(pwd))
                """
                snatch = TORDownloadMethod(newValueDict["BookID"], newValueDict["NZBtitle"], tor_url)

            if snatch:
                logger.info('Downloading %s from %s' % (newValueDict["NZBtitle"], newValueDict["NZBprov"]))
                notify_snatch("%s from %s at %s" %
                              (newValueDict["NZBtitle"], newValueDict["NZBprov"], now()))
                custom_notify_snatch(newValueDict["BookID"])
                scheduleJob(action='Start', target='processDir')
                return True + True  # we found it
    else:
        logger.debug("No RSS found for " + (book["authorName"] + ' ' +
                                            book['bookName']).strip())
    return False
