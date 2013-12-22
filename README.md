## LazyLibrarian
#### Contributers 
* Current author: DobyTang
  Branched from Herman-Rodgers
* Original author: Mar2zz  
* Previous maintainer: itsmegb   , Herman Rodgers


##### Dec 2013 #####
Back after a hectic 6 months, apologies for the late update of branch back to master.
Thats now complete.

Notice a few forks from the branches, happy to facilitate pull requests, i've alot more time over the next two weeks.

issues list is open again for additions

<<<<<<< HEAD
##### NOTICE JUNE 2013 ######
DobyTang on vacation - back in July - please note
=======
#### June 2013
I won't say I have taken over, but am willing to contribute and move this forward with the demise of many NZB sites

DobyTang on vacation - back in July - please note

Two branches currently exist
- Master - ported from Mar2zz, standard interface with Usenet, Calibre Auto Add and better logging - tested that bit more
  If you want safer, clone from here as normal git clone ......

- Herman-Rodgers-Branch - merged with changes by Herman which include auto update, 2nd NZB configuration, book type restriction
  - Stable but only has had a week of verification as of June 10th
  - if you want better experience, or willing to contribute clone from here 
  - $> git clone -b herman-rogers-merge https://github.com/DobyTang/LazyLibrarian.git

- If anyone is making changes could the fork this branch rather than master as there is ALOT of changes and if we hope to make this branch the master it would be easier later to meld them.

See ya'll in a few weeks - Niagra falls here I come.





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
<<<<<<< HEAD
* Run "python LazyLibrarian.py -d" to start in deamon mode  
* Fill in all the config fields
=======
* Run "python LazyLibrarian.py -daemon" to start in deamon mode  
* Set your username & password in the settings if you want.  
* Fill in all the config stuff  


## Update
Just run git pulls, build a update-through-interface soon enough available in Branch

## Remarks
Need an logo/favicon/icon badly. Made a temporary one. If you feel creative, go ahead. 
