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

import email.utils
import smtplib
from email.mime.text import MIMEText

import lazylibrarian
from lazylibrarian import logger
from lazylibrarian.common import notifyStrings, NOTIFY_SNATCH, NOTIFY_DOWNLOAD
from lazylibrarian.formatter import check_int


class EmailNotifier:
    @staticmethod
    def _notify(message, event, force=False):

        # suppress notifications if the notifier is disabled but the notify options are checked
        if not lazylibrarian.CONFIG['USE_EMAIL'] and not force:
            return False

        subject = event
        text = message
        message = MIMEText(message, 'plain', "utf-8")
        message['Subject'] = subject
        message['From'] = email.utils.formataddr(('LazyLibrarian', lazylibrarian.CONFIG['EMAIL_FROM']))
        message['To'] = lazylibrarian.CONFIG['EMAIL_TO']

        logger.debug('Email notification: %s' % message['Subject'])
        logger.debug('Email from: %s' % message['From'])
        logger.debug('Email to: %s' % message['To'])
        logger.debug('Email text: %s' % text)

        try:
            if lazylibrarian.CONFIG['EMAIL_SSL']:
                mailserver = smtplib.SMTP_SSL(lazylibrarian.CONFIG['EMAIL_SMTP_SERVER'],
                                                check_int(lazylibrarian.CONFIG['EMAIL_SMTP_PORT'], 465))
            else:
                mailserver = smtplib.SMTP(lazylibrarian.CONFIG['EMAIL_SMTP_SERVER'],
                                            check_int(lazylibrarian.CONFIG['EMAIL_SMTP_PORT'], 25))

            if lazylibrarian.CONFIG['EMAIL_TLS'] == 'True':
                mailserver.starttls()
            else:
                mailserver.ehlo()

            if lazylibrarian.CONFIG['EMAIL_SMTP_USER']:
                mailserver.login(lazylibrarian.CONFIG['EMAIL_SMTP_USER'], lazylibrarian.CONFIG['EMAIL_SMTP_PASSWORD'])

            mailserver.sendmail(lazylibrarian.CONFIG['EMAIL_FROM'], lazylibrarian.CONFIG['EMAIL_TO'], message.as_string())
            mailserver.quit()
            return True

        except Exception as e:
            logger.warn('Error sending Email: %s' % e)
            return False

        #
        # Public functions
        #

    def notify_snatch(self, title):
        if lazylibrarian.CONFIG['EMAIL_NOTIFY_ONSNATCH']:
            self._notify(message=title, event=notifyStrings[NOTIFY_SNATCH])

    def notify_download(self, title):
        if lazylibrarian.CONFIG['EMAIL_NOTIFY_ONDOWNLOAD']:
            self._notify(message=title, event=notifyStrings[NOTIFY_DOWNLOAD])

    def test_notify(self, title="Test"):
        return self._notify(message="This is a test notification from LazyLibrarian", event=title, force=True)


notifier = EmailNotifier
