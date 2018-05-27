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

from lazylibrarian import logger, database
from lib.rfeed import Item, Guid, Feed


def genFeed(ftype, limit=10, user=0, baseurl=''):
    if ftype == 'eBook':
        cmd = "select AuthorName,BookName,BookDesc,BookLibrary,BookID,BookLink from books,authors where"
        cmd += " BookLibrary != '' and books.AuthorID = authors.AuthorID order by BookLibrary desc limit %s" % limit
    elif ftype == 'AudioBook':
        cmd = "select AuthorName,BookName,BookDesc,AudioLibrary,BookID,BookLink from books,authors where"
        cmd += " AudioLibrary != '' and books.AuthorID = authors.AuthorID order by AudioLibrary desc limit %s" % limit
    elif ftype == 'Magazine':
        cmd = "select Title,IssueDate,IssueAcquired,IssueID from issues order by IssueAcquired desc limit %s" % limit
    else:
        logger.debug("Invalid feed type")
        return None

    myDB = database.DBConnection()
    results = myDB.select(cmd)
    items = []
    logger.debug("Found %s %s results" % (len(results), ftype))

    for res in results:
        link = ''
        if ftype == 'eBook':
            pubdate = datetime.datetime.strptime(res['BookLibrary'], '%Y-%m-%d %H:%M:%S')
            title = res['BookName']
            author = res['AuthorName']
            description = res['BookDesc']
            bookid = res['BookID']
            if user:
                link = '%s/serveBook/%s%s' % (baseurl, user, res['BookID'])

        elif ftype == 'AudioBook':
            pubdate = datetime.datetime.strptime(res['AudioLibrary'], '%Y-%m-%d %H:%M:%S')
            title = res['BookName']
            author = res['AuthorName']
            description = res['BookDesc']
            bookid = res['BookID']
            if user:
                link = '%s/serveAudio/%s%s' % (baseurl, user, res['BookID'])

        else:  # ftype == 'Magazine':
            pubdate = datetime.datetime.strptime(res['IssueAcquired'], '%Y-%m-%d')
            title = res['IssueDate']
            author = res['Title']
            description = author + ' ' + title
            bookid = res['IssueID']
            if user:
                link = '%s/serveIssue/%s%s' % (baseurl, user, res['IssueID'])

        item = Item(
            title=title,
            link=link,
            description=description,
            author=author,
            guid=Guid(bookid),
            pubDate=pubdate
        )
        items.append(item)

    title = "%s Recent Downloads" % ftype
    feed = Feed(
        title=title,
        link="http://www.example.com/rss",
        description="LazyLibrarian %s" % title,
        language="en-US",
        lastBuildDate=datetime.datetime.now(),
        items=items)
    logger.debug("Returning %s feed items" % len(items))
    return feed.rss()
