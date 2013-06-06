import time, threading, urllib, urllib2, os, re

from xml.etree import ElementTree
from xml.etree.ElementTree import Element, SubElement

import lazylibrarian

from lazylibrarian import logger, database, formatter, providers, sabnzbd

import lib.fuzzywuzzy as fuzzywuzzy
from lib.fuzzywuzzy import fuzz, process

def searchbook(books=None):

    # rename this thread
    threading.currentThread().name = "SEARCHBOOKS"
    myDB = database.DBConnection()
    searchlist = []
    searchlist1 = []

    if books is None:
        # We are performing a backlog search
        searchbooks = myDB.select('SELECT BookID, AuthorName, Bookname from books WHERE Status="Wanted"')

        # Clear cache
        if os.path.exists(".ProviderCache"):
            for f in os.listdir(".ProviderCache"):
                os.unlink("%s/%s" % (".ProviderCache", f))

        # Clearing throttling timeouts
        t = SimpleCache.ThrottlingProcessor()
        t.lastRequestTime.clear()
    else:
        # The user has added a new book
        searchbooks = []
        for book in books:
            searchbook = myDB.select('SELECT BookID, AuthorName, BookName from books WHERE BookID=? AND Status="Wanted"', [book['bookid']])
            for terms in searchbook:
                searchbooks.append(terms)

    for searchbook in searchbooks:
        bookid = searchbook[0]
        author = searchbook[1]
        book = searchbook[2]

        dic = {'...':'', ' & ':' ', ' = ': ' ', '?':'', '$':'s', ' + ':' ', '"':'', ',':'', '*':'', ':':'', ';':''}
        dicSearchFormatting = {'.':' +', ' + ':' '}

        author = formatter.latinToAscii(formatter.replace_all(author, dic))
        book = formatter.latinToAscii(formatter.replace_all(book, dic))

        # TRY SEARCH TERM just using author name and book type
        author = formatter.latinToAscii(formatter.replace_all(author, dicSearchFormatting))
        searchterm1 = author # + ' ' + lazylibrarian.EBOOK_TYPE 
        searchterm1 = re.sub('[\.\-\/]', ' ', searchterm1).encode('utf-8')
        searchterm1 = re.sub(r'\(.*?\)', '', searchterm1).encode('utf-8')
        searchterm1 = re.sub(r"\s\s+" , " ", searchterm1) # strip any double white space
        searchlist.append({"bookid": bookid, "bookName":searchbook[2], "authorName":searchbook[1], "searchterm": searchterm1.strip()})

    if not lazylibrarian.SAB_HOST and not lazylibrarian.BLACKHOLE:
        logger.info('No download method is set, use SABnzbd or blackhole')

    if not lazylibrarian.NEWZNAB and not lazylibrarian.NEWZNAB2:
        logger.info('No providers are set. use NEWZNAB.')

    counter = 0
    for book in searchlist:
        resultlist = []
        if lazylibrarian.NEWZNAB:
            logger.debug('Searching NZB\'s at provider %s ...' % lazylibrarian.NEWZNAB_HOST)
            resultlist = providers.NewzNab(book, "1")

        if lazylibrarian.NEWZNAB2:
            logger.debug('Searching NZB\'s at provider %s ...' % lazylibrarian.NEWZNAB_HOST2)
            resultlist += providers.NewzNab(book, "2")

        if not resultlist:
            logger.debug("Adding book %s to queue." % book['searchterm'])

        else:
            dictrepl = {'...':'', ' & ':' ', ' = ': ' ', '?':'', '$':'s', ' + ':' ', '"':'', ',':'', '*':'', '(':'', ')':'', '[':'', ']':'', '#':'', '0':'', '1':'', '2':'', '3':'', '4':'', '5':'', '6':'', '7':'', '8':'' , '9':'', '\'':'', ':':'', '!':'', '-':'', '\s\s':' ', ' the ':' ', ' a ':' ', ' and ':' ', ' to ':' ', ' of ':' ', ' for ':' ', ' my ':' ', ' in ':' ', ' at ':' ', ' with ':' ' }
            bookName = book['bookName']
            bookID = book['bookid']
            bookName = re.sub('[\.\-\/]', ' ', bookName)
            bookName = re.sub(r'\(.*?\)', '', bookName)
            bookName = formatter.latinToAscii(formatter.replace_all(bookName.lower(), dictrepl)).strip()
            logger.debug(u'bookName %s' % bookName)
            addedCounter = 0

            for nzb in resultlist:
				nzbTitle = formatter.latinToAscii(formatter.replace_all(str(nzb['nzbtitle']).lower(), dictrepl)).strip()
				logger.debug(u'nzbName %s' % nzbTitle)
				logger.debug("NZB Match %: " + str(fuzz.partial_ratio(bookName, nzbTitle)))	
				if (fuzz.partial_ratio(bookName, nzbTitle) > 80):
					logger.debug(u'FOUND %s' % nzbTitle.lower())
					addedCounter = addedCounter + 1
					bookid = nzb['bookid']
					nzbTitle = (book["authorName"] + ' - ' + book['bookName'] + ' LL.(' + bookID + ')').strip()
					nzburl = nzb['nzburl']
					nzbprov = nzb['nzbprov']

					controlValueDict = {"NZBurl": nzburl}
					newValueDict = {
                        "NZBprov": nzbprov,
                        "BookID": bookid,
                        "NZBdate": formatter.today(),
                        "NZBtitle": nzbTitle,
                        "Status": "Skipped"
					}
					myDB.upsert("wanted", newValueDict, controlValueDict)

					snatchedbooks = myDB.action('SELECT * from books WHERE BookID=? and Status="Snatched"', [bookid]).fetchone()
					if not snatchedbooks:
						snatch = DownloadMethod(bookid, nzbprov, nzbTitle, nzburl)
					break;
            if addedCounter == 0:
            	logger.info("No nzb's found for " + (book["authorName"] + ' ' + bookName).strip() + ". Adding book to queue.")
        counter = counter + 1


