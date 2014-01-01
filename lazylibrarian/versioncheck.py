import platform, subprocess, re, os, urllib2, tarfile, threading

import lazylibrarian
from lazylibrarian import logger, version

import lib.simplejson as simplejson

user = "dobytang"
#branch = "master"
repo="lazylibrarian"

#
#Function to execute GIT commands taking care of error logging etc
def runGit(args):

    git_locations = ['git']
        
    if platform.system().lower() == 'darwin':
        git_locations.append('/usr/local/git/bin/git')
        
    output = err = None
    
    for cur_git in git_locations:
    
        cmd = cur_git+' '+args
    
        try:
            logger.debug('(RunGit)Trying to execute: "' + cmd + '" with shell in ' + lazylibrarian.PROG_DIR)
            p = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, shell=True, cwd=lazylibrarian.PROG_DIR)
            output, err = p.communicate()
            logger.debug('(RunGit)Git output: [%s]' % output)
            
        except OSError:
            logger.debug('(RunGit)Command ' + cmd + ' didn\'t work, couldn\'t find git')
            continue
            
        if 'not found' in output or "not recognized as an internal or external command" in output:
            logger.debug('(RunGit)Unable to find git with command ' + cmd)
            output = None
        elif 'fatal:' in output or err:
            logger.error('(RunGit)Git returned bad info. Are you sure this is a git installation?')
            output = None
        elif output:
            break
            
    return (output, err)
            
#
#function to determine what type of install we are on & sets current Branch value
# - windows
# - git based
# - deployed source code
def getInstallType():
    
    if version.LAZYLIBRARIAN_VERSION.startswith('win32build'):
        lazylibrarian.INSTALL_TYPE = 'win'
        lazylibrarian.CURRENT_BRANCH = 'Windows'
        logger.debug('(getInstallType) [Windows] install detected. Setting Branch to [%s]' % lazylibrarian.CURRENT_BRANCH)
    
    elif os.path.isdir(os.path.join(lazylibrarian.PROG_DIR, '.git')):
        lazylibrarian.INSTALL_TYPE = 'git'
        lazylibrarian.CURRENT_BRANCH = getCurrentGitBranch()
        logger.debug('(getInstallType) [GIT] install detected. Setting Branch to [%s] ' % lazylibrarian.CURRENT_BRANCH)        
    else:      
        lazylibrarian.INSTALL_TYPE = 'source'
        lazylibrarian.CURRENT_BRANCH = 'master'
        logger.debug('(getInstallType) [Source]install detected. Setting Branch to [%s]' % lazylibrarian.CURRENT_BRANCH)

#
#Establish the version of the installed app for Source or GIT only
#Global variable set in LazyLibrarian.py on startup as it should be
def getCurrentVersion():
    version = ''

    if lazylibrarian.INSTALL_TYPE == 'win':
        logger.debug('(getCurrentVersion) Windows install - no update available')
        
        # Don't have a way to update exe yet, but don't want to set VERSION to None
        version = 'Windows Install'
        
    elif lazylibrarian.INSTALL_TYPE == 'git':
        output, err = runGit('rev-parse HEAD')
        
        if not output:
            logger.error('(getCurrentVersion) Couldn\'t find latest git installed version.')
            version = 'GIT Cannot establish version'
        else:
            cur_commit_hash = output.strip()
        
            if not re.match('^[a-z0-9]+$', cur_commit_hash):
                logger.error('(getCurrentVersion) Output doesn\'t look like a hash, not using it')
                version = 'GIT invalid hash return'
            
        version = cur_commit_hash
        
    elif lazylibrarian.INSTALL_TYPE == 'source':
        
        version_file = os.path.join(lazylibrarian.PROG_DIR, 'version.txt')
        
        if not os.path.isfile(version_file):
            version = 'No Version File'
            logger.debug('(getCurrentVersion) [%s] missing.' % version_file)
        else:
            fp = open(version_file, 'r')
            current_version = fp.read().strip(' \n\r')
            fp.close()
        
            if current_version:
                version = current_version
            else:
                version =  'No Version set in file'
    
    else:
        logger.error('(getCurrentVersion) Install Type not set - cannot get version value')
        version = 'Install type not set'
   
    updateVersionFile(version)
    logger.info('(getCurrentVersion) - Install type [%s] Local Version is set to [%s] ' % (lazylibrarian.INSTALL_TYPE,version))
    return version

