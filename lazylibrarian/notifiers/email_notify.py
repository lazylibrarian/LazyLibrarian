# This file is part of LazyLibrarian.
#
# LazyLibrarian is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# LazyLibrarian is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
#  GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with LazyLibrarian.  If not, see <http://www.gnu.org/licenses/>.

import smtplib
import cherrypy
from email.utils import formatdate, formataddr
from email.mime.text import MIMEText
from email.mime.application import MIMEApplication
from email.mime.multipart import MIMEMultipart

import lazylibrarian
import os
from lazylibrarian import logger, database
from lazylibrarian.common import notifyStrings, NOTIFY_SNATCH, NOTIFY_DOWNLOAD
from lazylibrarian.formatter import check_int, getList


class EmailNotifier:
    def __init__(self):
        pass

    @staticmethod
    def _notify(message, event, force=False, files=None, to_addr=None):

        # suppress notifications if the notifier is disabled but the notify options are checked
        if not lazylibrarian.CONFIG['USE_EMAIL'] and not force:
            return False

        subject = event
        text = message

        if files:
            message = MIMEMultipart()
            message.attach(MIMEText(text))
        else:
            message = MIMEText(text, 'plain', "utf-8")

        message['Subject'] = subject
        message['From'] = formataddr(('LazyLibrarian', lazylibrarian.CONFIG['EMAIL_FROM']))
        if to_addr:
            message['To'] = to_addr
        else:
            message['To'] = lazylibrarian.CONFIG['EMAIL_TO']
        message['Date'] = formatdate(localtime=True)

        logger.debug('Email notification: %s' % message['Subject'])
        logger.debug('Email from: %s' % message['From'])
        logger.debug('Email to: %s' % message['To'])
        logger.debug('Email text: %s' % text)
        logger.debug('Files: %s' % files)

        if files:
            for f in files:
                fsize = check_int(os.path.getsize(f), 0)
                if fsize > 20000000:
                    msg = '%s is too large (%s) to email' % (os.path.basename(f), fsize)
                    message.attach(MIMEText(msg))
                else:
                    logger.debug('Attaching %s' % os.path.basename(f))
                    with open(f, "rb") as fil:
                        part = MIMEApplication(fil.read(), Name=os.path.basename(f))
                        part['Content-Disposition'] = 'attachment; filename="%s"' % os.path.basename(f)
                        message.attach(part)

        try:
            if lazylibrarian.CONFIG['EMAIL_SSL']:
                mailserver = smtplib.SMTP_SSL(lazylibrarian.CONFIG['EMAIL_SMTP_SERVER'],
                                              check_int(lazylibrarian.CONFIG['EMAIL_SMTP_PORT'], 465))
            else:
                mailserver = smtplib.SMTP(lazylibrarian.CONFIG['EMAIL_SMTP_SERVER'],
                                          check_int(lazylibrarian.CONFIG['EMAIL_SMTP_PORT'], 25))

            if lazylibrarian.CONFIG['EMAIL_TLS']:
                mailserver.starttls()
            else:
                mailserver.ehlo()

            if lazylibrarian.CONFIG['EMAIL_SMTP_USER']:
                mailserver.login(lazylibrarian.CONFIG['EMAIL_SMTP_USER'], lazylibrarian.CONFIG['EMAIL_SMTP_PASSWORD'])

            mailserver.sendmail(lazylibrarian.CONFIG['EMAIL_FROM'], lazylibrarian.CONFIG['EMAIL_TO'],
                                message.as_string())
            mailserver.quit()
            return True

        except Exception as e:
            logger.warn('Error sending Email: %s' % e)
            return False

            #
            # Public functions
            #

    def notify_message(self, subject, message, to_addr):
        return self._notify(message=message, event=subject, force=True, to_addr=to_addr)

    def notify_snatch(self, title):
        if lazylibrarian.CONFIG['EMAIL_NOTIFY_ONSNATCH']:
            return self._notify(message=title, event=notifyStrings[NOTIFY_SNATCH])
        return False

    def notify_download(self, title, bookid=None, force=False):
        # suppress notifications if the notifier is disabled but the notify options are checked
        if not lazylibrarian.CONFIG['USE_EMAIL'] and not force:
            return False

        if lazylibrarian.CONFIG['EMAIL_NOTIFY_ONDOWNLOAD'] or force:
            files = None
            event = notifyStrings[NOTIFY_DOWNLOAD]
            logger.debug('Email send attachment is %s' % lazylibrarian.CONFIG['EMAIL_SENDFILE_ONDOWNLOAD'])
            if lazylibrarian.CONFIG['EMAIL_SENDFILE_ONDOWNLOAD']:
                if not bookid:
                    logger.debug('Email request to attach book, but no bookid')
                else:
                    filename = None
                    preftype = None
                    typelist = getList(lazylibrarian.CONFIG['EBOOK_TYPE'])

                    if lazylibrarian.CONFIG['HTTP_LOOK'] == 'legacy' or not lazylibrarian.CONFIG['USER_ACCOUNTS']:
                        preftype = typelist[0]
                        logger.debug('Preferred filetype = %s' % preftype)
                    else:
                        myDB = database.DBConnection()
                        cookie = cherrypy.request.cookie
                        if cookie and 'll_uid' in list(cookie.keys()):
                            res = myDB.match('SELECT BookType from users where UserID=?', (cookie['ll_uid'].value,))
                            if res and res['BookType']:
                                preftype = res['BookType']
                                logger.debug('User preferred filetype = %s' % preftype)
                        if not preftype:
                            logger.debug('Default preferred filetype = %s' % preftype)
                            preftype = typelist[0]

                    myDB = database.DBConnection()
                    data = myDB.match('SELECT BookFile,BookName from books where BookID=?', (bookid,))
                    if data:
                        bookfile = data['BookFile']
                        types = []
                        if bookfile and os.path.isfile(bookfile):
                            basename, extn = os.path.splitext(bookfile)
                            for item in typelist:
                                target = basename + '.' + item
                                if os.path.isfile(target):
                                    types.append(item)

                            logger.debug('Available filetypes: %s' % str(types))

                            if preftype in types:
                                filename = basename + '.' + preftype
                            else:
                                filename = basename + '.' + types[0]

                        title = data['BookName']
                        logger.debug('Found %s for bookid %s' % (filename, bookid))
                    else:
                        logger.debug('[%s] is not a valid bookid' % bookid)
                        data = myDB.match('SELECT IssueFile,Title,IssueDate from issues where IssueID=?', (bookid,))
                        if data:
                            filename = data['IssueFile']
                            title = "%s - %s" % (data['Title'], data['IssueDate'])
                            logger.debug('Found %s for issueid %s' % (filename, bookid))
                        else:
                            logger.debug('[%s] is not a valid issueid' % bookid)
                            filename = ''
                    if filename:
                        files = [filename]  # could add cover_image, opf
                        event = "LazyLibrarian Download"
            return self._notify(message=title, event=event, force=force, files=files)
        return False

    def test_notify(self, title='This is a test notification from LazyLibrarian'):
        if lazylibrarian.CONFIG['EMAIL_SENDFILE_ONDOWNLOAD']:
            myDB = database.DBConnection()
            data = myDB.match('SELECT bookid from books where bookfile <> ""')
            if data:
                return self.notify_download(title=title, bookid=data['bookid'], force=True)
        return self.notify_download(title=title, bookid=None, force=True)


notifier = EmailNotifier
