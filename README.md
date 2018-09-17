## LazyLibrarian
LazyLibrarian is a program to follow authors and grab metadata for all your digital reading needs.
It uses a combination of [Goodreads](https://www.goodreads.com/) [Librarything](https://www.librarything.com/) and optionally [GoogleBooks](https://www.googleapis.com/books/v1/) as sources for author info and book info. License: GNU GPL v3

Right now it's capable of the following:
* Import an existing calibre library (optional)
* Find authors and add them to the database
* List all books of an author and mark ebooks or audiobooks as 'wanted'.
* LazyLibrarian will search for a nzb-file or a torrent or magnet link for that book
* If a nzb/torrent/magnet is found it will be sent to a download client or saved in a black hole where your download client can pick it up.
* Currently supported download clients for usenet are :
- sabnzbd (versions later than 0.7.x preferred)
- nzbget
- synology_downloadstation
* Currently supported download clients for torrent and magnets are:
- deluge
- transmission
- utorrent
- qbittorrent
- rtorrent
- synology_downloadstation
* When processing the downloaded books it will save a cover picture (if available) and save all metadata into metadata.opf next to the bookfile (calibre compatible format)
* The new theme for the site allows it to be accessed (and usable) from devices with a smaller screen (such as an iPad)
* AutoAdd feature for book management tools like Calibre which must have books in flattened directory structure, or use calibre to import your books into an existing calibre library
* LazyLibrarian can also be used to search for and download magazines, and monitor for new issues

## Screenshots
<img src="http://i.imgur.com/O8awy.png" width="600">
<img src="http://i.imgur.com/fr0yE.png" width="600">
<img src="http://i.imgur.com/AOgh1.png" width="600">

## Install:
LazyLibrarian runs by default on port 5299 at http://localhost:5299

Linux / Mac OS X:

* Install Python 2 v2.6 or higher, or Python 3 v3.5 or higher 
* Git clone/extract LL wherever you like
* Run "python LazyLibrarian.py -d" to start in daemon mode
* Fill in all the config (see [Configuration Wiki](https://github.com/DobyTang/LazyLibrarian/wiki/Configuration) for full configuration)

* Start in daemon mode with `python LazyLibrarian.py -daemon`

## Documentation:
There is a wiki at https://github.com/DobyTang/LazyLibrarian/wiki   
and a reddit at https://www.reddit.com/r/LazyLibrarian/   

Docker tutorial here http://sasquatters.com/lazylibrarian-docker/   
Config tutorial here http://sasquatters.com/lazylibrarian-configuration/   
(thanks @mccorkled)   

For more options see the [Wiki](https://github.com/DobyTang/LazyLibrarian/wiki/).

## Update
Auto update available via interface from master for git and source installs

## Packages
rpm deb and snap packages here : https://github.com/DobyTang/LazyLibrarian/releases  
The snap package is confined to users home directory, so all books and downloads need to be accessible from there too.
Install the snap package with flags --dangerous --devmode  
AUR package available here: https://aur.archlinux.org/packages/lazylibrarian/  
QNAP LazyLibrarian is now available for the QNAP NAS via sherpa. https://forum.qnap.com/viewtopic.php?f=320&t=132373v

## Docker packages
armhf version here : https://hub.docker.com/r/lsioarmhf/lazylibrarian/  
x64 version here   : https://hub.docker.com/r/linuxserver/lazylibrarian/    
with calibredb here: https://hub.docker.com/r/thraxis/lazylibrarian-calibre/
