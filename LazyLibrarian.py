#!/usr/bin/env python2
# -*- coding: UTF-8 -*-
# first line tries to force python2 in case system defaults to python3 (eg freenas)
import ConfigParser
import locale
import os
import platform
import stat
import sys
import threading
import time
import re

import lazylibrarian
from lazylibrarian import webStart, logger, versioncheck, dbupgrade
from lazylibrarian.formatter import check_int

# The following should probably be made configurable at the settings level
# This fix is put in place for systems with broken SSL (like QNAP)
opt_out_of_certificate_verification = True
if opt_out_of_certificate_verification:
    try:
        import ssl
        ssl._create_default_https_context = ssl._create_unverified_context
    except:
        pass


# ==== end block (should be configurable at settings level)


def main():
    # rename this thread
    threading.currentThread().name = "MAIN"

    # Set paths
    if hasattr(sys, 'frozen'):
        lazylibrarian.FULL_PATH = os.path.abspath(sys.executable)
    else:
        lazylibrarian.FULL_PATH = os.path.abspath(__file__)

    lazylibrarian.PROG_DIR = os.path.dirname(lazylibrarian.FULL_PATH)
    lazylibrarian.ARGS = sys.argv[1:]

    lazylibrarian.SYS_ENCODING = None

    try:
        locale.setlocale(locale.LC_ALL, "")
        lazylibrarian.SYS_ENCODING = locale.getpreferredencoding()
    except (locale.Error, IOError):
        pass

    # for OSes that are poorly configured I'll just force UTF-8
    # windows cp1252 can't handle some accented author names,
    # eg "Marie Kondō" U+014D: LATIN SMALL LETTER O WITH MACRON, but utf-8 does
    if not lazylibrarian.SYS_ENCODING or lazylibrarian.SYS_ENCODING in (
            'ANSI_X3.4-1968', 'US-ASCII', 'ASCII') or '1252' in lazylibrarian.SYS_ENCODING:
        lazylibrarian.SYS_ENCODING = 'UTF-8'

    # Set arguments
    from optparse import OptionParser

    p = OptionParser()
    p.add_option('-d', '--daemon', action="store_true",
                 dest='daemon', help="Run the server as a daemon")
    p.add_option('-q', '--quiet', action="store_true",
                 dest='quiet', help="Don't log to console")
    p.add_option('--debug', action="store_true",
                 dest='debug', help="Show debuglog messages")
    p.add_option('--nolaunch', action="store_true",
                 dest='nolaunch', help="Don't start browser")
    p.add_option('--update', action="store_true",
                 dest='update', help="Update to latest version (only git or source installs)")
    p.add_option('--port',
                 dest='port', default=None,
                 help="Force webinterface to listen on this port")
    p.add_option('--datadir',
                 dest='datadir', default=None,
                 help="Path to the data directory")
    p.add_option('--config',
                 dest='config', default=None,
                 help="Path to config.ini file")
    p.add_option('-p', '--pidfile',
                 dest='pidfile', default=None,
                 help="Store the process id in the given file")

    options, args = p.parse_args()

    lazylibrarian.LOGLEVEL = 1
    if options.debug:
        lazylibrarian.LOGLEVEL = 2

    if options.quiet:
        lazylibrarian.LOGLEVEL = 0

    if options.daemon:
        if 'windows' not in platform.system().lower():
            lazylibrarian.DAEMON = True
            # lazylibrarian.LOGLEVEL = 0
            lazylibrarian.daemonize()
        else:
            print("Daemonize not supported under Windows, starting normally")

    if options.nolaunch:
        lazylibrarian.CONFIG['LAUNCH_BROWSER'] = False

    if options.update:
        lazylibrarian.SIGNAL = 'update'
        # This is the "emergency recovery" update in case lazylibrarian won't start.
        # Set up some dummy values for the update as we have not read the config file yet
        lazylibrarian.CONFIG['GIT_PROGRAM'] = ''
        lazylibrarian.CONFIG['GIT_USER'] = 'dobytang'
        lazylibrarian.CONFIG['GIT_REPO'] = 'lazylibrarian'
        lazylibrarian.CONFIG['LOGLIMIT'] = 2000
        versioncheck.getInstallType()
        if lazylibrarian.CONFIG['INSTALL_TYPE'] not in ['git', 'source']:
            lazylibrarian.SIGNAL = None
            print('Cannot update, not a git or source installation')
        else:
            lazylibrarian.shutdown(restart=True, update=True)

    if options.datadir:
        lazylibrarian.DATADIR = str(options.datadir)
    else:
        lazylibrarian.DATADIR = lazylibrarian.PROG_DIR

    if options.config:
        lazylibrarian.CONFIGFILE = str(options.config)
    else:
        lazylibrarian.CONFIGFILE = os.path.join(lazylibrarian.DATADIR, "config.ini")

    if options.pidfile:
        if lazylibrarian.DAEMON:
            lazylibrarian.PIDFILE = str(options.pidfile)

    # create and check (optional) paths
    if not os.path.exists(lazylibrarian.DATADIR):
        try:
            os.makedirs(lazylibrarian.DATADIR)
        except OSError:
            raise SystemExit('Could not create data directory: ' + lazylibrarian.DATADIR + '. Exit ...')

    if not os.access(lazylibrarian.DATADIR, os.W_OK):
        raise SystemExit('Cannot write to the data directory: ' + lazylibrarian.DATADIR + '. Exit ...')

    print "Lazylibrarian is starting up..."
    time.sleep(4)  # allow a bit of time for old task to exit if restarting. Needs to free logfile and server port.

    # create database and config
    lazylibrarian.DBFILE = os.path.join(lazylibrarian.DATADIR, 'lazylibrarian.db')
    lazylibrarian.CFG = ConfigParser.RawConfigParser()
    lazylibrarian.CFG.read(lazylibrarian.CONFIGFILE)

    # REMINDER ############ NO LOGGING BEFORE HERE ###############
    # There is no point putting in any logging above this line, as its not set till after initialize.
    lazylibrarian.initialize()

    # Set the install type (win,git,source) &
    # check the version when the application starts
    versioncheck.checkForUpdates()

    logger.debug('Current Version [%s] - Latest remote version [%s] - Install type [%s]' % (
        lazylibrarian.CONFIG['CURRENT_VERSION'], lazylibrarian.CONFIG['LATEST_VERSION'], lazylibrarian.CONFIG['INSTALL_TYPE']))

    if lazylibrarian.CONFIG['VERSIONCHECK_INTERVAL'] == 0:
        logger.debug('Automatic update checks are disabled')
        # pretend we're up to date so we don't keep warning the user
        # version check button will still override this if you want to
        lazylibrarian.CONFIG['LATEST_VERSION'] = lazylibrarian.CONFIG['CURRENT_VERSION']
        lazylibrarian.CONFIG['COMMITS_BEHIND'] = 0
    else:
        if check_int(lazylibrarian.CONFIG['GIT_UPDATED'], 0) == 0:
            if lazylibrarian.CONFIG['CURRENT_VERSION'] == lazylibrarian.CONFIG['LATEST_VERSION']:
                if lazylibrarian.CONFIG['INSTALL_TYPE'] == 'git' and lazylibrarian.CONFIG['COMMITS_BEHIND'] == 0:
                    lazylibrarian.CONFIG['GIT_UPDATED'] = str(int(time.time()))
                    logger.debug('Setting update timestamp to now')

    version_file = os.path.join(lazylibrarian.PROG_DIR, 'version.txt')
    if not os.path.isfile(version_file) and lazylibrarian.CONFIG['INSTALL_TYPE'] == 'source':
        # User may be running an old source zip, so force update
        lazylibrarian.CONFIG['COMMITS_BEHIND'] = 1
        lazylibrarian.SIGNAL = 'update'

    if lazylibrarian.CONFIG['COMMITS_BEHIND'] <= 0 and lazylibrarian.SIGNAL == 'update':
        lazylibrarian.SIGNAL = None
        if lazylibrarian.CONFIG['COMMITS_BEHIND'] == 0:
            logger.debug('Not updating, LazyLibrarian is already up to date')
        else:
            logger.debug('Not updating, LazyLibrarian has local changes')

    if options.port:
        lazylibrarian.CONFIG['HTTP_PORT'] = int(options.port)
        logger.info('Starting LazyLibrarian on forced port: %s, webroot "%s"' %
                    (lazylibrarian.CONFIG['HTTP_PORT'], lazylibrarian.CONFIG['HTTP_ROOT']))
    else:
        lazylibrarian.CONFIG['HTTP_PORT'] = int(lazylibrarian.CONFIG['HTTP_PORT'])
        logger.info('Starting LazyLibrarian on port: %s, webroot "%s"' %
                    (lazylibrarian.CONFIG['HTTP_PORT'], lazylibrarian.CONFIG['HTTP_ROOT']))

    if lazylibrarian.DAEMON:
        lazylibrarian.daemonize()

    curr_ver = dbupgrade.upgrade_needed()
    if curr_ver:
        lazylibrarian.UPDATE_MSG = 'Updating database to version %s' % curr_ver

    # Try to start the server.
    webStart.initialize({
        'http_port': lazylibrarian.CONFIG['HTTP_PORT'],
        'http_host': lazylibrarian.CONFIG['HTTP_HOST'],
        'http_root': lazylibrarian.CONFIG['HTTP_ROOT'],
        'http_user': lazylibrarian.CONFIG['HTTP_USER'],
        'http_pass': lazylibrarian.CONFIG['HTTP_PASS'],
        'http_proxy': lazylibrarian.CONFIG['HTTP_PROXY'],
        'https_enabled': lazylibrarian.CONFIG['HTTPS_ENABLED'],
        'https_cert': lazylibrarian.CONFIG['HTTPS_CERT'],
        'https_key': lazylibrarian.CONFIG['HTTPS_KEY'],
    })

    if lazylibrarian.CONFIG['LAUNCH_BROWSER'] and not options.nolaunch:
        lazylibrarian.launch_browser(lazylibrarian.CONFIG['HTTP_HOST'], lazylibrarian.CONFIG['HTTP_PORT'], lazylibrarian.CONFIG['HTTP_ROOT'])

    if curr_ver:
        threading.Thread(target=dbupgrade.dbupgrade, name="DB_UPGRADE", args=[curr_ver]).start()

    lazylibrarian.start()

    while True:
        if not lazylibrarian.SIGNAL:
            try:
                time.sleep(1)
            except KeyboardInterrupt:
                lazylibrarian.shutdown()
        else:
            if lazylibrarian.SIGNAL == 'shutdown':
                lazylibrarian.shutdown()
            elif lazylibrarian.SIGNAL == 'restart':
                lazylibrarian.shutdown(restart=True)
            elif lazylibrarian.SIGNAL == 'update':
                lazylibrarian.shutdown(restart=True, update=True)
            lazylibrarian.SIGNAL = None


if __name__ == "__main__":
    main()
