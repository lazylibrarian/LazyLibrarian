import os
import datetime

import lazylibrarian

from lazylibrarian import logger, database, sabnzbd

class DownloadInstruct:

    @staticmethod
    def DownloadMethod(bookid=None):

        myDB = database.DBConnection()
        nzbfile = myDB.action('SELECT AuthorName, BookName, NZBLink FROM wanted WHERE BookID=? AND Status="Pending"', [bookid]).fetchone()

        if not nzbfile:
            logger.info("All nzblinks failed. Adding book to queue")

        else:
            nzbname = nzbfile[0] + " " + nzbfile[1]
            nzblink = nzbfile[2]

            if lazylibrarian.SAB_HOST and lazylibrarian.SAB_PORT:
                logger.info("Preparing send results to Sabnzbd")
                result = sabnzbd.SABnzbd(nzbname=nzbname, nzblink=nzblink)

            elif lazylibrarian.BLACKHOLE:
                nzbmethod = "nzb2dir"
                nzbfolder = lazylibrarian.BLACKHOLEDIR

                if not os.path.exists(lazylibrarian.BLACKHOLEDIR):
                    logger.error('Blackhole folder does not exist, check path or config: ' + nzbfolder)
                if not os.access(lazylibrarian.BLACKHOLEDIR, os.W_OK):
                    logger.error('Blackhole folder is not writable, check permissions: ' + nzbfolder)

            if result:
                # update bookstable
                controlValueDict = {"BookID": bookid}
                newValueDict = {"Status":"Snatched"}
                myDB.upsert("books", newValueDict, controlValueDict)

                # update wantedtable
                controlValueDict = {"NZBLink": nzblink}
                newValueDict = {"Status": "Snatched"}
                myDB.upsert("wanted", newValueDict, controlValueDict)
            else:
                # update wantedtable
                controlValueDict = {"NZBLink": nzblink}
                newValueDict = {"Status": "Failed"}
                myDB.upsert("wanted", newValueDict, controlValueDict)



