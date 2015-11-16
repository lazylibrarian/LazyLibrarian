import unittest

from lazylibrarian import searchnzb


class SearchNZBTest(unittest.TestCase):

    def test_MakeSearchTermWebSafe(self):
        result = searchnzb.MakeSearchTermWebSafe("abc")
        self.assertEquals("abc", result)

    def test_MakeSearchTermWebSafe2(self):
        result = searchnzb.MakeSearchTermWebSafe("a + b?c")
        self.assertEquals("a bc", result)


if __name__ == '__main__':
    unittest.main()
