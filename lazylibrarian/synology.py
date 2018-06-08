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


import json

import lazylibrarian
from lazylibrarian import logger
from lazylibrarian.cache import fetchURL
from lazylibrarian.formatter import check_int
# noinspection PyUnresolvedReferences
from lib.six.moves.urllib_parse import urlencode


def _getJSON(URL, params):
    # Get JSON response from URL
    # Return json,True or error_msg,False

    URL += "/?%s" % urlencode(params)
    result, success = fetchURL(URL, retry=False)
    if success:
        try:
            result_json = json.loads(result)
            return result_json, True
        except (ValueError, AttributeError):
            return "Could not convert response to json", False

    return "getJSON returned %s" % result, False


def _errorMsg(errnum, api):
    # Convert DownloadStation errnum to an error message depending on which api call
    generic_errors = {
        100: 'Unknown error',
        101: 'Invalid parameter',
        102: 'The requested API does not exist',
        103: 'The requested method does not exist',
        104: 'The requested version does not support the functionality',
        105: 'The logged in session does not have permission',
        106: 'Session timeout',
        107: 'Session interrupted by duplicate login',
    }
    create_errors = {
        400: 'File upload failed',
        401: 'Max number of tasks reached',
        402: 'Destination denied',
        403: 'Destination does not exist',
        404: 'Invalid task id',
        405: 'Invalid task action',
        406: 'No default destination',
        407: 'Set destination failed',
        408: 'File does not exist'
    }
    login_errors = {
        400: 'No such account or incorrect password',
        401: 'Account disabled',
        402: 'Permission denied',
        403: '2-step verification code required',
        404: 'Failed to authenticate 2-step verification code'
    }
    if errnum in generic_errors:
        return generic_errors[errnum]
    if api == "login" and errnum in login_errors:
        return login_errors[errnum]
    if api == "create" and errnum in create_errors:
        return create_errors[errnum]
    return "Unknown error code in %s: %s" % (api, str(errnum))


def _login(hosturl):
    # Query the DownloadStation for api info and then log user in
    # return auth_cgi,task_cgi,sid or "","",""
    URL = hosturl + 'query.cgi'
    params = {
        "api": "SYNO.API.Info",
        "version": "1",
        "method": "query",
        "query": "SYNO.API.Auth,SYNO.DownloadStation.Task"
    }

    result, success = _getJSON(URL, params)
    if success:
        if not result['success']:
            errnum = result['error']['code']
            logger.debug("Synology API Error: %s" % _errorMsg(errnum, "query"))
            return "", "", ""
        else:
            auth_cgi = result['data']['SYNO.API.Auth']['path']
            task_cgi = result['data']['SYNO.DownloadStation.Task']['path']
    else:
        logger.debug("Synology Failed to get API info: %s" % result)
        return "", "", ""

    URL = hosturl + auth_cgi
    params = {
        "api": "SYNO.API.Auth",
        "version": "2",
        "method": "login",
        "account": lazylibrarian.CONFIG['SYNOLOGY_USER'],
        "passwd": lazylibrarian.CONFIG['SYNOLOGY_PASS'],
        "session": "LazyLibrarian",
        "format": "sid"
    }

    result, success = _getJSON(URL, params)
    if success:
        if not result['success']:
            errnum = result['error']['code']
            logger.debug("Synology Login Error: %s" % _errorMsg(errnum, "login"))
            return "", "", ""
        else:
            return hosturl + auth_cgi, hosturl + task_cgi, result['data']['sid']
    else:
        logger.debug("Synology Failed to login: %s" % result)
        return "", "", ""


def _logout(auth_cgi, sid):
    # Logout from session, return True or False

    params = {
        "api": "SYNO.API.Auth",
        "version": "1",
        "method": "logout",
        "session": "LazyLibrarian",
        "_sid": sid
    }

    result, success = _getJSON(auth_cgi, params)
    return success


def _listTasks(task_cgi, sid):
    # Get a list of running downloads and return as json, or "" if fail

    params = {
        "api": "SYNO.DownloadStation.Task",
        "version": "1",
        "method": "list",
        "session": "LazyLibrarian",
        "_sid": sid
    }

    result, success = _getJSON(task_cgi, params)

    if success:
        if not result['success']:
            errnum = result['error']['code']
            logger.debug("Synology Task Error: %s" % _errorMsg(errnum, "list"))
        else:
            items = result['data']
            logger.debug("Synology Nr. Tasks = %s" % items['total'])
            return items['tasks']
    else:
        logger.debug("Synology Failed to get task list: " + result)
    return ""


def _getInfo(task_cgi, sid, download_id):
    # Get additional info on a download_id, return json or "" if fail

    params = {
        "api": "SYNO.DownloadStation.Task",
        "version": "1",
        "method": "getinfo",
        "id": download_id,
        "additional": "detail",
        "session": "LazyLibrarian",
        "_sid": sid
    }

    result, success = _getJSON(task_cgi, params)
    logger.debug("Result from getInfo = %s" % repr(result))
    if success:
        if not result['success']:
            errnum = result['error']['code']
            logger.debug("Synology GetInfo Error: %s" % _errorMsg(errnum, "getinfo"))
        else:
            if result and 'data' in result:
                try:
                    return result['data']['tasks'][0]
                except KeyError:
                    logger.debug("Synology GetInfo invalid result: %s" % repr(result['data']))
                    return ""
    return ""


