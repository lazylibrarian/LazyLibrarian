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

# based on code found in https://gist.github.com/gpiancastelli/537923 by Giulio Piancastelli

import traceback
import lib.oauth2 as oauth
import urllib
import urlparse
from string import Template
import time
import xml.dom.minidom

import lazylibrarian
from lazylibrarian import logger, database
from lazylibrarian.gr import GoodReads

class grauth:

    def __init__(self):
        self.key = lazylibrarian.CONFIG['GR_API']
        self.secret = lazylibrarian.CONFIG['GR_SECRET']
        self.oauth_token = lazylibrarian.CONFIG['GR_OAUTH_TOKEN']
        self.oauth_secret = lazylibrarian.CONFIG['GR_OAUTH_SECRET']
        self.url = 'http://www.goodreads.com'
        self.consumer = None
        self.client = None
        self.token = None
        self.user_id = None
        self.oauth = None
        self.request_token = None


    def goodreads_oauth1(self):
        if self.key == 'ckvsiSDsuqh7omh74ZZ6Q':
            return "Please get your own personal GoodReads api key"
        if not self.secret:
            return "Invalid or missing GR_SECRET"

        #if self.oauth_token and self.oauth_secret:
        #    return "Already authorised"

        request_token_url = '%s/oauth/request_token' % self.url
        authorize_url = '%s/oauth/authorize' % self.url
        # access_token_url = '%s/oauth/access_token' % self.url

        consumer = oauth.Consumer(key=str(self.key), secret=str(self.secret))

        client = oauth.Client(consumer)

        try:
            response, content = client.request(request_token_url, 'GET')
        except Exception as e:
            return "Exception in client.request: %s" % str(e)

        if response['status'] != '200':
            return 'Invalid response from: %s' % request_token_url

        self.request_token = dict(urlparse.parse_qsl(content))

        authorize_link = '%s?oauth_token=%s' % (authorize_url, self.request_token['oauth_token'])
        return authorize_link

    def goodreads_oauth2(self):
        self.token = oauth.Token(self.request_token['oauth_token'], self.request_token['oauth_token_secret'])
        access_token_url = '%s/oauth/access_token' % self.url

        client = oauth.Client(self.consumer, self.token)
        response, content = client.request(access_token_url, 'POST')
        if response['status'] != '200':
            raise Exception('Invalid response: %s' % response['status'])

        access_token = dict(urlparse.parse_qsl(content))

        self.oauth_token = access_token['oauth_token']
        self.oauth_secret = access_token['oauth_token_secret']
        return {'gr_oauth_token': self.oauth_token, 'gr_oauth_secret': self.oauth_secret}
        #lazylibrarian.CONFIG['GR_OAUTH_TOKEN'] = self.oauth_token
        #lazylibrarian.CONFIG['GR_OAUTH_SECRET'] = self.oauth_secret
        #lazylibrarian.config_write()


    def get_user_id(self):

        if not self.key or not self.secret or not self.oauth_token or not self.oauth_secret:
            logger.debug("Goodreads sync error: Please authorise first")
            return ""
        else:
            try:
                if not self.consumer:
                    self.consumer = oauth.Consumer(key=str(self.key), secret=str(self.secret))
                if not self.token:
                    self.token = oauth.Token(self.oauth_token, self.oauth_secret)
                if not self.client:
                    self.client = oauth.Client(self.consumer, self.token)

                self.user_id = self.getUserId()
                return self.user_id
            except Exception as e:
                logger.debug("Unable to get UserID: %s" % str(e))
                return ""


    def get_gr_shelf(self, shelf='to-read'):

        if not self.key or not self.secret or not self.oauth_token or not self.oauth_secret:
            logger.debug("Goodreads sync error: Please authorise first")
            return []
        else:
            #
            # loop over each page of owned books
            #     loop over each book
            #         add book to list
            #
            if not self.consumer:
                self.consumer = oauth.Consumer(key=str(self.key), secret=str(self.secret))
            if not self.token:
                self.token = oauth.Token(self.oauth_token, self.oauth_secret)
            if not self.client:
                self.client = oauth.Client(self.consumer, self.token)

            self.user_id = self.getUserId()
            logger.debug('User id is: ' + self.user_id)

            current_page = 0
            total_books = 0
            gr_list = []

            while True:
                current_page = current_page + 1


                time_now = int(time.time())
                if time_now <= lazylibrarian.LAST_GOODREADS:
                    time.sleep(1)
                    lazylibrarian.LAST_GOODREADS = time_now
                content = self.getShelfBooks(current_page, shelf)
                xmldoc = xml.dom.minidom.parseString(content)

                page_books = 0
                for book in xmldoc.getElementsByTagName('book'):
                    book_id , book_title = self.getBookInfo(book)

                    if lazylibrarian.LOGLEVEL > 2:
                        try:
                            logger.debug('Book %10s : %s' % (str(book_id), book_title))
                        except UnicodeEncodeError:
                            logger.debug('Book %10s : %s' % (str(book_id), 'Title Messed Up By Unicode Error'))

                    gr_list.append(book_id)

                    page_books += 1
                    total_books += 1

                logger.debug('Found %s books on page %s (total = %s)' % (page_books, current_page, total_books))
                if page_books == 0:
                    break

            logger.debug('Found %s' % total_books)
            return gr_list


    #############################
    #
    # who are we?
    #
    def getUserId(self):

        response, content = self.client.request('%s/api/auth_user' % self.url,'GET')
        if response['status'] != '200':
            raise Exception('Cannot fetch resource: %s' % response['status'])

        userxml = xml.dom.minidom.parseString(content)
        self.user_id = userxml.getElementsByTagName('user')[0].attributes['id'].value
        return str(self.user_id)


    #############################
    #
    # fetch xml for a page of books on a shelf
    #
    def getShelfBooks(self, page, shelf_name):

        owned_template = Template('${base}/review/list?format=xml&v=2&id=${user_id}&sort=author&order=a&key=${key}&page=${page}&per_page=100&shelf=${shelf_name}')

        body = urllib.urlencode({})
        headers = {'content-type': 'application/x-www-form-urlencoded'}
        request_url = owned_template.substitute(base=self.url, user_id=self.user_id, page=page, key=self.key, shelf_name=shelf_name)
        response, content = self.client.request(request_url, 'GET', body, headers)
        if response['status'] != '200':
            raise Exception('Failure status: %s for page ' % response['status'] + page)
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


    def BookToList(self, book_id, shelf_name, action='add'):
        if action == 'remove':
            body = urllib.urlencode({'name': shelf_name, 'book_id': book_id, 'a': 'remove'})
        else:
            body = urllib.urlencode({'name': shelf_name, 'book_id': book_id})
        headers = {'content-type': 'application/x-www-form-urlencoded'}
        response, content = self.client.request('%s/shelf/add_to_shelf.xml' % self.url,'POST', body, headers)

        if response['status'] != '200' and response['status'] != '201':
            msg = 'Failure status: %s' % response['status']
            return False, msg
        return True, content


    #############################

