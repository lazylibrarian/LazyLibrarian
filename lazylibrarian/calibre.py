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

from subprocess import Popen, PIPE

import lazylibrarian
from lazylibrarian import logger

# calibredb search "#label":"false"
# calibredb custom_columns
# calibredb add_custom_column label name bool
# calibredb remove_custom_column --force label
# calibredb set_custom column id value


def calibredb(cmd=None, prelib=None, postlib=None):
    """ calibre-server needs to be started with --enable-auth and needs user/password to add/remove books
        only basic features are available without auth. calibre_server should look like  http://address:port/#library
        default library is used if no #library in the url
        or calibredb can talk to the database file as long as there is no running calibre """

    if not lazylibrarian.CONFIG['IMP_CALIBREDB']:
        return "No calibredb set in config", '', 1

    params = [lazylibrarian.CONFIG['IMP_CALIBREDB'], cmd]
    if lazylibrarian.CONFIG['CALIBRE_USE_SERVER']:
        dest_url = lazylibrarian.CONFIG['CALIBRE_SERVER']
        if lazylibrarian.CONFIG['CALIBRE_USER'] and lazylibrarian.CONFIG['CALIBRE_PASS']:
            params.extend(['--username', lazylibrarian.CONFIG['CALIBRE_USER'],
                           '--password', lazylibrarian.CONFIG['CALIBRE_PASS']])
    else:
        dest_url = lazylibrarian.DIRECTORY('eBook')

    if prelib:
        params.extend(prelib)
    if cmd != "--version":
        params.extend(['--with-library', dest_url])
    if postlib:
        params.extend(postlib)
    logger.debug(str(params))
    res = err = ''
    try:
        p = Popen(params, stdout=PIPE, stderr=PIPE)
        res, err = p.communicate()
        rc = p.returncode
        if rc:
            if 'Errno 111' in err:
                logger.debug("calibredb returned %s: Connection refused" % rc)
            else:
                logger.debug("calibredb returned %s: res[%s] err[%s]" % (rc, res, err))
    except Exception as e:
        logger.debug("calibredb exception: %s %s" % (type(e).__name__, str(e)))
        rc = 1

    if rc and dest_url.startswith('http'):
        # might be no server running, retry using file
        params = [lazylibrarian.CONFIG['IMP_CALIBREDB'], cmd]
        if prelib:
            params.extend(prelib)
        params.extend(['--with-library', lazylibrarian.DIRECTORY('eBook')])
        if postlib:
            params.extend(postlib)
        logger.debug(str(params))
        try:
            q = Popen(params, stdout=PIPE, stderr=PIPE)
            res, err = q.communicate()
            rc = q.returncode
            if rc:
                logger.debug("calibredb retry returned %s: res[%s] err[%s]" % (rc, res, err))
        except Exception as e:
            logger.debug("calibredb retry exception: %s %s" % (type(e).__name__, str(e)))
    return res, err, rc
