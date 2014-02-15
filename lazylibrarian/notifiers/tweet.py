# Author: Nic Wolfe <nic@wolfeden.ca>
# URL: http://code.google.com/p/lazylibrarian/
#
# This file is part of Sick Beard.
#
# Sick Beard is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# Sick Beard is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
#  GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with Sick Beard.  If not, see <http://www.gnu.org/licenses/>.

import lazylibrarian

from lazylibrarian import logger, common, formatter

# parse_qsl moved to urlparse module in v2.6
try:
    from urlparse import parse_qsl #@UnusedImport
except:
    from cgi import parse_qsl #@Reimport

import lib.oauth2 as oauth
import lib.pythontwitter as twitter

class TwitterNotifier:

    consumer_key = "208JPTMMnZjtKWA4obcH8g"
    consumer_secret = "BKaHzaQRd5PK6EH8EqPZ1w8mz6NSk9KErArarinHutk"
    
    REQUEST_TOKEN_URL = 'https://api.twitter.com/oauth/request_token'
    ACCESS_TOKEN_URL  = 'https://api.twitter.com/oauth/access_token'
    AUTHORIZATION_URL = 'https://api.twitter.com/oauth/authorize'
    SIGNIN_URL        = 'https://api.twitter.com/oauth/authenticate'
    
    def notify_snatch(self, title):
        if lazylibrarian.TWITTER_NOTIFY_ONSNATCH:
            self._notifyTwitter(common.notifyStrings[common.NOTIFY_SNATCH]+': '+title)

    def notify_download(self, title):
        if lazylibrarian.TWITTER_NOTIFY_ONDOWNLOAD:
            self._notifyTwitter(common.notifyStrings[common.NOTIFY_DOWNLOAD]+': '+title)

    def test_notify(self):
        return self._notifyTwitter("This is a test notification from LazyLibrarian / " + formatter.now(), force=True)

    def _get_authorization(self):
    
        signature_method_hmac_sha1 = oauth.SignatureMethod_HMAC_SHA1() #@UnusedVariable
        oauth_consumer             = oauth.Consumer(key=self.consumer_key, secret=self.consumer_secret)
        oauth_client               = oauth.Client(oauth_consumer)
    
        logger.info('Requesting temp token from Twitter')
    
        resp, content = oauth_client.request(self.REQUEST_TOKEN_URL, 'GET')
    
        if resp['status'] != '200':
            logger.info('Invalid respond from Twitter requesting temp token: %s' % resp['status'])
        else:
            request_token = dict(parse_qsl(content))
    
            lazylibrarian.TWITTER_USERNAME = request_token['oauth_token']
            lazylibrarian.TWITTER_PASSWORD = request_token['oauth_token_secret']
    
            return self.AUTHORIZATION_URL+"?oauth_token="+ request_token['oauth_token']
    
    def _get_credentials(self, key):
        request_token = {}
    
        request_token['oauth_token'] = lazylibrarian.TWITTER_USERNAME
        request_token['oauth_token_secret'] = lazylibrarian.TWITTER_PASSWORD
        request_token['oauth_callback_confirmed'] = 'true'
    
        token = oauth.Token(request_token['oauth_token'], request_token['oauth_token_secret'])
        token.set_verifier(key)
    
        logger.info('Generating and signing request for an access token using key '+key)
    
        signature_method_hmac_sha1 = oauth.SignatureMethod_HMAC_SHA1() #@UnusedVariable
        oauth_consumer             = oauth.Consumer(key=self.consumer_key, secret=self.consumer_secret)
        logger.info('oauth_consumer: '+str(oauth_consumer))
        oauth_client  = oauth.Client(oauth_consumer, token)
        logger.info('oauth_client: '+str(oauth_client))
        resp, content = oauth_client.request(self.ACCESS_TOKEN_URL, method='POST', body='oauth_verifier=%s' % key)
        logger.info('resp, content: '+str(resp)+','+str(content))
    
        access_token  = dict(parse_qsl(content))
        logger.info('access_token: '+str(access_token))
    
        logger.info('resp[status] = '+str(resp['status']))
        if resp['status'] != '200':
            logger.error('The request for a token with did not succeed: '+str(resp['status']))
            return False
        else:
            logger.info('Your Twitter Access Token key: %s' % access_token['oauth_token'])
            logger.info('Access Token secret: %s' % access_token['oauth_token_secret'])
            lazylibrarian.TWITTER_USERNAME = access_token['oauth_token']
            lazylibrarian.TWITTER_PASSWORD = access_token['oauth_token_secret']
            return True
    
    
    def _send_tweet(self, message=None):
    
        username=self.consumer_key
        password=self.consumer_secret
        access_token_key=lazylibrarian.TWITTER_USERNAME
        access_token_secret=lazylibrarian.TWITTER_PASSWORD
    
        logger.info(u"Sending tweet: "+message)
    
        api = twitter.Api(username, password, access_token_key, access_token_secret)
    
        try:
            api.PostUpdate(message)
        except Exception, e:
            logger.error(u"Error Sending Tweet: %s" %e)
            return False
    
        return True
    
    def _notifyTwitter(self, message='', force=False):
        prefix = lazylibrarian.TWITTER_PREFIX
    
        if not lazylibrarian.USE_TWITTER and not force:
            return False
    
        return self._send_tweet(prefix+": "+message)

notifier = TwitterNotifier