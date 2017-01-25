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

import os
import platform
import shutil
import subprocess
import threading
import time
import traceback
from urllib import FancyURLopener

import lazylibrarian
from lazylibrarian import database, logger, utorrent, transmission, qbittorrent, \
    deluge, rtorrent, synology, sabnzbd, nzbget
from lazylibrarian.common import scheduleJob, book_file, opf_file, setperm, bts_file
from lazylibrarian.formatter import plural, now, today, is_valid_booktype, unaccented_str, replace_all, unaccented
from lazylibrarian.gr import GoodReads
from lazylibrarian.importer import addAuthorToDB
from lazylibrarian.librarysync import get_book_info, find_book_in_db, LibraryScan
from lazylibrarian.magazinescan import create_id, create_cover
from lazylibrarian.notifiers import notify_download
from lib.deluge_client import DelugeRPCClient
from lib.fuzzywuzzy import fuzz


def processAlternate(source_dir=None):
    # import a book from an alternate directory
    try:
        if not source_dir or not os.path.isdir(source_dir):
            logger.warn("Alternate Directory not configured")
            return False
        if source_dir == lazylibrarian.DIRECTORY('Destination'):
            logger.warn('Alternate directory must not be the same as Destination')
            return False

        logger.debug('Processing alternate directory %s' % source_dir)
        # first, recursively process any books in subdirectories
        # ensure directory is unicode so we get unicode results from listdir
        if isinstance(source_dir, str):
            source_dir = source_dir.decode(lazylibrarian.SYS_ENCODING)
        for fname in os.listdir(source_dir):
            subdir = os.path.join(source_dir, fname)
            if os.path.isdir(subdir):
                processAlternate(subdir)
        # only import one book from each alternate (sub)directory, this is because
        # the importer may delete the directory after importing a book,
        # depending on lazylibrarian.DESTINATION_COPY setting
        # also if multiple books in a folder and only a "metadata.opf"
        # which book is it for?
        new_book = book_file(source_dir, booktype='book')
        if new_book:
            metadata = {}
            # see if there is a metadata file in this folder with the info we need
            # try book_name.opf first, or fall back to any filename.opf
            metafile = os.path.splitext(new_book)[0] + '.opf'
            if not os.path.isfile(metafile):
                metafile = opf_file(source_dir)
            if metafile and os.path.isfile(metafile):
                try:
                    metadata = get_book_info(metafile)
                except Exception as e:
                    logger.debug('Failed to read metadata from %s, %s' % (metafile, str(e)))
            else:
                logger.debug('No metadata file found for %s' % new_book)
            if 'title' not in metadata or 'creator' not in metadata:
                # if not got both, try to get metadata from the book file
                try:
                    metadata = get_book_info(new_book)
                except Exception as e:
                    logger.debug('No metadata found in %s, %s' % (new_book, str(e)))
            if 'title' in metadata and 'creator' in metadata:
                authorname = metadata['creator']
                bookname = metadata['title']
                myDB = database.DBConnection()

                authmatch = myDB.match('SELECT * FROM authors where AuthorName="%s"' % authorname)

                if not authmatch:
                    # try goodreads preferred authorname
                    logger.debug("Checking GoodReads for [%s]" % authorname)
                    GR = GoodReads(authorname)
                    try:
                        author_gr = GR.find_author_id()
                    except Exception:
                        author_gr = {}
                        logger.debug("No author id for [%s]" % authorname)
                    if author_gr:
                        grauthorname = author_gr['authorname']
                        logger.debug("GoodReads reports [%s] for [%s]" % (grauthorname, authorname))
                        authorname = grauthorname
                        authmatch = myDB.match('SELECT * FROM authors where AuthorName="%s"' % authorname)

                if authmatch:
                    logger.debug("ALT: Author %s found in database" % authorname)
                else:
                    logger.debug("ALT: Author %s not found, adding to database" % authorname)
                    addAuthorToDB(authorname)

                bookid = find_book_in_db(myDB, authorname, bookname)
                if bookid:
                    return import_book(source_dir, bookid)
                else:
                    logger.warn("Book %s by %s not found in database" % (bookname, authorname))
            else:
                logger.warn('Book %s has no metadata, unable to import' % new_book)
        else:
            logger.warn("No book file found in %s" % source_dir)
        return False
    except Exception:
        logger.error('Unhandled exception in processAlternate: %s' % traceback.format_exc())


def try_rename(directory, filename):
    # Shouldn't really need to do this, there must be a better way...
    # When we call listdir with unicode it returns unicode when it can,
    # or 8bit ascii str if it can't convert the filename to unicode
    # eg 'Stephen Hawking - A Brief History of Time (PDF&EPUB&MOB\xc4\xb0)\xb0\x06'
    # Return the new filename or empty string if failed
    if isinstance(filename, str):
        try:
            # try decode first in case we called listdir with str instead of unicode
            filename = filename.decode(lazylibrarian.SYS_ENCODING)
            return filename
        except Exception:
            logger.error("Unable to convert %s to sys encoding" % repr(filename))

    # strip out any non-ascii characters and try to rename
    newfname = ''.join([c for c in filename if 128 > ord(c) > 31])
    try:
        os.rename(os.path.join(directory, filename), os.path.join(directory, newfname))
        return newfname
    except Exception:
        logger.error("Unable to rename %s" % repr(filename))
        return ""