def DownloadMethod(bookid=None, nzbprov=None, nzbtitle=None, nzburl=None):

    myDB = database.DBConnection()

    if lazylibrarian.SAB_HOST and not lazylibrarian.BLACKHOLE:
        download = sabnzbd.SABnzbd(nzbtitle, nzburl)
        logger.debug('Nzbfile has been downloaded from ' + str(nzburl))
        myDB.action('UPDATE books SET status = "Snatched" WHERE BookID=?', [bookid])
        myDB.action('UPDATE wanted SET status = "Snatched" WHERE BookID=?', [bookid])

    elif lazylibrarian.BLACKHOLE:

        try:
            req = urllib2.Request(nzburl)
            req.add_header('User-Agent', 'lazylibrary/0.0 +https://github.com/herman-rogers/LazyLibrarian-1')
            nzbfile = urllib2.urlopen(req, timeout=90).read()
   

        except urllib2.URLError, e:
            logger.warn('Error fetching nzb from url: ' + nzburl + ' %s' % e)
            nzbfile = False;

        if (nzbfile):

            nzbname = str(nzbtitle) + '.nzb';
            nzbpath = os.path.join(lazylibrarian.BLACKHOLEDIR, nzbname);

            try:
                f = open(nzbpath, 'w');
                f.write(nzbfile);
                f.close();
                logger.info('NZB file saved to: ' + nzbpath);
                download = True;
                try:
                    os.chmod(nzbpath, 0777);
                except Exception, e:
                    logger.info("Could not chmod path: " + str(file2));
            except Exception, e:
                logger.error('%s not writable, NZB not saved. Error: %s' % (nzbpath, e));
                download = False;

    else:
        logger.error('No downloadmethod is enabled, check config.')
        return False

    if download:
        logger.debug('Nzbfile has been downloaded')
        myDB.action('UPDATE books SET status = "Snatched" WHERE BookID=?', [bookid])
        myDB.action('UPDATE wanted SET status = "Snatched" WHERE BookID=?', [bookid])
    else:
        logger.error(u'Failed to download nzb @ <a href="%s">%s</a>' % (nzburl, lazylibrarian.NEWZNAB_HOST))
        myDB.action('UPDATE wanted SET status = "Failed" WHERE NZBurl=?', [nzburl])
