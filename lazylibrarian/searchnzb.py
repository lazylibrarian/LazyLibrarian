import time, threading, urllib, urllib2, os, re

from xml.etree import ElementTree
from xml.etree.ElementTree import Element, SubElement

import lazylibrarian
import request

from lazylibrarian import logger, database, formatter, providers, nzbget, sabnzbd, SimpleCache, notifiers, searchmag, classes

import lib.fuzzywuzzy as fuzzywuzzy
from lib.fuzzywuzzy import fuzz, process

from lazylibrarian.common import USER_AGENT

#new to support torrents
from lazylibrarian.searchtorrents import TORDownloadMethod
from StringIO import StringIO
import gzip

def search_nzb_book(books=None, mags=None):
    if not(lazylibrarian.USE_NZB):
        return
    # rename this thread
    threading.currentThread().name = "SEARCHNZBBOOKS"
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
        if books != False:
            for book in books:
                searchbook = myDB.select('SELECT BookID, AuthorName, BookName from books WHERE BookID="%s" AND Status="Wanted"' % book['bookid'])
                for terms in searchbook:
                    searchbooks.append(terms)

    for searchbook in searchbooks:
        bookid = searchbook[0]
        author = searchbook[1]
        book = searchbook[2]

        dic = {'...':'', '.':' ', ' & ':' ', ' = ': ' ', '?':'', '$':'s', ' + ':' ', '"':'', ',':'', '*':'', ':':'', ';':''}
        dicSearchFormatting = {'.':' +', ' + ':' '}

        author = formatter.latinToAscii(formatter.replace_all(author, dic))
        book = formatter.latinToAscii(formatter.replace_all(book, dic))

        # TRY SEARCH TERM just using author name and book type
        author = formatter.latinToAscii(formatter.replace_all(author, dicSearchFormatting))
        searchterm = author + ' ' + book # + ' ' + lazylibrarian.EBOOK_TYPE 
        searchterm = re.sub('[\.\-\/]', ' ', searchterm).encode('utf-8')
        searchterm = re.sub(r'\(.*?\)', '', searchterm).encode('utf-8')
        searchterm = re.sub(r"\s\s+" , " ", searchterm) # strip any double white space
        searchlist.append({"bookid": bookid, "bookName":searchbook[2], "authorName":searchbook[1], "searchterm": searchterm.strip()})
    
    if not lazylibrarian.SAB_HOST and not lazylibrarian.NZB_DOWNLOADER_BLACKHOLE and not lazylibrarian.NZBGET_HOST:
        logger.info('No download method is set, use SABnzbd/NZBGet or blackhole')

    counter = 0
    for book in searchlist: 
        resultlist, nproviders = providers.IterateOverNewzNabSites(book,'book')

	if not nproviders:
		logger.info('No providers are set. try use NEWZNAB or TORZNAB')
		return

        #if you can't find teh book specifically, you might find under general search
        if not resultlist:
            logger.info("Searching for type book failed to find any books...moving to general search")
            resultlist, nproviders = providers.IterateOverNewzNabSites(book,'general')
	
        if not resultlist:
            logger.debug("Adding book %s to queue." % book['searchterm'])

        else:
            dictrepl = {'...':'', '.':' ', ' & ':' ', ' = ': ' ', '?':'', '$':'s', ' + ':' ', '"':'', ',':'', '*':'', '(':'', ')':'', '[':'', ']':'', '#':'', '0':'', '1':'', '2':'', '3':'', '4':'', '5':'', '6':'', '7':'', '8':'' , '9':'', '\'':'', ':':'', '!':'', '-':'', '\s\s':' ', ' the ':' ', ' a ':' ', ' and ':' ', ' to ':' ', ' of ':' ', ' for ':' ', ' my ':' ', ' in ':' ', ' at ':' ', ' with ':' ' }
            logger.debug(u'searchterm %s' % book['searchterm'])
            addedCounter = 0

            for nzb in resultlist:
                nzbTitle = formatter.latinToAscii(formatter.replace_all(str(nzb['nzbtitle']).lower(), dictrepl)).strip()
                nzbTitle = re.sub(r"\s\s+" , " ", nzbTitle) #remove extra whitespace
                logger.debug(u'nzbName %s' % nzbTitle)          

                match_ratio = int(lazylibrarian.MATCH_RATIO)
                nzbTitle_match = fuzz.token_sort_ratio(book['searchterm'].lower(), nzbTitle)
                logger.debug("NZB Title Match %: " + str(nzbTitle_match))
                
                if (nzbTitle_match > match_ratio):
                    logger.info(u'Found NZB: %s' % nzb['nzbtitle'])
                    addedCounter = addedCounter + 1
                    bookid = book['bookid']
                    nzbTitle = (book["authorName"] + ' - ' + book['bookName'] + ' LL.(' + book['bookid'] + ')').strip()
                    nzburl = nzb['nzburl']
                    nzbprov = nzb['nzbprov']
                    nzbdate_temp = nzb['nzbdate']
                    nzbsize_temp = nzb['nzbsize']  #Need to cater for when this is NONE (Issue 35)
                    if nzbsize_temp is None:
                        nzbsize_temp = 1000
                    nzbsize = str(round(float(nzbsize_temp) / 1048576,2))+' MB'
                    nzbdate = formatter.nzbdate2format(nzbdate_temp)
		    nzbmode = nzb['nzbmode']
                    
                    controlValueDict = {"NZBurl": nzburl}
                    newValueDict = {
                        "NZBprov": nzbprov,
                        "BookID": bookid,
                        "NZBdate": nzbdate,
                        "NZBsize": nzbsize,
                        "NZBtitle": nzbTitle,
			"NZBmode": nzbmode,
                        "Status": "Skipped"
                    }
                    myDB.upsert("wanted", newValueDict, controlValueDict)

                    snatchedbooks = myDB.action('SELECT * from books WHERE BookID="%s" and Status="Snatched"' % bookid).fetchone()
                    if not snatchedbooks:
			if nzbmode == "torznab":
				snatch = TORDownloadMethod(bookid, nzbprov, nzbTitle, nzburl)
			else:
                        	snatch = NZBDownloadMethod(bookid, nzbprov, nzbTitle, nzburl)
                        notifiers.notify_snatch(nzbTitle+' at '+formatter.now()) 
                    break;
            if addedCounter == 0:
                logger.info("No nzb's found for " + (book["authorName"] + ' ' + book['bookName']).strip() + ". Adding book to queue.")
        counter = counter + 1

    if not books or books==False:
        snatched = searchmag.searchmagazines(mags)
        for items in snatched:
		if items['nzbmode'] == "torznab":
			snatch = TORDownloadMethod(items['bookid'], items['nzbprov'], items['nzbtitle'], items['nzburl'])
		elif items['nzbmode'] == "torrent":
			snatch = TORDownloadMethod(items['bookid'], items['nzbprov'], items['nzbtitle'], items['nzburl'])
		else:
            		snatch = NZBDownloadMethod(items['bookid'], items['nzbprov'], items['nzbtitle'], items['nzburl'])
            	notifiers.notify_snatch(items['nzbtitle']+' at '+formatter.now()) 
    logger.info("NZBSearch for Wanted items complete")