def move_into_subdir(processpath, targetdir, fname):
    # move the book and any related files too, other book formats, or opf, jpg with same title
    # (files begin with fname) from processpath to new targetdir
    # can't move metadata.opf or cover.jpg or similar as can't be sure they are ours
    list_dir = os.listdir(processpath)
    for ourfile in list_dir:
        if isinstance(ourfile, str):
            if int(lazylibrarian.LOGLEVEL) > 2:
                logger.warn("unexpected unicode conversion moving file into subdir")
            ourfile = try_rename(processpath, ourfile)
            if not ourfile:
                ourfile = "failed rename"
        if int(lazylibrarian.LOGLEVEL) > 2:
            logger.debug("Checking %s for %s" % (ourfile, fname))
        if ourfile.startswith(fname):
            if is_valid_booktype(ourfile, booktype="book") \
                    or is_valid_booktype(ourfile, booktype="mag") \
                    or os.path.splitext(ourfile)[1].lower() in ['.opf', '.jpg']:
                try:
                    if lazylibrarian.DESTINATION_COPY:
                        shutil.copyfile(os.path.join(processpath, ourfile), os.path.join(targetdir, ourfile))
                        setperm(os.path.join(targetdir, ourfile))
                    else:
                        shutil.move(os.path.join(processpath, ourfile), os.path.join(targetdir, ourfile))
                        setperm(os.path.join(targetdir, ourfile))
                except Exception as why:
                    logger.debug("Failed to copy/move file %s to %s, %s" % (ourfile, targetdir, str(why)))


def cron_processDir():
    threading.currentThread().name = "CRON-POSTPROCESS"
    processDir()


