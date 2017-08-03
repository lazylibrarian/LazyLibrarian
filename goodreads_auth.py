# oauth example for goodreads
#
# based on code found in https://gist.github.com/gpiancastelli/537923 by Giulio Piancastelli
#
# run it
# visit the url
# confirm that you have accepted
# write down token!
#
import sys
import urlparse

import lib.oauth2 as oauth

if len(sys.argv) !=3:
    print "Usage: goodreads_auth your_key your_secret"
elif sys.argv[1] == 'ckvsiSDsuqh7omh74ZZ6Q':
    print "Please get your own personal GoodReads api key from "
    print "https://www.goodreads.com/api/keys and try again"
else:
    url = 'http://www.goodreads.com'
    request_token_url = '%s/oauth/request_token' % url
    authorize_url = '%s/oauth/authorize' % url
    access_token_url = '%s/oauth/access_token' % url

    consumer = oauth.Consumer(key=sys.argv[1], secret=sys.argv[2])

    client = oauth.Client(consumer)

    response, content = client.request(request_token_url, 'GET')
    if response['status'] != '200':
        raise Exception('Invalid response: %s, content: ' % response['status'] + content)

    request_token = dict(urlparse.parse_qsl(content))

    authorize_link = '%s?oauth_token=%s' % (authorize_url,
                                            request_token['oauth_token'])
    if not authorize_link.startswith('http'):
        print authorize_link
    else:
        print "Use a browser to visit this link and accept your application:"
        print authorize_link
        accepted = 'n'
        while accepted.lower() == 'n':
            # you need to access the authorize_link via a browser,
            # and proceed to manually authorize the consumer
            accepted = raw_input('Have you authorized me? (y/n) ')

        token = oauth.Token(request_token['oauth_token'],
                            request_token['oauth_token_secret'])

        client = oauth.Client(consumer, token)
        response, content = client.request(access_token_url, 'POST')
        if response['status'] != '200':
            raise Exception('Invalid response: %s' % response['status'])

        access_token = dict(urlparse.parse_qsl(content))

        # this is the token you should save for future use
        print 'Enter these values in LazyLibrarian config...: '
        print 'oauth key:    ' + access_token['oauth_token']
        print 'oauth secret: ' + access_token['oauth_token_secret']