def NZBDownloadMethod(bookid=None, nzbprov=None, nzbtitle=None, nzburl=None):

    myDB = database.DBConnection()
    if lazylibrarian.SAB_HOST and not lazylibrarian.NZB_DOWNLOADER_BLACKHOLE:
        download = sabnzbd.SABnzbd(nzbtitle, nzburl)

    elif lazylibrarian.NZBGET_HOST and not lazylibrarian.NZB_DOWNLOADER_BLACKHOLE:
        headers = {'User-Agent': USER_AGENT}
        data = request.request_content(url=nzburl, headers=headers)
        nzb = classes.NZBDataSearchResult()
        nzb.extraInfo.append(data)
        nzb.name = nzbtitle
        nzb.url = nzburl
        download = nzbget.sendNZB(nzb)

    elif lazylibrarian.NZB_DOWNLOADER_BLACKHOLE:

        try:
            req = urllib2.Request(nzburl)
	    if lazylibrarian.PROXY_HOST:
	    	req.set_proxy(lazylibrarian.PROXY_HOST, lazylibrarian.PROXY_TYPE)
            req.add_header('User-Agent', USER_AGENT)
            nzbfile = urllib2.urlopen(req, timeout=90).read()
   

        except urllib2.URLError, e:
            logger.warn('Error fetching nzb from url: ' + nzburl + ' %s' % e)
            nzbfile = False;

        if (nzbfile):

            nzbname = str(nzbtitle) + '.nzb';
            nzbpath = os.path.join(lazylibrarian.NZB_BLACKHOLEDIR, nzbname);

            try:
                f = open(nzbpath, 'w');
                f.write(nzbfile);
                f.close();
                logger.info('NZB file saved to: ' + nzbpath);
                download = True;
                try:
                    os.chmod(nzbpath, 0777);
                except Exception, e:
                    logger.info("Could not chmod path: " + str(nzbpath));
            except Exception, e:
                logger.error('%s not writable, NZB not saved. Error: %s' % (nzbpath, e));
                download = False;

    else:
        logger.error('No NZB download method is enabled, check config.')
        return False

    if download:
        logger.debug('Nzbfile has been downloaded from ' + str(nzburl))
        myDB.action('UPDATE books SET status = "Snatched" WHERE BookID="%s"' % bookid)
        myDB.action('UPDATE wanted SET status = "Snatched" WHERE NZBurl="%s"' % nzburl)
    else:
        logger.error(u'Failed to download nzb @ <a href="%s">%s</a>' % (nzburl, lazylibrarian.NEWZNAB_HOST))
        myDB.action('UPDATE wanted SET status = "Failed" WHERE NZBurl="%s"' % nzburl)

def MakeSearchTermWebSafe(insearchterm=None):

        dic = {'...':'', ' & ':' ', ' = ': ' ', '?':'', '$':'s', ' + ':' ', '"':'', ',':'', '*':''}

        searchterm = formatter.latinToAscii(formatter.replace_all(insearchterm, dic))

        searchterm = re.sub('[\.\-\/]', ' ', searchterm).encode('utf-8')
        
        logger.debug("Converting Search Term [%s] to Web Safe Search Term [%s]" % (insearchterm, searchterm))
        
        return searchterm
 

