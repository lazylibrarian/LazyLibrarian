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

	if not lazylibrarian.SAB_HOST and not lazylibrarian.NZB_DOWNLOADER_BLACKHOLE and not lazylibrarian.NZB_DOWNLOADER_NZBGET:
		logger.info('No download method is set, use SABnzbd/NZBGet or blackhole')

	if not lazylibrarian.NEWZNAB and not lazylibrarian.NEWZNAB2 and not lazylibrarian.USENETCRAWLER:
		logger.info('No providers are set. try use NEWZNAB.')

	if searchlist == []:
		logger.info('There is nothing to search for.  Mark some magazines as active.')

	for book in searchlist:
		
		resultlist = providers.IterateOverNewzNabSites(book,'mag')

		if not resultlist:
			logger.debug("Adding magazine %s to queue." % book['searchterm'])

		else:
			bad_regex = 0
			old_date = 0
			total_nzbs = 0
			new_date = 0
			for nzb in resultlist:                		
				total_nzbs = total_nzbs + 1
				bookid = nzb['bookid']
				nzbtitle = (u"%s" % nzb['nzbtitle'])
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

					nzbtitle_formatted = nzb['nzbtitle'].replace('.',' ').replace('-',' ').replace('/',' ').replace('+',' ').replace('_',' ').replace('(','').replace(')','')
					#Need to make sure that substrings of magazine titles don't get found (e.g. Maxim USA will find Maximum PC USA)
					keyword_check = nzbtitle_formatted.replace(bookid,'')
					#remove extra spaces if they're in a row
					nzbtitle_exploded_temp = " ".join(nzbtitle_formatted.split())
					nzbtitle_exploded = nzbtitle_exploded_temp.split(' ')

					bookid_exploded = bookid.split(' ')

					# check nzb starts with magazine title, and ends with a date
					# eg The MagPI Issue 22 - July 2015
					# do something like check left n words match title
					# then check last n words are a date
					
					name_match = 1 # assume name matches for now
					name_len = len(bookid_exploded)
					if len(nzbtitle_exploded) > name_len: # needs to be longer as it should include a date
					    while name_len:
						name_len = name_len - 1
						if nzbtitle_exploded[name_len].lower() != bookid_exploded[name_len].lower():
							name_match = 0 # name match failed
					if name_match:	
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

						if control_date is None: # we haven't got any copies of this magazine yet
							# get a rough time just over a month ago to compare to, in format yyyy-mm-dd
							# could perhaps calc differently for weekly, biweekly etc
							start_time = time.time()
							start_time -= 31*24*60*60 # number of seconds in 31 days
							control_date = time.strftime("%Y-%m-%d", time.localtime(start_time))
					
						# only grab a copy if it's newer than the most recent we have, or newer than a month ago if we have none
						comp_date = formatter.datecompare(newdatish, control_date)
						if comp_date > 0:
							myDB.upsert("magazines", {"LastAcquired": nzbdate, "IssueDate": newdatish}, {"Title": bookid})
							maglist.append({
								'bookid': bookid,
								'nzbprov': nzbprov,
								'nzbtitle': nzbtitle,
								'nzburl': nzburl
								})
							logger.debug('This issue of %s is new, downloading' % nzbtitle_formatted)
							new_date = new_date + 1
						else:
							logger.debug('This issue of %s is old; skipping.' % nzbtitle_formatted)
							old_date = old_date + 1
					else:
						logger.debug('NZB [%s] does not completely match search term [%s].' % (nzbtitle, bookid))
						bad_regex = bad_regex + 1

			logger.info('Found %s NZBs for %s.  %s are new, %s are old, and %s fail name or date matching' % (total_nzbs, bookid, new_date, old_date, bad_regex) )
	return maglist
