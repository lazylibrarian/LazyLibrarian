import shutil
import os
import subprocess
import threading
import platform
import hashlib
from urllib import FancyURLopener
from lib.fuzzywuzzy import fuzz
import lazylibrarian

from lazylibrarian import database, logger, gr
from lazylibrarian.magazinescan import create_id, create_cover
from lazylibrarian.formatter import plural, now, today, is_valid_booktype, unaccented_str, replace_all, unaccented
from lazylibrarian.common import scheduleJob, book_file, opf_file
from lazylibrarian.notifiers import notify_download
from lazylibrarian.importer import addAuthorToDB
from lazylibrarian.librarysync import get_book_info, find_book_in_db, LibraryScan
from lazylibrarian.gr import GoodReads

def processAlternate(source_dir=None):
    # import a book from an alternate directory
    if not source_dir or os.path.isdir(source_dir) is False:
        logger.warn('Alternate directory not found')
        return
    if source_dir == lazylibrarian.DESTINATION_DIR:
        logger.warn('Alternate directory must not be the same as destination')
        return

    logger.debug('Processing alternate directory %s' % source_dir)
    # first, recursively process any books in subdirectories
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
        if os.path.isfile(metafile):
            try:
                metadata = get_book_info(metafile)
            except:
                logger.debug('Failed to read metadata from %s' % metafile)
        else:
            logger.debug('No metadata file found for %s' % new_book)
        if not 'title' in metadata and 'creator' in metadata:
            # try to get metadata from the book file
            try:
                metadata = get_book_info(new_book)
            except:
                logger.debug('No metadata found in %s' % new_book)
        if 'title' in metadata and 'creator' in metadata:
            authorname = metadata['creator']
            bookname = metadata['title']
            myDB = database.DBConnection()

            authmatch = myDB.action('SELECT * FROM authors where AuthorName="%s"' % (authorname)).fetchone()

            if not authmatch:
                # try goodreads preferred authorname
                logger.debug( "Checking GoodReads for [%s]" % authorname)
                GR = GoodReads(authorname)
                try:
                    author_gr = GR.find_author_id()
                except:
                    logger.debug( "No author id for [%s]" % authorname)
                if author_gr:
                    grauthorname = author_gr['authorname']
                    logger.debug( "GoodReads reports [%s] for [%s]" % (grauthorname, authorname))
                    authorname = grauthorname
                    authmatch = myDB.action('SELECT * FROM authors where AuthorName="%s"' % (authorname)).fetchone()

            if authmatch:
                logger.debug("ALT: Author %s found in database" % (authorname))
            else:
                logger.debug("ALT: Author %s not found, adding to database" % (authorname))
                addAuthorToDB(authorname)

            bookid = find_book_in_db(myDB, authorname, bookname)
            if bookid:
                import_book(source_dir, bookid)
            else:
                logger.warn("Book %s by %s not found in database" % (bookname, authorname))
        else:
            logger.warn('Book %s has no metadata, unable to import' % new_book)
    else:
        logger.warn("No book file found in %s" % source_dir)


def cron_processDir():
    threading.currentThread().name = "CRON-POSTPROCESS"
    processDir()

