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


import os
import traceback
import platform
import subprocess
import json

import lazylibrarian
from lazylibrarian import logger, database
from lazylibrarian.bookwork import getBookWork
from lazylibrarian.formatter import plural, makeUnicode, makeBytestr, safe_unicode, check_int, md5_utf8
from lazylibrarian.common import safe_copy, setperm
from lazylibrarian.cache import cache_img, fetchURL
from shutil import copyfile
from lib.six import PY2, text_type
# noinspection PyUnresolvedReferences
from lib.six.moves.urllib_parse import quote_plus

try:
    import zipfile
except ImportError:
    if PY2:
        import lib.zipfile as zipfile
    else:
        import lib3.zipfile as zipfile


def getAuthorImages():
    """ Try to get an author image for all authors without one"""
    myDB = database.DBConnection()
    cmd = 'select AuthorID, AuthorName from authors where (AuthorImg like "%nophoto%" or AuthorImg is null)'
    cmd += ' and Manual is not "1"'
    authors = myDB.select(cmd)
    if authors:
        logger.info('Checking images for %s author%s' % (len(authors), plural(len(authors))))
        counter = 0
        for author in authors:
            authorid = author['AuthorID']
            imagelink = getAuthorImage(authorid)
            newValueDict = {}
            if not imagelink:
                logger.debug('No image found for %s' % author['AuthorName'])
                newValueDict = {"AuthorImg": 'images/nophoto.png'}
            elif 'nophoto' not in imagelink:
                logger.debug('Updating %s image to %s' % (author['AuthorName'], imagelink))
                newValueDict = {"AuthorImg": imagelink}

            if newValueDict:
                counter += 1
                controlValueDict = {"AuthorID": authorid}
                myDB.upsert("authors", newValueDict, controlValueDict)

        msg = 'Updated %s image%s' % (counter, plural(counter))
        logger.info('Author Image check complete: ' + msg)
    else:
        msg = 'No missing author images'
        logger.debug(msg)
    return msg


def getBookCovers():
    """ Try to get a cover image for all books """

    myDB = database.DBConnection()
    books = myDB.select('select BookID,BookImg from books where BookImg like "%nocover%" and Manual is not "1"')
    if books:
        logger.info('Checking covers for %s book%s' % (len(books), plural(len(books))))
        counter = 0
        for book in books:
            bookid = book['BookID']
            coverlink = getBookCover(bookid)
            if coverlink and "nocover" not in coverlink:
                controlValueDict = {"BookID": bookid}
                newValueDict = {"BookImg": coverlink}
                myDB.upsert("books", newValueDict, controlValueDict)
                counter += 1
        msg = 'Updated %s cover%s' % (counter, plural(counter))
        logger.info('Cover check complete: ' + msg)
    else:
        msg = 'No missing book covers'
        logger.debug(msg)
    return msg


