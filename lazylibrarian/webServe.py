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
import hashlib
import os
import random
import re
import threading
import time
import urllib
from shutil import copyfile, rmtree

import cherrypy
import lazylibrarian
import lib.simplejson as simplejson
from cherrypy.lib.static import serve_file
from lazylibrarian import logger, database, notifiers, versioncheck, magazinescan, \
    qbittorrent, utorrent, rtorrent, transmission, sabnzbd, nzbget, deluge, synology, grsync
from lazylibrarian.bookwork import setSeries, deleteEmptySeries, getSeriesAuthors, getBookCover
from lazylibrarian.cache import cache_img
from lazylibrarian.calibre import calibredb
from lazylibrarian.common import showJobs, restartJobs, clearLog, scheduleJob, checkRunningJobs, setperm, \
    aaUpdate, csv_file, saveLog, logHeader, pwd_generator, pwd_check, isValidEmail
from lazylibrarian.csvfile import import_CSV, export_CSV
from lazylibrarian.downloadmethods import NZBDownloadMethod, TORDownloadMethod, DirectDownloadMethod
from lazylibrarian.formatter import unaccented, unaccented_str, plural, now, today, check_int, replace_all, \
    safe_unicode, cleanName, surnameFirst, sortDefinite, getList
from lazylibrarian.gb import GoogleBooks
from lazylibrarian.gr import GoodReads
from lazylibrarian.importer import addAuthorToDB, addAuthorNameToDB, update_totals, search_for
from lazylibrarian.librarysync import LibraryScan
from lazylibrarian.manualbook import searchItem
from lazylibrarian.notifiers import notify_snatch, custom_notify_snatch
from lazylibrarian.postprocess import processAlternate, processDir
from lazylibrarian.searchbook import search_book
from lazylibrarian.searchmag import search_magazines
from lazylibrarian.calibre import calibreTest
from lib.deluge_client import DelugeRPCClient
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
        if cookie and 'll_uid' in cookie.keys():
            res = myDB.match('SELECT UserName,Perms from users where UserID=?', (cookie['ll_uid'].value,))
        else:
            cnt = myDB.match("select count('UserID') as counter from users")
            if cnt['counter'] == 1 and lazylibrarian.CONFIG['SINGLE_USER']:
                res = myDB.match('SELECT UserName,Perms,UserID from users')
                cherrypy.response.cookie['ll_uid'] = res['UserID']
                logger.debug("Auto-login for %s" % res['UserName'])
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
        elif templatename in ['series.html', 'members.html'] and not perm & lazylibrarian.perm_series:
            logger.warn('User %s attempted to access %s' % (username, templatename))
            templatename = "login.html"
        elif templatename in ['editauthor.html', 'editbook.html'] and not perm & lazylibrarian.perm_edit:
            logger.warn('User %s attempted to access %s' % (username, templatename))
            templatename = "login.html"
        elif templatename in ['manualsearch.html', 'searchresults.html'] and not perm & lazylibrarian.perm_search:
            logger.warn('User %s attempted to access %s' % (username, templatename))
            templatename = "login.html"

        if lazylibrarian.LOGLEVEL > 3:
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
        if cookie and 'll_uid' in cookie.keys():
            myDB = database.DBConnection()
            user = myDB.match('SELECT UserName,Name,Email from users where UserID=?', (cookie['ll_uid'].value,))
            if user:
                return serve_template(templatename="profile.html", title=title, user=user)
        return serve_template(templatename="index.html", title=title, authors=[])

    # noinspection PyUnusedLocal
    @cherrypy.expose
    @cherrypy.tools.json_out()
    def getIndex(self, iDisplayStart=0, iDisplayLength=100, iSortCol_0=0, sSortDir_0="desc", sSearch="", **kwargs):
        # kwargs is used by datatables to pass params
        # for arg in kwargs:
        #     print arg, kwargs[arg]
        myDB = database.DBConnection()
        iDisplayStart = int(iDisplayStart)
        iDisplayLength = int(iDisplayLength)
        lazylibrarian.CONFIG['DISPLAYLENGTH'] = iDisplayLength

        cmd = 'SELECT AuthorImg,AuthorName,LastBook,LastDate,Status'
        cmd += ',AuthorLink,LastLink,HaveBooks,UnignoredBooks,AuthorID from authors '
        if lazylibrarian.IGNORED_AUTHORS:
            cmd += 'where Status == "Ignored" '
        else:
            cmd += 'where Status != "Ignored" '
        cmd += 'order by AuthorName COLLATE NOCASE'
        rowlist = myDB.select(cmd)
        # At his point we want to sort and filter _before_ adding the html as it's much quicker
        # turn the sqlite rowlist into a list of lists
        rows = []
        filtered = []
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
                    percent = (havebooks * 100.0) / totalbooks
                else:
                    percent = 0
                if percent > 100:
                    percent = 100
                if percent <= 100:
                    css = 'success'
                if percent <= 75:
                    css = 'info'
                if percent <= 50:
                    css = 'warning'
                if percent <= 25:
                    css = 'danger'

                nrow.append(percent)  # convert have/total into a float
                nrow.extend(arow[4:])
                if lazylibrarian.CONFIG['HTTP_LOOK'] == 'legacy':
                    bar = '<div class="progress-container %s">' % css
                    bar += '<div style="width:%s%%"><span class="progressbar-front-text">' % percent
                    bar += '%s/%s</span></div>' % (havebooks, totalbooks)
                else:
                    bar = '<div class="progress center-block" style="width: 150px;">'
                    bar += '<div class="progress-bar-%s progress-bar progress-bar-striped" role="progressbar"' % css
                    bar += 'aria-valuenow="%s" aria-valuemin="0" aria-valuemax="100" style="width: %s%%;">' % (
                        percent, percent)
                    bar += '<span class="sr-only">%s%% Complete</span>' % percent
                    bar += '<span class="progressbar-front-text">%s/%s</span></div></div>' % (havebooks, totalbooks)
                nrow.append(bar)
                rows.append(nrow)  # add each rowlist to the masterlist
            if sSearch:
                filtered = filter(lambda x: sSearch.lower() in str(x).lower(), rows)
            else:
                filtered = rows
            sortcolumn = int(iSortCol_0)
            filtered.sort(key=lambda x: x[sortcolumn], reverse=sSortDir_0 == "desc")

            if iDisplayLength < 0:  # display = all
                rows = filtered
            else:
                rows = filtered[iDisplayStart:(iDisplayStart + iDisplayLength)]

        if lazylibrarian.LOGLEVEL > 3:
            logger.debug("getIndex returning %s to %s" % (iDisplayStart, iDisplayStart + iDisplayLength))
            logger.debug("getIndex filtered %s from %s:%s" % (len(filtered), len(rowlist), len(rows)))
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
        if cookie and 'll_uid' in cookie.keys():
            userid = cookie['ll_uid'].value
            myDB = database.DBConnection()
            user = myDB.match('SELECT UserName,Name,Email,Password from users where UserID=?', (userid,))
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

                if kwargs['email'] and user['Email'] != kwargs['email']:
                    changes += ' email'
                    myDB.action('UPDATE users SET email=? WHERE UserID=?', (kwargs['email'], userid))

                if kwargs['password']:
                    pwd = hashlib.md5(kwargs['password']).hexdigest()
                    if pwd != user['password']:
                        changes += ' password'
                        myDB.action('UPDATE users SET password=? WHERE UserID=?', (pwd, userid))
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
        if not cookie or 'll_uid' not in cookie.keys():
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
            pwd = hashlib.md5(password).hexdigest()
            res = myDB.match('SELECT UserID, Password from users where username=?', (username,))  # type: dict
        if res and pwd == res['Password']:
            cherrypy.response.cookie['ll_uid'] = res['UserID']
            if 'remember' in kwargs:
                cherrypy.response.cookie['ll_uid']['Max-Age'] = '86400'

            # successfully logged in, clear any failed attempts
            lazylibrarian.USER_BLOCKLIST[:] = [x for x in lazylibrarian.USER_BLOCKLIST if not x[0] == username]
            logger.debug("User %s logged in" % username)
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
        users = myDB.select('SELECT UserID, UserName, Name, Email, Perms from users')
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
            return simplejson.dumps({'email': match['Email'], 'name': match['Name'], 'perms': match['Perms'], })
        return simplejson.dumps({'email': '', 'name': '', 'perms': '0', })

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
                cmd = 'INSERT into users (UserID, UserName, Name, Password, Email, Perms) VALUES (?, ?, ?, ?, ?, ?)'
                myDB.action(cmd, (pwd_generator(), kwargs['username'], kwargs['fullname'],
                                  hashlib.md5(kwargs['password']).hexdigest(), kwargs['email'], perms))
                msg = "New user added: %s: %s" % (kwargs['username'], perm_msg)
                msg += "<br>Email sent to %s" % kwargs['email']
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
            details = myDB.match('SELECT UserID,Name,Email,Password,Perms from users where UserName=?', (user,))
            if details:
                userid = details['UserID']
                if kwargs['username'] and kwargs['username'] != user:
                    changes += ' username'
                    myDB.action('UPDATE users SET UserName=? WHERE UserID=?', (kwargs['username'], userid))

                if kwargs['fullname'] and details['Name'] != kwargs['fullname']:
                    changes += ' name'
                    myDB.action('UPDATE users SET Name=? WHERE UserID=?', (kwargs['fullname'], userid))

                if kwargs['email'] and details['Email'] != kwargs['email']:
                    if not isValidEmail(kwargs['email']):
                        return "Invalid email given"
                    changes += ' email'
                    myDB.action('UPDATE users SET email=? WHERE UserID=?', (kwargs['email'], userid))

                if kwargs['password']:
                    pwd = hashlib.md5(kwargs['password']).hexdigest()
                    if pwd != details['Password']:
                        changes += ' password'
                        myDB.action('UPDATE users SET password=? WHERE UserID=?', (pwd, userid))
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
                pwd = hashlib.md5(new_pwd).hexdigest()
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
        # kwargs is used by datatables to pass params
        iDisplayStart = int(iDisplayStart)
        iDisplayLength = int(iDisplayLength)
        lazylibrarian.CONFIG['DISPLAYLENGTH'] = iDisplayLength

        whichStatus = 'All'
        if kwargs['whichStatus']:
            whichStatus = kwargs['whichStatus']

        AuthorID = None
        if kwargs['AuthorID']:
            AuthorID = kwargs['AuthorID']

        myDB = database.DBConnection()
        # We pass series.SeriesID twice for datatables as the render function modifies it
        # and we need it in two columns. There is probably a better way...
        cmd = 'SELECT series.SeriesID,AuthorName,SeriesName,series.Status,seriesauthors.AuthorID,series.SeriesID'
        cmd += ' from series,authors,seriesauthors'
        cmd += ' where authors.AuthorID=seriesauthors.AuthorID and series.SeriesID=seriesauthors.SeriesID'
        args = []
        if whichStatus not in ['All', 'None']:
            cmd += ' and series.Status=?'
            args.append(whichStatus)
        if AuthorID and not AuthorID == 'None':
            cmd += ' and seriesauthors.AuthorID=?'
            args.append(AuthorID)
        cmd += ' GROUP BY series.seriesID'
        cmd += ' order by AuthorName,SeriesName'
        if args:
            rowlist = myDB.select(cmd, tuple(args))
        else:
            rowlist = myDB.select(cmd)

        # turn the sqlite rowlist into a list of lists
        filtered = []
        rows = []

        if len(rowlist):
            # the masterlist to be filled with the row data
            for row in rowlist:  # iterate through the sqlite3.Row objects
                entry = list(row)
                if lazylibrarian.CONFIG['SORT_SURNAME']:
                    entry[1] = surnameFirst(entry[1])
                rows.append(entry)  # add the rowlist to the masterlist

            if sSearch:
                filtered = filter(lambda x: sSearch.lower() in str(x).lower(), rows)
            else:
                filtered = rows

            sortcolumn = int(iSortCol_0)
            filtered.sort(key=lambda x: x[sortcolumn], reverse=sSortDir_0 == "desc")

            if iDisplayLength < 0:  # display = all
                rows = filtered
            else:
                rows = filtered[iDisplayStart:(iDisplayStart + iDisplayLength)]

        if lazylibrarian.LOGLEVEL > 3:
            logger.debug("getSeries returning %s to %s" % (iDisplayStart, iDisplayStart + iDisplayLength))
            logger.debug("getSeries filtered %s from %s:%s" % (len(filtered), len(rowlist), len(rows)))
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
            if cookie and 'll_uid' in cookie.keys():
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
                    flag = '&nbsp;<i class="fa fa-bookmark-o"></i>'
                elif entry[0] in HaveRead:
                    flag = '&nbsp;<i class="fa fa-bookmark"></i>'
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
        if action:
            for seriesid in args:
                # ouch dirty workaround...
                if not seriesid == 'book_table_length':
                    if action in ["Wanted", "Active", "Skipped", "Ignored"]:
                        match = myDB.match('SELECT SeriesName from series WHERE SeriesID=?', (seriesid,))
                        if match:
                            myDB.upsert("series", {'Status': action}, {'SeriesID': seriesid})
                            logger.debug('Status set to "%s" for "%s"' % (action, match['SeriesName']))
                            if action in ['Wanted', 'Active']:
                                threading.Thread(target=getSeriesAuthors, name='SERIESAUTHORS', args=[seriesid]).start()
                    elif action in ["Unread", "Read", "ToRead"]:
                        cookie = cherrypy.request.cookie
                        if cookie and 'll_uid' in cookie.keys():
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
    def config(self):
        self.label_thread('CONFIG')
        http_look_dir = os.path.join(lazylibrarian.PROG_DIR, 'data' + os.sep + 'interfaces')
        http_look_list = [name for name in os.listdir(http_look_dir)
                          if os.path.isdir(os.path.join(http_look_dir, name))]
        status_list = ['Skipped', 'Wanted', 'Have', 'Ignored']

        myDB = database.DBConnection()
        mags_list = []

        magazines = myDB.select('SELECT Title,Reject,Regex from magazines ORDER by Title COLLATE NOCASE')

        if magazines:
            for mag in magazines:
                title = mag['Title']
                regex = mag['Regex']
                if regex is None:
                    regex = ""
                reject = mag['Reject']
                if reject is None:
                    reject = ""
                mags_list.append({
                    'Title': title,
                    'Reject': reject,
                    'Regex': regex
                })

        # Don't pass the whole config, no need to pass the
        # lazylibrarian.globals
        config = {
            "http_look_list": http_look_list,
            "status_list": status_list,
            "magazines_list": mags_list
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
                    if admin['password'] == hashlib.md5('admin').hexdigest():
                        adminmsg += "The default admin user is 'admin' and password is 'admin'<br>"
                        adminmsg += "This is insecure, please change it on Config -> User Admin<br>"

        # first the non-config options
        if 'current_tab' in kwargs:
            lazylibrarian.CURRENT_TAB = kwargs['current_tab']

        interface = lazylibrarian.CFG.get('General', 'http_look')
        # now the config file entries
        for key in lazylibrarian.CONFIG_DEFINITIONS.keys():
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
                # default interface doesn't know about download priorities
                elif interface == 'legacy' and 'dlpriority' in key.lower():
                    pass
                # no key is returned for empty tickboxes...
                elif item_type == 'bool':
                    # print "No entry for bool " + key
                    lazylibrarian.CONFIG[key] = 0
                # or empty string values
                else:
                    # print "No entry for str " + key
                    lazylibrarian.CONFIG[key] = ''

        magazines = myDB.select('SELECT Title,Reject,Regex from magazines ORDER by upper(Title)')

        if magazines:
            count = 0
            for mag in magazines:
                title = mag['Title']
                reject = mag['Reject']
                regex = mag['Regex']
                # seems kwargs parameters from cherrypy are passed as latin-1, can't see how to
                # configure it, so we need to correct it on accented magazine names
                # eg "Elle Quebec" where we might have e-acute stored as unicode
                # e-acute is \xe9 in latin-1  but  \xc3\xa9 in utf-8
                # otherwise the comparison fails, but sometimes accented characters won't
                # fit latin-1 but fit utf-8 how can we tell ???
                # Check if we're a python 2 str, python3 str doesn't have "decode"
                if isinstance(title, str) and hasattr(title, "decode"):
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
            if count:
                logger.info("Magazine filters updated")

        count = 0
        while count < len(lazylibrarian.NEWZNAB_PROV):
            lazylibrarian.NEWZNAB_PROV[count]['ENABLED'] = bool(kwargs.get(
                'newznab[%i][enabled]' % count, False))
            lazylibrarian.NEWZNAB_PROV[count]['HOST'] = kwargs.get(
                'newznab[%i][host]' % count, '')
            lazylibrarian.NEWZNAB_PROV[count]['API'] = kwargs.get(
                'newznab[%i][api]' % count, '')
            lazylibrarian.NEWZNAB_PROV[count]['GENERALSEARCH'] = kwargs.get(
                'newznab[%i][generalsearch]' % count, '')
            lazylibrarian.NEWZNAB_PROV[count]['BOOKSEARCH'] = kwargs.get(
                'newznab[%i][booksearch]' % count, '')
            lazylibrarian.NEWZNAB_PROV[count]['MAGSEARCH'] = kwargs.get(
                'newznab[%i][magsearch]' % count, '')
            lazylibrarian.NEWZNAB_PROV[count]['AUDIOSEARCH'] = kwargs.get(
                'newznab[%i][audiosearch]' % count, '')
            lazylibrarian.NEWZNAB_PROV[count]['BOOKCAT'] = kwargs.get(
                'newznab[%i][bookcat]' % count, '')
            lazylibrarian.NEWZNAB_PROV[count]['MAGCAT'] = kwargs.get(
                'newznab[%i][magcat]' % count, '')
            lazylibrarian.NEWZNAB_PROV[count]['AUDIOCAT'] = kwargs.get(
                'newznab[%i][audiocat]' % count, '')
            lazylibrarian.NEWZNAB_PROV[count]['EXTENDED'] = kwargs.get(
                'newznab[%i][extended]' % count, '')
            lazylibrarian.NEWZNAB_PROV[count]['UPDATED'] = kwargs.get(
                'newznab[%i][updated]' % count, '')
            lazylibrarian.NEWZNAB_PROV[count]['MANUAL'] = bool(kwargs.get(
                'newznab[%i][manual]' % count, False))
            if interface != 'legacy':
                lazylibrarian.NEWZNAB_PROV[count]['DLPRIORITY'] = check_int(kwargs.get(
                    'newznab[%i][dlpriority]' % count, 0), 0)
            count += 1

        count = 0
        while count < len(lazylibrarian.TORZNAB_PROV):
            lazylibrarian.TORZNAB_PROV[count]['ENABLED'] = bool(kwargs.get(
                'torznab[%i][enabled]' % count, False))
            lazylibrarian.TORZNAB_PROV[count]['HOST'] = kwargs.get(
                'torznab[%i][host]' % count, '')
            lazylibrarian.TORZNAB_PROV[count]['API'] = kwargs.get(
                'torznab[%i][api]' % count, '')
            lazylibrarian.TORZNAB_PROV[count]['GENERALSEARCH'] = kwargs.get(
                'torznab[%i][generalsearch]' % count, '')
            lazylibrarian.TORZNAB_PROV[count]['BOOKSEARCH'] = kwargs.get(
                'torznab[%i][booksearch]' % count, '')
            lazylibrarian.TORZNAB_PROV[count]['MAGSEARCH'] = kwargs.get(
                'torznab[%i][magsearch]' % count, '')
            lazylibrarian.TORZNAB_PROV[count]['AUDIOSEARCH'] = kwargs.get(
                'torznab[%i][audiosearch]' % count, '')
            lazylibrarian.TORZNAB_PROV[count]['BOOKCAT'] = kwargs.get(
                'torznab[%i][bookcat]' % count, '')
            lazylibrarian.TORZNAB_PROV[count]['MAGCAT'] = kwargs.get(
                'torznab[%i][magcat]' % count, '')
            lazylibrarian.TORZNAB_PROV[count]['AUDIOCAT'] = kwargs.get(
                'torznab[%i][audiocat]' % count, '')
            lazylibrarian.TORZNAB_PROV[count]['EXTENDED'] = kwargs.get(
                'torznab[%i][extended]' % count, '')
            lazylibrarian.TORZNAB_PROV[count]['UPDATED'] = kwargs.get(
                'torznab[%i][updated]' % count, '')
            lazylibrarian.TORZNAB_PROV[count]['MANUAL'] = bool(kwargs.get(
                'torznab[%i][manual]' % count, False))
            if interface != 'legacy':
                lazylibrarian.TORZNAB_PROV[count]['DLPRIORITY'] = check_int(kwargs.get(
                    'torznab[%i][dlpriority]' % count, 0), 0)
            count += 1

        count = 0
        while count < len(lazylibrarian.RSS_PROV):
            lazylibrarian.RSS_PROV[count]['ENABLED'] = bool(kwargs.get('rss[%i][enabled]' % count, False))
            lazylibrarian.RSS_PROV[count]['HOST'] = kwargs.get('rss[%i][host]' % count, '')
            if interface != 'legacy':
                lazylibrarian.RSS_PROV[count]['DLPRIORITY'] = check_int(kwargs.get(
                    'rss[%i][dlpriority]' % count, 0), 0)
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
        if name is None or not name:
            raise cherrypy.HTTPRedirect("home")

        myDB = database.DBConnection()

        authorids = myDB.select("SELECT AuthorID from authors")
        authorlist = []
        for item in authorids:
            authorlist.append(item['AuthorID'])

        booksearch = myDB.select("SELECT Status,BookID from books")
        booklist = []
        for item in booksearch:
            booklist.append(item['BookID'])

        searchresults = search_for(name)
        return serve_template(templatename="searchresults.html", title='Search Results: "' + name + '"',
                              searchresults=searchresults, authorlist=authorlist,
                              booklist=booklist, booksearch=booksearch)

    # AUTHOR ############################################################

    @cherrypy.expose
    def authorPage(self, AuthorID, BookLang=None, library='eBook', Ignored=False):
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
        authorname = author['AuthorName']
        authorname = authorname.encode(lazylibrarian.SYS_ENCODING)

        return serve_template(
            templatename="author.html", title=urllib.quote_plus(authorname),
            author=author, languages=languages, booklang=BookLang, types=types, library=library, ignored=Ignored,
            showseries=lazylibrarian.SHOW_SERIES)

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
                u'AuthorID [%s]-[%s] %s - redirecting to Author home page' % (AuthorID, AuthorName, status))
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
            myDB.action('DELETE from seriesauthors WHERE AuthorID=?', (AuthorID,))
            myDB.action('DELETE from books WHERE AuthorID=?', (AuthorID,))
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
                authordir = safe_unicode(os.path.join(lazylibrarian.DIRECTORY('Audio'), AuthorName))
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
        raise cherrypy.HTTPRedirect("home")

    @cherrypy.expose
    def toggleAuth(self):
        if lazylibrarian.IGNORED_AUTHORS:  # show ignored ones, or active ones
            lazylibrarian.IGNORED_AUTHORS = False
        else:
            lazylibrarian.IGNORED_AUTHORS = True
        raise cherrypy.HTTPRedirect("home")

    # BOOKS #############################################################

    @cherrypy.expose
    def booksearch(self, author=None, title=None, bookid=None, action=None):
        self.label_thread('BOOKSEARCH')
        if '_title' in action:
            searchterm = title
        elif '_author' in action:
            searchterm = author
        else:  # if '_full' in action:
            searchterm = '%s %s' % (author, title)
            searchterm = searchterm.strip()

        if action == 'e_full':
            cat = 'book'
        elif action == 'a_full':
            cat = 'audio'
        else:
            cat = 'general'

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
            url = urllib.unquote_plus(url)
            url = url.replace(' ', '+')
            bookname = '%s LL.(%s)' % (bookdata["BookName"], bookid)
            if 'libgen' in provider:  # for libgen we use direct download links
                snatch = DirectDownloadMethod(bookid, bookname, url, bookdata["BookName"], library)
            elif mode in ["torznab", "torrent", "magnet"]:
                snatch = TORDownloadMethod(bookid, bookname, url, library)
            else:
                snatch = NZBDownloadMethod(bookid, bookname, url, library)
            if snatch:
                logger.info('Downloading %s %s from %s' % (library, bookdata["BookName"], provider))
                notify_snatch("%s from %s at %s" % (unaccented(bookdata["BookName"]), provider, now()))
                custom_notify_snatch(bookid)
                scheduleJob(action='Start', target='processDir')
            raise cherrypy.HTTPRedirect("authorPage?AuthorID=%s&library=%s" % (AuthorID, library))
        else:
            logger.debug('snatchBook Invalid bookid [%s]' % bookid)
            raise cherrypy.HTTPRedirect("home")

    @cherrypy.expose
    def audio(self, BookLang=None):
        myDB = database.DBConnection()
        if BookLang == '':
            BookLang = None
        languages = myDB.select(
            'SELECT DISTINCT BookLang from books WHERE AUDIOSTATUS !="Skipped" AND AUDIOSTATUS !="Ignored"')
        return serve_template(templatename="audio.html", title='AudioBooks', books=[],
                              languages=languages, booklang=BookLang)

    @cherrypy.expose
    def books(self, BookLang=None):
        myDB = database.DBConnection()
        if BookLang == '' or BookLang == 'None':
            BookLang = None
        languages = myDB.select('SELECT DISTINCT BookLang from books WHERE STATUS !="Skipped" AND STATUS !="Ignored"')
        return serve_template(templatename="books.html", title='Books', books=[],
                              languages=languages, booklang=BookLang)

    @cherrypy.expose
    @cherrypy.tools.json_out()
    def getBooks(self, iDisplayStart=0, iDisplayLength=100, iSortCol_0=0, sSortDir_0="desc", sSearch="", **kwargs):
        # kwargs is used by datatables to pass params
        # for arg in kwargs:
        #     print arg, kwargs[arg]

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
            if cookie and 'll_uid' in cookie.keys():
                res = myDB.match('SELECT UserName,ToRead,HaveRead,Perms from users where UserID=?',
                                 (cookie['ll_uid'].value,))
                if res:
                    perm = check_int(res['Perms'], 0)
                    ToRead = getList(res['ToRead'])
                    HaveRead = getList(res['HaveRead'])

                    if lazylibrarian.LOGLEVEL > 3:
                        logger.debug("getBooks userid %s read %s,%s" % (
                            cookie['ll_uid'].value, len(ToRead), len(HaveRead)))

        iDisplayStart = int(iDisplayStart)
        iDisplayLength = int(iDisplayLength)
        lazylibrarian.CONFIG['DISPLAYLENGTH'] = iDisplayLength

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

        library = None
        status_type = 'books.status'
        args = []
        if kwargs['source'] == "Manage":
            if kwargs['whichStatus'] == 'ToRead':
                cmd += ' and books.bookID in (' + ', '.join(ToRead) + ')'
            elif kwargs['whichStatus'] == 'Read':
                cmd += ' and books.bookID in (' + ', '.join(HaveRead) + ')'
            else:
                cmd += ' and books.STATUS="' + kwargs['whichStatus'] + '"'
        elif kwargs['source'] == "Books":
            cmd += ' and books.STATUS !="Skipped" AND books.STATUS !="Ignored"'
        elif kwargs['source'] == "Audio":
            cmd += ' and AUDIOSTATUS !="Skipped" AND AUDIOSTATUS !="Ignored"'
            status_type = 'audiostatus'
        elif kwargs['source'] == "Author":
            library = 'eBook'
            if 'library' in kwargs:
                library = kwargs['library']

            if library == 'AudioBook':
                status_type = 'audiostatus'
            else:
                status_type = 'books.status'

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
            cmd += ' GROUP BY bookimg, authorname, bookname, bookrate, bookdate, books.status, books.bookid, booklang,'
            cmd += ' booksub, booklink, workpage, books.authorid, seriesdisplay, booklibrary, audiostatus, audiolibrary'
        rowlist = myDB.select(cmd, tuple(args))

        # At his point we want to sort and filter _before_ adding the html as it's much quicker
        # turn the sqlite rowlist into a list of lists
        rows = []
        filtered = []
        if len(rowlist):
            for row in rowlist:  # iterate through the sqlite3.Row objects
                entry = list(row)
                if lazylibrarian.CONFIG['SORT_SURNAME']:
                    entry[1] = surnameFirst(entry[1])
                if lazylibrarian.CONFIG['SORT_DEFINITE']:
                    entry[2] = sortDefinite(entry[2])
                rows.append(entry)  # add each rowlist to the masterlist

            if sSearch:
                if library is not None:
                    if library == 'AudioBook':
                        searchFields = ['AuthorName', 'BookName', 'BookRate', 'BookDate', 'AudioStatus',
                                        'BookID', 'BookLang', 'BookSub', 'AuthorID', 'SeriesDisplay']
                    else:
                        searchFields = ['AuthorName', 'BookName', 'BookRate', 'BookDate', 'Status',
                                        'BookID', 'BookLang', 'BookSub', 'AuthorID', 'SeriesDisplay']
                    filtered = list()
                    for row in rowlist:
                        _dict = dict(row)
                        for key in searchFields:
                            if key == 'BookRate':
                                if check_int(sSearch, 0) == int(_dict.get(key, '')):
                                    filtered.append(list(row))
                                    break
                            else:
                                if sSearch.lower() in _dict.get(key, '').lower():
                                    filtered.append(list(row))
                                    break
                else:
                    filtered = filter(lambda x: sSearch.lower() in str(x).lower(), rows)

            else:
                filtered = rows

            # table headers and column headers do not match at this point
            sortcolumn = int(iSortCol_0)

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

            if sortcolumn in [4, 12]:  # date, series
                self.natural_sort(filtered, key=lambda x: x[sortcolumn], reverse=sSortDir_0 == "desc")
            elif sortcolumn in [2]:  # title
                filtered.sort(key=lambda x: x[sortcolumn].lower(), reverse=sSortDir_0 == "desc")
            else:
                filtered.sort(key=lambda x: x[sortcolumn], reverse=sSortDir_0 == "desc")

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
                elif 'google' in row[9]:
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
                    flag = '&nbsp;<i class="fa fa-bookmark-o"></i>'
                    flagTo += 1
                elif row[6] in HaveRead:
                    flag = '&nbsp;<i class="fa fa-bookmark"></i>'
                    flagHave += 1
                else:
                    flag = ''

                # Need to pass bookid and status twice as datatables modifies first one
                if status_type == 'audiostatus':
                    d.append([row[6], row[0], row[1], title, row[12], bookrate, row[4], row[14], row[11],
                              row[6], row[15], row[14], row[16], flag])
                else:
                    d.append([row[6], row[0], row[1], title, row[12], bookrate, row[4], row[5], row[11],
                              row[6], row[13], row[5], row[16], flag])
            rows = d

        if lazylibrarian.LOGLEVEL > 3:
            logger.debug("getBooks %s returning %s to %s, flagged %s,%s" % (
                kwargs['source'], iDisplayStart, iDisplayStart + iDisplayLength, flagTo, flagHave))
            logger.debug("getBooks filtered %s from %s:%s" % (len(filtered), len(rowlist), len(rows)))
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
            convert = lambda text: int(text) if text.isdigit() else text
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
                _ = threading.Thread(target=GB.find_book, name='GB-BOOK', args=[bookid]).start()
            else:  # lazylibrarian.CONFIG['BOOK_API'] == "GoodReads":
                GR = GoodReads(bookid)
                _ = threading.Thread(target=GR.find_book, name='GR-BOOK', args=[bookid]).start()

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

    @staticmethod
    def mimetype(filename):
        name = filename.lower()
        if name.endswith('.epub'):
            return 'application/epub+zip'
        elif name.endswith('.mobi') or name.endswith('.azw3'):
            return 'application/x-mobipocket-ebook'
        elif name.endswith('.pdf'):
            return 'application/pdf'
        elif name.endswith('.mp3'):
            return 'audio/mpeg3'
        return "application/x-download"

    @cherrypy.expose
    def requestBook(self, **kwargs):
        self.label_thread('REQUEST_BOOK')
        prefix = ''
        title = 'Request Error'
        cookie = cherrypy.request.cookie
        if cookie and 'll_uid' in cookie.keys():
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
    def openBook(self, bookid=None, library=None, redirect=None):
        self.label_thread('OPEN_BOOK')
        # we need to check the user priveleges and see if they can download the book
        myDB = database.DBConnection()
        if lazylibrarian.CONFIG['HTTP_LOOK'] == 'legacy' or not lazylibrarian.CONFIG['USER_ACCOUNTS']:
            perm = lazylibrarian.perm_admin
        else:
            perm = 0
            cookie = cherrypy.request.cookie
            if cookie and 'll_uid' in cookie.keys():
                res = myDB.match('SELECT UserName,Perms from users where UserID=?', (cookie['ll_uid'].value,))
                if res:
                    perm = check_int(res['Perms'], 0)

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
                        logger.debug('Opening %s %s' % (library, bookfile))
                        return serve_file(bookfile, self.mimetype(bookfile), "attachment")
                else:
                    library = 'eBook'
                    bookfile = bookdata["BookFile"]
                    if bookfile and os.path.isfile(bookfile):
                        logger.debug('Opening %s %s' % (library, bookfile))
                        return serve_file(bookfile, self.mimetype(bookfile), "attachment")

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

    @cherrypy.expose
    def authorUpdate(self, authorid='', authorname='', authorborn='', authordeath='', authorimg='', manual='0'):
        myDB = database.DBConnection()
        if authorid:
            authdata = myDB.match('SELECT * from authors WHERE AuthorID=?', (authorid,))
            if authdata:
                edited = ""
                if authorborn == 'None':
                    authorborn = ''
                if authordeath == 'None':
                    authordeath = ''
                if authorimg == 'None':
                    authorimg = ''
                manual = bool(check_int(manual, 0))

                if not (authdata["AuthorBorn"] == authorborn):
                    edited += "Born "
                if not (authdata["AuthorDeath"] == authordeath):
                    edited += "Died "
                if not (authdata["AuthorImg"] == authorimg):
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
                    # Check dates in format yyyy/mm/dd, or unchanged if fails datecheck
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
                                    logger.debug("Failed to copy file %s, %s %s" %
                                                 (authorimg, type(why).__name__, str(why)))

                        if authorimg.startswith('http'):
                            # cache image from url
                            extn = os.path.splitext(authorimg)[1].lower()
                            if extn and extn in ['.jpg', '.jpeg', '.png']:
                                authorimg, success = cache_img("author", authorid, authorimg)
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
        cmd = 'SELECT BookName,BookID,BookSub,BookGenre,BookLang,books.Manual,AuthorName,books.AuthorID '
        cmd += 'from books,authors WHERE books.AuthorID = authors.AuthorID and BookID=?'
        bookdata = myDB.match(cmd, (bookid,))
        cmd = 'SELECT SeriesName, SeriesNum from member,series '
        cmd += 'where series.SeriesID=member.SeriesID and BookID=?'
        seriesdict = myDB.select(cmd, (bookid,))
        if bookdata:
            covers = []
            for source in ['current', 'cover', 'goodreads', 'librarything', 'google']:
                cover = getBookCover(bookid, source)
                if cover:
                    covers.append([source, cover])

            return serve_template(templatename="editbook.html", title="Edit Book",
                                  config=bookdata, seriesdict=seriesdict, authors=authors, covers=covers)
        else:
            logger.info('Missing book %s' % bookid)

    @cherrypy.expose
    def bookUpdate(self, bookname='', bookid='', booksub='', bookgenre='', booklang='',
                   manual='0', authorname='', cover='', **kwargs):

        myDB = database.DBConnection()
        if bookid:
            cmd = 'SELECT BookName,BookSub,BookGenre,BookLang,BookImg,books.Manual,AuthorName,books.AuthorID '
            cmd += 'from books,authors WHERE books.AuthorID = authors.AuthorID and BookID=?'
            bookdata = myDB.match(cmd, (bookid,))
            if bookdata:
                edited = ''
                moved = False
                if bookgenre == 'None':
                    bookgenre = ''
                manual = bool(check_int(manual, 0))
                if not (bookdata["BookName"] == bookname):
                    edited += "Title "
                if not (bookdata["BookSub"] == booksub):
                    edited += "Subtitle "
                if not (bookdata["BookGenre"] == bookgenre):
                    edited += "Genre "
                if not (bookdata["BookLang"] == booklang):
                    edited += "Language "
                if not (bool(check_int(bookdata["Manual"], 0)) == manual):
                    edited += "Manual "
                if not (bookdata["AuthorName"] == authorname):
                    moved = True

                covertype = ''
                if cover == 'librarything':
                    covertype = '_lt'
                if cover == 'goodreads':
                    covertype = '_gr'
                if cover == 'google':
                    covertype = '_gb'

                if covertype:
                    cachedir = lazylibrarian.CACHEDIR
                    coverlink = 'cache/book/' + bookid + covertype + '.jpg'
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
                        'BookImg': coverlink,
                        'Manual': bool(manual)
                    }
                    myDB.upsert("books", newValueDict, controlValueDict)

                cmd = 'SELECT SeriesName, SeriesNum from member,series '
                cmd += 'where series.SeriesID=member.SeriesID and BookID=?'
                old_series = myDB.select(cmd, (bookid,))
                old_dict = {}
                new_dict = {}
                dict_counter = 0
                while "series[%s][name]" % dict_counter in kwargs:
                    s_name = kwargs["series[%s][name]" % dict_counter]
                    s_name = cleanName(unaccented(s_name), '&/')
                    new_dict[s_name] = kwargs["series[%s][number]" % dict_counter]
                    dict_counter += 1
                if 'series[new][name]' in kwargs and 'series[new][number]' in kwargs:
                    if kwargs['series[new][name]']:
                        s_name = kwargs["series[new][name]"]
                        s_name = cleanName(unaccented(s_name), '&/')
                        new_dict[s_name] = kwargs['series[new][number]']
                for item in old_series:
                    old_dict[cleanName(unaccented(item['SeriesName']), '&/')] = item['SeriesNum']

                series_changed = False
                for item in old_dict:
                    if item not in new_dict:
                        series_changed = True
                for item in new_dict:
                    if item not in old_dict:
                        series_changed = True
                    else:
                        if new_dict[item] != old_dict[item]:
                            series_changed = True
                if series_changed:
                    setSeries(new_dict, bookid)
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
        if redirect == 'members' and ' ' in action:
            library, action = action.split(' ')
            if library == 'A':
                library = 'AudioBook'
            else:
                library = 'eBook'
        myDB = database.DBConnection()
        if not redirect:
            redirect = "books"
        authorcheck = []
        if action:
            for bookid in args:
                # ouch dirty workaround...
                if bookid not in ['book_table_length', 'ignored', 'library', 'booklang']:
                    if action in ["Unread", "Read", "ToRead"]:
                        cookie = cherrypy.request.cookie
                        if cookie and 'll_uid' in cookie.keys():
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
                        title = myDB.match('SELECT BookName from books WHERE BookID=?', (bookid,))
                        if title:
                            bookname = title['BookName']
                            if library == 'eBook':
                                myDB.upsert("books", {'Status': action}, {'BookID': bookid})
                                logger.debug('Status set to "%s" for "%s"' % (action, bookname))
                            elif library == 'AudioBook':
                                myDB.upsert("books", {'AudioStatus': action}, {'BookID': bookid})
                                logger.debug('AudioStatus set to "%s" for "%s"' % (action, bookname))
                    elif action in ["Remove", "Delete"]:
                        bookdata = myDB.match(
                            'SELECT AuthorID,Bookname,BookFile,AudioFile from books WHERE BookID=?', (bookid,))
                        if bookdata:
                            AuthorID = bookdata['AuthorID']
                            bookname = bookdata['BookName']
                            if action == "Delete":
                                if library == 'eBook':
                                    bookfile = bookdata['BookFile']
                                else:
                                    bookfile = bookdata['AudioFile']
                                if bookfile and os.path.isfile(bookfile):
                                    try:
                                        rmtree(os.path.dirname(bookfile), ignore_errors=True)
                                        deleted = True
                                    except Exception as e:
                                        logger.debug('rmtree failed on %s, %s %s' %
                                                     (bookfile, type(e).__name__, str(e)))
                                        deleted = False

                                    if deleted:
                                        if bookfile == bookdata['BookFile']:
                                            logger.info('eBook %s deleted from disc' % bookname)
                                            try:
                                                calibreid = os.path.dirname(bookfile)
                                                if calibreid.endswith(')'):
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
                                        if bookfile == bookdata['AudioFile']:
                                            logger.info('AudioBook %s deleted from disc' % bookname)

                            authorcheck = myDB.match('SELECT Status from authors WHERE AuthorID=?', (AuthorID,))
                            if authorcheck:
                                if authorcheck['Status'] not in ['Active', 'Wanted']:
                                    myDB.action('delete from books where bookid=?', (bookid,))
                                    myDB.action('delete from wanted where bookid=?', (bookid,))
                                    logger.info('Removed "%s" from database' % bookname)
                                elif library == 'eBook':
                                    myDB.upsert("books", {"Status": "Ignored"}, {"BookID": bookid})
                                    logger.debug('Status set to Ignored for "%s"' % bookname)
                                else:
                                    myDB.upsert("books", {"AudioStatus": "Ignored"}, {"BookID": bookid})
                                    logger.debug('AudioStatus set to Ignored for "%s"' % bookname)
                            else:
                                myDB.action('delete from books where bookid=?', (bookid,))
                                myDB.action('delete from wanted where bookid=?', (bookid,))
                                logger.info('Removed "%s" from database' % bookname)

        if redirect == "author" or len(authorcheck):
            update_totals(AuthorID)

        # start searchthreads
        if action == 'Wanted':
            books = []
            for arg in args:
                # ouch dirty workaround...
                if arg not in ['booklang', 'library', 'ignored', 'book_table_length']:
                    books.append({"bookid": arg})

            if lazylibrarian.USE_NZB() or lazylibrarian.USE_TOR() \
                    or lazylibrarian.USE_RSS() or lazylibrarian.USE_DIRECT():
                threading.Thread(target=search_book, name='SEARCHBOOK', args=[books, library]).start()

        if redirect == "author":
            raise cherrypy.HTTPRedirect("authorPage?AuthorID=%s&library=%s" % (AuthorID, library))
        elif redirect in ["books", "audio"]:
            raise cherrypy.HTTPRedirect(redirect)
        elif redirect == "members":
            raise cherrypy.HTTPRedirect("seriesMembers?seriesid=%s" % seriesid)
        else:
            raise cherrypy.HTTPRedirect("manage")

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
                        myhash = hashlib.md5(magimg).hexdigest()
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
            cmd = 'SELECT BookLink,BookImg,BookID,BookName from books order by BookAdded DESC'
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

    @cherrypy.expose
    def magazines(self):
        myDB = database.DBConnection()
        
        magazines = myDB.select('select * from magazines order by Title')
        mags = []
        covercount = 0
        if magazines:
            for mag in magazines:
                title = mag['Title']
                count = myDB.match('SELECT COUNT(Title) as counter FROM issues WHERE Title=?', (title,))
                if count:
                    issues = count['counter']
                else:
                    issues = 0
                magimg = mag['LatestCover']

                # special flag to say "no covers required"
                if lazylibrarian.CONFIG['IMP_CONVERT'] == 'None' or not magimg or not os.path.isfile(magimg):
                    magimg = 'images/nocover.jpg'
                else:
                    myhash = hashlib.md5(magimg).hexdigest()
                    hashname = os.path.join(lazylibrarian.CACHEDIR, 'magazine', '%s.jpg' % myhash)
                    if not os.path.isfile(hashname):
                        copyfile(magimg, hashname)
                        setperm(hashname)
                    magimg = 'cache/magazine/' + myhash + '.jpg'
                    covercount += 1

                this_mag = dict(mag)
                this_mag['Count'] = issues
                this_mag['Cover'] = magimg
                temp_title = mag['Title']
                temp_title = temp_title.encode(lazylibrarian.SYS_ENCODING)
                this_mag['safetitle'] = urllib.quote_plus(temp_title)
                mags.append(this_mag)

            if lazylibrarian.CONFIG['HTTP_LOOK'] == 'legacy':
                if not lazylibrarian.CONFIG['MAG_IMG']:
                    covercount = 0
            else:
                if not lazylibrarian.CONFIG['TOGGLES'] and not lazylibrarian.CONFIG['MAG_IMG']:
                    covercount = 0
        return serve_template(templatename="magazines.html", title="Magazines", magazines=mags, covercount=covercount)

    @cherrypy.expose
    def issuePage(self, title):
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
                        myhash = hashlib.md5(magimg).hexdigest()
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

            if lazylibrarian.CONFIG['HTTP_LOOK'] == 'legacy':
                if not lazylibrarian.CONFIG['MAG_IMG'] or lazylibrarian.CONFIG['IMP_CONVERT'] == 'None':
                    covercount = 0
            elif not lazylibrarian.CONFIG['TOGGLES']:
                if not lazylibrarian.CONFIG['MAG_IMG'] or lazylibrarian.CONFIG['IMP_CONVERT'] == 'None':
                    covercount = 0

        if '&' in title and '&amp;' not in title:  # could use htmlparser but seems overkill for just '&'
            title = title.replace('&', '&amp;')

        return serve_template(templatename="issues.html", title=title, issues=mod_issues, covercount=covercount)

    @cherrypy.expose
    def pastIssues(self, whichStatus=None):
        if whichStatus is None:
            whichStatus = "Skipped"
        return serve_template(
            templatename="manageissues.html", title="Manage Past Issues", issues=[], whichStatus=whichStatus)

    @cherrypy.expose
    @cherrypy.tools.json_out()
    def getPastIssues(self, iDisplayStart=0, iDisplayLength=100, iSortCol_0=0, sSortDir_0="desc", sSearch="", **kwargs):
        # kwargs is used by datatables to pass params
        myDB = database.DBConnection()
        iDisplayStart = int(iDisplayStart)
        iDisplayLength = int(iDisplayLength)
        lazylibrarian.CONFIG['DISPLAYLENGTH'] = iDisplayLength
        # need to filter on whichStatus
        rowlist = myDB.select('SELECT NZBurl, NZBtitle, NZBdate, Auxinfo, NZBprov from pastissues WHERE Status=?',
                              (kwargs['whichStatus'],))
        rows = []
        filtered = []
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
                filtered = filter(lambda x: sSearch.lower() in str(x).lower(), rows)
            else:
                filtered = rows

            sortcolumn = int(iSortCol_0)
            filtered.sort(key=lambda x: x[sortcolumn], reverse=sSortDir_0 == "desc")

            if iDisplayLength < 0:  # display = all
                rows = filtered
            else:
                rows = filtered[iDisplayStart:(iDisplayStart + iDisplayLength)]

        if lazylibrarian.LOGLEVEL > 3:
            logger.debug("getPastIssues returning %s to %s" % (iDisplayStart, iDisplayStart + iDisplayLength))
            logger.debug("getPastIssues filtered %s from %s:%s" % (len(filtered), len(rowlist), len(rows)))
        mydict = {'iTotalDisplayRecords': len(filtered),
                  'iTotalRecords': len(rowlist),
                  'aaData': rows,
                  }
        return mydict

    @cherrypy.expose
    def openMag(self, bookid=None):
        bookid = urllib.unquote_plus(bookid)
        myDB = database.DBConnection()
        # we may want to open an issue with a hashed bookid
        mag_data = myDB.match('SELECT * from issues WHERE IssueID=?', (bookid,))
        if mag_data:
            IssueFile = mag_data["IssueFile"]
            if IssueFile and os.path.isfile(IssueFile):
                logger.debug('Opening file %s' % IssueFile)
                return serve_file(IssueFile, self.mimetype(IssueFile), "attachment")

        # or we may just have a title to find magazine in issues table
        mag_data = myDB.select('SELECT * from issues WHERE Title=?', (bookid,))
        if len(mag_data) <= 0:  # no issues!
            raise cherrypy.HTTPRedirect("magazines")
        elif len(mag_data) == 1 and lazylibrarian.CONFIG['MAG_SINGLE']:  # we only have one issue, get it
            IssueDate = mag_data[0]["IssueDate"]
            IssueFile = mag_data[0]["IssueFile"]
            logger.debug('Opening %s - %s' % (bookid, IssueDate))
            return serve_file(IssueFile, self.mimetype(IssueFile), "attachment")
        else:  # multiple issues, show a list
            logger.debug("%s has %s issue%s" % (bookid, len(mag_data), plural(len(mag_data))))
            bookid = bookid.encode(lazylibrarian.SYS_ENCODING)
            raise cherrypy.HTTPRedirect("issuePage?title=%s" % urllib.quote_plus(bookid))

    @cherrypy.expose
    def markPastIssues(self, action=None, **args):
        myDB = database.DBConnection()
        maglist = []
        for nzburl in args:
            if isinstance(nzburl, str) and hasattr(nzburl, "decode"):
                nzburl = nzburl.decode(lazylibrarian.SYS_ENCODING)
            # ouch dirty workaround...
            if not nzburl == 'book_table_length':
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
                if 'libgen' in items['nzbprov']:
                    snatch = DirectDownloadMethod(
                        items['bookid'],
                        items['nzbtitle'],
                        items['nzburl'],
                        items['nzbtitle'],
                        'magazine')
                elif items['nzbmode'] in ['torznab', 'torrent', 'magnet']:
                    snatch = TORDownloadMethod(
                        items['bookid'],
                        items['nzbtitle'],
                        items['nzburl'],
                        'magazine')
                else:
                    snatch = NZBDownloadMethod(
                        items['bookid'],
                        items['nzbtitle'],
                        items['nzburl'],
                        'magazine')
                if snatch:  # if snatch fails, downloadmethods already report it
                    myDB.action('UPDATE pastissues set status=? WHERE NZBurl=?', ("Snatched", items['nzburl']))
                    logger.info('Downloading %s from %s' % (items['nzbtitle'], items['nzbprov']))
                    notifiers.notify_snatch(items['nzbtitle'] + ' at ' + now())
                    custom_notify_snatch(items['bookid'])
                    scheduleJob(action='Start', target='processDir')
        raise cherrypy.HTTPRedirect("pastIssues")

    @cherrypy.expose
    def markIssues(self, action=None, **args):
        myDB = database.DBConnection()
        for item in args:
            # ouch dirty workaround...
            if not item == 'book_table_length':
                issue = myDB.match('SELECT IssueFile,Title,IssueDate from issues WHERE IssueID=?', (item,))
                if issue:
                    if action == "Delete":
                        result = self.deleteIssue(issue['IssueFile'])
                        if result:
                            logger.info('Issue %s of %s deleted from disc' % (issue['IssueDate'], issue['Title']))
                    if action == "Remove" or action == "Delete":
                        myDB.action('DELETE from issues WHERE IssueID=?', (item,))
                        logger.info('Issue %s of %s removed from database' % (issue['IssueDate'], issue['Title']))
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
            if os.path.exists(fname):
                os.remove(fname)
            # if the directory is now empty, delete that too
            try:
                os.rmdir(os.path.dirname(issuefile))
            except OSError:
                logger.debug('Directory %s not deleted, not empty?' % os.path.dirname(issuefile))
            return True
        except Exception as e:
            logger.debug('delete issue failed on %s, %s %s' % (issuefile, type(e).__name__, str(e)))
        return False

    @cherrypy.expose
    def markMagazines(self, action=None, **args):
        myDB = database.DBConnection()
        for item in args:
            if isinstance(item, str) and hasattr(item, "decode"):
                item = item.decode(lazylibrarian.SYS_ENCODING)
            # ouch dirty workaround...
            if not item == 'book_table_length':
                if action == "Paused" or action == "Active":
                    controlValueDict = {"Title": item}
                    newValueDict = {"Status": action}
                    myDB.upsert("magazines", newValueDict, controlValueDict)
                    logger.info('Status of magazine %s changed to %s' % (item, action))
                if action == "Delete":
                    issues = myDB.select('SELECT IssueFile from issues WHERE Title=?', (item,))
                    logger.debug('Deleting magazine %s from disc' % item)
                    issuedir = ''
                    for issue in issues:  # delete all issues of this magazine
                        result = self.deleteIssue(issue['IssueFile'])
                        if result:
                            logger.debug('Issue %s deleted from disc' % issue['IssueFile'])
                            issuedir = os.path.dirname(issue['IssueFile'])
                        else:
                            logger.debug('Failed to delete %s' % (issue['IssueFile']))
                    if issuedir:
                        magdir = os.path.dirname(issuedir)
                        # delete this magazines directory if now empty
                        try:
                            os.rmdir(magdir)
                            logger.debug('Magazine directory %s deleted from disc' % magdir)
                        except OSError:
                            logger.debug('Magazine directory %s is not empty' % magdir)
                    logger.info('Magazine %s deleted from disc' % item)
                if action == "Remove" or action == "Delete":
                    myDB.action('DELETE from magazines WHERE Title=?', (item,))
                    myDB.action('DELETE from pastissues WHERE BookID=?', (item,))
                    myDB.action('DELETE from issues WHERE Title=?', (item,))
                    myDB.action('DELETE from wanted where BookID=?', (item,))
                    logger.info('Magazine %s removed from database' % item)
                if action == "Reset":
                    controlValueDict = {"Title": item}
                    newValueDict = {
                        "LastAcquired": None,
                        "IssueDate": None,
                        "LatestCover": None,
                        "IssueStatus": "Wanted"
                    }
                    myDB.upsert("magazines", newValueDict, controlValueDict)
                    logger.info('Magazine %s details reset' % item)

        raise cherrypy.HTTPRedirect("magazines")

    @cherrypy.expose
    def searchForMag(self, bookid=None):
        myDB = database.DBConnection()
        bookid = urllib.unquote_plus(bookid)
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
        if title is None or not title:
            raise cherrypy.HTTPRedirect("magazines")
        else:
            reject = None
            if '~' in title:  # separate out the "reject words" list
                reject = title.split('~', 1)[1].strip()
                title = title.split('~', 1)[0].strip()

            # replace any non-ascii quotes/apostrophes with ascii ones eg "Collector's"
            dic = {u'\u2018': u"'", u'\u2019': u"'", u'\u201c': u'"', u'\u201d': u'"'}
            title = replace_all(title, dic)
            exists = myDB.match('SELECT Title from magazines WHERE Title=?', (title,))
            if exists:
                logger.debug("Magazine %s already exists (%s)" % (title, exists['Title']))
            else:
                controlValueDict = {"Title": title}
                newValueDict = {
                    "Regex": None,
                    "Reject": reject,
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
            return serve_template(templatename="response.html", prefix='LazyLibrarian is ',
                                  title="Version Check", message=message, timer=5)

        elif lazylibrarian.CONFIG['COMMITS_BEHIND'] > 0:
            message = "behind by %s commit%s" % (lazylibrarian.CONFIG['COMMITS_BEHIND'],
                                                 plural(lazylibrarian.CONFIG['COMMITS_BEHIND']))
            messages = lazylibrarian.COMMIT_LIST.replace('\n', '<br>')
            message = message + '<br><small>' + messages
            return serve_template(templatename="shutdown.html", title="Commits", prefix='LazyLibrarian is ',
                                  message=message, timer=15)

        else:
            message = "unknown version"
            messages = "Your version is not recognised at<br>https://github.com/%s/%s  Branch: %s" % (
                lazylibrarian.CONFIG['GIT_USER'], lazylibrarian.CONFIG['GIT_REPO'], lazylibrarian.CONFIG['GIT_BRANCH'])
            message = message + '<br><small>' + messages
            return serve_template(templatename="response.html", title="Commits", prefix='LazyLibrarian is ',
                                  message=message, timer=15)

            # raise cherrypy.HTTPRedirect("config")

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
        if library == 'Audio':
            raise cherrypy.HTTPRedirect("audio")
        raise cherrypy.HTTPRedirect("books")

    @cherrypy.expose
    def magazineScan(self):
        if 'MAGAZINE_SCAN' not in [n.name for n in [t for t in threading.enumerate()]]:
            try:
                threading.Thread(target=magazinescan.magazineScan, name='MAGAZINE_SCAN', args=[]).start()
            except Exception as e:
                logger.error('Unable to complete the scan: %s %s' % (type(e).__name__, str(e)))
        else:
            logger.debug('MAGAZINE_SCAN already running')
        raise cherrypy.HTTPRedirect("magazines")

    @cherrypy.expose
    def includeAlternate(self):
        if 'ALT-LIBRARYSCAN' not in [n.name for n in [t for t in threading.enumerate()]]:
            try:
                threading.Thread(target=LibraryScan, name='ALT-LIBRARYSCAN',
                                 args=[lazylibrarian.CONFIG['ALTERNATE_DIR'], 'eBook', None, False]).start()
            except Exception as e:
                logger.error('Unable to complete the libraryscan: %s %s' % (type(e).__name__, str(e)))
        else:
            logger.debug('ALT-LIBRARYSCAN already running')
        raise cherrypy.HTTPRedirect("manage")

    @cherrypy.expose
    def importAlternate(self):
        if 'IMPORTALT' not in [n.name for n in [t for t in threading.enumerate()]]:
            try:
                threading.Thread(target=processAlternate, name='IMPORTALT',
                                 args=[lazylibrarian.CONFIG['ALTERNATE_DIR']]).start()
            except Exception as e:
                logger.error('Unable to complete the import: %s %s' % (type(e).__name__, str(e)))
        else:
            logger.debug('IMPORTALT already running')
        raise cherrypy.HTTPRedirect("manage")

    @cherrypy.expose
    def importCSV(self):
        if 'IMPORTCSV' not in [n.name for n in [t for t in threading.enumerate()]]:
            try:
                threading.Thread(target=import_CSV, name='IMPORTCSV',
                                 args=[lazylibrarian.CONFIG['ALTERNATE_DIR']]).start()
                csvFile = csv_file(lazylibrarian.CONFIG['ALTERNATE_DIR'])
                if os.path.exists(csvFile):
                    message = "Importing books (background task) from %s" % csvFile
                else:
                    message = "No CSV file in [%s]" % lazylibrarian.CONFIG['ALTERNATE_DIR']
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
    def exportCSV(self):
        self.label_thread('EXPORTCSV')
        message = export_CSV(lazylibrarian.CONFIG['ALTERNATE_DIR'])
        message = message.replace('\n', '<br>')
        if lazylibrarian.CONFIG['HTTP_LOOK'] == 'legacy':
            raise cherrypy.HTTPRedirect("manage")
        else:
            return message

    # JOB CONTROL #######################################################

    @cherrypy.expose
    def shutdown(self):
        self.label_thread('SHUTDOWN')
        lazylibrarian.config_write()
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
        # show the current status of LL cron jobs in the log
        resultlist = showJobs()
        result = ''
        for line in resultlist:
            result = result + line + '\n'
        return result

    @cherrypy.expose
    def restart_Jobs(self):
        restartJobs(start='Restart')
        # and list the new run-times in the log
        return self.show_Jobs()

    @cherrypy.expose
    def stop_Jobs(self):
        restartJobs(start='Stop')
        # and list the new run-times in the log
        return self.show_Jobs()

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
        iDisplayStart = int(iDisplayStart)
        iDisplayLength = int(iDisplayLength)
        lazylibrarian.CONFIG['DISPLAYLENGTH'] = iDisplayLength

        if sSearch:
            filtered = filter(lambda x: sSearch.lower() in str(x).lower(), lazylibrarian.LOGLIST[::])
        else:
            filtered = lazylibrarian.LOGLIST[::]

        sortcolumn = int(iSortCol_0)
        filtered.sort(key=lambda x: x[sortcolumn], reverse=sSortDir_0 == "desc")
        if iDisplayLength < 0:  # display = all
            rows = filtered
        else:
            rows = filtered[iDisplayStart:(iDisplayStart + iDisplayLength)]
        if lazylibrarian.LOGLEVEL > 3:
            logger.debug("getLog returning %s to %s" % (iDisplayStart, iDisplayStart + iDisplayLength))
            logger.debug("getLog filtered %s from %s:%s" % (len(filtered), len(lazylibrarian.LOGLIST), len(rows)))
        mydict = {'iTotalDisplayRecords': len(filtered),
                  'iTotalRecords': len(lazylibrarian.LOGLIST),
                  'aaData': rows,
                  }
        return mydict

    # HISTORY ###########################################################

    @cherrypy.expose
    def history(self):
        myDB = database.DBConnection()
        # wanted status holds snatched processed for all, plus skipped and
        # ignored for magazine back issues
        cmd = "SELECT BookID,NZBurl,NZBtitle,NZBdate,NZBprov,Status,NZBsize,AuxInfo"
        cmd += " from wanted WHERE Status != 'Skipped' and Status != 'Ignored'"
        rowlist = myDB.select(cmd)
        # turn the sqlite rowlist into a list of dicts
        rows = []
        if len(rowlist):
            # the masterlist to be filled with the row data
            for row in rowlist:  # iterate through the sqlite3.Row objects
                thisrow = dict(row)
                # title needs spaces, not dots, for column resizing
                title = thisrow['NZBtitle']
                if title:
                    title = title.replace('.', ' ')
                    title = title.replace('LL (', 'LL.(')
                    thisrow['NZBtitle'] = title
                # provider needs to be shorter and with spaces for column resizing
                provider = thisrow['NZBprov']
                if provider:
                    if len(provider) > 20:
                        while len(provider) > 20 and '/' in provider:
                            provider = provider.split('/', 1)[1]
                        provider = provider.replace('/', ' ')
                        thisrow['NZBprov'] = provider
                if title and provider:
                    rows.append(thisrow)  # add the rowlist to the masterlist
        return serve_template(templatename="history.html", title="History", history=rows)

    @cherrypy.expose
    def clearhistory(self, status=None):
        myDB = database.DBConnection()
        if status == 'all':
            logger.info("Clearing all history")
            myDB.action("DELETE from wanted WHERE Status != 'Skipped' and Status != 'Ignored'")
        else:
            logger.info("Clearing history where status is %s" % status)
            myDB.action('DELETE from wanted WHERE Status=?', (status,))
        raise cherrypy.HTTPRedirect("history")

    @cherrypy.expose
    def clearblocked(self):
        cherrypy.response.headers['Cache-Control'] = "max-age=0,no-cache,no-store"
        # clear any currently blocked providers
        num = len(lazylibrarian.PROVIDER_BLOCKLIST)
        lazylibrarian.PROVIDER_BLOCKLIST = []
        result = 'Cleared %s blocked providers' % num
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
        count = myDB.match('SELECT COUNT(Provider) as counter FROM downloads')
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
            new_entry = "%4d - %s\n" % (line['Count'], line['Provider'])
            result = result + new_entry

        if result == '':
            result = 'No downloads'
        return result

    @cherrypy.expose
    def syncToGoodreads(self):
        if 'GRSync' not in [n.name for n in [t for t in threading.enumerate()]]:
            cherrypy.response.headers['Cache-Control'] = "max-age=0,no-cache,no-store"
            self.label_thread('GRSync')
            msg = grsync.sync_to_gr()
        else:
            msg = 'Goodreads Sync is already running'
        return msg

    @cherrypy.expose
    def grauthStep1(self):
        cherrypy.response.headers['Cache-Control'] = "max-age=0,no-cache,no-store"
        GA = grsync.grauth()
        return GA.goodreads_oauth1()

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
            lazylibrarian.config_write()
        return res

    # NOTIFIERS #########################################################

    @cherrypy.expose
    def twitterStep1(self):
        cherrypy.response.headers['Cache-Control'] = "max-age=0,no-cache,no-store"
        return notifiers.twitter_notifier._get_authorization()

    @cherrypy.expose
    def twitterStep2(self, key):
        cherrypy.response.headers['Cache-Control'] = "max-age=0,no-cache,no-store"
        result = notifiers.twitter_notifier._get_credentials(key)
        logger.info("result: " + str(result))
        if result:
            return "Key verification successful"
        else:
            return "Unable to verify key"

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
            lazylibrarian.config_write()
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
            lazylibrarian.config_write()
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
            lazylibrarian.config_write()
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
            lazylibrarian.config_write()
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
            lazylibrarian.config_write()
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
            lazylibrarian.config_write()
            return "Test Prowl notice sent successfully"
        else:
            return "Test Prowl notice failed"

    @cherrypy.expose
    def testNMA(self, **kwargs):
        cherrypy.response.headers['Cache-Control'] = "max-age=0,no-cache,no-store"
        threading.currentThread().name = "WEBSERVER"
        if 'apikey' in kwargs:
            lazylibrarian.CONFIG['NMA_APIKEY'] = kwargs['apikey']
        if 'priority' in kwargs:
            lazylibrarian.CONFIG['NMA_PRIORITY'] = check_int(kwargs['priority'], 0)

        result = notifiers.nma_notifier.test_notify()
        if result:
            lazylibrarian.config_write()
            return "Test NMA notice sent successfully"
        else:
            return "Test NMA notice failed"

    @cherrypy.expose
    def testSlack(self, **kwargs):
        cherrypy.response.headers['Cache-Control'] = "max-age=0,no-cache,no-store"
        threading.currentThread().name = "WEBSERVER"
        if 'token' in kwargs:
            lazylibrarian.CONFIG['SLACK_TOKEN'] = kwargs['token']

        result = notifiers.slack_notifier.test_notify()
        if result != "ok":
            return "Slack notification failed,\n%s" % result
        else:
            lazylibrarian.config_write()
            return "Slack notification successful"

    @cherrypy.expose
    def testCustom(self, **kwargs):
        cherrypy.response.headers['Cache-Control'] = "max-age=0,no-cache,no-store"
        threading.currentThread().name = "WEBSERVER"
        if 'script' in kwargs:
            lazylibrarian.CONFIG['CUSTOM_SCRIPT'] = kwargs['script']
        result = notifiers.custom_notifier.test_notify()
        if result:
            return "Custom notification failed,\n%s" % result
        else:
            lazylibrarian.config_write()
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
            lazylibrarian.config_write()
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
        else:
            logger.debug('POSTPROCESS already running')
        raise cherrypy.HTTPRedirect(source)

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
        elif source in ["books", "audio"]:
            if lazylibrarian.USE_NZB() or lazylibrarian.USE_TOR() \
                    or lazylibrarian.USE_RSS() or lazylibrarian.USE_DIRECT():
                if 'SEARCHALLBOOKS' not in [n.name for n in [t for t in threading.enumerate()]]:
                    threading.Thread(target=search_book, name='SEARCHALLBOOKS', args=[]).start()
            else:
                logger.debug('forceSearch called but no download methods set')
        else:
            logger.debug("forceSearch called with bad source")
        raise cherrypy.HTTPRedirect(source)

    @cherrypy.expose
    def manage(self, whichStatus=None, **kwargs):
        library = 'eBook'
        if 'library' in kwargs:
            library = kwargs['library']
        if whichStatus is None:
            whichStatus = "Wanted"
        types = ['eBook']
        if lazylibrarian.SHOW_AUDIO:
            types.append('AudioBook')
        return serve_template(templatename="managebooks.html", title="Manage Books",
                              books=[], types=types, library=library, whichStatus=whichStatus)

    @cherrypy.expose
    def testDeluge(self, **kwargs):
        cherrypy.response.headers['Cache-Control'] = "max-age=0,no-cache,no-store"
        threading.currentThread().name = "WEBSERVER"
        if 'host' in kwargs:
            lazylibrarian.CONFIG['DELUGE_HOST'] = kwargs['host']
        if 'port' in kwargs:
            lazylibrarian.CONFIG['DELUGE_PORT'] = check_int(kwargs['port'], 0)
        if 'user' in kwargs:
            lazylibrarian.CONFIG['DELUGE_USER'] = kwargs['user']
        if 'pwd' in kwargs:
            lazylibrarian.CONFIG['DELUGE_PASS'] = kwargs['pwd']
        if 'label' in kwargs:
            lazylibrarian.CONFIG['DELUGE_LABEL'] = kwargs['label']

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
                msg = "Deluge: Daemon connection Successful"
                if lazylibrarian.CONFIG['DELUGE_LABEL']:
                    labels = client.call('label.get_labels')
                    if lazylibrarian.CONFIG['DELUGE_LABEL'] not in labels:
                        msg = "Deluge: Unknown label [%s]\n" % lazylibrarian.CONFIG['DELUGE_LABEL']
                        if labels:
                            msg += "Valid labels:\n"
                            for label in labels:
                                msg += '%s\n' % label
                        else:
                            msg += "Deluge daemon seems to have no labels set"
                        return msg
            # success, save settings
            lazylibrarian.config_write()
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
            lazylibrarian.config_write()
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
            lazylibrarian.config_write()
        return msg

    @cherrypy.expose
    def testTransmission(self, **kwargs):
        cherrypy.response.headers['Cache-Control'] = "max-age=0,no-cache,no-store"
        threading.currentThread().name = "WEBSERVER"
        if 'host' in kwargs:
            lazylibrarian.CONFIG['TRANSMISSION_HOST'] = kwargs['host']
        if 'port' in kwargs:
            lazylibrarian.CONFIG['TRANSMISSION_PORT'] = check_int(kwargs['port'], 0)
        if 'user' in kwargs:
            lazylibrarian.CONFIG['TRANSMISSION_USER'] = kwargs['user']
        if 'pwd' in kwargs:
            lazylibrarian.CONFIG['TRANSMISSION_PASS'] = kwargs['pwd']
        msg = transmission.checkLink()
        if 'success' in msg:
            lazylibrarian.config_write()
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
            lazylibrarian.config_write()
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
            lazylibrarian.config_write()
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
            lazylibrarian.config_write()
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
            lazylibrarian.config_write()
        return msg

    @cherrypy.expose
    def testCalibredb(self, **kwargs):
        threading.currentThread().name = "WEBSERVER"
        cherrypy.response.headers['Cache-Control'] = "max-age=0,no-cache,no-store"
        if 'prg' in kwargs and kwargs['prg']:
            lazylibrarian.CONFIG['IMP_CALIBREDB'] = kwargs['prg']
        return calibreTest()
