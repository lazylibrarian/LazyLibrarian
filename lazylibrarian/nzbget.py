# This file is modified to work with lazylibrarian by CurlyMo <curlymoo1@gmail.com>
# as a part of XBian - XBMC on the Raspberry Pi

# Author: Nic Wolfe <nic@wolfeden.ca>
# URL: http://code.google.com/p/sickbeard/
#
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
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with LazyLibrarian.  If not, see <http://www.gnu.org/licenses/>.


from base64 import standard_b64encode

import lazylibrarian
from lazylibrarian import logger
from lazylibrarian.formatter import check_int
# noinspection PyUnresolvedReferences
from lib.six.moves import xmlrpc_client, http_client


def checkLink():
    # socket.setdefaulttimeout(2)
    test = sendNZB(cmd="test")
    # socket.setdefaulttimeout(None)
    if test:
        return "NZBget connection successful"
    return "NZBget connection FAILED\nCheck debug log"


def deleteNZB(nzbID, remove_data=False):
    if remove_data:
        sendNZB(cmd='GroupFinalDelete', nzbID=nzbID)
        return sendNZB(cmd='HistoryFinalDelete', nzbID=nzbID)
    else:
        sendNZB(cmd='GroupDelete', nzbID=nzbID)
        return sendNZB(cmd='HistoryDelete', nzbID=nzbID)