def getBookCover(bookID=None, src=None):
    """ Return link to a local file containing a book cover image for a bookid, and which source used.
        Try 1. Local file cached from goodreads/googlebooks when book was imported
            2. cover.jpg if we have the book
            3. LibraryThing cover image (if you have a dev key)
            4. LibraryThing whatwork (if available)
            5. Goodreads search (if book was imported from goodreads)
            6. OpenLibrary image
            7. Google isbn search (if google has a link to book for sale)
            8. Google images search (if lazylibrarian config allows)

        src = cache, cover, goodreads, librarything, whatwork, googleisbn, openlibrary, googleimage
        Return None if no cover available. """
    if not bookID:
        logger.error("getBookCover- No bookID")
        return None, src

    if not src:
        src = ''
    logger.debug("Getting %s cover for %s" % (src, bookID))
    # noinspection PyBroadException
    try:
        cachedir = lazylibrarian.CACHEDIR
        coverfile = os.path.join(cachedir, "book", bookID + '.jpg')
        if not src or src == 'cache' or src == 'current':
            if os.path.isfile(coverfile):  # use cached image if there is one
                lazylibrarian.CACHE_HIT = int(lazylibrarian.CACHE_HIT) + 1
                coverlink = 'cache/book/' + bookID + '.jpg'
                return coverlink, 'cache'
            elif src:
                lazylibrarian.CACHE_MISS = int(lazylibrarian.CACHE_MISS) + 1
                return None, src

        myDB = database.DBConnection()
        if not src or src == 'cover':
            item = myDB.match('select BookFile from books where bookID=?', (bookID,))
            if item:
                bookfile = item['BookFile']
                if bookfile:  # we may have a cover.jpg in the same folder
                    bookdir = os.path.dirname(bookfile)
                    coverimg = os.path.join(bookdir, "cover.jpg")
                    if os.path.isfile(coverimg):
                        if src:
                            coverfile = os.path.join(cachedir, "book", bookID + '_cover.jpg')
                            coverlink = 'cache/book/' + bookID + '_cover.jpg'
                            logger.debug("Caching cover.jpg for %s" % bookID)
                        else:
                            coverlink = 'cache/book/' + bookID + '.jpg'
                            logger.debug("Caching cover.jpg for %s" % coverfile)
                        _ = safe_copy(coverimg, coverfile)
                        return coverlink, src
            if src:
                logger.debug('No cover.jpg found for %s' % bookID)
                return None, src

        # see if librarything  has a cover
        if not src or src == 'librarything':
            if lazylibrarian.CONFIG['LT_DEVKEY']:
                cmd = 'select BookISBN from books where bookID=?'
                item = myDB.match(cmd, (bookID,))
                if item and item['BookISBN']:
                    img = 'https://www.librarything.com/devkey/%s/large/isbn/%s' % (
                           lazylibrarian.CONFIG['LT_DEVKEY'], item['BookISBN'])
                    if src:
                        coverlink, success, _ = cache_img("book", bookID + '_lt', img)
                    else:
                        coverlink, success, _ = cache_img("book", bookID, img, refresh=True)

                    # if librarything has no image they return a 1x1 gif
                    data = ''
                    coverfile = os.path.join(lazylibrarian.DATADIR, coverlink)
                    if os.path.isfile(coverfile):
                        with open(coverfile, 'rb') as f:
                            data = f.read()
                    if len(data) < 50:
                        logger.debug('Got an empty librarything image for %s [%s]' % (bookID, coverlink))
                    elif success:
                        logger.debug("Caching librarything cover for %s" % bookID)
                        return coverlink, 'librarything'
                    else:
                        logger.debug('Failed to cache image for %s [%s]' % (img, coverlink))
                else:
                    logger.debug("No isbn for %s" % bookID)
            if src:
                return None, src

        # see if librarything workpage has a cover
        if not src or src == 'whatwork':
            work = getBookWork(bookID, "Cover")
            if work:
                try:
                    img = work.split('workCoverImage')[1].split('="')[1].split('"')[0]
                    if img and img.startswith('http'):
                        if src:
                            coverlink, success, _ = cache_img("book", bookID + '_ww', img)
                        else:
                            coverlink, success, _ = cache_img("book", bookID, img, refresh=True)

                        # if librarything has no image they return a 1x1 gif
                        data = ''
                        coverfile = os.path.join(lazylibrarian.DATADIR, coverlink)
                        if os.path.isfile(coverfile):
                            with open(coverfile, 'rb') as f:
                                data = f.read()
                        if len(data) < 50:
                            logger.debug('Got an empty whatwork image for %s [%s]' % (bookID, coverlink))
                        elif success:
                            logger.debug("Caching whatwork cover for %s" % bookID)
                            return coverlink, 'whatwork'
                        else:
                            logger.debug('Failed to cache image for %s [%s]' % (img, coverlink))
                    else:
                        logger.debug("No image found in work page for %s" % bookID)
                except IndexError:
                    logger.debug('workCoverImage not found in work page for %s' % bookID)

                try:
                    img = work.split('og:image')[1].split('="')[1].split('"')[0]
                    if img and img.startswith('http'):
                        if src:
                            coverlink, success, _ = cache_img("book", bookID + '_ww', img)
                        else:
                            coverlink, success, _ = cache_img("book", bookID, img, refresh=True)

                        # if librarything has no image they return a 1x1 gif
                        data = ''
                        coverfile = os.path.join(lazylibrarian.DATADIR, coverlink)
                        if os.path.isfile(coverfile):
                            with open(coverfile, 'rb') as f:
                                data = f.read()
                        if len(data) < 50:
                            logger.debug('Got an empty whatwork image for %s [%s]' % (bookID, coverlink))
                        if success:
                            logger.debug("Caching whatwork cover for %s" % bookID)
                            return coverlink, 'whatwork'
                        else:
                            logger.debug('Failed to cache image for %s [%s]' % (img, coverlink))
                    else:
                        logger.debug("No image found in work page for %s" % bookID)
                except IndexError:
                    logger.debug('og:image not found in work page for %s' % bookID)
            else:
                logger.debug('No work page for %s' % bookID)
            if src:
                return None, src

        cmd = 'select BookName,AuthorName,BookLink,BookISBN from books,authors where bookID=?'
        cmd += ' and books.AuthorID = authors.AuthorID'
        item = myDB.match(cmd, (bookID,))
        safeparams = ''
        booklink = ''
        if item:
            title = safe_unicode(item['BookName'])
            author = safe_unicode(item['AuthorName'])
            if PY2:
                title = title.encode(lazylibrarian.SYS_ENCODING)
                author = author.encode(lazylibrarian.SYS_ENCODING)
            booklink = item['BookLink']
            safeparams = quote_plus("%s %s" % (author, title))

        # try to get a cover from goodreads
        if not src or src == 'goodreads':
            if booklink and 'goodreads' in booklink:
                # if the bookID is a goodreads one, we can call https://www.goodreads.com/book/show/{bookID}
                # and scrape the page for og:image
                # <meta property="og:image" content="https://i.gr-assets.com/images/S/photo.goodreads.com/books/
                # 1388267702i/16304._UY475_SS475_.jpg"/>
                # to get the cover
                result, success = fetchURL(booklink)
                if success:
                    try:
                        img = result.split('id="coverImage"')[1].split('src="')[1].split('"')[0]
                    except IndexError:
                        try:
                            img = result.split('og:image')[1].split('="')[1].split('"')[0]
                        except IndexError:
                            img = None
                    if img and img.startswith('http') and 'nocover' not in img and 'nophoto' not in img:
                        if src == 'goodreads':
                            coverlink, success, _ = cache_img("book", bookID + '_gr', img)
                        else:
                            coverlink, success, _ = cache_img("book", bookID, img, refresh=True)

                        data = ''
                        coverfile = os.path.join(lazylibrarian.DATADIR, coverlink)
                        if os.path.isfile(coverfile):
                            with open(coverfile, 'rb') as f:
                                data = f.read()
                        if len(data) < 50:
                            logger.debug('Got an empty goodreads image for %s [%s]' % (bookID, coverlink))
                        elif success:
                            logger.debug("Caching goodreads cover for %s %s" % (item['AuthorName'], item['BookName']))
                            return coverlink, 'goodreads'
                        else:
                            logger.debug("Error getting goodreads image for %s, [%s]" % (img, coverlink))
                    else:
                        logger.debug("No image found in goodreads page for %s" % bookID)
                else:
                    logger.debug("Error getting goodreads page %s, [%s]" % (booklink, result))
            if src:
                return None, src

        # try to get a cover from openlibrary
        if not src or src == 'openlibrary':
            if item['BookISBN']:
                baseurl = 'https://openlibrary.org/api/books?format=json&jscmd=data&bibkeys=ISBN:'
                result, success = fetchURL(baseurl + item['BookISBN'])
                if success:
                    try:
                        source = json.loads(result)  # type: dict
                    except Exception as e:
                        logger.debug("OpenLibrary json error: %s" % e)
                        source = []

                    img = ''
                    if source:
                        # noinspection PyUnresolvedReferences
                        k = source.keys()[0]
                        try:
                            img = source[k]['cover']['medium']
                        except KeyError:
                            try:
                                img = source[k]['cover']['large']
                            except KeyError:
                                logger.debug("No openlibrary image for %s" % item['BookISBN'])

                    if img and img.startswith('http') and 'nocover' not in img and 'nophoto' not in img:
                        if src == 'openlibrary':
                            coverlink, success, _ = cache_img("book", bookID + '_ol', img)
                        else:
                            coverlink, success, _ = cache_img("book", bookID, img, refresh=True)

                        data = ''
                        coverfile = os.path.join(lazylibrarian.DATADIR, coverlink)
                        if os.path.isfile(coverfile):
                            with open(coverfile, 'rb') as f:
                                data = f.read()
                        if len(data) < 50:
                            logger.debug('Got an empty openlibrary image for %s [%s]' % (bookID, coverlink))
                        elif success:
                            logger.debug("Caching openlibrary cover for %s %s" % (item['AuthorName'], item['BookName']))
                            return coverlink, 'openlibrary'
                else:
                    logger.debug("OpenLibrary error: %s" % result)
            if src:
                return None, src

        if not src or src == 'googleisbn':
            # try a google isbn page search...
            # there is no image returned if google doesn't have a link for buying the book
            if safeparams:
                URL = "http://www.google.com/search?q=ISBN+" + safeparams
                result, success = fetchURL(URL)
                if success:
                    try:
                        img = result.split('imgurl=')[1].split('&imgrefurl')[0]
                    except IndexError:
                        try:
                            img = result.split('img src="')[1].split('"')[0]
                        except IndexError:
                            img = None

                    if img and img.startswith('http'):
                        if src:
                            coverlink, success, _ = cache_img("book", bookID + '_gi', img)
                        else:
                            coverlink, success, _ = cache_img("book", bookID, img, refresh=True)

                        data = ''
                        coverfile = os.path.join(lazylibrarian.DATADIR, coverlink)
                        if os.path.isfile(coverfile):
                            with open(coverfile, 'rb') as f:
                                data = f.read()
                        if len(data) < 50:
                            logger.debug('Got an empty google image for %s [%s]' % (bookID, coverlink))
                        elif success:
                            logger.debug("Caching google isbn cover for %s %s" %
                                         (item['AuthorName'], item['BookName']))
                            return coverlink, 'google isbn'
                        else:
                            logger.debug("Error caching google image %s, [%s]" % (img, coverlink))
                    else:
                        logger.debug("No image found in google isbn page for %s" % bookID)
                else:
                    logger.debug("Failed to fetch url from google")
            else:
                logger.debug("No parameters for google isbn search for %s" % bookID)
            if src:
                return None, src

        if src == 'googleimage' or not src and lazylibrarian.CONFIG['IMP_GOOGLEIMAGE']:
            # try a google image search...
            # tbm=isch      search images
            # tbs=isz:l     large images
            # ift:jpg       jpeg file type
            if safeparams:
                URL = "https://www.google.com/search?tbm=isch&tbs=isz:l,ift:jpg&as_q=" + safeparams + "+ebook"
                img = None
                result, success = fetchURL(URL)
                if success:
                    try:
                        img = result.split('url?q=')[1].split('">')[1].split('src="')[1].split('"')[0]
                    except IndexError:
                        img = None

                if img and img.startswith('http'):
                    if src:
                        coverlink, success, _ = cache_img("book", bookID + '_gb', img)
                    else:
                        coverlink, success, _ = cache_img("book", bookID, img, refresh=True)

                    data = ''
                    coverfile = os.path.join(lazylibrarian.DATADIR, coverlink)
                    if os.path.isfile(coverfile):
                        with open(coverfile, 'rb') as f:
                            data = f.read()
                    if len(data) < 50:
                        logger.debug('Got an empty goodreads image for %s [%s]' % (bookID, coverlink))
                    elif success:
                        logger.debug("Caching google search cover for %s %s" %
                                     (item['AuthorName'], item['BookName']))
                        return coverlink, 'google image'
                    else:
                        logger.debug("Error getting google image %s, [%s]" % (img, coverlink))
                else:
                    logger.debug("No image found in google page for %s" % bookID)
            else:
                logger.debug("No parameters for google image search for %s" % bookID)
            if src:
                return None, src

        logger.debug("No image found from any configured source")
        return None, src
    except Exception:
        logger.error('Unhandled exception in getBookCover: %s' % traceback.format_exc())
    return None, src


