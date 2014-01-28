import unittest

from lazylibrarian import  providers


class ProvidersTest(unittest.TestCase):

   def test_ReturnSearchTypeStructureForBook(self):
        result = providers.ReturnSearchTypeStructure('api_key', {"bookid": 'bookid', "bookName":'bookname', "authorName":'author', "searchterm": 'term'}, 'book')
        self.assertEquals("abc",result)

   def test_ReturnSearchTypeStructureForMag(self):
        result = providers.ReturnSearchTypeStructure('api_key', {"bookid": 'bookid', "bookName":'bookname', "authorName":'author', "searchterm": 'term'}, 'mag')
        self.assertEquals("abc",result)

   def test_ReturnSearchTypeStructureForGeneral(self):
        result = providers.ReturnSearchTypeStructure('api_key', {"bookid": 'bookid', "bookName":'bookname', "authorName":'author', "searchterm": 'term'}, None)
        self.assertEquals("abc",result)


if __name__ == '__main__':
    unittest.main()