def test_auth():
    GA = grauth()
    try:
        user_id = GA.get_user_id()
    except Exception as e:
        return "GR Auth Error: %s" % str(e)
    if user_id:
        return "Pass: UserID is %s" % user_id
    else:
        return "Failed, check the debug log"


def sync_to_gr():
    to_read_shelf, ll_wanted, moved = grsync('Wanted', 'to-read')
    to_owned_shelf, ll_have, moved = grsync('Open', 'owned')
    msg = "%s added to to-read shelf\n" % to_read_shelf
    msg += "%s added to owned shelf\n" % to_owned_shelf
    msg += "%s moved to owned shelf\n" % moved
    msg += "%s marked Wanted\n" % ll_wanted
    msg += "%s marked Have" % ll_have
    return msg

def grsync(status, shelf):
    try:
        logger.debug('Syncing %s to %s shelf' % (status, shelf))
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
        gr_shelf = GA.get_gr_shelf(shelf=shelf)
        dstatus = status
        if dstatus == "Open":
            dstatus += "/Have"

        logger.debug("There are %s %s books, %s books on goodreads %s shelf" %
                     (len(ll_list), dstatus, len(gr_shelf), shelf))
        #print ll_list
        #print gr_shelf

        not_on_shelf = []
        not_in_ll = []
        for book in ll_list:
            if book not in gr_shelf:
                not_on_shelf.append(book)
        for book in gr_shelf:
            if book not in ll_list:
                not_in_ll.append(book)

        to_shelf = 0
        to_ll = 0
        moved = 0
        # these need adding to shelf
        if not lazylibrarian.CONFIG['GR_OAUTH_SECRET']:
            logger.debug('Not connected to goodreads')
        else:
            for book in not_on_shelf:
                #print "%s is not on shelf" % book
                time_now = int(time.time())
                if time_now <= lazylibrarian.LAST_GOODREADS:
                    time.sleep(1)
                    lazylibrarian.LAST_GOODREADS = time_now
                try:
                    res, content = GA.BookToList(book, shelf)
                except Exception as e:
                    logger.debug("Error in BookToList: %s" % str(e))
                    res = None

                if res:
                    logger.debug("%10s added to %s shelf" % (book, shelf))
                    to_shelf += 1
                    #print content
                else:
                    logger.debug("Failed to add %s to %s shelf" % (book, shelf))
                    #print content

        # "to-read" books need adding to lazylibrarian as "wanted" if not already Open/Have,
        # if they are already Open/Have, remove from goodreads to-read shelf, add to owned shelf
        # "owned" need adding as "Have" as librarysync will pick up "Open" ones or change Have to Open

        for book in not_in_ll:
            #print "%s is not marked %s" % (book, status)
            cmd = 'select Status from books where bookid="%s"' % book
            result = myDB.match(cmd)
            if result:
                if result['Status'] in ['Have', 'Open']:  # don't change status if we have it
                    if shelf == 'to-read':

                        time_now = int(time.time())
                        if time_now <= lazylibrarian.LAST_GOODREADS:
                            time.sleep(1)
                            lazylibrarian.LAST_GOODREADS = time_now
                        # need to move it from to-read shelf to owned shelf
                        res, content = GA.BookToList(book, 'to-read', 'remove')
                        if res:
                            logger.debug("%10s removed from to-read shelf" % book)
                            #print content
                        else:
                            logger.debug("Failed to remove %s from to-read shelf" % book)
                            #print content

                        time_now = int(time.time())
                        if time_now <= lazylibrarian.LAST_GOODREADS:
                            time.sleep(1)
                            lazylibrarian.LAST_GOODREADS = time_now
                        res, content = GA.BookToList(book, 'owned', 'add')
                        if res:
                            logger.debug("%10s added to owned shelf" % book)
                            moved += 1
                            #print content
                        else:
                            logger.debug("Failed to add %s to owned shelf" % book)
                            #print content
                    else:
                        logger.debug("%10s is already marked %s" % (book, result['Status']))
                elif shelf == 'owned':
                    myDB.action('UPDATE books SET Status="Have" WHERE BookID=?', (book,))
                else:
                    myDB.action('UPDATE books SET Status=? WHERE BookID=?', (status, book))
            else:  # add book to database as wanted
                logger.debug('Adding new book %s to database' % book)
                if not GR:
                    GR = GoodReads(book)
                GR.find_book(book)
                to_ll += 1

        logger.debug('Sync %s to %s shelf complete' % (status, shelf))
        return to_shelf, to_ll, moved

    except Exception:
        logger.error('Unhandled exception in grsync: %s' % traceback.format_exc())
        return 0,0,0

if __name__ == '__main__':
  test_auth()