def _deleteTask(task_cgi, sid, download_id, remove_data):
    # Delete a download task, return True or False

    params = {
        "api": "SYNO.DownloadStation.Task",
        "version": "1",
        "method": "delete",
        "id": download_id,
        "force_complete": remove_data,
        "session": "LazyLibrarian",
        "_sid": sid
    }

    result, success = _getJSON(task_cgi, params)
    logger.debug("Result from delete: %s" % repr(result))
    if success:
        if not result['success']:
            errnum = result['error']['code']
            logger.debug("Synology Delete Error: %s" % _errorMsg(errnum, "delete"))
        else:
            try:
                errnum = result['data']['error']
            except KeyError:
                errnum = 0
            if errnum:
                logger.debug("Synology Delete exited: %s" % _errorMsg(errnum, "delete"))
                return False
            return True
    return False


def _addTorrentURI(task_cgi, sid, torurl):
    # Sends a magnet, Torrent url or NZB url to DownloadStation
    # Return task ID, or False if failed

    params = {
        "api": "SYNO.DownloadStation.Task",
        "version": "1",
        "method": "create",
        "session": "LazyLibrarian",
        "uri": torurl,
        "destination": lazylibrarian.CONFIG['SYNOLOGY_DIR'],
        "_sid": sid
    }

    result, success = _getJSON(task_cgi, params)
    logger.debug("Result from create = %s" % repr(result))
    if success:
        if not result['success']:
            errnum = result['error']['code']
            logger.debug("Synology Create Error: %s" % _errorMsg(errnum, "create"))
        else:
            # DownloadStation doesn't return the download_id for the newly added uri
            # which we need for monitoring progress & deleting etc.
            # so we have to scan the task list to get the id
            for task in _listTasks(task_cgi, sid):  # type: dict
                if task['status'] == 'error':
                    try:
                        errmsg = task['status_extra']['error_detail']
                    except KeyError:
                        errmsg = "No error details"
                    logger.warn("Synology task [%s] failed: %s" % (task['title'], errmsg))
                else:
                    info = _getInfo(task_cgi, sid, task['id'])  # type: dict
                    try:
                        uri = info['additional']['detail']['uri']
                        if uri == torurl:
                            logger.debug('Synology task %s for %s' % (task['id'], task['title']))
                            return task['id']
                    except KeyError:
                        logger.debug("Unable to get uri for [%s] from getInfo" % task['title'])
            logger.debug("Synology URL [%s] was not found in tasklist" % torurl)
            return False
    else:
        logger.debug("Synology Failed to add task: %s" % result)
    return False


def _hostURL():
    # Build webapi_url from config settings
    host = lazylibrarian.CONFIG['SYNOLOGY_HOST']
    port = check_int(lazylibrarian.CONFIG['SYNOLOGY_PORT'], 0)
    if not host or not port:
        logger.debug("Invalid Synology host or port, check your config")
        return False
    if not host.startswith("http://") and not host.startswith("https://"):
        host = 'http://' + host
    if host.endswith('/'):
        host = host[:-1]
    return "%s:%s/webapi/" % (host, port)


#
# Public functions
#
def checkLink():
    # Make sure we can login to the synology drivestation
    # This function is used by the "test synology" button
    # to return a message giving success or fail
    msg = "Synology login FAILED\nCheck debug log"
    hosturl = _hostURL()
    if hosturl:
        auth_cgi, task_cgi, sid = _login(hosturl)
        if sid:
            msg = "Synology login successful"
            _logout(auth_cgi, sid)
    return msg


def removeTorrent(hashID, remove_data=False):
    # remove a torrent using hashID, and optionally delete the data
    # return True/False
    hosturl = _hostURL()
    if hosturl:
        auth_cgi, task_cgi, sid = _login(hosturl)
        if sid:
            result = _deleteTask(task_cgi, sid, hashID, remove_data)
            _logout(auth_cgi, sid)
            return result
    return False


def getName(download_id):
    # get the name of a download from it's download_id
    # return "" if not found
    hosturl = _hostURL()
    if hosturl:
        auth_cgi, task_cgi, sid = _login(hosturl)
        if sid:
            result = _getInfo(task_cgi, sid, download_id)  # type: dict
            _logout(auth_cgi, sid)
            if result and 'title' in result:
                return result['title']
    return ""


def getFiles(download_id):
    # get the name of a download from it's download_id
    # return "" if not found
    hosturl = _hostURL()
    if hosturl:
        auth_cgi, task_cgi, sid = _login(hosturl)
        if sid:
            result = _getInfo(task_cgi, sid, download_id)  # type: dict
            _logout(auth_cgi, sid)
            if result and 'additional' in result:
                try:
                    return result['additional']['file']
                except KeyError:
                    return ""
    return ""


def addTorrent(tor_url):
    # add a torrent/magnet/nzb to synology downloadstation
    # return it's id, or return False if error
    hosturl = _hostURL()
    if hosturl:
        auth_cgi, task_cgi, sid = _login(hosturl)
        if sid:
            result = _addTorrentURI(task_cgi, sid, tor_url)
            _logout(auth_cgi, sid)
            return result
    return False