def processDir(reset=False):
    try:
        threadname = threading.currentThread().name
        if "Thread-" in threadname:
            threading.currentThread().name = "POSTPROCESS"

        processpath = lazylibrarian.DIRECTORY('Download')
        ppcount = 0
        # processpath is set to unicode so we get unicode results from listdir
        try:
            downloads = os.listdir(processpath)
        except OSError as why:
            logger.error('Could not access directory [%s] %s' % (processpath, why.strerror))
            return

        logger.debug('Checking %s file%s in %s' % (len(downloads), plural(len(downloads)), processpath))

        myDB = database.DBConnection()
        snatched = myDB.select('SELECT * from wanted WHERE Status="Snatched"')
        logger.debug('There are %s file%s marked "Snatched"' % (len(snatched), plural(len(snatched))))

        skipped_extensions = ['.fail', '.part', '.bts', '.!ut', '.torrent', '.magnet', '.nzb']

        if len(snatched) > 0 and len(downloads) > 0:
            for book in snatched:
                # if torrent, see if we can get current status from the downloader as the name
                # may have been changed once magnet resolved, or download started or completed
                # depending on torrent downloader. Usenet doesn't change the name. We like usenet.
                torrentname = ''
                try:
                    logger.debug("%s was sent to %s" % (book['NZBtitle'], book['Source']))
                    if book['Source'] == 'TRANSMISSION':
                        torrentname = transmission.getTorrentFolder(book['DownloadID'])
                    elif book['Source'] == 'UTORRENT':
                        torrentname = utorrent.nameTorrent(book['DownloadID'])
                    elif book['Source'] == 'RTORRENT':
                        torrentname = rtorrent.getName(book['DownloadID'])
                    elif book['Source'] == 'QBITTORRENT':
                        torrentname = qbittorrent.getName(book['DownloadID'])
                    elif book['Source'] == 'SYNOLOGY_TOR':
                        torrentname = synology.getName(book['DownloadID'])
                    elif book['Source'] == 'DELUGEWEBUI':
                        torrentname = deluge.getTorrentFolder(book['DownloadID'])
                    elif book['Source'] == 'DELUGERPC':
                        client = DelugeRPCClient(lazylibrarian.DELUGE_HOST,
                                                 int(lazylibrarian.DELUGE_PORT),
                                                 lazylibrarian.DELUGE_USER,
                                                 lazylibrarian.DELUGE_PASS)
                        try:
                            client.connect()
                            result = client.call('core.get_torrent_status', book['DownloadID'], {})
                            #    for item in result:
                            #        logger.debug ('Deluge RPC result %s: %s' % (item, result[item]))
                            if 'name' in result:
                                torrentname = unaccented_str(result['name'])
                        except Exception as e:
                            logger.debug('DelugeRPC failed %s' % str(e))
                except Exception as e:
                    logger.debug("Failed to get updated torrent name from %s for %s: %s" %
                                 (book['Source'], book['DownloadID'], str(e)))

                matchtitle = unaccented_str(book['NZBtitle'])
                if torrentname and torrentname != matchtitle:
                    logger.debug("%s Changing [%s] to [%s]" % (book['Source'], matchtitle, torrentname))
                    myDB.action('UPDATE wanted SET NZBtitle = "%s" WHERE NZBurl = "%s"' %
                                (torrentname, book['NZBurl']))
                    matchtitle = torrentname

                # here we could also check percentage downloaded or eta or status?
                # If downloader says it hasn't completed, no need to look for it.

                matches = []
                logger.info('Looking for %s in %s' % (matchtitle, processpath))
                for fname in downloads:
                    if isinstance(fname, str):
                        if int(lazylibrarian.LOGLEVEL) > 2:
                            logger.warn("unexpected unicode conversion in downloads")
                        fname = try_rename(processpath, fname)
                    if not fname:
                        fname = "failed rename"
                    # skip if failed before or incomplete torrents, or incomplete btsync etc
                    if int(lazylibrarian.LOGLEVEL) > 2:
                        logger.debug("Checking extn on %s" % fname)
                    extn = os.path.splitext(fname)[1]
                    if not extn or extn not in skipped_extensions:
                        # This is to get round differences in torrent filenames.
                        # Usenet is ok, but Torrents aren't always returned with the name we searched for
                        # We ask the torrent downloader for the torrent name, but don't always get an answer
                        # so we try to do a "best match" on the name, there might be a better way...

                        matchname = fname
                        if ' LL.(' in matchname:
                            matchname = matchname.split(' LL.(')[0]

                        if ' LL.(' in matchtitle:
                            matchtitle = matchtitle.split(' LL.(')[0]
                        match = fuzz.token_set_ratio(matchtitle, matchname)
                        if int(lazylibrarian.LOGLEVEL) > 2:
                            logger.debug("%s%% match %s : %s" % (match, matchtitle, matchname))
                        if match >= lazylibrarian.DLOAD_RATIO:
                            pp_path = os.path.join(processpath, fname)
                            if isinstance(pp_path, str):
                                try:
                                    pp_path = pp_path.decode(lazylibrarian.SYS_ENCODING)
                                except:
                                    logger.error("Unable to convert %s to sys encoding" % repr(pp_path))
                                    pp_path = "Failed pp_path"

                            if os.path.isfile(pp_path):
                                # handle single file downloads here. Book/mag file in download root.
                                # move the file into it's own subdirectory so we don't move/delete
                                # things that aren't ours
                                if int(lazylibrarian.LOGLEVEL) > 2:
                                    logger.debug('%s is a file' % fname)
                                if is_valid_booktype(fname, booktype="book") \
                                        or is_valid_booktype(fname, booktype="mag"):
                                    if int(lazylibrarian.LOGLEVEL) > 2:
                                        logger.debug('file [%s] is a valid book/mag' % fname)
                                    if bts_file(processpath):
                                        logger.debug("Skipping %s, found a .bts file" % processpath)
                                    else:
                                        fname = os.path.splitext(fname)[0]
                                        targetdir = os.path.join(processpath, fname)
                                        if not os.path.exists(targetdir):
                                            try:
                                                os.makedirs(targetdir)
                                                setperm(targetdir)
                                            except OSError as why:
                                                logger.debug('Failed to create directory %s, %s' %
                                                             (targetdir, why.strerror))
                                        if not os.path.exists(targetdir):
                                            logger.debug('Unable to find directory %s' % targetdir)
                                        else:
                                            move_into_subdir(processpath, targetdir, fname)
                                            pp_path = targetdir

                            if os.path.isdir(pp_path):
                                logger.debug('Found folder (%s%%) %s for %s' % (match, pp_path, matchtitle))
                                if not os.listdir(pp_path):
                                    logger.debug("Skipping %s, folder is empty" % pp_path)
                                elif bts_file(pp_path):
                                    logger.debug("Skipping %s, found a .bts file" % pp_path)
                                else:
                                    matches.append([match, pp_path, book])
                            else:
                                logger.debug('%s is not a directory?' % pp_path)
                        else:
                            pp_path = os.path.join(processpath, fname)
                            matches.append([match, pp_path, book])  # so we can report closest match
                    else:
                        logger.debug('Skipping %s' % fname)

                match = 0
                if matches:
                    highest = max(matches, key=lambda x: x[0])
                    match = highest[0]
                    pp_path = highest[1]
                    book = highest[2]
                if match and match >= lazylibrarian.DLOAD_RATIO:
                    mostrecentissue = ''
                    logger.debug(u'Found match (%s%%): %s for %s' % (match, pp_path, book['NZBtitle']))
                    data = myDB.match('SELECT * from books WHERE BookID="%s"' % book['BookID'])
                    if data:  # it's a book
                        logger.debug(u'Processing book %s' % book['BookID'])
                        authorname = data['AuthorName']
                        authorname = ' '.join(authorname.split())  # ensure no extra whitespace
                        bookname = data['BookName']
                        if 'windows' in platform.system().lower() and '/' in lazylibrarian.EBOOK_DEST_FOLDER:
                            logger.warn('Please check your EBOOK_DEST_FOLDER setting')
                            lazylibrarian.EBOOK_DEST_FOLDER = lazylibrarian.EBOOK_DEST_FOLDER.replace('/', '\\')
                        # Default destination path, should be allowed change per config file.
                        dest_path = lazylibrarian.EBOOK_DEST_FOLDER.replace('$Author', authorname).replace(
                            '$Title', bookname)
                        global_name = lazylibrarian.EBOOK_DEST_FILE.replace('$Author', authorname).replace(
                            '$Title', bookname)
                        global_name = unaccented(global_name)
                        # Remove characters we don't want in the filename BEFORE adding to DESTINATION_DIR
                        # as windows drive identifiers have colon, eg c:  but no colons allowed elsewhere?
                        dic = {'<': '', '>': '', '...': '', ' & ': ' ', ' = ': ' ', '?': '', '$': 's',
                               ' + ': ' ', '"': '', ',': '', '*': '', ':': '', ';': '', '\'': ''}
                        dest_path = unaccented_str(replace_all(dest_path, dic))
                        dest_path = os.path.join(processpath, dest_path).encode(lazylibrarian.SYS_ENCODING)
                    else:
                        data = myDB.match('SELECT * from magazines WHERE Title="%s"' % book['BookID'])
                        if data:  # it's a magazine
                            logger.debug(u'Processing magazine %s' % book['BookID'])
                            # AuxInfo was added for magazine release date, normally housed in 'magazines'
                            # but if multiple files are downloading, there will be an error in post-processing
                            # trying to go to the same directory.
                            mostrecentissue = data['IssueDate']  # keep for processing issues arriving out of order
                            # Remove characters we don't want in the filename before (maybe) adding to DESTINATION_DIR
                            # as windows drive identifiers have colon, eg c:  but no colons allowed elsewhere?
                            dic = {'<': '', '>': '', '...': '', ' & ': ' ', ' = ': ' ', '?': '', '$': 's',
                                   ' + ': ' ', '"': '', ',': '', '*': '', ':': '', ';': '', '\'': ''}
                            mag_name = unaccented_str(replace_all(book['BookID'], dic))
                            # book auxinfo is a cleaned date, eg 2015-01-01
                            dest_path = lazylibrarian.MAG_DEST_FOLDER.replace(
                                '$IssueDate', book['AuxInfo']).replace('$Title', mag_name)

                            if lazylibrarian.MAG_RELATIVE:
                                if dest_path[0] not in '._':
                                    dest_path = '_' + dest_path
                                dest_path = os.path.join(processpath, dest_path).encode(
                                    lazylibrarian.SYS_ENCODING)
                            else:
                                dest_path = dest_path.encode(lazylibrarian.SYS_ENCODING)
                            authorname = None
                            bookname = None
                            global_name = lazylibrarian.MAG_DEST_FILE.replace('$IssueDate', book['AuxInfo']).replace(
                                '$Title', mag_name)
                            global_name = unaccented(global_name)
                        else:  # not recognised
                            logger.debug('Nothing in database matching "%s"' % book['BookID'])
                            continue
                else:
                    logger.debug("Snatched %s %s is not in download directory" % (book['NZBmode'], book['NZBtitle']))
                    if match:
                        logger.debug(u'Closest match (%s%%): %s' % (match, pp_path))
                        if int(lazylibrarian.LOGLEVEL) > 2:
                            for match in matches:
                                logger.debug('Match: %s%%  %s' % (match[0], match[1]))
                    continue

                if processDestination(pp_path, dest_path, authorname, bookname, global_name, book['BookID']):
                    logger.debug("Processing %s, %s" % (global_name, book['NZBurl']))
                    # update nzbs, only update the snatched ones in case multiple matches for same book/magazine issue
                    controlValueDict = {"BookID": book['BookID'], "NZBurl": book['NZBurl'], "Status": "Snatched"}
                    newValueDict = {"Status": "Processed", "NZBDate": now()}  # say when we processed it
                    myDB.upsert("wanted", newValueDict, controlValueDict)

                    if bookname:
                        # it's a book, if None it's a magazine
                        if len(lazylibrarian.IMP_CALIBREDB):
                            logger.debug('Calibre should have created the extras for us')
                        else:
                            processExtras(myDB, dest_path, global_name, data)
                    else:
                        # update mags
                        controlValueDict = {"Title": book['BookID']}
                        if mostrecentissue:
                            if mostrecentissue.isdigit() and str(book['AuxInfo']).isdigit():
                                older = int(mostrecentissue) > int(book['AuxInfo'])  # issuenumber
                            else:
                                older = mostrecentissue > book['AuxInfo']  # YYYY-MM-DD
                        else:
                            older = False
                        # dest_path is where we put the magazine after processing, but we don't have the full filename
                        # so look for any "book" in that directory
                        dest_file = book_file(dest_path, booktype='mag')
                        if older:  # check this in case processing issues arriving out of order
                            newValueDict = {"LastAcquired": today(), "IssueStatus": "Open"}
                        else:
                            newValueDict = {"IssueDate": book['AuxInfo'], "LastAcquired": today(),
                                            "LatestCover": os.path.splitext(dest_file)[0] + '.jpg',
                                            "IssueStatus": "Open"}
                        myDB.upsert("magazines", newValueDict, controlValueDict)
                        controlValueDict = {"Title": book['BookID'], "IssueDate": book['AuxInfo']}
                        newValueDict = {"IssueAcquired": today(),
                                        "IssueFile": dest_file,
                                        "IssueID": create_id("%s %s" % (book['BookID'], book['AuxInfo']))
                                        }
                        myDB.upsert("issues", newValueDict, controlValueDict)

                        # create a thumbnail cover for the new issue
                        create_cover(dest_file)

                    # calibre or ll copied/moved the files we want, now delete source files

                    to_delete = True
                    if book['NZBmode'] in ['torrent', 'magnet']:
                        # Only delete torrents if we don't want to keep seeding
                        if lazylibrarian.KEEP_SEEDING:
                            logger.warn('%s is seeding %s %s' % (book['Source'], book['NZBmode'], book['NZBtitle']))
                            to_delete = False
                        else:
                            # ask downloader to delete the torrent, but not the files
                            # we may delete them later, depending on other settings
                            if book['DownloadID'] != "unknown":
                                logger.debug('Removing %s from %s' % (book['NZBtitle'], book['Source'].lower()))
                                delete_task(book['Source'], book['DownloadID'], False)
                            else:
                                logger.warn("Unable to remove %s from %s, no DownloadID" %
                                            (book['NZBtitle'], book['Source'].lower()))

                    if to_delete:
                        # only delete the files if not in download root dir and if DESTINATION_COPY not set
                        if not lazylibrarian.DESTINATION_COPY and (pp_path != processpath):
                            if os.path.isdir(pp_path):
                                # calibre might have already deleted it?
                                try:
                                    shutil.rmtree(pp_path)
                                except Exception as why:
                                    logger.debug("Unable to remove %s, %s" % (pp_path, str(why)))

                    logger.info('Successfully processed: %s' % global_name)
                    ppcount += 1
                    notify_download("%s from %s at %s" % (global_name, book['NZBprov'], now()))
                else:
                    logger.error('Postprocessing for %s has failed.' % global_name)
                    logger.error('Warning - Residual files remain in %s.fail' % pp_path)
                    controlValueDict = {"NZBurl": book['NZBurl'], "Status": "Snatched"}
                    newValueDict = {"Status": "Failed", "NZBDate": now()}
                    myDB.upsert("wanted", newValueDict, controlValueDict)
                    # if it's a book, reset status so we try for a different version
                    # if it's a magazine, user can select a different one from pastissues table
                    if bookname:
                        myDB.action('UPDATE books SET status = "Wanted" WHERE BookID="%s"' % book['BookID'])

                    # at this point, as it failed we should move it or it will get postprocessed
                    # again (and fail again)
                    try:
                        os.rename(pp_path, pp_path + '.fail')
                    except Exception as e:
                        logger.debug("Unable to rename %s, %s" % (pp_path, str(e)))

        # Check for any books in download that weren't marked as snatched, but have a LL.(bookid)
        # do a fresh listdir in case we processed and deleted any earlier
        downloads = os.listdir(processpath)
        if int(lazylibrarian.LOGLEVEL) > 2:
            logger.debug("Scanning %s entries in %s for LL.(num)" % (len(downloads), processpath))
        for entry in downloads:
            if isinstance(entry, str):
                if int(lazylibrarian.LOGLEVEL) > 2:
                    logger.warn("unexpected unicode conversion in LL scanner")
                entry = try_rename(processpath, entry)
                if not entry:
                    entry = "failed rename"
            dname, extn = os.path.splitext(entry)
            if "LL.(" in entry:
                if not extn or extn not in skipped_extensions:
                    bookID = entry.split("LL.(")[1].split(")")[0]
                    logger.debug("Book with id: %s found in download directory" % bookID)
                    pp_path = os.path.join(processpath, entry)

                    if os.path.isfile(pp_path):
                        if int(lazylibrarian.LOGLEVEL) > 2:
                            logger.debug("%s is a file" % pp_path)
                        pp_path = os.path.join(processpath)

                    if os.path.isdir(pp_path):
                        if int(lazylibrarian.LOGLEVEL) > 2:
                            logger.debug("%s is a dir" % pp_path)
                        if import_book(pp_path, bookID):
                            if int(lazylibrarian.LOGLEVEL) > 2:
                                logger.debug("Imported %s" % pp_path)
                            ppcount += 1
                else:
                    if int(lazylibrarian.LOGLEVEL) > 2:
                        logger.debug("Skipping extn %s" % entry)
            else:
                if int(lazylibrarian.LOGLEVEL) > 2:
                    logger.debug("Skipping (not LL) %s" % entry)

        if ppcount == 0:
            logger.info('No snatched books/mags have been found')
        else:
            logger.info('%s book%s/mag%s processed.' % (ppcount, plural(ppcount), plural(ppcount)))

        # Now check for any that are still marked snatched...
        snatched = myDB.select('SELECT * from wanted WHERE Status="Snatched"')
        if lazylibrarian.TASK_AGE and len(snatched) > 0:
            for snatch in snatched:
                # FUTURE: we could check percentage downloaded or eta?
                # if percentage is increasing, it's just slow
                try:
                    when_snatched = time.strptime(snatch['NZBdate'], '%Y-%m-%d %H:%M:%S')
                    when_snatched = time.mktime(when_snatched)
                    diff = time.time() - when_snatched  # time difference in seconds
                except:
                    diff = 0
                hours = int(diff / 3600)
                if hours >= lazylibrarian.TASK_AGE:
                    logger.warn('%s was sent to %s %s hours ago, deleting failed task' %
                                (snatch['NZBtitle'], snatch['Source'].lower(), hours))
                    # change status to "Failed", and ask downloader to delete task and files
                    if snatch['BookID'] != 'unknown':
                        myDB.action('UPDATE wanted SET Status="Failed" WHERE BookID="%s"' % snatch['BookID'])
                        myDB.action('UPDATE books SET status = "Wanted" WHERE BookID="%s"' % snatch['BookID'])
                        delete_task(snatch['Source'], snatch['DownloadID'], True)

        # Check if postprocessor needs to run again
        snatched = myDB.select('SELECT * from wanted WHERE Status="Snatched"')
        if len(snatched) == 0:
            logger.info('Nothing marked as snatched.')
            scheduleJob(action='Stop', target='processDir')
            return

        if reset:
            scheduleJob(action='Restart', target='processDir')

    except Exception:
        logger.error('Unhandled exception in processDir: %s' % traceback.format_exc())


