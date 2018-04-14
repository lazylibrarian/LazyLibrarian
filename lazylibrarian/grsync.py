#  This file is part of Lazylibrarian.
#  Lazylibrarian is free software':'you can redistribute it and/or modify
#  it under the terms of the GNU General Public License as published by
#  the Free Software Foundation, either version 3 of the License, or
#  (at your option) any later version.
#  Lazylibrarian is distributed in the hope that it will be useful,
#  but WITHOUT ANY WARRANTY; without even the implied warranty of
#  MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
#  GNU General Public License for more details.
#  You should have received a copy of the GNU General Public License
#  along with Lazylibrarian.  If not, see <http://www.gnu.org/licenses/>.

# based on code found in https://gist.github.com/gpiancastelli/537923 by Giulio Piancastelli

import threading
import time
import traceback
import xml.dom.minidom
from string import Template

import lazylibrarian
import lib.oauth2 as oauth
from lazylibrarian import logger, database
from lazylibrarian.formatter import plural, getList
from lazylibrarian.gr import GoodReads
from lazylibrarian.common import gr_api_sleep
from lib.six import PY2
# noinspection PyUnresolvedReferences
from lib.six.moves.urllib_parse import urlencode, parse_qsl

client = ''
request_token = ''
consumer = ''
token = ''
user_id = ''