#
#Returns current branch name of installed version from GIT
#return "NON GIT INSTALL" if INSTALL TYPE is not GIT
def getCurrentGitBranch():
    #Can only work for GIT driven installs, so check install type
    if lazylibrarian.INSTALL_TYPE != 'git':
        logger.debug('Non GIT Install doing check update. Return NON GIT INSTALL')
        return 'NON GIT INSTALL'
    
    # use git rev-parse --abbrev-ref HEAD which returns the name of the current branch
    current_branch, err = runGit('rev-parse --abbrev-ref HEAD')
    
    current_branch = current_branch.strip('\n')
    
    if not current_branch:
        logger.error('failed to return current branch value')
        return 'InvalidBranch'

    logger.debug('(getCurrentGitBranch) Current local branch of repo is [%s] ' % current_branch)

    return current_branch

#not sure how this is called as we have same function in webServe.py also
#ensuring both are identical for now
def checkForUpdates():
    # rename this thread
    threading.currentThread().name = "VERSIONCHECK"
    logger.debug('(checkForUpdates) Set Install Type, Current & Latest Version and Commit status')
    getInstallType()
    lazylibrarian.CURRENT_VERSION = versioncheck.getCurrentVersion()
    lazylibrarian.LATEST_VERSION = versioncheck.getLatestVersion()
    lazylibrarian.COMMITS_BEHIND = getCommitDifferenceFromGit()
    logger.debug('(checkForUpdates) Done')
    #l = checkGithub()

#Return latest version from GITHUB 
#- if GIT install return latest on current branch
#- if nonGIT install return latest from master
def getLatestVersion():
    #Can only work for GIT driven installs, so check install type
    latest_version = 'Unknown'
    lazylibrarian.COMMITS_BEHIND = 'Unknown'

    if lazylibrarian.INSTALL_TYPE == 'git':
        latest_version = getLatestVersionaFromGit()
    elif lazylibrarian.INSTALL_TYPE == 'source':
        latest_version = getLatestVersionaFromGit()
    elif lazylibrarian.INSTALL_TYPE == 'win':
        latest_version = 'WIN INSTALL'
    else:
        latest_version =  'UNKNOWN INSTALL'
        
    lazylibrarian.LATEST_VERSION = latest_version
    return latest_version
    

#Don't call directly, use getLatestVersion as wrapper.
#Also removed reference to global variable setting.
def getLatestVersionaFromGit():
    latest_version = 'Unknown'
    
    #Can only work for non Windows driven installs, so check install type
    if lazylibrarian.INSTALL_TYPE == 'win':
        logger.debug('(getLatestVersionaFromGit) Code Error - Windows install - should not be called under a windows install')
        latest_version = 'WINDOWS INSTALL'
    else:
        #check current branch value of the local git repo as folks may pull from a branch not master
        branch = lazylibrarian.CURRENT_BRANCH
        
        if (branch == 'InvalidBranch'):
            logger.debug('(getLatestVersionaFromGit) - Failed to get a valid branch name from local repo')
        else:

            # Get the latest commit available from github
            url = 'https://api.github.com/repos/%s/%s/commits/%s' % (user, repo, branch)
            logger.info ('(getLatestVersionaFromGit) Retrieving latest version information from github command=[%s]' % url)
            try:
                result = urllib2.urlopen(url).read()
                git = simplejson.JSONDecoder().decode(result)
                latest_version = git['sha']
                logger.debug('(getLatestVersionaFromGit) Branch [%s] has Latest Version has been set to [%s]' % (branch, latest_version))
            except:
                logger.warn('(getLatestVersionaFromGit) Could not get the latest commit from github')
                latest_version = 'Not_Available_From_GitHUB'

    return latest_version

# See how many commits behind we are    
def getCommitDifferenceFromGit():
    commits = -1
    #Takes current latest version value and trys to diff it with the latest
    #version in the current branch.
    if lazylibrarian.CURRENT_VERSION:
        logger.info('(getCommitDifferenceFromGit) -  Comparing currently installed version with latest github version')
        url = 'https://api.github.com/repos/%s/LazyLibrarian/compare/%s...%s' % (user, lazylibrarian.CURRENT_VERSION, lazylibrarian.LATEST_VERSION)
        logger.debug('(getCommitDifferenceFromGit) -  Check for differences between local & repo by [%s]' % url)
        
        try:
            result = urllib2.urlopen(url).read()

            try:
                logger.debug('JSONDecode url')
                git = simplejson.JSONDecoder().decode(result)
                logger.debug('pull total_commits from json object')
                commits = git['total_commits']
                
                logger.info('(getCommitDifferenceFromGit) -  GitHub reports as follows Status [%s] - Ahead [%s] - Behind [%s] - Total Commits [%s] ' % (git['status'], git['ahead_by'], git['behind_by'], git['total_commits']))
            except:
                logger.warn('(getCommitDifferenceFromGit) -  could not get difference status from GitHub')


        except:
            logger.warn('(getCommitDifferenceFromGit) -  Could not get commits behind from github. Can happen if you have a local commit not pushed to repo')
            
            
        if commits >= 1:
            logger.info('(getCommitDifferenceFromGit) -  New version is available. You are %s commits behind' % commits)
        elif commits == 0:
            logger.info('(getCommitDifferenceFromGit) -  lazylibrarian is up to date ')
        elif commits == -1:
            logger.info('(getCommitDifferenceFromGit) -  You are running an unknown version of lazylibrarian. Run the updater to identify your version')
            
    else:
        logger.info('You are running an unknown version of lazylibrarian. Run the updater to identify your version')
        
    logger.debug('(getCommitDifferenceFromGit) - exiting with commit value of [%s]' % commits)
    #lazylibrarian.COMMITS_BEHIND = commits
    return commits
    
     