def processDir(reset=False):

    threadname = threading.currentThread().name
    if "Thread-" in threadname:
        threading.currentThread().name = "POSTPROCESS"

    if not lazylibrarian.DOWNLOAD_DIR or not os.path.isdir(lazylibrarian.DOWNLOAD_DIR):
        processpath = os.getcwd()
    else:
        processpath = lazylibrarian.DOWNLOAD_DIR

    logger.debug(' Checking [%s] for files to post process' % processpath)

    try:
        downloads = os.listdir(processpath)
    except OSError as why:
        logger.error('Could not access [%s] directory [%s]' % (processpath, why.strerror))
        return

    myDB = database.DBConnection()
    snatched = myDB.select('SELECT * from wanted WHERE Status="Snatched"')

    if len(snatched) == 0:
        logger.info('Nothing marked as snatched.')
        scheduleJob(action='Stop', target='processDir')
        return

    if len(downloads) == 0:
        logger.info('No downloads are found. Nothing to process.')
        return

    logger.info("Checking %s download%s for %s snatched file%s" %
        (len(downloads), plural(len(downloads)), len(snatched), plural(len(snatched))))
    ppcount = 0
    for book in snatched:
        matches = []
        for fname in downloads:
            if not fname.endswith('.fail'):  # has this failed before?
                # this is to get round differences in torrent filenames.
                # Torrents aren't always returned with the name we searched for
                # there might be a better way...
                if isinstance(fname, str):
                    matchname = fname.decode(lazylibrarian.SYS_ENCODING)
                else:
                    matchname = fname
                if ' LL.(' in matchname:
                    matchname = matchname.split(' LL.(')[0]
                matchtitle = book['NZBtitle']
                match = 0
                if matchtitle:
                    if ' LL.(' in matchtitle:
                        matchtitle = matchtitle.split(' LL.(')[0]
                    match = fuzz.token_set_ratio(matchtitle, matchname)
                if match >= lazylibrarian.DLOAD_RATIO:
                    fname = matchname
                    if os.path.isfile(os.path.join(processpath, fname)):
                        # handle single file downloads here...
                        if is_valid_booktype(fname, booktype="book") \
                            or is_valid_booktype(fname, booktype="mag"):
                            dirname = os.path.join(processpath, os.path.splitext(fname)[0])
                            if not os.path.exists(dirname):
                                try:
                                    os.makedirs(dirname)
                                except OSError as why:
                                    logger.debug('Failed to create directory %s, %s' % (dirname, why.strerror))
                            if os.path.exists(dirname):
                                try:
                                    shutil.move(os.path.join(processpath, fname), os.path.join(dirname, fname))
                                    fname = os.path.splitext(fname)[0]
                                except Exception as why:
                                    logger.debug("Failed to move file %s to %s, %s" %
                                        (fname, dirname, str(why)))
                    if os.path.isdir(os.path.join(processpath, fname)):
                        pp_path = os.path.join(processpath, fname)
                        logger.debug('Found folder (%s%%) %s for %s' % (match, pp_path, book['NZBtitle']))
                        matches.append([match, pp_path, book])
                else:
                    logger.debug('No match (%s%%) %s for %s' % (match, matchname, matchtitle))
            else:
                logger.debug('Skipping %s' % fname)

        if matches:
            highest = max(matches, key=lambda x: x[0])
            match = highest[0]
            pp_path = highest[1]
            book = highest[2]
            logger.debug(u'Best match (%s%%): %s for %s' %
                    (match, pp_path, book['NZBtitle']))

            data = myDB.select('SELECT * from books WHERE BookID="%s"' % book['BookID'])
            if data:
                authorname = data[0]['AuthorName']
                bookname = data[0]['BookName']
                if 'windows' in platform.system().lower() and '/' in lazylibrarian.EBOOK_DEST_FOLDER:
                    logger.warn('Please check your EBOOK_DEST_FOLDER setting')
                    lazylibrarian.EBOOK_DEST_FOLDER = lazylibrarian.EBOOK_DEST_FOLDER.replace('/', '\\')

                # Default destination path, should be allowed change per config file.
                dest_path = lazylibrarian.EBOOK_DEST_FOLDER.replace('$Author', authorname).replace(
                    '$Title', bookname)
                global_name = lazylibrarian.EBOOK_DEST_FILE.replace('$Author', authorname).replace(
                    '$Title', bookname)
                global_name = unaccented(global_name)
                # dest_path = authorname+'/'+bookname
                # global_name = bookname + ' - ' + authorname
                # Remove characters we don't want in the filename BEFORE adding to DESTINATION_DIR
                # as windows drive identifiers have colon, eg c:  but no colons allowed elsewhere?
                dic = {'<': '', '>': '', '...': '', ' & ': ' ', ' = ': ' ', '?': '', '$': 's',
                       ' + ': ' ', '"': '', ',': '', '*': '', ':': '', ';': '', '\'': ''}
                dest_path = unaccented_str(replace_all(dest_path, dic))
                dest_path = os.path.join(lazylibrarian.DESTINATION_DIR, dest_path).encode(
                    lazylibrarian.SYS_ENCODING)
            else:
                data = myDB.select('SELECT * from magazines WHERE Title="%s"' % book['BookID'])
                if data:
                    # AuxInfo was added for magazine release date, normally housed in 'magazines' but if multiple
                    # files are downloading, there will be an error in post-processing, trying to go to the
                    # same directory.
                    mostrecentissue = data[0]['IssueDate']  # keep for processing issues arriving out of order
                    # Remove characters we don't want in the filename before (maybe) adding to DESTINATION_DIR
                    # as windows drive identifiers have colon, eg c:  but no colons allowed elsewhere?
                    dic = {'<': '', '>': '', '...': '', ' & ': ' ', ' = ': ' ', '?': '', '$': 's',
                           ' + ': ' ', '"': '', ',': '', '*': '', ':': '', ';': '', '\'': ''}
                    mag_name = unaccented_str(replace_all(book['BookID'], dic))
                    # book auxinfo is a cleaned date, eg 2015-01-01
                    dest_path = lazylibrarian.MAG_DEST_FOLDER.replace(
                        '$IssueDate',
                        book['AuxInfo']).replace('$Title', mag_name)
                    # dest_path = '_Magazines/'+title+'/'+book['AuxInfo']
                    if lazylibrarian.MAG_RELATIVE:
                        if dest_path[0] not in '._':
                            dest_path = '_' + dest_path
                        dest_path = os.path.join(lazylibrarian.DESTINATION_DIR, dest_path).encode(
                            lazylibrarian.SYS_ENCODING)
                    else:
                        dest_path = dest_path.encode(lazylibrarian.SYS_ENCODING)
                    authorname = None
                    bookname = None
                    global_name = lazylibrarian.MAG_DEST_FILE.replace('$IssueDate', book['AuxInfo']).replace(
                        '$Title', mag_name)
                    global_name = unaccented(global_name)
                    # global_name = book['AuxInfo']+' - '+title
                else:
                    logger.debug("Snatched magazine %s is not in download directory" % (book['BookID']))
                    continue
        else:
            logger.debug("Snatched %s %s is not in download directory" % (book['NZBmode'], book['NZBtitle']))
            continue

        processBook = processDestination(pp_path, dest_path, authorname, bookname, global_name)

        if processBook:
            logger.debug("Processing %s, %s" % (global_name, book['NZBurl']))
            # update nzbs, only update the snatched ones in case multiple matches for same book / magazine issue
            controlValueDict = {"NZBurl": book['NZBurl'], "Status": "Snatched"}
            newValueDict = {"Status": "Processed", "NZBDate": now()}  # say when we processed it
            myDB.upsert("wanted", newValueDict, controlValueDict)

            if bookname is not None:  # it's a book, if None it's a magazine
                if len(lazylibrarian.IMP_CALIBREDB):
                    logger.debug('Calibre should have created the extras for us')
                else:
                    processExtras(myDB, dest_path, global_name, data)
            else:
                # update mags
                controlValueDict = {"Title": book['BookID']}
                if mostrecentissue:
                    if mostrecentissue.isdigit() and str(book['AuxInfo']).isdigit():
                        older = int(mostrecentissue) > int(book['AuxInfo']) # issuenumber
                    else:
                        older = mostrecentissue > book['AuxInfo']  # YYYY-MM-DD
                else:
                    older = False
                if older:  # check this in case processing issues arriving out of order
                    newValueDict = {"LastAcquired": today(), "IssueStatus": "Open"}
                else:
                    newValueDict = {"IssueDate": book['AuxInfo'], "LastAcquired": today(),
                                    "IssueStatus": "Open"}
                myDB.upsert("magazines", newValueDict, controlValueDict)
                # dest_path is where we put the magazine after processing, but we don't have the full filename
                # so look for any "book" in that directory
                dest_file = book_file(dest_path, booktype='mag')
                controlValueDict = {"Title": book['BookID'], "IssueDate": book['AuxInfo']}
                newValueDict = {"IssueAcquired": today(),
                                "IssueFile": dest_file,
                                "IssueID": create_id("%s %s" % (book['BookID'], book['AuxInfo']))
                                }
                myDB.upsert("issues", newValueDict, controlValueDict)

                # create a thumbnail cover for the new issue
                create_cover(dest_file)

            logger.info('Successfully processed: %s' % global_name)
            ppcount = ppcount + 1
            notify_download("%s at %s" % (global_name, now()))
        else:
            logger.error('Postprocessing for %s has failed.' % global_name)
            logger.error('Warning - Residual files remain in %s.fail' % pp_path)
            controlValueDict = {"NZBurl": book['NZBurl'], "Status": "Snatched"}
            newValueDict = {"Status": "Failed", "NZBDate": now()}
            myDB.upsert("wanted", newValueDict, controlValueDict)
            # if it's a book, reset status so we try for a different version
            # if it's a magazine, user can select a different one from pastissues table
            if bookname is not None:
                myDB.action('UPDATE books SET status = "Wanted" WHERE BookID="%s"' % book['BookID'])

            # at this point, as it failed we should move it or it will get postprocessed
            # again (and fail again)
            try:
                os.rename(pp_path, pp_path + '.fail')
            except:
                logger.debug("Unable to rename %s" % pp_path)

    downloads = os.listdir(processpath)  # check in case we processed/deleted some above
    for directory in downloads:
        if "LL.(" in directory and not directory.endswith('.fail'):
            bookID = str(directory).split("LL.(")[1].split(")")[0]
            logger.debug("Book with id: " + str(bookID) + " is in downloads")
            pp_path = os.path.join(processpath, directory)

            if os.path.isfile(pp_path):
                pp_path = os.path.join(processpath)

            if (os.path.isdir(pp_path)):
                logger.debug('Found LL folder %s.' % pp_path)
            if import_book(pp_path, bookID):
                ppcount = ppcount + 1

    if ppcount == 0:
        logger.info('No snatched books/mags have been found')
    else:
        logger.info('%s book%s/mag%s processed.' % (ppcount, plural(ppcount), plural(ppcount)))

    if reset:
        scheduleJob(action='Restart', target='processDir')