class grauth:
    def __init__(self):
        return

    @staticmethod
    def goodreads_oauth1():
        global client, request_token, consumer
        if lazylibrarian.CONFIG['GR_API'] == 'ckvsiSDsuqh7omh74ZZ6Q':
            msg = "Please get your own personal GoodReads api key from https://www.goodreads.com/api/keys and try again"
            return msg
        if not lazylibrarian.CONFIG['GR_SECRET']:
            return "Invalid or missing GR_SECRET"

        if lazylibrarian.CONFIG['GR_OAUTH_TOKEN'] and lazylibrarian.CONFIG['GR_OAUTH_SECRET']:
            return "Already authorised"

        request_token_url = '%s/oauth/request_token' % 'https://www.goodreads.com'
        authorize_url = '%s/oauth/authorize' % 'https://www.goodreads.com'
        # access_token_url = '%s/oauth/access_token' % 'https://www.goodreads.com'

        consumer = oauth.Consumer(key=str(lazylibrarian.CONFIG['GR_API']),
                                  secret=str(lazylibrarian.CONFIG['GR_SECRET']))

        client = oauth.Client(consumer)

        try:
            response, content = client.request(request_token_url, 'GET')

        except Exception as e:
            logger.error("Exception in client.request: %s %s" % (type(e).__name__, traceback.format_exc()))
            return "Exception in client.request: see debug log"

        if not response['status'].startswith('2'):
            return 'Invalid response [%s] from: %s' % (response['status'], request_token_url)

        request_token = dict(parse_qsl(content))
        if not PY2:
            request_token = {key.decode("utf-8"): request_token[key].decode("utf-8") for key in request_token}
        if 'oauth_token' in request_token:
            authorize_link = '%s?oauth_token=%s' % (authorize_url, request_token['oauth_token'])
            # print authorize_link
            return authorize_link
        else:
            return "No oauth_token, got %s" % content

    @staticmethod
    def goodreads_oauth2():
        global request_token, consumer, token, client
        try:
            if request_token and 'oauth_token' in request_token and 'oauth_token_secret' in request_token:
                token = oauth.Token(request_token['oauth_token'], request_token['oauth_token_secret'])
            else:
                return "Unable to run oAuth2 - Have you run oAuth1?"
        except Exception as e:
            logger.error("Exception in oAuth2: %s %s" % (type(e).__name__, traceback.format_exc()))
            return "Unable to run oAuth2 - Have you run oAuth1?"

        access_token_url = '%s/oauth/access_token' % 'https://www.goodreads.com'

        client = oauth.Client(consumer, token)

        try:
            response, content = client.request(access_token_url, 'POST')
        except Exception as e:
            logger.error("Exception in oauth2 client.request: %s %s" % (type(e).__name__, traceback.format_exc()))
            return "Error in oauth2 client request: see error log"

        if not response['status'].startswith('2'):
            return 'Invalid response [%s] from %s' % (response['status'], access_token_url)

        access_token = dict(parse_qsl(content))
        if not PY2:
            access_token = {key.decode("utf-8"): access_token[key].decode("utf-8") for key in access_token}
        # print access_token
        lazylibrarian.CONFIG['GR_OAUTH_TOKEN'] = access_token['oauth_token']
        lazylibrarian.CONFIG['GR_OAUTH_SECRET'] = access_token['oauth_token_secret']
        lazylibrarian.config_write('API')
        return "Authorisation complete"

    def get_user_id(self):
        global consumer, client, token, user_id
        if not lazylibrarian.CONFIG['GR_API'] or not lazylibrarian.CONFIG['GR_SECRET'] or not \
                lazylibrarian.CONFIG['GR_OAUTH_TOKEN'] or not lazylibrarian.CONFIG['GR_OAUTH_SECRET']:
            logger.warn("Goodreads user id error: Please authorise first")
            return ""
        else:
            try:
                consumer = oauth.Consumer(key=str(lazylibrarian.CONFIG['GR_API']),
                                          secret=str(lazylibrarian.CONFIG['GR_SECRET']))
                token = oauth.Token(lazylibrarian.CONFIG['GR_OAUTH_TOKEN'], lazylibrarian.CONFIG['GR_OAUTH_SECRET'])
                client = oauth.Client(consumer, token)
                user_id = self.getUserId()
                return user_id
            except Exception as e:
                logger.error("Unable to get UserID: %s %s" % (type(e).__name__, str(e)))
                return ""

    def get_shelf_list(self):
        global consumer, client, token, user_id
        if not lazylibrarian.CONFIG['GR_API'] or not lazylibrarian.CONFIG['GR_SECRET'] or not \
                lazylibrarian.CONFIG['GR_OAUTH_TOKEN'] or not lazylibrarian.CONFIG['GR_OAUTH_SECRET']:
            logger.warn("Goodreads get shelf error: Please authorise first")
            return []
        else:
            #
            # loop over each page of shelves
            #     loop over each shelf
            #         add shelf to list
            #
            consumer = oauth.Consumer(key=str(lazylibrarian.CONFIG['GR_API']),
                                      secret=str(lazylibrarian.CONFIG['GR_SECRET']))
            token = oauth.Token(lazylibrarian.CONFIG['GR_OAUTH_TOKEN'], lazylibrarian.CONFIG['GR_OAUTH_SECRET'])
            client = oauth.Client(consumer, token)
            user_id = self.getUserId()

            current_page = 0
            shelves = []
            page_shelves = 1
            while page_shelves:
                current_page = current_page + 1
                page_shelves = 0
                shelf_template = Template('${base}/shelf/list.xml?user_id=${user_id}&key=${key}&page=${page}')
                body = urlencode({})
                headers = {'Content-Type': 'application/x-www-form-urlencoded'}
                request_url = shelf_template.substitute(base='https://www.goodreads.com', user_id=user_id,
                                                        page=current_page, key=lazylibrarian.CONFIG['GR_API'])
                gr_api_sleep()
                try:
                    response, content = client.request(request_url, 'GET', body, headers)
                except Exception as e:
                    logger.error("Exception in client.request: %s %s" % (type(e).__name__, traceback.format_exc()))
                    return shelves

                if not response['status'].startswith('2'):
                    logger.error('Failure status: %s for page %s' % (response['status'], current_page))
                else:
                    xmldoc = xml.dom.minidom.parseString(content)

                    shelf_list = xmldoc.getElementsByTagName('shelves')[0]
                    for item in shelf_list.getElementsByTagName('user_shelf'):
                        shelf_name = item.getElementsByTagName('name')[0].firstChild.nodeValue
                        shelf_count = item.getElementsByTagName('book_count')[0].firstChild.nodeValue
                        shelf_exclusive = item.getElementsByTagName('exclusive_flag')[0].firstChild.nodeValue
                        shelves.append({'name': shelf_name, 'books': shelf_count, 'exclusive': shelf_exclusive})
                        page_shelves += 1

                        if lazylibrarian.LOGLEVEL > 2:
                            logger.debug('Shelf %s : %s: Exclusive %s' % (shelf_name, shelf_count, shelf_exclusive))

                    if lazylibrarian.LOGLEVEL > 2:
                        logger.debug('Found %s shelves on page %s' % (page_shelves, current_page))

            logger.debug('Found %s shelves on %s page%s' % (len(shelves), current_page - 1, plural(current_page - 1)))
            # print shelves
            return shelves

    def follow_author(self, authorid=None, follow=True):
        global consumer, client, token, user_id
        if not lazylibrarian.CONFIG['GR_API'] or not lazylibrarian.CONFIG['GR_SECRET'] or not \
                lazylibrarian.CONFIG['GR_OAUTH_TOKEN'] or not lazylibrarian.CONFIG['GR_OAUTH_SECRET']:
            logger.warn("Goodreads follow author error: Please authorise first")
            return False, 'Unauthorised'

        consumer = oauth.Consumer(key=str(lazylibrarian.CONFIG['GR_API']),
                                  secret=str(lazylibrarian.CONFIG['GR_SECRET']))
        token = oauth.Token(lazylibrarian.CONFIG['GR_OAUTH_TOKEN'], lazylibrarian.CONFIG['GR_OAUTH_SECRET'])
        client = oauth.Client(consumer, token)
        user_id = self.getUserId()

        # follow https://www.goodreads.com/author_followings?id=AUTHOR_ID&format=xml
        # unfollow https://www.goodreads.com/author_followings/AUTHOR_FOLLOWING_ID?format=xml
        gr_api_sleep()

        if follow:
            body = urlencode({'id': authorid, 'format': 'xml'})
            headers = {'Content-Type': 'application/x-www-form-urlencoded'}
            try:
                response, content = client.request('%s/author_followings' % 'https://www.goodreads.com', 'POST', body,
                                                   headers)
            except Exception as e:
                logger.error("Exception in client.request: %s %s" % (type(e).__name__, traceback.format_exc()))
                return False, "Error in client.request: see error log"
        else:
            body = urlencode({'format': 'xml'})
            headers = {'Content-Type': 'application/x-www-form-urlencoded'}
            try:
                response, content = client.request('%s/author_followings/%s' % ('https://www.goodreads.com', authorid),
                                                   'DELETE', body, headers)
            except Exception as e:
                logger.error("Exception in client.request: %s %s" % (type(e).__name__, traceback.format_exc()))
                return False, "Error in client.request: see error log"

        if follow and response['status'] == '422':
            return True, 'Already following'

        if response['status'].startswith('2'):
            if follow:
                return True, content.split('<id>')[1].split('</id>')[0]
            return True, ''
        return False, 'Failure status: %s' % response['status']

    def create_shelf(self, shelf='lazylibrarian'):
        global consumer, client, token, user_id
        if not lazylibrarian.CONFIG['GR_API'] or not lazylibrarian.CONFIG['GR_SECRET'] or not \
                lazylibrarian.CONFIG['GR_OAUTH_TOKEN'] or not lazylibrarian.CONFIG['GR_OAUTH_SECRET']:
            logger.warn("Goodreads create shelf error: Please authorise first")
            return False, 'Unauthorised'

        consumer = oauth.Consumer(key=str(lazylibrarian.CONFIG['GR_API']),
                                  secret=str(lazylibrarian.CONFIG['GR_SECRET']))
        token = oauth.Token(lazylibrarian.CONFIG['GR_OAUTH_TOKEN'], lazylibrarian.CONFIG['GR_OAUTH_SECRET'])
        client = oauth.Client(consumer, token)
        user_id = self.getUserId()

        # could also pass [featured] [exclusive_flag] [sortable_flag] all default to False
        body = urlencode({'user_shelf[name]': shelf.lower()})
        headers = {'Content-Type': 'application/x-www-form-urlencoded'}
        gr_api_sleep()

        try:
            response, content = client.request('%s/user_shelves.xml' % 'https://www.goodreads.com', 'POST',
                                               body, headers)
        except Exception as e:
            logger.error("Exception in client.request: %s %s" % (type(e).__name__, traceback.format_exc()))
            return False, "Error in client.request: see error log"

        if not response['status'].startswith('2'):
            msg = 'Failure status: %s' % response['status']
            return False, msg
        return True, ''

    def get_gr_shelf_contents(self, shelf='to-read'):
        global consumer, client, token, user_id
        if not lazylibrarian.CONFIG['GR_API'] or not lazylibrarian.CONFIG['GR_SECRET'] or not \
                lazylibrarian.CONFIG['GR_OAUTH_TOKEN'] or not lazylibrarian.CONFIG['GR_OAUTH_SECRET']:
            logger.warn("Goodreads shelf contents error: Please authorise first")
            return []
        else:
            #
            # loop over each page of owned books
            #     loop over each book
            #         add book to list
            #
            consumer = oauth.Consumer(key=str(lazylibrarian.CONFIG['GR_API']),
                                      secret=str(lazylibrarian.CONFIG['GR_SECRET']))
            token = oauth.Token(lazylibrarian.CONFIG['GR_OAUTH_TOKEN'], lazylibrarian.CONFIG['GR_OAUTH_SECRET'])
            client = oauth.Client(consumer, token)
            user_id = self.getUserId()
            logger.debug('User id is: ' + user_id)

            current_page = 0
            total_books = 0
            gr_list = []

            while True:
                current_page = current_page + 1
                content = self.getShelfBooks(current_page, shelf)
                xmldoc = xml.dom.minidom.parseString(content)

                page_books = 0
                for book in xmldoc.getElementsByTagName('book'):
                    book_id, book_title = self.getBookInfo(book)

                    if lazylibrarian.LOGLEVEL > 2:
                        try:
                            logger.debug('Book %10s : %s' % (str(book_id), book_title))
                        except UnicodeEncodeError:
                            logger.debug('Book %10s : %s' % (str(book_id), 'Title Messed Up By Unicode Error'))

                    gr_list.append(book_id)

                    page_books += 1
                    total_books += 1

                if lazylibrarian.LOGLEVEL > 2:
                    logger.debug('Found %s books on page %s (total = %s)' % (page_books, current_page, total_books))
                if page_books == 0:
                    break

            logger.debug('Found %s' % total_books)
            return gr_list

    #############################
    #
    # who are we?
    #
    @staticmethod
    def getUserId():
        global client, user_id
        gr_api_sleep()

        try:
            response, content = client.request('%s/api/auth_user' % 'https://www.goodreads.com', 'GET')
        except Exception as e:
            logger.error("Error in client.request: %s %s" % (type(e).__name__, traceback.format_exc()))
            return ''
        if not response['status'].startswith('2'):
            logger.error('Cannot fetch resource: %s' % response['status'])
            return ''

        userxml = xml.dom.minidom.parseString(content)
        user_id = userxml.getElementsByTagName('user')[0].attributes['id'].value
        return str(user_id)

    #############################
    #
    # fetch xml for a page of books on a shelf
    #
    @staticmethod
    def getShelfBooks(page, shelf_name):
        global client, user_id
        data = '${base}/review/list?format=xml&v=2&id=${user_id}&sort=author&order=a'
        data += '&key=${key}&page=${page}&per_page=100&shelf=${shelf_name}'
        owned_template = Template(data)
        body = urlencode({})
        headers = {'Content-Type': 'application/x-www-form-urlencoded'}
        request_url = owned_template.substitute(base='https://www.goodreads.com', user_id=user_id, page=page,
                                                key=lazylibrarian.CONFIG['GR_API'], shelf_name=shelf_name)
        gr_api_sleep()
        try:
            response, content = client.request(request_url, 'GET', body, headers)
        except Exception as e:
            logger.error("Exception in client.request: %s %s" % (type(e).__name__, traceback.format_exc()))
            return "Error in client.request: see error log"
        if not response['status'].startswith('2'):
            logger.error('Failure status: %s for page %s' % (response['status'], page))
        return content

    #############################
    #
    # grab id and title from a <book> node
    #
    @staticmethod
    def getBookInfo(book):
        book_id = book.getElementsByTagName('id')[0].firstChild.nodeValue
        book_title = book.getElementsByTagName('title')[0].firstChild.nodeValue
        return book_id, book_title

    @staticmethod
    def BookToList(book_id, shelf_name, action='add'):
        global client
        if action == 'remove':
            body = urlencode({'name': shelf_name, 'book_id': book_id, 'a': 'remove'})
        else:
            body = urlencode({'name': shelf_name, 'book_id': book_id})
        headers = {'Content-Type': 'application/x-www-form-urlencoded'}
        gr_api_sleep()
        try:
            response, content = client.request('%s/shelf/add_to_shelf.xml' % 'https://www.goodreads.com', 'POST',
                                               body, headers)
        except Exception as e:
            logger.error("Exception in client.request: %s %s" % (type(e).__name__, traceback.format_exc()))
            return False, "Error in client.request: see error log"

        if not response['status'].startswith('2'):
            msg = 'Failure status: %s' % response['status']
            return False, msg
        return True, content

        #############################


