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
import datetime
import traceback
from urllib import FancyURLopener

import lazylibrarian
from lazylibrarian import database, logger, utorrent, transmission, qbittorrent, \
    deluge, rtorrent, synology, sabnzbd, nzbget
from lazylibrarian.common import scheduleJob, book_file, opf_file, setperm, bts_file
from lazylibrarian.formatter import plural, now, today, is_valid_booktype, unaccented_str, replace_all, \
    unaccented, getList
from lazylibrarian.gr import GoodReads
from lazylibrarian.importer import addAuthorToDB, addAuthorNameToDB, update_totals
from lazylibrarian.librarysync import get_book_info, find_book_in_db, LibraryScan
from lazylibrarian.magazinescan import create_id, create_cover
from lazylibrarian.notifiers import notify_download, custom_notify_download
from lib.deluge_client import DelugeRPCClient
from lib.fuzzywuzzy import fuzz

# Need to remove characters we don't want in the filename BEFORE adding to EBOOK_DIR
# as windows drive identifiers have colon, eg c:  but no colons allowed elsewhere?
__dic__ = {'<': '', '>': '', '...': '', ' & ': ' ', ' = ': ' ', '?': '', '$': 's',
           ' + ': ' ', '"': '', ',': '', '*': '', ':': '', ';': '', '\'': ''}


def update_downloads(provider):
    myDB = database.DBConnection()
    entry = myDB.match('SELECT Count FROM downloads where Provider=?', (provider,))
    if entry:
        counter = int(entry['Count'])
        myDB.action('UPDATE downloads SET Count=? WHERE Provider=?', (counter + 1, provider))
    else:
        myDB.action('INSERT into downloads (Count, Provider) VALUES  (?, ?)', (1, provider))


def processAlternate(source_dir=None):
    # import a book from an alternate directory
    try:
        if not source_dir or not os.path.isdir(source_dir):
            logger.warn("Alternate Directory not configured")
            return False
        if source_dir == lazylibrarian.DIRECTORY('eBook'):
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
        # depending on lazylibrarian.CONFIG['DESTINATION_COPY'] setting
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
                authorid = ''
                authmatch = myDB.match('SELECT * FROM authors where AuthorName=?', (authorname,))

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
                        authorid = author_gr['authorid']
                        logger.debug("GoodReads reports [%s] for [%s]" % (grauthorname, authorname))
                        authorname = grauthorname
                        authmatch = myDB.match('SELECT * FROM authors where AuthorID=?', (authorid,))

                if authmatch:
                    logger.debug("ALT: Author %s found in database" % authorname)
                else:
                    logger.debug("ALT: Author %s not found, adding to database" % authorname)
                    if authorid:
                        addAuthorToDB(authorid=authorid)
                    else:
                        addAuthorNameToDB(author=authorname)

                bookid = find_book_in_db(authorname, bookname)
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
    if int(lazylibrarian.LOGLEVEL) > 2:
        logger.debug("try_rename %s %s %s %s" % (type(filename), repr(filename), type(directory), repr(directory)))

    if isinstance(filename, str):
        try:
            # try decode first in case we called listdir with str instead of unicode
            filename = filename.decode(lazylibrarian.SYS_ENCODING)
            return filename
        except UnicodeDecodeError:
            logger.error("Unable to convert %s to sys encoding" % repr(filename))

    # strip out any non-ascii characters and try to rename
    newfname = ''.join([c for c in filename if 128 > ord(c) > 31])
    try:
        os.rename(os.path.join(directory, filename), os.path.join(directory, newfname))
        return newfname
    except OSError:
        logger.error("Unable to rename %s" % repr(filename))
        return ""


def move_into_subdir(sourcedir, targetdir, fname, move='move'):
    # move the book and any related files too, other book formats, or opf, jpg with same title
    # (files begin with fname) from sourcedir to new targetdir
    # can't move metadata.opf or cover.jpg or similar as can't be sure they are ours
    list_dir = os.listdir(sourcedir)
    for ourfile in list_dir:
        if isinstance(ourfile, str):
            if int(lazylibrarian.LOGLEVEL) > 2:
                logger.warn("unexpected unicode conversion moving file into subdir")
            ourfile = try_rename(sourcedir, ourfile)
            if not ourfile:
                ourfile = "failed rename"
        if int(lazylibrarian.LOGLEVEL) > 2:
            logger.debug("Checking %s for %s" % (ourfile, fname))
        if ourfile.startswith(fname) or is_valid_booktype(ourfile, booktype="audiobook"):
            if is_valid_booktype(ourfile, booktype="book") \
                    or is_valid_booktype(ourfile, booktype="audiobook") \
                    or is_valid_booktype(ourfile, booktype="mag") \
                    or os.path.splitext(ourfile)[1].lower() in ['.opf', '.jpg']:
                try:
                    if lazylibrarian.CONFIG['DESTINATION_COPY'] or move == 'copy':
                        shutil.copyfile(os.path.join(sourcedir, ourfile), os.path.join(targetdir, ourfile))
                        setperm(os.path.join(targetdir, ourfile))
                    else:
                        shutil.move(os.path.join(sourcedir, ourfile), os.path.join(targetdir, ourfile))
                        setperm(os.path.join(targetdir, ourfile))
                except Exception as why:
                    logger.debug("Failed to copy/move file %s to [%s], %s" % (ourfile, targetdir, str(why)))


def cron_processDir():
    if 'POSTPROCESS' not in [n.name for n in [t for t in threading.enumerate()]]:
        processDir()