def import_book(pp_path=None, bookID=None):

    # Separated this into a function so we can more easily import books from an alternate directory
    # and move them into LL folder structure given just the bookID, returns True or False
    # eg if import_book(source_directory, bookID):
    #         ppcount = ppcount + 1
    #
    myDB = database.DBConnection()
    data = myDB.select('SELECT * from books WHERE BookID="%s"' % bookID)
    if data:
        authorname = data[0]['AuthorName']
        bookname = data[0]['BookName']

        # try:
        #    auth_dir = os.path.join(lazylibrarian.DESTINATION_DIR, authorname).encode(lazylibrarian.SYS_ENCODING)
        #    os.chmod(auth_dir, 0777)
        # except Exception, e:
        #    logger.debug("Could not chmod author directory: " + str(auth_dir))

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
        dest_path = os.path.join(lazylibrarian.DESTINATION_DIR, dest_path).encode(lazylibrarian.SYS_ENCODING)

        processBook = processDestination(pp_path, dest_path, authorname, bookname, global_name)

        if processBook:
            # update nzbs
            was_snatched = len(myDB.select('SELECT BookID FROM wanted WHERE BookID="%s"' % bookID))
            if was_snatched:
                controlValueDict = {"BookID": bookID}
                newValueDict = {"Status": "Processed", "NZBDate": now()}  # say when we processed it
                myDB.upsert("wanted", newValueDict, controlValueDict)
            if bookname:
                if len(lazylibrarian.IMP_CALIBREDB):
                    logger.debug('Calibre should have created the extras for us')
                else:
                    processExtras(myDB, dest_path, global_name, data)
            logger.info('Successfully processed: %s' % global_name)
            notify_download("%s at %s" % (global_name, now()))
            return True
        else:
            logger.error('Postprocessing for %s has failed.' % global_name)
            logger.error('Warning - Residual files remain in %s.fail' % pp_path)
            was_snatched = len(myDB.select('SELECT BookID FROM wanted WHERE BookID="%s"' % bookID))
            if was_snatched:
                controlValueDict = {"BookID": bookID}
                newValueDict = {"Status": "Failed", "NZBDate": now()}
                myDB.upsert("wanted", newValueDict, controlValueDict)
            # reset status so we try for a different version
            myDB.action('UPDATE books SET status = "Wanted" WHERE BookID="%s"' % bookID)
            try:
                os.rename(pp_path, pp_path + '.fail')
            except:
                logger.debug("Unable to rename %s" % pp_path)
    return False


