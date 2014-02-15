import unittest,os, sys

#from lazylibrarian import  versioncheck
import lazylibrarian
from lazylibrarian import  versioncheck,version

#
# These tests MUST be executed in the root PROG_DIR directory. Otherwise
# test for GIT install doesn't work correctly
#execution is via  python -m unittest discover -s lazylibrarian/unittests/ -v



class VersionCheckTest(unittest.TestCase):

    
   def setUp(self):
        pass

   def tearDown(self):
        lazylibrarian.INSTALL_TYPE = ''
        lazylibrarian.PROG_DIR = ''
        version.LAZYLIBRARIAN_VERSION =  ''
        
        
#Check setVersion function
   def test_getInstallTypeGIT(self):
       lazylibrarian.PROG_DIR = os.path.dirname(os.path.abspath(__file__))
      
       result = versioncheck.getInstallType()
       self.assertEquals("git",lazylibrarian.INSTALL_TYPE)
       
   def test_getInstallTypeWIN(self):
       version.LAZYLIBRARIAN_VERSION = 'win32build'
       result = versioncheck.getInstallType()
       self.assertEquals("win",lazylibrarian.INSTALL_TYPE)
       self.assertEquals("Windows",lazylibrarian.CURRENT_BRANCH)
        
   def test_getInstallTypeSource(self):
       lazylibrarian.PROG_DIR = '/tmp'
       result = versioncheck.getInstallType()
       self.assertEquals("source",lazylibrarian.INSTALL_TYPE)
       self.assertEquals("master",lazylibrarian.CURRENT_BRANCH)
       





#getCurrentBranch returns branch name of current install. 
#for most it should be master.
   def test_getCurrentBranch(self):
        lazylibrarian.INSTALL_TYPE = 'git'
        
        #doesn't work as tests are in unittest directory. so it doesn't pick up the root install dir
        lazylibrarian.PROG_DIR = os.path.dirname(os.path.abspath(__file__))
        result = versioncheck.getCurrentGitBranch()
        self.assertEquals("master",result)

#IF you have a windows or non git based install this should return "NON GIT INSTALL"
   def test_getCurrentBranchForNonGITInstalls(self):
        lazylibrarian.INSTALL_TYPE = 'win'
        result = versioncheck.getCurrentGitBranch()
        self.assertEquals("NON GIT INSTALL",result)


#
#getVersion Unit test - 4 options
#No install type set
#Install type - win, git, source
#check responses back from each setting is correct.
   def test_getCurrentVersion(self):
        result = versioncheck.getCurrentVersion()
        self.assertEquals("Install type not set",result)

#can never pass as the version should alwayscheck next version
   def test_getCurrentVersion_ForGIT(self):
        lazylibrarian.INSTALL_TYPE = 'git'
        lazylibrarian.PROG_DIR = os.path.dirname(os.path.abspath(__file__))
        #lazylibrarian.PROG_DIR = 'doesnt matter'
        result = versioncheck.getCurrentVersion()
        self.assertEquals("ac3be411f792c62895ad16bc120d92eaf44345c2",result)

   def test_getCurrentVersion_ForWindows(self):
       #Over write the version file value
        lazylibrarian.INSTALL_TYPE = 'win'
        result = versioncheck.getCurrentVersion()
        self.assertEquals("Windows Install",result)

   def test_getCurrentVersion_ForSource(self):
       #Over write the version file value
        lazylibrarian.INSTALL_TYPE = 'source'
        result = versioncheck.getCurrentVersion()
        self.assertEquals("test-version-file",result)





#simple git test, just check a version is returned but not care about the version number
   def test_runGit(self):
       lazylibrarian.PROG_DIR = os.path.dirname(os.path.abspath(__file__))
       output, err = versioncheck.runGit('--version')
       self.assertTrue(output.strip().startswith('git version'))

   def test_getLatestVersion_GIT(self):
       lazylibrarian.INSTALL_TYPE = 'git'
       lazylibrarian.PROG_DIR = os.path.dirname(os.path.abspath(__file__))
       result = versioncheck.getLatestVersion()
       self.assertEquals(lazylibrarian.LATEST_VERSION, result)
       
   def test_getLatestVersion_SOURCE(self):
       lazylibrarian.INSTALL_TYPE = 'source'
       lazylibrarian.PROG_DIR = os.path.dirname(os.path.abspath(__file__))
       result = versioncheck.getLatestVersion()
       self.assertEquals(lazylibrarian.LATEST_VERSION, result)

   def test_getLatestVersion_WIN(self):
       lazylibrarian.INSTALL_TYPE = 'win'
       result = versioncheck.getLatestVersion()
       self.assertEquals("WIN INSTALL",result)

   def test_getLatestVersion(self):
       result = versioncheck.getLatestVersion()
       self.assertEquals("UNKNOWN INSTALL",result)


   def test_getLatestVersionaFromGit_TypeWin(self):
       lazylibrarian.INSTALL_TYPE = 'win'
       result = versioncheck.getLatestVersionaFromGit()
       self.assertEquals("WINDOWS INSTALL",result)

   def test_getLatestVersionaFromGit_TypeGit(self):
       lazylibrarian.INSTALL_TYPE = 'git'
       lazylibrarian.PROG_DIR = os.path.dirname(os.path.abspath(__file__))
       result = versioncheck.getLatestVersionaFromGit()
#       self.assertEquals('ac3be411f792c62895ad16bc120d92eaf44345c2',result)
       pass


   def test_updateVersionFile(self):
        pass
        
        
#tests todo
#OS Install
#auto update on/off

if __name__ == '__main__':
    unittest.main()