def getAuthorImage(authorid=None):
    # tbm=isch      search images
    # tbs=ift:jpg  jpeg file type
    if not authorid:
        logger.error("getAuthorImage: No authorid")
        return None

    cachedir = lazylibrarian.CACHEDIR
    coverfile = os.path.join(cachedir, "author", authorid + '.jpg')

    if os.path.isfile(coverfile):  # use cached image if there is one
        lazylibrarian.CACHE_HIT = int(lazylibrarian.CACHE_HIT) + 1
        logger.debug("getAuthorImage: Returning Cached response for %s" % coverfile)
        coverlink = 'cache/author/' + authorid + '.jpg'
        return coverlink

    lazylibrarian.CACHE_MISS = int(lazylibrarian.CACHE_MISS) + 1
    myDB = database.DBConnection()
    author = myDB.match('select AuthorName from authors where AuthorID=?', (authorid,))
    if author:
        authorname = safe_unicode(author['AuthorName'])
        if PY2:
            authorname = authorname.encode(lazylibrarian.SYS_ENCODING)
        safeparams = quote_plus("author %s" % authorname)
        URL = "https://www.google.com/search?tbm=isch&tbs=ift:jpg,itp:face&as_q=" + safeparams + 'author'
        result, success = fetchURL(URL)
        if success:
            try:
                img = result.split('url?q=')[1].split('">')[1].split('src="')[1].split('"')[0]
            except IndexError:
                img = None
            if img and img.startswith('http'):
                coverlink, success, was_in_cache = cache_img("author", authorid, img)
                if success:
                    if was_in_cache:
                        logger.debug("Returning cached google image for %s" % authorname)
                    else:
                        logger.debug("Cached google image for %s" % authorname)
                    return coverlink
                else:
                    logger.debug("Error getting google image %s, [%s]" % (img, coverlink))
            else:
                logger.debug("No image found in google page for %s" % authorname)
        else:
            logger.debug("Error getting google page for %s, [%s]" % (safeparams, result))
    else:
        logger.debug("No author found for %s" % authorid)
    return None


