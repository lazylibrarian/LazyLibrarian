#!/usr/bin/env python
"""
Created on Apr 19, 2012
@author: dan, Faless

    GNU GENERAL PUBLIC LICENSE - Version 3

    This program is free software: you can redistribute it and/or modify
    it under the terms of the GNU General Public License as published by
    the Free Software Foundation, either version 3 of the License, or
    (at your option) any later version.

    This program is distributed in the hope that it will be useful,
    but WITHOUT ANY WARRANTY; without even the implied warranty of
    MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
    GNU General Public License for more details.

    You should have received a copy of the GNU General Public License
    along with this program.  If not, see <http://www.gnu.org/licenses/>.

    http://www.gnu.org/licenses/gpl-3.0.txt

    modified by PAB for lazylibrarian...
    Added timeout to metadata download, warn about shutl.rmtree errors
    check if libtorrent available (it's architecture specific)
"""

import os.path as pt
import shutil
import tempfile
from time import sleep

import lazylibrarian
from lazylibrarian import logger


def magnet2torrent(magnet, output_name=None):
    try:
        import libtorrent as lt
    except ImportError:
        try:
            from lib.libtorrent import libtorrent as lt
        except ImportError:
            logger.error("Unable to import libtorrent, disabling magnet conversion")
            lazylibrarian.TOR_CONVERT_MAGNET = False
            return False

    if output_name and \
            not pt.isdir(output_name) and \
            not pt.isdir(pt.dirname(pt.abspath(output_name))):
        logger.debug("Invalid output folder: " + pt.dirname(pt.abspath(output_name)))
        return False

    tempdir = tempfile.mkdtemp()
    ses = lt.session()
    params = {
        'save_path': tempdir,
        'storage_mode': lt.storage_mode_t(2),
        'paused': False,
        'auto_managed': True,
        'duplicate_is_error': True
    }
    handle = lt.add_magnet_uri(ses, magnet, params)

    logger.debug("Downloading Metadata (this may take a while)")
    counter = 90
    while counter and not handle.has_metadata():
        try:
            sleep(1)
            counter -= 1
        except KeyboardInterrupt:
            counter = 0
    if not counter:
        logger.debug("magnet2Torrent Aborting...")
        ses.pause()
        logger.debug("Cleanup dir " + tempdir)
        try:
            shutil.rmtree(tempdir)
        except Exception as e:
            logger.debug("Error removing directory: %s" % str(e))
        return False
    ses.pause()

    torinfo = handle.get_torrent_info()
    torfile = lt.create_torrent(torinfo)
    torcontent = lt.bencode(torfile.generate())
    ses.remove_torrent(handle)

    output = pt.abspath(torinfo.name() + ".torrent")
    if output_name:
        if pt.isdir(output_name):
            output = pt.abspath(pt.join(
                output_name, torinfo.name() + ".torrent"))
        elif pt.isdir(pt.dirname(pt.abspath(output_name))):
            output = pt.abspath(output_name)

    logger.debug("Saving torrent file here : " + output + " ...")
    with open(output, "wb") as f:
        f.write(torcontent)
    logger.debug("Saved! Cleaning up dir: " + tempdir)
    try:
        shutil.rmtree(tempdir)
    except Exception as e:
        logger.debug("Error removing directory: %s" % str(e))
    return output
