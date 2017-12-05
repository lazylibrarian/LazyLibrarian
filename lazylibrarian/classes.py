#  This file is part of LazyLibrarian.
#
#  LazyLibrarian is free software: you can redistribute it and/or modify
#  it under the terms of the GNU General Public License as published by
#  the Free Software Foundation, either version 3 of the License, or
#  (at your option) any later version.
#
#  LazyLibrarian is distributed in the hope that it will be useful,
#  but WITHOUT ANY WARRANTY; without even the implied warranty of
#  MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
#  GNU General Public License for more details.
#
#  You should have received a copy of the GNU General Public License
#  along with LazyLibrarian.  If not, see <http://www.gnu.org/licenses/>.

#
# Stolen from Sick-Beard's classes.py ##
#


class SearchResult:

    """
    Represents a search result from an indexer.
    """

    def __init__(self):
        self.provider = ""

        # URL to the NZB/torrent file
        self.url = ""

        # used by some providers to store extra info associated with the result
        self.extraInfo = []

        # release name
        self.name = ""

    def __str__(self):

        if self.provider is None:
            return "Invalid provider, unable to print self"

        # noinspection PyUnresolvedReferences
        myString = self.provider.name + " @ " + self.url + "\n"
        myString += "Extra Info:\n"
        for extra in self.extraInfo:
            myString += "  " + extra + "\n"
        return myString


class NZBSearchResult(SearchResult):

    """
    Regular NZB result with an URL to the NZB
    """
    resultType = "nzb"


class NZBDataSearchResult(SearchResult):

    """
    NZB result where the actual NZB XML data is stored in the extraInfo
    """
    resultType = "nzbdata"


class TorrentSearchResult(SearchResult):

    """
    Torrent result with an URL to the torrent
    """
    resultType = "torrent"