def delete_task(Source, DownloadID, remove_data):
    try:
        if Source == "BLACKHOLE":
            logger.warn("Download %s has not been processed from blackhole" % DownloadID)
        elif Source == "SABNZBD":
            sabnzbd.SABnzbd(DownloadID, 'delete', remove_data)
        elif Source == "NZBGET":
            nzbget.deleteNZB(DownloadID, remove_data)
        elif Source == "UTORRENT":
            utorrent.removeTorrent(DownloadID, remove_data)
        elif Source == "RTORRENT":
            rtorrent.removeTorrent(DownloadID, remove_data)
        elif Source == "QBITTORRENT":
            qbittorrent.removeTorrent(DownloadID, remove_data)
        elif Source == "TRANSMISSION":
            transmission.removeTorrent(DownloadID, remove_data)
        elif Source == "SYNOLOGY_TOR" or Source == "SYNOLOGY_NZB":
            synology.removeTorrent(DownloadID, remove_data)
        elif Source == "DELUGEWEBUI":
            deluge.removeTorrent(DownloadID, remove_data)
        elif Source == "DELUGERPC":
            client = DelugeRPCClient(lazylibrarian.DELUGE_HOST,
                                     int(lazylibrarian.DELUGE_PORT),
                                     lazylibrarian.DELUGE_USER,
                                     lazylibrarian.DELUGE_PASS)
            try:
                client.connect()
                client.call('core.remove_torrent', DownloadID, remove_data)
            except Exception as e:
                logger.debug('DelugeRPC failed %s' % str(e))
                return False
        else:
            logger.debug("Unknown source [%s] in delete_task" % Source)
            return False
        return True

    except Exception as e:
        logger.debug("Failed to delete task %s from %s: %s" % (DownloadID, Source, str(e)))
        return False


