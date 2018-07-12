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
# Adapted for LazyLibrarian from Mylar

import lazylibrarian
from lazylibrarian import logger, database
import cherrypy
from xml.sax.saxutils import escape
import os
import tempfile
from urllib import quote_plus
from cherrypy.lib.static import serve_file, serve_download
from lazylibrarian.formatter import now, makeUnicode, md5_utf8
from lazylibrarian.cache import cache_img
from lib.six.moves.urllib_parse import quote_plus
from lib.six import PY2

try:
    import zipfile
except ImportError:
    if PY2:
        import lib.zipfile as zipfile
    else:
        import lib3.zipfile as zipfile

cmd_list = ['root', 'Authors', 'Magazines', 'Magazine', 'Author', 'RecentBooks', 'RecentAudio', 'RecentMags',
            'Audio', 'Book', 'Issue']


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
            logger.debug('Received OPDS command: ' + self.cmd)
            methodToCall = getattr(self, "_" + self.cmd)
            _ = methodToCall(**self.kwargs)
            if self.img:
                return serve_file(path=self.img, content_type='image/jpeg')
            if self.file and self.filename:
                return serve_download(path=self.file, name=self.filename)
            if isinstance(self.data, basestring):
                return self.data
            else:
                cherrypy.response.headers['Content-Type'] = "text/xml"
                return lazylibrarian.webServe.serve_template(templatename="opds.html",
                                                             title=self.data['title'], opds=self.data)
        else:
            return self.data

    @staticmethod
    def _error_with_message(message):
        error = '<feed><error>%s</error></feed>' % message
        cherrypy.response.headers['Content-Type'] = "text/xml"
        return error

    @staticmethod
    def _dic_from_query(query):
        myDB = database.DBConnection()
        rows = myDB.select(query)

        rows_as_dic = []

        for row in rows:
            row_as_dic = dict(zip(row.keys(), row))
            rows_as_dic.append(row_as_dic)

        return rows_as_dic

    def _root(self, **kwargs):
        myDB = database.DBConnection()
        feed = {'title': 'LazyLibrarian OPDS', 'id': 'OPDSRoot', 'updated': now()}
        links = []
        entries = []
        links.append(getLink(href=self.opdsroot, type='application/atom+xml; profile=opds-catalog; kind=navigation',
                             rel='start', title='Home'))
        links.append(getLink(href=self.opdsroot, type='application/atom+xml; profile=opds-catalog; kind=navigation',
                             rel='self'))
        links.append(
            getLink(href='%s?cmd=search' % self.opdsroot, type='application/opensearchdescription+xml', rel='search',
                    title='Search'))
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
        authors = myDB.select("SELECT authorname from authors order by authorname")
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
        magazines = myDB.select("SELECT title from magazines order by title")
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
        self.data = feed
        return

    def _Authors(self, **kwargs):
        index = 0
        if 'index' in kwargs:
            index = int(kwargs['index'])
        myDB = database.DBConnection()
        feed = {}
        feed['title'] = 'LazyLibrarian OPDS - Authors'
        feed['id'] = 'Authors'
        feed['updated'] = now()
        links = []
        entries = []
        links.append(getLink(href=self.opdsroot, type='application/atom+xml; profile=opds-catalog; kind=navigation',
                             rel='start', title='Home'))
        links.append(getLink(href='%s?cmd=Authors' % self.opdsroot,
                             type='application/atom+xml; profile=opds-catalog; kind=navigation', rel='self'))
        cmd = "SELECT AuthorName,AuthorID,HaveBooks,TotalBooks,DateAdded from Authors order by AuthorName"
        authors = myDB.select(cmd)
        for author in authors:
            totalbooks = author['TotalBooks']
            havebooks = author['HaveBooks']
            lastupdated = author['DateAdded']
            name = makeUnicode(author['AuthorName'])
            if havebooks > 0:
                entries.append(
                    {
                        'title': escape('%s (%s/%s)' % (name, havebooks, totalbooks)),
                        'id': escape('author:%s' % author['AuthorID']),
                        'updated': lastupdated,
                        'content': escape('%s (%s)' % (name, havebooks)),
                        'href': '%s?cmd=Author&amp;authorid=%s' % (self.opdsroot, author['AuthorID']),
                        'kind': 'navigation',
                        'rel': 'subsection',
                    }
                )
        if len(entries) > (index + self.PAGE_SIZE):
            links.append(
                getLink(href='%s?cmd=Authors&amp;index=%s' % (self.opdsroot, index + self.PAGE_SIZE),
                        type='application/atom+xml; profile=opds-catalog; kind=navigation', rel='next'))
        if index >= self.PAGE_SIZE:
            links.append(
                getLink(href='%s?cmd=Authors&amp;index=%s' % (self.opdsroot, index - self.PAGE_SIZE),
                        type='application/atom+xml; profile=opds-catalog; kind=navigation', rel='previous'))

        feed['links'] = links
        feed['entries'] = entries[index:(index + self.PAGE_SIZE)]
        self.data = feed
        return

    def _Magazines(self, **kwargs):
        index = 0
        if 'index' in kwargs:
            index = int(kwargs['index'])
        myDB = database.DBConnection()
        feed = {'title': 'LazyLibrarian OPDS - Magazines', 'id': 'Magazines', 'updated': now()}
        links = []
        entries = []
        links.append(getLink(href=self.opdsroot, type='application/atom+xml; profile=opds-catalog; kind=navigation',
                             rel='start', title='Home'))
        links.append(getLink(href='%s?cmd=Magazines' % self.opdsroot,
                             type='application/atom+xml; profile=opds-catalog; kind=navigation', rel='self'))

        cmd = 'select magazines.*,(select count(*) as counter from issues where magazines.title = issues.title)'
        cmd += ' as Iss_Cnt from magazines order by magazines.title'
        mags = myDB.select(cmd)
        for mag in mags:
            if mag['Iss_Cnt'] > 0:
                title = makeUnicode(mag['Title'])
                entry = {
                    'title': escape('%s (%s)' % (title, mag['Iss_Cnt'])),
                    'id': escape('magazine:%s' % title),
                    'updated': mag['LastAcquired'],
                    'content': escape('%s (%s)' % (title, mag['Iss_Cnt'])),
                    'href': '%s?cmd=Magazine&amp;magid=%s' % (self.opdsroot, quote_plus(title)),
                    'kind': 'acquisition',
                    'rel': 'subsection',
                }
                if lazylibrarian.CONFIG['OPDS_METAINFO']:
                    res = cache_img('magazine', md5_utf8(mag['LatestCover']), mag['LatestCover'], refresh=True)
                    entry['image'] = res[0]
                entries.append(entry)

        if len(entries) > (index + self.PAGE_SIZE):
            links.append(
                getLink(href='%s?cmd=Magazines&amp;index=%s' % (self.opdsroot, index + self.PAGE_SIZE),
                        type='application/atom+xml; profile=opds-catalog; kind=navigation', rel='next'))
        if index >= self.PAGE_SIZE:
            links.append(
                getLink(href='%s?cmd=Magazines&amp;index=%s' % (self.opdsroot, index - self.PAGE_SIZE),
                        type='application/atom+xml; profile=opds-catalog; kind=navigation', rel='previous'))

        feed['links'] = links
        feed['entries'] = entries[index:(index + self.PAGE_SIZE)]
        self.data = feed
        return

    def _Magazine(self, **kwargs):
        index = 0
        if 'index' in kwargs:
            index = int(kwargs['index'])
        myDB = database.DBConnection()
        if 'magid' not in kwargs:
            self.data = self._error_with_message('No Magazine Provided')
            return
        links = []
        entries = []
        title = ''
        cmd = "SELECT Title,IssueID,IssueDate,IssueAcquired,IssueFile from issues "
        cmd += "WHERE Title='%s' order by IssueDate DESC"
        issues = myDB.select(cmd % kwargs['magid'])
        for issue in issues:
            title = makeUnicode(issue['Title'])
            entry = {
                'title': escape('%s (%s)' % (title, issue['IssueDate'])),
                'id': escape('issue:%s' % issue['IssueID']),
                'updated': issue['IssueAcquired'],
                'content': escape('%s (%s)' % (title, issue['IssueDate'])),
                'href': '%s?cmd=Serve&amp;issueid=%s' % (self.opdsroot, quote_plus(issue['IssueID'])),
                'kind': 'acquisition',
                'rel': 'subsection',
            }
            if lazylibrarian.CONFIG['OPDS_METAINFO']:
                fname = os.path.splitext(issue['IssueFile'])[0]
                res = cache_img('magazine', issue['IssueID'], fname + '.jpg')
                entry['image'] = res[0]
            entries.append(entry)

        feed = {}
        title = '%s (%s)' % (escape(title), len(entries))
        feed['title'] = 'LazyLibrarian OPDS - %s' % title
        feed['id'] = 'magazine:%s' % escape(kwargs['magid'])
        feed['updated'] = now()
        links.append(getLink(href=self.opdsroot, type='application/atom+xml; profile=opds-catalog; kind=navigation',
                             rel='start', title='Home'))
        links.append(getLink(href='%s?cmd=Magazines' % self.opdsroot,
                             type='application/atom+xml; profile=opds-catalog; kind=navigation', rel='self'))
        if len(entries) > (index + self.PAGE_SIZE):
            links.append(
                getLink(href='%s?cmd=Magazine&amp;magid=%s&amp;index=%s' % (self.opdsroot, quote_plus(kwargs['magid']),
                                                                            index + self.PAGE_SIZE),
                        type='application/atom+xml; profile=opds-catalog; kind=navigation',
                        rel='next'))
        if index >= self.PAGE_SIZE:
            links.append(
                getLink(href='%s?cmd=Magazine&amp;magid=%s&amp;index=%s' % (self.opdsroot, quote_plus(kwargs['magid']),
                                                                            index - self.PAGE_SIZE),
                        type='application/atom+xml; profile=opds-catalog; kind=navigation',
                        rel='previous'))

        feed['links'] = links
        feed['entries'] = entries[index:(index + self.PAGE_SIZE)]
        self.data = feed
        return

    def _Author(self, **kwargs):
        index = 0
        if 'index' in kwargs:
            index = int(kwargs['index'])
        myDB = database.DBConnection()
        if 'authorid' not in kwargs:
            self.data = self._error_with_message('No Author Provided')
            return
        links = []
        entries = []
        cmd = "SELECT AuthorName,AuthorBorn,AuthorDeath from authors WHERE AuthorID='%s'"
        author = myDB.match(cmd % kwargs['authorid'])
        born = author['AuthorBorn']
        died = author['AuthorDeath']
        author = makeUnicode(author['AuthorName'])
        cmd = "SELECT BookName,BookDate,BookID,BookAdded,BookDesc,BookImg from books "
        cmd += "where (Status='Open' or AudioStatus='Open') and AuthorID=? order by BookDate DESC"
        books = myDB.select(cmd, (kwargs['authorid'],))
        for book in books:
            entry = {
                'title': escape('%s (%s)' % (book['BookName'], book['BookDate'])),
                'id': escape('book:%s' % book['BookID']),
                'updated': book['BookAdded'],
                'href': '%s?cmd=Serve&amp;bookid=%s' % (self.opdsroot, book['BookID']),
                'kind': 'acquisition',
                'rel': 'subsection',
            }

            if lazylibrarian.CONFIG['OPDS_METAINFO']:
                entry['image'] = book['BookImg']
                entry['content'] = escape('%s - %s' % (book['BookName'], book['BookDesc']))
                if born or died:
                    entry['author'] = escape('%s (%s-%s)' % (author, born, died))
                else:
                    entry['author'] = escape('%s' % author)
            else:
                entry['content'] = escape('%s (%s)' % (book['BookName'], book['BookAdded']))
            entries.append(entry)

        feed = {}
        authorname = '%s (%s)' % (escape(author), len(entries))
        feed['title'] = 'LazyLibrarian OPDS - %s' % authorname
        feed['id'] = 'author:%s' % escape(kwargs['authorid'])
        feed['updated'] = now()
        links.append(getLink(href=self.opdsroot, type='application/atom+xml; profile=opds-catalog; kind=navigation',
                             rel='start', title='Home'))
        links.append(getLink(href='%s?cmd=Authors' % self.opdsroot,
                             type='application/atom+xml; profile=opds-catalog; kind=navigation', rel='self'))
        if len(entries) > (index + self.PAGE_SIZE):
            links.append(
                getLink(href='%s?cmd=Author&amp;authorid=%s&amp;index=%s' % (self.opdsroot,
                                                                             quote_plus(kwargs['authorid']),
                                                                             index + self.PAGE_SIZE),
                        type='application/atom+xml; profile=opds-catalog; kind=navigation', rel='next'))
        if index >= self.PAGE_SIZE:
            links.append(
                getLink(href='%s?cmd=Author&amp;pubid=%s&amp;index=%s' % (self.opdsroot,
                                                                          quote_plus(kwargs['authorid']),
                                                                          index - self.PAGE_SIZE),
                        type='application/atom+xml; profile=opds-catalog; kind=navigation', rel='previous'))

        feed['links'] = links
        feed['entries'] = entries[index:(index + self.PAGE_SIZE)]
        self.data = feed
        return

    def _RecentMags(self, **kwargs):
        index = 0
        if 'index' in kwargs:
            index = int(kwargs['index'])
        myDB = database.DBConnection()
        feed = {}
        feed['title'] = 'LazyLibrarian OPDS - Recent Magazines'
        feed['id'] = 'Recent Magazines'
        feed['updated'] = now()
        links = []
        entries = []
        links.append(getLink(href=self.opdsroot, type='application/atom+xml; profile=opds-catalog; kind=navigation',
                             rel='start', title='Home'))
        links.append(getLink(href='%s?cmd=RecentMags' % self.opdsroot,
                             type='application/atom+xml; profile=opds-catalog; kind=navigation', rel='self'))

        cmd = "select Title,IssueID,IssueAcquired,IssueDate,IssueFile from issues "
        cmd += "where IssueFile != '' order by IssueAcquired DESC"
        mags = myDB.select(cmd)
        for mag in mags:
            title = makeUnicode(mag['Title'])
            entry = {
                'title': escape('%s' % mag['IssueDate']),
                'id': escape('issue:%s' % mag['IssueID']),
                'updated': mag['IssueAcquired'],
                'content': escape('%s (%s)' % (title, mag['IssueDate'])),
                'href': '%s?cmd=Serve&amp;issueid=%s' % (self.opdsroot, quote_plus(mag['IssueID'])),
                'kind': 'acquisition',
                'rel': 'subsection',
                'author': title,
            }
            if lazylibrarian.CONFIG['OPDS_METAINFO']:
                fname = os.path.splitext(mag['IssueFile'])[0]
                res = cache_img('magazine', mag['IssueID'], fname + '.jpg')
                entry['image'] = res[0]
            entries.append(entry)

        if len(entries) > (index + self.PAGE_SIZE):
            links.append(
                getLink(href='%s?cmd=RecentMags&amp;index=%s' % (self.opdsroot, index + self.PAGE_SIZE),
                        type='application/atom+xml; profile=opds-catalog; kind=navigation', rel='next'))
        if index >= self.PAGE_SIZE:
            links.append(
                getLink(href='%s?cmd=RecentMags&amp;index=%s' % (self.opdsroot, index - self.PAGE_SIZE),
                        type='application/atom+xml; profile=opds-catalog; kind=navigation', rel='previous'))

        feed['links'] = links
        feed['entries'] = entries[index:(index + self.PAGE_SIZE)]
        self.data = feed
        return

    def _RecentBooks(self, **kwargs):
        index = 0
        if 'index' in kwargs:
            index = int(kwargs['index'])
        myDB = database.DBConnection()
        feed = {'title': 'LazyLibrarian OPDS - Recent Books', 'id': 'Recent Books', 'updated': now()}
        links = []
        entries = []
        links.append(getLink(href=self.opdsroot, type='application/atom+xml; profile=opds-catalog; kind=navigation',
                             rel='start', title='Home'))
        links.append(getLink(href='%s?cmd=RecentBooks' % self.opdsroot,
                             type='application/atom+xml; profile=opds-catalog; kind=navigation', rel='self'))

        cmd = "select BookName,BookID,BookLibrary,BookDate,BookImg,BookDesc,BookAdded,AuthorID "
        cmd += "from books where Status='Open' order by BookLibrary DESC"
        books = myDB.select(cmd)
        for book in books:
            title = makeUnicode(book['BookName'])
            entry = {
                'title': escape(title),
                'id': escape('issue:%s' % book['BookID']),
                'updated': book['BookLibrary'],
                'href': '%s?cmd=Serve&amp;bookid=%s' % (self.opdsroot, quote_plus(book['BookID'])),
                'kind': 'acquisition',
                'rel': 'subsection',
            }
            if lazylibrarian.CONFIG['OPDS_METAINFO']:
                author = myDB.match("SELECT AuthorName from authors WHERE AuthorID='%s'" % book['AuthorID'])
                author = makeUnicode(author['AuthorName'])
                entry['image'] = book['BookImg']
                entry['content'] = escape('%s - %s' % (title, book['BookDesc']))
                entry['author'] = escape('%s' % author)
            else:
                entry['content'] = escape('%s (%s)' % (title, book['BookAdded']))
            entries.append(entry)

        if len(entries) > (index + self.PAGE_SIZE):
            links.append(
                getLink(href='%s?cmd=RecentBooks&amp;index=%s' % (self.opdsroot, index + self.PAGE_SIZE),
                        type='application/atom+xml; profile=opds-catalog; kind=navigation', rel='next'))
        if index >= self.PAGE_SIZE:
            links.append(
                getLink(href='%s?cmd=RecentBooks&amp;index=%s' % (self.opdsroot, index - self.PAGE_SIZE),
                        type='application/atom+xml; profile=opds-catalog; kind=navigation', rel='previous'))

        feed['links'] = links
        feed['entries'] = entries[index:(index + self.PAGE_SIZE)]
        self.data = feed
        return

    def _RecentAudio(self, **kwargs):
        index = 0
        if 'index' in kwargs:
            index = int(kwargs['index'])
        myDB = database.DBConnection()
        feed = {'title': 'LazyLibrarian OPDS - Recent AudioBooks', 'id': 'Recent AudioBooks', 'updated': now()}
        links = []
        entries = []
        links.append(getLink(href=self.opdsroot, type='application/atom+xml; profile=opds-catalog; kind=navigation',
                             rel='start', title='Home'))
        links.append(getLink(href='%s?cmd=RecentAudio' % self.opdsroot,
                             type='application/atom+xml; profile=opds-catalog; kind=navigation', rel='self'))

        cmd = "select BookName,BookID,AudioLibrary,BookDate,BookImg,BookDesc,BookAdded,AuthorID "
        cmd += "from books WHERE AudioStatus='Open' order by AudioLibrary DESC"
        books = myDB.select(cmd)
        for book in books:
            title = makeUnicode(book['BookName'])
            entry = {
                'title': escape(title),
                'id': escape('issue:%s' % book['BookID']),
                'updated': book['AudioLibrary'],
                'href': '%s?cmd=Serve&amp;audioid=%s' % (self.opdsroot, quote_plus(book['BookID'])),
                'kind': 'acquisition',
                'rel': 'subsection',
            }
            if lazylibrarian.CONFIG['OPDS_METAINFO']:
                author = myDB.match("SELECT AuthorName from authors WHERE AuthorID='%s'" % book['AuthorID'])
                author = makeUnicode(author['AuthorName'])
                entry['image'] = book['BookImg']
                entry['content'] = escape('%s - %s' % (title, book['BookDesc']))
                entry['author'] = escape('%s' % author)
            else:
                entry['content'] = escape('%s (%s)' % (title, book['BookAdded']))
            entries.append(entry)

        if len(entries) > (index + self.PAGE_SIZE):
            links.append(
                getLink(href='%s?cmd=RecentAudio&amp;index=%s' % (self.opdsroot, index + self.PAGE_SIZE),
                        type='application/atom+xml; profile=opds-catalog; kind=navigation', rel='next'))
        if index >= self.PAGE_SIZE:
            links.append(
                getLink(href='%s?cmd=RecentAudio&amp;index=%s' % (self.opdsroot, index - self.PAGE_SIZE),
                        type='application/atom+xml; profile=opds-catalog; kind=navigation', rel='previous'))

        feed['links'] = links
        feed['entries'] = entries[index:(index + self.PAGE_SIZE)]
        self.data = feed
        return

    def _Serve(self, **kwargs):
        if 'bookid' in kwargs:
            myid = int(kwargs['bookid'])
            myDB = database.DBConnection()
            res = myDB.match('SELECT BookFile,BookName from books where bookid=?', (myid,))
            self.file = res['BookFile']
            self.filename = os.path.split(res['BookFile'])[1]
            return
        elif 'issueid' in kwargs:
            myid = int(kwargs['issueid'])
            myDB = database.DBConnection()
            res = myDB.match('SELECT IssueFile from issues where issueid=?', (myid,))
            self.file = res['IssueFile']
            self.filename = os.path.split(res['IssueFile'])[1]
            return
        elif 'audioid' in kwargs:
            myid = int(kwargs['audioid'])
            myDB = database.DBConnection()
            res = myDB.match('SELECT AudioFile,BookName from books where audioid=?', (myid,))
            basefile = res['AudioFile']
            # zip up all the audiobook parts in a temporary file
            if basefile and os.path.isfile(basefile):
                parentdir = os.path.dirname(basefile)
                with tempfile.NamedTemporaryFile() as tmp:
                    with zipfile.ZipFile(tmp, 'w', zipfile.ZIP_DEFLATED) as myzip:
                        for root, dirs, files in os.walk(parentdir):
                            for fname in files:
                                myzip.write(os.path.join(root, fname), fname)
                    # Reset file pointer
                    tmp.seek(0)
                    return serve_file(tmp.name, 'application/x-zip-compressed', 'attachment',
                                      name=res['BookName'] + '.zip')


def getLink(href=None, type=None, rel=None, title=None):
    link = {}
    if href:
        link['href'] = href
    if type:
        link['type'] = type
    if rel:
        link['rel'] = rel
    if title:
        link['title'] = title
    return link
