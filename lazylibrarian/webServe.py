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


import datetime
import hashlib
import os
import random
import re
import threading
import time
import traceback
from shutil import copyfile, rmtree

# noinspection PyUnresolvedReferences
from lib.six.moves.urllib_parse import quote_plus, unquote_plus, urlsplit, urlunsplit

import cherrypy
import lazylibrarian
import lib.simplejson as simplejson
from cherrypy.lib.static import serve_file
from lazylibrarian import logger, database, notifiers, versioncheck, magazinescan, \
    qbittorrent, utorrent, rtorrent, transmission, sabnzbd, nzbget, deluge, synology, grsync
from lazylibrarian.bookwork import setSeries, deleteEmptySeries, getSeriesAuthors
from lazylibrarian.cache import cache_img
from lazylibrarian.calibre import calibreTest, syncCalibreList, calibredb
from lazylibrarian.common import showJobs, restartJobs, clearLog, scheduleJob, checkRunningJobs, setperm, \
    aaUpdate, csv_file, saveLog, logHeader, pwd_generator, pwd_check, isValidEmail, mimeType, zipAudio, runScript
from lazylibrarian.csvfile import import_CSV, export_CSV, dump_table, restore_table
from lazylibrarian.downloadmethods import NZBDownloadMethod, TORDownloadMethod, DirectDownloadMethod
from lazylibrarian.formatter import unaccented, unaccented_str, plural, now, today, check_int, replace_all, \
    safe_unicode, cleanName, surnameFirst, sortDefinite, getList, makeUnicode, makeBytestr, md5_utf8, dateFormat, \
    check_year, dispName
from lazylibrarian.gb import GoogleBooks
from lazylibrarian.gr import GoodReads
from lazylibrarian.images import getBookCover, createMagCover
from lazylibrarian.importer import addAuthorToDB, addAuthorNameToDB, update_totals, search_for
from lazylibrarian.librarysync import LibraryScan
from lazylibrarian.manualbook import searchItem
from lazylibrarian.notifiers import notify_snatch, custom_notify_snatch
from lazylibrarian.postprocess import processAlternate, processDir, delete_task, getDownloadProgress
from lazylibrarian.providers import test_provider
from lazylibrarian.searchbook import search_book
from lazylibrarian.searchmag import search_magazines
from lazylibrarian.searchrss import search_wishlist
from lazylibrarian.rssfeed import genFeed
from lazylibrarian.opds import OPDS
from lazylibrarian.bookrename import nameVars
from lib.deluge_client import DelugeRPCClient
from lib.six import PY2, text_type
from mako import exceptions
from mako.lookup import TemplateLookup


def serve_template(templatename, **kwargs):
    threading.currentThread().name = "WEBSERVER"
    interface_dir = os.path.join(str(lazylibrarian.PROG_DIR), 'data/interfaces/')
    template_dir = os.path.join(str(interface_dir), lazylibrarian.CONFIG['HTTP_LOOK'])
    if not os.path.isdir(template_dir):
        logger.error("Unable to locate template [%s], reverting to legacy" % template_dir)
        lazylibrarian.CONFIG['HTTP_LOOK'] = 'legacy'
        template_dir = os.path.join(str(interface_dir), lazylibrarian.CONFIG['HTTP_LOOK'])

    _hplookup = TemplateLookup(directories=[template_dir], input_encoding='utf-8')
    # noinspection PyBroadException
    try:
        if lazylibrarian.UPDATE_MSG:
            template = _hplookup.get_template("dbupdate.html")
            return template.render(perm=0, message="Database upgrade in progress, please wait...",
                                   title="Database Upgrade", timer=5)

        if lazylibrarian.CONFIG['HTTP_LOOK'] == 'legacy' or not lazylibrarian.CONFIG['USER_ACCOUNTS']:
            template = _hplookup.get_template(templatename)
            # noinspection PyArgumentList
            return template.render(perm=lazylibrarian.perm_admin, **kwargs)

        username = ''  # anyone logged in yet?
        perm = 0
        res = None
        myDB = database.DBConnection()
        cookie = cherrypy.request.cookie
        if cookie and 'll_uid' in list(cookie.keys()):
            res = myDB.match('SELECT UserName,Perms from users where UserID=?', (cookie['ll_uid'].value,))
        else:
            cnt = myDB.match("select count(*) as counter from users")
            if cnt['counter'] == 1 and lazylibrarian.CONFIG['SINGLE_USER']:
                res = myDB.match('SELECT UserName,Perms,UserID from users')
                cherrypy.response.cookie['ll_uid'] = res['UserID']
                logger.debug("Auto-login for %s" % res['UserName'])
                lazylibrarian.SHOWLOGOUT = 0
            else:
                lazylibrarian.SHOWLOGOUT = 1
        if res:
            perm = check_int(res['Perms'], 0)
            username = res['UserName']

        if perm == 0 and templatename != "register.html" and templatename != "response.html":
            templatename = "login.html"
        elif templatename == 'config.html' and not perm & lazylibrarian.perm_config:
            logger.warn('User %s attempted to access %s' % (username, templatename))
            templatename = "login.html"
        elif templatename == 'logs.html' and not perm & lazylibrarian.perm_logs:
            logger.warn('User %s attempted to access %s' % (username, templatename))
            templatename = "login.html"
        elif templatename == 'history.html' and not perm & lazylibrarian.perm_history:
            logger.warn('User %s attempted to access %s' % (username, templatename))
            templatename = "login.html"
        elif templatename == 'managebooks.html' and not perm & lazylibrarian.perm_managebooks:
            logger.warn('User %s attempted to access %s' % (username, templatename))
            templatename = "login.html"
        elif templatename == 'books.html' and not perm & lazylibrarian.perm_ebook:
            logger.warn('User %s attempted to access %s' % (username, templatename))
            templatename = "login.html"
        elif templatename == 'author.html' and not perm & lazylibrarian.perm_ebook \
                and not perm & lazylibrarian.perm_audio:
            logger.warn('User %s attempted to access %s' % (username, templatename))
            templatename = "login.html"
        elif templatename in ['magazines.html', 'issues.html', 'manageissues.html'] \
                and not perm & lazylibrarian.perm_magazines:
            logger.warn('User %s attempted to access %s' % (username, templatename))
            templatename = "login.html"
        elif templatename == 'audio.html' and not perm & lazylibrarian.perm_audio:
            logger.warn('User %s attempted to access %s' % (username, templatename))
            templatename = "login.html"
        elif templatename == 'choosetype.html' and not perm & lazylibrarian.perm_download:
            logger.warn('User %s attempted to access %s' % (username, templatename))
            templatename = "login.html"
        elif templatename in ['series.html', 'members.html'] and not perm & lazylibrarian.perm_series:
            logger.warn('User %s attempted to access %s' % (username, templatename))
            templatename = "login.html"
        elif templatename in ['editauthor.html', 'editbook.html'] and not perm & lazylibrarian.perm_edit:
            logger.warn('User %s attempted to access %s' % (username, templatename))
            templatename = "login.html"
        elif templatename in ['manualsearch.html', 'searchresults.html'] and not perm & lazylibrarian.perm_search:
            logger.warn('User %s attempted to access %s' % (username, templatename))
            templatename = "login.html"

        if lazylibrarian.LOGLEVEL & lazylibrarian.log_admin:
            logger.debug("User %s: %s %s" % (username, perm, templatename))
        template = _hplookup.get_template(templatename)
        if templatename == "login.html":
            return template.render(perm=0, title="Redirected")
        else:
            # noinspection PyArgumentList
            return template.render(perm=perm, **kwargs)
    except Exception:
        return exceptions.html_error_template().render()


