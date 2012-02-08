## LazyLibrarian

Author: Mar2zz  
Blogs: mar2zz.tweakblogs.net  
License: GNU GPL v3  

Feel free to post issues and featurerequests @ https://github.com/Mar2zz/LazyLibrarian/issues,  
though I am aware of the many bugs right now, and am solving them one at a time, LL is very alpha, so use at own risk!.  

There may be many non working options/links during this Work In Progress-stage.

If you know css very well, feel free to change the look by adding pull-requests, I am aware of the fact that it is one ugly monstrous webapp right now  

##Screenshot
<img src="http://tweakers.net/ext/f/nRWbGC8qWH2y2BqYNVHUJuIn/full.png" width="800">
<img src="http://tweakers.net/ext/f/4gmyYa6Wf8zcd0WpbanIGFwl/full.png" width="800">

Yes, there is a lot of headphones references in this project. In fact, I used headphones as a base, but also code from SickBeard and CouchPotato to learn how to write a python program.
It's a goal to eliminate all references to these other projects, but I need to create a working program first. Taking babysteps ;)

LazyLibrarian is a program to follow authors and grab metadata for all your digital reading needs. It uses the extensive Goodreads.com website as a source, but I'd like to write locales too (like bol.com for dutch info. Other languages need to be added by others).

Right now its capable of the following:  
* find authors or books and add them to the database  
* list all books of an author and add them as 'wanted'.  
* LazyLibrarian will search a nzb-file for that book (only Newznab supported (e.g. nzb.su)  
* If a nzb is found it will be send to sabnzbd or saved in a blackhole where your downloadapp can pick it up.  

## Install:

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




