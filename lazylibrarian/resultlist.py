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
import traceback

import lazylibrarian
from lazylibrarian import logger, database
from lazylibrarian.common import scheduleJob
from lazylibrarian.downloadmethods import NZBDownloadMethod, TORDownloadMethod, DirectDownloadMethod
from lazylibrarian.formatter import unaccented_str, replace_all, getList, now, check_int
from lazylibrarian.notifiers import notify_snatch, custom_notify_snatch
from lazylibrarian.providers import get_searchterm
from lib.fuzzywuzzy import fuzz


def processResultList(resultlist, book, searchtype, source):
    """ Separated this out into two functions
        1. get the "best" match
        2. if over match threshold, send it to downloader
        This lets us try several searchtypes and stop at the first successful one
        and we can combine results from tor/nzb searches in one task
        Return 0 if not found, 1 if already snatched, 2 if we found it
    """
    match = findBestResult(resultlist, book, searchtype, source)
    if match:
        score = match[0]
        # resultTitle = match[1]
        # newValueDict = match[2]
        # controlValueDict = match[3]
        # dlpriority = match[4]

        if score < int(lazylibrarian.CONFIG['MATCH_RATIO']):
            return 0
        return downloadResult(match, book)
    return 0


def findBestResult(resultlist, book, searchtype, source):
    """ resultlist: collated results from search providers
        book:       the book we want to find
        searchtype: book, magazine, shortbook, audiobook etc.
        source:     nzb, tor, rss, direct
        return:     highest scoring match, or None if no match
    """
    # noinspection PyBroadException
    try:
        myDB = database.DBConnection()
        dictrepl = {'...': '', '.': ' ', ' & ': ' ', ' = ': ' ', '?': '', '$': 's', ' + ': ' ', '"': '',
                    ',': ' ', '*': '', '(': '', ')': '', '[': '', ']': '', '#': '', '0': '', '1': '',
                    '2': '', '3': '', '4': '', '5': '', '6': '', '7': '', '8': '', '9': '', '\'': '',
                    ':': '', '!': '', '-': ' ', '\s\s': ' '}

        dic = {'...': '', '.': ' ', ' & ': ' ', ' = ': ' ', '?': '', '$': 's', ' + ': ' ', '"': '',
               ',': '', '*': '', ':': '.', ';': '', '\'': ''}

        if source == 'rss':
            author, title = get_searchterm(book, searchtype)
        else:
            author = unaccented_str(replace_all(book['authorName'], dic))
            title = unaccented_str(replace_all(book['bookName'], dic))

        if book['library'] == 'AudioBook':
            reject_list = getList(lazylibrarian.CONFIG['REJECT_AUDIO'])
            maxsize = check_int(lazylibrarian.CONFIG['REJECT_MAXAUDIO'], 0)
            minsize = check_int(lazylibrarian.CONFIG['REJECT_MINAUDIO'], 0)
            auxinfo = 'AudioBook'

        else:  # elif book['library'] == 'eBook':
            reject_list = getList(lazylibrarian.CONFIG['REJECT_WORDS'])
            maxsize = check_int(lazylibrarian.CONFIG['REJECT_MAXSIZE'], 0)
            minsize = check_int(lazylibrarian.CONFIG['REJECT_MINSIZE'], 0)
            auxinfo = 'eBook'

        if source == 'nzb':
            prefix = 'nzb'
        else:  # rss and libgen return same names as torrents
            prefix = 'tor_'

        logger.debug('Searching %s %s results for best %s match' % (len(resultlist), source, auxinfo))

        matches = []
        for res in resultlist:
            resultTitle = unaccented_str(replace_all(res[prefix + 'title'], dictrepl)).strip()
            resultTitle = re.sub(r"\s\s+", " ", resultTitle)  # remove extra whitespace
            Author_match = fuzz.token_set_ratio(author, resultTitle)
            Book_match = fuzz.token_set_ratio(title, resultTitle)
            if lazylibrarian.LOGLEVEL & lazylibrarian.log_fuzz:
                logger.debug("%s author/book Match: %s/%s %s at %s" %
                             (source.upper(), Author_match, Book_match, resultTitle, res[prefix + 'prov']))

            rejected = False

            url = res[prefix + 'url']
            if url is None:
                rejected = True
                logger.debug("Rejecting %s, no URL found" % resultTitle)

            if not rejected and lazylibrarian.CONFIG['BLACKLIST_FAILED']:
                blacklisted = myDB.match('SELECT * from wanted WHERE NZBurl=? and Status="Failed"', (url,))
                if blacklisted:
                    logger.debug("Rejecting %s, url blacklisted (Failed) at %s" %
                                 (resultTitle, blacklisted['NZBprov']))
                    rejected = True
                if not rejected:
                    blacklisted = myDB.match('SELECT * from wanted WHERE NZBprov=? and NZBtitle=? and Status="Failed"',
                                             (res[prefix + 'prov'], resultTitle))
                    if blacklisted:
                        logger.debug("Rejecting %s, title blacklisted (Failed) at %s" %
                                     (resultTitle, blacklisted['NZBprov']))
                        rejected = True

            if not rejected and lazylibrarian.CONFIG['BLACKLIST_PROCESSED']:
                blacklisted = myDB.match('SELECT * from wanted WHERE NZBurl=?', (url,))
                if blacklisted:
                    logger.debug("Rejecting %s, url blacklisted (%s) at %s" %
                                 (resultTitle, blacklisted['Status'], blacklisted['NZBprov']))
                    rejected = True
                if not rejected:
                    blacklisted = myDB.match('SELECT * from wanted WHERE NZBprov=? and NZBtitle=?',
                                             (res[prefix + 'prov'], resultTitle))
                    if blacklisted:
                        logger.debug("Rejecting %s, title blacklisted (%s) at %s" %
                                     (resultTitle, blacklisted['Status'], blacklisted['NZBprov']))
                        rejected = True

            if not rejected and not url.startswith('http') and not url.startswith('magnet'):
                rejected = True
                logger.debug("Rejecting %s, invalid URL [%s]" % (resultTitle, url))

            if not rejected:
                for word in reject_list:
                    if word in getList(resultTitle.lower()) and word not in getList(author.lower()) \
                            and word not in getList(title.lower()):
                        rejected = True
                        logger.debug("Rejecting %s, contains %s" % (resultTitle, word))
                        break

            size_temp = check_int(res[prefix + 'size'], 1000)  # Need to cater for when this is NONE (Issue 35)
            size = round(float(size_temp) / 1048576, 2)

            if not rejected and maxsize and size > maxsize:
                rejected = True
                logger.debug("Rejecting %s, too large (%sMb)" % (resultTitle, size))

            if not rejected and minsize and size < minsize:
                rejected = True
                logger.debug("Rejecting %s, too small (%sMb)" % (resultTitle, size))

            if not rejected:
                bookid = book['bookid']
                # newTitle = (author + ' - ' + title + ' LL.(' + book['bookid'] + ')').strip()
                # newTitle = resultTitle + ' LL.(' + book['bookid'] + ')'

                if source == 'nzb':
                    mode = res['nzbmode']  # nzb, torznab
                else:
                    mode = res['tor_type']  # torrent, magnet, nzb(from rss), direct

                controlValueDict = {"NZBurl": url}
                newValueDict = {
                    "NZBprov": res[prefix + 'prov'],
                    "BookID": bookid,
                    "NZBdate": now(),  # when we asked for it
                    "NZBsize": size,
                    "NZBtitle": resultTitle,
                    "NZBmode": mode,
                    "AuxInfo": auxinfo,
                    "Status": "Matched"
                }

                score = (Book_match + Author_match) / 2  # as a percentage
                # lose a point for each unwanted word in the title so we get the closest match
                # but for RSS ignore anything at the end in square braces [keywords, genres etc]
                if source == 'rss':
                    wordlist = getList(resultTitle.rsplit('[', 1)[0].lower())
                else:
                    wordlist = getList(resultTitle.lower())
                words = [x for x in wordlist if x not in getList(author.lower())]
                words = [x for x in words if x not in getList(title.lower())]
                typelist = ''

                if newValueDict['AuxInfo'] == 'eBook':
                    words = [x for x in words if x not in getList(lazylibrarian.CONFIG['EBOOK_TYPE'])]
                    typelist = getList(lazylibrarian.CONFIG['EBOOK_TYPE'])
                elif newValueDict['AuxInfo'] == 'AudioBook':
                    words = [x for x in words if x not in getList(lazylibrarian.CONFIG['AUDIOBOOK_TYPE'])]
                    typelist = getList(lazylibrarian.CONFIG['AUDIOBOOK_TYPE'])
                score -= len(words)
                # prioritise titles that include the ebook types we want
                # add more points for booktypes nearer the left in the list
                # eg if epub, mobi, pdf  add 3 points if epub found, 2 for mobi, 1 for pdf
                booktypes = [x for x in wordlist if x in typelist]
                if booktypes:
                    typelist = list(reversed(typelist))
                    for item in booktypes:
                        for i in [i for i, x in enumerate(typelist) if x == item]:
                            score += i + 1

                matches.append([score, newValueDict, controlValueDict, res['priority']])

        if matches:
            highest = max(matches, key=lambda s: (s[0], s[3]))
            score = highest[0]
            newValueDict = highest[1]
            # controlValueDict = highest[2]
            dlpriority = highest[3]

            if score < int(lazylibrarian.CONFIG['MATCH_RATIO']):
                logger.info('Nearest match (%s%%): %s using %s search for %s %s' %
                            (score, newValueDict['NZBtitle'], searchtype, book['authorName'], book['bookName']))
            else:
                logger.info('Best match (%s%%): %s using %s search, %s priority %s' %
                            (score, newValueDict['NZBtitle'], searchtype, newValueDict['NZBprov'], dlpriority))
            return highest
        else:
            logger.debug("No %s found for [%s] using searchtype %s" % (source, book["searchterm"], searchtype))
        return None
    except Exception:
        logger.error('Unhandled exception in findBestResult: %s' % traceback.format_exc())


