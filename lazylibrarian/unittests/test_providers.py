import unittest

from lazylibrarian import  providers

from xml.etree import ElementTree

class ProvidersTest(unittest.TestCase):

   def test_ReturnSearchTypeStructureForBook(self):
        result = providers.ReturnSearchTypeStructure('api_key', {"bookid": 'bookid', "bookName":'bookname', "authorName":'author', "searchterm": 'term'}, 'book')
        self.assertEquals ({'author': 'author', 'apikey': 'api_key', 't': 'book', 'cat': 7020, 'title': 'bookname'},result)

   def test_ReturnSearchTypeStructureForMag(self):
        result = providers.ReturnSearchTypeStructure('api_key', {"bookid": 'bookid', "bookName":'bookname', "authorName":'author', "searchterm": 'term'}, 'mag')
        self.assertEquals( {'q': 'term', 'apikey': 'api_key', 't': 'search', 'extended': 1, 'cat': 7020},result)

   def test_ReturnSearchTypeStructureForGeneral(self):
        result = providers.ReturnSearchTypeStructure('api_key', {"bookid": 'bookid', "bookName":'bookname', "authorName":'author', "searchterm": 'term'}, None)
        self.assertEquals( {'q': 'term', 'apikey': 'api_key', 't': 'search', 'extended': 1, 'cat': 7020},result)

   def test_ReturnResultsFieldsBySearchTypeForBook(self):
        book = {"bookid": 'input_bookid', "bookName":'input_bookname', "authorName":'input_authorname', "searchterm": 'safe_searchterm'}

        newsnabplus_resp = '''<?xml version="1.0" encoding="utf-8"?>
                <rss xmlns:atom="http://www.w3.org/2005/Atom" xmlns:newznab="http://www.newznab.com/DTD/2010/feeds/attributes/" version="2.0">
                       <channel>
                              <atom:link href="queryhere" rel="self" type="application/rss+xml"></atom:link>
                              <title>usenet-crawler</title>
                              <description>usenet-crawler Feed</description>
                              <link>http://www.usenet-crawler.com/</link>
                              <language>en-gb</language>
                              <webMaster>info@usenet-crawler.com (usenet-crawler)</webMaster>
                              <category></category>
                              <image>
                                     <url>http://www.usenet-crawler.com/templates/default/images/banner.jpg</url>
                                     <title>usenet-crawler</title>
                                     <link>http://www.usenet-crawler.com/</link>
                                     <description>Visit usenet-crawler - A quick usenet indexer</description>
                                 </image>
                              <newznab:response offset="0" total="3292"></newznab:response>
                              <item>
                                     <title>Debbie Macomber - When First They Met (html)</title>
                                     <guid isPermaLink="true">http://www.usenet-crawler.com/details/1c055031d3b32be8e2b9eaee1e33c315</guid>
                                     <link>http</link>
                                     <comments>http://www.usenet-crawler.com/details/1c055031d3b32be8e2b9eaee1e33c315#comments</comments>
                                     <pubDate>Sat, 02 Mar 2013 06:51:28 +0100</pubDate>
                                     <category>Books > Ebook</category>
                                     <description>Debbie Macomber - When First They Met (html)</description>
                                     <enclosure url="http" length="192447" type="application/x-nzb"></enclosure>
                                     <newznab:attr name="category" value="7000"></newznab:attr>
                                     <newznab:attr name="category" value="7020"></newznab:attr>
                                     <newznab:attr name="size" value="192447"></newznab:attr>
                                     <newznab:attr name="guid" value="1c055031d3b32be8e2b9eaee1e33c315"></newznab:attr>
                                 </item>
                          </channel>
                   </rss>                '''
        resultxml = ElementTree.fromstring(newsnabplus_resp).getiterator('item')
        nzb = iter(resultxml).next()
        result = providers.ReturnResultsFieldsBySearchType(book, nzb, 'mag', 'hostname')
        #self.maxDiff = None
        self.assertEquals({'bookid': 'input_bookid', 'nzbdate': 'Sat, 02 Mar 2013 06:51:28 +0100', 'nzbtitle': 'Debbie Macomber - When First They Met (html)', 'nzbsize': '192447', 'nzburl': 'http', 'nzbprov': 'hostname'},result)
        
    
   def test_ReturnResultsFieldsBySearchTypeForMag(self):
        book = {"bookid": 'input_bookid', "bookName":'input_bookname', "authorName":'input_authorname', "searchterm": 'safe_searchterm'}

        newsnabplus_resp = '''<?xml version="1.0" encoding="utf-8" ?> 
            <rss version="2.0" xmlns:atom="http://www.w3.org/2005/Atom" xmlns:newznab="http://www.newznab.com/DTD/2010/feeds/attributes/">
                <channel>
                    <atom:link href="http://www.usenet-crawler.com/api?q=scientific+american&amp;apikey=78c0509bc6bb91742ae0a0b6231e75e4&amp;t=search&amp;extended=1&amp;cat=7020" rel="self" type="application/rss+xml" />
                    <title>usenet-crawler</title>
                    <description>usenet-crawler Feed</description>
                    <link>http://www.usenet-crawler.com/</link>
                    <language>en-gb</language>
                    <webMaster>info@usenet-crawler.com (usenet-crawler)</webMaster>
                    <category></category>
                    <image>
                        <url>http://www.usenet-crawler.com/templates/default/images/banner.jpg</url>
                        <title>usenet-crawler</title>
                        <link>http://www.usenet-crawler.com/</link>
                        <description>Visit usenet-crawler - A quick usenet indexer</description>
                    </image>

                    <newznab:response offset="0" total="3292" />
                    <item>
                        <title>Scientific.American.SCIAM.November.20.3</title>
                        <guid isPermaLink="true">http://www.usenet-crawler.com/details/6814309804e3648c58a9f23345c2a28a</guid>
                        <link>http://www.usenet-crawler.com/getnzb/6814309804e3648c58a9f23345c2a28a.nzb&amp;i=155518&amp;r=78c0509bc6bb91742ae0a0b6231e75e4</link>
                        <comments>http://www.usenet-crawler.com/details/6814309804e3648c58a9f23345c2a28a#comments</comments> 	
                        <pubDate>Thu, 21 Nov 2013 16:13:52 +0100</pubDate> 
                        <category>Books &gt; Ebook</category> 	
                        <description>Scientific.American.SCIAM.November.20.3</description>
                        <enclosure url="http://www.usenet-crawler.com/getnzb/6814309804e3648c58a9f23345c2a28a.nzb&amp;i=155518&amp;r=78c0509bc6bb91742ae0a0b6231e75e4" length="20811405" type="application/x-nzb" />

                        <newznab:attr name="category" value="7000" />
                        <newznab:attr name="category" value="7020" />
                        <newznab:attr name="size" value="20811405" />
                        <newznab:attr name="guid" value="6814309804e3648c58a9f23345c2a28a" />
                        <newznab:attr name="files" value="4" />
                        <newznab:attr name="poster" value="TROLL &lt;EBOOKS@town.ag&gt;" />

                        <newznab:attr name="grabs" value="10" />
                        <newznab:attr name="comments" value="0" />
                        <newznab:attr name="password" value="0" />
                        <newznab:attr name="usenetdate" value="Thu, 21 Nov 2013 12:13:01 +0100" />
                        <newznab:attr name="group" value="alt.binaries.ebook" />
                    </item>
                </channel>
            </rss>                '''
        #Take the above xml, parse it into element tree, extract the item from it
        #could have just put in item text, but took live example
        resultxml = ElementTree.fromstring(newsnabplus_resp).getiterator('item')
        nzb = iter(resultxml).next()
        result = providers.ReturnResultsFieldsBySearchType(book, nzb, 'mag', 'hostname')
        self.assertEquals({'bookid': 'input_bookid', 'nzbdate': 'Thu, 21 Nov 2013 16:13:52 +0100', 'nzbtitle': 'Scientific.American.SCIAM.November.20.3', 'nzbsize': '20811405', 'nzburl': 'http://www.usenet-crawler.com/getnzb/6814309804e3648c58a9f23345c2a28a.nzb&i=155518&r=78c0509bc6bb91742ae0a0b6231e75e4', 'nzbprov': 'hostname'},result)
        
   def test_ReturnResultsFieldsBySearchTypeForGeneral(self):
        book = {"bookid": 'input_bookid', "bookName":'input_bookname', "authorName":'input_authorname', "searchterm": 'safe_searchterm'}

        newsnabplus_resp = '''<?xml version="1.0" encoding="utf-8" ?> 
            <rss version="2.0" xmlns:atom="http://www.w3.org/2005/Atom" xmlns:newznab="http://www.newznab.com/DTD/2010/feeds/attributes/">
                <channel>
                    <atom:link href="http://www.usenet-crawler.com/api?q=scientific+american&amp;apikey=78c0509bc6bb91742ae0a0b6231e75e4&amp;t=search&amp;extended=1&amp;cat=7020" rel="self" type="application/rss+xml" />
                    <title>usenet-crawler</title>
                    <description>usenet-crawler Feed</description>
                    <link>http://www.usenet-crawler.com/</link>
                    <language>en-gb</language>
                    <webMaster>info@usenet-crawler.com (usenet-crawler)</webMaster>
                    <category></category>
                    <image>
                        <url>http://www.usenet-crawler.com/templates/default/images/banner.jpg</url>
                        <title>usenet-crawler</title>
                        <link>http://www.usenet-crawler.com/</link>
                        <description>Visit usenet-crawler - A quick usenet indexer</description>
                    </image>

                    <newznab:response offset="0" total="3292" />
                    <item>
                        <title>Scientific.American.SCIAM.November.20.3</title>
                        <guid isPermaLink="true">http://www.usenet-crawler.com/details/6814309804e3648c58a9f23345c2a28a</guid>
                        <link>http://www.usenet-crawler.com/getnzb/6814309804e3648c58a9f23345c2a28a.nzb&amp;i=155518&amp;r=78c0509bc6bb91742ae0a0b6231e75e4</link>
                        <comments>http://www.usenet-crawler.com/details/6814309804e3648c58a9f23345c2a28a#comments</comments> 	
                        <pubDate>Thu, 21 Nov 2013 16:13:52 +0100</pubDate> 
                        <category>Books &gt; Ebook</category> 	
                        <description>Scientific.American.SCIAM.November.20.3</description>
                        <enclosure url="http://www.usenet-crawler.com/getnzb/6814309804e3648c58a9f23345c2a28a.nzb&amp;i=155518&amp;r=78c0509bc6bb91742ae0a0b6231e75e4" length="20811405" type="application/x-nzb" />

                        <newznab:attr name="category" value="7000" />
                        <newznab:attr name="category" value="7020" />
                        <newznab:attr name="size" value="20811405" />
                        <newznab:attr name="guid" value="6814309804e3648c58a9f23345c2a28a" />
                        <newznab:attr name="files" value="4" />
                        <newznab:attr name="poster" value="TROLL &lt;EBOOKS@town.ag&gt;" />

                        <newznab:attr name="grabs" value="10" />
                        <newznab:attr name="comments" value="0" />
                        <newznab:attr name="password" value="0" />
                        <newznab:attr name="usenetdate" value="Thu, 21 Nov 2013 12:13:01 +0100" />
                        <newznab:attr name="group" value="alt.binaries.ebook" />
                    </item>
                </channel>
            </rss>                '''
        #Take the above xml, parse it into element tree, extract the item from it
        #could have just put in item text, but took live example
        resultxml = ElementTree.fromstring(newsnabplus_resp).getiterator('item')
        nzb = iter(resultxml).next()
        result = providers.ReturnResultsFieldsBySearchType(book, nzb, None, 'hostname')
        self.assertEquals({'bookid': 'input_bookid', 'nzbdate': 'Thu, 21 Nov 2013 16:13:52 +0100', 'nzbtitle': 'Scientific.American.SCIAM.November.20.3', 'nzbsize': '20811405', 'nzburl': 'http://www.usenet-crawler.com/getnzb/6814309804e3648c58a9f23345c2a28a.nzb&i=155518&r=78c0509bc6bb91742ae0a0b6231e75e4', 'nzbprov': 'hostname'},result)


if __name__ == '__main__':
    unittest.main()