def processExtras(myDB=None, dest_path=None, global_name=None, data=None):
    # given book data, handle calibre autoadd, book image, opf,
    # and update author and book counts
    authorname = data[0]['AuthorName']
    bookid = data[0]['BookID']
    bookname = data[0]['BookName']
    bookdesc = data[0]['BookDesc']
    bookisbn = data[0]['BookIsbn']
    bookimg = data[0]['BookImg']
    bookdate = data[0]['BookDate']
    booklang = data[0]['BookLang']
    bookpub = data[0]['BookPub']

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
    havebooks = myDB.action(
        'SELECT count("BookID") as counter FROM books WHERE AuthorName="%s" AND (Status="Have" OR Status="Open")' %
        authorname).fetchone()
    controlValueDict = {"AuthorName": authorname}
    newValueDict = {"HaveBooks": havebooks['counter']}
    countauthor = len(myDB.select('SELECT AuthorID FROM authors WHERE AuthorName="%s"' % authorname))
    if countauthor:
        myDB.upsert("authors", newValueDict, controlValueDict)


def processDestination(pp_path=None, dest_path=None, authorname=None, bookname=None, global_name=None):

    # check we got a book/magazine in the downloaded files, if not, return
    if bookname:
        booktype = 'book'
    else:
        booktype = 'mag'

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
        try:
            logger.debug('Importing %s into calibre library' % (global_name))
            # calibre is broken, ignores metadata.opf and book_name.opf
            # also ignores --title and --author as parameters
            # so we have to configure calibre to parse the filename for author/title
            # and rename the book to the format we want calibre to use
            for bookfile in os.listdir(pp_path):
                filename, extn = os.path.splitext(bookfile)
                # calibre does not like quotes in author names
                os.rename(os.path.join(pp_path, filename + extn), os.path.join(pp_path, global_name.replace('"','_') + extn))

            params =    [lazylibrarian.IMP_CALIBREDB,
                            'add',
                            #'--title="%s"' % bookname,
                            #'--author="%s"' % unaccented(authorname),
                            '-1',
                            '--with-library',
                            lazylibrarian.DESTINATION_DIR, pp_path
                        ]
            logger.debug(str(params))
            res = subprocess.check_output(params, stderr=subprocess.STDOUT)
            if res:
                logger.debug('%s reports: %s' % (lazylibrarian.IMP_CALIBREDB, unaccented_str(res)))
            # calibre does not like quotes in author names
            calibre_dir = os.path.join(lazylibrarian.DESTINATION_DIR, unaccented_str(authorname.replace('"','_')), '')
            if os.path.isdir(calibre_dir):
                imported = LibraryScan(calibre_dir)  # rescan authors directory so we get the new book in our database
            else:
                logger.error("Failed to locate calibre dir [%s]" % calibre_dir)
                imported = False
                #imported = LibraryScan(lazylibrarian.DESTINATION_DIR)  # may have to rescan whole library instead
            if not imported and not 'already exist' in res:
                return False
        except subprocess.CalledProcessError as e:
            logger.debug(params)
            logger.debug('calibredb import failed: %s' % e.output)
            return False
        except OSError as e:
            logger.debug('calibredb failed, %s' % e.strerror)
            return False

    else:
        # we are copying the files ourselves
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

        # ok, we've got a target directory, try to copy only the files we want, renaming them on the fly.
        # After the copy completes, delete source files if DESTINATION_COPY not set,
        # but don't delete source files if copy failed or if in root of download dir
        for fname in os.listdir(pp_path):
            if fname.lower().endswith(".jpg") or fname.lower().endswith(".opf") or \
                    is_valid_booktype(fname, booktype=booktype):
                logger.debug('Copying %s to directory %s' % (fname, dest_path))
                try:
                    shutil.copyfile(os.path.join(pp_path, fname), os.path.join(
                        dest_path, global_name + os.path.splitext(fname)[1]))
                except Exception as why:
                    logger.debug("Failed to copy file %s to %s, %s" % (
                        fname, dest_path, str(why)))
                    return False
            else:
                logger.debug('Ignoring unwanted file: %s' % fname)

    # calibre or ll copied the files we want, now delete source files if not in download root dir
    if not lazylibrarian.DESTINATION_COPY:
        if pp_path != lazylibrarian.DOWNLOAD_DIR:
            if os.path.isdir(pp_path):
                # calibre might have already deleted it
                try:
                    shutil.rmtree(pp_path)
                except Exception as why:
                    logger.debug("Unable to remove %s, %s" % (pp_path, str(why)))
                    return False
    return True


def processAutoAdd(src_path=None):
    # Called to copy the book files to an auto add directory for the likes of Calibre which can't do nested dirs
    autoadddir = lazylibrarian.IMP_AUTOADD
    logger.debug('AutoAdd - Attempt to copy from [%s] to [%s]' % (src_path, autoadddir))

    if not os.path.exists(autoadddir):
        logger.error('AutoAdd directory [%s] is missing or not set - cannot perform autoadd copy' % autoadddir)
        return False
    else:
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

    logger.info('Auto Add completed for [%s]' % dstname)
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
        logger.error('Error fetching cover from url: %s, %s' % (bookimg, e))


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