def downloadResult(match, book):
    """ match:  best result from search providers
        book:   book we are downloading (needed for reporting author name)
        return: 0 if failed to snatch
                1 if already snatched
                2 if we snatched it
    """
    # noinspection PyBroadException
    try:
        myDB = database.DBConnection()

        newValueDict = match[1]
        controlValueDict = match[2]

        # It's possible to get book and wanted tables "Snatched" status out of sync
        # for example if a user marks a book as "Wanted" after a search task snatches it and before postprocessor runs
        # so check status in both tables here
        snatched = myDB.match('SELECT BookID from wanted WHERE BookID=? and AuxInfo=? and Status="Snatched"',
                              (newValueDict["BookID"], newValueDict["AuxInfo"]))
        if snatched:
            logger.debug('%s %s %s already marked snatched in wanted table' %
                         (newValueDict["AuxInfo"], book['authorName'], book['bookName']))
            return 1  # someone else already found it

        if newValueDict["AuxInfo"] == 'eBook':
            snatched = myDB.match('SELECT BookID from books WHERE BookID=? and Status="Snatched"',
                                  (newValueDict["BookID"],))
        else:
            snatched = myDB.match('SELECT BookID from books WHERE BookID=? and AudioStatus="Snatched"',
                                  (newValueDict["BookID"],))
        if snatched:
            logger.debug('%s %s %s already marked snatched in book table' %
                         (newValueDict["AuxInfo"], book['authorName'], book['bookName']))
            return 1  # someone else already found it

        myDB.upsert("wanted", newValueDict, controlValueDict)
        if newValueDict['NZBmode'] == 'direct':
            snatch, res = DirectDownloadMethod(newValueDict["BookID"], newValueDict["NZBtitle"],
                                               controlValueDict["NZBurl"], newValueDict["AuxInfo"])
        elif newValueDict['NZBmode'] in ["torznab", "torrent", "magnet"]:
            snatch, res = TORDownloadMethod(newValueDict["BookID"], newValueDict["NZBtitle"],
                                            controlValueDict["NZBurl"], newValueDict["AuxInfo"])
        elif newValueDict['NZBmode'] == 'nzb':
            snatch, res = NZBDownloadMethod(newValueDict["BookID"], newValueDict["NZBtitle"],
                                            controlValueDict["NZBurl"], newValueDict["AuxInfo"])
        else:
            res = 'Unhandled NZBmode [%s] for %s' % (newValueDict['NZBmode'], controlValueDict["NZBurl"])
            logger.error(res)
            snatch = 0

        if snatch:
            logger.info('Downloading %s %s from %s' %
                        (newValueDict["AuxInfo"], newValueDict["NZBtitle"], newValueDict["NZBprov"]))
            custom_notify_snatch("%s %s" % (newValueDict["BookID"], newValueDict['AuxInfo']))
            notify_snatch("%s %s from %s at %s" %
                          (newValueDict["AuxInfo"], newValueDict["NZBtitle"], newValueDict["NZBprov"], now()))
            # at this point we could add NZBprov to the blocklist with a short timeout, a second or two?
            # This would implement a round-robin search system. Blocklist with an incremental counter.
            # If number of active providers == number blocklisted, so no unblocked providers are left,
            # either sleep for a while, or unblock the one with the lowest counter.
            scheduleJob(action='Start', target='processDir')
            return 2  # we found it
        else:
            myDB.action('UPDATE wanted SET status="Failed",DLResult=? WHERE NZBurl=?',
                        (res, controlValueDict["NZBurl"]))
        return 0
    except Exception:
        logger.error('Unhandled exception in downloadResult: %s' % traceback.format_exc())
        return 0
