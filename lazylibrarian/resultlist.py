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
    """
    match = findBestResult(resultlist, book, searchtype, source)
    if match:
        score = match[0]
        # resultTitle = match[1]
        # newValueDict = match[2]
        # controlValueDict = match[3]
        # dlpriority = match[4]

        if score < int(lazylibrarian.CONFIG['MATCH_RATIO']):
            return False
        return downloadResult(match, book)
    return False


def findBestResult(resultlist, book, searchtype, source):
    """ resultlist: collated results from search providers
        book:       the book we want to find
        searchtype: book, magazine, shortbook, audiobook etc.
        source:     nzb, tor, rss
        return:     highest scoring match, or None if no match
    """
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
        else:  # rss returns same names as torrents
            prefix = 'tor_'

        logger.debug('Searching %s %s results for best %s match' % (len(resultlist), source, auxinfo))

        matches = []
        for res in resultlist:
            resultTitle = unaccented_str(replace_all(res[prefix + 'title'], dictrepl)).strip()
            resultTitle = re.sub(r"\s\s+", " ", resultTitle)  # remove extra whitespace
            Author_match = fuzz.token_set_ratio(author, resultTitle)
            Book_match = fuzz.token_set_ratio(title, resultTitle)
            logger.debug(u"%s author/book Match: %s/%s %s at %s" %
                         (source.upper(), Author_match, Book_match, resultTitle, res[prefix + 'prov']))

            rejected = False

            url = res[prefix + 'url']
            if url is None:
                rejected = True
                logger.debug("Rejecting %s, no URL found" % resultTitle)

            if not rejected:
                already_failed = myDB.match('SELECT * from wanted WHERE NZBurl=? and Status="Failed"', (url,))
                if already_failed:
                    logger.debug("Rejecting %s, blacklisted at %s" % (resultTitle, already_failed['NZBprov']))
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
                    logger.debug("Rejecting %s, too large" % resultTitle)

            if not rejected and minsize and size < minsize:
                rejected = True
                logger.debug("Rejecting %s, too small" % resultTitle)

            if not rejected:
                bookid = book['bookid']
                newTitle = (author + ' - ' + title + ' LL.(' + book['bookid'] + ')').strip()

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
                    "NZBtitle": newTitle,
                    "NZBmode": mode,
                    "AuxInfo": auxinfo,
                    "Status": "Skipped"
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
                booktypes = ''
                if newValueDict['AuxInfo'] == 'eBook':
                    words = [x for x in words if x not in getList(lazylibrarian.CONFIG['EBOOK_TYPE'])]
                    booktypes = [x for x in wordlist if x in getList(lazylibrarian.CONFIG['EBOOK_TYPE'])]
                elif newValueDict['AuxInfo'] == 'AudioBook':
                    words = [x for x in words if x not in getList(lazylibrarian.CONFIG['AUDIOBOOK_TYPE'])]
                    booktypes = [x for x in wordlist if x in getList(lazylibrarian.CONFIG['AUDIOBOOK_TYPE'])]
                score -= len(words)
                # prioritise titles that include the ebook types we want
                score += len(booktypes)
                matches.append([score, resultTitle, newValueDict, controlValueDict, res['priority']])

        if matches:
            highest = max(matches, key=lambda s: (s[0], s[4]))
            score = highest[0]
            resultTitle = highest[1]
            newValueDict = highest[2]
            # controlValueDict = highest[3]
            dlpriority = highest[4]

            if score < int(lazylibrarian.CONFIG['MATCH_RATIO']):
                logger.info(u'Nearest match (%s%%): %s using %s search for %s %s' %
                            (score, resultTitle, searchtype, book['authorName'], book['bookName']))
            else:
                logger.info(u'Best match (%s%%): %s using %s search, %s priority %s' %
                            (score, resultTitle, searchtype, newValueDict['NZBprov'], dlpriority))
            return highest
        else:
            logger.debug("No %s found for [%s] using searchtype %s" % (source, book["searchterm"], searchtype))
        return None
    except Exception:
        logger.error('Unhandled exception in findBestResult: %s' % traceback.format_exc())


def downloadResult(match, book):
    """ match:  best result from search providers
        book:   book we are downloading
        return: True if already snatched, False if failed to snatch, >True if we snatched it
    """
    try:
        myDB = database.DBConnection()

        resultTitle = match[1]
        newValueDict = match[2]
        controlValueDict = match[3]

        if book['library'] == 'AudioBook':
            auxinfo = 'AudioBook'
        else:  # elif book['library'] == 'eBook':
            auxinfo = 'eBook'

        if auxinfo == 'eBook':
            snatchedbooks = myDB.match('SELECT BookID from books WHERE BookID=? and Status="Snatched"',
                                       (newValueDict["BookID"],))
        else:
            snatchedbooks = myDB.match('SELECT BookID from books WHERE BookID=? and AudioStatus="Snatched"',
                                       (newValueDict["BookID"],))

        if snatchedbooks:
            logger.debug('%s %s already marked snatched' % (book['authorName'], book['bookName']))
            return True  # someone else already found it
        else:
            myDB.upsert("wanted", newValueDict, controlValueDict)
            if 'libgen' in newValueDict["NZBprov"]:  # for libgen we use direct download links
                snatch = DirectDownloadMethod(newValueDict["BookID"], newValueDict["NZBtitle"],
                                              controlValueDict["NZBurl"], resultTitle, auxinfo)
            elif newValueDict['NZBmode'] in ["torznab", "torrent", "magnet"]:
                snatch = TORDownloadMethod(newValueDict["BookID"], newValueDict["NZBtitle"],
                                           controlValueDict["NZBurl"], auxinfo)
            elif newValueDict['NZBmode'] == 'nzb':
                snatch = NZBDownloadMethod(newValueDict["BookID"], newValueDict["NZBtitle"],
                                           controlValueDict["NZBurl"], auxinfo)
            else:
                logger.error('Unhandled NZBmode [%s] for %s' % (newValueDict['NZBmode'], controlValueDict["NZBurl"]))
                snatch = False

            if snatch:
                logger.info('Downloading %s %s from %s' %
                            (auxinfo, newValueDict["NZBtitle"], newValueDict["NZBprov"]))
                notify_snatch("%s %s from %s at %s" %
                              (auxinfo, newValueDict["NZBtitle"], newValueDict["NZBprov"], now()))
                custom_notify_snatch(newValueDict["BookID"])
                # at this point we could add NZBprov to the blocklist with a short timeout, a second or two?
                # This would implement a round-robin search system. Blocklist with an incremental counter.
                # If number of active providers == number blocklisted, so no unblocked providers are left,
                # either sleep for a while, or unblock the one with the lowest counter.
                scheduleJob(action='Start', target='processDir')
                return True + True  # we found it
        return False
    except Exception:
        logger.error('Unhandled exception in downloadResult: %s' % traceback.format_exc())
