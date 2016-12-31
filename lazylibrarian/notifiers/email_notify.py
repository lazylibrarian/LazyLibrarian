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


class EmailNotifier:
    def _notify(self, message, event, force=False):

        # suppress notifications if the notifier is disabled but the notify options are checked
        if not lazylibrarian.USE_EMAIL and not force:
            return False

        subject = event
        text = message
        message = MIMEText(message, 'plain', "utf-8")
        message['Subject'] = subject
        message['From'] = email.utils.formataddr(('LazyLibrarian', lazylibrarian.EMAIL_FROM))
        message['To'] = lazylibrarian.EMAIL_TO

        logger.debug('Email notification: %s' % message['Subject'])
        logger.debug('Email from: %s' % message['From'])
        logger.debug('Email to: %s' % message['To'])
        logger.debug('Email text: %s' % text)

        try:
            if lazylibrarian.EMAIL_SSL:
                mailserver = smtplib.SMTP_SSL(lazylibrarian.EMAIL_SMTP_SERVER, lazylibrarian.EMAIL_SMTP_PORT)
            else:
                mailserver = smtplib.SMTP(lazylibrarian.EMAIL_SMTP_SERVER, lazylibrarian.EMAIL_SMTP_PORT)

            if lazylibrarian.EMAIL_TLS:
                mailserver.starttls()

            mailserver.ehlo()

            if lazylibrarian.EMAIL_SMTP_USER:
                mailserver.login(lazylibrarian.EMAIL_SMTP_USER, lazylibrarian.EMAIL_SMTP_PASSWORD)

            mailserver.sendmail(lazylibrarian.EMAIL_FROM, lazylibrarian.EMAIL_TO, message.as_string())
            mailserver.quit()
            return True

        except Exception as e:
            logger.warn('Error sending Email: %s' % e)
            return False

        #
        # Public functions
        #

    def notify_snatch(self, title):
        if lazylibrarian.EMAIL_NOTIFY_ONSNATCH:
            self._notify(message=title, event=notifyStrings[NOTIFY_SNATCH])

    def notify_download(self, title):
        if lazylibrarian.EMAIL_NOTIFY_ONDOWNLOAD:
            self._notify(message=title, event=notifyStrings[NOTIFY_DOWNLOAD])

    def test_notify(self, title="Test"):
        return self._notify(message="This is a test notification from LazyLibrarian", event=title, force=True)


notifier = EmailNotifier
