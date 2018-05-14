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

import datetime
import os
import re
import traceback
from hashlib import sha1

import lazylibrarian
from lib.six import PY2

from lazylibrarian import database, logger
from lazylibrarian.common import safe_move
from lazylibrarian.formatter import getList, is_valid_booktype, plural, makeUnicode, makeBytestr, \
    replace_all, check_year
from lazylibrarian.images import createMagCover


def create_id(issuename=None):
    hashID = sha1(makeBytestr(issuename)).hexdigest()
    # logger.debug('Issue %s Hash: %s' % (issuename, hashID))
    return hashID


def magazineScan(title=None):
    lazylibrarian.MAG_UPDATE = 1
    onetitle = title

    # noinspection PyBroadException
    try:
        myDB = database.DBConnection()

        mag_path = lazylibrarian.CONFIG['MAG_DEST_FOLDER']
        mag_path = mag_path.split('$')[0]

        if lazylibrarian.CONFIG['MAG_RELATIVE']:
            if mag_path[0] not in '._':
                mag_path = '_' + mag_path
            mag_path = os.path.join(lazylibrarian.DIRECTORY('eBook'), mag_path)

        if PY2:
            mag_path = mag_path.encode(lazylibrarian.SYS_ENCODING)

        if lazylibrarian.CONFIG['FULL_SCAN'] and not onetitle:
            mags = myDB.select('select * from Issues')
            # check all the issues are still there, delete entry if not
            for mag in mags:
                title = mag['Title']
                issuedate = mag['IssueDate']
                issuefile = mag['IssueFile']

                if issuefile and not os.path.isfile(issuefile):
                    myDB.action('DELETE from Issues where issuefile=?', (issuefile,))
                    logger.info('Issue %s - %s deleted as not found on disk' % (title, issuedate))
                    controlValueDict = {"Title": title}
                    newValueDict = {
                        "LastAcquired": None,  # clear magazine dates
                        "IssueDate": None,  # we will fill them in again later
                        "LatestCover": None,
                        "IssueStatus": "Skipped"  # assume there are no issues now
                    }
                    myDB.upsert("magazines", newValueDict, controlValueDict)
                    logger.debug('Magazine %s details reset' % title)

            mags = myDB.select('SELECT * from magazines')
            # now check the magazine titles and delete any with no issues
            for mag in mags:
                title = mag['Title']
                count = myDB.select('SELECT COUNT(Title) as counter FROM issues WHERE Title=?', (title,))
                issues = count[0]['counter']
                if not issues:
                    logger.debug('Magazine %s deleted as no issues found' % title)
                    myDB.action('DELETE from magazines WHERE Title=?', (title,))

        if onetitle:
            match = myDB.match('SELECT LatestCover from magazines where Title=?', (onetitle,))
            if match:
                mag_path = os.path.dirname(match['LatestCover'])

        logger.info(' Checking [%s] for magazines' % mag_path)

        matchString = ''
        for char in lazylibrarian.CONFIG['MAG_DEST_FILE']:
            matchString = matchString + '\\' + char
        # massage the MAG_DEST_FILE config parameter into something we can use
        # with regular expression matching
        booktypes = ''
        count = -1
        booktype_list = getList(lazylibrarian.CONFIG['MAG_TYPE'])
        for book_type in booktype_list:
            count += 1
            if count == 0:
                booktypes = book_type
            else:
                booktypes = booktypes + '|' + book_type
        match = matchString.replace("\\$\\I\\s\\s\\u\\e\\D\\a\\t\\e", "(?P<issuedate>.*?)").replace(
            "\\$\\T\\i\\t\\l\\e", "(?P<title>.*?)") + '\.[' + booktypes + ']'
        title_pattern = re.compile(match, re.VERBOSE)
        match = matchString.replace("\\$\\I\\s\\s\\u\\e\\D\\a\\t\\e", "(?P<issuedate>.*?)").replace(
            "\\$\\T\\i\\t\\l\\e", "") + '\.[' + booktypes + ']'
        date_pattern = re.compile(match, re.VERBOSE)

        # try to ensure startdir is str as os.walk can fail if it tries to convert a subdir or file
        # to utf-8 and fails (eg scandinavian characters in ascii 8bit)
        for rootdir, dirnames, filenames in os.walk(makeBytestr(mag_path)):
            rootdir = makeUnicode(rootdir)
            filenames = [makeUnicode(item) for item in filenames]
            for fname in filenames:
                # maybe not all magazines will be pdf?
                if is_valid_booktype(fname, booktype='mag'):
                    issuedate = ''
                    # noinspection PyBroadException
                    try:
                        match = title_pattern.match(fname)
                        if match:
                            title = match.group("title")
                            issuedate = match.group("issuedate")
                            if lazylibrarian.LOGLEVEL & lazylibrarian.log_magdates:
                                logger.debug("Title pattern [%s][%s]" % (title, issuedate))
                            match = True
                        else:
                            logger.debug("Title pattern match failed for [%s]" % fname)
                    except Exception:
                        match = False

                    if not match:
                        # noinspection PyBroadException
                        try:
                            match = date_pattern.match(fname)
                            if match:
                                issuedate = match.group("issuedate")
                                title = os.path.basename(rootdir)
                                if lazylibrarian.LOGLEVEL & lazylibrarian.log_magdates:
                                    logger.debug("Date pattern [%s][%s]" % (title, issuedate))
                                match = True
                            else:
                                logger.debug("Date pattern match failed for [%s]" % fname)
                        except Exception:
                            match = False

                    if not match:
                        title = os.path.basename(rootdir)
                        issuedate = ''

                    dic = {'.': ' ', '-': ' ', '/': ' ', '+': ' ', '_': ' ', '(': '', ')': '', '[': ' ', ']': ' ',
                           '#': '# '}
                    if issuedate:
                        exploded = replace_all(issuedate, dic).strip()
                        # remove extra spaces if they're in a row
                        exploded = " ".join(exploded.split())
                        exploded = exploded.split(' ')
                        regex_pass, issuedate, year = lazylibrarian.searchmag.get_issue_date(exploded)
                        if lazylibrarian.LOGLEVEL & lazylibrarian.log_magdates:
                            logger.debug("Date regex [%s][%s][%s]" % (regex_pass, issuedate, year))
                        if not regex_pass:
                            issuedate = ''

                    if not issuedate:
                        exploded = replace_all(fname, dic).strip()
                        exploded = " ".join(exploded.split())
                        exploded = exploded.split(' ')
                        regex_pass, issuedate, year = lazylibrarian.searchmag.get_issue_date(exploded)
                        if lazylibrarian.LOGLEVEL & lazylibrarian.log_magdates:
                            logger.debug("File regex [%s][%s][%s]" % (regex_pass, issuedate, year))
                        if not regex_pass:
                            issuedate = ''

                    if not issuedate:
                        logger.warn("Invalid name format for [%s]" % fname)
                        continue

                    issuefile = os.path.join(rootdir, fname)  # full path to issue.pdf
                    mtime = os.path.getmtime(issuefile)
                    iss_acquired = datetime.date.isoformat(datetime.date.fromtimestamp(mtime))

                    if lazylibrarian.CONFIG['MAG_RENAME']:
                        filedate = issuedate
                        if issuedate and issuedate.isdigit():
                            if len(issuedate) == 8:
                                if check_year(issuedate[:4]):
                                    filedate = 'Issue %d %s' % (int(issuedate[4:]), issuedate[:4])
                                else:
                                    filedate = 'Vol %d Iss %d' % (int(issuedate[:4]), int(issuedate[4:]))
                            elif len(issuedate) == 12:
                                filedate = 'Vol %d Iss %d %s' % (int(issuedate[4:8]), int(issuedate[8:]),
                                                                 issuedate[:4])

                        extn = os.path.splitext(fname)[1]
                        newfname = lazylibrarian.CONFIG['MAG_DEST_FILE'].replace('$Title', title).replace(
                                                                                 '$IssueDate', filedate)
                        newfname = newfname + extn
                        if newfname and newfname != fname:
                            logger.debug("Rename %s -> %s" % (fname, newfname))
                            newissuefile = os.path.join(rootdir, newfname)
                            newissuefile = safe_move(issuefile, newissuefile)
                            if os.path.exists(issuefile.replace(extn, '.jpg')):
                                safe_move(issuefile.replace(extn, '.jpg'), newissuefile.replace(extn, '.jpg'))
                            if os.path.exists(issuefile.replace(extn, '.opf')):
                                safe_move(issuefile.replace(extn, '.opf'), newissuefile.replace(extn, '.opf'))
                            issuefile = newissuefile

                    logger.debug("Found %s Issue %s" % (title, issuedate))
                    controlValueDict = {"Title": title}

                    # is this magazine already in the database?
                    mag_entry = myDB.match(
                        'SELECT LastAcquired, IssueDate, MagazineAdded from magazines WHERE Title=?', (title,))
                    if not mag_entry:
                        # need to add a new magazine to the database
                        newValueDict = {
                            "Reject": None,
                            "Status": "Active",
                            "MagazineAdded": None,
                            "LastAcquired": None,
                            "LatestCover": None,
                            "IssueDate": None,
                            "IssueStatus": "Skipped",
                            "Regex": None
                        }
                        logger.debug("Adding magazine %s" % title)
                        myDB.upsert("magazines", newValueDict, controlValueDict)
                        magissuedate = None
                        magazineadded = None
                        maglastacquired = None
                    else:
                        maglastacquired = mag_entry['LastAcquired']
                        magissuedate = mag_entry['IssueDate']
                        magazineadded = mag_entry['MagazineAdded']
                        magissuedate = str(magissuedate).zfill(4)

                    issuedate = str(issuedate).zfill(4)  # for sorting issue numbers

                    # is this issue already in the database?
                    issue_id = create_id("%s %s" % (title, issuedate))
                    iss_entry = myDB.match('SELECT Title,IssueFile from issues WHERE Title=? and IssueDate=?',
                                           (title, issuedate))
                    new_opf = False
                    if not iss_entry or iss_entry['IssueFile'] != issuefile:
                        new_opf = True  # new entry or name changed
                        if not iss_entry:
                            logger.debug("Adding issue %s %s" % (title, issuedate))
                        else:
                            logger.debug("Updating issue %s %s" % (title, issuedate))
                        controlValueDict = {"Title": title, "IssueDate": issuedate}
                        newValueDict = {
                            "IssueAcquired": iss_acquired,
                            "IssueID": issue_id,
                            "IssueFile": issuefile
                        }
                        myDB.upsert("Issues", newValueDict, controlValueDict)

                    createMagCover(issuefile)
                    lazylibrarian.postprocess.processMAGOPF(issuefile, title, issuedate, issue_id, overwrite=new_opf)

                    # see if this issues date values are useful
                    controlValueDict = {"Title": title}
                    if not mag_entry:  # new magazine, this is the only issue
                        newValueDict = {
                            "MagazineAdded": iss_acquired,
                            "LastAcquired": iss_acquired,
                            "LatestCover": os.path.splitext(issuefile)[0] + '.jpg',
                            "IssueDate": issuedate,
                            "IssueStatus": "Open"
                        }
                        myDB.upsert("magazines", newValueDict, controlValueDict)
                    else:
                        # Set magazine_issuedate to issuedate of most recent issue we have
                        # Set latestcover to most recent issue cover
                        # Set magazine_added to acquired date of earliest issue we have
                        # Set magazine_lastacquired to acquired date of most recent issue we have
                        # acquired dates are read from magazine file timestamps
                        newValueDict = {"IssueStatus": "Open"}
                        if not magazineadded or iss_acquired < magazineadded:
                            newValueDict["MagazineAdded"] = iss_acquired
                        if not maglastacquired or iss_acquired > maglastacquired:
                            newValueDict["LastAcquired"] = iss_acquired
                        if not magissuedate or issuedate >= magissuedate:
                            newValueDict["IssueDate"] = issuedate
                            newValueDict["LatestCover"] = os.path.splitext(issuefile)[0] + '.jpg'
                        myDB.upsert("magazines", newValueDict, controlValueDict)

        if lazylibrarian.CONFIG['FULL_SCAN'] and not onetitle:
            magcount = myDB.match("select count(*) from magazines")
            isscount = myDB.match("select count(*) from issues")
            logger.info("Magazine scan complete, found %s magazine%s, %s issue%s" %
                        (magcount['count(*)'], plural(magcount['count(*)']),
                         isscount['count(*)'], plural(isscount['count(*)'])))
        else:
            logger.info("Magazine scan complete")
        lazylibrarian.MAG_UPDATE = 0

    except Exception:
        lazylibrarian.MAG_UPDATE = 0
        logger.error('Unhandled exception in magazineScan: %s' % traceback.format_exc())