def import_book(pp_path=None, bookID=None):
    try:
        # Move a book into LL folder structure given just the folder and bookID, returns True or False
        # Called from "import_alternate" or if we find a "LL.(xxx)" folder that doesn't match a snatched book/mag
        #
        myDB = database.DBConnection()
        data = myDB.match('SELECT * from books WHERE BookID="%s"' % bookID)
        if data:
            authorname = data['AuthorName']
            authorname = ' '.join(authorname.split())  # ensure no extra whitespace
            bookname = data['BookName']
            processpath = lazylibrarian.DIRECTORY('Destination')

            if 'windows' in platform.system().lower() and '/' in lazylibrarian.EBOOK_DEST_FOLDER:
                logger.warn('Please check your EBOOK_DEST_FOLDER setting')
                lazylibrarian.EBOOK_DEST_FOLDER = lazylibrarian.EBOOK_DEST_FOLDER.replace('/', '\\')

            dest_path = lazylibrarian.EBOOK_DEST_FOLDER.replace('$Author', authorname).replace('$Title', bookname)
            global_name = lazylibrarian.EBOOK_DEST_FILE.replace('$Author', authorname).replace('$Title', bookname)
            global_name = unaccented(global_name)
            # Remove characters we don't want in the filename BEFORE adding to DESTINATION_DIR
            # as windows drive identifiers have colon, eg c:  but no colons allowed elsewhere?
            dic = {'<': '', '>': '', '...': '', ' & ': ' ', ' = ': ' ', '?': '', '$': 's',
                   ' + ': ' ', '"': '', ',': '', '*': '', ':': '', ';': '', '\'': ''}
            dest_path = unaccented_str(replace_all(dest_path, dic))
            dest_path = os.path.join(processpath, dest_path).encode(lazylibrarian.SYS_ENCODING)

            if processDestination(pp_path, dest_path, authorname, bookname, global_name, bookID):
                # update nzbs
                was_snatched = myDB.match('SELECT BookID, NZBprov FROM wanted WHERE BookID="%s"' % bookID)
                snatched_from = "from " + was_snatched['NZBprov'] if was_snatched else "manually added"
                if was_snatched:
                    controlValueDict = {"BookID": bookID}
                    newValueDict = {"Status": "Processed", "NZBDate": now()}  # say when we processed it
                    myDB.upsert("wanted", newValueDict, controlValueDict)
                    if bookname:
                        if len(lazylibrarian.IMP_CALIBREDB):
                            logger.debug('Calibre should have created the extras')
                        else:
                            processExtras(myDB, dest_path, global_name, data)

                    if not lazylibrarian.DESTINATION_COPY and pp_path != processpath:
                        if os.path.isdir(pp_path):
                            # calibre might have already deleted it?
                            try:
                                shutil.rmtree(pp_path)
                            except Exception as why:
                                logger.debug("Unable to remove %s, %s" % (pp_path, str(why)))

                logger.info('Successfully processed: %s' % global_name)
                notify_download("%s %s at %s" % (global_name, snatched_from, now()))
                return True
            else:
                logger.error('Postprocessing for %s has failed.' % global_name)
                logger.error('Warning - Residual files remain in %s.fail' % pp_path)
                was_snatched = myDB.match('SELECT BookID FROM wanted WHERE BookID="%s"' % bookID)
                if was_snatched:
                    controlValueDict = {"BookID": bookID}
                    newValueDict = {"Status": "Failed", "NZBDate": now()}
                    myDB.upsert("wanted", newValueDict, controlValueDict)
                # reset status so we try for a different version
                myDB.action('UPDATE books SET status = "Wanted" WHERE BookID="%s"' % bookID)
                try:
                    os.rename(pp_path, pp_path + '.fail')
                except Exception as e:
                    logger.debug("Unable to rename %s, %s" % (pp_path, str(e)))
        return False
    except Exception:
        logger.error('Unhandled exception in importBook: %s' % traceback.format_exc())


