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

import datetime
import os
import platform
import re
import subprocess
import traceback
from hashlib import sha1

import lazylibrarian
from lazylibrarian import database, logger
from lazylibrarian.common import setperm
from lazylibrarian.formatter import getList, is_valid_booktype, plural


def create_covers(refresh=False):
    myDB = database.DBConnection()
    issues = myDB.select('SELECT IssueFile from issues')
    if refresh:
        logger.info("Creating covers for %s issue%s" % (len(issues), plural(len(issues))))
    else:
        logger.info("Checking covers for %s issue%s" % (len(issues), plural(len(issues))))
    for item in issues:
        create_cover(item['IssueFile'], refresh=refresh)
    logger.info("Cover creation completed")


def create_cover(issuefile=None, refresh=False):
    if lazylibrarian.IMP_CONVERT == 'None':  # special flag to say "no covers required"
        return
    if issuefile is None or not os.path.isfile(issuefile):
        return

    # create a thumbnail cover if there isn't one
    extn = os.path.splitext(issuefile)[1]
    if extn:
        coverfile = issuefile.replace(extn, '.jpg')
    else:
        logger.debug('Unable to create cover for %s, no extension?' % issuefile)
        return
    if os.path.isfile(coverfile):
        if refresh:
            os.remove(coverfile)
        else:
            return  # quit if cover already exists

    generator = ""
    GS = ""
    if platform.system() == "Windows":
        params = ["where", "gswin64c"]
        try:
            GS = subprocess.check_output(params, stderr=subprocess.STDOUT).strip()
            generator = "gswin64c"
        except Exception as e:
            logger.debug("where gswin64c failed: %s" % str(e))
        if not os.path.isfile(GS):
            params = ["where", "gswin32c"]
            try:
                GS = subprocess.check_output(params, stderr=subprocess.STDOUT).strip()
                generator = "gswin32c"
            except Exception as e:
                logger.debug("where gswin32c failed: %s" % str(e))
        if not os.path.isfile(GS):
            logger.debug("No gswin found")
            generator = "(no windows ghostscript found)"
        else:
            params = [GS, "--version"]
            res = subprocess.check_output(params, stderr=subprocess.STDOUT)
            logger.debug("Found %s [%s] version %s" % (generator, GS, res))
            generator = "%s version %s" % (generator, res)
            if '[' in issuefile:
                issuefile = issuefile.split('[')[0]
            params = [GS, "-sDEVICE=jpeg", "-dNOPAUSE", "-dBATCH", "-dSAFER", "-dFirstPage=1", "-dLastPage=1",
                      "-dUseCropBox", "-sOutputFile=%s" % coverfile, issuefile]
            res = subprocess.check_output(params, stderr=subprocess.STDOUT)
            if not os.path.isfile(coverfile):
                logger.debug("Failed to create jpg: %s" % res)

    else:  # not windows
        try:
            from wand.image import Image
            interface = "wand"
        except Exception:
            try:
                # No PythonMagick in python3
                import PythonMagick
                interface = "pythonmagick"
            except Exception:
                interface = ""

        try:
            if len(lazylibrarian.IMP_CONVERT):  # allow external convert to override libraries
                generator = "external program: %s" % lazylibrarian.IMP_CONVERT
                if "gsconvert.py" in lazylibrarian.IMP_CONVERT:
                    msg = "Use of gsconvert.py is deprecated, equivalent functionality is now built in. "
                    msg += "Support for gsconvert.py may be removed in a future release. See wiki for details."
                    logger.warn(msg)
                converter = lazylibrarian.IMP_CONVERT
                if not converter.startswith(os.sep):  # full path given, or just program_name?
                    converter = os.path.join(os.getcwd(), lazylibrarian.IMP_CONVERT)
                try:
                    params = [converter, '%s' % issuefile, '%s' % coverfile]
                    res = subprocess.check_output(params, stderr=subprocess.STDOUT)
                    if res:
                        logger.debug('%s reports: %s' % (lazylibrarian.IMP_CONVERT, res))
                except Exception as e:
                    # logger.debug(params)
                    logger.debug('External "convert" failed %s' % e)

            elif interface == 'wand':
                generator = "wand interface"
                with Image(filename=issuefile + '[0]') as img:
                    img.save(filename=coverfile)

            elif interface == 'pythonmagick':
                generator = "pythonmagick interface"
                img = PythonMagick.Image()
                img.read(issuefile + '[0]')
                img.write(coverfile)
            else:
                GS = os.path.join(os.getcwd(), "gs")
                generator = "local gs"
                if not os.path.isfile(GS):
                    GS = ""
                    params = ["which", "gs"]
                    try:
                        GS = subprocess.check_output(params, stderr=subprocess.STDOUT).strip()
                        generator = GS
                    except Exception as e:
                        logger.debug("which gs failed: %s" % str(e))
                    if not os.path.isfile(GS):
                        logger.debug("Cannot find gs")
                        generator = "(no gs found)"
                    else:
                        params = [GS, "--version"]
                        res = subprocess.check_output(params, stderr=subprocess.STDOUT)
                        logger.debug("Found gs [%s] version %s" % (GS, res))
                        generator = "%s version %s" % (generator, res)
                        if '[' in issuefile:
                            issuefile = issuefile.split('[')[0]
                        params = [GS, "-sDEVICE=jpeg", "-dNOPAUSE", "-dBATCH", "-dSAFER", "-dFirstPage=1",
                                  "-dLastPage=1", "-dUseCropBox", "-sOutputFile=%s" % coverfile, issuefile]
                        res = subprocess.check_output(params, stderr=subprocess.STDOUT)
                        if not os.path.isfile(coverfile):
                            logger.debug("Failed to create jpg: %s" % res)

        except Exception:
            logger.debug("Unable to create cover for %s using %s" % (issuefile, generator))
            logger.debug('Exception in create_cover: %s' % traceback.format_exc())

    if os.path.isfile(coverfile):
        setperm(coverfile)
        logger.debug("Created cover for %s using %s" % (issuefile, generator))


