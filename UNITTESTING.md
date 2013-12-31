#
# Dec 2013
#
#starting to introduce some form of BDD/TDD testing using the simple unittest tools

I am by no means an exprt on TDD/BDD. My aim is to start simple.

Inspiration is Uncle Bob - The Clean Coder and Clean Code books (Robert Martin). I had the pleasure of seeing him at work in the office in Dublin, and it was amazing. Simple genius always is.

So my attempts will revolve around the "Boy Scout Rule" - Code must be no worse after I touch it.

To achieve this I hope to 
- create unit test(s) around the function I'm changing
- create new test(s) for the change required [these will be broken until code added]
- refactor the area of change into logical smaller functions
- make the change and check in once all tests pass.




#
#Requires
#
unittest for python

 sudo apt-get install python-setuptools


#
#Execution
#- run from the Lazylibrarian root directory (directory where LazyLibrarian.py exists)
python -m unittest discover lazylibrarian/unittests/

expected output looks as follows (the two periods indicate 2 tests run)
..
----------------------------------------------------------------------
Ran 2 tests in 0.001s

OK