def processExtras(myDB=None, dest_path=None, global_name=None, data=None):
    # given book data, handle calibre autoadd, book image, opf,
    # and update author and book counts
    authorname = data['AuthorName']
    bookid = data['BookID']
    bookname = data['BookName']
    bookdesc = data['BookDesc']
    bookisbn = data['BookIsbn']
    bookimg = data['BookImg']
    bookdate = data['BookDate']
    booklang = data['BookLang']
    bookpub = data['BookPub']

    # If you use auto add by Calibre you need the book in a single directory, not nested
    # So take the file you Copied/Moved to Dest_path and copy it to a Calibre auto add folder.
    if lazylibrarian.IMP_AUTOADD:
        processAutoAdd(dest_path)

    # try image
    processIMG(dest_path, bookimg, global_name)

    # try metadata
    processOPF(dest_path, authorname, bookname, bookisbn, bookid, bookpub, bookdate, bookdesc, booklang, global_name)

    # update books
    # dest_path is where we put the book after processing, but we don't have the full filename
    # we don't keep the extension, so look for any "book" in that directory
    dest_file = book_file(dest_path, booktype='book')
    if isinstance(dest_file, str):
        dest_file = dest_file.decode(lazylibrarian.SYS_ENCODING)
    controlValueDict = {"BookID": bookid}
    newValueDict = {"Status": "Open", "BookFile": dest_file}
    myDB.upsert("books", newValueDict, controlValueDict)

    # update authors
    havebooks = myDB.match(
        'SELECT count("BookID") as counter FROM books WHERE AuthorName="%s" AND (Status="Have" OR Status="Open")' %
        authorname)
    controlValueDict = {"AuthorName": authorname}
    newValueDict = {"HaveBooks": havebooks['counter']}
    countauthor = len(myDB.select('SELECT AuthorID FROM authors WHERE AuthorName="%s"' % authorname))
    if countauthor:
        myDB.upsert("authors", newValueDict, controlValueDict)


