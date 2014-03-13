## LazyLibrarian

### 2014 ###
Jan,20 Exciting news update. TheGuardian has gracefully agreed to review the code base with a view to bringing in his improvements into the new UI. All going well this branch will hopefully include
- Twitter notifications
- magasine search
- improved configurations
- optimised UI workflow to the Herman-Rodgers UI

And a shout out to nncrypted for bring forth changes and enhancement patches also.

Thanks folks, because I was going cross-eyed trying to bring in the huge volume of changes you both have added to the original branch over a new UI.


To all other contributors - Patches are gratefully received espically when they can be auto merged :).

Thanks - DobyTang


Drive for this year is unit test expansion
New Features
Stability


##### Dec 2013 #####
Back after a hectic 6 months, apologies for the late update of branch back to master.
Thats now complete.

Notice a few forks from the branches, happy to facilitate pull requests, i've alot more time over the next two weeks.

issues list is open again for additions


#### LazyLibrarian
LazyLibrarian is a program to follow authors and grab metadata for all your digital reading needs. 
It uses Goodreads.com (for author info and book info) websites as a source. License: GNU GPL v3 

Right now its capable of the following:  
* Find authors and add them to the database  
* List all books of an author and add them as 'wanted'.  
* LazyLibrarian will search a nzb-file for that book (only Newznab and nzbmatrix are currently supported)  
* If a nzb is found it will be send to sabnzbd or saved in a blackhole where your downloadapp can pick it up.  
* When processing the downloaded books it will save a coverpicture (if available) and save all metadata into metadata.opf next to the bookfile (calibre compatible format)
* The new theme for the site allows it to be accessed (and usable) from devices with a smaller screen (such as an iPad)
* AutoAdd feature for book management tools like Calibre which must have books in flattened directory structure
* Added Usenet Crawler configuration + 2 NZB configurations (alas NZBMatrix is gone and removed)

##Screenshots
<img src="http://i.imgur.com/O8awy.png" width="600">
<img src="http://i.imgur.com/fr0yE.png" width="600">
<img src="http://i.imgur.com/AOgh1.png" width="600">

## Install:  
LazyLibrarian runs by default on port 5299 at http://localhost:5299/

Linux / Mac OS X:

* Install Python 2.6 or higher  
* Git clone/extract LL wherever you like  
* Run "python LazyLibrarian.py -d" to start in deamon mode  
* Fill in all the config fields
=======
* Run "python LazyLibrarian.py -daemon" to start in deamon mode  
* Set your username & password in the settings if you want.  
* Fill in all the config stuff  


## Update
Auto update available via interface from master

## Remarks
Need an logo/favicon/icon badly. Made a temporary one. If you feel creative, go ahead. 
