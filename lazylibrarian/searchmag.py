import time, threading, urllib, urllib2, os, re

from xml.etree import ElementTree
from xml.etree.ElementTree import Element, SubElement

import lazylibrarian

from lazylibrarian import logger, database, formatter, providers, sabnzbd, SimpleCache, notifiers

import lib.fuzzywuzzy as fuzzywuzzy
from lib.fuzzywuzzy import fuzz, process

def searchmagazines(mags=None):
	maglist = []
	myDB = database.DBConnection()
	searchlist = []

	threading.currentThread().name = "SEARCHMAGS"


	if mags is None:
		searchmags = myDB.select('SELECT Title, Frequency, LastAcquired, IssueDate from magazines WHERE Status="Active"')
	else:
		searchmags = []
		for magazine in mags:
			searchmags_temp = myDB.select('SELECT Title, Frequency, LastAcquired, IssueDate from magazines WHERE Title=? AND Status="Active"', [magazine['bookid']])
			for terms in searchmags_temp:
				searchmags.append(terms)

	for searchmag in searchmags:
		bookid = searchmag[0]
		searchterm = searchmag[0]
		frequency = searchmag[1]
		last_acquired = searchmag[2]
		issue_date = searchmag[3]

		dic = {'...':'', ' & ':' ', ' = ': ' ', '?':'', '$':'s', ' + ':' ', '"':'', ',':'', '*':''}

		searchterm = formatter.latinToAscii(formatter.replace_all(searchterm, dic))
		searchterm = re.sub('[\.\-\/]', ' ', searchterm).encode('utf-8')
		searchlist.append({"bookid": bookid, "searchterm": searchterm})

	if not lazylibrarian.SAB_HOST and not lazylibrarian.BLACKHOLE:
		logger.info('No download method is set, use SABnzbd or blackhole')

	if not lazylibrarian.NEWZNAB and not lazylibrarian.NEWZNAB2 and not lazylibrarian.USENETCRAWLER:
		logger.info('No providers are set. try use NEWZNAB.')

	if searchlist == []:
		logger.info('There is nothing to search for.  Mark some magazines as active.')

	for book in searchlist:
		resultlist = []
		if lazylibrarian.NEWZNAB:
			logger.debug('Searching NZB\'s at provider %s ...' % lazylibrarian.NEWZNAB_HOST)
			resultlist = providers.NewzNab(book, "1")

		if lazylibrarian.NEWZNAB2:
			logger.debug('Searching NZB\'s at provider %s ...' % lazylibrarian.NEWZNAB_HOST2)
			resultlist += providers.NewzNab(book, "2")

		if lazylibrarian.USENETCRAWLER: 
			logger.info('Searching NZB\'s at provider UsenetCrawler ...')
			resultlist += providers.UsenetCrawler(book, 'mag')

			#AHHH pass the book not the search book - bloody names the same, so wrong keys passing over

		if not resultlist:
			logger.debug("Adding book %s to queue." % book['searchterm'])

		else:
			bad_regex = 0
			old_date = 0
			total_nzbs = 0
			new_date = 0
			for nzb in resultlist:
				total_nzbs = total_nzbs + 1
				bookid = nzb['bookid']
				nzbtitle = nzb['nzbtitle']
				nzburl = nzb['nzburl']
				nzbprov = nzb['nzbprov']
				nzbdate_temp = nzb['nzbdate']
				nzbsize_temp = nzb['nzbsize']
				nzbsize = str(round(float(nzbsize_temp) / 1048576,2))+' MB'
				nzbdate = formatter.nzbdate2format(nzbdate_temp)

				checkifmag = myDB.select('SELECT * from magazines WHERE Title=?', [bookid])
				if checkifmag:
					for results in checkifmag:
						control_date = results['IssueDate']
						frequency = results['Frequency']
						regex = results['Regex']

					nzbtitle_formatted = nzb['nzbtitle'].replace('.',' ').replace('/',' ').replace('+',' ').replace('_',' ').replace('(','').replace(')','')
					#Need to make sure that substrings of magazine titles don't get found (e.g. Maxim USA will find Maximum PC USA)
					keyword_check = nzbtitle_formatted.replace(bookid,'')
					#remove extra spaces if they're in a row
					nzbtitle_exploded_temp = " ".join(nzbtitle_formatted.split())
					nzbtitle_exploded = nzbtitle_exploded_temp.split(' ')

					bookid_exploded = bookid.split(' ')

					#Make sure that NZB contains exact magazine phrase, and that NZB title begins with magazine title
					#logger.debug('[%s] !=[%s] & [%s] == [%s]' %(keyword_check.lower(),nzbtitle_formatted.lower(),nzbtitle_exploded[0].lower(),bookid_exploded[0].lower()))
					if keyword_check.lower() != nzbtitle_formatted.lower() and nzbtitle_exploded[0].lower() == bookid_exploded[0].lower():
						
						if len(nzbtitle_exploded) > 1:
							#regexA = DD MonthName YYYY OR MonthName YYYY
							regexA_year = nzbtitle_exploded[len(nzbtitle_exploded)-1]
							regexA_month_temp = nzbtitle_exploded[len(nzbtitle_exploded)-2]
							regexA_month = formatter.month2num(regexA_month_temp)

							if frequency == "Weekly" or frequency == "BiWeekly":
								regexA_day = nzbtitle_exploded[len(nzbtitle_exploded)-3].zfill(2)
							else:
								regexA_day = '01'
							newdatish_regexA = regexA_year+regexA_month+regexA_day

							try:
								int(newdatish_regexA)
								newdatish = regexA_year+'-'+regexA_month+'-'+regexA_day
							except:
								#regexB = MonthName DD YYYY
								regexB_year = nzbtitle_exploded[len(nzbtitle_exploded)-1]
								regexB_day = nzbtitle_exploded[len(nzbtitle_exploded)-2].zfill(2)
								regexB_month_temp = nzbtitle_exploded[len(nzbtitle_exploded)-3]
								regexB_month = formatter.month2num(regexB_month_temp)
								newdatish_regexB = regexB_year+regexB_month+regexB_day

								try:
									int(newdatish_regexB)
									newdatish = regexB_year+'-'+regexB_month+'-'+regexB_day
								except:
									#regexC = YYYY-MM
									regexC_last = nzbtitle_exploded[len(nzbtitle_exploded)-1]
									regexC_exploded = regexC_last.split('-')
									if len(regexC_exploded) == 2:
										regexC_year = regexC_exploded[0]
										regexC_month = regexC_exploded[1].zfill(2)
										regexC_day = '01'
										newdatish_regexC = regexC_year+regexC_month+regexC_day
									elif len(regexC_exploded) == 3:
										regexC_year = regexC_exploded[0]
										regexC_month = regexC_exploded[1].zfill(2)
										regexC_day = regexC_exploded[2].zfill(2)
										newdatish_regexC = regexC_year+regexC_month+regexC_day
									else:
										newdatish_regexC = 'Invalid'

									try:
										int(newdatish_regexC)
										newdatish = regexC_year+'-'+regexC_month+'-'+regexC_day
									except:
										logger.debug('NZB %s not in proper date format.' % nzbtitle_formatted)
										bad_regex = bad_regex + 1
										continue

						else:
							continue

						#Don't want to overwrite status = Skipped for NZBs that have been previously found
						wanted_status = myDB.select('SELECT * from wanted WHERE NZBtitle=?', [nzbtitle])
						if wanted_status:
							for results in wanted_status:
								status = results['Status']
						else:
							status = "Skipped"

						controlValueDict = {"NZBurl": nzburl}
						newValueDict = {
							"NZBprov": nzbprov,
							"BookID": bookid,
							"NZBdate": nzbdate,
							"NZBtitle": nzbtitle,
							"AuxInfo": newdatish,
							"Status": status,
							"NZBsize": nzbsize
							}
						myDB.upsert("wanted", newValueDict, controlValueDict)
						#print nzbtitle_formatted
						#print newdatish

						if control_date is None:
							myDB.upsert("magazines", {"LastAcquired": nzbdate, "IssueDate": newdatish}, {"Title": bookid})
							maglist.append({
								'bookid': bookid,
								'nzbprov': nzbprov,
								'nzbtitle': nzbtitle,
								'nzburl': nzburl
								})
							new_date = new_date + 1
						else:
							comp_date = formatter.datecompare(newdatish, control_date)
							if comp_date > 0:
								myDB.upsert("magazines", {"LastAcquired": nzbdate, "IssueDate": newdatish}, {"Title": bookid})
								maglist.append({
									'bookid': bookid,
									'nzbprov': nzbprov,
									'nzbtitle': nzbtitle,
									'nzburl': nzburl
									})
								new_date = new_date + 1
							else:
								logger.debug('This issue of %s is old; skipping.' % nzbtitle_formatted)
								old_date = old_date + 1
					else:
						logger.debug('NZB [%s] does not completely match search term [%s].' % (nzbtitle, bookid))
						bad_regex = bad_regex + 1

			logger.info('Found %s NZBs for %s.  %s are new, %s are old, and %s have bad date formatting' % (total_nzbs, bookid, new_date, old_date, bad_regex) )
	return maglist