#
#writes a version.txt file in the LL root dir with value of parameter
def updateVersionFile(new_version_id):
        # Update version.txt located in LL home dir.
        version_path = os.path.join(lazylibrarian.PROG_DIR, 'version.txt')
        
        try:
            logger.debug("(updateVersionFile) Updating [%s] with value [%s]" % (version_path, new_version_id))
            ver_file = open(version_path, 'w')
            ver_file.write(new_version_id)
            ver_file.close()
        except IOError, e:
            logger.error(u"(updateVersionFile) Unable to write current version to version.txt, update not complete: "+ex(e))
        
def update():

     
    if lazylibrarian.INSTALL_TYPE == 'win':
        logger.debug('(update) Windows install - no update available')    
        logger.info('(update) Windows .exe updating not supported yet.')
        #pass
    elif lazylibrarian.INSTALL_TYPE == 'git':

        branch = getCurrentGitBranch()

        output, err = runGit('stash clear')
        output, err = runGit('pull origin ' + branch)
        	
        if not output:
            logger.error('(update) Couldn\'t download latest version')
            
        for line in output.split('\n'):
        
            if 'Already up-to-date.' in line:
                logger.info('(update) No update available, not updating')
                logger.info('(update) Output: ' + str(output))
            elif line.endswith('Aborting.'):
                logger.error('(update) Unable to update from git: '+line)
                logger.info('(update) Output: ' + str(output))
                
    elif  lazylibrarian.INSTALL_TYPE == 'source':

        #As this is a non GIT install, we assume that the comparison is 
        #always to master.
        branch = lazylibrarian.CURRENT_BRANCH
        
        tar_download_url = 'https://github.com/%s/%s/tarball/%s' % (user, repo, branch)
        update_dir = os.path.join(lazylibrarian.PROG_DIR, 'update')
        version_path = os.path.join(lazylibrarian.PROG_DIR, 'version.txt')
        
        try:
            logger.info('(update) Downloading update from: '+tar_download_url)
            data = urllib2.urlopen(tar_download_url)
        except (IOError, URLError):
            logger.error("(update) Unable to retrieve new version from "+tar_download_url+", can't update")
            return
            
        download_name = data.geturl().split('/')[-1]
        
        tar_download_path = os.path.join(lazylibrarian.PROG_DIR, download_name)
        
        # Save tar to disk
        f = open(tar_download_path, 'wb')
        f.write(data.read())
        f.close()
        
        # Extract the tar to update folder
        logger.info('(update) Extracing file' + tar_download_path)
        tar = tarfile.open(tar_download_path)
        tar.extractall(update_dir)
        tar.close()
        
        # Delete the tar.gz
        logger.info('(update) Deleting file' + tar_download_path)
        os.remove(tar_download_path)
        
        # Find update dir name
        update_dir_contents = [x for x in os.listdir(update_dir) if os.path.isdir(os.path.join(update_dir, x))]
        if len(update_dir_contents) != 1:
            logger.error(u"(update) Invalid update data, update failed: "+str(update_dir_contents))
            return
        content_dir = os.path.join(update_dir, update_dir_contents[0])
        
        # walk temp folder and move files to main folder
        for dirname, dirnames, filenames in os.walk(content_dir):
            dirname = dirname[len(content_dir)+1:]
            for curfile in filenames:
                old_path = os.path.join(content_dir, dirname, curfile)
                new_path = os.path.join(lazylibrarian.PROG_DIR, dirname, curfile)
                
                if os.path.isfile(new_path):
                    os.remove(new_path)
                os.renames(old_path, new_path)
                
        # Update version.txt
        updateVersionFile(lazylibrarian.LATEST_VERSION)
    else:
        logger.error("(update) Cannot perform update - Install Type not set")
        return
