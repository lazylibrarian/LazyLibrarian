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

from __future__ import print_function
import os
import sys

import cherrypy
import lib.cherrypy_cors as cherrypy_cors
import lazylibrarian
from lazylibrarian import logger
from lazylibrarian.webServe import WebInterface

cp_ver = getattr(cherrypy, '__version__', None)
if cp_ver and int(cp_ver.split('.')[0]) >= 10:
    try:
        import portend
    except ImportError:
        portend = None


def initialize(options=None):
    if options is None:
        options = {}
    https_enabled = options['https_enabled']
    https_cert = options['https_cert']
    https_key = options['https_key']

    if https_enabled:
        if not (os.path.exists(https_cert) and os.path.exists(https_key)):
            logger.warn("Disabled HTTPS because of missing certificate and key.")
            https_enabled = False

    options_dict = {
        'log.screen': False,
        'server.thread_pool': 10,
        'server.socket_port': options['http_port'],
        'server.socket_host': options['http_host'],
        'engine.autoreload.on': False,
        'tools.encode.on': True,
        'tools.encode.encoding': 'utf-8',
        'tools.decode.on': True,
        'error_page.401': lazylibrarian.common.error_page_401,
    }

    if https_enabled:
        options_dict['server.ssl_certificate'] = https_cert
        options_dict['server.ssl_private_key'] = https_key
        protocol = "https"
    else:
        protocol = "http"

    logger.info("Starting LazyLibrarian web server on %s://%s:%d/" %
                (protocol, options['http_host'], options['http_port']))
    cherrypy_cors.install()
    cherrypy.config.update(options_dict)

    conf = {
        '/': {
            # 'tools.staticdir.on': True,
            # 'tools.staticdir.dir': os.path.join(lazylibrarian.PROG_DIR, 'data'),
            'tools.staticdir.root': os.path.join(lazylibrarian.PROG_DIR, 'data'),
            'tools.proxy.on': options['http_proxy']  # pay attention to X-Forwarded-Proto header
        },
        '/api': {
            'cors.expose.on': True,
        },
        '/interfaces': {
            'tools.staticdir.on': True,
            'tools.staticdir.dir': os.path.join(lazylibrarian.PROG_DIR, 'data', 'interfaces')
        },
        '/images': {
            'tools.staticdir.on': True,
            'tools.staticdir.dir': os.path.join(lazylibrarian.PROG_DIR, 'data', 'images')
        },
        '/cache': {
            'tools.staticdir.on': True,
            'tools.staticdir.dir': lazylibrarian.CACHEDIR
        },
        '/css': {
            'tools.staticdir.on': True,
            'tools.staticdir.dir': os.path.join(lazylibrarian.PROG_DIR, 'data', 'css')
        },
        '/js': {
            'tools.staticdir.on': True,
            'tools.staticdir.dir': os.path.join(lazylibrarian.PROG_DIR, 'data', 'js')
        },
        '/favicon.ico': {
            'tools.staticfile.on': True,
            # 'tools.staticfile.filename': "images/favicon.ico"
            'tools.staticfile.filename': os.path.join(lazylibrarian.PROG_DIR, 'data', 'images', 'favicon.ico')
        }
    }

    if lazylibrarian.CONFIG['PROXY_LOCAL']:
        conf['/'].update({
            # NOTE default if not specified is to use apache style X-Forwarded-Host
            # 'tools.proxy.local': 'X-Forwarded-Host'  # this is for apache2
            # 'tools.proxy.local': 'Host'  # this is for nginx
            # 'tools.proxy.local': 'X-Host'  # this is for lighthttpd
            'tools.proxy.local': lazylibrarian.CONFIG['PROXY_LOCAL']
        })
    if options['http_pass'] != "":
        logger.info("Web server authentication is enabled, username is '%s'" % options['http_user'])
        conf['/'].update({
            'tools.auth_basic.on': True,
            'tools.auth_basic.realm': 'LazyLibrarian',
            'tools.auth_basic.checkpassword': cherrypy.lib.auth_basic.checkpassword_dict({
                options['http_user']: options['http_pass']
            })
        })
        conf['/api'].update({
            'tools.auth_basic.on': False,
        })
    if options['opds_authentication']:
        user_list = {}
        if len(options['opds_username']) > 0:
            user_list[options['opds_username']] = options['opds_password']
        if options['http_password'] is not None and options['http_username'] != options['opds_username']:
            user_list[options['http_username']] = options['http_password']
        conf['/opds'] = {'tools.auth_basic.on': True,
                         'tools.auth_basic.realm': 'LazyLibrarian OPDS',
                         'tools.auth_basic.checkpassword': cherrypy.lib.auth_basic.checkpassword_dict(user_list)}
    else:
        conf['/opds'] = {'tools.auth_basic.on': False}

    # Prevent time-outs
    cherrypy.engine.timeout_monitor.unsubscribe()
    cherrypy.tree.mount(WebInterface(), str(options['http_root']), config=conf)

    cherrypy.engine.autoreload.subscribe()

    try:
        if cp_ver and int(cp_ver.split('.')[0]) >= 10:
            portend.Checker().assert_free(str(options['http_host']), options['http_port'])
        else:
            cherrypy.process.servers.check_port(str(options['http_host']), options['http_port'])
        cherrypy.server.start()
    except Exception as e:
        print(str(e))
        print('Failed to start on port: %i. Is something else running?' % (options['http_port']))
        sys.exit(1)

    cherrypy.server.wait()
