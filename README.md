## LazyLibrarian

#### IMPORTANT UPDATE
As Mar2zz can no longer maintain LazyLibrarian, i have taken over.
I don't have a lot of free time, but i will try my best to get a usable application.

itsmegb

#### PLEASE READ THE FOLLOWING
Due to personal reasons I can't find the time anymore to work on this project. If you like it and know you way around in python, create a master repo of this for yourself and continue developing. Sometimes I have some minutes to spare, so I will contribute to your repo, but between now and a year ahead I am too busy with other projects that consume all 'spare' time that I have. So if you like to be master of a gitproject, feel free to use LazyLibrarian for it. When someone else has started developing in another repo I will delete this one and clone the other repo here.

To create a masterrepo: clone lazylibrarian into a folder, delete the .git folder inside and follow the normal instructions to start/upload your own repo.
#### IMPORTANT

Author: Mar2zz  
Blogs: mar2zz.tweakblogs.net  
License: GNU GPL v3  


LazyLibrarian is a program to follow authors and grab metadata for all your digital reading needs. It uses the extensive GoogleBooks (for bookinfo) and Goodreads.com (for authorinfo) websites as a source, but I'd like to write locales too (like bol.com for dutch info. Other languages need to be added by others).  

Feel free to post issues and featurerequests @ https://github.com/Mar2zz/LazyLibrarian/issues,  
though I am aware of the many bugs right now, and am solving them one at a time, LL is very alpha, so use at own risk!.  

There may be many non working options/links during this Work In Progress-stage.

If you know css very well, feel free to change the look by adding pull-requests, I am aware of the fact that it is one ugly monstrous webapp right now  

##Screenshot
<img src="http://tweakers.net/ext/f/nRWbGC8qWH2y2BqYNVHUJuIn/full.png" width="800">
<img src="http://tweakers.net/ext/f/4gmyYa6Wf8zcd0WpbanIGFwl/full.png" width="800">

Yes, it looks like headphones, that's because I am using it's datatables also for generating booktables. I also copied a lot of code from Headphones, CouchPotato and Sickbeard. I am learning python, so I hope my coding will become better with practice (consider when you laugh out loud about my code that I didn't know any python a few months ago)...  Taking babysteps ;)  

Right now its capable of the following:  
* find authors or books and add them to the database  
* list all books of an author and add them as 'wanted'.  
* LazyLibrarian will search a nzb-file for that book (only Newznab supported (e.g. nzb.su)  
* If a nzb is found it will be send to sabnzbd or saved in a blackhole where your downloadapp can pick it up.  
* When processing the downloaded books it will save a coverpicture (if available) and save all metadata into metadata.opf next to the bookfile (calibre compatible format)

## Install:  
LazyLibrarian runs by default @ port 5299 at http://hostname:5299/home.  

Linux:

* Install Python 2.6 or higher  
* Git clone/extract LL wherever you like  
* Run "python LazyLibrarian.py -daemon" to start in deamon mode  
* Set your username & password in the settings if you want.  
* Fill in all the config stuff  

Ubuntu (init.d script):

* Copy "initd.ubuntu" to /etc/init.d/lazylibrarian - > "sudo cp initd.ubuntu /etc/init.d/lazylibrarian"  
* Copy "default.ubuntu" to /etc/default/lazylibrarian - > "sudo cp default.ubuntu /etc/default/lazylibrarian"  
* Edit the required daemon settings in /etc/default/lazylibrarian - > editor /etc/default/lazylibrarian  
* If your LL installation isn't in "/opt/lazylibrarian/", make sure to change the path there also!  
* Make executable "sudo chmod a+x /etc/init.d/lazylibrarian"  
* Add it to the startup items: "sudo update-rc.d lazylibrarian defaults"  
* Start with "sudo service lazylibrarian start"  

## Update
Just run git pulls, build a update-through-interface soon enough.

## Remarks
Need an logo/favicon/icon badly. Made a temporary one. If you feel creative, go ahead. 