def test_auth():
    global user_id
    GA = grauth()
    try:
        user_id = GA.get_user_id()
    except Exception as e:
        return "GR Auth %s: %s" % (type(e).__name__, str(e))
    if user_id:
        return "Pass: UserID is %s" % user_id
    else:
        return "Failed, check the debug log"


def cron_sync_to_gr():
    if 'GRSync' not in [n.name for n in [t for t in threading.enumerate()]]:
        _ = sync_to_gr()
    else:
        logger.debug("GRSync is already running")


def sync_to_gr():
    msg = ''
    try:
        threading.currentThread().name = 'GRSync'
        if lazylibrarian.CONFIG['GR_WANTED']:
            to_read_shelf, ll_wanted = grsync('Wanted', lazylibrarian.CONFIG['GR_WANTED'])
            msg += "%s change%s to %s shelf\n" % (to_read_shelf, plural(to_read_shelf),
                                                  lazylibrarian.CONFIG['GR_WANTED'])
            msg += "%s change%s to Wanted from GoodReads\n" % (ll_wanted, plural(ll_wanted))
        else:
            msg += "Sync Wanted books is disabled\n"
        if lazylibrarian.CONFIG['GR_OWNED']:
            to_owned_shelf, ll_have = grsync('Open', lazylibrarian.CONFIG['GR_OWNED'])
            msg += "%s change%s to %s shelf\n" % (to_owned_shelf, plural(to_owned_shelf),
                                                  lazylibrarian.CONFIG['GR_OWNED'])
            msg += "%s change%s to Owned from GoodReads\n" % (ll_have, plural(ll_have))
        else:
            msg += "Sync Owned books is disabled\n"
        logger.info(msg.strip('\n').replace('\n', ', '))
    except Exception as e:
        logger.error("Exception in sync_to_gr: %s %s" % (type(e).__name__, str(e)))
    finally:
        threading.currentThread().name = 'WEBSERVER'
        return msg