def create_id(issuename=None):
    hashID = sha1(issuename).hexdigest()
    # logger.debug('Issue %s Hash: %s' % (issuename, hashID))
    return hashID


def magazineScan():
  try:
    myDB = database.DBConnection()

    mag_path = lazylibrarian.MAG_DEST_FOLDER
    if '$' in mag_path:
        mag_path = mag_path.split('$')[0]

    if lazylibrarian.MAG_RELATIVE:
        if mag_path[0] not in '._':
            mag_path = '_' + mag_path
        mag_path = os.path.join(lazylibrarian.DIRECTORY('Destination'), mag_path).encode(lazylibrarian.SYS_ENCODING)
    else:
        mag_path = mag_path.encode(lazylibrarian.SYS_ENCODING)

    if lazylibrarian.FULL_SCAN:
        mags = myDB.select('select * from Issues')
        # check all the issues are still there, delete entry if not
        for mag in mags:
            title = mag['Title']
            issuedate = mag['IssueDate']
            issuefile = mag['IssueFile']

            if issuefile and not os.path.isfile(issuefile):
                myDB.action('DELETE from Issues where issuefile="%s"' % issuefile)
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
            count = myDB.select('SELECT COUNT(Title) as counter FROM issues WHERE Title="%s"' % title)
            issues = count[0]['counter']
            if not issues:
                logger.debug('Magazine %s deleted as no issues found' % title)
                myDB.action('DELETE from magazines WHERE Title="%s"' % title)

    logger.info(' Checking [%s] for magazines' % mag_path)

    matchString = ''
    for char in lazylibrarian.MAG_DEST_FILE:
        matchString = matchString + '\\' + char
    # massage the MAG_DEST_FILE config parameter into something we can use
    # with regular expression matching
    booktypes = ''
    count = -1
    booktype_list = getList(lazylibrarian.MAG_TYPE)
    for book_type in booktype_list:
        count += 1
        if count == 0:
            booktypes = book_type
        else:
            booktypes = booktypes + '|' + book_type
    matchString = matchString.replace("\\$\\I\\s\\s\\u\\e\\D\\a\\t\\e", "(?P<issuedate>.*?)").replace(
        "\\$\\T\\i\\t\\l\\e", "(?P<title>.*?)") + '\.[' + booktypes + ']'
    pattern = re.compile(matchString, re.VERBOSE)

    for dirname, dirnames, filenames in os.walk(mag_path):
        for fname in filenames[:]:
            # maybe not all magazines will be pdf?
            if is_valid_booktype(fname, booktype='mag'):
                try:
                    match = pattern.match(fname)
                    if match:
                        issuedate = match.group("issuedate")
                        title = match.group("title")
                    else:
                        logger.debug("Pattern match failed for [%s]" % fname)
                        continue
                except Exception:
                    logger.debug("Invalid name format for [%s]" % fname)
                    continue

                logger.debug("Found Issue %s" % fname)

                issuefile = os.path.join(dirname, fname)  # full path to issue.pdf
                mtime = os.path.getmtime(issuefile)
                iss_acquired = datetime.date.isoformat(datetime.date.fromtimestamp(mtime))

                controlValueDict = {"Title": title}

                # is this magazine already in the database?
                mag_entry = myDB.select('SELECT * from magazines WHERE Title="%s" COLLATE NOCASE' % title)
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
                else:
                    maglastacquired = mag_entry[0]['LastAcquired']
                    magissuedate = mag_entry[0]['IssueDate']
                    magazineadded = mag_entry[0]['MagazineAdded']
                    magissuedate = str(magissuedate).zfill(4)

                issuedate = str(issuedate).zfill(4)  # for sorting issue numbers

                # is this issue already in the database?
                controlValueDict = {"Title": title, "IssueDate": issuedate}
                issue_id = create_id("%s %s" % (title, issuedate))
                iss_entry = myDB.match('SELECT Title from issues WHERE Title="%s" COLLATE NOCASE and IssueDate="%s"' % (
                    title, issuedate))
                if not iss_entry:
                    newValueDict = {
                        "IssueAcquired": iss_acquired,
                        "IssueID": issue_id,
                        "IssueFile": issuefile
                    }
                    myDB.upsert("Issues", newValueDict, controlValueDict)
                    logger.debug("Adding issue %s %s" % (title, issuedate))

                create_cover(issuefile)

                # see if this issues date values are useful
                # if its a new magazine, magazineadded,magissuedate,lastacquired are all None
                # if magazineadded is NOT None, but the others are, we've deleted one or more issues
                # so the most recent dates may be wrong and need to be updated.
                # Set magazine_issuedate to issuedate of most recent issue we have
                # Set magazine_added to acquired date of earliest issue we have
                # Set magazine_lastacquired to acquired date of most recent issue we have
                # acquired dates are read from magazine file timestamps
                if magazineadded is None:  # new magazine, this might be the only issue
                    controlValueDict = {"Title": title}
                    newValueDict = {
                        "MagazineAdded": iss_acquired,
                        "LastAcquired": iss_acquired,
                        "LatestCover": os.path.splitext(issuefile)[0] + '.jpg',
                        "IssueDate": issuedate,
                        "IssueStatus": "Open"
                    }
                    myDB.upsert("magazines", newValueDict, controlValueDict)
                else:
                    if iss_acquired < magazineadded:
                        controlValueDict = {"Title": title}
                        newValueDict = {"MagazineAdded": iss_acquired}
                        myDB.upsert("magazines", newValueDict, controlValueDict)
                    if maglastacquired is None or iss_acquired > maglastacquired:
                        controlValueDict = {"Title": title}
                        newValueDict = {"LastAcquired": iss_acquired,
                                        "LatestCover": os.path.splitext(issuefile)[0] + '.jpg'}
                        myDB.upsert("magazines", newValueDict, controlValueDict)
                    if magissuedate is None or issuedate > magissuedate:
                        controlValueDict = {"Title": title}
                        newValueDict = {"IssueDate": issuedate}
                        myDB.upsert("magazines", newValueDict, controlValueDict)

    magcount = myDB.match("select count(*) from magazines")
    isscount = myDB.match("select count(*) from issues")

    logger.info("Magazine scan complete, found %s magazine%s, %s issue%s" %
                (magcount['count(*)'], plural(magcount['count(*)']),
                 isscount['count(*)'], plural(isscount['count(*)'])))

  except Exception:
    logger.error('Unhandled exception in magazineScan: %s' % traceback.format_exc())