def processDestination(pp_path=None, dest_path=None, authorname=None, bookname=None, global_name=None, bookid=None):
    # check we got a book/magazine in the downloaded files, if not, return
    if bookname:
        booktype = 'book'
    else:
        booktype = 'mag'

    # ensure directory is unicode so we get unicode results from listdir
    if isinstance(pp_path, str):
        pp_path = pp_path.decode(lazylibrarian.SYS_ENCODING)

    got_book = False
    for bookfile in os.listdir(pp_path):
        if is_valid_booktype(bookfile, booktype=booktype):
            got_book = bookfile
            break

    if got_book is False:
        # no book/mag found in a format we wanted. Leave for the user to delete or convert manually
        logger.warn('Failed to locate a book/magazine in %s, leaving for manual processing' % pp_path)
        return False

    # Do we want calibre to import the book for us
    if bookname and len(lazylibrarian.IMP_CALIBREDB):
        processpath = lazylibrarian.DIRECTORY('Destination')
        params = []
        try:
            logger.debug('Importing %s into calibre library' % global_name)
            # calibre ignores metadata.opf and book_name.opf
            for bookfile in os.listdir(pp_path):
                filename, extn = os.path.splitext(bookfile)
                # calibre does not like quotes in author names
                os.rename(os.path.join(pp_path, filename + extn), os.path.join(
                    pp_path, global_name.replace('"', '_') + extn))

            if bookid.isdigit():
                identifier = "goodreads:%s" % bookid
            else:
                identifier = "google:%s" % bookid

            params = [lazylibrarian.IMP_CALIBREDB,
                      'add',
                      '-1',
                      '--with-library=%s' % processpath,
                      pp_path
                      ]
            logger.debug(str(params))
            res = subprocess.check_output(params, stderr=subprocess.STDOUT)
            if res:
                logger.debug('%s reports: %s' % (lazylibrarian.IMP_CALIBREDB, unaccented_str(res)))
                if 'already exist' in res:
                    logger.warn('Calibre failed to import %s %s, reports book already exists' % (authorname, bookname))
                if 'Added book ids' in res:
                    calibre_id = res.split("book ids: ", 1)[1].split("\n", 1)[0]
                    logger.debug('Calibre ID: %s' % calibre_id)
                    authorparams = [lazylibrarian.IMP_CALIBREDB,
                                    'set_metadata',
                                    '--field',
                                    'authors:%s' % unaccented(authorname),
                                    '--with-library',
                                    processpath,
                                    calibre_id
                                    ]
                    logger.debug(str(authorparams))
                    res = subprocess.check_output(authorparams, stderr=subprocess.STDOUT)
                    if res:
                        logger.debug('%s author reports: %s' % (lazylibrarian.IMP_CALIBREDB, unaccented_str(res)))

                    titleparams = [lazylibrarian.IMP_CALIBREDB,
                                   'set_metadata',
                                   '--field',
                                   'title:%s' % unaccented(bookname),
                                   '--with-library',
                                   processpath,
                                   calibre_id
                                   ]
                    logger.debug(str(titleparams))
                    res = subprocess.check_output(titleparams, stderr=subprocess.STDOUT)
                    if res:
                        logger.debug('%s book reports: %s' % (lazylibrarian.IMP_CALIBREDB, unaccented_str(res)))

                    metaparams = [lazylibrarian.IMP_CALIBREDB,
                                  'set_metadata',
                                  '--field',
                                  'identifiers:%s' % identifier,
                                  '--with-library',
                                  processpath,
                                  calibre_id
                                  ]
                    logger.debug(str(metaparams))
                    res = subprocess.check_output(metaparams, stderr=subprocess.STDOUT)
                    if res:
                        logger.debug('%s identifier reports: %s' % (lazylibrarian.IMP_CALIBREDB, unaccented_str(res)))

            # calibre does not like quotes in author names
            calibre_dir = os.path.join(processpath, unaccented_str(authorname.replace('"', '_')), '')
            if os.path.isdir(calibre_dir):
                imported = LibraryScan(calibre_dir)  # rescan authors directory so we get the new book in our database
            else:
                logger.error("Failed to locate calibre dir [%s]" % calibre_dir)
                imported = False
                # imported = LibraryScan(processpath)  # may have to rescan whole library instead
            if not imported:
                return False
        except subprocess.CalledProcessError as e:
            logger.debug(params)
            logger.debug('calibredb import failed: %s' % e.output)
            return False
        except OSError as e:
            logger.debug('calibredb failed, %s' % e.strerror)
            return False

    else:
        # we are copying the files ourselves, either it's a magazine or we don't want to use calibre
        if not os.path.exists(dest_path):
            logger.debug('%s does not exist, so it\'s safe to create it' % dest_path)
        elif not os.path.isdir(dest_path):
            logger.debug('%s exists but is not a directory, deleting it' % dest_path)
            try:
                os.remove(dest_path)
            except OSError as why:
                logger.debug('Failed to delete %s, %s' % (dest_path, why.strerror))
                return False

        if not os.path.exists(dest_path):
            try:
                os.makedirs(dest_path)
            except OSError as why:
                logger.debug('Failed to create directory %s, %s' % (dest_path, why.strerror))
                return False
            setperm(dest_path)

        # ok, we've got a target directory, try to copy only the files we want, renaming them on the fly.
        for fname in os.listdir(pp_path):
            if fname.lower().endswith(".jpg") or fname.lower().endswith(".opf") or \
                    is_valid_booktype(fname, booktype=booktype):
                logger.debug('Copying %s to directory %s' % (fname, dest_path))
                try:
                    shutil.copyfile(os.path.join(pp_path, fname), os.path.join(
                        dest_path, global_name + os.path.splitext(fname)[1]))
                    setperm(os.path.join(dest_path, global_name + os.path.splitext(fname)[1]))
                except Exception as why:
                    logger.debug("Failed to copy file %s to %s, %s" % (
                        fname, dest_path, str(why)))
                    return False
            else:
                logger.debug('Ignoring unwanted file: %s' % fname)
    return True