def sendNZB(nzb=None, cmd=None, nzbID=None):
    # we can send a new nzb, or commands to act on an existing nzbID (or array of nzbIDs)
    # by setting nzbID and cmd (we currently only use test, listgroups and delete)

    host = lazylibrarian.CONFIG['NZBGET_HOST']
    port = check_int(lazylibrarian.CONFIG['NZBGET_PORT'], 0)
    if not host or not port:
        res = 'Invalid NZBget host or port, check your config'
        logger.error(res)
        return False, res

    addToTop = False
    nzbgetXMLrpc = "%(username)s:%(password)s@%(host)s:%(port)s/xmlrpc"

    if not host.startswith("http://") and not host.startswith("https://"):
        host = 'http://' + host

    if host.endswith('/'):
        host = host[:-1]
    hostparts = host.split('://')

    url = hostparts[0] + '://' + nzbgetXMLrpc % {"host": hostparts[1], "username": lazylibrarian.CONFIG['NZBGET_USER'],
                                                 "port": port,
                                                 "password": lazylibrarian.CONFIG['NZBGET_PASS']}
    try:
        nzbGetRPC = xmlrpc_client.ServerProxy(url)
    except Exception as e:
        res = "NZBget connection to %s failed: %s %s" % (url, type(e).__name__, str(e))
        logger.error(res)
        return False, res

    if cmd == "test":
        msg = "lazylibrarian connection test"
    elif nzbID:
        msg = "lazylibrarian connected to %s %s" % (cmd, nzbID)
    else:
        msg = "lazylibrarian connected to drop off %s any moment now." % (nzb.name + ".nzb")

    try:
        if nzbGetRPC.writelog("INFO", msg):
            logger.debug("Successfully connected to NZBget")
            if cmd == "test":
                # should check nzbget category is valid
                return True, ''
        else:
            if nzbID is not None:
                res = "Successfully connected to NZBget, unable to send message"
                logger.debug(res)
                return False, res
            else:
                logger.info("Successfully connected to NZBget, but unable to send %s" % (nzb.name + ".nzb"))

    except http_client.socket.error as e:
        res = "Please check your NZBget host and port (if it is running). "
        res += "NZBget is not responding to this combination: %s" % e
        logger.error(res)
        logger.error("NZBget url set to [%s]" % url)
        return False, res

    except xmlrpc_client.ProtocolError as e:
        if e.errmsg == "Unauthorized":
            res = "NZBget password is incorrect."
        else:
            res = "Protocol Error: %s" % e.errmsg
        logger.error(res)
        return False, res

    if nzbID is not None:
        # its a command for an existing task
        id_array = [int(nzbID)]
        if cmd in ['GroupDelete', 'GroupFinalDelete', 'HistoryDelete', 'HistoryFinalDelete']:
            return nzbGetRPC.editqueue(cmd, 0, "", id_array), ''
        elif cmd == 'listgroups':
            return nzbGetRPC.listgroups(), ''
        else:
            res = 'Unsupported nzbget command %s' % repr(cmd)
            logger.debug(res)
            return False, res

    nzbcontent64 = None
    if nzb.resultType == "nzbdata":
        data = nzb.extraInfo[0]
        nzbcontent64 = standard_b64encode(data)

    logger.info("Sending NZB to NZBget")
    logger.debug("URL: " + url)

    dupekey = ""
    dupescore = 0

    try:
        # Find out if nzbget supports priority (Version 9.0+), old versions
        # beginning with a 0.x will use the old command
        nzbget_version_str = nzbGetRPC.version()
        nzbget_version = int(nzbget_version_str[:nzbget_version_str.find(".")])
        logger.debug("NZB Version %s" % nzbget_version)
        # for some reason 14 seems to not work with >= 13 method? I get invalid param autoAdd
        # PAB think its fixed now, code had autoAdd param as "False", it's not a string, it's bool so False
        if nzbget_version == 0:  # or nzbget_version == 14:
            if nzbcontent64:
                nzbget_result = nzbGetRPC.append(nzb.name + ".nzb",
                                                 lazylibrarian.CONFIG['NZBGET_CATEGORY'], addToTop, nzbcontent64)
            else:
                # from lazylibrarian.common.providers.generic import GenericProvider
                # if nzb.resultType == "nzb":
                #     genProvider = GenericProvider("")
                #     data = genProvider.getURL(nzb.url)
                #     if (data is None):
                #         return False
                #     nzbcontent64 = standard_b64encode(data)
                # nzbget_result = nzbGetRPC.append(nzb.name + ".nzb", lazylibrarian.CONFIG['NZBGET_CATEGORY'],
                #       addToTop, nzbcontent64)
                return False, "No nzbcontent64 found"
        elif nzbget_version == 12:
            if nzbcontent64:
                nzbget_result = nzbGetRPC.append(nzb.name + ".nzb", lazylibrarian.CONFIG['NZBGET_CATEGORY'],
                                                 lazylibrarian.CONFIG['NZBGET_PRIORITY'], False,
                                                 nzbcontent64, False, dupekey, dupescore, "score")
            else:
                nzbget_result = nzbGetRPC.appendurl(nzb.name + ".nzb", lazylibrarian.CONFIG['NZBGET_CATEGORY'],
                                                    lazylibrarian.CONFIG['NZBGET_PRIORITY'], False, nzb.url, False,
                                                    dupekey, dupescore, "score")
        # v13+ has a new combined append method that accepts both (url and content)
        # also the return value has changed from boolean to integer
        # (Positive number representing NZBID of the queue item. 0 and negative numbers represent error codes.)
        elif nzbget_version >= 13:
            nzbget_result = nzbGetRPC.append(nzb.name + ".nzb", nzbcontent64 if nzbcontent64 is not None else nzb.url,
                                             lazylibrarian.CONFIG['NZBGET_CATEGORY'],
                                             lazylibrarian.CONFIG['NZBGET_PRIORITY'], False, False, dupekey, dupescore,
                                             "score")
            if nzbget_result <= 0:
                nzbget_result = False
        else:
            if nzbcontent64:
                nzbget_result = nzbGetRPC.append(nzb.name + ".nzb", lazylibrarian.CONFIG['NZBGET_CATEGORY'],
                                                 lazylibrarian.CONFIG['NZBGET_PRIORITY'], False, nzbcontent64)
            else:
                nzbget_result = nzbGetRPC.appendurl(nzb.name + ".nzb", lazylibrarian.CONFIG['NZBGET_CATEGORY'],
                                                    lazylibrarian.CONFIG['NZBGET_PRIORITY'], False, nzb.url)

        if nzbget_result:
            logger.debug("NZB sent to NZBget successfully")
            return nzbget_result, ''
        else:
            res = "NZBget could not add %s to the queue" % (nzb.name + ".nzb")
            logger.error(res)
            return False, res
    except Exception as e:
        res = "Connect Error to NZBget: could not add %s to the queue: %s %s" % (nzb.name + ".nzb",
                                                                                 type(e).__name__, str(e))
        logger.error(res)
        return False, res
