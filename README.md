## LazyLibrarian
LazyLibrarian is a program to follow authors and grab metadata for all your digital reading needs.
It uses a combination of [Goodreads](https://www.goodreads.com/) [Librarything](https://www.librarything.com/) and optionally [GoogleBooks](https://www.googleapis.com/books/v1/) as sources for author info and book info. License: GNU GPL v3

Right now it's capable of the following:
* Import an existing calibre library (optional)
* Find authors and add them to the database
* List all books of an author and add them as 'wanted'.
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

##Screenshots
<img src="http://i.imgur.com/O8awy.png" width="600">
<img src="http://i.imgur.com/fr0yE.png" width="600">
<img src="http://i.imgur.com/AOgh1.png" width="600">

## Install:
LazyLibrarian runs by default on port 5299 at http://localhost:5299

Linux / Mac OS X:

* Install Python 2.6 or higher
* Git clone/extract LL wherever you like
* Run "python LazyLibrarian.py -d" to start in daemon mode
* Fill in all the config (see [Configuration Wiki](https://github.com/DobyTang/LazyLibrarian/wiki/Configuration) for full configuration)

* Start in daemon mode with `python LazyLibrarian.py -daemon`

## Minimal Configuration (uTorrent):
This is the bare minimum to get you up and running. For more options see the [Configuration Wiki](https://github.com/DobyTang/LazyLibrarian/wiki/Configuration).

### Downloaders
- Open localhost:5299/config
- Select Downloaders tab and check the uTorrent box.
- Host: localhost
- Port: Found in "uTorrent | Options Menu | Preferences | Connections | Port used for incoming connections"
- In "uTorrent settings | Advanced | WebUI" check Enable WebUI and make a username and password. Fill that username and password in to LazyLibrarian.
- In Download Settings Directory in Lazylibrarian change the path to where uTorrent keeps your completed downloads.
Found in "uTorrent Settings | Directories | Move completed downloads to"

### Providers
Check some or all of the torrent provider boxes.

### Processing
In "Folders | Base Destination Folder" type the directory where you want to keep the books LazyLib downloads. For example putting a books folder in Documents. The system documents folder for windows is "C:\Users\USERNAME\Documents\Books\" where USERNAME is your Windows User Name.

### Usage
Open localhost:5299/home or click the LazyLibrarian icon in the top left. Type a book or author name into the top right search bar. Then on the search results screen select "Add Book" to make LazyLib start searching for the book. Not all books can be found instantly, but LazyLib will keep searching!


## Update
Auto update available via interface from master for git and source installs

## Packages
rpm and deb packages here : https://github.com/DobyTang/LazyLibrarian/releases  
AUR package available here: https://aur.archlinux.org/packages/lazylibrarian/  

## Docker packages
x64 version here  : https://hub.docker.com/r/linuxserver/lazylibrarian/  
armhf version here: https://hub.docker.com/r/lsioarmhf/lazylibrarian/