def grfollow(authorid, follow=True):
    myDB = database.DBConnection()
    match = myDB.match('SELECT AuthorName,GRfollow from authors WHERE authorid=?', (authorid,))
    if match:
        if follow:
            action = 'Follow'
            aname = match['AuthorName']
            actionid = authorid
        else:
            action = 'Unfollow'
            aname = authorid
            actionid = match['GRfollow']

        GA = grauth()
        res, msg = GA.follow_author(actionid, follow)
        if res:
            if follow:
                return "%s author %s, followid=%s" % (action, aname, msg)
            else:
                return "%s author %s" % (action, aname)
        else:
            return "Unable to %s %s: %s" % (action, authorid, msg)
    else:
        return "Unable to (un)follow %s, invalid authorid" % authorid


def grsync(status, shelf):
    # noinspection PyBroadException
    try:
        shelf = shelf.lower()
        logger.info('Syncing %s to %s shelf' % (status, shelf))
        myDB = database.DBConnection()
        cmd = 'select bookid from books where status="%s"' % status
        if status == 'Open':
            cmd += ' or status="Have"'
        results = myDB.select(cmd)
        ll_list = []
        for terms in results:
            ll_list.append(terms['bookid'])

        GA = grauth()
        GR = None
        shelves = GA.get_shelf_list()
        found = False
        for item in shelves:  # type: dict
            if item['name'] == shelf:
                found = True
                break
        if not found:
            res, msg = GA.create_shelf(shelf=shelf)
            if not res:
                logger.debug("Unable to create shelf %s: %s" % (shelf, msg))
                return 0, 0
            else:
                logger.debug("Created new goodreads shelf: %s" % shelf)

        gr_shelf = GA.get_gr_shelf_contents(shelf=shelf)
        dstatus = status
        if dstatus == "Open":
            dstatus += "/Have"

        logger.info("There are %s %s books, %s books on goodreads %s shelf" %
                    (len(ll_list), dstatus, len(gr_shelf), shelf))

        # Sync method for WANTED:
        # Get results of last_sync (if any)
        # For each book in last_sync
        #    if not in ll_list, new deletion, remove from gr_shelf
        #    if not in gr_shelf, new deletion, remove from ll_list, mark Skipped
        # For each book in ll_list
        #    if not in last_sync, new addition, add to gr_shelf
        # For each book in gr_shelf
        #    if not in last sync, new addition, add to ll_list, mark Wanted
        #
        # save ll WANTED as last_sync

        # For HAVE/OPEN method is the same, but only change status if HAVE, not OPEN

        cmd = 'select SyncList from sync where UserID="%s" and Label="%s"' % ("goodreads", shelf)
        res = myDB.match(cmd)
        last_sync = []
        shelf_changed = 0
        ll_changed = 0
        if res:
            last_sync = getList(res['SyncList'])

        added_to_shelf = list(set(gr_shelf) - set(last_sync))
        removed_from_shelf = list(set(last_sync) - set(gr_shelf))
        added_to_ll = list(set(ll_list) - set(last_sync))
        removed_from_ll = list(set(last_sync) - set(ll_list))

        logger.info("%s missing from lazylibrarian %s" % (len(removed_from_ll), shelf))
        for book in removed_from_ll:
            # first the deletions since last sync...
            try:
                res, content = GA.BookToList(book, shelf, action='remove')
            except Exception as e:
                logger.error("Error removing %s from %s: %s %s" % (book, shelf, type(e).__name__, str(e)))
                res = None
                content = ''
            if res:
                logger.debug("%10s removed from %s shelf" % (book, shelf))
                shelf_changed += 1
            else:
                logger.warn("Failed to remove %s from %s shelf: %s" % (book, shelf, content))

        logger.info("%s missing from goodreads %s" % (len(removed_from_shelf), shelf))
        for book in removed_from_shelf:
            # deleted from goodreads
            cmd = 'select Status from books where BookID="%s"' % book
            res = myDB.match(cmd)
            if not res:
                logger.debug('Adding new book %s to database' % book)
                if not GR:
                    GR = GoodReads(book)
                GR.find_book(book)
                res = myDB.match(cmd)
            if not res:
                logger.warn('Book %s not found in database' % book)
            else:
                if res['Status'] in ['Have', 'Wanted']:
                    myDB.action('UPDATE books SET Status="Skipped" WHERE BookID=?', (book,))
                    ll_changed += 1
                    logger.debug("%10s set to Skipped" % book)
                else:
                    logger.warn("Not removing %s, book is marked %s" % (book, res['Status']))

        # new additions to lazylibrarian
        logger.info("%s new in lazylibrarian %s" % (len(added_to_ll), shelf))
        for book in added_to_ll:
            try:
                res, content = GA.BookToList(book, shelf, action='add')
            except Exception as e:
                logger.error("Error adding %s to %s: %s %s" % (book, shelf, type(e).__name__, str(e)))
                res = None
                content = ''
            if res:
                logger.debug("%10s added to %s shelf" % (book, shelf))
                shelf_changed += 1
            else:
                logger.warn("Failed to add %s to %s shelf: %s" % (book, shelf, content))

        # new additions to goodreads shelf
        logger.info("%s new in goodreads %s" % (len(added_to_shelf), shelf))
        for book in added_to_shelf:
            cmd = 'select Status from books where BookID="%s"' % book
            res = myDB.match(cmd)
            if not res:
                logger.debug('Adding new book %s to database' % book)
                if not GR:
                    GR = GoodReads(book)
                GR.find_book(book)
                res = myDB.match(cmd)
            if not res:
                logger.warn('Book %s not found in database' % book)
            else:
                if status == 'Open':
                    if res['Status'] == 'Open':
                        logger.warn("Book %s is already marked Open" % book)
                    else:
                        myDB.action('UPDATE books SET Status="Have" WHERE BookID=?', (book,))
                        ll_changed += 1
                        logger.debug("%10s set to Have" % book)
                elif status == 'Wanted':
                    # if in "wanted" and already marked "Open/Have", optionally delete from "wanted"
                    # (depending on user prefs, to-read and wanted might not be the same thing)
                    if lazylibrarian.CONFIG['GR_UNIQUE'] and res['Status'] in ['Open', 'Have']:
                        try:
                            res, content = GA.BookToList(book, shelf, action='remove')
                        except Exception as e:
                            logger.error("Error removing %s from %s: %s %s" % (book, shelf, type(e).__name__, str(e)))
                            res = None
                            content = ''
                        if res:
                            logger.debug("%10s removed from %s shelf" % (book, shelf))
                            shelf_changed += 1
                        else:
                            logger.warn("Failed to remove %s from %s shelf: %s" % (book, shelf, content))
                    elif res['Status'] != 'Open':
                        myDB.action('UPDATE books SET Status="Wanted" WHERE BookID=?', (book,))
                        ll_changed += 1
                        logger.debug("%10s set to Wanted" % book)
                    else:
                        logger.warn("Not setting %s as Wanted, already marked Open" % book)

        # get new definitive list from ll
        cmd = 'select bookid from books where status="%s"' % status
        if status == 'Open':
            cmd += ' or status="Have"'
        results = myDB.select(cmd)
        ll_list = []
        for terms in results:
            ll_list.append(terms['bookid'])

        # store as comparison for next sync
        controlValueDict = {"UserID": "goodreads", "Label": shelf}
        newValueDict = {"Date": str(time.time()), "Synclist": ', '.join(ll_list)}
        myDB.upsert("sync", newValueDict, controlValueDict)

        logger.debug('Sync %s to %s shelf complete' % (status, shelf))
        return shelf_changed, ll_changed

    except Exception:
        logger.error('Unhandled exception in grsync: %s' % traceback.format_exc())
        return 0, 0