def processDir(reset=False):
    try:
        threadname = threading.currentThread().name
        if "Thread-" in threadname:
            threading.currentThread().name = "POSTPROCESS"

        download_dir = lazylibrarian.DIRECTORY('Download')
        ppcount = 0
        # download_dir is set to unicode so we get unicode results from listdir
        try:
            downloads = os.listdir(download_dir)
        except OSError as why:
            logger.error('Could not access directory [%s] %s' % (download_dir, why.strerror))
            return

        logger.debug('Checking %s file%s in %s' % (len(downloads), plural(len(downloads)), download_dir))

        myDB = database.DBConnection()
        snatched = myDB.select('SELECT * from wanted WHERE Status="Snatched"')
        logger.debug('Found %s file%s marked "Snatched"' % (len(snatched), plural(len(snatched))))

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
                        client = DelugeRPCClient(lazylibrarian.CONFIG['DELUGE_HOST'],
                                                 int(lazylibrarian.CONFIG['DELUGE_PORT']),
                                                 lazylibrarian.CONFIG['DELUGE_USER'],
                                                 lazylibrarian.CONFIG['DELUGE_PASS'])
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
                    myDB.action('UPDATE wanted SET NZBtitle=? WHERE NZBurl=?', (torrentname, book['NZBurl']))
                    matchtitle = torrentname

                # here we could also check percentage downloaded or eta or status?
                # If downloader says it hasn't completed, no need to look for it.

                matches = []

                book_type = book['AuxInfo']
                if book_type != 'AudioBook' and book_type != 'eBook':
                    if book_type is None or book_type == '':
                        book_type = 'eBook'
                    else:
                        book_type = 'Magazine'

                logger.info('Looking for %s %s in %s' % (book_type, matchtitle, download_dir))
                for fname in downloads:
                    if isinstance(fname, str):
                        if int(lazylibrarian.LOGLEVEL) > 2:
                            logger.warn("unexpected unicode conversion in downloads")
                        fname = try_rename(download_dir, fname)
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
                        # torrents might have words_separated_by_underscores
                        matchname = matchname.split(' LL.(')[0].replace('_', ' ')
                        matchtitle = matchtitle.split(' LL.(')[0].replace('_', ' ')
                        match = fuzz.token_set_ratio(matchtitle, matchname)
                        if int(lazylibrarian.LOGLEVEL) > 2:
                            logger.debug("%s%% match %s : %s" % (match, matchtitle, matchname))
                        if match >= lazylibrarian.CONFIG['DLOAD_RATIO']:
                            pp_path = os.path.join(download_dir, fname)
                            if isinstance(pp_path, str):
                                try:
                                    pp_path = pp_path.decode(lazylibrarian.SYS_ENCODING)
                                except UnicodeDecodeError:
                                    logger.error("Unable to convert %s to sys encoding" % repr(pp_path))
                                    pp_path = "Failed pp_path"

                            if int(lazylibrarian.LOGLEVEL) > 2:
                                logger.debug("processDir %s %s" % (type(pp_path), repr(pp_path)))

                            if os.path.isfile(pp_path):
                                # handle single file downloads here. Book/mag file in download root.
                                # move the file into it's own subdirectory so we don't move/delete
                                # things that aren't ours
                                if int(lazylibrarian.LOGLEVEL) > 2:
                                    logger.debug('%s is a file' % fname)
                                if is_valid_booktype(fname, booktype="book") \
                                        or is_valid_booktype(fname, booktype="audiobook") \
                                        or is_valid_booktype(fname, booktype="mag"):
                                    if int(lazylibrarian.LOGLEVEL) > 2:
                                        logger.debug('file [%s] is a valid book/mag' % fname)
                                    if bts_file(download_dir):
                                        logger.debug("Skipping %s, found a .bts file" % download_dir)
                                    else:
                                        fname = os.path.splitext(fname)[0]
                                        while fname[-1] in '. ':
                                            fname = fname[:-1]
                                        targetdir = os.path.join(download_dir, fname)
                                        try:
                                            os.makedirs(targetdir)
                                            setperm(targetdir)
                                        except OSError as why:
                                            if not os.path.isdir(targetdir):
                                                logger.debug('Failed to create directory [%s], %s' %
                                                             (targetdir, why.strerror))
                                        if os.path.isdir(targetdir):
                                            if book['NZBmode'] in ['torrent', 'magnet', 'torznab'] and \
                                                    lazylibrarian.CONFIG['KEEP_SEEDING']:
                                                move_into_subdir(download_dir, targetdir, fname, move='copy')
                                            else:
                                                move_into_subdir(download_dir, targetdir, fname)
                                            pp_path = targetdir

                            if os.path.isdir(pp_path):
                                logger.debug('Found folder (%s%%) [%s] for %s %s' %
                                             (match, pp_path, book_type, matchtitle))
                                skipped = False
                                if book_type == 'eBook' and not book_file(pp_path, 'ebook'):
                                    logger.debug("Skipping %s, no ebook found" % pp_path)
                                    skipped = True
                                elif book_type == 'AudioBook' and not book_file(pp_path, 'audiobook'):
                                    logger.debug("Skipping %s, no audiobook found" % pp_path)
                                    skipped = True
                                elif book_type == 'Magazine' and not book_file(pp_path, 'mag'):
                                    logger.debug("Skipping %s, no magazine found" % pp_path)
                                    skipped = True
                                if not os.listdir(pp_path):
                                    logger.debug("Skipping %s, folder is empty" % pp_path)
                                    skipped = True
                                elif bts_file(pp_path):
                                    logger.debug("Skipping %s, found a .bts file" % pp_path)
                                    skipped = True
                                if not skipped:
                                    matches.append([match, pp_path, book])
                            else:
                                logger.debug('%s is not a directory?' % pp_path)
                        else:
                            pp_path = os.path.join(download_dir, fname)
                            matches.append([match, pp_path, book])  # so we can report closest match
                    else:
                        logger.debug('Skipping %s' % fname)

                match = 0
                if matches:
                    highest = max(matches, key=lambda x: x[0])
                    match = highest[0]
                    pp_path = highest[1]
                    book = highest[2]
                if match and match >= lazylibrarian.CONFIG['DLOAD_RATIO']:
                    mostrecentissue = ''
                    logger.debug(u'Found match (%s%%): %s for %s %s' % (match, pp_path, book_type, book['NZBtitle']))

                    cmd = 'SELECT AuthorName,BookName from books,authors WHERE BookID=?'
                    cmd += ' and books.AuthorID = authors.AuthorID'
                    data = myDB.match(cmd, (book['BookID'],))
                    if data:  # it's ebook/audiobook
                        logger.debug(u'Processing %s %s' % (book_type, book['BookID']))
                        authorname = data['AuthorName']
                        authorname = ' '.join(authorname.split())  # ensure no extra whitespace
                        bookname = data['BookName']
                        if 'windows' in platform.system().lower() and '/' in lazylibrarian.CONFIG['EBOOK_DEST_FOLDER']:
                            logger.warn('Please check your EBOOK_DEST_FOLDER setting')
                            lazylibrarian.CONFIG['EBOOK_DEST_FOLDER'] = lazylibrarian.CONFIG[
                                'EBOOK_DEST_FOLDER'].replace('/', '\\')
                        # Default destination path, should be allowed change per config file.
                        dest_path = lazylibrarian.CONFIG['EBOOK_DEST_FOLDER'].replace('$Author', authorname).replace(
                            '$Title', bookname)
                        global_name = lazylibrarian.CONFIG['EBOOK_DEST_FILE'].replace('$Author', authorname).replace(
                            '$Title', bookname)
                        global_name = unaccented(global_name)
                        dest_path = unaccented_str(replace_all(dest_path, __dic__))
                        dest_dir = lazylibrarian.DIRECTORY('eBook')
                        if book_type == 'AudioBook' and lazylibrarian.DIRECTORY('Audio'):
                            dest_dir = lazylibrarian.DIRECTORY('Audio')
                        dest_path = os.path.join(dest_dir, dest_path).encode(lazylibrarian.SYS_ENCODING)
                    else:
                        data = myDB.match('SELECT IssueDate from magazines WHERE Title=?', (book['BookID'],))
                        if data:  # it's a magazine
                            logger.debug(u'Processing magazine %s' % book['BookID'])
                            # AuxInfo was added for magazine release date, normally housed in 'magazines'
                            # but if multiple files are downloading, there will be an error in post-processing
                            # trying to go to the same directory.
                            mostrecentissue = data['IssueDate']  # keep for processing issues arriving out of order
                            mag_name = unaccented_str(replace_all(book['BookID'], __dic__))
                            # book auxinfo is a cleaned date, eg 2015-01-01
                            dest_path = lazylibrarian.CONFIG['MAG_DEST_FOLDER'].replace(
                                '$IssueDate', book['AuxInfo']).replace('$Title', mag_name)

                            if lazylibrarian.CONFIG['MAG_RELATIVE']:
                                if dest_path[0] not in '._':
                                    dest_path = '_' + dest_path
                                dest_dir = lazylibrarian.DIRECTORY('eBook')
                                dest_path = os.path.join(dest_dir, dest_path).encode(lazylibrarian.SYS_ENCODING)
                            else:
                                dest_path = dest_path.encode(lazylibrarian.SYS_ENCODING)
                            authorname = None
                            bookname = None
                            global_name = lazylibrarian.CONFIG['MAG_DEST_FILE'].replace('$IssueDate',
                                                                                        book['AuxInfo']).replace(
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

                success, dest_file = processDestination(pp_path, dest_path, authorname, bookname,
                                                        global_name, book['BookID'], book_type)
                if success:
                    logger.debug("Processed %s: %s, %s" % (book['NZBmode'], global_name, book['NZBurl']))
                    # update nzbs, only update the snatched ones in case multiple matches for same book/magazine issue
                    controlValueDict = {"NZBurl": book['NZBurl'], "Status": "Snatched"}
                    newValueDict = {"Status": "Processed", "NZBDate": now()}  # say when we processed it
                    myDB.upsert("wanted", newValueDict, controlValueDict)

                    if bookname:  # it's ebook or audiobook
                        processExtras(dest_file, global_name, book['BookID'], book_type)
                    else:  # update mags
                        if mostrecentissue:
                            if mostrecentissue.isdigit() and str(book['AuxInfo']).isdigit():
                                older = (int(mostrecentissue) > int(book['AuxInfo']))  # issuenumber
                            else:
                                older = (mostrecentissue > book['AuxInfo'])  # YYYY-MM-DD
                        else:
                            older = False

                        controlValueDict = {"Title": book['BookID']}
                        if older:  # check this in case processing issues arriving out of order
                            newValueDict = {"LastAcquired": today(), "IssueStatus": "Open"}
                        else:
                            newValueDict = {"IssueDate": book['AuxInfo'], "LastAcquired": today(),
                                            "LatestCover": os.path.splitext(dest_file)[0] + '.jpg',
                                            "IssueStatus": "Open"}
                        myDB.upsert("magazines", newValueDict, controlValueDict)

                        iss_id = create_id("%s %s" % (book['BookID'], book['AuxInfo']))
                        controlValueDict = {"Title": book['BookID'], "IssueDate": book['AuxInfo']}
                        newValueDict = {"IssueAcquired": today(),
                                        "IssueFile": dest_file,
                                        "IssueID": iss_id
                                        }
                        myDB.upsert("issues", newValueDict, controlValueDict)

                        # create a thumbnail cover for the new issue
                        create_cover(dest_file)
                        processMAGOPF(dest_file, book['BookID'], book['AuxInfo'], iss_id)

                    # calibre or ll copied/moved the files we want, now delete source files

                    to_delete = True
                    if book['NZBmode'] in ['torrent', 'magnet', 'torznab']:
                        # Only delete torrents if we don't want to keep seeding
                        if lazylibrarian.CONFIG['KEEP_SEEDING']:
                            logger.warn('%s is seeding %s %s' % (book['Source'], book['NZBmode'], book['NZBtitle']))
                            to_delete = False
                    if to_delete:
                        # ask downloader to delete the torrent, but not the files
                        # we may delete them later, depending on other settings
                        if not book['Source']:
                            logger.warn("Unable to remove %s, no source" % book['NZBtitle'])
                        elif not book['DownloadID'] or book['DownloadID'] == "unknown":
                            logger.warn("Unable to remove %s from %s, no DownloadID" %
                                        (book['NZBtitle'], book['Source'].lower()))
                        elif book['Source'] != 'DIRECT':
                            logger.debug('Removing %s from %s' % (book['NZBtitle'], book['Source'].lower()))
                            delete_task(book['Source'], book['DownloadID'], False)

                    if to_delete:
                        # only delete the files if not in download root dir and if DESTINATION_COPY not set
                        if not lazylibrarian.CONFIG['DESTINATION_COPY'] and (pp_path != download_dir):
                            if os.path.isdir(pp_path):
                                # calibre might have already deleted it?
                                try:
                                    shutil.rmtree(pp_path)
                                    logger.debug('Deleted %s, %s from %s' %
                                                 (book['NZBtitle'], book['NZBmode'], book['Source'].lower()))
                                except Exception as why:
                                    logger.debug("Unable to remove %s, %s" % (pp_path, str(why)))
                        else:
                            if lazylibrarian.CONFIG['DESTINATION_COPY']:
                                logger.debug("Not removing original files as Keep Files is set")
                            else:
                                logger.debug("Not removing original files as in download root")

                    logger.info('Successfully processed: %s' % global_name)

                    ppcount += 1
                    custom_notify_download(book['BookID'])

                    notify_download("%s %s from %s at %s" %
                                    (book_type, global_name, book['NZBprov'], now()), book['BookID'])
                    update_downloads(book['NZBprov'])
                else:
                    logger.error('Postprocessing for %s has failed: %s' % (global_name, dest_file))
                    controlValueDict = {"NZBurl": book['NZBurl'], "Status": "Snatched"}
                    newValueDict = {"Status": "Failed", "NZBDate": now()}
                    myDB.upsert("wanted", newValueDict, controlValueDict)
                    # if it's a book, reset status so we try for a different version
                    # if it's a magazine, user can select a different one from pastissues table
                    if book_type == 'eBook':
                        myDB.action('UPDATE books SET status="Wanted" WHERE BookID=?', (book['BookID'],))
                    elif book_type == 'AudioBook':
                        myDB.action('UPDATE books SET audiostatus="Wanted" WHERE BookID=?', (book['BookID'],))

                    # at this point, as it failed we should move it or it will get postprocessed
                    # again (and fail again)
                    try:
                        os.rename(pp_path, pp_path + '.fail')
                        logger.error('Warning - Residual files remain in %s.fail' % pp_path)
                    except Exception as e:
                        # rename fails on MacOS as can't rename a directory that's not empty??
                        logger.error("Unable to rename %s, %s" % (pp_path, str(e)))
                        try:
                            fname = os.path.join(pp_path, "LL.(fail).bts")
                            with open(fname, 'a'):
                                os.utime(fname, None)
                            logger.error('Warning - Residual files remain in %s' % pp_path)
                        except OSError:
                            logger.error('Warning - Unable to create bts file. Residual files remain in %s' % pp_path)

        # Check for any books in download that weren't marked as snatched, but have a LL.(bookid)
        # do a fresh listdir in case we processed and deleted any earlier
        # and don't process any we've already done as we might not want to delete originals
        downloads = os.listdir(download_dir)
        if int(lazylibrarian.LOGLEVEL) > 2:
            logger.debug("Scanning %s entries in %s for LL.(num)" % (len(downloads), download_dir))
        for entry in downloads:
            if "LL.(" in entry:
                if isinstance(entry, str):
                    if int(lazylibrarian.LOGLEVEL) > 2:
                        logger.warn("unexpected unicode conversion in LL scanner")
                    entry = try_rename(download_dir, entry)
                    if not entry:
                        entry = "failed rename"
                dname, extn = os.path.splitext(entry)
                if not extn or extn not in skipped_extensions:
                    bookID = entry.split("LL.(")[1].split(")")[0]
                    logger.debug("Book with id: %s found in download directory" % bookID)
                    data = myDB.match('SELECT BookFile from books WHERE BookID=?', (bookID,))
                    if data and data['BookFile'] and os.path.isfile(data['BookFile']):
                        logger.debug('Skipping BookID %s, already exists' % bookID)
                    else:
                        pp_path = os.path.join(download_dir, entry)

                        if int(lazylibrarian.LOGLEVEL) > 2:
                            logger.debug("Checking type of %s" % pp_path)

                        if os.path.isfile(pp_path):
                            if int(lazylibrarian.LOGLEVEL) > 2:
                                logger.debug("%s is a file" % pp_path)
                            pp_path = os.path.join(download_dir)

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

        logger.info('%s book%s/mag%s processed.' % (ppcount, plural(ppcount), plural(ppcount)))

        # Now check for any that are still marked snatched...
        snatched = myDB.select('SELECT * from wanted WHERE Status="Snatched"')
        if lazylibrarian.CONFIG['TASK_AGE'] and len(snatched) > 0:
            for book in snatched:
                book_type = book['AuxInfo']
                if book_type != 'AudioBook' and book_type != 'eBook':
                    if book_type is None or book_type == '':
                        book_type = 'eBook'
                    else:
                        book_type = 'Magazine'
                # FUTURE: we could check percentage downloaded or eta?
                # if percentage is increasing, it's just slow
                try:
                    when_snatched = time.strptime(book['NZBdate'], '%Y-%m-%d %H:%M:%S')
                    when_snatched = time.mktime(when_snatched)
                    diff = time.time() - when_snatched  # time difference in seconds
                except ValueError:
                    diff = 0
                hours = int(diff / 3600)
                if hours >= lazylibrarian.CONFIG['TASK_AGE']:
                    if book['Source']:
                        logger.warn('%s was sent to %s %s hours ago, deleting failed task' %
                                (book['NZBtitle'], book['Source'].lower(), hours))
                    # change status to "Failed", and ask downloader to delete task and files
                    if book['BookID'] != 'unknown':
                        if book_type == 'eBook':
                            myDB.action('UPDATE books SET status="Wanted" WHERE BookID=?', (book['BookID'],))
                        elif book_type == 'AudioBook':
                            myDB.action('UPDATE books SET audiostatus="Wanted" WHERE BookID=?', (book['BookID'],))
                        myDB.action('UPDATE wanted SET Status="Failed" WHERE BookID=?', (book['BookID'],))
                        delete_task(book['Source'], book['DownloadID'], True)

        # Check if postprocessor needs to run again
        snatched = myDB.select('SELECT * from wanted WHERE Status="Snatched"')
        if len(snatched) == 0:
            logger.info('Nothing marked as snatched. Stopping postprocessor.')
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
            sabnzbd.SABnzbd(DownloadID, 'delhistory', remove_data)
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
            client = DelugeRPCClient(lazylibrarian.CONFIG['DELUGE_HOST'],
                                     int(lazylibrarian.CONFIG['DELUGE_PORT']),
                                     lazylibrarian.CONFIG['DELUGE_USER'],
                                     lazylibrarian.CONFIG['DELUGE_PASS'])
            try:
                client.connect()
                client.call('core.remove_torrent', DownloadID, remove_data)
            except Exception as e:
                logger.debug('DelugeRPC failed %s' % str(e))
                return False
        elif Source == 'DIRECT':
            return True
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
        # eg from a manual search
        if int(lazylibrarian.LOGLEVEL) > 2:
            logger.debug("import_book %s" % pp_path)
        if book_file(pp_path, "audiobook"):
            book_type = "AudioBook"
            dest_dir = lazylibrarian.DIRECTORY('Audio')
        elif book_file(pp_path, "ebook"):
            book_type = "eBook"
            dest_dir = lazylibrarian.DIRECTORY('eBook')
        else:
            logger.warn("Failed to find an ebook or audiobook in [%s]" % pp_path)
            return False

        myDB = database.DBConnection()
        cmd = 'SELECT AuthorName,BookName from books,authors WHERE BookID=? and books.AuthorID = authors.AuthorID'
        data = myDB.match(cmd, (bookID,))
        if data:
            cmd = 'SELECT BookID, NZBprov, AuxInfo FROM wanted WHERE BookID=? and Status="Snatched"'
            # we may have snatched an ebook and audiobook of the same title/id
            was_snatched = myDB.select(cmd, (bookID,))
            want_audio = False
            want_ebook = False
            for item in was_snatched:
                if item['AuxInfo'] == 'AudioBook':
                    want_audio = True
                elif item['AuxInfo'] == 'eBook' or item['AuxInfo'] == '':
                    want_ebook = True

            match = False
            if want_audio and book_type == "AudioBook":
                match = True
            elif want_ebook and book_type == "eBook":
                match = True
            elif not was_snatched:
                logger.debug('Bookid %s was not snatched so cannot check type, contains %s' % (bookID, book_type))
                match = True
            if not match:
                logger.debug('Bookid %s, failed to find valid %s' % (bookID, book_type))
                return False

            authorname = data['AuthorName']
            authorname = ' '.join(authorname.split())  # ensure no extra whitespace
            bookname = data['BookName']
            # DEST_FOLDER pattern is the same for ebook and audiobook
            if 'windows' in platform.system().lower() and '/' in lazylibrarian.CONFIG['EBOOK_DEST_FOLDER']:
                logger.warn('Please check your EBOOK_DEST_FOLDER setting')
                lazylibrarian.CONFIG['EBOOK_DEST_FOLDER'] = lazylibrarian.CONFIG['EBOOK_DEST_FOLDER'].replace('/', '\\')

            dest_path = lazylibrarian.CONFIG['EBOOK_DEST_FOLDER'].replace('$Author', authorname).replace('$Title',
                                                                                                         bookname)
            # global_name is only used for ebooks to ensure book/cover/opf all have the same basename
            # audiobooks are usually multi part so can't be renamed this way
            global_name = lazylibrarian.CONFIG['EBOOK_DEST_FILE'].replace('$Author', authorname).replace('$Title',
                                                                                                         bookname)
            global_name = unaccented(global_name)
            dest_path = unaccented_str(replace_all(dest_path, __dic__))
            dest_path = os.path.join(dest_dir, dest_path).encode(lazylibrarian.SYS_ENCODING)

            if int(lazylibrarian.LOGLEVEL) > 2:
                logger.debug("processDestination %s" % pp_path)

            success, dest_file = processDestination(pp_path, dest_path, authorname, bookname,
                                                    global_name, bookID, book_type)
            if success:
                # update nzbs
                snatched_from = "from " + was_snatched[0]['NZBprov'] if was_snatched else "manually added"
                if int(lazylibrarian.LOGLEVEL) > 2:
                    logger.debug("was_snatched %s" % snatched_from)
                if was_snatched:
                    controlValueDict = {"BookID": bookID}
                    newValueDict = {"Status": "Processed", "NZBDate": now()}  # say when we processed it
                    myDB.upsert("wanted", newValueDict, controlValueDict)

                if bookname:
                    processExtras(dest_file, global_name, bookID, book_type)

                if not lazylibrarian.CONFIG['DESTINATION_COPY'] and pp_path != dest_dir:
                    if os.path.isdir(pp_path):
                        # calibre might have already deleted it?
                        try:
                            shutil.rmtree(pp_path)
                        except Exception as why:
                            logger.debug("Unable to remove %s, %s" % (pp_path, str(why)))
                else:
                    if lazylibrarian.CONFIG['DESTINATION_COPY']:
                        logger.debug("Not removing original files as Keep Files is set")
                    else:
                        logger.debug("Not removing original files as in download root")

                logger.info('Successfully processed: %s' % global_name)
                custom_notify_download(bookID)

                notify_download("%s %s from %s at %s" %
                                    (book_type, global_name, snatched_from, now()), bookID)
                update_downloads(snatched_from)
                return True
            else:
                logger.error('Postprocessing for %s has failed: %s' % (global_name, dest_file))
                logger.error('Warning - Residual files remain in %s.fail' % pp_path)
                was_snatched = myDB.match('SELECT NZBurl FROM wanted WHERE BookID=? and Status="Snatched"', (bookID,))
                if was_snatched:
                    controlValueDict = {"NZBurl": was_snatched['NZBurl']}
                    newValueDict = {"Status": "Failed", "NZBDate": now()}
                    myDB.upsert("wanted", newValueDict, controlValueDict)
                # reset status so we try for a different version
                if book_type == 'AudioBook':
                    myDB.action('UPDATE books SET audiostatus="Wanted" WHERE BookID=?', (bookID,))
                else:
                    myDB.action('UPDATE books SET status="Wanted" WHERE BookID=?', (bookID,))
                try:
                    os.rename(pp_path, pp_path + '.fail')
                    logger.error('Warning - Residual files remain in %s.fail' % pp_path)
                except Exception as e:
                    # rename fails on MacOS as can't rename a directory that's not empty??
                    logger.error("Unable to rename %s, %s" % (pp_path, str(e)))
                    try:
                        fname = os.path.join(pp_path, "LL.(fail).bts")
                        with open(fname, 'a'):
                            os.utime(fname, None)
                        logger.error('Warning - Residual files remain in %s' % pp_path)
                    except OSError as e:
                        logger.error('Warning - Unable to create bts file. Residual files remain in %s: %s' %
                                     (pp_path, str(e)))
        return False
    except Exception:
        logger.error('Unhandled exception in importBook: %s' % traceback.format_exc())


def processExtras(dest_file=None, global_name=None, bookid=None, book_type="eBook"):
    # given bookid, handle author count, calibre autoadd, book image, opf

    if not bookid:
        logger.error('processExtras: No bookid supplied')
        return

    myDB = database.DBConnection()

    controlValueDict = {"BookID": bookid}
    if book_type == 'AudioBook':
        newValueDict = {"AudioFile": dest_file, "AudioStatus": "Open", "AudioLibrary": now()}
        myDB.upsert("books", newValueDict, controlValueDict)
    else:
        newValueDict = {"Status": "Open", "BookFile": dest_file, "BookLibrary": now()}
        myDB.upsert("books", newValueDict, controlValueDict)

    # update authors book counts
    match = myDB.match('SELECT AuthorID FROM books WHERE BookID=?', (bookid,))
    if match:
        update_totals(match['AuthorID'])

    if book_type != 'eBook':  # only do autoadd/img/opf for ebooks
        return

    if len(lazylibrarian.CONFIG['IMP_CALIBREDB']):
        logger.debug('Calibre should have created the extras for us')
        return

    dest_path = os.path.dirname(dest_file)
    # If you use auto add by Calibre you need the book in a single directory, not nested
    # So take the file you Copied/Moved to Dest_path and copy it to a Calibre auto add folder.
    if lazylibrarian.CONFIG['IMP_AUTOADD']:
        processAutoAdd(dest_path)

    cmd = 'SELECT AuthorName,BookID,BookName,BookDesc,BookIsbn,BookImg,BookDate,'
    cmd += 'BookLang,BookPub from books,authors WHERE BookID=? and books.AuthorID = authors.AuthorID'
    data = myDB.match(cmd, (bookid,))
    if not data:
        logger.error('processExtras: No data found for bookid %s' % bookid)
        return

    # try image
    processIMG(dest_path, data['BookImg'], global_name)

    # try metadata
    processOPF(dest_path, data, global_name)


def processDestination(pp_path=None, dest_path=None, authorname=None, bookname=None, global_name=None, bookid=None,
                       booktype=None):
    """ Copy book/mag and associated files into target directory
        Return True, full_path_to_book  or False, error_message"""

    if not bookname:
        booktype = 'mag'

    booktype = booktype.lower()

    # ensure directory is unicode so we get unicode results from listdir
    if isinstance(pp_path, str):
        pp_path = pp_path.decode(lazylibrarian.SYS_ENCODING)

    match = False
    if booktype == 'ebook' and lazylibrarian.CONFIG['ONE_FORMAT']:
        booktype_list = getList(lazylibrarian.CONFIG['EBOOK_TYPE'])
        for btype in booktype_list:
            if not match:
                for fname in os.listdir(pp_path):
                    extn = os.path.splitext(fname)[1].lstrip('.')
                    if extn and extn.lower() == btype:
                        match = btype
                        break
        if match:
            logger.debug('One format import, best match = %s' % match)
            for fname in os.listdir(pp_path):
                if is_valid_booktype(fname, booktype=booktype) and not fname.endswith(match):
                    try:
                        logger.debug('Deleting %s' % os.path.splitext(fname)[1])
                        os.remove(os.path.join(pp_path, fname))
                    except OSError as why:
                        logger.debug('Unable to delete %s: %s' % (fname, why.strerror))

    else:  # mag or audiobook or multi-format book
        for fname in os.listdir(pp_path):
            if is_valid_booktype(fname, booktype=booktype):
                match = True
                break

    if not match:
        # no book/mag found in a format we wanted. Leave for the user to delete or convert manually
        return False, 'Unable to locate a valid filetype (%s) in %s, leaving for manual processing' % (
            booktype, pp_path)

    # If ebook, do we want calibre to import the book for us
    newbookfile = ''
    if booktype == 'ebook' and len(lazylibrarian.CONFIG['IMP_CALIBREDB']):
        dest_dir = lazylibrarian.DIRECTORY('eBook')
        params = []
        try:
            logger.debug('Importing %s into calibre library' % global_name)
            # calibre may ignore metadata.opf and book_name.opf depending on calibre settings,
            # and ignores opf data if there is data embedded in the book file
            # so we send separate "set_metadata" commands after the import
            for fname in os.listdir(pp_path):
                filename, extn = os.path.splitext(fname)
                # calibre does not like quotes in author names
                os.rename(os.path.join(pp_path, filename + extn), os.path.join(
                    pp_path, global_name.replace('"', '_') + extn))

            calibre_id = ''
            if bookid.isdigit():
                identifier = "goodreads:%s" % bookid
            else:
                identifier = "google:%s" % bookid

            params = [lazylibrarian.CONFIG['IMP_CALIBREDB'],
                      'add',
                      '-1',
                      '--with-library=%s' % dest_dir,
                      pp_path
                      ]
            logger.debug(str(params))
            res = subprocess.check_output(params, stderr=subprocess.STDOUT)
            if not res:
                logger.debug('No response from %s' % lazylibrarian.CONFIG['IMP_CALIBREDB'])
            else:
                logger.debug('%s reports: %s' % (lazylibrarian.CONFIG['IMP_CALIBREDB'], unaccented_str(res)))
                if 'already exist' in res:
                    logger.warn('Calibre failed to import %s %s, reports book already exists' % (authorname, bookname))
                if 'Added book ids' in res:
                    calibre_id = res.split("book ids: ", 1)[1].split("\n", 1)[0]
                    logger.debug('Calibre ID: %s' % calibre_id)
                    authorparams = [lazylibrarian.CONFIG['IMP_CALIBREDB'],
                                    'set_metadata',
                                    '--field',
                                    'authors:%s' % unaccented(authorname),
                                    '--with-library',
                                    dest_dir,
                                    calibre_id
                                    ]
                    logger.debug(str(authorparams))
                    res = subprocess.check_output(authorparams, stderr=subprocess.STDOUT)
                    if res:
                        logger.debug(
                            '%s author reports: %s' % (lazylibrarian.CONFIG['IMP_CALIBREDB'], unaccented_str(res)))

                    titleparams = [lazylibrarian.CONFIG['IMP_CALIBREDB'],
                                   'set_metadata',
                                   '--field',
                                   'title:%s' % unaccented(bookname),
                                   '--with-library',
                                   dest_dir,
                                   calibre_id
                                   ]
                    logger.debug(str(titleparams))
                    res = subprocess.check_output(titleparams, stderr=subprocess.STDOUT)
                    if res:
                        logger.debug(
                            '%s book reports: %s' % (lazylibrarian.CONFIG['IMP_CALIBREDB'], unaccented_str(res)))

                    metaparams = [lazylibrarian.CONFIG['IMP_CALIBREDB'],
                                  'set_metadata',
                                  '--field',
                                  'identifiers:%s' % identifier,
                                  '--with-library',
                                  dest_dir,
                                  calibre_id
                                  ]
                    logger.debug(str(metaparams))
                    res = subprocess.check_output(metaparams, stderr=subprocess.STDOUT)
                    if res:
                        logger.debug(
                            '%s identifier reports: %s' % (lazylibrarian.CONFIG['IMP_CALIBREDB'], unaccented_str(res)))

            # calibre does not like quotes in author names
            calibre_dir = os.path.join(dest_dir, unaccented_str(authorname.replace('"', '_')), '')
            if os.path.isdir(calibre_dir):  # assumed author directory
                target_dir = os.path.join(calibre_dir, '%s (%s)' % (global_name, calibre_id))
                if os.path.isdir(target_dir):
                    imported = LibraryScan(target_dir)
                    newbookfile = book_file(target_dir, booktype='ebook')
                    if newbookfile:
                        setperm(target_dir)
                        for fname in os.listdir(target_dir):
                            setperm(os.path.join(target_dir, fname))
                    else:
                        logger.warn("Failed to find a valid ebook in [%s]" % target_dir)
                        imported = False
                else:
                    imported = LibraryScan(calibre_dir)  # rescan whole authors directory
            else:
                logger.error("Failed to locate calibre dir [%s]" % calibre_dir)
                imported = False
                # imported = LibraryScan(dest_dir)  # may have to rescan whole library instead
            if not imported:
                return False, "Unable to import book to %s" % calibre_dir
        except subprocess.CalledProcessError as e:
            logger.debug(params)
            return False, 'calibredb import failed: %s' % e.output
        except OSError as e:
            return False, 'calibredb failed, %s' % e.strerror
    else:
        # we are copying the files ourselves, either it's audiobook, magazine or we don't want to use calibre
        if not os.path.exists(dest_path):
            logger.debug('%s does not exist, so it\'s safe to create it' % dest_path)
        elif not os.path.isdir(dest_path):
            logger.debug('%s exists but is not a directory, deleting it' % dest_path)
            try:
                os.remove(dest_path)
            except OSError as why:
                return False, 'Unable to delete %s: %s' % (dest_path, why.strerror)

        try:
            os.makedirs(dest_path)
            setperm(dest_path)
        except OSError as why:
            if not os.path.isdir(dest_path):
                return False, 'Unable to create directory %s: %s' % (dest_path, why.strerror)

        # ok, we've got a target directory, try to copy only the files we want, renaming them on the fly.
        firstfile = ''  # try to keep track of "preferred" ebook type or the first part of multi-part audiobooks

        for fname in os.listdir(pp_path):
            if isinstance(fname, str):
                if int(lazylibrarian.LOGLEVEL) > 2:
                    logger.warn("unexpected unicode conversion copying file to target directory")
                fname = try_rename(pp_path, fname)
            if fname.lower().endswith(".jpg") or fname.lower().endswith(".opf") or \
                    is_valid_booktype(fname, booktype=booktype):
                logger.debug('Copying %s to directory %s' % (fname, dest_path))
                try:
                    if booktype == 'audiobook':
                        destfile = os.path.join(dest_path, fname)  # don't rename, just copy it
                    else:
                        # for ebooks, the book, jpg, opf all have the same basename
                        destfile = os.path.join(dest_path, global_name + os.path.splitext(fname)[1])
                    shutil.copyfile(os.path.join(pp_path, fname), destfile)
                    setperm(destfile)
                    if is_valid_booktype(destfile, booktype=booktype):
                        newbookfile = destfile
                        if booktype == 'audiobook' and '01' in destfile:
                            firstfile = destfile
                except Exception as why:
                    return False, "Unable to copy file %s to %s: %s" % (fname, dest_path, str(why))
            else:
                logger.debug('Ignoring unwanted file: %s' % fname)

        # for ebooks, prefer the first book_type found in ebook_type list
        if booktype == 'ebook':
            book_basename = os.path.join(dest_path, global_name)
            booktype_list = getList(lazylibrarian.CONFIG['EBOOK_TYPE'])
            for book_type in booktype_list:
                preferred_type = "%s.%s" % (book_basename, book_type)
                if os.path.exists(preferred_type):
                    logger.debug("Link to preferred type %s" % book_type)
                    firstfile = preferred_type
                    break

        if firstfile:
            newbookfile = firstfile
    return True, newbookfile


def processAutoAdd(src_path=None):
    # Called to copy the book files to an auto add directory for the likes of Calibre which can't do nested dirs
    # ensure directory is unicode so we get unicode results from listdir
    if isinstance(src_path, str):
        src_path = src_path.decode(lazylibrarian.SYS_ENCODING)
    autoadddir = lazylibrarian.CONFIG['IMP_AUTOADD']
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
        # Update - seems Calibre will only use the jpeg if named same as book, not cover.jpg
        # and only imports one format of each ebook, treats the others as duplicates, might be configable in calibre?
        # ignores author/title data in opf file if there is any embedded in book

        match = False
        if lazylibrarian.CONFIG['ONE_FORMAT']:
            booktype_list = getList(lazylibrarian.CONFIG['EBOOK_TYPE'])
            for booktype in booktype_list:
                while not match:
                    for name in names:
                        extn = os.path.splitext(name)[1].lstrip('.')
                        if extn and extn.lower() == booktype:
                            match = booktype
                            break

        for name in names:
            if match and is_valid_booktype(name, booktype="book") and not name.endswith(match):
                logger.debug('Skipping %s' % os.path.splitext(name)[1])
            else:
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

def processMAGOPF(issuefile, title, issue, issueID):
    """ Needs calibre to be configured to read metadata from file contents, not filename """
    dest_path, global_name = os.path.split(issuefile)
    global_name, extn = os.path.splitext(global_name)

    if len(issue) == 10 and issue[8:] == '01' and issue[4] == '-' and issue[7] == '-':  # yyyy-mm-01
        yr = issue[0:4]
        mn = issue[5:7]
        month = lazylibrarian.MONTHNAMES[int(mn)][0]
        iname = "%s - %s%s %s" % (title, month[0].upper(), month[1:], yr)  # The Magpi - January 2017
    elif title in issue:
        iname = issue  # 0063 - Android Magazine -> 0063
    else:
        iname = "%s - %s" % (title, issue)  # Android Magazine - 0063

    mtime = os.path.getmtime(issuefile)
    iss_acquired = datetime.date.isoformat(datetime.date.fromtimestamp(mtime))

    data = {
            'AuthorName': title,
            'BookID': issueID,
            'BookName': iname,
            'BookDesc': '',
            'BookIsbn': '',
            'BookDate': iss_acquired,
            'BookLang': 'eng',
            'BookImg': global_name + '.jpg',
            'BookPub': ''
            }
    processOPF(dest_path, data, global_name)

def processOPF(dest_path=None, data=None, global_name=None):

    opfpath = os.path.join(dest_path, global_name + '.opf')
    if os.path.exists(opfpath):
        logger.debug('%s already exists. Did not create one.' % opfpath)
        return

    authorname = data['AuthorName']
    bookid = data['BookID']
    bookname = data['BookName']
    bookdesc = data['BookDesc']
    bookisbn = data['BookIsbn']
    # bookimg = data['BookImg']
    bookdate = data['BookDate']
    booklang = data['BookLang']
    bookpub = data['BookPub']

    if bookid.isdigit():
        scheme = 'GOODREADS'
    else:
        scheme = 'GoogleBooks'

    opfinfo = '<?xml version="1.0"  encoding="UTF-8"?>\n\
<package version="2.0" xmlns="http://www.idpf.org/2007/opf" >\n\
    <metadata xmlns:dc="http://purl.org/dc/elements/1.1/" xmlns:opf="http://www.idpf.org/2007/opf">\n\
        <dc:title>%s</dc:title>\n\
        <creator>%s</creator>\n\
        <dc:language>%s</dc:language>\n\
        <dc:identifier scheme="%s">%s</dc:identifier>\n' % (bookname, authorname, booklang, scheme, bookid)

    if bookisbn:
        opfinfo += '        <dc:identifier scheme="ISBN">%s</dc:identifier>\n' % bookisbn

    if bookpub:
        opfinfo += '        <dc:publisher>%s</dc:publisher>\n' % bookpub

    if bookdate:
        opfinfo += '        <dc:date>%s</dc:date>\n' % bookdate

    if bookdesc:
        opfinfo += '        <dc:description>%s</dc:description>\n' % bookdesc

    opfinfo += '        <guide>\n\
            <reference href="%s" type="cover" title="Cover"/>\n\
        </guide>\n\
    </metadata>\n\
</package>' % global_name + '.jpg'  # file in current directory, not full path

    dic = {'...': '', ' & ': ' ', ' = ': ' ', '$': 's', ' + ': ' ', ',': '', '*': ''}

    opfinfo = unaccented_str(replace_all(opfinfo, dic))

    # handle metadata
    opfpath = os.path.join(dest_path, global_name + '.opf')
    with open(opfpath, 'wb') as opf:
        opf.write(opfinfo)
    logger.debug('Saved metadata to: ' + opfpath)


class imgGoogle(FancyURLopener):
    # Hack because Google wants a user agent for downloading images,
    # which is stupid because it's so easy to circumvent.
    version = 'Mozilla/5.0 (X11; U; Linux i686) Gecko/20071127 Firefox/2.0.0.11'
