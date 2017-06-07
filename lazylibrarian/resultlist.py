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

import lazylibrarian
from lazylibrarian import logger, database
from lazylibrarian.common import scheduleJob
from lazylibrarian.downloadmethods import NZBDownloadMethod, TORDownloadMethod, DirectDownloadMethod
from lazylibrarian.formatter import unaccented_str, replace_all, getList, now, check_int
from lazylibrarian.notifiers import notify_snatch, custom_notify_snatch
from lazylibrarian.providers import get_searchterm
from lib.fuzzywuzzy import fuzz


def processResultList(resultlist, book, searchtype, source):
    myDB = database.DBConnection()
    dictrepl = {'...': '', '.': ' ', ' & ': ' ', ' = ': ' ', '?': '', '$': 's', ' + ': ' ', '"': '',
                ',': ' ', '*': '', '(': '', ')': '', '[': '', ']': '', '#': '', '0': '', '1': '',
                '2': '', '3': '', '4': '', '5': '', '6': '', '7': '', '8': '', '9': '', '\'': '',
                ':': '', '!': '', '-': ' ', '\s\s': ' '}

    dic = {'...': '', '.': ' ', ' & ': ' ', ' = ': ' ', '?': '', '$': 's', ' + ': ' ', '"': '',
           ',': '', '*': '', ':': '.', ';': '', '\'': ''}

    match_ratio = int(lazylibrarian.CONFIG['MATCH_RATIO'])
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
    elif source == 'tor':
        prefix = 'tor_'
    else:  # rss returns torrents
        prefix = 'tor_'

    matches = []
    for res in resultlist:
        Title = unaccented_str(replace_all(res[prefix + 'title'], dictrepl)).strip()
        Title = re.sub(r"\s\s+", " ", Title)  # remove extra whitespace
        if source == 'rss':
            author, title = get_searchterm(book, searchtype)
        Author_match = fuzz.token_set_ratio(author, Title)
        Book_match = fuzz.token_set_ratio(title, Title)
        logger.debug(u"%s author/book Match: %s/%s for %s at %s" %
                     (source.upper(), Author_match, Book_match, Title, res[prefix + 'prov']))

        rejected = False

        url = res[prefix + 'url']
        if url is None:
            rejected = True
            logger.debug("Rejecting %s, no URL found" % Title)

        if not rejected:
            already_failed = myDB.match('SELECT * from wanted WHERE NZBurl="%s" and Status="Failed"' % url)
            if already_failed:
                logger.debug("Rejecting %s, blacklisted at %s" % (Title, already_failed['NZBprov']))
                rejected = True

        if not rejected:
            if not url.startswith('http'):
                rejected = True
                logger.debug("Rejecting %s, invalid URL" % Title)

        if not rejected:
            for word in reject_list:
                if word in Title.lower() and word not in author.lower() and word not in title.lower():
                    rejected = True
                    logger.debug("Rejecting %s, contains %s" % (Title, word))
                    break

        size_temp = res[prefix + 'size']  # Need to cater for when this is NONE (Issue 35)
        size_temp = check_int(size_temp, 1000)
        size = round(float(size_temp) / 1048576, 2)

        if not rejected:
            if maxsize and size > maxsize:
                rejected = True
                logger.debug("Rejecting %s, too large" % Title)

        if not rejected:
            if minsize and size < minsize:
                rejected = True
                logger.debug("Rejecting %s, too small" % Title)

        if not rejected:
            bookid = book['bookid']
            newTitle = (author + ' - ' + title + ' LL.(' + book['bookid'] + ')').strip()

            if source == 'nzb':
                mode = res['nzbmode']
            elif source == 'tor':
                mode = "torrent"
            else:  # rss returns torrents
                mode = "torrent"

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
                temptitle = Title.rsplit('[', 1)[0]
                wordlist = getList(temptitle.lower())
            else:
                wordlist = getList(Title.lower())
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
            if len(booktypes):
                score += 1
            matches.append([score, Title, newValueDict, controlValueDict, res['priority']])

    if matches:
        highest = max(matches, key=lambda s: (s[0], s[4]))
        score = highest[0]
        Title = highest[1]
        newValueDict = highest[2]
        controlValueDict = highest[3]

        if score < match_ratio:
            logger.info(u'Nearest %s match (%s%%): %s using %s search for %s %s' %
                        (source.upper(), score, Title, searchtype, author, title))
            return False

        logger.info(u'Best %s match (%s%%): %s using %s search' % (source.upper(), score, Title, searchtype))

        if auxinfo == 'eBook':
            snatchedbooks = myDB.match('SELECT BookID from books WHERE BookID="%s" and Status="Snatched"' %
                                       newValueDict["BookID"])
        else:
            snatchedbooks = myDB.match('SELECT BookID from books WHERE BookID="%s" and AudioStatus="Snatched"' %
                                       newValueDict["BookID"])

        if snatchedbooks:
            logger.debug('%s %s already marked snatched' % (author, title))
            return True  # someone else found it
        else:
            myDB.upsert("wanted", newValueDict, controlValueDict)
            if '.nzb' in controlValueDict["NZBurl"]:
                snatch = NZBDownloadMethod(newValueDict["BookID"], newValueDict["NZBtitle"], controlValueDict["NZBurl"])
            elif newValueDict["NZBprov"] == 'libgen':  # for libgen we use direct download links
                snatch = DirectDownloadMethod(newValueDict["BookID"], newValueDict["NZBtitle"],
                                              controlValueDict["NZBurl"], Title)
            elif newValueDict['NZBmode'] == "torznab" or newValueDict['NZBmode'] == "torrent":
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
        logger.debug("No %s found for [%s] using searchtype %s" % (source, book["searchterm"], searchtype))
    return False