def processAutoAdd(src_path=None):
    # Called to copy the book files to an auto add directory for the likes of Calibre which can't do nested dirs
    # ensure directory is unicode so we get unicode results from listdir
    if isinstance(src_path, str):
        src_path = src_path.decode(lazylibrarian.SYS_ENCODING)
    autoadddir = lazylibrarian.IMP_AUTOADD
    logger.debug('AutoAdd - Attempt to copy from [%s] to [%s]' % (src_path, autoadddir))

    if not os.path.exists(autoadddir):
        logger.error('AutoAdd directory [%s] is missing or not set - cannot perform autoadd copy' % autoadddir)
        return False
    # Now try and copy all the book files into a single dir.
    try:
        names = os.listdir(src_path)
        # TODO : n files jpg, opf & book(s) should have same name
        # Caution - book may be pdf, mobi, epub or all 3.
        # for now simply copy all files, and let the autoadder sort it out
        #
        # Update - seems Calibre only uses the ebook, not the jpeg or opf files
        # and only imports one format of each ebook, treats the others as duplicates
        # Maybe need to rewrite this so we only copy the first ebook we find and ignore everything else
        #
        for name in names:
            srcname = os.path.join(src_path, name)
            dstname = os.path.join(autoadddir, name)
            logger.debug('AutoAdd Copying file [%s] as copy [%s] to [%s]' % (name, srcname, dstname))
            try:
                shutil.copyfile(srcname, dstname)
            except Exception as why:
                logger.error('AutoAdd - Failed to copy file [%s] because [%s] ' % (name, str(why)))
                return False
            try:
                os.chmod(dstname, 0o666)  # make rw for calibre
            except OSError as why:
                logger.warn("Could not set permission of %s because [%s]" % (dstname, why.strerror))
                # permissions might not be fatal, continue

    except OSError as why:
        logger.error('AutoAdd - Failed because [%s]' % why.strerror)
        return False

    logger.info('Auto Add completed for [%s]' % src_path)
    return True


def processIMG(dest_path=None, bookimg=None, global_name=None):
    # handle pictures
    try:
        if bookimg and bookimg.startswith('http'):
            logger.debug('Downloading cover from ' + bookimg)
            coverpath = os.path.join(dest_path, global_name + '.jpg')
            with open(coverpath, 'wb') as img:
                imggoogle = imgGoogle()
                img.write(imggoogle.open(bookimg).read())
                # try:
                #    os.chmod(coverpath, 0777)
                # except Exception, e:
                #    logger.error("Could not chmod path: " + str(coverpath))

    except (IOError, EOFError) as e:
        if hasattr(e, 'strerror'):
            errmsg = e.strerror
        else:
            errmsg = str(e)

        logger.error('Error fetching cover from url: %s, %s' % (bookimg, errmsg))


def processOPF(dest_path=None, authorname=None, bookname=None, bookisbn=None, bookid=None,
               bookpub=None, bookdate=None, bookdesc=None, booklang=None, global_name=None):
    opfinfo = '<?xml version="1.0"  encoding="UTF-8"?>\n\
<package version="2.0" xmlns="http://www.idpf.org/2007/opf" >\n\
    <metadata xmlns:dc="http://purl.org/dc/elements/1.1/" xmlns:opf="http://www.idpf.org/2007/opf">\n\
        <dc:title>%s</dc:title>\n\
        <creator>%s</creator>\n\
        <dc:language>%s</dc:language>\n\
        <dc:identifier scheme="GoogleBooks">%s</dc:identifier>\n' % (bookname, authorname, booklang, bookid)

    if bookisbn:
        opfinfo += '        <dc:identifier scheme="ISBN">%s</dc:identifier>\n' % bookisbn

    if bookpub:
        opfinfo += '        <dc:publisher>%s</dc:publisher>\n' % bookpub

    if bookdate:
        opfinfo += '        <dc:date>%s</dc:date>\n' % bookdate

    if bookdesc:
        opfinfo += '        <dc:description>%s</dc:description>\n' % bookdesc

    opfinfo += '        <guide>\n\
            <reference href="cover.jpg" type="cover" title="Cover"/>\n\
        </guide>\n\
    </metadata>\n\
</package>'

    dic = {'...': '', ' & ': ' ', ' = ': ' ', '$': 's', ' + ': ' ', ',': '', '*': ''}

    opfinfo = unaccented_str(replace_all(opfinfo, dic))

    # handle metadata
    opfpath = os.path.join(dest_path, global_name + '.opf')
    if not os.path.exists(opfpath):
        with open(opfpath, 'wb') as opf:
            opf.write(opfinfo)
        logger.debug('Saved metadata to: ' + opfpath)
    else:
        logger.debug('%s already exists. Did not create one.' % opfpath)


class imgGoogle(FancyURLopener):
    # Hack because Google wants a user agent for downloading images,
    # which is stupid because it's so easy to circumvent.
    version = 'Mozilla/5.0 (X11; U; Linux i686) Gecko/20071127 Firefox/2.0.0.11'
