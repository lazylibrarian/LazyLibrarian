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
import json
import lazylibrarian
from lazylibrarian import logger, database
from lazylibrarian.formatter import unaccented, getList
from lazylibrarian.importer import addAuthorNameToDB, search_for, import_book
from lazylibrarian.librarysync import find_book_in_db

# calibredb custom_columns
# calibredb add_custom_column label name bool
# calibredb remove_custom_column --force label
# calibredb set_custom label id value
# calibredb search "#label":"false"  # returns list of ids (slow)


def calibreReadList(col_read, col_toread):
    """ Get a list of all books in linked calibre library, including optional 'read' and 'toread' columns
        which could be per-user columns. If success, return list of dicts {"title": "", "id": 0, "authors": ""}
        If error, return error message (not a dict) """
    fieldlist = 'title,authors'
    if col_read:
        fieldlist += ',*' + col_read
    if col_toread:
        fieldlist += ',*' + col_toread
    res, err, rc = calibredb("list", "", ['--for-machine', '--fields', fieldlist])
    if rc:
        if res:
            return res
        return err
    else:
        # return json.loads(res)
        calibre_list = json.loads(res)
        return map_bookids(calibre_list, col_read, col_toread)


def map_bookids(calibre_list, col_read, col_toread):
    """ Get the lazylibrarian bookid for each read/toread calibre book so we can map our id to theirs
        Return list of dicts with added bookids """
    for item in calibre_list:
        if col_read and '*' + col_read in item or col_toread and '*' + col_toread in item:
            authorname, authorid, added = addAuthorNameToDB(item['authors'], refresh=False, addbooks=False)
            if authorname:
                bookid = find_book_in_db(authorname, item['title'])
                if not bookid:
                    searchterm = "%s <ll> %s" % (item['title'], authorname)
                    results = search_for(unaccented(searchterm))
                    if results:
                        result = results[0]
                        if result['author_fuzz'] > lazylibrarian.CONFIG['MATCH_RATIO'] \
                                and result['book_fuzz'] > lazylibrarian.CONFIG['MATCH_RATIO']:
                            logger.debug("Found (%s%% %s%%) %s: %s" % (result['author_fuzz'], result['book_fuzz'],
                                                                       result['authorname'], result['bookname']))
                            bookid = result['bookid']
                            import_book(bookid)
                if bookid:
                    item['BookID'] = bookid
                else:
                    logger.warn('Calibre Book [%s] by [%s] is not in lazylibrarian database' %
                                (item['title'], authorname))
            else:
                logger.warn('Calibre Author [%s] is not in lazylibrarian database' % (item['authors']))

    # Now check lazylibrarian read/toread in the calibre library, warn about missing ones
    # which might be books calibre doesn't have, or might be minor differences in author or title
    myDB = database.DBConnection()
    cmd = 'SELECT SyncList from sync WHERE Label=?'
    readlist = myDB.match(cmd, (col_read,))
    toreadlist = myDB.match(cmd, (col_toread,))

    for idlist in [readlist, toreadlist]:
        booklist = getList(idlist)
        for bookid in booklist:
            cmd = "SELECT AuthorID,BookName from books where BookID=?"
            book = myDB.match(cmd, (bookid,))
            if not book:
                logger.error('Error finding bookid %s' % bookid)
            else:
                cmd = "SELECT AuthorName from authors where AuthorID=?"
                author = myDB.match(cmd, (book['AuthorID'],))
                if not author:
                    logger.error('Error finding authorid %s' % book['AuthorID'])
                else:
                    match = False
                    for item in calibre_list:
                        if item['authors'] == author['AuthorName'] and item['title'] == book['BookName']:
                            if 'BookId' not in item:
                                item['BookID'] = str(bookid)
                            match = True
                            break
                    if not match:
                        logger.warn("No match for %s by %s in calibre database" %
                                    (book['BookName'], author['AuthorName']))
    logger.debug("BookID mapping complete")
    return calibre_list


def calibreTest():
    res, err, rc = calibredb('--version')
    if rc:
        msg = "calibredb communication failed: "
        if err:
            return msg + err
        return msg + res

    res = res.strip('\n')
    if '(calibre ' in res and res.endswith(')'):
        # extract calibredb version number
        res = res.split('(calibre ')[1]
        res = 'calibredb ok, version ' + res[:-1]
        # get a list of categories and counters from the database
        cats, err, rc = calibredb('list_categories', ['-i'])
        cnt = 0
        if rc:
            res = res + '\nDatabase READ Failed'
        else:
            res = res + '\nDatabase: ' + err
            for entry in cats.split('\n'):
                try:
                    words = entry.split()
                    if words[-1].isdigit():
                        cnt += int(words[-1])
                except IndexError:
                    cnt += 0
        if cnt:
            res = res + '\nDatabase READ ok'
            wrt, err, rc = calibredb('add', ['--authors', 'LazyLibrarian', '--title', 'dummy', '--empty'], [])
            if 'Added book ids' not in wrt:
                res = res + '\nDatabase WRITE Failed'
            else:
                calibre_id = wrt.split("book ids: ", 1)[1].split("\n", 1)[0]
                rmv, err, rc = calibredb('remove', ['--permanent', calibre_id], [])
                if not rc:
                    res = res + '\nDatabase WRITE ok'
                else:
                    res = res + '\nDatabase WRITE2 Failed: '
        else:
            res = res + '\nDatabase READ Failed or database is empty'
    else:
        res = 'calibredb Failed'
    return res


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
        params.extend(['--with-library', '%s' % dest_url])
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
        dest_url = lazylibrarian.DIRECTORY('eBook')
        params.extend(['--with-library', dest_url])
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
            rc = 1
    if rc:
        return res, err, rc
    else:
        return res, dest_url, 0
