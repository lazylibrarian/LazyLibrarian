import os, sys, time, cherrypy, threading, locale
from lib.configobj import ConfigObj

import lazylibrarian
from lazylibrarian import webStart, logger

def main():
	#DIFFEREMT
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
    if not lazylibrarian.SYS_ENCODING or lazylibrarian.SYS_ENCODING in ('ANSI_X3.4-1968', 'US-ASCII', 'ASCII'):
        lazylibrarian.SYS_ENCODING = 'UTF-8'

	#check the version when the application starts
    from lazylibrarian import versioncheck
    lazylibrarian.CURRENT_VERSION = versioncheck.getVersion()
    LATEST_VERSION = versioncheck.checkGithub()

    # Set arguments
    from optparse import OptionParser

    p = OptionParser()
    p.add_option('-d', '--daemon', action = "store_true",
                 dest = 'daemon', help = "Run the server as a daemon")
    p.add_option('-q', '--quiet', action = "store_true",
                 dest = 'quiet', help = "Don't log to console")
    p.add_option('--debug', action="store_true",
                 dest = 'debug', help = "Show debuglog messages")
    p.add_option('--nolaunch', action = "store_true",
                 dest = 'nolaunch', help="Don't start browser")
    p.add_option('--port',
                 dest = 'port', default = None,
                 help = "Force webinterface to listen on this port")
    p.add_option('--datadir',
                 dest = 'datadir', default = None,
                 help = "Path to the data directory")
    p.add_option('--config',
                 dest = 'config', default = None,
                 help = "Path to config.ini file")
    p.add_option('-p', '--pidfile',
                 dest = 'pidfile', default = None,
                 help = "Store the process id in the given file")

    options, args = p.parse_args()

    if options.debug:
        lazylibrarian.LOGLEVEL = 2

    if options.quiet:
        lazylibrarian.LOGLEVEL = 0

    if options.daemon:
        if not sys.platform == 'win32':
            lazylibrarian.DAEMON = True
            lazylibrarian.LOGLEVEL = 0
            lazylibrarian.daemonize()
        else:
            print "Daemonize not supported under Windows, starting normally"

    if options.nolaunch:
        lazylibrarian.LAUNCH_BROWSER = False

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

    # create database and config
    lazylibrarian.DBFILE = os.path.join(lazylibrarian.DATADIR, 'lazylibrarian.db')
    lazylibrarian.CFG = ConfigObj(lazylibrarian.CONFIGFILE, encoding='utf-8')

    lazylibrarian.initialize()

    if options.port:
        HTTP_PORT = int(options.port)
        logger.info('Starting LazyLibrarian on forced port: %s' % HTTP_PORT)
    else:
        HTTP_PORT = int(lazylibrarian.HTTP_PORT)
        logger.info('Starting LazyLibrarian on port: %s' % lazylibrarian.HTTP_PORT)

    if lazylibrarian.DAEMON:
        lazylibrarian.daemonize()

    # Try to start the server. 
    webStart.initialize({
                    'http_port': HTTP_PORT,
                    'http_host': lazylibrarian.HTTP_HOST,
                    'http_root': lazylibrarian.HTTP_ROOT,
                    'http_user': lazylibrarian.HTTP_USER,
                    'http_pass': lazylibrarian.HTTP_PASS,
            })

    if lazylibrarian.LAUNCH_BROWSER and not options.nolaunch:
        lazylibrarian.launch_browser(lazylibrarian.HTTP_HOST, lazylibrarian.HTTP_PORT, lazylibrarian.HTTP_ROOT)

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
            else:
                lazylibrarian.shutdown(restart=True, update=True)
            lazylibrarian.SIGNAL = None
    return

if __name__ == "__main__":
    main()
