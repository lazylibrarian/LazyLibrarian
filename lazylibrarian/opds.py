#!/usr/bin/env python
# -*- coding: utf-8 -*-

#  This file is part of LazyLibrarian.
#
#  LazyLibrarian is free software: you can redistribute it and/or modify
#  it under the terms of the GNU General Public License as published by
#  the Free Software Foundation, either version 3 of the License, or
#  (at your option) any later version.
#
#  LazyLibrarian is distributed in the hope that it will be useful,
#  but WITHOUT ANY WARRANTY; without even the implied warranty of
#  MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
#  GNU General Public License for more details.
#
#  You should have received a copy of the GNU General Public License
#  along with LazyLibrarian.  If not, see <http://www.gnu.org/licenses/>.
#  Adapted for LazyLibrarian from Mylar

import lazylibrarian
from lazylibrarian import logger, database
import cherrypy
import os
import datetime
from cherrypy.lib.static import serve_file
from lazylibrarian.formatter import makeUnicode, check_int, plural, getList
from lazylibrarian.common import mimeType, zipAudio
from lazylibrarian.cache import cache_img
# noinspection PyUnresolvedReferences
from lib.six.moves.urllib_parse import quote_plus
from lib.six import string_types


searchable = ['Authors', 'Magazines', 'Series', 'Author', 'RecentBooks', 'RecentAudio', 'RecentMags']

cmd_list = searchable + ['root', 'Serve', 'search', 'Members', 'Magazine']