# noinspection PyProtectedMember
class WebInterface(object):
    @cherrypy.expose
    def index(self):
        raise cherrypy.HTTPRedirect("home")

    @cherrypy.expose
    def home(self):
        title = 'Authors'
        if lazylibrarian.IGNORED_AUTHORS:
            title = 'Ignored Authors'
        return serve_template(templatename="index.html", title=title, authors=[])

    @cherrypy.expose
    def profile(self):
        title = 'User Profile'
        cookie = cherrypy.request.cookie
        if cookie and 'll_uid' in list(cookie.keys()):
            myDB = database.DBConnection()
            user = myDB.match('SELECT UserName,Name,Email,SendTo from users where UserID=?', (cookie['ll_uid'].value,))
            if user:
                return serve_template(templatename="profile.html", title=title, user=user)
        return serve_template(templatename="index.html", title=title, authors=[])

    # noinspection PyUnusedLocal
    @cherrypy.expose
    @cherrypy.tools.json_out()
    def getIndex(self, iDisplayStart=0, iDisplayLength=100, iSortCol_0=0, sSortDir_0="desc", sSearch="", **kwargs):
        rows = []
        filtered = []
        rowlist = []
        # noinspection PyBroadException
        try:
            # kwargs is used by datatables to pass params
            # for arg in kwargs:
            #     print arg, kwargs[arg]
            myDB = database.DBConnection()
            iDisplayStart = int(iDisplayStart)
            iDisplayLength = int(iDisplayLength)
            lazylibrarian.CONFIG['DISPLAYLENGTH'] = iDisplayLength

            cmd = 'SELECT AuthorImg,AuthorName,LastBook,LastDate,Status'
            cmd += ',AuthorLink,LastLink,HaveBooks,UnignoredBooks,AuthorID,LastBookID from authors '
            if lazylibrarian.IGNORED_AUTHORS:
                cmd += 'where Status == "Ignored" '
            else:
                cmd += 'where Status != "Ignored" '
            cmd += 'order by AuthorName COLLATE NOCASE'

            if lazylibrarian.LOGLEVEL & lazylibrarian.log_serverside:
                logger.debug("getIndex %s" % cmd)

            rowlist = myDB.select(cmd)
            # At his point we want to sort and filter _before_ adding the html as it's much quicker
            # turn the sqlite rowlist into a list of lists
            if len(rowlist):
                for row in rowlist:  # iterate through the sqlite3.Row objects
                    arow = list(row)
                    if lazylibrarian.CONFIG['SORT_SURNAME']:
                        arow[1] = surnameFirst(arow[1])
                    if lazylibrarian.CONFIG['SORT_DEFINITE']:
                        arow[2] = sortDefinite(arow[2])
                    nrow = arow[:4]
                    havebooks = check_int(arow[7], 0)
                    totalbooks = check_int(arow[8], 0)
                    if totalbooks:
                        percent = int((havebooks * 100.0) / totalbooks)
                    else:
                        percent = 0
                    if percent > 100:
                        percent = 100

                    if percent <= 25:
                        css = 'danger'
                    elif percent <= 50:
                        css = 'warning'
                    elif percent <= 75:
                        css = 'info'
                    else:
                        css = 'success'

                    nrow.append(percent)
                    nrow.extend(arow[4:])
                    if lazylibrarian.CONFIG['HTTP_LOOK'] == 'legacy':
                        bar = '<div class="progress-container %s">' % css
                        bar += '<div style="width:%s%%"><span class="progressbar-front-text">' % percent
                        bar += '%s/%s</span></div>' % (havebooks, totalbooks)
                    else:
                        bar = ''
                    nrow.append(bar)
                    rows.append(nrow)  # add each rowlist to the masterlist
                if sSearch:
                    if lazylibrarian.LOGLEVEL & lazylibrarian.log_serverside:
                        logger.debug("filter %s" % sSearch)
                    filtered = [x for x in rows if sSearch.lower() in str(x).lower()]
                else:
                    filtered = rows

                if lazylibrarian.CONFIG['HTTP_LOOK'] == 'legacy':
                    sortcolumn = int(iSortCol_0)
                else:
                    sortcolumn = int(iSortCol_0) - 1

                if lazylibrarian.LOGLEVEL & lazylibrarian.log_serverside:
                    logger.debug("sortcolumn %d" % sortcolumn)

                filtered.sort(key=lambda y: y[sortcolumn], reverse=sSortDir_0 == "desc")

                if iDisplayLength < 0:  # display = all
                    rows = filtered
                else:
                    rows = filtered[iDisplayStart:(iDisplayStart + iDisplayLength)]

            if lazylibrarian.LOGLEVEL & lazylibrarian.log_serverside:
                logger.debug("getIndex returning %s to %s" % (iDisplayStart, iDisplayStart + iDisplayLength))
                logger.debug("getIndex filtered %s from %s:%s" % (len(filtered), len(rowlist), len(rows)))
        except Exception:
            logger.error('Unhandled exception in getIndex: %s' % traceback.format_exc())
            rows = []
            rowlist = []
            filtered = []
        finally:
            mydict = {'iTotalDisplayRecords': len(filtered),
                      'iTotalRecords': len(rowlist),
                      'aaData': rows,
                      }
            return mydict

    @staticmethod
    def label_thread(name=None):
        if name:
            threading.currentThread().name = name
        else:
            threadname = threading.currentThread().name
            if "Thread-" in threadname:
                threading.currentThread().name = "WEBSERVER"

    # USERS ############################################################

    @cherrypy.expose
    def logout(self):
        cherrypy.response.cookie['ll_uid'] = ''
        cherrypy.response.cookie['ll_uid']['expires'] = 0
        # cherrypy.lib.sessions.expire()
        raise cherrypy.HTTPRedirect("home")

    @cherrypy.expose
    def user_register(self):
        self.label_thread("REGISTER")
        return serve_template(templatename="register.html", title="User Registration / Contact form")

    @cherrypy.expose
    def user_update(self, **kwargs):
        if 'password' in kwargs and 'password2' in kwargs and kwargs['password']:
            if kwargs['password'] != kwargs['password2']:
                return "Passwords do not match"
        if kwargs['password']:
            if not pwd_check(kwargs['password']):
                return "Password must be at least 8 digits long\nand not contain spaces"

        changes = ''
        cookie = cherrypy.request.cookie
        if cookie and 'll_uid' in list(cookie.keys()):
            userid = cookie['ll_uid'].value
            myDB = database.DBConnection()
            user = myDB.match('SELECT UserName,Name,Email,Password,BookType from users where UserID=?', (userid,))
            if user:
                if kwargs['username'] and user['UserName'] != kwargs['username']:
                    # if username changed, must not have same username as another user
                    match = myDB.match('SELECT UserName from users where UserName=?', (kwargs['username'],))
                    if match:
                        return "Unable to change username: already exists"
                    else:
                        changes += ' username'
                        myDB.action('UPDATE users SET UserName=? WHERE UserID=?', (kwargs['username'], userid))

                if kwargs['fullname'] and user['Name'] != kwargs['fullname']:
                    changes += ' name'
                    myDB.action('UPDATE users SET Name=? WHERE UserID=?', (kwargs['fullname'], userid))

                if user['Email'] != kwargs['email']:
                    changes += ' email'
                    myDB.action('UPDATE users SET email=? WHERE UserID=?', (kwargs['email'], userid))

                if user['SendTo'] != kwargs['sendto']:
                    changes += ' sendto'
                    myDB.action('UPDATE users SET sendto=? WHERE UserID=?', (kwargs['sendto'], userid))

                if user['BookType'] != kwargs['booktype']:
                    changes += ' BookType'
                    myDB.action('UPDATE users SET BookType=? WHERE UserID=?', (kwargs['booktype'], userid))

                if kwargs['password']:
                    pwd = md5_utf8(kwargs['password'])
                    if pwd != user['password']:
                        changes += ' password'
                        myDB.action('UPDATE users SET password=? WHERE UserID=?', (pwd, userid))

                # only allow admin to change these
                # if kwargs['calread'] and user['CalibreRead'] != kwargs['calread']:
                #     changes += ' CalibreRead'
                #     myDB.action('UPDATE users SET CalibreRead=? WHERE UserID=?', (kwargs['calread'], userid))

                # if kwargs['caltoread'] and user['CalibreToRead'] != kwargs['caltoread']:
                #     changes += ' CalibreToRead'
                #     myDB.action('UPDATE users SET CalibreToRead=? WHERE UserID=?', (kwargs['caltoread'], userid))

            if changes:
                return 'Updated user details:%s' % changes
        return "No changes made"

    @cherrypy.expose
    def user_login(self, **kwargs):
        # anti-phishing
        # block ip address if over 5 failed usernames in a row.
        # dont count attempts older than 24 hrs
        self.label_thread("LOGIN")
        limit = int(time.time()) - 1 * 60 * 60
        lazylibrarian.USER_BLOCKLIST[:] = [x for x in lazylibrarian.USER_BLOCKLIST if x[1] > limit]
        remote_ip = cherrypy.request.remote.ip
        cnt = 0
        for item in lazylibrarian.USER_BLOCKLIST:
            if item[0] == remote_ip:
                cnt += 1
        if cnt >= 5:
            msg = "IP address [%s] is blocked" % remote_ip
            logger.warn(msg)
            return msg

        myDB = database.DBConnection()
        # is it a retry login (failed user/pass)
        cookie = cherrypy.request.cookie
        if not cookie or 'll_uid' not in list(cookie.keys()):
            cherrypy.response.cookie['ll_uid'] = ''
        username = ''
        password = ''
        res = ''
        pwd = ''
        if 'username' in kwargs:
            username = kwargs['username']
        if 'password' in kwargs:
            password = kwargs['password']
        if username and password:
            pwd = md5_utf8(password)
            res = myDB.match('SELECT UserID, Password from users where username=?', (username,))  # type: dict
        if res and pwd == res['Password']:
            cherrypy.response.cookie['ll_uid'] = res['UserID']
            if 'remember' in kwargs:
                cherrypy.response.cookie['ll_uid']['Max-Age'] = '86400'

            # successfully logged in, clear any failed attempts
            lazylibrarian.USER_BLOCKLIST[:] = [x for x in lazylibrarian.USER_BLOCKLIST if not x[0] == username]
            logger.debug("User %s logged in" % username)
            lazylibrarian.SHOWLOGOUT = 1
            return ''
        elif res:
            # anti-phishing. Block user if 3 failed passwords in a row.
            cnt = 0
            for item in lazylibrarian.USER_BLOCKLIST:
                if item[0] == username:
                    cnt += 1
            if cnt >= 2:
                msg = "Too many failed attempts. Reset password or retry after 1 hour"
            else:
                lazylibrarian.USER_BLOCKLIST.append((username, int(time.time())))
                msg = "Wrong password entered. You have %s attempt%s left" % (2 - cnt, plural(2 - cnt))
            logger.warn("Failed login: %s: %s" % (username, lazylibrarian.LOGIN_MSG))
        else:
            # invalid or missing username, or valid user but missing password
            msg = "Invalid user or password."
            lazylibrarian.USER_BLOCKLIST.append((remote_ip, int(time.time())))
        return msg

    @cherrypy.expose
    def user_contact(self, **kwargs):
        self.label_thread('USERCONTACT')
        remote_ip = cherrypy.request.remote.ip
        msg = 'IP: %s\n' % remote_ip
        for item in kwargs:
            if kwargs[item]:
                line = "%s: %s\n" % (item, unaccented(kwargs[item]))
            else:
                line = "%s: \n" % item
            msg += line
        if 'email' in kwargs and kwargs['email']:
            result = notifiers.email_notifier.notify_message('Message from LazyLibrarian User',
                                                             msg, lazylibrarian.CONFIG['ADMIN_EMAIL'])
            if result:
                return "Message sent to admin, you will receive a reply by email"
            else:
                logger.error("Unable to send message to admin: %s" % msg)
                return "Message not sent, please try again later"
        else:
            return "No message sent, no return email address"

    @cherrypy.expose
    def userAdmin(self):
        self.label_thread('USERADMIN')
        myDB = database.DBConnection()
        title = "Manage User Accounts"
        cmd = 'SELECT UserID, UserName, Name, Email, SendTo, Perms, CalibreRead, CalibreToRead, BookType from users'
        users = myDB.select(cmd)
        return serve_template(templatename="users.html", title=title, users=users)

    @cherrypy.expose
    def admin_delete(self, **kwargs):
        myDB = database.DBConnection()
        user = kwargs['user']
        if user:
            match = myDB.match('SELECT Perms from users where UserName=?', (user,))
            if match:
                perm = check_int(match['Perms'], 0)
                if perm & 1:
                    count = 0
                    perms = myDB.select('SELECT Perms from users')
                    for item in perms:
                        val = check_int(item['Perms'], 0)
                        if val & 1:
                            count += 1
                    if count < 2:
                        return "Unable to delete last administrator"
                myDB.action('DELETE from users WHERE UserName=?', (user,))
                return "User %s deleted" % user
            return "User not found"
        return "No user!"

    @cherrypy.expose
    def admin_userdata(self, **kwargs):
        myDB = database.DBConnection()
        match = myDB.match('SELECT * from users where UserName=?', (kwargs['user'],))
        if match:
            res = simplejson.dumps({'email': match['Email'], 'name': match['Name'], 'perms': match['Perms'],
                                    'calread': match['CalibreRead'], 'caltoread': match['CalibreToRead'],
                                    'sendto': match['SendTo'], 'booktype': match['BookType']})
        else:
            res = simplejson.dumps({'email': '', 'name': '', 'perms': '0', 'calread': '', 'caltoread': '',
                                    'sendto': '', 'booktype': ''})
        return res

    @cherrypy.expose
    def admin_users(self, **kwargs):
        myDB = database.DBConnection()
        user = kwargs['user']
        new_user = not user

        if new_user:
            msg = "New user NOT added: "
            if not kwargs['username']:
                return msg + "No username given"
            else:
                # new user must not have same username as an existing one
                match = myDB.match('SELECT UserName from users where UserName=?', (kwargs['username'],))
                if match:
                    return msg + "Username already exists"

            if not kwargs['fullname']:
                return msg + "No fullname given"

            if not kwargs['email']:
                return msg + "No email given"

            if not isValidEmail(kwargs['email']):
                return msg + "Invalid email given"

            perms = check_int(kwargs['perms'], 0)
            if not perms:
                return msg + "No permissions or invalid permissions given"
            if not kwargs['password']:
                return msg + "No password given"

            if perms == lazylibrarian.perm_admin:
                perm_msg = 'ADMIN'
            elif perms == lazylibrarian.perm_friend:
                perm_msg = 'Friend'
            elif perms == lazylibrarian.perm_guest:
                perm_msg = 'Guest'
            else:
                perm_msg = 'Custom %s' % perms

            msg_template = "Your lazylibrarian username is {username}\n"
            msg_template += "Your password is {password}\n"
            msg_template += "You can log in to lazylibrarian and change these to something more memorable\n"
            msg_template += "You have been given {permission} access\n"
            msg = msg_template.replace('{username}', kwargs['username']).replace(
                '{password}', kwargs['password']).replace(
                '{permission}', perm_msg)

            result = notifiers.email_notifier.notify_message('LazyLibrarian New Account', msg, kwargs['email'])

            if result:
                cmd = 'INSERT into users (UserID, UserName, Name, Password, Email, SendTo, Perms)'
                cmd += ' VALUES (?, ?, ?, ?, ?, ?, ?)'
                myDB.action(cmd, (pwd_generator(), kwargs['username'], kwargs['fullname'],
                                  md5_utf8(kwargs['password']), kwargs['email'], kwargs['sendto'], perms))
                msg = "New user added: %s: %s" % (kwargs['username'], perm_msg)
                msg += "<br>Email sent to %s" % kwargs['email']
                cnt = myDB.match("select count(*) as counter from users")
                if cnt['counter'] > 1:
                    lazylibrarian.SHOWLOGOUT = 1
            else:
                msg = "New user NOT added"
                msg += "<br>Failed to send email to %s" % kwargs['email']
            return msg

        else:
            if user != kwargs['username']:
                # if username changed, must not have same username as another user
                match = myDB.match('SELECT UserName from users where UserName=?', (kwargs['username'],))
                if match:
                    return "Username already exists"

            changes = ''
            cmd = 'SELECT UserID,Name,Email,SendTo,Password,Perms,CalibreRead,CalibreToRead,BookType'
            cmd += ' from users where UserName=?'
            details = myDB.match(cmd, (user,))

            if details:
                userid = details['UserID']
                if kwargs['username'] and kwargs['username'] != user:
                    changes += ' username'
                    myDB.action('UPDATE users SET UserName=? WHERE UserID=?', (kwargs['username'], userid))

                if kwargs['fullname'] and details['Name'] != kwargs['fullname']:
                    changes += ' name'
                    myDB.action('UPDATE users SET Name=? WHERE UserID=?', (kwargs['fullname'], userid))

                if details['Email'] != kwargs['email']:
                    if kwargs['email']:
                        if not isValidEmail(kwargs['email']):
                            return "Invalid email given"
                    changes += ' email'
                    myDB.action('UPDATE users SET email=? WHERE UserID=?', (kwargs['email'], userid))

                if details['SendTo'] != kwargs['sendto']:
                    if kwargs['sendto']:
                        if not isValidEmail(kwargs['sendto']):
                            return "Invalid sendto email given"
                    changes += ' sendto'
                    myDB.action('UPDATE users SET sendto=? WHERE UserID=?', (kwargs['sendto'], userid))

                if kwargs['password']:
                    pwd = md5_utf8(kwargs['password'])
                    if pwd != details['Password']:
                        changes += ' password'
                        myDB.action('UPDATE users SET password=? WHERE UserID=?', (pwd, userid))

                if details['CalibreRead'] != kwargs['calread']:
                    changes += ' CalibreRead'
                    myDB.action('UPDATE users SET CalibreRead=? WHERE UserID=?', (kwargs['calread'], userid))

                if details['CalibreToRead'] != kwargs['caltoread']:
                    changes += ' CalibreToRead'
                    myDB.action('UPDATE users SET CalibreToRead=? WHERE UserID=?', (kwargs['caltoread'], userid))

                if details['BookType'] != kwargs['booktype']:
                    changes += ' BookType'
                    myDB.action('UPDATE users SET BookType=? WHERE UserID=?', (kwargs['booktype'], userid))

                if details['Perms'] != kwargs['perms']:
                    oldperm = check_int(details['Perms'], 0)
                    newperm = check_int(kwargs['perms'], 0)
                    if oldperm & 1 and not newperm & 1:
                        count = 0
                        perms = myDB.select('SELECT Perms from users')
                        for item in perms:
                            val = check_int(item['Perms'], 0)
                            if val & 1:
                                count += 1
                        if count < 2:
                            return "Unable to remove last administrator"
                    if oldperm != newperm:
                        changes += ' Perms'
                        myDB.action('UPDATE users SET Perms=? WHERE UserID=?', (kwargs['perms'], userid))

                if changes:
                    return 'Updated user details:%s' % changes
            return "No changes made"

    @cherrypy.expose
    def password_reset(self, **kwargs):
        self.label_thread('PASSWORD_RESET')
        res = {}
        remote_ip = cherrypy.request.remote.ip
        myDB = database.DBConnection()
        if 'username' in kwargs and kwargs['username']:
            logger.debug("Reset password request from %s, IP:%s" % (kwargs['username'], remote_ip))
            res = myDB.match('SELECT UserID,Email from users where username=?', (kwargs['username'],))  # type: dict
            if res:
                if 'email' in kwargs and kwargs['email']:
                    if res['Email']:
                        if kwargs['email'] == res['Email']:
                            msg = ''
                        else:
                            msg = 'Email does not match our records'
                    else:
                        msg = 'No email address registered'
                else:
                    msg = 'No email address supplied'
            else:
                msg = "Unknown username"
        else:
            msg = "Who are you?"

        if res and not msg:
            new_pwd = pwd_generator()
            msg = "Your new password is %s" % new_pwd
            result = notifiers.email_notifier.notify_message('LazyLibrarian New Password', msg, res['Email'])
            if result:
                pwd = md5_utf8(new_pwd)
                myDB.action("UPDATE users SET Password=? WHERE UserID=?", (pwd, res['UserID']))
                return "Password reset, check your email"
            else:
                msg = "Failed to send email to [%s]" % res['Email']
        msg = "Password not reset: %s" % msg
        logger.error("%s IP:%s" % (msg, remote_ip))
        return msg

    @cherrypy.expose
    def generatepwd(self):
        return pwd_generator()

    # SERIES ############################################################
    @cherrypy.expose
    @cherrypy.tools.json_out()
    def getSeries(self, iDisplayStart=0, iDisplayLength=100, iSortCol_0=0, sSortDir_0="desc", sSearch="", **kwargs):
        rows = []
        filtered = []
        rowlist = []
        # noinspection PyBroadException
        try:
            # kwargs is used by datatables to pass params
            iDisplayStart = int(iDisplayStart)
            iDisplayLength = int(iDisplayLength)
            lazylibrarian.CONFIG['DISPLAYLENGTH'] = iDisplayLength

            whichStatus = 'All'
            if kwargs['whichStatus']:
                whichStatus = kwargs['whichStatus']

            AuthorID = ''
            if kwargs['AuthorID']:
                AuthorID = kwargs['AuthorID']

            if not AuthorID or AuthorID == 'None':
                AuthorID = ''

            myDB = database.DBConnection()
            # We pass series.SeriesID twice for datatables as the render function modifies it
            # and we need it in two columns. There is probably a better way...
            cmd = 'SELECT series.SeriesID,AuthorName,SeriesName,series.Status,seriesauthors.AuthorID,series.SeriesID,'
            cmd += 'Have,Total from series,authors,seriesauthors,member'
            cmd += ' where authors.AuthorID=seriesauthors.AuthorID and series.SeriesID=seriesauthors.SeriesID'
            cmd += ' and member.seriesid=series.seriesid and seriesnum=1'
            args = []
            if whichStatus == 'Empty':
                cmd += ' and Have = 0'
            elif whichStatus == 'Partial':
                cmd += ' and Have > 0'
            elif whichStatus == 'Complete':
                cmd += ' and Have > 0 and Have = Total'
            elif whichStatus not in ['All', 'None']:
                cmd += ' and series.Status=?'
                args.append(whichStatus)
            if AuthorID:
                cmd += ' and seriesauthors.AuthorID=?'
                args.append(AuthorID)
            cmd += ' GROUP BY series.seriesID'
            cmd += ' order by AuthorName,SeriesName'

            if lazylibrarian.LOGLEVEL & lazylibrarian.log_serverside:
                logger.debug("getSeries %s: %s" % (cmd, str(args)))

            if args:
                rowlist = myDB.select(cmd, tuple(args))
            else:
                rowlist = myDB.select(cmd)

            # turn the sqlite rowlist into a list of lists
            if len(rowlist):
                for row in rowlist:  # iterate through the sqlite3.Row objects
                    entry = list(row)
                    if lazylibrarian.CONFIG['SORT_SURNAME']:
                        entry[1] = surnameFirst(entry[1])
                    rows.append(entry)  # add the rowlist to the masterlist

                if sSearch:
                    if lazylibrarian.LOGLEVEL & lazylibrarian.log_serverside:
                        logger.debug("filter %s" % sSearch)
                    filtered = [x for x in rows if sSearch.lower() in str(x).lower()]
                else:
                    filtered = rows

                sortcolumn = int(iSortCol_0)
                if lazylibrarian.LOGLEVEL & lazylibrarian.log_serverside:
                    logger.debug("sortcolumn %d" % sortcolumn)

                for row in filtered:
                    have = check_int(row[6], 0)
                    total = check_int(row[7], 0)
                    if total:
                        percent = int((have * 100.0) / total)
                    else:
                        percent = 0

                    if percent > 100:
                        percent = 100

                    row.append(percent)

                    if sortcolumn == 4:  # status
                        sortcolumn = 3
                    elif sortcolumn == 3:  # percent
                        sortcolumn = 8

                if sortcolumn == 8:  # sort on percent,-total
                    if sSortDir_0 == "desc":
                        filtered.sort(key=lambda y: (-int(y[8]), int(y[7])))
                    else:
                        filtered.sort(key=lambda y: (int(y[8]), -int(y[7])))
                else:
                    filtered.sort(key=lambda y: y[sortcolumn], reverse=sSortDir_0 == "desc")

                if iDisplayLength < 0:  # display = all
                    rows = filtered
                else:
                    rows = filtered[iDisplayStart:(iDisplayStart + iDisplayLength)]

            if lazylibrarian.LOGLEVEL & lazylibrarian.log_serverside:
                logger.debug("getSeries returning %s to %s" % (iDisplayStart, iDisplayStart + iDisplayLength))
                logger.debug("getSeries filtered %s from %s:%s" % (len(filtered), len(rowlist), len(rows)))
        except Exception:
            logger.error('Unhandled exception in getSeries: %s' % traceback.format_exc())
            rows = []
            rowlist = []
            filtered = []
        finally:
            mydict = {'iTotalDisplayRecords': len(filtered),
                      'iTotalRecords': len(rowlist),
                      'aaData': rows,
                      }
            return mydict

    @cherrypy.expose
    def series(self, AuthorID=None, whichStatus=None):
        myDB = database.DBConnection()
        title = "Series"
        if AuthorID:
            match = myDB.match('SELECT AuthorName from authors WHERE AuthorID=?', (AuthorID,))
            if match:
                title = "%s Series" % match['AuthorName']
            if '&' in title and '&amp;' not in title:
                title = title.replace('&', '&amp;')

        return serve_template(templatename="series.html", title=title, authorid=AuthorID, series=[],
                              whichStatus=whichStatus)

    @cherrypy.expose
    def seriesMembers(self, seriesid):
        myDB = database.DBConnection()
        cmd = 'SELECT SeriesName,series.SeriesID,AuthorName,seriesauthors.AuthorID'
        cmd += ' from series,authors,seriesauthors'
        cmd += ' where authors.AuthorID=seriesauthors.AuthorID and series.SeriesID=seriesauthors.SeriesID'
        cmd += ' and series.SeriesID=?'
        series = myDB.match(cmd, (seriesid,))
        cmd = 'SELECT member.BookID,BookName,SeriesNum,BookImg,books.Status,AuthorName,authors.AuthorID,'
        cmd += 'BookLink,WorkPage,AudioStatus'
        cmd += ' from member,series,books,authors'
        cmd += ' where series.SeriesID=member.SeriesID and books.BookID=member.BookID'
        cmd += ' and books.AuthorID=authors.AuthorID and (books.Status != "Ignored" or AudioStatus != "Ignored")'
        cmd += ' and series.SeriesID=? order by SeriesName'
        members = myDB.select(cmd, (seriesid,))
        # is it a multi-author series?
        multi = "False"
        authorid = ''
        for item in members:
            if not authorid:
                authorid = item['AuthorID']
            else:
                if not authorid == item['AuthorID']:
                    multi = "True"
                    break

        ToRead = []
        HaveRead = []
        if lazylibrarian.CONFIG['HTTP_LOOK'] != 'legacy' and lazylibrarian.CONFIG['USER_ACCOUNTS']:
            cookie = cherrypy.request.cookie
            if cookie and 'll_uid' in list(cookie.keys()):
                res = myDB.match('SELECT UserName,ToRead,HaveRead,Perms from users where UserID=?',
                                 (cookie['ll_uid'].value,))
                if res:
                    ToRead = getList(res['ToRead'])
                    HaveRead = getList(res['HaveRead'])

        # turn the sqlite rowlist into a list of lists
        rows = []

        if len(members):
            # the masterlist to be filled with the row data
            for row in members:  # iterate through the sqlite3.Row objects
                entry = list(row)
                if entry[0] in ToRead:
                    flag = '&nbsp;<i class="far fa-bookmark"></i>'
                elif entry[0] in HaveRead:
                    flag = '&nbsp;<i class="fas fa-bookmark"></i>'
                else:
                    flag = ''
                newrow = {'BookID': entry[0], 'BookName': entry[1], 'SeriesNum': entry[2], 'BookImg': entry[3],
                          'Status': entry[4], 'AuthorName': entry[5], 'AuthorID': entry[6], 'BookLink': entry[7],
                          'WorkPage': entry[8], 'AudioStatus': entry[9], 'Flag': flag}
                rows.append(newrow)  # add the new dict to the masterlist

        return serve_template(templatename="members.html", title=series['SeriesName'],
                              members=rows, series=series, multi=multi)

    @cherrypy.expose
    def markSeries(self, action=None, **args):
        myDB = database.DBConnection()
        args.pop('book_table_length', None)
        if action:
            for seriesid in args:
                if action in ["Wanted", "Active", "Skipped", "Ignored"]:
                    match = myDB.match('SELECT SeriesName from series WHERE SeriesID=?', (seriesid,))
                    if match:
                        myDB.upsert("series", {'Status': action}, {'SeriesID': seriesid})
                        logger.debug('Status set to "%s" for "%s"' % (action, match['SeriesName']))
                        if action in ['Wanted', 'Active']:
                            threading.Thread(target=getSeriesAuthors, name='SERIESAUTHORS', args=[seriesid]).start()
                elif action in ["Unread", "Read", "ToRead"]:
                    cookie = cherrypy.request.cookie
                    if cookie and 'll_uid' in list(cookie.keys()):
                        res = myDB.match('SELECT ToRead,HaveRead from users where UserID=?',
                                         (cookie['ll_uid'].value,))
                        if res:
                            ToRead = getList(res['ToRead'])
                            HaveRead = getList(res['HaveRead'])
                            members = myDB.select('SELECT bookid from member where seriesid=?', (seriesid,))
                            if members:
                                for item in members:
                                    bookid = item['bookid']
                                    if action == "Unread":
                                        if bookid in ToRead:
                                            ToRead.remove(bookid)
                                        if bookid in HaveRead:
                                            HaveRead.remove(bookid)
                                        logger.debug('Status set to "unread" for "%s"' % bookid)
                                    elif action == "Read":
                                        if bookid in ToRead:
                                            ToRead.remove(bookid)
                                        if bookid not in HaveRead:
                                            HaveRead.append(bookid)
                                        logger.debug('Status set to "read" for "%s"' % bookid)
                                    elif action == "ToRead":
                                        if bookid not in ToRead:
                                            ToRead.append(bookid)
                                        if bookid in HaveRead:
                                            HaveRead.remove(bookid)
                                        logger.debug('Status set to "to read" for "%s"' % bookid)
                                myDB.action('UPDATE users SET ToRead=?,HaveRead=? WHERE UserID=?',
                                            (', '.join(ToRead), ', '.join(HaveRead), cookie['ll_uid'].value))
            if "redirect" in args:
                if not args['redirect'] == 'None':
                    raise cherrypy.HTTPRedirect("series?AuthorID=%s" % args['redirect'])
            raise cherrypy.HTTPRedirect("series")

    # CONFIG ############################################################

    @cherrypy.expose
    def saveFilters(self):
        self.label_thread('WEBSERVER')
        savedir = lazylibrarian.DATADIR
        mags = dump_table('magazines', savedir)
        msg = "%d magazine%s exported" % (mags, plural(mags))
        return msg

    @cherrypy.expose
    def saveUsers(self):
        self.label_thread('WEBSERVER')
        savedir = lazylibrarian.DATADIR
        users = dump_table('users', savedir)
        msg = "%d user%s exported" % (users, plural(users))
        return msg

    @cherrypy.expose
    def loadFilters(self):
        self.label_thread('WEBSERVER')
        savedir = lazylibrarian.DATADIR
        mags = restore_table('magazines', savedir)
        msg = "%d magazine%s imported" % (mags, plural(mags))
        return msg

    @cherrypy.expose
    def loadUsers(self):
        self.label_thread('WEBSERVER')
        savedir = lazylibrarian.DATADIR
        users = restore_table('users', savedir)
        msg = "%d user%s imported" % (users, plural(users))
        return msg

    @cherrypy.expose
    def config(self):
        self.label_thread('CONFIG')
        http_look_dir = os.path.join(lazylibrarian.PROG_DIR, 'data' + os.path.sep + 'interfaces')
        http_look_list = [name for name in os.listdir(http_look_dir)
                          if os.path.isdir(os.path.join(http_look_dir, name))]
        status_list = ['Skipped', 'Wanted', 'Have', 'Ignored']

        myDB = database.DBConnection()
        mags_list = []

        magazines = myDB.select(
                        'SELECT Title,Reject,Regex,DateType,CoverPage from magazines ORDER by Title COLLATE NOCASE')

        if magazines:
            for mag in magazines:
                title = mag['Title']
                regex = mag['Regex']
                if not regex:
                    regex = ""
                reject = mag['Reject']
                if not reject:
                    reject = ""
                datetype = mag['DateType']
                if not datetype:
                    datetype = ""
                coverpage = check_int(mag['CoverPage'], 1)
                mags_list.append({
                    'Title': title,
                    'Reject': reject,
                    'Regex': regex,
                    'DateType': datetype,
                    'CoverPage': coverpage
                })

        # Reset api counters if it's a new day
        if lazylibrarian.NABAPICOUNT != today():
            lazylibrarian.NABAPICOUNT = today()
            for provider in lazylibrarian.NEWZNAB_PROV:
                provider['APICOUNT'] = 0
            for provider in lazylibrarian.TORZNAB_PROV:
                provider['APICOUNT'] = 0

        # Don't pass the whole config, no need to pass the
        # lazylibrarian.globals
        config = {
            "http_look_list": http_look_list,
            "status_list": status_list,
            "magazines_list": mags_list,
            "namevars": nameVars('test'),
            "updated": time.ctime(check_int(lazylibrarian.CONFIG['GIT_UPDATED'], 0))
        }
        return serve_template(templatename="config.html", title="Settings", config=config)

    @cherrypy.expose
    def configUpdate(self, **kwargs):
        # print len(kwargs)
        # for arg in kwargs:
        #    print arg

        myDB = database.DBConnection()
        adminmsg = ''
        if 'user_accounts' in kwargs:
            if kwargs['user_accounts'] and not lazylibrarian.CFG.get('General', 'user_accounts'):
                # we just turned user_accounts on, check it's set up ok
                email = ''
                if 'admin_email' in kwargs and kwargs['admin_email']:
                    email = kwargs['admin_email']
                elif lazylibrarian.CFG.get('General', 'admin_email'):
                    email = lazylibrarian.CFG.get('General', 'admin_email')
                else:
                    adminmsg += 'Please set a contact email so users can make requests<br>'

                if email and not isValidEmail(email):
                    adminmsg += 'Contact email looks invalid, please check<br>'

                if lazylibrarian.CFG.get('General', 'http_user'):
                    adminmsg += 'Please remove WEBSERVER USER as user accounts are active<br>'

                admin = myDB.match('SELECT password from users where name="admin"')
                if admin:
                    if admin['password'] == md5_utf8('admin'):
                        adminmsg += "The default admin user is 'admin' and password is 'admin'<br>"
                        adminmsg += "This is insecure, please change it on Config -> User Admin<br>"

        # first the non-config options
        if 'current_tab' in kwargs:
            lazylibrarian.CURRENT_TAB = kwargs['current_tab']

        interface = lazylibrarian.CFG.get('General', 'http_look')
        # now the config file entries
        for key in list(lazylibrarian.CONFIG_DEFINITIONS.keys()):
            item_type, section, default = lazylibrarian.CONFIG_DEFINITIONS[key]
            if key.lower() in kwargs:
                value = kwargs[key.lower()]
                if item_type == 'bool':
                    if not value or value == 'False' or value == '0':
                        value = 0
                    else:
                        value = 1
                elif item_type == 'int':
                    value = check_int(value, default)
                lazylibrarian.CONFIG[key] = value
            else:
                # no key is returned for strings not available in config html page so leave these unchanged
                if key in lazylibrarian.CONFIG_NONWEB or key in lazylibrarian.CONFIG_GIT:
                    pass
                # default interface doesn't know about other interfaces variables
                elif interface == 'legacy' and key in lazylibrarian.CONFIG_NONDEFAULT:
                    pass
                # default interface doesn't know about download priorities or displaynames
                elif interface == 'legacy' and ('dlpriority' in key.lower() or 'dispname' in key.lower()):
                    pass
                # no key is returned for empty tickboxes...
                elif item_type == 'bool':
                    # print "No entry for bool " + key
                    lazylibrarian.CONFIG[key] = 0
                # or empty string values
                else:
                    # print "No entry for str " + key
                    lazylibrarian.CONFIG[key] = ''

        magazines = myDB.select('SELECT Title,Reject,Regex,DateType,CoverPage from magazines ORDER by upper(Title)')

        if magazines:
            count = 0
            for mag in magazines:
                title = mag['Title']
                reject = mag['Reject']
                regex = mag['Regex']
                datetype = mag['DateType']
                coverpage = check_int(mag['CoverPage'], 1)
                # seems kwargs parameters from cherrypy are sometimes passed as latin-1,
                # can't see how to configure it, so we need to correct it on accented magazine names
                # eg "Elle Quebec" where we might have e-acute stored as unicode
                # e-acute is \xe9 in latin-1  but  \xc3\xa9 in utf-8
                # otherwise the comparison fails, but sometimes accented characters won't
                # fit latin-1 but fit utf-8 how can we tell ???
                if not isinstance(title, text_type):
                    try:
                        title = title.encode('latin-1')
                    except UnicodeEncodeError:
                        try:
                            title = title.encode('utf-8')
                        except UnicodeEncodeError:
                            logger.warn('Unable to convert title [%s]' % repr(title))
                            title = unaccented(title)

                new_reject = kwargs.get('reject_list[%s]' % title, None)
                if not new_reject == reject:
                    count += 1
                    controlValueDict = {'Title': title}
                    newValueDict = {'Reject': new_reject}
                    myDB.upsert("magazines", newValueDict, controlValueDict)
                new_regex = kwargs.get('regex[%s]' % title, None)
                if not new_regex == regex:
                    count += 1
                    controlValueDict = {'Title': title}
                    newValueDict = {'Regex': new_regex}
                    myDB.upsert("magazines", newValueDict, controlValueDict)
                new_datetype = kwargs.get('datetype[%s]' % title, None)
                if not new_datetype == datetype:
                    count += 1
                    controlValueDict = {'Title': title}
                    newValueDict = {'DateType': new_datetype}
                    myDB.upsert("magazines", newValueDict, controlValueDict)
                new_coverpage = check_int(kwargs.get('coverpage[%s]' % title, None), 1)
                if not new_coverpage == coverpage:
                    count += 1
                    controlValueDict = {'Title': title}
                    newValueDict = {'CoverPage': new_coverpage}
                    myDB.upsert("magazines", newValueDict, controlValueDict)
            if count:
                logger.info("Magazine filters updated")

        count = 0
        while count < len(lazylibrarian.NEWZNAB_PROV):
            lazylibrarian.NEWZNAB_PROV[count]['ENABLED'] = bool(kwargs.get(
                'newznab_%i_enabled' % count, False))
            lazylibrarian.NEWZNAB_PROV[count]['HOST'] = kwargs.get(
                'newznab_%i_host' % count, '')
            lazylibrarian.NEWZNAB_PROV[count]['API'] = kwargs.get(
                'newznab_%i_api' % count, '')
            lazylibrarian.NEWZNAB_PROV[count]['GENERALSEARCH'] = kwargs.get(
                'newznab_%i_generalsearch' % count, '')
            lazylibrarian.NEWZNAB_PROV[count]['BOOKSEARCH'] = kwargs.get(
                'newznab_%i_booksearch' % count, '')
            lazylibrarian.NEWZNAB_PROV[count]['MAGSEARCH'] = kwargs.get(
                'newznab_%i_magsearch' % count, '')
            lazylibrarian.NEWZNAB_PROV[count]['AUDIOSEARCH'] = kwargs.get(
                'newznab_%i_audiosearch' % count, '')
            lazylibrarian.NEWZNAB_PROV[count]['BOOKCAT'] = kwargs.get(
                'newznab_%i_bookcat' % count, '')
            lazylibrarian.NEWZNAB_PROV[count]['MAGCAT'] = kwargs.get(
                'newznab_%i_magcat' % count, '')
            lazylibrarian.NEWZNAB_PROV[count]['AUDIOCAT'] = kwargs.get(
                'newznab_%i_audiocat' % count, '')
            lazylibrarian.NEWZNAB_PROV[count]['EXTENDED'] = kwargs.get(
                'newznab_%i_extended' % count, '')
            lazylibrarian.NEWZNAB_PROV[count]['UPDATED'] = kwargs.get(
                'newznab_%i_updated' % count, '')
            lazylibrarian.NEWZNAB_PROV[count]['MANUAL'] = bool(kwargs.get(
                'newznab_%i_manual' % count, False))
            if interface != 'legacy':
                lazylibrarian.NEWZNAB_PROV[count]['APILIMIT'] = check_int(kwargs.get(
                    'newznab_%i_apilimit' % count, 0), 0)
                lazylibrarian.NEWZNAB_PROV[count]['DLPRIORITY'] = check_int(kwargs.get(
                    'newznab_%i_dlpriority' % count, 0), 0)
                lazylibrarian.NEWZNAB_PROV[count]['DLTYPES'] = kwargs.get(
                    'newznab_%i_dltypes' % count, 'E')
                lazylibrarian.NEWZNAB_PROV[count]['DISPNAME'] = kwargs.get(
                    'newznab_%i_dispname' % count, '')
            count += 1

        count = 0
        while count < len(lazylibrarian.TORZNAB_PROV):
            lazylibrarian.TORZNAB_PROV[count]['ENABLED'] = bool(kwargs.get(
                'torznab_%i_enabled' % count, False))
            lazylibrarian.TORZNAB_PROV[count]['HOST'] = kwargs.get(
                'torznab_%i_host' % count, '')
            lazylibrarian.TORZNAB_PROV[count]['API'] = kwargs.get(
                'torznab_%i_api' % count, '')
            lazylibrarian.TORZNAB_PROV[count]['GENERALSEARCH'] = kwargs.get(
                'torznab_%i_generalsearch' % count, '')
            lazylibrarian.TORZNAB_PROV[count]['BOOKSEARCH'] = kwargs.get(
                'torznab_%i_booksearch' % count, '')
            lazylibrarian.TORZNAB_PROV[count]['MAGSEARCH'] = kwargs.get(
                'torznab_%i_magsearch' % count, '')
            lazylibrarian.TORZNAB_PROV[count]['AUDIOSEARCH'] = kwargs.get(
                'torznab_%i_audiosearch' % count, '')
            lazylibrarian.TORZNAB_PROV[count]['BOOKCAT'] = kwargs.get(
                'torznab_%i_bookcat' % count, '')
            lazylibrarian.TORZNAB_PROV[count]['MAGCAT'] = kwargs.get(
                'torznab_%i_magcat' % count, '')
            lazylibrarian.TORZNAB_PROV[count]['AUDIOCAT'] = kwargs.get(
                'torznab_%i_audiocat' % count, '')
            lazylibrarian.TORZNAB_PROV[count]['EXTENDED'] = kwargs.get(
                'torznab_%i_extended' % count, '')
            lazylibrarian.TORZNAB_PROV[count]['UPDATED'] = kwargs.get(
                'torznab_%i_updated' % count, '')
            lazylibrarian.TORZNAB_PROV[count]['MANUAL'] = bool(kwargs.get(
                'torznab_%i_manual' % count, False))
            if interface != 'legacy':
                lazylibrarian.TORZNAB_PROV[count]['APILIMIT'] = check_int(kwargs.get(
                    'torznab_%i_apilimit' % count, 0), 0)
                lazylibrarian.TORZNAB_PROV[count]['DLPRIORITY'] = check_int(kwargs.get(
                    'torznab_%i_dlpriority' % count, 0), 0)
                lazylibrarian.TORZNAB_PROV[count]['DLTYPES'] = kwargs.get(
                    'torznab_%i_dltypes' % count, 'E')
                lazylibrarian.TORZNAB_PROV[count]['DISPNAME'] = kwargs.get(
                    'torznab_%i_dispname' % count, '')
            count += 1

        count = 0
        while count < len(lazylibrarian.RSS_PROV):
            lazylibrarian.RSS_PROV[count]['ENABLED'] = bool(kwargs.get('rss_%i_enabled' % count, False))
            lazylibrarian.RSS_PROV[count]['HOST'] = kwargs.get('rss_%i_host' % count, '')
            if interface != 'legacy':
                lazylibrarian.RSS_PROV[count]['DLPRIORITY'] = check_int(kwargs.get(
                    'rss_%i_dlpriority' % count, 0), 0)
                lazylibrarian.RSS_PROV[count]['DLTYPES'] = kwargs.get(
                    'rss_%i_dltypes' % count, 'E')
                lazylibrarian.RSS_PROV[count]['DISPNAME'] = kwargs.get(
                    'rss_%i_dispname' % count, '')
            count += 1

        lazylibrarian.config_write()
        checkRunningJobs()

        if adminmsg:
            return serve_template(templatename="response.html", prefix="",
                                  title="User Accounts", message=adminmsg, timer=0)

        raise cherrypy.HTTPRedirect("config")

    # SEARCH ############################################################

    @cherrypy.expose
    def search(self, name):
        self.label_thread('SEARCH')
        if not name:
            raise cherrypy.HTTPRedirect("home")

        myDB = database.DBConnection()

        authorids = myDB.select("SELECT AuthorID from authors where status != 'Loading'")
        authorlist = []
        for item in authorids:
            authorlist.append(item['AuthorID'])
        authorids = myDB.select("SELECT AuthorID from authors where status = 'Loading'")
        loadlist = []
        for item in authorids:
            loadlist.append(item['AuthorID'])

        booksearch = myDB.select("SELECT Status,BookID from books")
        booklist = []
        for item in booksearch:
            booklist.append(item['BookID'])

        searchresults = search_for(name)
        return serve_template(templatename="searchresults.html", title='Search Results: "' + name + '"',
                              searchresults=searchresults, authorlist=authorlist, loadlist=loadlist,
                              booklist=booklist, booksearch=booksearch)

    # AUTHOR ############################################################

    @cherrypy.expose
    def markAuthors(self, action=None, redirect=None, **args):
        myDB = database.DBConnection()
        for arg in ['author_table_length', 'ignored']:
            args.pop(arg, None)
        if not redirect:
            redirect = "home"
        if action:
            for authorid in args:
                check = myDB.match("SELECT AuthorName from authors WHERE AuthorID=?", (authorid,))
                if not check:
                    logger.warn('Unable to set Status to "%s" for "%s"' % (action, authorid))
                elif action in ["Active", "Wanted", "Paused", "Ignored"]:
                    myDB.upsert("authors", {'Status': action}, {'AuthorID': authorid})
                    logger.info('Status set to "%s" for "%s"' % (action, check['AuthorName']))
                elif action == "Delete":
                    logger.info("Removing author and books: %s" % check['AuthorName'])
                    books = myDB.select("SELECT BookFile from books WHERE AuthorID=? AND BookFile is not null",
                                        (authorid,))
                    for book in books:
                        if os.path.exists(book['BookFile']):
                            try:
                                rmtree(os.path.dirname(book['BookFile']), ignore_errors=True)
                            except Exception as e:
                                logger.warn('rmtree failed on %s, %s %s' %
                                            (book['BookFile'], type(e).__name__, str(e)))

                    myDB.action('DELETE from authors WHERE AuthorID=?', (authorid,))
                elif action == "Remove":
                    logger.info("Removing author: %s" % check['AuthorName'])
                    myDB.action('DELETE from authors WHERE AuthorID=?', (authorid,))

        raise cherrypy.HTTPRedirect(redirect)

    global lastauthor
    # noinspection PyRedeclaration
    lastauthor = ''

    @cherrypy.expose
    def authorPage(self, AuthorID, BookLang=None, library='eBook', Ignored=False):
        global lastauthor
        myDB = database.DBConnection()
        if Ignored:
            languages = myDB.select(
                "SELECT DISTINCT BookLang from books WHERE AuthorID=? AND Status ='Ignored'", (AuthorID,))
        else:
            languages = myDB.select(
                "SELECT DISTINCT BookLang from books WHERE AuthorID=? AND Status !='Ignored'", (AuthorID,))

        author = myDB.match("SELECT * from authors WHERE AuthorID=?", (AuthorID,))

        types = ['eBook']
        if lazylibrarian.SHOW_AUDIO:
            types.append('AudioBook')

        if not author:
            raise cherrypy.HTTPRedirect("home")

        # if we've changed author, reset to first page of new authors books
        if AuthorID == lastauthor:
            firstpage = 'false'
        else:
            lastauthor = AuthorID
            firstpage = 'true'

        authorname = author['AuthorName']
        if not authorname:  # still loading?
            raise cherrypy.HTTPRedirect("home")

        if PY2:
            authorname = authorname.encode(lazylibrarian.SYS_ENCODING)

        return serve_template(
            templatename="author.html", title=quote_plus(authorname),
            author=author, languages=languages, booklang=BookLang, types=types, library=library, ignored=Ignored,
            showseries=lazylibrarian.SHOW_SERIES, firstpage=firstpage)

    @cherrypy.expose
    def setAuthor(self, AuthorID, status):

        myDB = database.DBConnection()
        authorsearch = myDB.match('SELECT AuthorName from authors WHERE AuthorID=?', (AuthorID,))
        if authorsearch:
            AuthorName = authorsearch['AuthorName']
            logger.info("%s author: %s" % (status, AuthorName))

            controlValueDict = {'AuthorID': AuthorID}
            newValueDict = {'Status': status}
            myDB.upsert("authors", newValueDict, controlValueDict)
            logger.debug(
                'AuthorID [%s]-[%s] %s - redirecting to Author home page' % (AuthorID, AuthorName, status))
            raise cherrypy.HTTPRedirect("authorPage?AuthorID=%s" % AuthorID)
        else:
            logger.debug('pauseAuthor Invalid authorid [%s]' % AuthorID)
            raise cherrypy.HTTPRedirect("home")

    @cherrypy.expose
    def pauseAuthor(self, AuthorID):
        self.setAuthor(AuthorID, 'Paused')

    @cherrypy.expose
    def wantAuthor(self, AuthorID):
        self.setAuthor(AuthorID, 'Wanted')

    @cherrypy.expose
    def resumeAuthor(self, AuthorID):
        self.setAuthor(AuthorID, 'Active')

    @cherrypy.expose
    def ignoreAuthor(self, AuthorID):
        self.setAuthor(AuthorID, 'Ignored')

    @cherrypy.expose
    def removeAuthor(self, AuthorID):
        myDB = database.DBConnection()
        authorsearch = myDB.match('SELECT AuthorName from authors WHERE AuthorID=?', (AuthorID,))
        if authorsearch:  # to stop error if try to remove an author while they are still loading
            AuthorName = authorsearch['AuthorName']
            logger.info("Removing all references to author: %s" % AuthorName)
            myDB.action('DELETE from authors WHERE AuthorID=?', (AuthorID,))
        raise cherrypy.HTTPRedirect("home")

    @cherrypy.expose
    def refreshAuthor(self, AuthorID):
        myDB = database.DBConnection()
        authorsearch = myDB.match('SELECT AuthorName from authors WHERE AuthorID=?', (AuthorID,))
        if authorsearch:  # to stop error if try to refresh an author while they are still loading
            threading.Thread(target=addAuthorToDB, name='REFRESHAUTHOR', args=[None, True, AuthorID]).start()
            raise cherrypy.HTTPRedirect("authorPage?AuthorID=%s" % AuthorID)
        else:
            logger.debug('refreshAuthor Invalid authorid [%s]' % AuthorID)
            raise cherrypy.HTTPRedirect("home")

    @cherrypy.expose
    def followAuthor(self, AuthorID):
        # empty GRfollow is not-yet-used, zero means manually unfollowed so sync leaves it alone
        myDB = database.DBConnection()
        authorsearch = myDB.match('SELECT AuthorName, GRfollow from authors WHERE AuthorID=?', (AuthorID,))
        if authorsearch:
            if authorsearch['GRfollow'] and authorsearch['GRfollow'] != '0':
                logger.warn("Already Following %s" % authorsearch['AuthorName'])
            else:
                msg = grsync.grfollow(AuthorID, True)
                if msg.startswith('Unable'):
                    logger.warn(msg)
                else:
                    logger.info(msg)
                    followid = msg.split("followid=")[1]
                    myDB.action("UPDATE authors SET GRfollow=? WHERE AuthorID=?", (followid, AuthorID))
        else:
            logger.error("Invalid authorid to follow (%s)" % AuthorID)
        raise cherrypy.HTTPRedirect("authorPage?AuthorID=%s" % AuthorID)

    @cherrypy.expose
    def unfollowAuthor(self, AuthorID):
        myDB = database.DBConnection()
        authorsearch = myDB.match('SELECT AuthorName, GRfollow from authors WHERE AuthorID=?', (AuthorID,))
        if authorsearch:
            if not authorsearch['GRfollow'] or authorsearch['GRfollow'] == '0':
                logger.warn("Not Following %s" % authorsearch['AuthorName'])
            else:
                msg = grsync.grfollow(AuthorID, False)
                if msg.startswith('Unable'):
                    logger.warn(msg)
                else:
                    myDB.action("UPDATE authors SET GRfollow='0' WHERE AuthorID=?", (AuthorID,))
                    logger.info(msg)
        else:
            logger.error("Invalid authorid to unfollow (%s)" % AuthorID)
        raise cherrypy.HTTPRedirect("authorPage?AuthorID=%s" % AuthorID)

    @cherrypy.expose
    def libraryScanAuthor(self, AuthorID, **kwargs):
        myDB = database.DBConnection()
        authorsearch = myDB.match('SELECT AuthorName from authors WHERE AuthorID=?', (AuthorID,))
        if authorsearch:  # to stop error if try to refresh an author while they are still loading
            AuthorName = authorsearch['AuthorName']
            library = 'eBook'
            if 'library' in kwargs:
                library = kwargs['library']

            if library == 'AudioBook':
                authordir = safe_unicode(os.path.join(lazylibrarian.DIRECTORY('AudioBook'), AuthorName))
            else:  # if library == 'eBook':
                authordir = safe_unicode(os.path.join(lazylibrarian.DIRECTORY('eBook'), AuthorName))
            if not os.path.isdir(authordir):
                # books might not be in exact same authorname folder due to capitalisation
                # eg Calibre puts books into folder "Eric Van Lustbader", but
                # goodreads told lazylibrarian he's "Eric van Lustbader", note the lowercase 'v'
                # or calibre calls "Neil deGrasse Tyson" "Neil DeGrasse Tyson" with a capital 'D'
                # so convert the name and try again...
                AuthorName = ' '.join(word[0].upper() + word[1:] for word in AuthorName.split())
                if library == 'AudioBook':
                    authordir = safe_unicode(os.path.join(lazylibrarian.DIRECTORY('Audio'), AuthorName))
                else:  # if library == 'eBook':
                    authordir = safe_unicode(os.path.join(lazylibrarian.DIRECTORY('eBook'), AuthorName))
            if not os.path.isdir(authordir):
                # if still not found, see if we have a book by them, and what directory it's in
                if library == 'AudioBook':
                    sourcefile = 'AudioFile'
                else:
                    sourcefile = 'BookFile'
                cmd = 'SELECT %s from books,authors where books.AuthorID = authors.AuthorID' % sourcefile
                cmd += '  and AuthorName=? and %s <> ""' % sourcefile
                anybook = myDB.match(cmd, (AuthorName,))
                if anybook:
                    authordir = safe_unicode(os.path.dirname(os.path.dirname(anybook[sourcefile])))
            if os.path.isdir(authordir):
                remove = bool(lazylibrarian.CONFIG['FULL_SCAN'])
                try:
                    threading.Thread(target=LibraryScan, name='AUTHOR_SCAN',
                                     args=[authordir, library, AuthorID, remove]).start()
                except Exception as e:
                    logger.error('Unable to complete the scan: %s %s' % (type(e).__name__, str(e)))
            else:
                # maybe we don't have any of their books
                logger.warn('Unable to find author directory: %s' % authordir)

            raise cherrypy.HTTPRedirect("authorPage?AuthorID=%s&library=%s" % (AuthorID, library))
        else:
            logger.debug('ScanAuthor Invalid authorid [%s]' % AuthorID)
            raise cherrypy.HTTPRedirect("home")

    @cherrypy.expose
    def addAuthor(self, AuthorName):
        threading.Thread(target=addAuthorNameToDB, name='ADDAUTHOR', args=[AuthorName, False]).start()
        raise cherrypy.HTTPRedirect("home")

    @cherrypy.expose
    def addAuthorID(self, AuthorID):
        threading.Thread(target=addAuthorToDB, name='ADDAUTHOR', args=['', False, AuthorID]).start()
        time.sleep(2)  # so we get some data before going to authorpage
        raise cherrypy.HTTPRedirect("authorPage?AuthorID=%s" % AuthorID)
        # raise cherrypy.HTTPRedirect("home")

    @cherrypy.expose
    def toggleAuth(self):
        if lazylibrarian.IGNORED_AUTHORS:  # show ignored ones, or active ones
            lazylibrarian.IGNORED_AUTHORS = False
        else:
            lazylibrarian.IGNORED_AUTHORS = True
        raise cherrypy.HTTPRedirect("home")

    # BOOKS #############################################################

    @cherrypy.expose
    def booksearch(self, author=None, title=None, bookid=None, action=''):
        self.label_thread('BOOKSEARCH')
        if '_title' in action:
            searchterm = title
        elif '_author' in action:
            searchterm = author
        else:  # if '_full' in action: or legacy interface
            searchterm = '%s %s' % (author, title)
            searchterm = searchterm.strip()

        if action == 'e_full':
            cat = 'book'
        elif action == 'a_full':
            cat = 'audio'
        elif action:
            cat = 'general'
        else:  # legacy interface
            cat = 'book'

        results = searchItem(searchterm, bookid, cat)
        library = 'eBook'
        if action.startswith('a_'):
            library = 'AudioBook'
        return serve_template(templatename="manualsearch.html", title=library + ' Search Results: "' +
                              searchterm + '"', bookid=bookid, results=results, library=library)

    @cherrypy.expose
    def countProviders(self):
        cherrypy.response.headers['Cache-Control'] = "max-age=0,no-cache,no-store"
        count = lazylibrarian.USE_NZB() + lazylibrarian.USE_TOR() + lazylibrarian.USE_RSS() + lazylibrarian.USE_DIRECT()
        return "Searching %s providers, please wait..." % count

    @cherrypy.expose
    def snatchBook(self, bookid=None, mode=None, provider=None, url=None, size=None, library=None):
        logger.debug("snatch bookid %s mode=%s from %s url=[%s]" % (bookid, mode, provider, url))
        myDB = database.DBConnection()
        bookdata = myDB.match('SELECT AuthorID, BookName from books WHERE BookID=?', (bookid,))
        if bookdata:
            size_temp = check_int(size, 1000)  # Need to cater for when this is NONE (Issue 35)
            size = round(float(size_temp) / 1048576, 2)
            controlValueDict = {"NZBurl": url}
            newValueDict = {
                "NZBprov": provider,
                "BookID": bookid,
                "NZBdate": now(),  # when we asked for it
                "NZBsize": size,
                "NZBtitle": bookdata["BookName"],
                "NZBmode": mode,
                "AuxInfo": library,
                "Status": "Snatched"
            }
            myDB.upsert("wanted", newValueDict, controlValueDict)
            AuthorID = bookdata["AuthorID"]
            # bookname = '%s LL.(%s)' % (bookdata["BookName"], bookid)
            if mode == 'direct':
                snatch, res = DirectDownloadMethod(bookid, bookdata["BookName"], url, library)
            elif mode in ["torznab", "torrent", "magnet"]:
                snatch, res = TORDownloadMethod(bookid, bookdata["BookName"], url, library)
            elif mode == 'nzb':
                snatch, res = NZBDownloadMethod(bookid, bookdata["BookName"], url, library)
            else:
                res = 'Unhandled NZBmode [%s] for %s' % (mode, url)
                logger.error(res)
                snatch = False
            if snatch:
                logger.info('Downloading %s %s from %s' % (library, bookdata["BookName"], provider))
                custom_notify_snatch("%s %s" % (bookid, library))
                notify_snatch("%s from %s at %s" % (unaccented(bookdata["BookName"]), provider, now()))
                scheduleJob(action='Start', target='PostProcessor')
            else:
                myDB.action('UPDATE wanted SET status="Failed",DLResult=? WHERE NZBurl=?', (res, url))
            raise cherrypy.HTTPRedirect("authorPage?AuthorID=%s&library=%s" % (AuthorID, library))
        else:
            logger.debug('snatchBook Invalid bookid [%s]' % bookid)
            raise cherrypy.HTTPRedirect("home")

    @cherrypy.expose
    def audio(self, BookLang=None):
        cookie = cherrypy.request.cookie
        if cookie and 'll_uid' in list(cookie.keys()):
            user = cookie['ll_uid'].value
        else:
            user = 0
        myDB = database.DBConnection()
        if not BookLang or BookLang == 'None':
            BookLang = None
        languages = myDB.select(
            'SELECT DISTINCT BookLang from books WHERE AUDIOSTATUS !="Skipped" AND AUDIOSTATUS !="Ignored"')
        return serve_template(templatename="audio.html", title='AudioBooks', books=[],
                              languages=languages, booklang=BookLang, user=user)

    @cherrypy.expose
    def books(self, BookLang=None):
        cookie = cherrypy.request.cookie
        if cookie and 'll_uid' in list(cookie.keys()):
            user = cookie['ll_uid'].value
        else:
            user = 0
        myDB = database.DBConnection()
        if not BookLang or BookLang == 'None':
            BookLang = None
        languages = myDB.select('SELECT DISTINCT BookLang from books WHERE STATUS !="Skipped" AND STATUS !="Ignored"')
        return serve_template(templatename="books.html", title='Books', books=[],
                              languages=languages, booklang=BookLang, user=user)

    @cherrypy.expose
    @cherrypy.tools.json_out()
    def getBooks(self, iDisplayStart=0, iDisplayLength=100, iSortCol_0=0, sSortDir_0="desc", sSearch="", **kwargs):
        # kwargs is used by datatables to pass params
        # for arg in kwargs:
        #     print arg, kwargs[arg]
        rows = []
        filtered = []
        rowlist = []
        # noinspection PyBroadException
        try:
            iDisplayStart = int(iDisplayStart)
            iDisplayLength = int(iDisplayLength)
            lazylibrarian.CONFIG['DISPLAYLENGTH'] = iDisplayLength

            myDB = database.DBConnection()
            ToRead = []
            HaveRead = []
            flagTo = 0
            flagHave = 0
            if lazylibrarian.CONFIG['HTTP_LOOK'] == 'legacy' or not lazylibrarian.CONFIG['USER_ACCOUNTS']:
                perm = lazylibrarian.perm_admin
            else:
                perm = 0
                cookie = cherrypy.request.cookie
                if cookie and 'll_uid' in list(cookie.keys()):
                    res = myDB.match('SELECT UserName,ToRead,HaveRead,Perms from users where UserID=?',
                                     (cookie['ll_uid'].value,))
                    if res:
                        perm = check_int(res['Perms'], 0)
                        ToRead = getList(res['ToRead'])
                        HaveRead = getList(res['HaveRead'])

                        if lazylibrarian.LOGLEVEL & lazylibrarian.log_serverside:
                            logger.debug("getBooks userid %s read %s,%s" % (
                                cookie['ll_uid'].value, len(ToRead), len(HaveRead)))

            # group_concat needs sqlite3 >= 3.5.4, we check version in __init__
            if lazylibrarian.GROUP_CONCAT:
                cmd = 'SELECT bookimg,authorname,bookname,bookrate,bookdate,books.status,books.bookid,booklang,'
                cmd += ' booksub,booklink,workpage,books.authorid,seriesdisplay,booklibrary,audiostatus,audiolibrary,'
                cmd += ' group_concat(series.seriesid || "~" || series.seriesname, "^") as series'
                cmd += ' FROM books, authors'
                cmd += ' LEFT OUTER JOIN member ON (books.BookID = member.BookID)'
                cmd += ' LEFT OUTER JOIN series ON (member.SeriesID = series.SeriesID)'
                cmd += ' WHERE books.AuthorID = authors.AuthorID'
            else:
                cmd = 'SELECT bookimg,authorname,bookname,bookrate,bookdate,books.status,bookid,booklang,'
                cmd += 'booksub,booklink,workpage,books.authorid,seriesdisplay,booklibrary,audiostatus,audiolibrary'
                cmd += ' from books,authors where books.AuthorID = authors.AuthorID'

            library = 'eBook'
            status_type = 'books.status'
            if 'library' in kwargs:
                library = kwargs['library']
            if library == 'AudioBook':
                status_type = 'audiostatus'
            args = []
            if kwargs['source'] == "Manage":
                if kwargs['whichStatus'] == 'ToRead':
                    cmd += ' and books.bookID in (' + ', '.join(ToRead) + ')'
                elif kwargs['whichStatus'] == 'Read':
                    cmd += ' and books.bookID in (' + ', '.join(HaveRead) + ')'
                else:
                    cmd += ' and ' + status_type + '="' + kwargs['whichStatus'] + '"'

            elif kwargs['source'] == "Books":
                cmd += ' and books.STATUS !="Skipped" AND books.STATUS !="Ignored"'
            elif kwargs['source'] == "Audio":
                cmd += ' and AUDIOSTATUS !="Skipped" AND AUDIOSTATUS !="Ignored"'
            elif kwargs['source'] == "Author":
                cmd += ' and books.AuthorID=?'
                args.append(kwargs['AuthorID'])
                if 'ignored' in kwargs and kwargs['ignored'] == "True":
                    cmd += ' and %s="Ignored"' % status_type
                else:
                    cmd += ' and %s != "Ignored"' % status_type

            if kwargs['source'] in ["Books", "Author", "Audio"]:
                # for these we need to check and filter on BookLang if set
                if 'booklang' in kwargs and kwargs['booklang'] != '' and kwargs['booklang'] != 'None':
                    cmd += ' and BOOKLANG=?'
                    args.append(kwargs['booklang'])

            if lazylibrarian.GROUP_CONCAT:
                cmd += ' GROUP BY bookimg, authorname, bookname, bookrate, bookdate, books.status, books.bookid,'
                cmd += ' booklang, booksub, booklink, workpage, books.authorid, seriesdisplay, booklibrary, '
                cmd += ' audiostatus, audiolibrary'

            if lazylibrarian.LOGLEVEL & lazylibrarian.log_serverside:
                logger.debug("getBooks %s: %s" % (cmd, str(args)))
            rowlist = myDB.select(cmd, tuple(args))

            # At his point we want to sort and filter _before_ adding the html as it's much quicker
            # turn the sqlite rowlist into a list of lists
            if len(rowlist):
                for row in rowlist:  # iterate through the sqlite3.Row objects
                    entry = list(row)
                    if lazylibrarian.CONFIG['SORT_SURNAME']:
                        entry[1] = surnameFirst(entry[1])
                    if lazylibrarian.CONFIG['SORT_DEFINITE']:
                        entry[2] = sortDefinite(entry[2])
                    rows.append(entry)  # add each rowlist to the masterlist

                if sSearch:
                    if lazylibrarian.LOGLEVEL & lazylibrarian.log_serverside:
                        logger.debug("filter %s" % sSearch)
                    if library is not None:
                        if library == 'AudioBook':
                            searchFields = ['AuthorName', 'BookName', 'BookDate', 'AudioStatus',
                                            'BookID', 'BookLang', 'BookSub', 'AuthorID', 'SeriesDisplay']
                        else:
                            searchFields = ['AuthorName', 'BookName', 'BookDate', 'Status',
                                            'BookID', 'BookLang', 'BookSub', 'AuthorID', 'SeriesDisplay']
                        filtered = list()
                        sSearch_lower = sSearch.lower()
                        for row in rowlist:
                            _dict = dict(row)
                            for key in searchFields:
                                if _dict[key] and sSearch_lower in _dict[key].lower():
                                    filtered.append(list(row))
                                    break
                    else:
                        filtered = [x for x in rows if sSearch.lower() in str(x).lower()]
                else:
                    filtered = rows

                # table headers and column headers do not match at this point
                sortcolumn = int(iSortCol_0)
                if lazylibrarian.LOGLEVEL & lazylibrarian.log_serverside:
                    logger.debug("sortcolumn %d" % sortcolumn)

                if sortcolumn < 4:  # author, title
                    sortcolumn -= 1
                elif sortcolumn == 4:  # series
                    sortcolumn = 12
                elif sortcolumn == 8:  # status
                    if status_type == 'audiostatus':
                        sortcolumn = 14
                    else:
                        sortcolumn = 5
                elif sortcolumn == 7:  # added
                    if status_type == 'audiostatus':
                        sortcolumn = 15
                    else:
                        sortcolumn = 13
                else:  # rating, date
                    sortcolumn -= 2

                if lazylibrarian.LOGLEVEL & lazylibrarian.log_serverside:
                    logger.debug("final sortcolumn %d" % sortcolumn)

                if sortcolumn in [12, 13, 15]:  # series, date
                    self.natural_sort(filtered, key=lambda y: y[sortcolumn] if y[sortcolumn] is not None else '',
                                      reverse=sSortDir_0 == "desc")
                elif sortcolumn in [2]:  # title
                    filtered.sort(key=lambda y: y[sortcolumn].lower(), reverse=sSortDir_0 == "desc")
                else:
                    filtered.sort(key=lambda y: y[sortcolumn], reverse=sSortDir_0 == "desc")

                if iDisplayLength < 0:  # display = all
                    rows = filtered
                else:
                    rows = filtered[iDisplayStart:(iDisplayStart + iDisplayLength)]

                # now add html to the ones we want to display
                d = []  # the masterlist to be filled with the html data
                for row in rows:
                    worklink = ''
                    sitelink = ''
                    bookrate = int(round(float(row[3])))
                    if bookrate > 5:
                        bookrate = 5

                    if row[10] and len(row[10]) > 4:  # is there a workpage link
                        worklink = '<a href="' + row[10] + '" target="_new"><small><i>LibraryThing</i></small></a>'

                    editpage = '<a href="editBook?bookid=' + row[6] + '" target="_new"><small><i>Manual</i></a>'

                    if 'goodreads' in row[9]:
                        sitelink = '<a href="%s" target="_new"><small><i>GoodReads</i></small></a>' % row[9]
                    elif 'books.google.com' in row[9] or 'market.android.com' in row[9]:
                        sitelink = '<a href="%s" target="_new"><small><i>GoogleBooks</i></small></a>' % row[9]
                    title = row[2]
                    if row[8]:  # is there a sub-title
                        title = '%s<br><small><i>%s</i></small>' % (title, row[8])
                    title = title + '<br>' + sitelink + '&nbsp;' + worklink
                    if perm & lazylibrarian.perm_edit:
                        title = title + '&nbsp;' + editpage

                    if not lazylibrarian.GROUP_CONCAT:
                        row.append('')  # empty string for series links as no group_concat

                    if row[6] in ToRead:
                        flag = '&nbsp;<i class="far fa-bookmark"></i>'
                        flagTo += 1
                    elif row[6] in HaveRead:
                        flag = '&nbsp;<i class="fas fa-bookmark"></i>'
                        flagHave += 1
                    else:
                        flag = ''

                    # Need to pass bookid and status twice as datatables modifies first one
                    if status_type == 'audiostatus':
                        thisrow = [row[6], row[0], row[1], title, row[12], bookrate, row[4], row[14], row[11],
                                   row[6], dateFormat(row[15], lazylibrarian.CONFIG['DATE_FORMAT']),
                                   row[14], row[16], flag]
                        if kwargs['source'] == "Manage":
                            cmd = "SELECT Time,Interval,Count from failedsearch WHERE Bookid=? AND Library='AudioBook'"
                            searches = myDB.match(cmd, (row[6],))
                            if searches:
                                thisrow.append("%s/%s" % (searches['Count'], searches['Interval']))
                                thisrow.append(time.strftime("%d %b %Y", time.localtime(searches['Time'])))
                            else:
                                thisrow.append('0')
                                thisrow.append('')
                        d.append(thisrow)
                    else:
                        thisrow = [row[6], row[0], row[1], title, row[12], bookrate, row[4], row[5], row[11],
                                   row[6], dateFormat(row[13], lazylibrarian.CONFIG['DATE_FORMAT']),
                                   row[5], row[16], flag]
                        if kwargs['source'] == "Manage":
                            cmd = "SELECT Time,Interval,Count from failedsearch WHERE Bookid=? AND Library='eBook'"
                            searches = myDB.match(cmd, (row[6],))
                            if searches:
                                thisrow.append("%s/%s" % (searches['Count'], searches['Interval']))
                                try:
                                    thisrow.append(time.strftime("%d %b %Y", time.localtime(float(searches['Time']))))
                                except (ValueError, TypeError):
                                    thisrow.append('')
                            else:
                                thisrow.append('0')
                                thisrow.append('')
                        d.append(thisrow)
                rows = d

            if lazylibrarian.LOGLEVEL & lazylibrarian.log_serverside:
                logger.debug("getBooks %s returning %s to %s, flagged %s,%s" % (
                    kwargs['source'], iDisplayStart, iDisplayStart + iDisplayLength, flagTo, flagHave))
                logger.debug("getBooks filtered %s from %s:%s" % (len(filtered), len(rowlist), len(rows)))
        except Exception:
            logger.error('Unhandled exception in getBooks: %s' % traceback.format_exc())
            rows = []
            rowlist = []
            filtered = []
        finally:
            mydict = {'iTotalDisplayRecords': len(filtered),
                      'iTotalRecords': len(rowlist),
                      'aaData': rows,
                      }
            return mydict

    @staticmethod
    def natural_sort(lst, key=lambda s: s, reverse=False):
        """
        Sort the list into natural alphanumeric order.
        """

        # noinspection PyShadowingNames
        def get_alphanum_key_func(key):
            convert = lambda text: int(text) if text and text.isdigit() else text
            return lambda s: [convert(c) for c in re.split('([0-9]+)', key(s))]

        sort_key = get_alphanum_key_func(key)
        lst.sort(key=sort_key, reverse=reverse)

    @cherrypy.expose
    def addBook(self, bookid=None):
        myDB = database.DBConnection()
        AuthorID = ""
        match = myDB.match('SELECT AuthorID from books WHERE BookID=?', (bookid,))
        if match:
            myDB.upsert("books", {'Status': 'Wanted'}, {'BookID': bookid})
            AuthorID = match['AuthorID']
            update_totals(AuthorID)
        else:
            if lazylibrarian.CONFIG['BOOK_API'] == "GoogleBooks":
                GB = GoogleBooks(bookid)
                t = threading.Thread(target=GB.find_book, name='GB-BOOK', args=[bookid, "Wanted"])
                t.start()
            else:  # lazylibrarian.CONFIG['BOOK_API'] == "GoodReads":
                GR = GoodReads(bookid)
                t = threading.Thread(target=GR.find_book, name='GR-BOOK', args=[bookid, "Wanted"])
                t.start()
            t.join(timeout=10)  # 10 s to add book before redirect
        if lazylibrarian.CONFIG['IMP_AUTOSEARCH']:
            books = [{"bookid": bookid}]
            self.startBookSearch(books)

        if AuthorID:
            raise cherrypy.HTTPRedirect("authorPage?AuthorID=%s" % AuthorID)
        else:
            raise cherrypy.HTTPRedirect("books")

    @cherrypy.expose
    def startBookSearch(self, books=None, library=None):
        if books:
            if lazylibrarian.USE_NZB() or lazylibrarian.USE_TOR() \
                    or lazylibrarian.USE_RSS() or lazylibrarian.USE_DIRECT():
                threading.Thread(target=search_book, name='SEARCHBOOK', args=[books, library]).start()
                booktype = library
                if not booktype:
                    booktype = 'book'  # all types
                logger.debug("Searching for %s with id: %s" % (booktype, books[0]["bookid"]))
            else:
                logger.warn("Not searching for book, no search methods set, check config.")
        else:
            logger.debug("BookSearch called with no books")

    @cherrypy.expose
    def searchForBook(self, bookid=None, library=None):
        myDB = database.DBConnection()
        AuthorID = ''
        bookdata = myDB.match('SELECT AuthorID from books WHERE BookID=?', (bookid,))
        if bookdata:
            AuthorID = bookdata["AuthorID"]

            # start searchthreads
            books = [{"bookid": bookid}]
            self.startBookSearch(books, library=library)

        if AuthorID:
            raise cherrypy.HTTPRedirect("authorPage?AuthorID=%s" % AuthorID)
        else:
            raise cherrypy.HTTPRedirect("books")

    @cherrypy.expose
    def requestBook(self, **kwargs):
        self.label_thread('REQUEST_BOOK')
        prefix = ''
        title = 'Request Error'
        cookie = cherrypy.request.cookie
        if cookie and 'll_uid' in list(cookie.keys()):
            myDB = database.DBConnection()
            res = myDB.match('SELECT Name,UserName,UserID,Email from users where UserID=?', (cookie['ll_uid'].value,))
            if res:
                cmd = 'SELECT BookFile,AudioFile,AuthorName,BookName from books,authors WHERE BookID=?'
                cmd += ' and books.AuthorID = authors.AuthorID'
                bookdata = myDB.match(cmd, (kwargs['bookid'],))
                kwargs.update(bookdata)
                kwargs.update(res)
                kwargs.update({'message': 'Request to Download'})

                remote_ip = cherrypy.request.remote.ip
                msg = 'IP: %s\n' % remote_ip
                for item in kwargs:
                    if kwargs[item]:
                        line = "%s: %s\n" % (item, unaccented(kwargs[item]))
                    else:
                        line = "%s: \n" % item
                    msg += line
                if 'library' in kwargs and kwargs['library']:
                    booktype = kwargs['library']
                else:
                    booktype = 'book'

                title = "%s: %s" % (booktype, bookdata['BookName'])

                if 'email' in kwargs and kwargs['email']:
                    result = notifiers.email_notifier.notify_message('Request from LazyLibrarian User',
                                                                     msg, lazylibrarian.CONFIG['ADMIN_EMAIL'])
                    if result:
                        prefix = "Message sent"
                        msg = "You will receive a reply by email"
                    else:
                        logger.error("Unable to send message to: %s" % msg)
                        prefix = "Message not sent"
                        msg = "Please try again later"
                else:
                    prefix = "Unable to send message"
                    msg = "No email address supplied"
            else:
                msg = "Unknown user"
        else:
            msg = "Nobody logged in?"

        if prefix == "Message sent":
            timer = 5
        else:
            timer = 0
        return serve_template(templatename="response.html", prefix=prefix,
                              title=title, message=msg, timer=timer)

    @cherrypy.expose
    def serveBook(self, feedid=None):
        logger.debug("Serve Book [%s]" % feedid)
        return self.serveItem(feedid, "book")

    @cherrypy.expose
    def serveAudio(self, feedid=None):
        logger.debug("Serve Audio [%s]" % feedid)
        return self.serveItem(feedid, "audio")

    @cherrypy.expose
    def serveIssue(self, feedid=None):
        logger.debug("Serve Issue [%s]" % feedid)
        return self.serveItem(feedid, "issue")

    @cherrypy.expose
    def serveItem(self, feedid, ftype):
        userid = feedid[:10]
        itemid = feedid[10:]
        if len(userid) != 10:
            logger.debug("Invalid userID [%s]" % userid)
            return

        myDB = database.DBConnection()
        res = myDB.match('SELECT UserName,Perms,BookType from users where UserID=?', (userid,))
        if res:
            perm = check_int(res['Perms'], 0)
            preftype = res['BookType']
        else:
            logger.debug("Invalid userID [%s]" % userid)
            return

        if not perm & lazylibrarian.perm_download:
            logger.debug("Insufficient permissions for userID [%s]" % userid)
            return

        if ftype == 'audio':
            res = myDB.match('SELECT AudioFile,BookName from books WHERE BookID=?', (itemid,))
            if res:
                basefile = res['AudioFile']
                # zip up all the audiobook parts
                if basefile and os.path.isfile(basefile):
                    target = zipAudio(os.path.dirname(basefile), res['BookName'])
                    return self.send_file(target, name=res['BookName'] + '.zip')

        basefile = None
        if ftype == 'book':
            res = myDB.match('SELECT BookFile from books WHERE BookID=?', (itemid,))
            if res:
                basefile = res['BookFile']
                basename, extn = os.path.splitext(basefile)
                types = []
                for item in getList(lazylibrarian.CONFIG['EBOOK_TYPE']):
                    target = basename + '.' + item
                    if os.path.isfile(target):
                        types.append(item)

                # serve user preferred type if available, or system preferred type
                if preftype and preftype in types:
                    basefile = basename + '.' + preftype
                else:
                    basefile = basename + '.' + types[0]

        elif ftype == 'issue':
            res = myDB.match('SELECT IssueFile from issues WHERE IssueID=?', (itemid,))
            if res:
                basefile = res['IssueFile']

        if basefile and os.path.isfile(basefile):
            logger.debug('Opening %s %s' % (ftype, basefile))
            return self.send_file(basefile)

        else:
            logger.warn("No file found for %s %s" % (ftype, itemid))

    @cherrypy.expose
    def openBook(self, bookid=None, library=None, redirect=None, booktype=None):
        self.label_thread('OPEN_BOOK')
        # we need to check the user priveleges and see if they can download the book
        myDB = database.DBConnection()
        if lazylibrarian.CONFIG['HTTP_LOOK'] == 'legacy' or not lazylibrarian.CONFIG['USER_ACCOUNTS']:
            perm = lazylibrarian.perm_admin
            preftype = ''
        else:
            perm = 0
            preftype = ''
            cookie = cherrypy.request.cookie
            if cookie and 'll_uid' in list(cookie.keys()):
                res = myDB.match('SELECT UserName,Perms,BookType from users where UserID=?',
                                 (cookie['ll_uid'].value,))
                if res:
                    perm = check_int(res['Perms'], 0)
                    preftype = res['BookType']

        if booktype is not None:
            preftype = booktype

        cmd = 'SELECT BookFile,AudioFile,AuthorName,BookName from books,authors WHERE BookID=?'
        cmd += ' and books.AuthorID = authors.AuthorID'
        bookdata = myDB.match(cmd, (bookid,))
        if not bookdata:
            logger.warn('Missing bookid: %s' % bookid)
        else:
            if perm & lazylibrarian.perm_download:
                authorName = bookdata["AuthorName"]
                bookName = bookdata["BookName"]
                if library == 'AudioBook':
                    bookfile = bookdata["AudioFile"]
                    if bookfile and os.path.isfile(bookfile):
                        parentdir = os.path.dirname(bookfile)
                        index = os.path.join(parentdir, 'playlist.ll')
                        if os.path.isfile(index):
                            if booktype == 'zip':
                                zipfile = zipAudio(parentdir, bookName)
                                logger.debug('Opening %s %s' % (library, zipfile))
                                return self.send_file(zipfile, name="Audiobook zip of %s" % bookName)
                            idx = check_int(booktype, 0)
                            if idx:
                                with open(index, 'r') as f:
                                    part = f.read().splitlines()[idx - 1]
                                bookfile = os.path.join(parentdir, part)
                                logger.debug('Opening %s %s' % (library, bookfile))
                                return self.send_file(bookfile, name="Audiobook part %s of %s" % (idx, bookName))
                            # noinspection PyUnusedLocal
                            cnt = sum(1 for line in open(index))
                            if cnt <= 1:
                                logger.debug('Opening %s %s' % (library, bookfile))
                                return self.send_file(bookfile, name="Audiobook %s" % bookName)
                            else:
                                msg = "Please select which part to download"
                                item = 1
                                partlist = ''
                                while item <= cnt:
                                    if partlist:
                                        partlist += ' '
                                    partlist += str(item)
                                    item += 1
                                    partlist += ' zip'
                                safetitle = bookName.replace('&', '&amp;').replace("'", "")

                            return serve_template(templatename="choosetype.html", prefix="AudioBook",
                                                  title=safetitle, pop_message=msg,
                                                  pop_types=partlist, bookid=bookid,
                                                  valid=getList(partlist.replace(' ', ',')))
                        else:
                            logger.debug('Opening %s %s' % (library, bookfile))
                            return self.send_file(bookfile, name="Audiobook %s" % bookName)
                else:
                    library = 'eBook'
                    bookfile = bookdata["BookFile"]
                    if bookfile and os.path.isfile(bookfile):
                        basename, extn = os.path.splitext(bookfile)
                        types = []
                        for item in getList(lazylibrarian.CONFIG['EBOOK_TYPE']):
                            target = basename + '.' + item
                            if os.path.isfile(target):
                                types.append(item)

                        if preftype:
                            if preftype in types:
                                bookfile = basename + '.' + preftype
                            else:
                                msg = "%s<br> Not available as %s, only " % (bookName, preftype)
                                typestr = ''
                                for item in types:
                                    if typestr:
                                        typestr += ' '
                                    typestr += item
                                msg += typestr
                                return serve_template(templatename="choosetype.html", prefix="",
                                                      title="Not Available", pop_message=msg,
                                                      pop_types=typestr, bookid=bookid,
                                                      valid=getList(lazylibrarian.CONFIG['EBOOK_TYPE']))
                        elif len(types) > 1:
                            msg = "Please select format to download"
                            typestr = ''
                            for item in types:
                                if typestr:
                                    typestr += ' '
                                typestr += item
                            return serve_template(templatename="choosetype.html", prefix="",
                                                  title="Choose Type", pop_message=msg,
                                                  pop_types=typestr, bookid=bookid,
                                                  valid=getList(lazylibrarian.CONFIG['EBOOK_TYPE']))

                        logger.debug('Opening %s %s' % (library, bookfile))
                        return self.send_file(bookfile, name="eBook %s" % bookName)

                logger.info('Missing %s %s, %s [%s]' % (library, authorName, bookName, bookfile))
            else:
                return self.requestBook(library=library, bookid=bookid, redirect=redirect)

    @cherrypy.expose
    def editAuthor(self, authorid=None):
        self.label_thread('EDIT_AUTHOR')
        myDB = database.DBConnection()

        data = myDB.match('SELECT * from authors WHERE AuthorID=?', (authorid,))
        if data:
            return serve_template(templatename="editauthor.html", title="Edit Author", config=data)
        else:
            logger.info('Missing author %s:' % authorid)

    # noinspection PyUnusedLocal
    # kwargs needed for passing utf8 hidden input
    @cherrypy.expose
    def authorUpdate(self, authorid='', authorname='', authorborn='', authordeath='', authorimg='',
                     manual='0', **kwargs):
        myDB = database.DBConnection()
        if authorid:
            authdata = myDB.match('SELECT * from authors WHERE AuthorID=?', (authorid,))
            if authdata:
                edited = ""
                if not authorborn or authorborn == 'None':
                    authorborn = None
                if not authordeath or authordeath == 'None':
                    authordeath = None
                if authorimg == 'None':
                    authorimg = ''
                manual = bool(check_int(manual, 0))

                if not (authdata["AuthorBorn"] == authorborn):
                    edited += "Born "
                if not (authdata["AuthorDeath"] == authordeath):
                    edited += "Died "
                if authorimg and (authdata["AuthorImg"] != authorimg):
                    edited += "Image "
                if not (bool(check_int(authdata["Manual"], 0)) == manual):
                    edited += "Manual "

                if not (authdata["AuthorName"] == authorname):
                    match = myDB.match('SELECT AuthorName from authors where AuthorName=?', (authorname,))
                    if match:
                        logger.debug("Unable to rename, new author name %s already exists" % authorname)
                        authorname = authdata["AuthorName"]
                    else:
                        edited += "Name "

                if edited:
                    # Check dates in format yyyy/mm/dd, or None to clear date
                    # Leave unchanged if fails datecheck
                    if authorborn is not None:
                        ab = authorborn
                        authorborn = authdata["AuthorBorn"]  # assume fail, leave unchanged
                        if ab:
                            rejected = True
                            if len(ab) == 10:
                                try:
                                    _ = datetime.date(int(ab[:4]), int(ab[5:7]), int(ab[8:]))
                                    authorborn = ab
                                    rejected = False
                                except ValueError:
                                    authorborn = authdata["AuthorBorn"]
                            if rejected:
                                logger.warn("Author Born date [%s] rejected" % ab)
                                edited = edited.replace('Born ', '')

                    if authordeath is not None:
                        ab = authordeath
                        authordeath = authdata["AuthorDeath"]  # assume fail, leave unchanged
                        if ab:
                            rejected = True
                            if len(ab) == 10:
                                try:
                                    _ = datetime.date(int(ab[:4]), int(ab[5:7]), int(ab[8:]))
                                    authordeath = ab
                                    rejected = False
                                except ValueError:
                                    authordeath = authdata["AuthorDeath"]
                            if rejected:
                                logger.warn("Author Died date [%s] rejected" % ab)
                                edited = edited.replace('Died ', '')

                    if not authorimg:
                        authorimg = authdata["AuthorImg"]
                    else:
                        if authorimg == 'none':
                            authorimg = os.path.join(lazylibrarian.PROG_DIR, 'data', 'images', 'nophoto.png')

                        rejected = True
                        # Cache file image
                        if os.path.isfile(authorimg):
                            extn = os.path.splitext(authorimg)[1].lower()
                            if extn and extn in ['.jpg', '.jpeg', '.png']:
                                destfile = os.path.join(lazylibrarian.CACHEDIR, 'author', authorid + '.jpg')
                                try:
                                    copyfile(authorimg, destfile)
                                    setperm(destfile)
                                    authorimg = 'cache/author/' + authorid + '.jpg'
                                    rejected = False
                                except Exception as why:
                                    logger.warn("Failed to copy file %s, %s %s" %
                                                (authorimg, type(why).__name__, str(why)))

                        if authorimg.startswith('http'):
                            # cache image from url
                            extn = os.path.splitext(authorimg)[1].lower()
                            if extn and extn in ['.jpg', '.jpeg', '.png']:
                                authorimg, success, _ = cache_img("author", authorid, authorimg)
                                if success:
                                    rejected = False

                        if rejected:
                            logger.warn("Author Image [%s] rejected" % authorimg)
                            authorimg = authdata["AuthorImg"]
                            edited = edited.replace('Image ', '')

                    controlValueDict = {'AuthorID': authorid}
                    newValueDict = {
                        'AuthorName': authorname,
                        'AuthorBorn': authorborn,
                        'AuthorDeath': authordeath,
                        'AuthorImg': authorimg,
                        'Manual': bool(manual)
                    }
                    myDB.upsert("authors", newValueDict, controlValueDict)
                    logger.info('Updated [ %s] for %s' % (edited, authorname))

                else:
                    logger.debug('Author [%s] has not been changed' % authorname)

            raise cherrypy.HTTPRedirect("authorPage?AuthorID=%s" % authorid)
        else:
            raise cherrypy.HTTPRedirect("authors")

    @cherrypy.expose
    def editBook(self, bookid=None):
        cherrypy.response.headers['Cache-Control'] = "max-age=0,no-cache,no-store"
        self.label_thread('EDIT_BOOK')
        myDB = database.DBConnection()
        authors = myDB.select(
            "SELECT AuthorName from authors WHERE Status !='Ignored' ORDER by AuthorName COLLATE NOCASE")
        cmd = 'SELECT BookName,BookID,BookSub,BookGenre,BookLang,books.Manual,AuthorName,books.AuthorID,BookDate '
        cmd += 'from books,authors WHERE books.AuthorID = authors.AuthorID and BookID=?'
        bookdata = myDB.match(cmd, (bookid,))
        cmd = 'SELECT SeriesName, SeriesNum from member,series '
        cmd += 'where series.SeriesID=member.SeriesID and BookID=?'
        seriesdict = myDB.select(cmd, (bookid,))
        if bookdata:
            covers = []
            for source in ['current', 'cover', 'goodreads', 'librarything', 'whatwork',
                           'openlibrary', 'googleisbn', 'googleimage']:
                cover, _ = getBookCover(bookid, source)
                if cover:
                    covers.append([source, cover])

            return serve_template(templatename="editbook.html", title="Edit Book",
                                  config=bookdata, seriesdict=seriesdict, authors=authors, covers=covers)
        else:
            logger.info('Missing book %s' % bookid)

    @cherrypy.expose
    def bookUpdate(self, bookname='', bookid='', booksub='', bookgenre='', booklang='', bookdate='',
                   manual='0', authorname='', cover='', newid='', **kwargs):
        cherrypy.response.headers['Cache-Control'] = "max-age=0,no-cache,no-store"
        myDB = database.DBConnection()

        if bookid:
            cmd = 'SELECT BookName,BookSub,BookGenre,BookLang,BookImg,BookDate,books.Manual,AuthorName,books.AuthorID '
            cmd += ' from books,authors WHERE books.AuthorID = authors.AuthorID and BookID=?'
            bookdata = myDB.match(cmd, (bookid,))
            if bookdata:
                edited = ''
                moved = False
                if bookgenre == 'None':
                    bookgenre = ''
                manual = bool(check_int(manual, 0))

                if newid and not (bookid == newid):
                    cmd = "SELECT BookName,Authorname from books,authors "
                    cmd += "WHERE books.AuthorID = authors.AuthorID and BookID=?"
                    match = myDB.match(cmd, (newid,))
                    if match:
                        logger.warn("Cannot change bookid to %s, in use by %s/%s" %
                                    (newid, match['BookName'], match['AuthorName']))
                    else:
                        logger.warn("Updating bookid is not supported yet")
                        # edited += "BookID "
                if not (bookdata["BookName"] == bookname):
                    edited += "Title "
                if not (bookdata["BookSub"] == booksub):
                    edited += "Subtitle "
                if not (bookdata["BookGenre"] == bookgenre):
                    edited += "Genre "
                if not (bookdata["BookLang"] == booklang):
                    edited += "Language "
                if not (bookdata["BookDate"] == bookdate):
                    if bookdate == '0000':
                        edited += "Date "
                    else:
                        # googlebooks sometimes gives yyyy, sometimes yyyy-mm, sometimes yyyy-mm-dd
                        if len(bookdate) == 4:
                            y = check_year(bookdate)
                        elif len(bookdate) in [7, 10]:
                            y = check_year(bookdate[:4])
                            if y and len(bookdate) == 7:
                                try:
                                    _ = datetime.date(int(bookdate[:4]), int(bookdate[5:7]), 1)
                                except ValueError:
                                    y = 0
                            elif y and len(bookdate) == 10:
                                try:
                                    _ = datetime.date(int(bookdate[:4]), int(bookdate[5:7]), int(bookdate[8:]))
                                except ValueError:
                                    y = 0
                        else:
                            y = 0
                        if y:
                            edited += "Date "
                        else:
                            bookdate = bookdata["BookDate"]
                if not (bool(check_int(bookdata["Manual"], 0)) == manual):
                    edited += "Manual "
                if not (bookdata["AuthorName"] == authorname):
                    moved = True

                covertype = ''
                if cover == 'librarything':
                    covertype = '_lt'
                elif cover == 'whatwork':
                    covertype = '_ww'
                elif cover == 'goodreads':
                    covertype = '_gr'
                elif cover == 'openlibrary':
                    covertype = '_ol'
                elif cover == 'googleisbn':
                    covertype = '_gi'
                elif cover == 'googleimage':
                    covertype = '_gb'

                if covertype:
                    cachedir = lazylibrarian.CACHEDIR
                    coverlink = 'cache/book/' + bookid + '.jpg'
                    coverfile = os.path.join(cachedir, "book", bookid + '.jpg')
                    newcoverfile = os.path.join(cachedir, "book", bookid + covertype + '.jpg')
                    if os.path.exists(newcoverfile):
                        copyfile(newcoverfile, coverfile)
                    edited += 'Cover '
                else:
                    coverlink = bookdata['BookImg']

                if edited:
                    controlValueDict = {'BookID': bookid}
                    newValueDict = {
                        'BookName': bookname,
                        'BookSub': booksub,
                        'BookGenre': bookgenre,
                        'BookLang': booklang,
                        'BookDate': bookdate,
                        'BookImg': coverlink,
                        'Manual': bool(manual)
                    }
                    myDB.upsert("books", newValueDict, controlValueDict)

                cmd = 'SELECT SeriesName, SeriesNum, series.SeriesID from member,series '
                cmd += 'where series.SeriesID=member.SeriesID and BookID=?'
                old_series = myDB.select(cmd, (bookid,))
                old_list = []
                new_list = []
                dict_counter = 0
                while "series[%s][name]" % dict_counter in kwargs:
                    s_name = kwargs["series[%s][name]" % dict_counter]
                    s_name = cleanName(unaccented(s_name), '&/')
                    s_num = kwargs["series[%s][number]" % dict_counter]
                    match = myDB.match('SELECT SeriesID from series WHERE SeriesName=?', (s_name,))
                    if match:
                        new_list.append([match['SeriesID'], s_num, s_name])
                    else:
                        new_list.append(['', s_num, s_name])
                    dict_counter += 1
                if 'series[new][name]' in kwargs and 'series[new][number]' in kwargs:
                    if kwargs['series[new][name]']:
                        s_name = kwargs["series[new][name]"]
                        s_name = cleanName(unaccented(s_name), '&/')
                        s_num = kwargs['series[new][number]']
                        new_list.append(['', s_num, s_name])
                for item in old_series:
                    old_list.append([item['SeriesID'], item['SeriesNum'], item['SeriesName']])

                series_changed = False
                for item in old_list:
                    if item[1:] not in [i[1:] for i in new_list]:
                        series_changed = True
                for item in new_list:
                    if item[1:] not in [i[1:] for i in old_list]:
                        series_changed = True
                if series_changed:
                    setSeries(new_list, bookid)
                    deleteEmptySeries()
                    edited += "Series "

                if edited:
                    logger.info('Updated [ %s] for %s' % (edited, bookname))
                else:
                    logger.debug('Book [%s] has not been changed' % bookname)

                if moved:
                    authordata = myDB.match('SELECT AuthorID from authors WHERE AuthorName=?', (authorname,))
                    if authordata:
                        controlValueDict = {'BookID': bookid}
                        newValueDict = {'AuthorID': authordata['AuthorID']}
                        myDB.upsert("books", newValueDict, controlValueDict)
                        update_totals(bookdata["AuthorID"])  # we moved from here
                        update_totals(authordata['AuthorID'])  # to here

                    logger.info('Book [%s] has been moved' % bookname)
                else:
                    logger.debug('Book [%s] has not been moved' % bookname)
                # if edited or moved:

                raise cherrypy.HTTPRedirect("editBook?bookid=%s" % bookid)

        raise cherrypy.HTTPRedirect("books")

    @cherrypy.expose
    def markBooks(self, AuthorID=None, seriesid=None, action=None, redirect=None, **args):
        if 'library' in args:
            library = args['library']
        else:
            library = 'eBook'
            if redirect == 'audio':
                library = 'AudioBook'

        if 'marktype' in args:
            library = args['marktype']

        for arg in ['book_table_length', 'ignored', 'library', 'booklang']:
            args.pop(arg, None)

        myDB = database.DBConnection()
        if not redirect:
            redirect = "books"
        check_totals = []
        if redirect == 'author':
            check_totals = [AuthorID]
        if action:
            for bookid in args:
                if action in ["Unread", "Read", "ToRead"]:
                    cookie = cherrypy.request.cookie
                    if cookie and 'll_uid' in list(cookie.keys()):
                        res = myDB.match('SELECT ToRead,HaveRead from users where UserID=?',
                                         (cookie['ll_uid'].value,))
                        if res:
                            ToRead = getList(res['ToRead'])
                            HaveRead = getList(res['HaveRead'])
                            if action == "Unread":
                                if bookid in ToRead:
                                    ToRead.remove(bookid)
                                if bookid in HaveRead:
                                    HaveRead.remove(bookid)
                                logger.debug('Status set to "unread" for "%s"' % bookid)
                            elif action == "Read":
                                if bookid in ToRead:
                                    ToRead.remove(bookid)
                                if bookid not in HaveRead:
                                    HaveRead.append(bookid)
                                logger.debug('Status set to "read" for "%s"' % bookid)
                            elif action == "ToRead":
                                if bookid not in ToRead:
                                    ToRead.append(bookid)
                                if bookid in HaveRead:
                                    HaveRead.remove(bookid)
                                logger.debug('Status set to "to read" for "%s"' % bookid)

                            ToRead = list(set(ToRead))
                            HaveRead = list(set(HaveRead))
                            myDB.action('UPDATE users SET ToRead=?,HaveRead=? WHERE UserID=?',
                                        (', '.join(ToRead), ', '.join(HaveRead), cookie['ll_uid'].value))

                elif action in ["Wanted", "Have", "Ignored", "Skipped"]:
                    bookdata = myDB.match('SELECT AuthorID,BookName from books WHERE BookID=?', (bookid,))
                    if bookdata:
                        authorid = bookdata['AuthorID']
                        bookname = bookdata['BookName']
                        if authorid not in check_totals:
                            check_totals.append(authorid)
                        if 'eBook' in library:
                            myDB.upsert("books", {'Status': action}, {'BookID': bookid})
                            logger.debug('Status set to "%s" for "%s"' % (action, bookname))
                        if 'Audio' in library:
                            myDB.upsert("books", {'AudioStatus': action}, {'BookID': bookid})
                            logger.debug('AudioStatus set to "%s" for "%s"' % (action, bookname))
                elif action in ["NoDelay"]:
                    myDB.action("delete from failedsearch WHERE BookID=? AND Library=?", (bookid, library))
                    logger.debug('%s delay set to zero for %s' % (library, bookid))
                elif action in ["Remove", "Delete"]:
                    bookdata = myDB.match(
                        'SELECT AuthorID,Bookname,BookFile,AudioFile from books WHERE BookID=?', (bookid,))
                    if bookdata:
                        authorid = bookdata['AuthorID']
                        bookname = bookdata['BookName']
                        if authorid not in check_totals:
                            check_totals.append(authorid)
                        if action == "Delete":
                            if 'Audio' in library:
                                bookfile = bookdata['AudioFile']
                                if bookfile and os.path.isfile(bookfile):
                                    try:
                                        rmtree(os.path.dirname(bookfile), ignore_errors=True)
                                        logger.info('AudioBook %s deleted from disc' % bookname)
                                    except Exception as e:
                                        logger.warn('rmtree failed on %s, %s %s' %
                                                    (bookfile, type(e).__name__, str(e)))

                            if 'eBook' in library:
                                bookfile = bookdata['BookFile']
                                if bookfile and os.path.isfile(bookfile):
                                    try:
                                        rmtree(os.path.dirname(bookfile), ignore_errors=True)
                                        deleted = True
                                    except Exception as e:
                                        logger.warn('rmtree failed on %s, %s %s' %
                                                    (bookfile, type(e).__name__, str(e)))
                                        deleted = False

                                    if deleted:
                                        logger.info('eBook %s deleted from disc' % bookname)
                                        try:
                                            calibreid = os.path.dirname(bookfile)
                                            if calibreid.endswith(')'):
                                                # noinspection PyTypeChecker
                                                calibreid = calibreid.rsplit('(', 1)[1].split(')')[0]
                                                if not calibreid or not calibreid.isdigit():
                                                    calibreid = None
                                            else:
                                                calibreid = None
                                        except IndexError:
                                            calibreid = None

                                        if calibreid:
                                            res, err, rc = calibredb('remove', [calibreid], None)
                                            if res and not rc:
                                                logger.debug('%s reports: %s' %
                                                             (lazylibrarian.CONFIG['IMP_CALIBREDB'],
                                                              unaccented_str(res)))
                                            else:
                                                logger.debug('No response from %s' %
                                                             lazylibrarian.CONFIG['IMP_CALIBREDB'])

                        authorcheck = myDB.match('SELECT Status from authors WHERE AuthorID=?', (authorid,))
                        if authorcheck:
                            if authorcheck['Status'] not in ['Active', 'Wanted']:
                                myDB.action('delete from books where bookid=?', (bookid,))
                                logger.info('Removed "%s" from database' % bookname)
                            elif 'eBook' in library:
                                myDB.upsert("books", {"Status": "Ignored"}, {"BookID": bookid})
                                logger.debug('Status set to Ignored for "%s"' % bookname)
                            elif 'Audio' in library:
                                myDB.upsert("books", {"AudioStatus": "Ignored"}, {"BookID": bookid})
                                logger.debug('AudioStatus set to Ignored for "%s"' % bookname)
                        else:
                            myDB.action('delete from books where bookid=?', (bookid,))
                            logger.info('Removed "%s" from database' % bookname)

        if check_totals:
            for author in check_totals:
                update_totals(author)

        # start searchthreads
        if action == 'Wanted':
            books = []
            for arg in ['booklang', 'library', 'ignored', 'book_table_length']:
                args.pop(arg, None)
            for arg in args:
                books.append({"bookid": arg})

            if lazylibrarian.USE_NZB() or lazylibrarian.USE_TOR() \
                    or lazylibrarian.USE_RSS() or lazylibrarian.USE_DIRECT():
                if 'eBook' in library:
                    threading.Thread(target=search_book, name='SEARCHBOOK', args=[books, 'eBook']).start()
                if 'Audio' in library:
                    threading.Thread(target=search_book, name='SEARCHBOOK', args=[books, 'AudioBook']).start()

        if redirect == "author":
                if 'eBook' in library:
                    raise cherrypy.HTTPRedirect("authorPage?AuthorID=%s&library=%s" % (AuthorID, 'eBook'))
                if 'Audio' in library:
                    raise cherrypy.HTTPRedirect("authorPage?AuthorID=%s&library=%s" % (AuthorID, 'AudioBook'))
        elif redirect in ["books", "audio"]:
            raise cherrypy.HTTPRedirect(redirect)
        elif redirect == "members":
            raise cherrypy.HTTPRedirect("seriesMembers?seriesid=%s" % seriesid)
        elif 'Audio' in library:
            raise cherrypy.HTTPRedirect("manage?library=%s" % 'AudioBook')
        raise cherrypy.HTTPRedirect("manage?library=%s" % 'eBook')

    # WALL #########################################################

    @cherrypy.expose
    def magWall(self, title=None):
        self.label_thread('MAGWALL')
        myDB = database.DBConnection()
        cmd = 'SELECT IssueFile,IssueID,IssueDate from issues'
        args = None
        if title:
            title = title.replace('&amp;', '&')
            cmd += ' WHERE Title=?'
            args = (title,)
        cmd += ' order by IssueAcquired DESC'
        issues = myDB.select(cmd, args)
        title = "Recent Issues"
        if not len(issues):
            raise cherrypy.HTTPRedirect("magazines")
        else:
            mod_issues = []
            count = 0
            maxcount = check_int(lazylibrarian.CONFIG['MAX_WALL'], 0)
            for issue in issues:
                magfile = issue['IssueFile']
                extn = os.path.splitext(magfile)[1]
                if extn:
                    magimg = magfile.replace(extn, '.jpg')
                    if not magimg or not os.path.isfile(magimg):
                        magimg = 'images/nocover.jpg'
                    else:
                        myhash = md5_utf8(magimg)
                        hashname = os.path.join(lazylibrarian.CACHEDIR, 'magazine', myhash + ".jpg")
                        if not os.path.isfile(hashname):
                            copyfile(magimg, hashname)
                            setperm(hashname)
                        magimg = 'cache/magazine/' + myhash + '.jpg'
                else:
                    logger.debug('No extension found on %s' % magfile)
                    magimg = 'images/nocover.jpg'

                this_issue = dict(issue)
                this_issue['Cover'] = magimg
                mod_issues.append(this_issue)
                count += 1
                if maxcount and count >= maxcount:
                    title = "%s (Top %i)" % (title, count)
                    break

        return serve_template(
            templatename="coverwall.html", title=title, results=mod_issues, redirect="magazines",
            columns=lazylibrarian.CONFIG['WALL_COLUMNS'])

    @cherrypy.expose
    def bookWall(self, have='0'):
        self.label_thread('BOOKWALL')
        myDB = database.DBConnection()
        if have == '1':
            cmd = 'SELECT BookLink,BookImg,BookID,BookName from books where Status="Open" order by BookLibrary DESC'
            title = 'Recently Downloaded Books'
        else:
            cmd = 'SELECT BookLink,BookImg,BookID,BookName from books where Status != "Ignored" order by BookAdded DESC'
            title = 'Recently Added Books'
        results = myDB.select(cmd)
        if not len(results):
            raise cherrypy.HTTPRedirect("books")
        maxcount = check_int(lazylibrarian.CONFIG['MAX_WALL'], 0)
        if maxcount and len(results) > maxcount:
            results = results[:maxcount]
            title = "%s (Top %i)" % (title, len(results))
        return serve_template(
            templatename="coverwall.html", title=title, results=results, redirect="books", have=have,
            columns=lazylibrarian.CONFIG['WALL_COLUMNS'])

    @cherrypy.expose
    def audioWall(self):
        self.label_thread('AUDIOWALL')
        myDB = database.DBConnection()
        results = myDB.select(
            'SELECT AudioFile,BookImg,BookID,BookName from books where AudioStatus="Open" order by AudioLibrary DESC')
        if not len(results):
            raise cherrypy.HTTPRedirect("audio")
        title = "Recent AudioBooks"
        maxcount = check_int(lazylibrarian.CONFIG['MAX_WALL'], 0)
        if maxcount and len(results) > maxcount:
            results = results[:maxcount]
            title = "%s (Top %i)" % (title, len(results))
        return serve_template(
            templatename="coverwall.html", title=title, results=results, redirect="audio",
            columns=lazylibrarian.CONFIG['WALL_COLUMNS'])

    @cherrypy.expose
    def wallColumns(self, redirect=None, count=None, have=0):
        columns = check_int(lazylibrarian.CONFIG['WALL_COLUMNS'], 6)
        if count == 'up' and columns <= 12:
            columns += 1
        elif count == 'down' and columns > 1:
            columns -= 1
        lazylibrarian.CONFIG['WALL_COLUMNS'] = columns
        if redirect == 'audio':
            raise cherrypy.HTTPRedirect('audioWall')
        elif redirect == 'books':
            raise cherrypy.HTTPRedirect('bookWall?have=%s' % have)
        elif redirect == 'magazines':
            raise cherrypy.HTTPRedirect('magWall')
        else:
            raise cherrypy.HTTPRedirect('home')

    # MAGAZINES #########################################################

    # noinspection PyUnusedLocal
    @cherrypy.expose
    @cherrypy.tools.json_out()
    def getMags(self, iDisplayStart=0, iDisplayLength=100, iSortCol_0=0, sSortDir_0="desc", sSearch="", **kwargs):
        # kwargs is used by datatables to pass params
        # for arg in kwargs:
        #     print arg, kwargs[arg]
        rows = []
        filtered = []
        rowlist = []
        # noinspection PyBroadException
        try:
            iDisplayStart = int(iDisplayStart)
            iDisplayLength = int(iDisplayLength)
            lazylibrarian.CONFIG['DISPLAYLENGTH'] = iDisplayLength
            mags = []
            myDB = database.DBConnection()
            cmd = 'select magazines.*,(select count(*) as counter from issues where magazines.title = issues.title)'
            cmd += ' as Iss_Cnt from magazines order by Title'

            rowlist = myDB.select(cmd)

            if len(rowlist):
                for mag in rowlist:
                    magimg = mag['LatestCover']
                    if not lazylibrarian.CONFIG['IMP_MAGCOVER'] or not magimg or not os.path.isfile(magimg):
                        magimg = 'images/nocover.jpg'
                    else:
                        myhash = md5_utf8(magimg)
                        hashname = os.path.join(lazylibrarian.CACHEDIR, 'magazine', '%s.jpg' % myhash)
                        if not os.path.isfile(hashname):
                            copyfile(magimg, hashname)
                            setperm(hashname)
                        magimg = 'cache/magazine/' + myhash + '.jpg'

                    this_mag = dict(mag)
                    this_mag['Cover'] = magimg
                    temp_title = mag['Title']
                    if PY2:
                        temp_title = temp_title.encode(lazylibrarian.SYS_ENCODING)
                    this_mag['safetitle'] = quote_plus(temp_title)
                    mags.append(this_mag)

                rowlist = []
                if len(mags):
                    for mag in mags:
                        entry = [mag['safetitle'], mag['Cover'], mag['Title'], mag['Iss_Cnt'], mag['LastAcquired'],
                                 mag['IssueDate'], mag['Status'], mag['IssueStatus']]
                        rowlist.append(entry)  # add each rowlist to the masterlist

                if sSearch:
                    if lazylibrarian.LOGLEVEL & lazylibrarian.log_serverside:
                        logger.debug("filter %s" % sSearch)
                    filtered = [x for x in rowlist if sSearch.lower() in str(x).lower()]
                else:
                    filtered = rowlist

                sortcolumn = int(iSortCol_0)
                if lazylibrarian.LOGLEVEL & lazylibrarian.log_serverside:
                    logger.debug("sortcolumn %d" % sortcolumn)

                if sortcolumn in [4, 5]:  # dates
                    self.natural_sort(filtered, key=lambda y: y[sortcolumn] if y[sortcolumn] is not None else '',
                                      reverse=sSortDir_0 == "desc")
                elif sortcolumn == 2:  # title
                    filtered.sort(key=lambda y: y[sortcolumn].lower(), reverse=sSortDir_0 == "desc")
                else:
                    filtered.sort(key=lambda y: y[sortcolumn], reverse=sSortDir_0 == "desc")

                if iDisplayLength < 0:  # display = all
                    rows = filtered
                else:
                    rows = filtered[iDisplayStart:(iDisplayStart + iDisplayLength)]

                for row in rows:
                    row[4] = dateFormat(row[4], lazylibrarian.CONFIG['DATE_FORMAT'])
                    if row[5] and row[5].isdigit():
                        if len(row[5]) == 8:
                            if check_year(row[5][:4]):
                                row[5] = 'Issue %d %s' % (int(row[5][4:]), row[5][:4])
                            else:
                                row[5] = 'Vol %d #%d' % (int(row[5][:4]), int(row[5][4:]))
                        elif len(row[5]) == 12:
                            row[5] = 'Vol %d #%d %s' % (int(row[5][4:8]), int(row[5][8:]), row[5][:4])
                    else:
                        row[5] = dateFormat(row[5], lazylibrarian.CONFIG['ISS_FORMAT'])

            if lazylibrarian.LOGLEVEL & lazylibrarian.log_serverside:
                logger.debug("getMags returning %s to %s" % (iDisplayStart, iDisplayStart + iDisplayLength))
                logger.debug("getMags filtered %s from %s:%s" % (len(filtered), len(rowlist), len(rows)))
        except Exception:
            logger.error('Unhandled exception in getMags: %s' % traceback.format_exc())
            rows = []
            rowlist = []
            filtered = []
        finally:
            mydict = {'iTotalDisplayRecords': len(filtered),
                      'iTotalRecords': len(rowlist),
                      'aaData': rows,
                      }
            return mydict

    @cherrypy.expose
    def magazines(self):
        if lazylibrarian.CONFIG['HTTP_LOOK'] != 'legacy':
            cookie = cherrypy.request.cookie
            if cookie and 'll_uid' in list(cookie.keys()):
                user = cookie['ll_uid'].value
            else:
                user = 0
            # use server-side processing
            covers = 1
            if not lazylibrarian.CONFIG['TOGGLES'] and not lazylibrarian.CONFIG['MAG_IMG']:
                covers = 0
            return serve_template(templatename="magazines.html", title="Magazines", magazines=[],
                                  covercount=covers, user=user)

        myDB = database.DBConnection()

        cmd = 'select magazines.*,(select count(*) as counter from issues where magazines.title = issues.title)'
        cmd += ' as Iss_Cnt from magazines order by Title'
        magazines = myDB.select(cmd)
        mags = []
        covercount = 0
        if magazines:
            for mag in magazines:
                magimg = mag['LatestCover']
                if not lazylibrarian.CONFIG['IMP_MAGCOVER'] or not magimg or not os.path.isfile(magimg):
                    magimg = 'images/nocover.jpg'
                else:
                    myhash = md5_utf8(magimg)
                    hashname = os.path.join(lazylibrarian.CACHEDIR, 'magazine', '%s.jpg' % myhash)
                    if not os.path.isfile(hashname):
                        copyfile(magimg, hashname)
                        setperm(hashname)
                    magimg = 'cache/magazine/' + myhash + '.jpg'
                    covercount += 1

                this_mag = dict(mag)
                this_mag['Cover'] = magimg
                temp_title = mag['Title']
                if PY2:
                    temp_title = temp_title.encode(lazylibrarian.SYS_ENCODING)
                this_mag['safetitle'] = quote_plus(temp_title)
                mags.append(this_mag)

            if not lazylibrarian.CONFIG['MAG_IMG']:
                covercount = 0

        return serve_template(templatename="magazines.html", title="Magazines", magazines=mags, covercount=covercount)

    @cherrypy.expose
    @cherrypy.tools.json_out()
    def getIssues(self, iDisplayStart=0, iDisplayLength=100, iSortCol_0=0, sSortDir_0="desc", sSearch="", **kwargs):
        rows = []
        filtered = []
        rowlist = []
        # noinspection PyBroadException
        try:
            iDisplayStart = int(iDisplayStart)
            iDisplayLength = int(iDisplayLength)
            lazylibrarian.CONFIG['DISPLAYLENGTH'] = iDisplayLength

            title = kwargs['title'].replace('&amp;', '&')
            myDB = database.DBConnection()
            rowlist = myDB.select('SELECT * from issues WHERE Title=? order by IssueDate DESC', (title,))
            if len(rowlist):
                mod_issues = []
                covercount = 0
                for issue in rowlist:
                    magfile = issue['IssueFile']
                    extn = os.path.splitext(magfile)[1]
                    if extn:
                        magimg = magfile.replace(extn, '.jpg')
                        if not magimg or not os.path.isfile(magimg):
                            magimg = 'images/nocover.jpg'
                        else:
                            myhash = md5_utf8(magimg)
                            hashname = os.path.join(lazylibrarian.CACHEDIR, 'magazine', myhash + ".jpg")
                            if not os.path.isfile(hashname):
                                copyfile(magimg, hashname)
                                setperm(hashname)
                            magimg = 'cache/magazine/' + myhash + '.jpg'
                            covercount += 1
                    else:
                        logger.debug('No extension found on %s' % magfile)
                        magimg = 'images/nocover.jpg'

                    this_issue = dict(issue)
                    this_issue['Cover'] = magimg
                    mod_issues.append(this_issue)

                rowlist = []
                if len(mod_issues):
                    for mag in mod_issues:
                        entry = [mag['Title'], mag['Cover'], mag['IssueDate'], mag['IssueAcquired'],
                                 mag['IssueID']]
                        rowlist.append(entry)  # add each rowlist to the masterlist

                if sSearch:
                    if lazylibrarian.LOGLEVEL & lazylibrarian.log_serverside:
                        logger.debug("filter %s" % sSearch)
                    filtered = [x for x in rowlist if sSearch.lower() in str(x).lower()]
                else:
                    filtered = rowlist

                sortcolumn = int(iSortCol_0)
                if lazylibrarian.LOGLEVEL & lazylibrarian.log_serverside:
                    logger.debug("sortcolumn %d" % sortcolumn)

                if sortcolumn in [2, 3]:  # dates
                    self.natural_sort(filtered, key=lambda y: y[sortcolumn] if y[sortcolumn] is not None else '',
                                      reverse=sSortDir_0 == "desc")
                else:
                    filtered.sort(key=lambda y: y[sortcolumn], reverse=sSortDir_0 == "desc")

                if iDisplayLength < 0:  # display = all
                    rows = filtered
                else:
                    rows = filtered[iDisplayStart:(iDisplayStart + iDisplayLength)]

            for row in rows:
                row[3] = dateFormat(row[3], lazylibrarian.CONFIG['DATE_FORMAT'])
                if row[2] and row[2].isdigit():
                    if len(row[2]) == 8:
                        # Year/Issue or Volume/Issue with no year
                        if check_year(row[2][:4]):
                            row[2] = 'Issue %d %s' % (int(row[2][4:]), row[2][:4])
                        else:
                            row[2] = 'Vol %d #%d' % (int(row[2][:4]), int(row[2][4:]))
                    elif len(row[2]) == 12:
                        row[2] = 'Vol %d #%d %s' % (int(row[2][4:8]), int(row[2][8:]), row[2][:4])
                else:
                    row[2] = dateFormat(row[2], lazylibrarian.CONFIG['ISS_FORMAT'])

            if lazylibrarian.LOGLEVEL & lazylibrarian.log_serverside:
                logger.debug("getIssues returning %s to %s" % (iDisplayStart, iDisplayStart + iDisplayLength))
                logger.debug("getIssues filtered %s from %s:%s" % (len(filtered), len(rowlist), len(rows)))
        except Exception:
            logger.error('Unhandled exception in getIssues: %s' % traceback.format_exc())
            rows = []
            rowlist = []
            filtered = []
        finally:
            mydict = {'iTotalDisplayRecords': len(filtered),
                      'iTotalRecords': len(rowlist),
                      'aaData': rows,
                      }
            return mydict

    @cherrypy.expose
    def issuePage(self, title):
        if title and '&' in title and '&amp;' not in title:  # could use htmlparser but seems overkill for just '&'
            safetitle = title.replace('&', '&amp;')
        else:
            safetitle = title

        if lazylibrarian.CONFIG['HTTP_LOOK'] != 'legacy':
            # use server-side processing
            if not lazylibrarian.CONFIG['TOGGLES'] and not lazylibrarian.CONFIG['MAG_IMG']:
                covercount = 0
            else:
                covercount = 1
            return serve_template(templatename="issues.html", title=safetitle, issues=[], covercount=covercount)

        myDB = database.DBConnection()

        issues = myDB.select('SELECT * from issues WHERE Title=? order by IssueDate DESC', (title,))

        if not len(issues):
            raise cherrypy.HTTPRedirect("magazines")
        else:
            mod_issues = []
            covercount = 0
            for issue in issues:
                magfile = issue['IssueFile']
                extn = os.path.splitext(magfile)[1]
                if extn:
                    magimg = magfile.replace(extn, '.jpg')
                    if not magimg or not os.path.isfile(magimg):
                        magimg = 'images/nocover.jpg'
                    else:
                        myhash = md5_utf8(magimg)
                        hashname = os.path.join(lazylibrarian.CACHEDIR, 'magazine', myhash + ".jpg")
                        if not os.path.isfile(hashname):
                            copyfile(magimg, hashname)
                            setperm(hashname)
                        magimg = 'cache/magazine/' + myhash + '.jpg'
                        covercount += 1
                else:
                    logger.debug('No extension found on %s' % magfile)
                    magimg = 'images/nocover.jpg'

                this_issue = dict(issue)
                this_issue['Cover'] = magimg
                mod_issues.append(this_issue)
            logger.debug("Found %s cover%s" % (covercount, plural(covercount)))

            if not lazylibrarian.CONFIG['MAG_IMG'] or not lazylibrarian.CONFIG['IMP_MAGCOVER']:
                covercount = 0

        return serve_template(templatename="issues.html", title=safetitle, issues=mod_issues, covercount=covercount)

    @cherrypy.expose
    def pastIssues(self, whichStatus=None, mag=None):
        if not mag or mag == 'None':
            title = "Past Issues"
        else:
            title = mag
        if not whichStatus or whichStatus == 'None':
            whichStatus = "Skipped"
        return serve_template(
            templatename="manageissues.html", title=title, issues=[], whichStatus=whichStatus, mag=mag)

    @cherrypy.expose
    @cherrypy.tools.json_out()
    def getPastIssues(self, iDisplayStart=0, iDisplayLength=100, iSortCol_0=0, sSortDir_0="desc", sSearch="", **kwargs):
        # kwargs is used by datatables to pass params
        rows = []
        filtered = []
        rowlist = []
        # noinspection PyBroadException
        try:
            myDB = database.DBConnection()
            iDisplayStart = int(iDisplayStart)
            iDisplayLength = int(iDisplayLength)
            lazylibrarian.CONFIG['DISPLAYLENGTH'] = iDisplayLength
            # need to filter on whichStatus and optional mag title
            cmd = 'SELECT NZBurl, NZBtitle, NZBdate, Auxinfo, NZBprov from pastissues WHERE Status=?'
            args = [kwargs['whichStatus']]
            if 'mag' in kwargs and kwargs['mag'] != 'None':
                cmd += ' AND BookID=?'
                args.append(kwargs['mag'].replace('&amp;', '&'))

            if lazylibrarian.LOGLEVEL & lazylibrarian.log_serverside:
                logger.debug("getPastIssues %s: %s" % (cmd, str(args)))
            rowlist = myDB.select(cmd, tuple(args))
            if len(rowlist):
                for row in rowlist:  # iterate through the sqlite3.Row objects
                    thisrow = list(row)
                    # title needs spaces for column resizing
                    title = thisrow[1]
                    title = title.replace('.', ' ')
                    title = title.replace('LL (', 'LL.(')
                    thisrow[1] = title
                    # make this shorter and with spaces for column resizing
                    provider = thisrow[4]
                    if len(provider) > 20:
                        while len(provider) > 20 and '/' in provider:
                            provider = provider.split('/', 1)[1]
                        provider = provider.replace('/', ' ')
                        thisrow[4] = provider
                    rows.append(thisrow)  # add each rowlist to the masterlist

                if sSearch:
                    if lazylibrarian.LOGLEVEL & lazylibrarian.log_serverside:
                        logger.debug("filter %s" % sSearch)
                    filtered = [x for x in rows if sSearch.lower() in str(x).lower()]
                else:
                    filtered = rows

                sortcolumn = int(iSortCol_0)
                if lazylibrarian.LOGLEVEL & lazylibrarian.log_serverside:
                    logger.debug("sortcolumn %d" % sortcolumn)

                filtered.sort(key=lambda y: y[sortcolumn], reverse=sSortDir_0 == "desc")

                if iDisplayLength < 0:  # display = all
                    rows = filtered
                else:
                    rows = filtered[iDisplayStart:(iDisplayStart + iDisplayLength)]

            if lazylibrarian.LOGLEVEL & lazylibrarian.log_serverside:
                logger.debug("getPastIssues returning %s to %s" % (iDisplayStart, iDisplayStart + iDisplayLength))
                logger.debug("getPastIssues filtered %s from %s:%s" % (len(filtered), len(rowlist), len(rows)))
        except Exception:
            logger.error('Unhandled exception in getPastIssues: %s' % traceback.format_exc())
            rows = []
            rowlist = []
            filtered = []
        finally:
            mydict = {'iTotalDisplayRecords': len(filtered),
                      'iTotalRecords': len(rowlist),
                      'aaData': rows,
                      }
            return mydict

    @cherrypy.expose
    def openMag(self, bookid=None):
        bookid = unquote_plus(bookid)
        myDB = database.DBConnection()
        # we may want to open an issue with a hashed bookid
        mag_data = myDB.match('SELECT * from issues WHERE IssueID=?', (bookid,))
        if mag_data:
            IssueFile = mag_data["IssueFile"]
            if IssueFile and os.path.isfile(IssueFile):
                logger.debug('Opening file %s' % IssueFile)
                return self.send_file(IssueFile, name="Magazine %s %s" % (mag_data["Title"], mag_data["IssueDate"]))

        # or we may just have a title to find magazine in issues table
        mag_data = myDB.select('SELECT * from issues WHERE Title=?', (bookid,))
        if len(mag_data) <= 0:  # no issues!
            raise cherrypy.HTTPRedirect("magazines")
        elif len(mag_data) == 1 and lazylibrarian.CONFIG['MAG_SINGLE']:  # we only have one issue, get it
            IssueDate = mag_data[0]["IssueDate"]
            IssueFile = mag_data[0]["IssueFile"]
            logger.debug('Opening %s - %s' % (bookid, IssueDate))
            return self.send_file(IssueFile, name="Magazine %s %s" % (bookid, IssueDate))
        else:  # multiple issues, show a list
            logger.debug("%s has %s issue%s" % (bookid, len(mag_data), plural(len(mag_data))))
            if PY2:
                bookid = bookid.encode(lazylibrarian.SYS_ENCODING)
            raise cherrypy.HTTPRedirect("issuePage?title=%s" % quote_plus(bookid))

    @cherrypy.expose
    def markPastIssues(self, action=None, **args):
        myDB = database.DBConnection()
        maglist = []
        args.pop('book_table_length', None)

        for nzburl in args:
            nzburl = makeUnicode(nzburl)
            # some NZBurl have &amp;  some have just & so need to try both forms
            if '&' in nzburl and '&amp;' not in nzburl:
                nzburl2 = nzburl.replace('&', '&amp;')
            elif '&amp;' in nzburl:
                nzburl2 = nzburl.replace('&amp;', '&')
            else:
                nzburl2 = ''

            if not nzburl2:
                title = myDB.select('SELECT * from pastissues WHERE NZBurl=?', (nzburl,))
            else:
                title = myDB.select('SELECT * from pastissues WHERE NZBurl=? OR NZBurl=?', (nzburl, nzburl2))

            for item in title:
                nzburl = item['NZBurl']
                if action == 'Remove':
                    myDB.action('DELETE from pastissues WHERE NZBurl=?', (nzburl,))
                    logger.debug('Item %s removed from past issues' % item['NZBtitle'])
                    maglist.append({'nzburl': nzburl})
                elif action == 'Wanted':
                    bookid = item['BookID']
                    nzbprov = item['NZBprov']
                    nzbtitle = item['NZBtitle']
                    nzbmode = item['NZBmode']
                    nzbsize = item['NZBsize']
                    auxinfo = item['AuxInfo']
                    maglist.append({
                        'bookid': bookid,
                        'nzbprov': nzbprov,
                        'nzbtitle': nzbtitle,
                        'nzburl': nzburl,
                        'nzbmode': nzbmode
                    })
                    # copy into wanted table
                    controlValueDict = {'NZBurl': nzburl}
                    newValueDict = {
                        'BookID': bookid,
                        'NZBtitle': nzbtitle,
                        'NZBdate': now(),
                        'NZBprov': nzbprov,
                        'Status': action,
                        'NZBsize': nzbsize,
                        'AuxInfo': auxinfo,
                        'NZBmode': nzbmode
                    }
                    myDB.upsert("wanted", newValueDict, controlValueDict)

                elif action in ['Ignored', 'Skipped']:
                    myDB.action('UPDATE pastissues set status=? WHERE NZBurl=?', (action, nzburl))
                    logger.debug('Item %s marked %s in past issues' % (item['NZBtitle'], action))
                    maglist.append({'nzburl': nzburl})

        if action == 'Remove':
            logger.info('Removed %s item%s from past issues' % (len(maglist), plural(len(maglist))))
        else:
            logger.info('Status set to %s for %s past issue%s' % (action, len(maglist), plural(len(maglist))))
        # start searchthreads
        if action == 'Wanted':
            for items in maglist:
                logger.debug('Snatching %s, %s from %s' % (items['nzbtitle'], items['nzbmode'], items['nzbprov']))
                myDB.action('UPDATE pastissues set status=? WHERE NZBurl=?', (action, items['nzburl']))
                if items['nzbmode'] == 'direct':
                    snatch, res = DirectDownloadMethod(
                        items['bookid'],
                        items['nzbtitle'],
                        items['nzburl'],
                        'magazine')
                elif items['nzbmode'] in ['torznab', 'torrent', 'magnet']:
                    snatch, res = TORDownloadMethod(
                        items['bookid'],
                        items['nzbtitle'],
                        items['nzburl'],
                        'magazine')
                elif items['nzbmode'] == 'nzb':
                    snatch, res = NZBDownloadMethod(
                        items['bookid'],
                        items['nzbtitle'],
                        items['nzburl'],
                        'magazine')
                else:
                    res = 'Unhandled NZBmode [%s] for %s' % (items['nzbmode'], items["nzburl"])
                    logger.error(res)
                    snatch = 0
                if snatch:
                    myDB.action('UPDATE pastissues set status=? WHERE NZBurl=?', ("Snatched", items['nzburl']))
                    logger.info('Downloading %s from %s' % (items['nzbtitle'], items['nzbprov']))
                    custom_notify_snatch("%s %s" % (items['bookid'], 'Magazine'))
                    notifiers.notify_snatch(items['nzbtitle'] + ' at ' + now())
                    scheduleJob(action='Start', target='PostProcessor')
                else:
                    myDB.action('UPDATE pastissues SET status="Failed",DLResult=? WHERE NZBurl=?',
                                (res, items["nzburl"]))
        raise cherrypy.HTTPRedirect("pastIssues")

    @cherrypy.expose
    def markIssues(self, action=None, **args):
        myDB = database.DBConnection()
        title = ''
        args.pop('book_table_length', None)

        if action:
            for item in args:
                issue = myDB.match('SELECT IssueFile,Title,IssueDate from issues WHERE IssueID=?', (item,))
                if issue:
                    title = issue['Title']
                    if 'reCover' in action:
                        createMagCover(issue['IssueFile'], refresh=True, pagenum=check_int(action[-1], 1))
                    if action == "Delete":
                        result = self.deleteIssue(issue['IssueFile'])
                        if result:
                            logger.info('Issue %s of %s deleted from disc' % (issue['IssueDate'], issue['Title']))
                    if action == "Remove" or action == "Delete":
                        myDB.action('DELETE from issues WHERE IssueID=?', (item,))
                        logger.info('Issue %s of %s removed from database' % (issue['IssueDate'], issue['Title']))
                        # Set magazine_issuedate to issuedate of most recent issue we have
                        # Set latestcover to most recent issue cover
                        # Set magazine_lastacquired to acquired date of most recent issue we have
                        # Set magazine_added to acquired date of earliest issue we have
                        cmd = 'select IssueDate,IssueAcquired,IssueFile from issues where title=?'
                        cmd += ' order by IssueDate '
                        newest = myDB.match(cmd + 'DESC', (title,))
                        oldest = myDB.match(cmd + 'ASC', (title,))
                        controlValueDict = {'Title': title}
                        if newest and oldest:
                            old_acquired = ''
                            new_acquired = ''
                            cover = ''
                            issuefile = newest['IssueFile']
                            if os.path.exists(issuefile):
                                cover = os.path.splitext(issuefile)[0] + '.jpg'
                                mtime = os.path.getmtime(issuefile)
                                new_acquired = datetime.date.isoformat(datetime.date.fromtimestamp(mtime))
                            issuefile = oldest['IssueFile']
                            if os.path.exists(issuefile):
                                mtime = os.path.getmtime(issuefile)
                                old_acquired = datetime.date.isoformat(datetime.date.fromtimestamp(mtime))

                            newValueDict = {
                                'IssueDate': newest['IssueDate'],
                                'LatestCover': cover,
                                'LastAcquired': new_acquired,
                                'MagazineAdded': old_acquired
                            }
                        else:
                            newValueDict = {
                                'IssueDate': '',
                                'LastAcquired': '',
                                'LatestCover': '',
                                'MagazineAdded': ''
                            }
                        myDB.upsert("magazines", newValueDict, controlValueDict)
        if title:
            raise cherrypy.HTTPRedirect("issuePage?title=%s" % quote_plus(title))
        else:
            raise cherrypy.HTTPRedirect("magazines")

    @staticmethod
    def deleteIssue(issuefile):
        try:
            # delete the magazine file and any cover image / opf
            if os.path.exists(issuefile):
                os.remove(issuefile)
            fname, extn = os.path.splitext(issuefile)
            for extn in ['.opf', '.jpg']:
                if os.path.exists(fname + extn):
                    os.remove(fname + extn)

            # if the directory is now empty, delete that too
            if lazylibrarian.CONFIG['MAG_DELFOLDER']:
                try:
                    os.rmdir(os.path.dirname(issuefile))
                except OSError as e:
                    logger.debug('Directory %s not deleted: %s' % (os.path.dirname(issuefile), str(e)))
                return True
        except Exception as e:
            logger.warn('delete issue failed on %s, %s %s' % (issuefile, type(e).__name__, str(e)))
        return False

    @cherrypy.expose
    def markMagazines(self, action=None, **args):
        myDB = database.DBConnection()
        args.pop('book_table_length', None)

        for item in args:
            title = makeUnicode(unquote_plus(item))
            if action == "Paused" or action == "Active":
                controlValueDict = {"Title": title}
                newValueDict = {"Status": action}
                myDB.upsert("magazines", newValueDict, controlValueDict)
                logger.info('Status of magazine %s changed to %s' % (title, action))
            if action == "Delete":
                issues = myDB.select('SELECT IssueFile from issues WHERE Title=?', (title,))
                logger.debug('Deleting magazine %s from disc' % title)
                issuedir = ''
                for issue in issues:  # delete all issues of this magazine
                    result = self.deleteIssue(issue['IssueFile'])
                    if result:
                        logger.debug('Issue %s deleted from disc' % issue['IssueFile'])
                        issuedir = os.path.dirname(issue['IssueFile'])
                    else:
                        logger.debug('Failed to delete %s' % (issue['IssueFile']))

                # if the directory is now empty, delete that too
                if issuedir and lazylibrarian.CONFIG['MAG_DELFOLDER']:
                    magdir = os.path.dirname(issuedir)
                    try:
                        os.rmdir(magdir)
                        logger.debug('Magazine directory %s deleted from disc' % magdir)
                    except OSError:
                        logger.debug('Magazine directory %s is not empty' % magdir)
                    logger.info('Magazine %s deleted from disc' % title)

            if action == "Remove" or action == "Delete":
                myDB.action('DELETE from magazines WHERE Title=?', (title,))
                myDB.action('DELETE from pastissues WHERE BookID=?', (title,))
                myDB.action('DELETE from wanted where BookID=?', (title,))
                logger.info('Magazine %s removed from database' % title)
            if action == "Reset":
                controlValueDict = {"Title": title}
                newValueDict = {
                    "LastAcquired": None,
                    "IssueDate": None,
                    "LatestCover": None,
                    "IssueStatus": "Wanted"
                }
                myDB.upsert("magazines", newValueDict, controlValueDict)
                logger.info('Magazine %s details reset' % title)

        raise cherrypy.HTTPRedirect("magazines")

    @cherrypy.expose
    def searchForMag(self, bookid=None):
        myDB = database.DBConnection()
        bookid = unquote_plus(bookid)
        bookdata = myDB.match('SELECT * from magazines WHERE Title=?', (bookid,))
        if bookdata:
            # start searchthreads
            mags = [{"bookid": bookid}]
            self.startMagazineSearch(mags)
            raise cherrypy.HTTPRedirect("magazines")

    @cherrypy.expose
    def startMagazineSearch(self, mags=None):
        if mags:
            if lazylibrarian.USE_NZB() or lazylibrarian.USE_TOR() \
                    or lazylibrarian.USE_RSS() or lazylibrarian.USE_DIRECT():
                threading.Thread(target=search_magazines, name='SEARCHMAG', args=[mags, False]).start()
                logger.debug("Searching for magazine with title: %s" % mags[0]["bookid"])
            else:
                logger.warn("Not searching for magazine, no download methods set, check config")
        else:
            logger.debug("MagazineSearch called with no magazines")

    @cherrypy.expose
    def addMagazine(self, title=None):
        myDB = database.DBConnection()
        if not title or title == 'None':
            raise cherrypy.HTTPRedirect("magazines")
        else:
            reject = None
            if '~' in title:  # separate out the "reject words" list
                reject = title.split('~', 1)[1].strip()
                title = title.split('~', 1)[0].strip()

            # replace any non-ascii quotes/apostrophes with ascii ones eg "Collector's"
            dic = {'\u2018': "'", '\u2019': "'", '\u201c': '"', '\u201d': '"'}
            title = replace_all(title, dic)
            exists = myDB.match('SELECT Title from magazines WHERE Title=?', (title,))
            if exists:
                logger.debug("Magazine %s already exists (%s)" % (title, exists['Title']))
            else:
                controlValueDict = {"Title": title}
                newValueDict = {
                    "Regex": None,
                    "Reject": reject,
                    "DateType": "",
                    "Status": "Active",
                    "MagazineAdded": today(),
                    "IssueStatus": "Wanted"
                }
                myDB.upsert("magazines", newValueDict, controlValueDict)
                mags = [{"bookid": title}]
                if lazylibrarian.CONFIG['IMP_AUTOSEARCH']:
                    self.startMagazineSearch(mags)
            raise cherrypy.HTTPRedirect("magazines")

    # UPDATES ###########################################################

    @cherrypy.expose
    def checkForUpdates(self):
        self.label_thread('UPDATES')
        versioncheck.checkForUpdates()
        if lazylibrarian.CONFIG['COMMITS_BEHIND'] == 0:
            if lazylibrarian.COMMIT_LIST:
                message = "unknown status"
                messages = lazylibrarian.COMMIT_LIST.replace('\n', '<br>')
                message = message + '<br><small>' + messages
            else:
                message = "up to date"
        elif lazylibrarian.CONFIG['COMMITS_BEHIND'] > 0:
            message = "behind by %s commit%s" % (lazylibrarian.CONFIG['COMMITS_BEHIND'],
                                                 plural(lazylibrarian.CONFIG['COMMITS_BEHIND']))
            messages = lazylibrarian.COMMIT_LIST.replace('\n', '<br>')
            message = message + '<br><small>' + messages
        else:
            message = "unknown version"
            messages = "Your version is not recognised at<br>https://github.com/%s/%s  Branch: %s" % (
                lazylibrarian.CONFIG['GIT_USER'], lazylibrarian.CONFIG['GIT_REPO'], lazylibrarian.CONFIG['GIT_BRANCH'])
            message = message + '<br><small>' + messages

        if lazylibrarian.CONFIG['HTTP_LOOK'] == 'legacy':
            return serve_template(templatename="response.html", prefix='LazyLibrarian is ',
                                  title="Version Check", message=message, timer=5)
        else:
            return "LazyLibrarian is %s" % message

    @cherrypy.expose
    def forceUpdate(self):
        if 'AAUPDATE' not in [n.name for n in [t for t in threading.enumerate()]]:
            threading.Thread(target=aaUpdate, name='AAUPDATE', args=[False]).start()
        else:
            logger.debug('AAUPDATE already running')
        raise cherrypy.HTTPRedirect("home")

    @cherrypy.expose
    def update(self):
        self.label_thread('UPDATING')
        logger.debug('(webServe-Update) - Performing update')
        lazylibrarian.SIGNAL = 'update'
        message = 'Updating...'
        return serve_template(templatename="shutdown.html", prefix='LazyLibrarian is ', title="Updating",
                              message=message, timer=30)

    # IMPORT/EXPORT #####################################################

    @cherrypy.expose
    def libraryScan(self, **kwargs):
        library = 'eBook'
        if 'library' in kwargs:
            library = kwargs['library']
        remove = bool(lazylibrarian.CONFIG['FULL_SCAN'])
        threadname = "%s_SCAN" % library.upper()
        if threadname not in [n.name for n in [t for t in threading.enumerate()]]:
            try:
                threading.Thread(target=LibraryScan, name=threadname, args=[None, library, None, remove]).start()
            except Exception as e:
                logger.error('Unable to complete the scan: %s %s' % (type(e).__name__, str(e)))
        else:
            logger.debug('%s already running' % threadname)
        if library == 'AudioBook':
            raise cherrypy.HTTPRedirect("audio")
        raise cherrypy.HTTPRedirect("books")

    @cherrypy.expose
    def magazineScan(self, **kwargs):
        if 'title' in kwargs:
            title = kwargs['title']
            title = title.replace('&amp;', '&')
        else:
            title = ''

        if 'MAGAZINE_SCAN' not in [n.name for n in [t for t in threading.enumerate()]]:
            try:
                if title:
                    threading.Thread(target=magazinescan.magazineScan, name='MAGAZINE_SCAN', args=[title]).start()
                else:
                    threading.Thread(target=magazinescan.magazineScan, name='MAGAZINE_SCAN', args=[]).start()
            except Exception as e:
                logger.error('Unable to complete the scan: %s %s' % (type(e).__name__, str(e)))
        else:
            logger.debug('MAGAZINE_SCAN already running')
        if title:
            raise cherrypy.HTTPRedirect("issuePage?title=%s" % quote_plus(title))
        else:
            raise cherrypy.HTTPRedirect("magazines")

    @cherrypy.expose
    def includeAlternate(self, library='eBook'):
        if 'ALT-LIBRARYSCAN' not in [n.name for n in [t for t in threading.enumerate()]]:
            try:
                threading.Thread(target=LibraryScan, name='ALT-LIBRARYSCAN',
                                 args=[lazylibrarian.CONFIG['ALTERNATE_DIR'], library, None, False]).start()
            except Exception as e:
                logger.error('Unable to complete the libraryscan: %s %s' % (type(e).__name__, str(e)))
        else:
            logger.debug('ALT-LIBRARYSCAN already running')
        raise cherrypy.HTTPRedirect("manage?library=%s" % library)

    @cherrypy.expose
    def importAlternate(self, library='eBook'):
        if 'IMPORTALT' not in [n.name for n in [t for t in threading.enumerate()]]:
            try:
                threading.Thread(target=processAlternate, name='IMPORTALT',
                                 args=[lazylibrarian.CONFIG['ALTERNATE_DIR'], library]).start()
            except Exception as e:
                logger.error('Unable to complete the import: %s %s' % (type(e).__name__, str(e)))
        else:
            logger.debug('IMPORTALT already running')
        raise cherrypy.HTTPRedirect("manage?library=%s" % library)

    @cherrypy.expose
    def rssFeed(self, **kwargs):
        self.label_thread('RSSFEED')
        if 'type' in kwargs:
            ftype = kwargs['type']
        else:
            return

        if 'limit' in kwargs:
            limit = kwargs['limit']
        else:
            limit = '10'

        # url might end in .xml
        if not limit.isdigit():
            try:
                limit = int(limit.split('.')[0])
            except (IndexError, ValueError):
                limit = 10

        userid = 0
        if 'user' in kwargs:
            userid = kwargs['user']
        else:
            cookie = cherrypy.request.cookie
            if cookie and 'll_uid' in list(cookie.keys()):
                userid = cookie['ll_uid'].value

        scheme, netloc, path, qs, anchor = urlsplit(cherrypy.url())
        try:
            netloc = cherrypy.request.headers['X-Forwarded-Host']
        except KeyError:
            pass

        if 'X-Forwarded-For' in cherrypy.request.headers:
            remote_ip = cherrypy.request.headers['X-Forwarded-For']  # apache2
        elif 'X-Host' in cherrypy.request.headers:
            remote_ip = cherrypy.request.headers['X-Host']  # lighthttpd
        elif 'Remote-Addr' in cherrypy.request.headers:
            remote_ip = cherrypy.request.headers['Remote-Addr']
        else:
            remote_ip = cherrypy.request.remote.ip

        filename = 'LazyLibrarian_RSS_' + ftype + '.xml'
        path = path.replace('rssFeed', '').rstrip('/')
        baseurl = urlunsplit((scheme, netloc, path, qs, anchor))
        logger.debug("RSS Feed request %s %s%s: %s %s" % (limit, ftype, plural(limit), remote_ip, userid))
        cherrypy.response.headers["Content-Type"] = 'application/rss+xml'
        cherrypy.response.headers["Content-Disposition"] = 'attachment; filename="%s"' % filename
        res = genFeed(ftype, limit=limit, user=userid, baseurl=baseurl)
        return makeBytestr(res)

    @cherrypy.expose
    def importCSV(self, library='eBook'):
        if 'IMPORTCSV' not in [n.name for n in [t for t in threading.enumerate()]]:
            try:
                csvFile = csv_file(lazylibrarian.CONFIG['ALTERNATE_DIR'], library=library)
                if os.path.exists(csvFile):
                    message = "Importing books (background task) from %s" % csvFile
                    threading.Thread(target=import_CSV, name='IMPORTCSV',
                                     args=[lazylibrarian.CONFIG['ALTERNATE_DIR'], library]).start()
                else:
                    message = "No %s CSV file in [%s]" % (library, lazylibrarian.CONFIG['ALTERNATE_DIR'])
            except Exception as e:
                message = 'Unable to complete the import: %s %s' % (type(e).__name__, str(e))
                logger.error(message)
        else:
            message = 'IMPORTCSV already running'
            logger.debug(message)

        if lazylibrarian.CONFIG['HTTP_LOOK'] == 'legacy':
            raise cherrypy.HTTPRedirect("manage")
        else:
            return message

    @cherrypy.expose
    def exportCSV(self, library='eBook'):
        self.label_thread('EXPORTCSV')
        message = export_CSV(lazylibrarian.CONFIG['ALTERNATE_DIR'], library=library)
        message = message.replace('\n', '<br>')
        if lazylibrarian.CONFIG['HTTP_LOOK'] == 'legacy':
            raise cherrypy.HTTPRedirect("manage")
        else:
            return message

    # JOB CONTROL #######################################################

    @cherrypy.expose
    def shutdown(self):
        self.label_thread('SHUTDOWN')
        # lazylibrarian.config_write()
        lazylibrarian.SIGNAL = 'shutdown'
        message = 'closing ...'
        return serve_template(templatename="shutdown.html", prefix='LazyLibrarian is ', title="Close library",
                              message=message, timer=15)

    @cherrypy.expose
    def restart(self):
        self.label_thread('RESTART')
        lazylibrarian.SIGNAL = 'restart'
        message = 'reopening ...'
        return serve_template(templatename="shutdown.html", prefix='LazyLibrarian is ', title="Reopen library",
                              message=message, timer=30)

    @cherrypy.expose
    def show_Jobs(self):
        cherrypy.response.headers['Cache-Control'] = "max-age=0,no-cache,no-store"
        # show the current status of LL cron jobs
        resultlist = showJobs()
        result = ''
        for line in resultlist:
            result = result + line + '\n'
        return result

    @cherrypy.expose
    def restart_Jobs(self):
        restartJobs(start='Restart')
        # return self.show_Jobs()

    @cherrypy.expose
    def stop_Jobs(self):
        restartJobs(start='Stop')
        # return self.show_Jobs()

    # LOGGING ###########################################################

    @cherrypy.expose
    def clearLog(self):
        # Clear the log
        result = clearLog()
        logger.info(result)
        raise cherrypy.HTTPRedirect("logs")

    @cherrypy.expose
    def logHeader(self):
        # Return the log header info
        result = logHeader()
        return result

    @cherrypy.expose
    def saveLog(self):
        # Save the debug log to a zipfile
        self.label_thread('SAVELOG')
        result = saveLog()
        logger.info(result)
        raise cherrypy.HTTPRedirect("logs")

    @cherrypy.expose
    def toggleLog(self):
        # Toggle the debug log
        # LOGLEVEL 0, quiet
        # 1 normal
        # 2 debug
        # >2 extra debugging
        self.label_thread()
        if lazylibrarian.LOGLEVEL > 1:
            lazylibrarian.LOGLEVEL = 1
        else:
            if lazylibrarian.LOGLEVEL < 2:
                lazylibrarian.LOGLEVEL = 2
        if lazylibrarian.LOGLEVEL < 2:
            logger.info('Debug log OFF, loglevel is %s' % lazylibrarian.LOGLEVEL)
        else:
            logger.info('Debug log ON, loglevel is %s' % lazylibrarian.LOGLEVEL)
        raise cherrypy.HTTPRedirect("logs")

    @cherrypy.expose
    def logs(self):
        return serve_template(templatename="logs.html", title="Log", lineList=[])  # lazylibrarian.LOGLIST)

    # noinspection PyUnusedLocal
    @cherrypy.expose
    @cherrypy.tools.json_out()
    def getLog(self, iDisplayStart=0, iDisplayLength=100, iSortCol_0=0, sSortDir_0="desc", sSearch="", **kwargs):
        # kwargs is used by datatables to pass params
        rows = []
        filtered = []
        # noinspection PyBroadException
        try:
            iDisplayStart = int(iDisplayStart)
            iDisplayLength = int(iDisplayLength)
            lazylibrarian.CONFIG['DISPLAYLENGTH'] = iDisplayLength

            if sSearch:
                if lazylibrarian.LOGLEVEL & lazylibrarian.log_serverside:
                    logger.debug("filter %s" % sSearch)
                filtered = [x for x in lazylibrarian.LOGLIST[::] if sSearch.lower() in str(x).lower()]
            else:
                filtered = lazylibrarian.LOGLIST[::]

            sortcolumn = int(iSortCol_0)
            if lazylibrarian.LOGLEVEL & lazylibrarian.log_serverside:
                logger.debug("sortcolumn %d" % sortcolumn)

            filtered.sort(key=lambda y: y[sortcolumn], reverse=sSortDir_0 == "desc")
            if iDisplayLength < 0:  # display = all
                rows = filtered
            else:
                rows = filtered[iDisplayStart:(iDisplayStart + iDisplayLength)]
            if lazylibrarian.LOGLEVEL & lazylibrarian.log_serverside:
                logger.debug("getLog returning %s to %s" % (iDisplayStart, iDisplayStart + iDisplayLength))
                logger.debug("getLog filtered %s from %s:%s" % (len(filtered), len(lazylibrarian.LOGLIST), len(rows)))
        except Exception:
            logger.error('Unhandled exception in getLog: %s' % traceback.format_exc())
            rows = []
            filtered = []
        finally:
            mydict = {'iTotalDisplayRecords': len(filtered),
                      'iTotalRecords': len(lazylibrarian.LOGLIST),
                      'aaData': rows,
                      }
            return mydict

    # HISTORY ###########################################################

    @cherrypy.expose
    def history(self):
        return serve_template(templatename="history.html", title="History", history=[])

    # noinspection PyUnusedLocal
    @cherrypy.expose
    @cherrypy.tools.json_out()
    def getHistory(self, iDisplayStart=0, iDisplayLength=100, iSortCol_0=0, sSortDir_0="desc", sSearch="", **kwargs):
        # kwargs is used by datatables to pass params
        # for arg in kwargs:
        #     print arg, kwargs[arg]
        rows = []
        filtered = []
        rowlist = []
        # noinspection PyBroadException
        try:
            myDB = database.DBConnection()
            iDisplayStart = int(iDisplayStart)
            iDisplayLength = int(iDisplayLength)
            lazylibrarian.CONFIG['DISPLAYLENGTH'] = iDisplayLength
            myDB = database.DBConnection()
            cmd = "SELECT NZBTitle,AuxInfo,BookID,NZBProv,NZBDate,NZBSize,Status,Source,DownloadID,rowid from wanted"
            rowlist = myDB.select(cmd)
            # turn the sqlite rowlist into a list of dicts
            if len(rowlist):
                # the masterlist to be filled with the row data
                for row in rowlist:  # iterate through the sqlite3.Row objects
                    nrow = list(row)
                    # title needs spaces, not dots, for column resizing
                    title = nrow[0]  # type: str
                    if title:
                        title = title.replace('.', ' ')
                        title = title.replace('LL (', 'LL.(')
                        nrow[0] = title
                    # provider name needs to be shorter and with spaces for column resizing
                    if nrow[3]:
                        nrow[3] = dispName(nrow[3].strip('/'))
                        rows.append(nrow)  # add the rowlist to the masterlist

                if sSearch:
                    if lazylibrarian.LOGLEVEL & lazylibrarian.log_serverside:
                        logger.debug("filter %s" % sSearch)
                    filtered = [x for x in rows if sSearch.lower() in str(x).lower()]
                else:
                    filtered = rows

                sortcolumn = int(iSortCol_0)
                if lazylibrarian.LOGLEVEL & lazylibrarian.log_serverside:
                    logger.debug("sortcolumn %d" % sortcolumn)

                if sortcolumn == 6:
                    sortcolumn = 9

                filtered.sort(key=lambda y: y[sortcolumn], reverse=sSortDir_0 == "desc")

                if iDisplayLength < 0:  # display = all
                    nrows = filtered
                else:
                    nrows = filtered[iDisplayStart:(iDisplayStart + iDisplayLength)]

                lazylibrarian.HIST_REFRESH = 0
                rows = []
                for row in nrows:
                    # separate out rowid and other additions so we don't break legacy interface
                    rowid = row[9]
                    row = row[:9]
                    if lazylibrarian.CONFIG['HTTP_LOOK'] != 'legacy':
                        if row[6] == 'Snatched':
                            progress = getDownloadProgress(row[7], row[8])
                            row.append(progress)
                            if progress < 100:
                                lazylibrarian.HIST_REFRESH = lazylibrarian.CONFIG['HIST_REFRESH']
                        else:
                            row.append(-1)
                        row.append(rowid)
                        row.append(row[4])  # keep full datetime for tooltip
                        row[4] = dateFormat(row[4], lazylibrarian.CONFIG['DATE_FORMAT'])
                    rows.append(row)

            if lazylibrarian.LOGLEVEL & lazylibrarian.log_serverside:
                logger.debug("getHistory returning %s to %s" % (iDisplayStart, iDisplayStart + iDisplayLength))
                logger.debug("getHistory filtered %s from %s:%s" % (len(filtered), len(rowlist), len(rows)))
        except Exception:
            logger.error('Unhandled exception in getHistory: %s' % traceback.format_exc())
            rows = []
            rowlist = []
            filtered = []
        finally:
            mydict = {'iTotalDisplayRecords': len(filtered),
                      'iTotalRecords': len(rowlist),
                      'aaData': rows,
                      }
            return mydict

    @cherrypy.expose
    def bookdesc(self, bookid=None):
        global lastauthor
        myDB = database.DBConnection()
        if not bookid:
            return 'No BookID^No BookID'
        res = myDB.match("SELECT BookName,BookDesc,AuthorID from books WHERE bookid=?", (bookid,))
        if not res:
            return 'BookID not found^No Details'
        text = res['BookDesc']
        if not text:
            text = "No Description"
        lastauthor = res['AuthorID']
        return res['BookName'] + '^' + text

    @cherrypy.expose
    def dlinfo(self, target=None):
        myDB = database.DBConnection()
        if '^' not in target:
            return ''
        status, rowid = target.split('^')
        if status == 'Ignored':
            match = myDB.match('select ScanResult from books WHERE bookid=?', (rowid,))
            message = 'Reason: %s<br>' % match['ScanResult']
        else:
            cmd = 'select NZBurl,NZBtitle,NZBdate,NZBprov,Status,NZBsize,AuxInfo,NZBmode,DLResult,Source,DownloadID '
            cmd += 'from wanted where rowid=?'
            match = myDB.match(cmd, (rowid,))
            dltype = match['AuxInfo']
            if dltype not in ['eBook', 'AudioBook']:
                if not dltype:
                    dltype = 'eBook'
                else:
                    dltype = 'Magazine'
            message = "Title: %s<br>" % match['NZBtitle']
            message += "Type: %s %s<br>" % (match['NZBmode'], dltype)
            message += "Date: %s<br>" % match['NZBdate']
            message += "Size: %s Mb<br>" % match['NZBsize']
            message += "Provider: %s<br>" % dispName(match['NZBprov'])
            message += "Downloader: %s<br>" % match['Source']
            message += "DownloadID: %s<br>" % match['DownloadID']
            message += "URL: %s<br>" % match['NZBurl']
            if status == 'Processed':
                message += "File: %s<br>" % match['DLResult']
            else:
                message += "Error: %s<br>" % match['DLResult']
        return message

    @cherrypy.expose
    def deletehistory(self, rowid=None):
        myDB = database.DBConnection()
        if not rowid:
            return
        match = myDB.match('SELECT NZBtitle,Status from wanted WHERE rowid=?', (rowid,))
        if match:
            logger.debug('Deleting %s history item %s' % (match['Status'], match['NZBtitle']))
            myDB.action('DELETE from wanted WHERE rowid=?', (rowid,))

    @cherrypy.expose
    def markhistory(self, rowid=None):
        myDB = database.DBConnection()
        if not rowid:
            return
        match = myDB.match('SELECT NZBtitle,Status,BookID,AuxInfo from wanted WHERE rowid=?', (rowid,))
        logger.debug('Marking %s history item %s as Failed' % (match['Status'], match['NZBtitle']))
        myDB.action('UPDATE wanted SET Status="Failed" WHERE rowid=?', (rowid,))
        book_type = match['AuxInfo']
        if book_type not in ['AudioBook', 'eBook']:
            if not book_type:
                book_type = 'eBook'
            else:
                book_type = 'Magazine'
        if book_type == 'AudioBook':
            myDB.action('UPDATE books SET audiostatus="Wanted" WHERE BookID=?', (match['BookID'],))
        else:
            myDB.action('UPDATE books SET status="Wanted" WHERE BookID=?', (match['BookID'],))

    @cherrypy.expose
    def clearhistory(self, status=None):
        myDB = database.DBConnection()
        if not status or status == 'all':
            logger.info("Clearing all history")
            # also reset the Snatched status in book table to Wanted and cancel any failed download task
            # ONLY reset if status is still Snatched, as maybe a later task succeeded
            status = "Snatched"
            cmd = 'SELECT BookID,AuxInfo,Source,DownloadID from wanted WHERE Status=?'
            rowlist = myDB.select(cmd, (status,))
            for book in rowlist:
                if book['BookID'] != 'unknown':
                    if book['AuxInfo'] == 'eBook':
                        myDB.action('UPDATE books SET Status="Wanted" WHERE Bookid=? AND Status=?',
                                    (book['BookID'], status))
                    elif book['AuxInfo'] == 'AudioBook':
                        myDB.action('UPDATE books SET AudioStatus="Wanted" WHERE Bookid=? AND AudioStatus=?',
                                    (book['BookID'], status))
                    delete_task(book['Source'], book['DownloadID'], True)
            myDB.action("DELETE from wanted")
        else:
            logger.info("Clearing history where status is %s" % status)
            if status == 'Snatched':
                # also reset the Snatched status in book table to Wanted and cancel any failed download task
                # ONLY reset if status is still Snatched, as maybe a later task succeeded
                cmd = 'SELECT BookID,AuxInfo,Source,DownloadID from wanted WHERE Status=?'
                rowlist = myDB.select(cmd, (status,))
                for book in rowlist:
                    if book['BookID'] != 'unknown':
                        if book['AuxInfo'] == 'eBook':
                            myDB.action('UPDATE books SET Status="Wanted" WHERE Bookid=? AND Status=?',
                                        (book['BookID'], status))
                        elif book['AuxInfo'] == 'AudioBook':
                            myDB.action('UPDATE books SET AudioStatus="Wanted" WHERE Bookid=? AND AudioStatus=?',
                                        (book['BookID'], status))
                    delete_task(book['Source'], book['DownloadID'], True)
            myDB.action('DELETE from wanted WHERE Status=?', (status,))
        raise cherrypy.HTTPRedirect("history")

    @cherrypy.expose
    def testprovider(self, **kwargs):
        cherrypy.response.headers['Cache-Control'] = "max-age=0,no-cache,no-store"
        threading.currentThread().name = "TESTPROVIDER"
        if 'name' in kwargs and kwargs['name']:
            host = ''
            api = ''
            if 'host' in kwargs and kwargs['host']:
                host = kwargs['host']
            if 'api' in kwargs and kwargs['api']:
                api = kwargs['api']
            result, name = test_provider(kwargs['name'], host=host, api=api)
            if result:
                lazylibrarian.config_write(kwargs['name'])
                msg = "%s test PASSED" % name
            else:
                msg = "%s test FAILED, check debug log" % name
        else:
            msg = "Invalid or missing name in testprovider"
        return msg

    @cherrypy.expose
    def clearblocked(self):
        cherrypy.response.headers['Cache-Control'] = "max-age=0,no-cache,no-store"
        # clear any currently blocked providers
        num = len(lazylibrarian.PROVIDER_BLOCKLIST)
        lazylibrarian.PROVIDER_BLOCKLIST = []
        result = 'Cleared %s blocked provider%s' % (num, plural(num))
        logger.debug(result)
        return result

    @cherrypy.expose
    def showblocked(self):
        cherrypy.response.headers['Cache-Control'] = "max-age=0,no-cache,no-store"
        # show any currently blocked providers
        result = ''
        for line in lazylibrarian.PROVIDER_BLOCKLIST:
            resume = int(line['resume']) - int(time.time())
            if resume > 0:
                resume = int(resume / 60) + (resume % 60 > 0)
                new_entry = "%s blocked for %s minute%s, %s\n" % (line['name'], resume, plural(resume), line['reason'])
                result = result + new_entry

        if result == '':
            result = 'No blocked providers'
        logger.debug(result)
        return result

    @cherrypy.expose
    def cleardownloads(self):
        cherrypy.response.headers['Cache-Control'] = "max-age=0,no-cache,no-store"
        # clear download counters
        myDB = database.DBConnection()
        count = myDB.match('SELECT COUNT(*) as counter FROM downloads')
        if count:
            num = count['counter']
        else:
            num = 0
        result = 'Deleted download counter for %s provider%s' % (num, plural(num))
        myDB.action('DELETE from downloads')
        logger.debug(result)
        return result

    @cherrypy.expose
    def showdownloads(self):
        cherrypy.response.headers['Cache-Control'] = "max-age=0,no-cache,no-store"
        # show provider download totals
        myDB = database.DBConnection()
        result = ''
        downloads = myDB.select('SELECT Count,Provider FROM downloads ORDER BY Count DESC')
        for line in downloads:
            provname = dispName(line['Provider'].strip('/'))
            new_entry = "%4d - %s\n" % (line['Count'], provname)
            result = result + new_entry

        if result == '':
            result = 'No downloads'
        return result

    @cherrypy.expose
    def syncToCalibre(self):
        cherrypy.response.headers['Cache-Control'] = "max-age=0,no-cache,no-store"
        if 'CalSync' in [n.name for n in [t for t in threading.enumerate()]]:
            msg = 'Calibre Sync is already running'
        else:
            self.label_thread('CalSync')
            cookie = cherrypy.request.cookie
            if cookie and 'll_uid' in list(cookie.keys()):
                userid = cookie['ll_uid'].value
                msg = syncCalibreList(userid=userid)
                self.label_thread('WEBSERVER')
            else:
                msg = "No userid found"
        return msg

    @cherrypy.expose
    def syncToGoodreads(self):
        if 'GRSync' not in [n.name for n in [t for t in threading.enumerate()]]:
            cherrypy.response.headers['Cache-Control'] = "max-age=0,no-cache,no-store"
            self.label_thread('GRSync')
            msg = grsync.sync_to_gr()
            self.label_thread('WEBSERVER')
        else:
            msg = 'Goodreads Sync is already running'
        return msg

    @cherrypy.expose
    def grauthStep1(self, **kwargs):
        cherrypy.response.headers['Cache-Control'] = "max-age=0,no-cache,no-store"
        if 'gr_api' in kwargs:
            lazylibrarian.CONFIG['GR_API'] = kwargs['gr_api']
        if 'gr_secret' in kwargs:
            lazylibrarian.CONFIG['GR_SECRET'] = kwargs['gr_secret']
        GA = grsync.grauth()
        res = GA.goodreads_oauth1()
        return res

    @cherrypy.expose
    def grauthStep2(self):
        cherrypy.response.headers['Cache-Control'] = "max-age=0,no-cache,no-store"
        GA = grsync.grauth()
        return GA.goodreads_oauth2()

    @cherrypy.expose
    def testGRAuth(self, **kwargs):
        cherrypy.response.headers['Cache-Control'] = "max-age=0,no-cache,no-store"
        threading.currentThread().name = "WEBSERVER"
        if 'gr_api' in kwargs:
            lazylibrarian.CONFIG['GR_API'] = kwargs['gr_api']
        if 'gr_secret' in kwargs:
            lazylibrarian.CONFIG['GR_SECRET'] = kwargs['gr_secret']
        if 'gr_oauth_token' in kwargs:
            lazylibrarian.CONFIG['GR_OAUTH_TOKEN'] = kwargs['gr_oauth_token']
        if 'gr_oauth_secret' in kwargs:
            lazylibrarian.CONFIG['GR_OAUTH_SECRET'] = kwargs['gr_oauth_secret']
        res = grsync.test_auth()
        if res.startswith('Pass:'):
            lazylibrarian.config_write('API')
        return res

    # NOTIFIERS #########################################################

    @cherrypy.expose
    def twitterStep1(self):
        cherrypy.response.headers['Cache-Control'] = "max-age=0,no-cache,no-store"
        return notifiers.twitter_notifier._get_authorization()

    @cherrypy.expose
    def twitterStep2(self, key):
        cherrypy.response.headers['Cache-Control'] = "max-age=0,no-cache,no-store"
        if key:
            result = notifiers.twitter_notifier._get_credentials(key)
            if result:
                lazylibrarian.config_write('Twitter')
                return "Key verification successful"
            else:
                return "Unable to verify key"
        else:
            return "No Key provided"

    @cherrypy.expose
    def testTwitter(self):
        cherrypy.response.headers['Cache-Control'] = "max-age=0,no-cache,no-store"
        threading.currentThread().name = "WEBSERVER"
        result = notifiers.twitter_notifier.test_notify()
        if result:
            return "Tweet successful, check your twitter to make sure it worked"
        else:
            return "Error sending tweet"

    @cherrypy.expose
    def testAndroidPN(self, **kwargs):
        cherrypy.response.headers['Cache-Control'] = "max-age=0,no-cache,no-store"
        threading.currentThread().name = "WEBSERVER"
        if 'url' in kwargs:
            lazylibrarian.CONFIG['ANDROIDPN_URL'] = kwargs['url']
        if 'username' in kwargs:
            lazylibrarian.CONFIG['ANDROIDPN_USERNAME'] = kwargs['username']
        if 'broadcast' in kwargs:
            if kwargs['broadcast'] == 'True':
                lazylibrarian.CONFIG['ANDROIDPN_BROADCAST'] = True
            else:
                lazylibrarian.CONFIG['ANDROIDPN_BROADCAST'] = False
        result = notifiers.androidpn_notifier.test_notify()
        if result:
            lazylibrarian.config_write('AndroidPN')
            return "Test AndroidPN notice sent successfully"
        else:
            return "Test AndroidPN notice failed"

    @cherrypy.expose
    def testBoxcar(self, **kwargs):
        cherrypy.response.headers['Cache-Control'] = "max-age=0,no-cache,no-store"
        threading.currentThread().name = "WEBSERVER"
        if 'token' in kwargs:
            lazylibrarian.CONFIG['BOXCAR_TOKEN'] = kwargs['token']
        result = notifiers.boxcar_notifier.test_notify()
        if result:
            lazylibrarian.config_write('Boxcar')
            return "Boxcar notification successful,\n%s" % result
        else:
            return "Boxcar notification failed"

    @cherrypy.expose
    def testPushbullet(self, **kwargs):
        cherrypy.response.headers['Cache-Control'] = "max-age=0,no-cache,no-store"
        threading.currentThread().name = "WEBSERVER"
        if 'token' in kwargs:
            lazylibrarian.CONFIG['PUSHBULLET_TOKEN'] = kwargs['token']
        if 'device' in kwargs:
            lazylibrarian.CONFIG['PUSHBULLET_DEVICEID'] = kwargs['device']
        result = notifiers.pushbullet_notifier.test_notify()
        if result:
            lazylibrarian.config_write('PushBullet')
            return "Pushbullet notification successful,\n%s" % result
        else:
            return "Pushbullet notification failed"

    @cherrypy.expose
    def testPushover(self, **kwargs):
        cherrypy.response.headers['Cache-Control'] = "max-age=0,no-cache,no-store"
        threading.currentThread().name = "WEBSERVER"
        if 'apitoken' in kwargs:
            lazylibrarian.CONFIG['PUSHOVER_APITOKEN'] = kwargs['apitoken']
        if 'keys' in kwargs:
            lazylibrarian.CONFIG['PUSHOVER_KEYS'] = kwargs['keys']
        if 'priority' in kwargs:
            lazylibrarian.CONFIG['PUSHOVER_PRIORITY'] = check_int(kwargs['priority'], 0)
        if 'device' in kwargs:
            lazylibrarian.CONFIG['PUSHOVER_DEVICE'] = kwargs['device']

        result = notifiers.pushover_notifier.test_notify()
        if result:
            lazylibrarian.config_write('Pushover')
            return "Pushover notification successful,\n%s" % result
        else:
            return "Pushover notification failed"

    @cherrypy.expose
    def testTelegram(self, **kwargs):
        cherrypy.response.headers['Cache-Control'] = "max-age=0,no-cache,no-store"
        threading.currentThread().name = "WEBSERVER"
        if 'token' in kwargs:
            lazylibrarian.CONFIG['TELEGRAM_TOKEN'] = kwargs['token']
        if 'userid' in kwargs:
            lazylibrarian.CONFIG['TELEGRAM_USERID'] = kwargs['userid']

        result = notifiers.telegram_notifier.test_notify()
        if result:
            lazylibrarian.config_write('Telegram')
            return "Test Telegram notice sent successfully"
        else:
            return "Test Telegram notice failed"

    @cherrypy.expose
    def testProwl(self, **kwargs):
        cherrypy.response.headers['Cache-Control'] = "max-age=0,no-cache,no-store"
        threading.currentThread().name = "WEBSERVER"
        if 'apikey' in kwargs:
            lazylibrarian.CONFIG['PROWL_APIKEY'] = kwargs['apikey']
        if 'priority' in kwargs:
            lazylibrarian.CONFIG['PROWL_PRIORITY'] = check_int(kwargs['priority'], 0)

        result = notifiers.prowl_notifier.test_notify()
        if result:
            lazylibrarian.config_write('Prowl')
            return "Test Prowl notice sent successfully"
        else:
            return "Test Prowl notice failed"

    @cherrypy.expose
    def testGrowl(self, **kwargs):
        cherrypy.response.headers['Cache-Control'] = "max-age=0,no-cache,no-store"
        threading.currentThread().name = "WEBSERVER"
        if 'apikey' in kwargs:
            lazylibrarian.CONFIG['GROWL_HOST'] = kwargs['host']
        if 'priority' in kwargs:
            lazylibrarian.CONFIG['GROWL_PASSWORD'] = check_int(kwargs['password'], 0)

        result = notifiers.growl_notifier.test_notify()
        if result:
            lazylibrarian.config_write('Growl')
            return "Test Growl notice sent successfully"
        else:
            return "Test Growl notice failed"

    @cherrypy.expose
    def testNMA(self, **kwargs):
        cherrypy.response.headers['Cache-Control'] = "max-age=0,no-cache,no-store"
        threading.currentThread().name = "WEBSERVER"
        if 'apikey' in kwargs:
            lazylibrarian.CONFIG['NMA_APIKEY'] = kwargs['apikey']
        if 'priority' in kwargs:
            lazylibrarian.CONFIG['NMA_PRIORITY'] = check_int(kwargs['priority'], 0)

        result = notifiers.nma_notifier.test_notify('NMA')
        if result:
            lazylibrarian.config_write('NMA')
            return "Test NMA notice sent successfully"
        else:
            return "Test NMA notice failed"

    @cherrypy.expose
    def testSlack(self, **kwargs):
        cherrypy.response.headers['Cache-Control'] = "max-age=0,no-cache,no-store"
        threading.currentThread().name = "WEBSERVER"
        if 'token' in kwargs:
            lazylibrarian.CONFIG['SLACK_TOKEN'] = kwargs['token']
        if 'url' in kwargs:
            lazylibrarian.CONFIG['SLACK_URL'] = kwargs['url']

        result = notifiers.slack_notifier.test_notify()
        if result != "ok":
            return "Slack notification failed,\n%s" % result
        else:
            lazylibrarian.config_write('Slack')
            return "Slack notification successful"

    @cherrypy.expose
    def testCustom(self, **kwargs):
        cherrypy.response.headers['Cache-Control'] = "max-age=0,no-cache,no-store"
        threading.currentThread().name = "WEBSERVER"
        if 'script' in kwargs:
            lazylibrarian.CONFIG['CUSTOM_SCRIPT'] = kwargs['script']
        result = notifiers.custom_notifier.test_notify()
        if result is False:
            return "Custom notification failed"
        else:
            lazylibrarian.config_write('Custom')
            return "Custom notification successful"

    @cherrypy.expose
    def testEmail(self, **kwargs):
        cherrypy.response.headers['Cache-Control'] = "max-age=0,no-cache,no-store"
        threading.currentThread().name = "WEBSERVER"
        if 'tls' in kwargs:
            if kwargs['tls'] == 'True':
                lazylibrarian.CONFIG['EMAIL_TLS'] = True
            else:
                lazylibrarian.CONFIG['EMAIL_TLS'] = False
        if 'ssl' in kwargs:
            if kwargs['ssl'] == 'True':
                lazylibrarian.CONFIG['EMAIL_SSL'] = True
            else:
                lazylibrarian.CONFIG['EMAIL_SSL'] = False
        if 'sendfile' in kwargs:
            if kwargs['sendfile'] == 'True':
                lazylibrarian.CONFIG['EMAIL_SENDFILE_ONDOWNLOAD'] = True
            else:
                lazylibrarian.CONFIG['EMAIL_SENDFILE_ONDOWNLOAD'] = False
        if 'emailfrom' in kwargs:
            lazylibrarian.CONFIG['EMAIL_FROM'] = kwargs['emailfrom']
        if 'emailto' in kwargs:
            lazylibrarian.CONFIG['EMAIL_TO'] = kwargs['emailto']
        if 'server' in kwargs:
            lazylibrarian.CONFIG['EMAIL_SMTP_SERVER'] = kwargs['server']
        if 'user' in kwargs:
            lazylibrarian.CONFIG['EMAIL_SMTP_USER'] = kwargs['user']
        if 'password' in kwargs:
            lazylibrarian.CONFIG['EMAIL_SMTP_PASSWORD'] = kwargs['password']
        if 'port' in kwargs:
            lazylibrarian.CONFIG['EMAIL_SMTP_PORT'] = kwargs['port']

        result = notifiers.email_notifier.test_notify()
        if not result:
            return "Email notification failed"
        else:
            lazylibrarian.config_write('Email')
            return "Email notification successful, check your email"

    # API ###############################################################

    @cherrypy.expose
    def api(self, **kwargs):
        from lazylibrarian.api import Api
        a = Api()
        # noinspection PyArgumentList
        a.checkParams(**kwargs)
        return a.fetchData

    @cherrypy.expose
    def generateAPI(self):
        api_key = hashlib.sha224(str(random.getrandbits(256))).hexdigest()[0:32]
        lazylibrarian.CONFIG['API_KEY'] = api_key
        logger.info("New API generated")
        raise cherrypy.HTTPRedirect("config")

    # ALL ELSE ##########################################################

    @cherrypy.expose
    def forceProcess(self, source=None):
        if 'POSTPROCESS' not in [n.name for n in [t for t in threading.enumerate()]]:
            threading.Thread(target=processDir, name='POSTPROCESS', args=[True]).start()
            scheduleJob(action='Restart', target='PostProcessor')
        else:
            logger.debug('POSTPROCESS already running')
        raise cherrypy.HTTPRedirect(source)

    @cherrypy.expose
    def forceWish(self, source=None):
        if lazylibrarian.USE_WISHLIST():
            search_wishlist()
        else:
            logger.warn('WishList search called but no wishlist providers set')
        if source:
            raise cherrypy.HTTPRedirect(source)
        raise cherrypy.HTTPRedirect('books')

    @cherrypy.expose
    def forceSearch(self, source=None, title=None):
        if source == "magazines":
            if lazylibrarian.USE_NZB() or lazylibrarian.USE_TOR() \
                    or lazylibrarian.USE_RSS() or lazylibrarian.USE_DIRECT():
                if title:
                    title = title.replace('&amp;', '&')
                    self.searchForMag(bookid=title)
                elif 'SEARCHALLMAG' not in [n.name for n in [t for t in threading.enumerate()]]:
                    threading.Thread(target=search_magazines, name='SEARCHALLMAG', args=[]).start()
                    scheduleJob(action='Restart', target='search_magazines')
            else:
                logger.warn('Search called but no download providers set')
        elif source in ["books", "audio"]:
            if lazylibrarian.USE_NZB() or lazylibrarian.USE_TOR() \
                    or lazylibrarian.USE_RSS() or lazylibrarian.USE_DIRECT():
                if 'SEARCHALLBOOKS' not in [n.name for n in [t for t in threading.enumerate()]]:
                    threading.Thread(target=search_book, name='SEARCHALLBOOKS', args=[]).start()
                    scheduleJob(action='Restart', target='search_book')
                    if lazylibrarian.USE_RSS():
                        scheduleJob(action='Restart', target='search_rss_book')
            else:
                logger.warn('Search called but no download providers set')
        else:
            logger.debug("forceSearch called with bad source")
            raise cherrypy.HTTPRedirect('books')
        raise cherrypy.HTTPRedirect(source)

    @cherrypy.expose
    def manage(self, whichStatus=None, **kwargs):
        library = 'eBook'
        if 'library' in kwargs:
            library = kwargs['library']
        if not whichStatus or whichStatus == 'None':
            whichStatus = "Wanted"
        types = ['eBook']
        if lazylibrarian.SHOW_AUDIO:
            types.append('AudioBook')
        return serve_template(templatename="managebooks.html", title="Manage %ss" % library,
                              books=[], types=types, library=library, whichStatus=whichStatus)

    @cherrypy.expose
    def testDeluge(self, **kwargs):
        cherrypy.response.headers['Cache-Control'] = "max-age=0,no-cache,no-store"
        threading.currentThread().name = "WEBSERVER"
        if 'host' in kwargs:
            lazylibrarian.CONFIG['DELUGE_HOST'] = kwargs['host']
        if 'base' in kwargs:
            lazylibrarian.CONFIG['DELUGE_BASE'] = kwargs['base']
        if 'cert' in kwargs:
            lazylibrarian.CONFIG['DELUGE_CERT'] = kwargs['cert']
        if 'port' in kwargs:
            lazylibrarian.CONFIG['DELUGE_PORT'] = check_int(kwargs['port'], 0)
        if 'pwd' in kwargs:
            lazylibrarian.CONFIG['DELUGE_PASS'] = kwargs['pwd']
        if 'label' in kwargs:
            lazylibrarian.CONFIG['DELUGE_LABEL'] = kwargs['label']
        if 'user' in kwargs:
            lazylibrarian.CONFIG['DELUGE_USER'] = kwargs['user']
            # if daemon, no cert used
            lazylibrarian.CONFIG['DELUGE_CERT'] = ''
            # and host must not contain http:// or https://
            host = lazylibrarian.CONFIG['DELUGE_HOST']
            host = host.replace('https://', '').replace('http://', '')
            lazylibrarian.CONFIG['DELUGE_HOST'] = host

        try:
            if not lazylibrarian.CONFIG['DELUGE_USER']:
                # no username, talk to the webui
                msg = deluge.checkLink()
                if 'FAILED' in msg:
                    return msg
            else:
                # if there's a username, talk to the daemon directly
                client = DelugeRPCClient(lazylibrarian.CONFIG['DELUGE_HOST'],
                                         check_int(lazylibrarian.CONFIG['DELUGE_PORT'], 0),
                                         lazylibrarian.CONFIG['DELUGE_USER'],
                                         lazylibrarian.CONFIG['DELUGE_PASS'])
                client.connect()
                msg = "Deluge: Daemon connection Successful\n"
                if lazylibrarian.CONFIG['DELUGE_LABEL']:
                    labels = client.call('label.get_labels')
                    if labels:
                        if lazylibrarian.LOGLEVEL & lazylibrarian.log_dlcomms:
                            logger.debug("Valid labels: %s" % str(labels))
                    else:
                        msg += "Deluge daemon seems to have no labels set\n"

                    mylabel = lazylibrarian.CONFIG['DELUGE_LABEL'].lower()
                    if mylabel != lazylibrarian.CONFIG['DELUGE_LABEL']:
                        lazylibrarian.CONFIG['DELUGE_LABEL'] = mylabel

                    if not PY2:
                        labels = [makeUnicode(s) for s in labels]
                    if mylabel not in labels:
                        res = client.call('label.add', mylabel)
                        if not res:
                            msg += "Label [%s] was added" % lazylibrarian.CONFIG['DELUGE_LABEL']
                        else:
                            msg = str(res)
                    else:
                        msg += 'Label [%s] is valid' % lazylibrarian.CONFIG['DELUGE_LABEL']
            # success, save settings
            lazylibrarian.config_write('DELUGE')
            return msg

        except Exception as e:
            msg = "Deluge: Daemon connection FAILED\n"
            if 'Connection refused' in str(e):
                msg += str(e)
                msg += "Check Deluge daemon HOST and PORT settings"
            elif 'need more than 1 value' in str(e):
                msg += "Invalid USERNAME or PASSWORD"
            else:
                msg += type(e).__name__ + ' ' + str(e)
            return msg

    @cherrypy.expose
    def testSABnzbd(self, **kwargs):
        cherrypy.response.headers['Cache-Control'] = "max-age=0,no-cache,no-store"
        threading.currentThread().name = "WEBSERVER"
        if 'host' in kwargs:
            lazylibrarian.CONFIG['SAB_HOST'] = kwargs['host']
        if 'port' in kwargs:
            lazylibrarian.CONFIG['SAB_PORT'] = check_int(kwargs['port'], 0)
        if 'user' in kwargs:
            lazylibrarian.CONFIG['SAB_USER'] = kwargs['user']
        if 'pwd' in kwargs:
            lazylibrarian.CONFIG['SAB_PASS'] = kwargs['pwd']
        if 'api' in kwargs:
            lazylibrarian.CONFIG['SAB_API'] = kwargs['api']
        if 'cat' in kwargs:
            lazylibrarian.CONFIG['SAB_CAT'] = kwargs['cat']
        if 'subdir' in kwargs:
            lazylibrarian.CONFIG['SAB_SUBDIR'] = kwargs['subdir']
        msg = sabnzbd.checkLink()
        if 'success' in msg:
            lazylibrarian.config_write('SABnzbd')
        return msg

    @cherrypy.expose
    def testNZBget(self, **kwargs):
        cherrypy.response.headers['Cache-Control'] = "max-age=0,no-cache,no-store"
        threading.currentThread().name = "WEBSERVER"
        if 'host' in kwargs:
            lazylibrarian.CONFIG['NZBGET_HOST'] = kwargs['host']
        if 'port' in kwargs:
            lazylibrarian.CONFIG['NZBGET_PORT'] = check_int(kwargs['port'], 0)
        if 'user' in kwargs:
            lazylibrarian.CONFIG['NZBGET_USER'] = kwargs['user']
        if 'pwd' in kwargs:
            lazylibrarian.CONFIG['NZBGET_PASS'] = kwargs['pwd']
        if 'cat' in kwargs:
            lazylibrarian.CONFIG['NZBGET_CATEGORY'] = kwargs['cat']
        if 'pri' in kwargs:
            lazylibrarian.CONFIG['NZBGET_PRIORITY'] = check_int(kwargs['pri'], 0)
        msg = nzbget.checkLink()
        if 'success' in msg:
            lazylibrarian.config_write('NZBGet')
        return msg

    @cherrypy.expose
    def testTransmission(self, **kwargs):
        cherrypy.response.headers['Cache-Control'] = "max-age=0,no-cache,no-store"
        threading.currentThread().name = "WEBSERVER"
        if 'host' in kwargs:
            lazylibrarian.CONFIG['TRANSMISSION_HOST'] = kwargs['host']
        if 'base' in kwargs:
            lazylibrarian.CONFIG['TRANSMISSION_BASE'] = kwargs['base']
        if 'port' in kwargs:
            lazylibrarian.CONFIG['TRANSMISSION_PORT'] = check_int(kwargs['port'], 0)
        if 'user' in kwargs:
            lazylibrarian.CONFIG['TRANSMISSION_USER'] = kwargs['user']
        if 'pwd' in kwargs:
            lazylibrarian.CONFIG['TRANSMISSION_PASS'] = kwargs['pwd']
        msg = transmission.checkLink()
        if 'success' in msg:
            lazylibrarian.config_write('TRANSMISSION')
        return msg

    @cherrypy.expose
    def testqBittorrent(self, **kwargs):
        cherrypy.response.headers['Cache-Control'] = "max-age=0,no-cache,no-store"
        threading.currentThread().name = "WEBSERVER"
        if 'host' in kwargs:
            lazylibrarian.CONFIG['QBITTORRENT_HOST'] = kwargs['host']
        if 'port' in kwargs:
            lazylibrarian.CONFIG['QBITTORRENT_PORT'] = check_int(kwargs['port'], 0)
        if 'user' in kwargs:
            lazylibrarian.CONFIG['QBITTORRENT_USER'] = kwargs['user']
        if 'pwd' in kwargs:
            lazylibrarian.CONFIG['QBITTORRENT_PASS'] = kwargs['pwd']
        if 'label' in kwargs:
            lazylibrarian.CONFIG['QBITTORRENT_LABEL'] = kwargs['label']
        msg = qbittorrent.checkLink()
        if 'success' in msg:
            lazylibrarian.config_write('QBITTORRENT')
        return msg

    @cherrypy.expose
    def testuTorrent(self, **kwargs):
        cherrypy.response.headers['Cache-Control'] = "max-age=0,no-cache,no-store"
        threading.currentThread().name = "WEBSERVER"
        if 'host' in kwargs:
            lazylibrarian.CONFIG['UTORRENT_HOST'] = kwargs['host']
        if 'port' in kwargs:
            lazylibrarian.CONFIG['UTORRENT_PORT'] = check_int(kwargs['port'], 0)
        if 'user' in kwargs:
            lazylibrarian.CONFIG['UTORRENT_USER'] = kwargs['user']
        if 'pwd' in kwargs:
            lazylibrarian.CONFIG['UTORRENT_PASS'] = kwargs['pwd']
        if 'label' in kwargs:
            lazylibrarian.CONFIG['UTORRENT_LABEL'] = kwargs['label']
        msg = utorrent.checkLink()
        if 'success' in msg:
            lazylibrarian.config_write('UTORRENT')
        return msg

    @cherrypy.expose
    def testrTorrent(self, **kwargs):
        cherrypy.response.headers['Cache-Control'] = "max-age=0,no-cache,no-store"
        threading.currentThread().name = "WEBSERVER"
        if 'host' in kwargs:
            lazylibrarian.CONFIG['RTORRENT_HOST'] = kwargs['host']
        if 'dir' in kwargs:
            lazylibrarian.CONFIG['RTORRENT_DIR'] = kwargs['dir']
        if 'user' in kwargs:
            lazylibrarian.CONFIG['RTORRENT_USER'] = kwargs['user']
        if 'pwd' in kwargs:
            lazylibrarian.CONFIG['RTORRENT_PASS'] = kwargs['pwd']
        if 'label' in kwargs:
            lazylibrarian.CONFIG['RTORRENT_LABEL'] = kwargs['label']
        msg = rtorrent.checkLink()
        if 'success' in msg:
            lazylibrarian.config_write('RTORRENT')
        return msg

    @cherrypy.expose
    def testSynology(self, **kwargs):
        cherrypy.response.headers['Cache-Control'] = "max-age=0,no-cache,no-store"
        threading.currentThread().name = "WEBSERVER"
        if 'host' in kwargs:
            lazylibrarian.CONFIG['SYNOLOGY_HOST'] = kwargs['host']
        if 'port' in kwargs:
            lazylibrarian.CONFIG['SYNOLOGY_PORT'] = check_int(kwargs['port'], 0)
        if 'user' in kwargs:
            lazylibrarian.CONFIG['SYNOLOGY_USER'] = kwargs['user']
        if 'pwd' in kwargs:
            lazylibrarian.CONFIG['SYNOLOGY_PASS'] = kwargs['pwd']
        if 'dir' in kwargs:
            lazylibrarian.CONFIG['SYNOLOGY_DIR'] = kwargs['dir']
        msg = synology.checkLink()
        if 'success' in msg:
            lazylibrarian.config_write('SYNOLOGY')
        return msg

    @cherrypy.expose
    def testCalibredb(self, **kwargs):
        threading.currentThread().name = "WEBSERVER"
        cherrypy.response.headers['Cache-Control'] = "max-age=0,no-cache,no-store"
        if 'prg' in kwargs and kwargs['prg']:
            lazylibrarian.CONFIG['IMP_CALIBREDB'] = kwargs['prg']
        return calibreTest()

    @cherrypy.expose
    def testPreProcessor(self, **kwargs):
        threading.currentThread().name = "WEBSERVER"
        cherrypy.response.headers['Cache-Control'] = "max-age=0,no-cache,no-store"
        if 'prg' in kwargs and kwargs['prg']:
            lazylibrarian.CONFIG['IMP_PREPROCESS'] = kwargs['prg']

        params = [lazylibrarian.CONFIG['IMP_PREPROCESS'], 'test', '']
        rc, res, err = runScript(params)
        if rc:
            return "Preprocessor returned %s: res[%s] err[%s]" % (rc, res, err)
        return res

    @cherrypy.expose
    def opds(self, **kwargs):
        op = OPDS()
        op.checkParams(**kwargs)
        data = op.fetchData()
        return data

    @staticmethod
    def send_file(basefile, name=None):
        if lazylibrarian.CONFIG['USER_ACCOUNTS']:
            myDB = database.DBConnection()
            cookie = cherrypy.request.cookie
            if cookie and 'll_uid' in list(cookie.keys()):
                res = myDB.match('SELECT SendTo from users where UserID=?', (cookie['ll_uid'].value,))
                if res and res['SendTo']:
                    fsize = check_int(os.path.getsize(basefile), 0)
                    if fsize > 20000000:
                        msg = '%s is too large (%s) to email' % (os.path.split(basefile)[1], fsize)
                        logger.debug(msg)
                    else:
                        logger.debug("Emailing %s to %s" % (basefile, res['SendTo']))
                        if name:
                            msg = name + ' is attached'
                        else:
                            msg = ''
                        result = notifiers.email_notifier.email_file(subject="Message from LazyLibrarian",
                                                                     message=msg, to_addr=res['SendTo'],
                                                                     files=[basefile])
                        if result:
                            msg = "Emailed file %s to %s" % (os.path.split(basefile)[1], res['SendTo'])
                            logger.debug(msg)
                        else:
                            msg = "Failed to email file %s to %s" % (os.path.split(basefile)[1], res['SendTo'])
                            logger.error(msg)
                    return serve_template(templatename="choosetype.html", prefix="SendTo", title='Send file',
                                          pop_message=msg, pop_types='', bookid='', valid='')

        if name and name.endswith('zip'):
            return serve_file(basefile, mimeType(basefile), "attachment", name=name)
        return serve_file(basefile, mimeType(basefile), "attachment")