def createMagCovers(refresh=False):
    if not lazylibrarian.CONFIG['IMP_MAGCOVER']:
        logger.info('Cover creation is disabled in config')
        return
    myDB = database.DBConnection()
    #  <> '' ignores empty string or NULL
    issues = myDB.select("SELECT IssueFile from issues WHERE IssueFile <> ''")
    if refresh:
        logger.info("Creating covers for %s issue%s" % (len(issues), plural(len(issues))))
    else:
        logger.info("Checking covers for %s issue%s" % (len(issues), plural(len(issues))))
    cnt = 0
    for item in issues:
        try:
            createMagCover(item['IssueFile'], refresh=refresh)
            cnt += 1
        except Exception as why:
            logger.warn('Unable to create cover for %s, %s %s' % (item['IssueFile'], type(why).__name__, str(why)))
    logger.info("Cover creation completed")
    if refresh:
        return "Created covers for %s issue%s" % (cnt, plural(cnt))
    return "Checked covers for %s issue%s" % (cnt, plural(cnt))


def createMagCover(issuefile=None, refresh=False, pagenum=1):
    if not lazylibrarian.CONFIG['IMP_MAGCOVER']:
        return 'unwanted'
    if issuefile is None or not os.path.isfile(issuefile):
        logger.debug('No issuefile %s' % issuefile)
        return 'failed'

    base, extn = os.path.splitext(issuefile)
    if not extn:
        logger.debug('Unable to create cover for %s, no extension?' % issuefile)
        return 'failed'

    coverfile = base + '.jpg'

    if os.path.isfile(coverfile):
        if refresh:
            os.remove(coverfile)
        else:
            logger.debug('Cover for %s exists' % issuefile)
            return  'exists'  # quit if cover already exists and we didn't want to refresh

    logger.debug('Creating cover for %s' % issuefile)
    data = ''  # result from unzip or unrar
    extn = extn.lower()
    if extn in ['.cbz', '.epub']:
        try:
            data = zipfile.ZipFile(issuefile)
        except Exception as why:
            logger.error("Failed to read zip file %s, %s %s" % (issuefile, type(why).__name__, str(why)))
            data = ''
    elif extn in ['.cbr']:
        try:
            # unrar will complain if the library isn't installed, needs to be compiled separately
            # see https://pypi.python.org/pypi/unrar/ for instructions
            # Download source from http://www.rarlab.com/rar_add.htm
            # note we need LIBRARY SOURCE not a binary package
            # make lib; sudo make install-lib; sudo ldconfig
            # lib.unrar should then be able to find libunrar.so
            from lib.unrar import rarfile
            data = rarfile.RarFile(issuefile)
        except Exception as why:
            logger.error("Failed to read rar file %s, %s %s" % (issuefile, type(why).__name__, str(why)))
            data = ''
    if data:
        img = None
        try:
            for member in data.namelist():
                memlow = member.lower()
                if '-00.' in memlow or '000.' in memlow or 'cover.' in memlow:
                    if memlow.endswith('.jpg') or memlow.endswith('.jpeg'):
                        img = data.read(member)
                        break
            if img:
                with open(coverfile, 'wb') as f:
                    if PY2:
                        f.write(img)
                    else:
                        f.write(img.encode())
                return 'ok'
            else:
                logger.debug("Failed to find image in %s" % issuefile)
        except Exception as why:
            logger.error("Failed to extract image from %s, %s %s" % (issuefile, type(why).__name__, str(why)))

    elif extn == '.pdf':
        generator = ""
        if len(lazylibrarian.CONFIG['IMP_CONVERT']):  # allow external convert to override libraries
            generator = "external program: %s" % lazylibrarian.CONFIG['IMP_CONVERT']
            if "gsconvert.py" in lazylibrarian.CONFIG['IMP_CONVERT']:
                msg = "Use of gsconvert.py is deprecated, equivalent functionality is now built in. "
                msg += "Support for gsconvert.py may be removed in a future release. See wiki for details."
                logger.warn(msg)
            converter = lazylibrarian.CONFIG['IMP_CONVERT']
            postfix = ''
            # if not os.path.isfile(converter):  # full path given, or just program_name?
            #     converter = os.path.join(os.getcwd(), lazylibrarian.CONFIG['IMP_CONVERT'])
            if 'convert' in converter and 'gs' not in converter:
                # tell imagemagick to only convert first page
                postfix = '[0]'
            try:
                params = [converter, '%s%s' % (issuefile, postfix), '%s' % coverfile]
                res = subprocess.check_output(params, stderr=subprocess.STDOUT)
                res = makeUnicode(res).strip()
                if res:
                    logger.debug('%s reports: %s' % (lazylibrarian.CONFIG['IMP_CONVERT'], res))
            except Exception as e:
                # logger.debug(params)
                logger.warn('External "convert" failed %s %s' % (type(e).__name__, str(e)))

        elif platform.system() == "Windows":
            GS = os.path.join(os.getcwd(), "gswin64c.exe")
            generator = "local gswin64c"
            if not os.path.isfile(GS):
                GS = os.path.join(os.getcwd(), "gswin32c.exe")
                generator = "local gswin32c"
            if not os.path.isfile(GS):
                params = ["where", "gswin64c"]
                try:
                    GS = subprocess.check_output(params, stderr=subprocess.STDOUT)
                    GS = makeUnicode(GS).strip()
                    generator = "gswin64c"
                except Exception as e:
                    logger.debug("where gswin64c failed: %s %s" % (type(e).__name__, str(e)))
            if not os.path.isfile(GS):
                params = ["where", "gswin32c"]
                try:
                    GS = subprocess.check_output(params, stderr=subprocess.STDOUT)
                    GS = makeUnicode(GS).strip()
                    generator = "gswin32c"
                except Exception as e:
                    logger.debug("where gswin32c failed: %s %s" % (type(e).__name__, str(e)))
            if not os.path.isfile(GS):
                logger.debug("No gswin found")
                generator = "(no windows ghostscript found)"
            else:
                # noinspection PyBroadException
                try:
                    params = [GS, "--version"]
                    res = subprocess.check_output(params, stderr=subprocess.STDOUT)
                    res = makeUnicode(res).strip()
                    logger.debug("Found %s [%s] version %s" % (generator, GS, res))
                    generator = "%s version %s" % (generator, res)
                    issuefile = issuefile.split('[')[0]
                    params = [GS, "-sDEVICE=jpeg", "-dNOPAUSE", "-dBATCH", "-dSAFER",
                              "-dFirstPage=%d"  % check_int(pagenum, 1),
                              "-dLastPage=%d" % check_int(pagenum, 1),
                              "-dUseCropBox", "-sOutputFile=%s" % coverfile, issuefile]

                    res = subprocess.check_output(params, stderr=subprocess.STDOUT)
                    res = makeUnicode(res).strip()

                    if not os.path.isfile(coverfile):
                        logger.debug("Failed to create jpg: %s" % res)
                except Exception:  # as why:
                    logger.warn("Failed to create jpg for %s" % issuefile)
                    logger.debug('Exception in gswin create_cover: %s' % traceback.format_exc())
        else:  # not windows
            try:
                # noinspection PyUnresolvedReferences
                from wand.image import Image
                interface = "wand"
            except ImportError:
                try:
                    # No PythonMagick in python3
                    # noinspection PyUnresolvedReferences
                    import PythonMagick
                    interface = "pythonmagick"
                except ImportError:
                    interface = ""
            try:
                if interface == 'wand':
                    generator = "wand interface"
                    with Image(filename=issuefile + '[' + str(check_int(pagenum, 1) - 1) + ']') as img:
                        img.save(filename=coverfile)

                elif interface == 'pythonmagick':
                    generator = "pythonmagick interface"
                    img = PythonMagick.Image()
                    # PythonMagick requires filenames to be bytestr, not unicode
                    if type(issuefile) is text_type:
                        issuefile = makeBytestr(issuefile)
                    if type(coverfile) is text_type:
                        coverfile = makeBytestr(coverfile)
                    img.read(issuefile + '[' + str(check_int(pagenum, 1) - 1) + ']')
                    img.write(coverfile)

                else:
                    GS = os.path.join(os.getcwd(), "gs")
                    generator = "local gs"
                    if not os.path.isfile(GS):
                        GS = ""
                        params = ["which", "gs"]
                        try:
                            GS = subprocess.check_output(params, stderr=subprocess.STDOUT)
                            GS = makeUnicode(GS).strip()
                            generator = GS
                        except Exception as e:
                            logger.debug("which gs failed: %s %s" % (type(e).__name__, str(e)))
                        if not os.path.isfile(GS):
                            logger.debug("Cannot find gs")
                            generator = "(no gs found)"
                        else:
                            params = [GS, "--version"]
                            res = subprocess.check_output(params, stderr=subprocess.STDOUT)
                            res = makeUnicode(res).strip()
                            logger.debug("Found gs [%s] version %s" % (GS, res))
                            generator = "%s version %s" % (generator, res)
                            issuefile = issuefile.split('[')[0]
                            params = [GS, "-sDEVICE=jpeg", "-dNOPAUSE", "-dBATCH", "-dSAFER",
                                      "-dFirstPage=%d" % check_int(pagenum, 1),
                                      "-dLastPage=%d" % check_int(pagenum, 1) ,
                                      "-dUseCropBox", "-sOutputFile=%s" % coverfile, issuefile]
                            res = subprocess.check_output(params, stderr=subprocess.STDOUT)
                            res = makeUnicode(res).strip()
                            if not os.path.isfile(coverfile):
                                logger.debug("Failed to create jpg: %s" % res)
            except Exception as e:
                logger.warn("Unable to create cover for %s using %s %s" % (issuefile, type(e).__name__, generator))
                logger.debug('Exception in create_cover: %s' % traceback.format_exc())

        if os.path.isfile(coverfile):
            setperm(coverfile)
            logger.debug("Created cover (page %d) for %s using %s" % (check_int(pagenum, 1), issuefile, generator))
            myhash = md5_utf8(coverfile)
            hashname = os.path.join(lazylibrarian.CACHEDIR, 'magazine', '%s.jpg' % myhash)
            copyfile(coverfile, hashname)
            setperm(hashname)
            return hashname

    # if not recognised extension or cover creation failed
    try:
        coverfile = safe_copy(os.path.join(lazylibrarian.PROG_DIR, 'data/images/nocover.jpg'), coverfile)
        setperm(coverfile)
    except Exception as why:
        logger.error("Failed to copy nocover file, %s %s" % (type(why).__name__, str(why)))
    return 'Failed'