class OPDS(object):

    def __init__(self):
        self.cmd = None
        self.PAGE_SIZE = 30
        self.img = None
        self.file = None
        self.filename = None
        self.kwargs = None
        self.data = None

        if lazylibrarian.CONFIG['HTTP_ROOT'] is None:
            self.opdsroot = '/opds'
        elif lazylibrarian.CONFIG['HTTP_ROOT'].endswith('/'):
            self.opdsroot = lazylibrarian.CONFIG['HTTP_ROOT'] + 'opds'
        else:
            if lazylibrarian.CONFIG['HTTP_ROOT'] != '/':
                self.opdsroot = lazylibrarian.CONFIG['HTTP_ROOT'] + '/opds'
            else:
                self.opdsroot = lazylibrarian.CONFIG['HTTP_ROOT'] + 'opds'

        my_ip = None
        if 'X-Forwarded-Host' in cherrypy.request.headers:
            my_ip = cherrypy.request.headers['X-Forwarded-Host']
        elif 'Host' in cherrypy.request.headers:
            my_ip = cherrypy.request.headers['Host']
        if my_ip:
            self.opdsroot = '%s://%s%s' % (cherrypy.request.scheme, my_ip, self.opdsroot)

        self.searchroot = self.opdsroot.replace('/opds', '')

    def checkParams(self, **kwargs):

        if 'cmd' not in kwargs:
            self.cmd = 'root'

        if not lazylibrarian.CONFIG['OPDS_ENABLED']:
            self.data = self._error_with_message('OPDS not enabled')
            return

        if not self.cmd:
            if kwargs['cmd'] not in cmd_list:
                self.data = self._error_with_message('Unknown command: %s' % kwargs['cmd'])
                return
            else:
                self.cmd = kwargs.pop('cmd')

        self.kwargs = kwargs
        self.data = 'OK'

    def fetchData(self):

        if self.data == 'OK':
            if 'X-Forwarded-For' in cherrypy.request.headers:
                remote_ip = cherrypy.request.headers['X-Forwarded-For']  # apache2
            elif 'X-Host' in cherrypy.request.headers:
                remote_ip = cherrypy.request.headers['X-Host']  # lighthttpd
            elif 'Remote-Addr' in cherrypy.request.headers:
                remote_ip = cherrypy.request.headers['Remote-Addr']
            else:
                remote_ip = cherrypy.request.remote.ip
            logger.debug('Received OPDS command from %s: %s %s' % (remote_ip, self.cmd, self.kwargs))
            if self.cmd == 'search':
                if 't' in self.kwargs and self.kwargs['t'] in searchable:
                    self.cmd = self.kwargs['t']
                else:
                    self.cmd = 'RecentBooks'
            methodToCall = getattr(self, "_" + self.cmd)
            _ = methodToCall(**self.kwargs)
            if self.img:
                return serve_file(self.img, content_type='image/jpeg')
            if self.file and self.filename:
                logger.debug('Downloading %s: %s' % (self.filename, self.file))
                return serve_file(self.file, mimeType(self.filename), 'attachment', name=self.filename)
            if isinstance(self.data, string_types):
                return self.data
            else:
                cherrypy.response.headers['Content-Type'] = "text/xml"
                return lazylibrarian.webServe.serve_template(templatename="opds.html",
                                                             title=self.data['title'], opds=self.data)
        else:
            return self.data


    def multiLink(self, bookfile, bookid):
        types = []
        multi = ''
        basename, extn = os.path.splitext(bookfile)
        for item in getList(lazylibrarian.CONFIG['EBOOK_TYPE']):
            target = basename + '.' + item
            if os.path.isfile(target):
                types.append(item)
        if len(types) > 1:
            for fmt in types:
                multi += '<link href="'
                multi += '%s?cmd=Serve&amp;bookid=%s&amp;fmt=%s' % (self.opdsroot, quote_plus(bookid), fmt)
                multi += '" rel="http://opds-spec.org/acquisition" type="' + mimeType('.' + fmt) + '"/>'
        return multi


    @staticmethod
    def _error_with_message(message):
        error = '<feed><error>%s</error></feed>' % message
        cherrypy.response.headers['Content-Type'] = "text/xml"
        return error

    def _root(self):
        myDB = database.DBConnection()
        feed = {'title': 'LazyLibrarian OPDS', 'id': 'OPDSRoot', 'updated': now()}
        links = []
        entries = []
        links.append(getLink(href=self.opdsroot, ftype='application/atom+xml; profile=opds-catalog; kind=navigation',
                             rel='start', title='Home'))
        links.append(getLink(href=self.opdsroot, ftype='application/atom+xml; profile=opds-catalog; kind=navigation',
                             rel='self'))
        links.append(getLink(href='%s/opensearchbooks.xml' % self.searchroot,
                             ftype='application/opensearchdescription+xml', rel='search', title='Search Books'))
        entries.append(
            {
                'title': 'Recent eBooks',
                'id': 'RecentBooks',
                'updated': now(),
                'content': 'Recently Added eBooks',
                'href': '%s?cmd=RecentBooks' % self.opdsroot,
                'kind': 'acquisition',
                'rel': 'subsection',
            }
        )
        entries.append(
            {
                'title': 'Recent AudioBooks',
                'id': 'RecentAudio',
                'updated': now(),
                'content': 'Recently Added AudioBooks',
                'href': '%s?cmd=RecentAudio' % self.opdsroot,
                'kind': 'acquisition',
                'rel': 'subsection',
            }
        )
        entries.append(
            {
                'title': 'Recent Magazines',
                'id': 'RecentMags',
                'updated': now(),
                'content': 'Recently Added Magazines',
                'href': '%s?cmd=RecentMags' % self.opdsroot,
                'kind': 'acquisition',
                'rel': 'subsection',
            }
        )
        authors = myDB.select("SELECT authorname from authors WHERE Status != 'Ignored' order by authorname")
        if len(authors) > 0:
            count = len(authors)
            entries.append(
                {
                    'title': 'Authors (%s)' % count,
                    'id': 'Authors',
                    'updated': now(),
                    'content': 'List of Authors',
                    'href': '%s?cmd=Authors' % self.opdsroot,
                    'kind': 'navigation',
                    'rel': 'subsection',
                }
            )
        series = myDB.select("SELECT Have from series WHERE CAST(Have AS INTEGER) > 0 order by seriesname")
        if len(series) > 0:
            count = len(series)
            entries.append(
                {
                    'title': 'Series (%s)' % count,
                    'id': 'Series',
                    'updated': now(),
                    'content': 'List of Series',
                    'href': '%s?cmd=Series' % self.opdsroot,
                    'kind': 'navigation',
                    'rel': 'subsection',
                }
            )
        magazines = myDB.select("SELECT title from magazines WHERE LastAcquired != '' order by title")
        if len(magazines) > 0:
            count = len(magazines)
            entries.append(
                {
                    'title': 'Magazines (%s)' % count,
                    'id': 'Magazines',
                    'updated': now(),
                    'content': 'List of Magazines',
                    'href': '%s?cmd=Magazines' % self.opdsroot,
                    'kind': 'navigation',
                    'rel': 'subsection',
                }
            )

        feed['links'] = links
        feed['entries'] = entries
        # logger.debug("Returning %s entries" % len(entries))
        self.data = feed
        return

    def _Authors(self, **kwargs):
        index = 0
        if 'index' in kwargs:
            index = check_int(kwargs['index'], 0)
        myDB = database.DBConnection()
        feed = {'title': 'LazyLibrarian OPDS - Authors', 'id': 'Authors', 'updated': now()}
        links = []
        entries = []
        links.append(getLink(href=self.opdsroot, ftype='application/atom+xml; profile=opds-catalog; kind=navigation',
                             rel='start', title='Home'))
        links.append(getLink(href='%s?cmd=Authors' % self.opdsroot,
                             ftype='application/atom+xml; profile=opds-catalog; kind=navigation', rel='self'))
        links.append(getLink(href='%s/opensearchauthors.xml' % self.searchroot,
                             ftype='application/opensearchdescription+xml', rel='search', title='Search Authors'))
        cmd = "SELECT AuthorName,AuthorID,HaveBooks,TotalBooks,DateAdded,AuthorImg from Authors WHERE "
        if 'query' in kwargs:
            cmd += "AuthorName LIKE '%" + kwargs['query'] + "%' AND "
        cmd += "CAST(HaveBooks AS INTEGER) > 0 order by AuthorName"
        results = myDB.select(cmd)
        page = results[index:(index + self.PAGE_SIZE)]
        for author in page:
            totalbooks = check_int(author['TotalBooks'], 0)
            havebooks = check_int(author['HaveBooks'], 0)
            lastupdated = author['DateAdded']
            name = makeUnicode(author['AuthorName'])
            entry = {
                    'title': escape('%s (%s/%s)' % (name, havebooks, totalbooks)),
                    'id': escape('author:%s' % author['AuthorID']),
                    'updated': opdstime(lastupdated),
                    'content': escape('%s (%s)' % (name, havebooks)),
                    'href': '%s?cmd=Author&amp;authorid=%s' % (self.opdsroot, author['AuthorID']),
                    'author': escape('%s' % name),
                    'kind': 'navigation',
                    'rel': 'subsection',
                }

            if lazylibrarian.CONFIG['OPDS_METAINFO']:
                entry['thumbnail'] = '/' + author['AuthorImg']
            entries.append(entry)

        if len(results) > (index + self.PAGE_SIZE):
            links.append(
                getLink(href='%s?cmd=Authors&amp;index=%s' % (self.opdsroot, index + self.PAGE_SIZE),
                        ftype='application/atom+xml; profile=opds-catalog; kind=navigation', rel='next'))
        if index >= self.PAGE_SIZE:
            links.append(
                getLink(href='%s?cmd=Authors&amp;index=%s' % (self.opdsroot, index - self.PAGE_SIZE),
                        ftype='application/atom+xml; profile=opds-catalog; kind=navigation', rel='previous'))

        feed['links'] = links
        feed['entries'] = entries
        logger.debug("Returning %s author%s" % (len(entries), plural(len(entries))))
        self.data = feed
        return

    def _Magazines(self, **kwargs):
        index = 0
        if 'index' in kwargs:
            index = check_int(kwargs['index'], 0)
        myDB = database.DBConnection()
        feed = {'title': 'LazyLibrarian OPDS - Magazines', 'id': 'Magazines', 'updated': now()}
        links = []
        entries = []
        links.append(getLink(href=self.opdsroot, ftype='application/atom+xml; profile=opds-catalog; kind=navigation',
                             rel='start', title='Home'))
        links.append(getLink(href='%s?cmd=Magazines' % self.opdsroot,
                             ftype='application/atom+xml; profile=opds-catalog; kind=navigation', rel='self'))
        links.append(getLink(href='%s/opensearchmagazines.xml' % self.searchroot,
                             ftype='application/opensearchdescription+xml', rel='search', title='Search Magazines'))
        cmd = 'select magazines.*,(select count(*) as counter from issues where magazines.title = issues.title)'
        cmd += ' as Iss_Cnt from magazines '
        if 'query' in kwargs:
            cmd += "WHERE magazines.title LIKE '%" + kwargs['query'] + "%' "
        cmd += 'order by magazines.title'
        results = myDB.select(cmd)
        page = results[index:(index + self.PAGE_SIZE)]
        for mag in page:
            if mag['Iss_Cnt'] > 0:
                title = makeUnicode(mag['Title'])
                entry = {
                    'title': escape('%s (%s)' % (title, mag['Iss_Cnt'])),
                    'id': escape('magazine:%s' % title),
                    'updated': opdstime(mag['LastAcquired']),
                    'content': escape('%s' % title),
                    'href': '%s?cmd=Magazine&amp;magid=%s' % (self.opdsroot, quote_plus(title)),
                    'kind': 'navigation',
                    'rel': 'subsection',
                }

                # if lazylibrarian.CONFIG['OPDS_METAINFO']:
                #     res = cache_img('magazine', md5_utf8(mag['LatestCover']), mag['LatestCover'], refresh=True)
                #     entry['thumbnail'] = '/' + res[0]
                entries.append(entry)

        if len(results) > (index + self.PAGE_SIZE):
            links.append(
                getLink(href='%s?cmd=Magazines&amp;index=%s' % (self.opdsroot, index + self.PAGE_SIZE),
                        ftype='application/atom+xml; profile=opds-catalog; kind=navigation', rel='next'))
        if index >= self.PAGE_SIZE:
            links.append(
                getLink(href='%s?cmd=Magazines&amp;index=%s' % (self.opdsroot, index - self.PAGE_SIZE),
                        ftype='application/atom+xml; profile=opds-catalog; kind=navigation', rel='previous'))

        feed['links'] = links
        feed['entries'] = entries
        logger.debug("Returning %s magazine%s" % (len(entries), plural(len(entries))))
        self.data = feed
        return

    def _Series(self, **kwargs):
        index = 0
        if 'index' in kwargs:
            index = check_int(kwargs['index'], 0)
        myDB = database.DBConnection()
        feed = {'title': 'LazyLibrarian OPDS - Series', 'id': 'Series', 'updated': now()}
        links = []
        entries = []
        links.append(getLink(href=self.opdsroot, ftype='application/atom+xml; profile=opds-catalog; kind=navigation',
                             rel='start', title='Home'))
        links.append(getLink(href='%s?cmd=Series' % self.opdsroot,
                             ftype='application/atom+xml; profile=opds-catalog; kind=navigation', rel='self'))
        links.append(getLink(href='%s/opensearchseries.xml' % self.searchroot,
                             ftype='application/opensearchdescription+xml', rel='search', title='Search Series'))
        cmd = "SELECT SeriesName,SeriesID,Have,Total from Series WHERE CAST(Have AS INTEGER) > 0 "
        if 'query' in kwargs:
            cmd += "AND SeriesName LIKE '%" + kwargs['query'] + "%' "
        cmd += "order by SeriesName"
        results = myDB.select(cmd)
        page = results[index:(index + self.PAGE_SIZE)]
        for series in page:
            cmd = "SELECT books.BookID,SeriesNum from books,member where SeriesID=? "
            cmd += "and books.bookid = member.bookid order by CAST(SeriesNum AS INTEGER)"
            firstbook = myDB.match(cmd, (series['SeriesID'],))
            if firstbook:
                cmd = 'SELECT AuthorName from authors,books WHERE authors.authorid = books.authorid AND books.bookid=?'
                res = myDB.match(cmd, (firstbook['BookID'],))
                author = res['AuthorName']
            else:
                author = 'Unknown'
            totalbooks = check_int(series['Total'], 0)
            havebooks = check_int(series['Have'], 0)
            sername = makeUnicode(series['SeriesName'])
            entries.append(
                {
                    'title': escape('%s (%s/%s) %s' % (sername, havebooks, totalbooks, author)),
                    'id': escape('series:%s' % series['SeriesID']),
                    'updated': now(),
                    'content': escape('%s (%s)' % (sername, havebooks)),
                    'href': '%s?cmd=Members&amp;seriesid=%s' % (self.opdsroot, series['SeriesID']),
                    'kind': 'navigation',
                    'rel': 'subsection',
                }
            )
        if len(results) > (index + self.PAGE_SIZE):
            links.append(
                getLink(href='%s?cmd=Series&amp;index=%s' % (self.opdsroot, index + self.PAGE_SIZE),
                        ftype='application/atom+xml; profile=opds-catalog; kind=navigation', rel='next'))
        if index >= self.PAGE_SIZE:
            links.append(
                getLink(href='%s?cmd=Series&amp;index=%s' % (self.opdsroot, index - self.PAGE_SIZE),
                        ftype='application/atom+xml; profile=opds-catalog; kind=navigation', rel='previous'))

        feed['links'] = links
        feed['entries'] = entries
        logger.debug("Returning %s series" % len(entries))
        self.data = feed
        return

    def _Magazine(self, **kwargs):
        index = 0
        if 'index' in kwargs:
            index = check_int(kwargs['index'], 0)
        myDB = database.DBConnection()
        if 'magid' not in kwargs:
            self.data = self._error_with_message('No Magazine Provided')
            return
        links = []
        entries = []
        title = ''
        cmd = "SELECT Title,IssueID,IssueDate,IssueAcquired,IssueFile from issues "
        cmd += "WHERE Title='%s' order by IssueDate DESC"
        results = myDB.select(cmd % kwargs['magid'])
        page = results[index:(index + self.PAGE_SIZE)]
        for issue in page:
            title = makeUnicode(issue['Title'])
            entry = {'title': escape('%s (%s)' % (title, issue['IssueDate'])),
                     'id': escape('issue:%s' % issue['IssueID']),
                     'updated': opdstime(issue['IssueAcquired']),
                     'content': escape('%s - %s' % (title, issue['IssueDate'])),
                     'href': '%s?cmd=Serve&amp;issueid=%s' % (self.opdsroot, quote_plus(issue['IssueID'])),
                     'kind': 'acquisition',
                     'rel': 'file',
                     'type': mimeType(issue['IssueFile'])}
            if lazylibrarian.CONFIG['OPDS_METAINFO']:
                fname = os.path.splitext(issue['IssueFile'])[0]
                res = cache_img('magazine', issue['IssueID'], fname + '.jpg')
                entry['image'] = self.searchroot + '/' + res[0]
                entry['thumbnail'] = entry['image']
            entries.append(entry)

        feed = {}
        title = '%s (%s)' % (escape(title), len(entries))
        feed['title'] = 'LazyLibrarian OPDS - %s' % title
        feed['id'] = 'magazine:%s' % escape(kwargs['magid'])
        feed['updated'] = now()
        links.append(getLink(href=self.opdsroot, ftype='application/atom+xml; profile=opds-catalog; kind=navigation',
                             rel='start', title='Home'))
        links.append(getLink(href='%s?cmd=Magazine&amp;magid=%s' % (self.opdsroot, quote_plus(kwargs['magid'])),
                             ftype='application/atom+xml; profile=opds-catalog; kind=navigation', rel='self'))
        if len(results) > (index + self.PAGE_SIZE):
            links.append(
                getLink(href='%s?cmd=Magazine&amp;magid=%s&amp;index=%s' % (self.opdsroot, quote_plus(kwargs['magid']),
                                                                            index + self.PAGE_SIZE),
                        ftype='application/atom+xml; profile=opds-catalog; kind=navigation', rel='next'))
        if index >= self.PAGE_SIZE:
            links.append(
                getLink(href='%s?cmd=Magazine&amp;magid=%s&amp;index=%s' % (self.opdsroot, quote_plus(kwargs['magid']),
                                                                            index - self.PAGE_SIZE),
                        ftype='application/atom+xml; profile=opds-catalog; kind=navigation', rel='previous'))

        feed['links'] = links
        feed['entries'] = entries
        logger.debug("Returning %s issue%s" % (len(entries), plural(len(entries))))
        self.data = feed
        return

    def _Author(self, **kwargs):
        index = 0
        if 'index' in kwargs:
            index = check_int(kwargs['index'], 0)
        myDB = database.DBConnection()
        if 'authorid' not in kwargs:
            self.data = self._error_with_message('No Author Provided')
            return
        links = []
        entries = []
        links.append(getLink(href='%s/opensearchbooks.xml' % self.searchroot,
                             ftype='application/opensearchdescription+xml', rel='search', title='Search Books'))
        author = myDB.match("SELECT AuthorName from authors WHERE AuthorID=?", (kwargs['authorid'],))
        author = makeUnicode(author['AuthorName'])
        cmd = "SELECT BookName,BookDate,BookID,BookAdded,BookDesc,BookImg,BookFile,AudioFile from books WHERE "
        if 'query' in kwargs:
            cmd += "BookName LIKE '%" + kwargs['query'] + "%' AND "
        cmd += "(Status='Open' or AudioStatus='Open') and AuthorID=? order by BookDate DESC"
        results = myDB.select(cmd, (kwargs['authorid'],))
        page = results[index:(index + self.PAGE_SIZE)]

        for book in page:
            mime_type = None
            rel = 'file'
            if book['BookFile']:
                mime_type = self.multiLink(book['BookFile'], book['BookID'])
                if mime_type:
                    rel = 'multi'
                else:
                    mime_type = mimeType(book['BookFile'])

            elif book['AudioFile']:
                mime_type = mimeType(book['AudioFile'])

            if mime_type:
                entry = {'title': escape('%s (%s)' % (book['BookName'], book['BookDate'])),
                         'id': escape('book:%s' % book['BookID']),
                         'updated': opdstime(book['BookAdded']),
                         'href': '%s?cmd=Serve&amp;bookid=%s' % (self.opdsroot, book['BookID']),
                         'kind': 'acquisition',
                         'rel': rel,
                         'type': mime_type}
                if lazylibrarian.CONFIG['OPDS_METAINFO']:
                    entry['image'] = self.searchroot + '/' + book['BookImg']
                    entry['thumbnail'] = entry['image']
                    entry['content'] = escape('%s - %s' % (book['BookName'], book['BookDesc']))
                    entry['author'] = escape('%s' % author)
                else:
                    entry['content'] = escape('%s (%s)' % (book['BookName'], book['BookAdded']))
                entries.append(entry)

        feed = {}
        authorname = '%s (%s)' % (escape(author), len(entries))
        feed['title'] = 'LazyLibrarian OPDS - %s' % authorname
        feed['id'] = 'author:%s' % escape(kwargs['authorid'])
        feed['updated'] = now()
        links.append(getLink(href=self.opdsroot, ftype='application/atom+xml; profile=opds-catalog; kind=navigation',
                             rel='start', title='Home'))
        links.append(getLink(href='%s?cmd=Authors' % self.opdsroot,
                             ftype='application/atom+xml; profile=opds-catalog; kind=navigation', rel='self'))
        if len(results) > (index + self.PAGE_SIZE):
            links.append(
                getLink(href='%s?cmd=Author&amp;authorid=%s&amp;index=%s' % (self.opdsroot,
                                                                             quote_plus(kwargs['authorid']),
                                                                             index + self.PAGE_SIZE),
                        ftype='application/atom+xml; profile=opds-catalog; kind=navigation', rel='next'))
        if index >= self.PAGE_SIZE:
            links.append(
                getLink(href='%s?cmd=Author&amp;authorid=%s&amp;index=%s' % (self.opdsroot,
                                                                             quote_plus(kwargs['authorid']),
                                                                             index - self.PAGE_SIZE),
                        ftype='application/atom+xml; profile=opds-catalog; kind=navigation', rel='previous'))
        feed['links'] = links
        feed['entries'] = entries
        self.data = feed
        logger.debug("Returning %s book%s" % (len(entries), plural(len(entries))))
        return

    def _Members(self, **kwargs):
        index = 0
        if 'index' in kwargs:
            index = check_int(kwargs['index'], 0)
        myDB = database.DBConnection()
        if 'seriesid' not in kwargs:
            self.data = self._error_with_message('No Series Provided')
            return
        links = []
        entries = []
        series = myDB.match("SELECT SeriesName from Series WHERE SeriesID=?", (kwargs['seriesid'],))
        cmd = "SELECT BookName,BookDate,BookAdded,BookDesc,BookImg,BookFile,AudioFile,books.BookID,SeriesNum "
        cmd += "from books,member where (Status='Open' or AudioStatus='Open') and SeriesID=? "
        cmd += "and books.bookid = member.bookid order by CAST(SeriesNum AS INTEGER)"
        results = myDB.select(cmd, (kwargs['seriesid'],))
        cmd = 'SELECT AuthorName from authors,books WHERE authors.authorid = books.authorid AND '
        cmd += 'books.bookid=?'
        res = myDB.match(cmd, (results[0]['BookID'],))
        author = res['AuthorName']
        page = results[index:(index + self.PAGE_SIZE)]
        for book in page:
            mime_type = None
            rel = 'file'
            if book['BookFile']:
                mime_type = self.multiLink(book['BookFile'], book['BookID'])
                if mime_type:
                    rel = 'multi'
                else:
                    mime_type = mimeType(book['BookFile'])

            elif book['AudioFile']:
                mime_type = mimeType(book['AudioFile'])
            if mime_type:
                if book['SeriesNum']:
                    snum = ' (%s)' % book['SeriesNum']
                else:
                    snum = ''
                entry = {'title': escape('%s%s' % (book['BookName'], snum)),
                         'id': escape('book:%s' % book['BookID']),
                         'updated': opdstime(book['BookAdded']),
                         'href': '%s?cmd=Serve&amp;bookid=%s' % (self.opdsroot, book['BookID']),
                         'kind': 'acquisition',
                         'rel': rel,
                         'author': escape("%s" % author),
                         'type': mime_type}

                if lazylibrarian.CONFIG['OPDS_METAINFO']:
                    entry['image'] = self.searchroot + '/' + book['BookImg']
                    entry['thumbnail'] = entry['image']
                    entry['content'] = escape('%s (%s %s) %s' % (book['BookName'], series['SeriesName'],
                                                                 book['SeriesNum'], book['BookDesc']))
                else:
                    entry['content'] = escape('%s (%s %s) %s' % (book['BookName'], series['SeriesName'],
                                                                 book['SeriesNum'], book['BookAdded']))
                entries.append(entry)

        feed = {}
        seriesname = '%s (%s) %s' % (escape(series['SeriesName']), len(entries), author)
        feed['title'] = 'LazyLibrarian OPDS - %s' % seriesname
        feed['id'] = 'series:%s' % escape(kwargs['seriesid'])
        feed['updated'] = now()
        links.append(getLink(href=self.opdsroot, ftype='application/atom+xml; profile=opds-catalog; kind=navigation',
                             rel='start', title='Home'))
        links.append(getLink(href='%s?cmd=Series' % self.opdsroot,
                             ftype='application/atom+xml; profile=opds-catalog; kind=navigation', rel='self'))
        if len(results) > (index + self.PAGE_SIZE):
            links.append(
                getLink(href='%s?cmd=Members&amp;seriesid=%s&amp;index=%s' % (self.opdsroot, kwargs['seriesid'],
                                                                              index + self.PAGE_SIZE),
                        ftype='application/atom+xml; profile=opds-catalog; kind=navigation', rel='next'))
        if index >= self.PAGE_SIZE:
            links.append(
                getLink(href='%s?cmd=Members&amp;seriesid=%s&amp;index=%s' % (self.opdsroot, kwargs['seriesid'],
                                                                              index - self.PAGE_SIZE),
                        ftype='application/atom+xml; profile=opds-catalog; kind=navigation', rel='previous'))

        feed['links'] = links
        feed['entries'] = entries
        logger.debug("Returning %s book%s" % (len(entries), plural(len(entries))))
        self.data = feed
        return

    def _RecentMags(self, **kwargs):
        index = 0
        if 'index' in kwargs:
            index = check_int(kwargs['index'], 0)
        myDB = database.DBConnection()
        feed = {'title': 'LazyLibrarian OPDS - Recent Magazines', 'id': 'Recent Magazines', 'updated': now()}
        links = []
        entries = []
        links.append(getLink(href=self.opdsroot, ftype='application/atom+xml; profile=opds-catalog; kind=navigation',
                             rel='start', title='Home'))
        links.append(getLink(href='%s?cmd=RecentMags' % self.opdsroot,
                             ftype='application/atom+xml; profile=opds-catalog; kind=navigation', rel='self'))
        links.append(getLink(href='%s/opensearchmagazines.xml' % self.searchroot,
                             ftype='application/opensearchdescription+xml', rel='search', title='Search Magazines'))
        cmd = "select Title,IssueID,IssueAcquired,IssueDate,IssueFile from issues "
        cmd += "where IssueFile != '' "
        if 'query' in kwargs:
            cmd += "AND Title LIKE '%" + kwargs['query'] + "%' "
        cmd += "order by IssueAcquired DESC"
        results = myDB.select(cmd)
        page = results[index:(index + self.PAGE_SIZE)]
        for mag in page:
            title = makeUnicode(mag['Title'])
            entry = {'title': escape('%s' % mag['IssueDate']),
                     'id': escape('issue:%s' % mag['IssueID']),
                     'updated': opdstime(mag['IssueAcquired']),
                     'content': escape('%s - %s' % (title, mag['IssueDate'])),
                     'href': '%s?cmd=Serve&amp;issueid=%s' % (self.opdsroot, quote_plus(mag['IssueID'])),
                     'kind': 'acquisition',
                     'rel': 'file',
                     'author': escape(title),
                     'type': mimeType(mag['IssueFile'])}
            if lazylibrarian.CONFIG['OPDS_METAINFO']:
                fname = os.path.splitext(mag['IssueFile'])[0]
                res = cache_img('magazine', mag['IssueID'], fname + '.jpg')
                entry['image'] = self.searchroot + '/' + res[0]
                entry['thumbnail'] = entry['image']
            entries.append(entry)

        if len(results) > (index + self.PAGE_SIZE):
            links.append(
                getLink(href='%s?cmd=RecentMags&amp;index=%s' % (self.opdsroot, index + self.PAGE_SIZE),
                        ftype='application/atom+xml; profile=opds-catalog; kind=navigation', rel='next'))
        if index >= self.PAGE_SIZE:
            links.append(
                getLink(href='%s?cmd=RecentMags&amp;index=%s' % (self.opdsroot, index - self.PAGE_SIZE),
                        ftype='application/atom+xml; profile=opds-catalog; kind=navigation', rel='previous'))

        feed['links'] = links
        feed['entries'] = entries
        logger.debug("Returning %s issue%s" % (len(entries), plural(len(entries))))
        self.data = feed
        return

    def _RecentBooks(self, **kwargs):
        index = 0
        if 'index' in kwargs:
            index = check_int(kwargs['index'], 0)
        myDB = database.DBConnection()
        feed = {'title': 'LazyLibrarian OPDS - Recent Books', 'id': 'Recent Books', 'updated': now()}
        links = []
        entries = []
        links.append(getLink(href=self.opdsroot, ftype='application/atom+xml; profile=opds-catalog; kind=navigation',
                             rel='start', title='Home'))
        links.append(getLink(href='%s?cmd=RecentBooks' % self.opdsroot,
                             ftype='application/atom+xml; profile=opds-catalog; kind=navigation', rel='self'))
        links.append(getLink(href='%s/opensearchbooks.xml' % self.searchroot,
                             ftype='application/opensearchdescription+xml', rel='search', title='Search Books'))
        cmd = "select BookName,BookID,BookLibrary,BookDate,BookImg,BookDesc,BookAdded,BookFile,AuthorID "
        cmd += "from books where Status='Open' "
        if 'query' in kwargs:
            cmd += "AND BookName LIKE '%" + kwargs['query'] + "%' "
        cmd += "order by BookLibrary DESC"
        results = myDB.select(cmd)
        page = results[index:(index + self.PAGE_SIZE)]
        for book in page:
            mime_type = None
            rel = 'file'
            if book['BookFile']:
                mime_type = self.multiLink(book['BookFile'], book['BookID'])
                if mime_type:
                    rel = 'multi'
                else:
                    mime_type = mimeType(book['BookFile'])

            elif book['AudioFile']:
                mime_type = mimeType(book['AudioFile'])
            if mime_type:
                title = makeUnicode(book['BookName'])
                entry = {'title': escape(title),
                         'id': escape('book:%s' % book['BookID']),
                         'updated': opdstime(book['BookLibrary']),
                         'href': '%s?cmd=Serve&amp;bookid=%s' % (self.opdsroot, quote_plus(book['BookID'])),
                         'kind': 'acquisition',
                         'rel': rel,
                         'type': mime_type}

                if lazylibrarian.CONFIG['OPDS_METAINFO']:
                    author = myDB.match("SELECT AuthorName from authors WHERE AuthorID=?", (book['AuthorID'],))
                    author = makeUnicode(author['AuthorName'])
                    entry['image'] = self.searchroot + '/' + book['BookImg']
                    entry['thumbnail'] = entry['image']
                    entry['content'] = escape('%s - %s' % (title, book['BookDesc']))
                    entry['author'] = escape('%s' % author)
                else:
                    entry['content'] = escape('%s (%s)' % (title, book['BookAdded']))
                entries.append(entry)

            """
                <link type="application/epub+zip" rel="http://opds-spec.org/acquisition"
                title="EPUB (no images)" length="18552" href="//www.gutenberg.org/ebooks/57490.epub.noimages"/>
                <link type="application/x-mobipocket-ebook" rel="http://opds-spec.org/acquisition"
                title="Kindle (no images)" length="110360" href="//www.gutenberg.org/ebooks/57490.kindle.noimages"/>
            """

        if len(results) > (index + self.PAGE_SIZE):
            links.append(
                getLink(href='%s?cmd=RecentBooks&amp;index=%s' % (self.opdsroot, index + self.PAGE_SIZE),
                        ftype='application/atom+xml; profile=opds-catalog; kind=navigation', rel='next'))
        if index >= self.PAGE_SIZE:
            links.append(
                getLink(href='%s?cmd=RecentBooks&amp;index=%s' % (self.opdsroot, index - self.PAGE_SIZE),
                        ftype='application/atom+xml; profile=opds-catalog; kind=navigation', rel='previous'))

        feed['links'] = links
        feed['entries'] = entries
        logger.debug("Returning %s book%s" % (len(entries), plural(len(entries))))
        self.data = feed
        return

    def _RecentAudio(self, **kwargs):
        index = 0
        if 'index' in kwargs:
            index = check_int(kwargs['index'], 0)
        myDB = database.DBConnection()
        feed = {'title': 'LazyLibrarian OPDS - Recent AudioBooks', 'id': 'Recent AudioBooks', 'updated': now()}
        links = []
        entries = []
        links.append(getLink(href=self.opdsroot, ftype='application/atom+xml; profile=opds-catalog; kind=navigation',
                             rel='start', title='Home'))
        links.append(getLink(href='%s?cmd=RecentAudio' % self.opdsroot,
                             ftype='application/atom+xml; profile=opds-catalog; kind=navigation', rel='self'))
        links.append(getLink(href='%s/opensearchbooks.xml' % self.searchroot,
                             ftype='application/opensearchdescription+xml', rel='search', title='Search Books'))

        cmd = "select BookName,BookID,AudioLibrary,BookDate,BookImg,BookDesc,BookAdded,AuthorID from books WHERE "
        if 'query' in kwargs:
            cmd += "BookName LIKE '%" + kwargs['query'] + "%' AND "
        cmd += "AudioStatus='Open' order by AudioLibrary DESC"
        results = myDB.select(cmd)
        page = results[index:(index + self.PAGE_SIZE)]
        for book in page:
            title = makeUnicode(book['BookName'])
            entry = {'title': escape(title),
                     'id': escape('audio:%s' % book['BookID']),
                     'updated': opdstime(book['AudioLibrary']),
                     'href': '%s?cmd=Serve&amp;audioid=%s' % (self.opdsroot, quote_plus(book['BookID'])),
                     'kind': 'acquisition',
                     'rel': 'file',
                     'type': mimeType("we_send.zip")}
            if lazylibrarian.CONFIG['OPDS_METAINFO']:
                author = myDB.match("SELECT AuthorName from authors WHERE AuthorID=?", (book['AuthorID'],))
                author = makeUnicode(author['AuthorName'])
                entry['image'] = self.searchroot + '/' + book['BookImg']
                entry['thumbnail'] = entry['image']
                entry['content'] = escape('%s - %s' % (title, book['BookDesc']))
                entry['author'] = escape('%s' % author)
            else:
                entry['content'] = escape('%s (%s)' % (title, book['BookAdded']))
            entries.append(entry)

        if len(results) > (index + self.PAGE_SIZE):
            links.append(
                getLink(href='%s?cmd=RecentAudio&amp;index=%s' % (self.opdsroot, index + self.PAGE_SIZE),
                        ftype='application/atom+xml; profile=opds-catalog; kind=navigation', rel='next'))
        if index >= self.PAGE_SIZE:
            links.append(
                getLink(href='%s?cmd=RecentAudio&amp;index=%s' % (self.opdsroot, index - self.PAGE_SIZE),
                        ftype='application/atom+xml; profile=opds-catalog; kind=navigation', rel='previous'))

        feed['links'] = links
        feed['entries'] = entries
        logger.debug("Returning %s result%s" % (len(entries), plural(len(entries))))
        self.data = feed
        return

    def _Serve(self, **kwargs):
        if 'bookid' in kwargs:
            if 'fmt' in kwargs:
                fmt = kwargs['fmt']
            else:
                fmt = ''
            myid = kwargs['bookid']
            myDB = database.DBConnection()
            res = myDB.match('SELECT BookFile,BookName from books where bookid=?', (myid,))
            bookfile = res['BookFile']
            if fmt:
                bookfile = os.path.splitext(bookfile)[0] + '.' + fmt
            self.file = bookfile
            self.filename = os.path.split(bookfile)[1]
            return
        elif 'issueid' in kwargs:
            myid = kwargs['issueid']
            myDB = database.DBConnection()
            res = myDB.match('SELECT IssueFile from issues where issueid=?', (myid,))
            self.file = res['IssueFile']
            self.filename = os.path.split(res['IssueFile'])[1]
            return
        elif 'audioid' in kwargs:
            myid = kwargs['audioid']
            myDB = database.DBConnection()
            res = myDB.match('SELECT AudioFile,BookName from books where BookID=?', (myid,))
            basefile = res['AudioFile']
            # zip up all the audiobook parts
            if basefile and os.path.isfile(basefile):
                target = zipAudio(os.path.dirname(basefile), res['BookName'])
                self.file = target
                self.filename = res['BookName'] + '.zip'
            return


def getLink(href=None, ftype=None, rel=None, title=None):
    link = {}
    if href:
        link['href'] = href
    if ftype:
        link['type'] = ftype
    if rel:
        link['rel'] = rel
    if title:
        link['title'] = title
    return link


def escape(data):
    """Escape &, <, and > in a string of data.
    """
    # must do ampersand first
    data = data.replace("&", "&amp;")
    data = data.replace(">", "&gt;")
    data = data.replace("<", "&lt;")
    return data


def now():
    dtnow = datetime.datetime.now()
    return dtnow.strftime("%Y-%m-%dT%H:%M:%SZ")


def opdstime(datestr):
    # YYYY-MM-DDTHH:MM:SSZ
    if not datestr:
        return now()
    if len(datestr) == 10:
        return "%s%s" % (datestr, 'T00:00:00Z')
    elif len(datestr) == 19:
        return "%sT%sZ" % (datestr[:10], datestr[11:])
    return now()
