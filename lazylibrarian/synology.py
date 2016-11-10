#!/usr/bin/python

import urllib
import urllib2
import socket
import json
import ssl
import lazylibrarian
from lazylibrarian import logger
from lazylibrarian.common import USER_AGENT


def _getJSON(URL, params):
    # Get JSON response from URL
    # Return True,json or False,error_msg
    data = urllib.urlencode(params)
    request = urllib2.Request(URL, data)
    if lazylibrarian.PROXY_HOST:
        request.set_proxy(lazylibrarian.PROXY_HOST, lazylibrarian.PROXY_TYPE)
    request.add_header('User-Agent', USER_AGENT)

    try:
        resp = urllib2.urlopen(request, timeout=30)
        if str(resp.getcode()).startswith("2"):
            # (200 OK etc)
            try:
                result = resp.read()
                try:
                    result_json = json.JSONDecoder().decode(result)
                    return True, result_json
                except (ValueError, AttributeError):
                    return False, "Could not convert response to json"
            except socket.error as e:
                return False, "Socket error %s" % str(e)
        else:
            return False, "Error code %s" % resp.getcode()
    except (socket.timeout) as e:
        return False, "Timeout"
    except (urllib2.HTTPError, urllib2.URLError, ssl.SSLError) as e:
        if hasattr(e, 'reason'):
            return False, "%s" %  e.reason
        else:
            return False, "%s" % str(e)


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
    params =    {
                    "api": "SYNO.API.Info",
                    "version": "1",
                    "method": "query",
                    "query": "SYNO.API.Auth,SYNO.DownloadStation.Task"
                }

    success, result = _getJSON(URL, params)
    if success:
        if not result['success']:
            errnum = result['error']['code']
            logger.debug("Synology API Error: %s" % _errorMsg(errnum, "query"))
            return "","",""
        else:
            auth_cgi = result['data']['SYNO.API.Auth']['path']
            task_cgi = result['data']['SYNO.DownloadStation.Task']['path']
    else:
        logger.debug("Synology Failed to get API info: %s" % result)
        return "","",""

    URL = hosturl + auth_cgi
    params =    {
                    "api": "SYNO.API.Auth",
                    "version": "2",
                    "method": "login",
                    "account": lazylibrarian.SYNOLOGY_USER,
                    "passwd": lazylibrarian.SYNOLOGY_PASS,
                    "session": "LazyLibrarian",
                    "format": "sid"
                }

    success, result = _getJSON(URL, params)
    if success:
        if not result['success']:
            errnum = result['error']['code']
            logger.debug("Synology Login Error: %s" % _errorMsg(errnum, "login"))
            return "","",""
        else:
            return hosturl + auth_cgi, hosturl + task_cgi, result['data']['sid']
    else:
        logger.debug("Synology Failed to login: %s" % result)
        return "","",""


def _logout(auth_cgi, sid):
    # Logout from session, return True or False

    params =    {
                    "api": "SYNO.API.Auth",
                    "version": "1",
                    "method": "logout",
                    "session": "LazyLibrarian",
                    "_sid": sid
                }

    success, result = _getJSON(auth_cgi, params)
    return success

def _listTasks(task_cgi, sid):
    # Get a list of running downloads and return as json, or "" if fail

    params =    {
                    "api": "SYNO.DownloadStation.Task",
                    "version": "1",
                    "method": "list",
                    "session": "LazyLibrarian",
                    "_sid": sid
                }

    success, result = _getJSON(task_cgi, params)

    if success:
        if not result['success']:
            errnum = result['error']['code']
            logger.debug("Synology Task Error: %s"  % _errorMsg(errnum, "list"))
        else:
            items = result['data']
            logger.debug("Synology Nr. Tasks = %s" % items['total'])
            return items['tasks']
    else:
        logger.debug("Synology Failed to get task list: " + result)
    return ""


def _getInfo(task_cgi, sid, download_id):
    # Get additional info on a download_id, return json or "" if fail

    params =    {
                    "api": "SYNO.DownloadStation.Task",
                    "version": "1",
                    "method": "getinfo",
                    "id": download_id,
                    "additional": "detail",
                    "session": "LazyLibrarian",
                    "_sid": sid
                }

    success, result = _getJSON(task_cgi, params)
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

    params =    {
                    "api": "SYNO.DownloadStation.Task",
                    "version": "1",
                    "method": "delete",
                    "id": download_id,
                    "force_complete": remove_data,
                    "session": "LazyLibrarian",
                    "_sid": sid
                }

    success, result = _getJSON(task_cgi, params)
    logger.debug("Result from delete: %s" % repr(result))
    if success:
        if not result['success']:
            errnum = result['error']['code']
            logger.debug("Synology Delete Error: %s" % _errorMsg(errnum, "delete"))
        else:
            try:
                errnum = result['data']['error']
            except KeyError, TypeError:
                errnum = 0
            if errnum:
                logger.debug("Synology Delete exited: %s" % _errorMsg(errnum, "delete"))
                return False
            return True
    return False


def _addTorrentURI(task_cgi, sid, torurl):
    # Sends a magnet, Torrent url or NZB url to DownloadStation
    # Return task ID, or False if failed

    params =    {
                    "api": "SYNO.DownloadStation.Task",
                    "version": "1",
                    "method": "create",
                    "session": "LazyLibrarian",
                    "uri": torurl,
                    "destination": lazylibrarian.SYNOLOGY_DIR,
                    "_sid": sid
                }

    success, result = _getJSON(task_cgi, params)
    logger.debug("Result from create = %s" % repr(result))
    if success:
        if not result['success']:
            errnum = result['error']['code']
            logger.debug("Synology Create Error: %s" % _errorMsg(errnum, "create"))
        else:
            # DownloadStation doesn't return the download_id for the newly added uri
            # which we need for monitoring progress & deleting etc.
            # so we have to scan the task list to get the id
            for task in _listTasks(task_cgi, sid):
                if task['status'] == 'error':
                    try:
                        errmsg = task['status_extra']['error_detail']
                    except KeyError, TypeError:
                        errmsg = "No error details"
                    logger.warn("Synology task [%s] failed: %s" % (task['title'], errmsg))
                else:
                    info = _getInfo(task_cgi, sid, task['id'])
                    try:
                        uri = info['additional']['detail']['uri']
                        if uri == torurl:
                            logger.debug('Synology task %s for %s' % (task['id'], task['title']))
                            return task['id']
                    except KeyError, TypeError:
                        logger.debug("Unable to get uri for [%s] from getInfo" % task['title'])
            logger.debug("Synology URL [%s] was not found in tasklist" % torurl)
            return False
    else:
        logger.debug("Synology Failed to add task: %s" % result)
    return False


def _hostURL():
    # Build webapi_url from config settings
    host = lazylibrarian.SYNOLOGY_HOST
    port = lazylibrarian.SYNOLOGY_PORT
    if not host:
        logger.debug("Synology host not defined, check config")
        return False
    if not host.startswith('http'):
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
            result = _getInfo(task_cgi, sid, download_id)
            _logout(auth_cgi, sid)
            if result and 'title' in result:
                return result['title']
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
