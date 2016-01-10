import os
import datetime
import lazylibrarian
import threading
import subprocess
from lazylibrarian import database, logger, formatter, notifiers, common
try:
    from wand.image import Image
except ImportError:
    try:
        import PythonMagick
    except:
        lazylibrarian.MAGICK = 'convert'  # may have external, don't know yet


def create_cover(issuefile=None):
    if not lazylibrarian.IMP_CONVERT == 'None':  # special flag to say "no covers required"
        # create a thumbnail cover if there isn't one
        if '.' in issuefile:
            words = issuefile.split('.')
            extn = '.' + words[len(words) - 1]
            coverfile = issuefile.replace(extn, '.jpg')
        else:
            logger.debug('Unable to create cover for %s, no extension?' % issuefile)
            return
        if not os.path.isfile(coverfile):
            logger.debug("Creating cover for %s using %s" % (issuefile, lazylibrarian.MAGICK))
            try:
                # No PythonMagick in python3, hence allow wand, but more complicated
                # to install - try to use external imagemagick convert?
                # should work on win/mac/linux as long as imagemagick is installed
                # and config points to external "convert" program

                if len(lazylibrarian.IMP_CONVERT):  # allow external convert to override libraries
                    try:
                        params = [lazylibrarian.IMP_CONVERT, issuefile + '[0]', coverfile]
                        subprocess.check_output(params, stderr=subprocess.STDOUT)
                    except subprocess.CalledProcessError as e:
                        logger.warn('ImageMagick "convert" failed %s' % e.output)

                elif lazylibrarian.MAGICK == 'wand':
                    with Image(filename=issuefile + '[0]') as img:
                        img.save(filename=coverfile)

                elif lazylibrarian.MAGICK == 'pythonmagick':
                    img = PythonMagick.Image()
                    img.read(issuefile + '[0]')
                    img.write(coverfile)
            except:
                logger.debug("Unable to create cover for %s using %s" % (issuefile, lazylibrarian.MAGICK))


def magazineScan(thread=None):
    # rename this thread
    if thread is None:
        threading.currentThread().name = "MAGAZINESCAN"

    myDB = database.DBConnection()

    mag_path = lazylibrarian.MAG_DEST_FOLDER
    if '$' in mag_path:
        mag_path = mag_path.split('$')[0]

    if lazylibrarian.MAG_RELATIVE:
        if mag_path[0] not in '._':
            mag_path = '_' + mag_path
        mag_path = os.path.join(lazylibrarian.DESTINATION_DIR, mag_path).encode(lazylibrarian.SYS_ENCODING)
    else:
        mag_path = mag_path.encode(lazylibrarian.SYS_ENCODING)

    if lazylibrarian.FULL_SCAN:
        mags = myDB.select('select * from Issues')

        for mag in mags:
            title = mag['Title']
            issuedate = mag['IssueDate']
            issuefile = mag['IssueFile']

            if not issuefile and os.path.isfile(issuefile):
                myDB.action('DELETE from Issues where issuefile="%s"' % issuefile)
                logger.info('Issue %s - %s deleted as not found on disk' % (title, issuedate))
                controlValueDict = {"Title": title}
                newValueDict = {
                    "LastAcquired": None,       # clear magazine dates
                    "IssueDate": None,       # we will fill them in again later
                    "IssueStatus": "Skipped"    # assume there are no issues now
                }
                myDB.upsert("magazines", newValueDict, controlValueDict)
                logger.debug('Magazine %s details reset' % title)

    logger.info(' Checking [%s] for magazines' % mag_path)

    for dirname, dirnames, filenames in os.walk(mag_path):
        for fname in filenames[:]:
            # maybe not all magazines will be pdf?
            if formatter.is_valid_booktype(fname, booktype='mag'):
                try:
                    title = fname.split('-')[3]
                    title = title.split('.')[-2]
                    title = title.strip()
                    issuedate = fname.split(' ')[0]
                    issuefile = os.path.join(dirname, fname)  # full path to issue.pdf
                    logger.debug("Found Issue %s" % fname)
                except:
                    logger.debug("Invalid name format for %s" % fname)
                    continue

                mtime = os.path.getmtime(issuefile)
                iss_acquired = datetime.date.isoformat(datetime.date.fromtimestamp(mtime))

                # magazines : Title, Frequency, Regex, Status, MagazineAdded, LastAcquired, IssueDate, IssueStatus
                # issues    : Title, IssueAcquired, IssueDate, IssueFile

                controlValueDict = {"Title": title}

                # is this magazine already in the database?
                mag_entry = myDB.select('SELECT * from magazines WHERE Title="%s"' % title)
                if not mag_entry:
                    # need to add a new magazine to the database
                    newValueDict = {
                        "Frequency": "Monthly",  # no idea really, set a default value
                        "Regex": None,
                        "Status": "Active",
                        "MagazineAdded": None,
                        "LastAcquired": None,
                        "IssueDate": None,
                        "IssueStatus": "Skipped"
                    }
                    logger.debug("Adding magazine %s" % title)
                    myDB.upsert("magazines", newValueDict, controlValueDict)
                    lastacquired = None
                    magissuedate = None
                    magazineadded = None
                else:
                    maglastacquired = mag_entry[0]['LastAcquired']
                    magissuedate = mag_entry[0]['IssueDate']
                    magazineadded = mag_entry[0]['MagazineAdded']

                # is this issue already in the database?
                controlValueDict = {"Title": title, "IssueDate": issuedate}
                iss_entry = myDB.select('SELECT * from issues WHERE Title="%s" and IssueDate="%s"' % (
                    title, issuedate))
                if not iss_entry:
                    newValueDict = {
                        "IssueAcquired": iss_acquired,
                        "IssueFile": issuefile
                    }
                    logger.debug("Adding issue %s %s" % (title, issuedate))
                    myDB.upsert("Issues", newValueDict, controlValueDict)

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
                        newValueDict = {"LastAcquired": iss_acquired}
                        myDB.upsert("magazines", newValueDict, controlValueDict)
                    if magissuedate is None or issuedate > magissuedate:
                        controlValueDict = {"Title": title}
                        newValueDict = {"IssueDate": issuedate}
                        myDB.upsert("magazines", newValueDict, controlValueDict)

    magcount = myDB.action("select count(*) from magazines").fetchone()
    isscount = myDB.action("select count(*) from issues").fetchone()

    logger.info("Magazine scan complete, found %s magazines, %s issues" % (magcount['count(*)'], isscount['count(*)']))
