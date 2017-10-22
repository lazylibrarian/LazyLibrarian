#  This file is part of Lazylibrarian.
#
#  Lazylibrarian is free software':'you can redistribute it and/or modify
#  it under the terms of the GNU General Public License as published by
#  the Free Software Foundation, either version 3 of the License, or
#  (at your option) any later version.
#
#  Lazylibrarian is distributed in the hope that it will be useful,
#  but WITHOUT ANY WARRANTY; without even the implied warranty of
#  MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
#  GNU General Public License for more details.
#
#  You should have received a copy of the GNU General Public License
#  along with Lazylibrarian.  If not, see <http://www.gnu.org/licenses/>.

import os
import platform
import re
import subprocess
import tarfile
import threading
import time
import lib.requests as requests

import lazylibrarian
from lazylibrarian import logger, version
from lazylibrarian.common import USER_AGENT, proxyList
from lazylibrarian.formatter import getList, check_int


def logmsg(level, msg):
    # log messages to logger if initialised, or print if not.
    if lazylibrarian.__INITIALIZED__:
        if level == 'error':
            logger.error(msg)
        elif level == 'info':
            logger.info(msg)
        elif level == 'debug':
            logger.debug(msg)
        elif level == 'warn':
            logger.warn(msg)
        else:
            logger.info(msg)
    else:
        print level.upper(), msg


def runGit(args):
    # Function to execute GIT commands taking care of error logging etc
    if lazylibrarian.CONFIG['GIT_PROGRAM']:
        git_locations = ['"' + lazylibrarian.CONFIG['GIT_PROGRAM'] + '"']
    else:
        git_locations = ['git']

    if platform.system().lower() == 'darwin':
        git_locations.append('/usr/local/git/bin/git')

    output = err = None

    for cur_git in git_locations:

        cmd = cur_git + ' ' + args

        try:
            logmsg('debug', '(RunGit)Trying to execute: "' + cmd + '" with shell in ' + lazylibrarian.PROG_DIR)
            p = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                                 shell=True, cwd=lazylibrarian.PROG_DIR)
            output, err = p.communicate()
            logmsg('debug', '(RunGit)Git output: [%s]' % output.strip('\n'))

        except OSError:
            logmsg('debug', '(RunGit)Command ' + cmd + ' didn\'t work, couldn\'t find git')
            continue

        if 'not found' in output or "not recognized as an internal or external command" in output:
            logmsg('debug', '(RunGit)Unable to find git with command ' + cmd)
            logmsg('error', 'git not found - please ensure git executable is in your PATH')
            output = None
        elif 'fatal:' in output or err:
            logmsg('error', '(RunGit)Git returned bad info. Are you sure this is a git installation?')
            output = None
        elif output:
            break

    return output, err


#
# function to determine what type of install we are on & sets current Branch value
# - windows
# - git based
# - deployed source code


def getInstallType():
    # need a way of detecting if we are running a windows .exe file
    # (which we can't upgrade)  rather than just running git or source on windows
    # We use a string in the version.py file for this
    # FUTURE:   Add a version number string in this file too?
    try:
        install = version.LAZYLIBRARIAN_VERSION.lower()
    except Exception:
        install = 'unknown'

    if install in ['windows', 'win32build']:
        lazylibrarian.CONFIG['INSTALL_TYPE'] = 'win'
        lazylibrarian.CURRENT_BRANCH = 'Windows'

    elif install == 'package':  # deb, rpm, other non-upgradeable
        lazylibrarian.CONFIG['INSTALL_TYPE'] = 'package'
        lazylibrarian.CONFIG['GIT_BRANCH'] = 'Package'

    elif os.path.isdir(os.path.join(lazylibrarian.PROG_DIR, '.git')):
        lazylibrarian.CONFIG['INSTALL_TYPE'] = 'git'
        lazylibrarian.CONFIG['GIT_BRANCH'] = getCurrentGitBranch()
    else:
        lazylibrarian.CONFIG['INSTALL_TYPE'] = 'source'
        lazylibrarian.CONFIG['GIT_BRANCH'] = 'master'

    logmsg('debug', '(getInstallType) [%s] install detected. Setting Branch to [%s]' %
           (lazylibrarian.CONFIG['INSTALL_TYPE'], lazylibrarian.CONFIG['GIT_BRANCH']))


def getCurrentVersion():
    # Establish the version of the installed app for Source or GIT only
    # Global variable set in LazyLibrarian.py on startup as it should be
    if lazylibrarian.CONFIG['INSTALL_TYPE'] == 'win':
        logmsg('debug', '(getCurrentVersion) Windows install - no update available')

        # Don't have a way to update exe yet, but don't want to set VERSION to None
        VERSION = 'Windows Install'

    elif lazylibrarian.CONFIG['INSTALL_TYPE'] == 'git':
        output, err = runGit('rev-parse HEAD')

        if not output:
            logmsg('error', '(getCurrentVersion) Couldn\'t find latest git installed version.')
            cur_commit_hash = 'GIT Cannot establish version'
        else:
            cur_commit_hash = output.strip()

            if not re.match('^[a-z0-9]+$', cur_commit_hash):
                logmsg('error', '(getCurrentVersion) Output doesn\'t look like a hash, not using it')
                cur_commit_hash = 'GIT invalid hash return'

        VERSION = cur_commit_hash

    elif lazylibrarian.CONFIG['INSTALL_TYPE'] in ['source', 'package']:

        version_file = os.path.join(lazylibrarian.PROG_DIR, 'version.txt')

        if not os.path.isfile(version_file):
            VERSION = 'No Version File'
            logmsg('debug', '(getCurrentVersion) [%s] missing.' % version_file)
            return VERSION
        else:
            fp = open(version_file, 'r')
            current_version = fp.read().strip(' \n\r')
            fp.close()

            if current_version:
                VERSION = current_version
            else:
                VERSION = 'No Version set in file'
                return VERSION
    else:
        logmsg('error', '(getCurrentVersion) Install Type not set - cannot get version value')
        VERSION = 'Install type not set'
        return VERSION

    updated = updateVersionFile(VERSION)
    if updated:
        logmsg('debug', '(getCurrentVersion) - Install type [%s] Local Version is set to [%s] ' % (
            lazylibrarian.CONFIG['INSTALL_TYPE'], VERSION))
    else:
        logmsg('debug', '(getCurrentVersion) - Install type [%s] Local Version is unchanged [%s] ' % (
            lazylibrarian.CONFIG['INSTALL_TYPE'], VERSION))

    return VERSION


def getCurrentGitBranch():
    # Returns current branch name of installed version from GIT
    # return "NON GIT INSTALL" if INSTALL TYPE is not GIT
    # Can only work for GIT driven installs, so check install type
    if lazylibrarian.CONFIG['INSTALL_TYPE'] != 'git':
        logmsg('debug', 'Non GIT Install doing getCurrentGitBranch')
        return 'NON GIT INSTALL'

    # use git rev-parse --abbrev-ref HEAD which returns the name of the current branch
    current_branch, err = runGit('rev-parse --abbrev-ref HEAD')
    current_branch = str(current_branch)
    current_branch = current_branch.strip(' \n\r')

    if not current_branch:
        logmsg('error', 'failed to return current branch value')
        return 'InvalidBranch'

    logmsg('debug', '(getCurrentGitBranch) Current local branch of repo is [%s] ' % current_branch)

    return current_branch


def checkForUpdates():
    """ Called at startup, from webserver with thread name WEBSERVER, or as a cron job """
    if 'Thread-' in threading.currentThread().name:
        threading.currentThread().name = "CRON-VERSIONCHECK"
    logmsg('debug', 'Set Install Type, Current & Latest Version and Commit status')
    getInstallType()
    lazylibrarian.CONFIG['CURRENT_VERSION'] = getCurrentVersion()
    lazylibrarian.CONFIG['LATEST_VERSION'] = getLatestVersion()
    if lazylibrarian.CONFIG['CURRENT_VERSION'] == lazylibrarian.CONFIG['LATEST_VERSION']:
        lazylibrarian.CONFIG['COMMITS_BEHIND'] = 0
        lazylibrarian.COMMIT_LIST = ""
    else:
        lazylibrarian.CONFIG['COMMITS_BEHIND'], lazylibrarian.COMMIT_LIST = getCommitDifferenceFromGit()
    logmsg('debug', 'Update check complete')


def getLatestVersion():
    # Return latest version from GITHUB
    # if GIT install return latest on current branch
    # if nonGIT install return latest from master
    # Can only work for GIT driven installs, so check install type
    # lazylibrarian.CONFIG['COMMITS_BEHIND'] = 'Unknown'

    if lazylibrarian.CONFIG['INSTALL_TYPE'] in ['git', 'source', 'package']:
        latest_version = getLatestVersion_FromGit()
    elif lazylibrarian.CONFIG['INSTALL_TYPE'] in ['win']:
        latest_version = 'WINDOWS INSTALL'
    else:
        latest_version = 'UNKNOWN INSTALL'

    lazylibrarian.CONFIG['LATEST_VERSION'] = latest_version
    return latest_version


def getLatestVersion_FromGit():
    # Don't call directly, use getLatestVersion as wrapper.
    # Also removed reference to global variable setting.
    latest_version = 'Unknown'

    # Can only work for non Windows driven installs, so check install type
    if lazylibrarian.CONFIG['INSTALL_TYPE'] == 'win':
        logmsg('debug', '(getLatestVersion_FromGit) Error - should not be called under a windows install')
        latest_version = 'WINDOWS INSTALL'
    else:
        # check current branch value of the local git repo as folks may pull from a branch not master
        branch = lazylibrarian.CONFIG['GIT_BRANCH']

        if branch == 'InvalidBranch':
            logmsg('debug', '(getLatestVersion_FromGit) - Failed to get a valid branch name from local repo')
        else:
            if branch == 'Package':  # check packages against master
                branch = 'master'
            # Get the latest commit available from github
            url = 'https://api.github.com/repos/%s/%s/commits/%s' % (
                lazylibrarian.CONFIG['GIT_USER'], lazylibrarian.CONFIG['GIT_REPO'], branch)
            logmsg('debug',
                   '(getLatestVersion_FromGit) Retrieving latest version information from github command=[%s]' % url)

            age = lazylibrarian.CONFIG['GIT_UPDATED']
            try:
                headers = {'User-Agent': USER_AGENT}
                if age:
                    logmsg('debug', '(getLatestVersion_FromGit) Checking if modified since %s' % age)
                    headers.update({'If-Modified-Since': age})
                proxies = proxyList()
                timeout = check_int(lazylibrarian.CONFIG['HTTP_TIMEOUT'], 30)
                r = requests.get(url, timeout=timeout, headers=headers, proxies=proxies)

                if str(r.status_code).startswith('2'):
                    git = r.json()
                    latest_version = git['sha']
                    logmsg('debug', '(getLatestVersion_FromGit) Branch [%s] Latest Version has been set to [%s]' % (
                        branch, latest_version))
                elif str(r.status_code) == '304':
                    latest_version = lazylibrarian.CONFIG['CURRENT_VERSION']
                    logmsg('debug', '(getLatestVersion_FromGit) Not modified, currently on Latest Version')
            except Exception as e:
                logmsg('warn', '(getLatestVersion_FromGit) Could not get the latest commit from github')
                logmsg('debug', 'git %s for %s: %s' % (type(e).__name__, url, str(e)))
                latest_version = 'Not_Available_From_GitHUB'

    return latest_version


def getCommitDifferenceFromGit():
    # See how many commits behind we are
    # Takes current latest version value and trys to diff it with the latest
    # version in the current branch.
    commit_list = ''
    commits = -1
    if lazylibrarian.CONFIG['LATEST_VERSION'] == 'Not_Available_From_GitHUB':
        commits = 0  # don't report a commit diff as we don't know anything
    if lazylibrarian.CONFIG['CURRENT_VERSION'] and commits != 0:
        logmsg('info', '[VersionCheck] -  Comparing currently installed version with latest github version')
        url = 'https://api.github.com/repos/%s/LazyLibrarian/compare/%s...%s' % (
            lazylibrarian.CONFIG['GIT_USER'], lazylibrarian.CONFIG['CURRENT_VERSION'],
            lazylibrarian.CONFIG['LATEST_VERSION'])
        logmsg('debug', '(getCommitDifferenceFromGit) -  Check for differences between local & repo by [%s]' % url)

        try:
            headers = {'User-Agent': USER_AGENT}
            proxies = proxyList()
            timeout = check_int(lazylibrarian.CONFIG['HTTP_TIMEOUT'], 30)
            r = requests.get(url, timeout=timeout, headers=headers, proxies=proxies)
            git = r.json()
            logmsg('debug', 'pull total_commits from json object')
            commits = int(git['total_commits'])

            msg = '(getCommitDifferenceFromGit) -  GitHub reports as follows '
            msg += 'Status [%s] - Ahead [%s] - Behind [%s] - Total Commits [%s]' % (
                git['status'], git['ahead_by'], git['behind_by'], git['total_commits'])
            logmsg('debug', msg)

            if int(git['total_commits']) > 0:
                messages = []
                for item in git['commits']:
                    messages.insert(0, item['commit']['message'])
                for line in messages:
                    commit_list = "%s\n%s" % (commit_list, line)
        except Exception as e:
            logmsg('warn', '(getCommitDifferenceFromGit) %s -  could not get difference status from GitHub' %
                   type(e).__name__)

        if commits > 1:
            logmsg('info', '[VersionCheck] -  New version is available. You are %s commits behind' % commits)
        elif commits == 1:
            logmsg('info', '[VersionCheck] -  New version is available. You are one commit behind')
        elif commits == 0:
            logmsg('info', '[VersionCheck] -  lazylibrarian is up to date ')
            # lazylibrarian.CONFIG['GIT_UPDATED'] = time.strftime("%a, %d %b %Y %H:%M:%S GMT", time.gmtime())
        elif commits < 0:
            msg = '[VersionCheck] -  You are running an unknown version of lazylibrarian. '
            msg += 'Run the updater to identify your version'
            logmsg('info', msg)

    elif lazylibrarian.CONFIG['LATEST_VERSION'] == 'Not_Available_From_GitHUB':
        commit_list = 'Unable to get latest version from GitHub'
        logmsg('info', commit_list)
    else:
        logmsg('info', 'You are running an unknown version of lazylibrarian. Run the updater to identify your version')

    logmsg('debug', '(getCommitDifferenceFromGit) - exiting with commit value of [%s]' % commits)
    # lazylibrarian.CONFIG['COMMITS_BEHIND'] = commits
    return commits, commit_list


def updateVersionFile(new_version_id):
    # Update version.txt located in LL home dir.
    version_path = os.path.join(lazylibrarian.PROG_DIR, 'version.txt')

    try:
        logmsg('debug', "(updateVersionFile) Updating [%s] with value [%s]" % (
            version_path, new_version_id))
        if os.path.exists(version_path):
            with open(version_path, 'r') as ver_file:
                current_version = ver_file.read().strip(' \n\r')
            if current_version == new_version_id:
                return False

        with open(version_path, 'w') as ver_file:
            ver_file.write(new_version_id)

        lazylibrarian.CONFIG['CURRENT_VERSION'] = new_version_id
        return True
    except IOError as e:
        logmsg('error',
               u"(updateVersionFile) Unable to write current version to version.txt, update not complete: %s" % str(e))
        return False


def update():
    if lazylibrarian.CONFIG['INSTALL_TYPE'] == 'win':
        logmsg('debug', '(update) Windows install - no update available')
        logmsg('info', '(update) Windows .exe updating not supported yet.')
        return False
    elif lazylibrarian.CONFIG['INSTALL_TYPE'] == 'package':
        logmsg('debug', '(update) Package install - no update available')
        logmsg('info', '(update) Please use your package manager to update')
        return False

    elif lazylibrarian.CONFIG['INSTALL_TYPE'] == 'git':
        branch = getCurrentGitBranch()

        _, _ = runGit('stash clear')
        output, err = runGit('pull origin ' + branch)

        success = True
        if not output:
            logmsg('error', '(update) Couldn\'t download latest version')
            success = False
        for line in output.split('\n'):
            if 'Already up-to-date.' in line:
                logmsg('info', '(update) No update available, not updating')
                logmsg('info', '(update) Output: ' + str(output))
                success = False
                # lazylibrarian.CONFIG['GIT_UPDATED'] = time.strftime("%a, %d %b %Y %H:%M:%S GMT", time.gmtime())
            elif 'Aborting' in line or 'local changes' in line:
                logmsg('error', '(update) Unable to update from git: ' + line)
                logmsg('info', '(update) Output: ' + str(output))
                success = False
        if success:
            lazylibrarian.CONFIG['GIT_UPDATED'] = time.strftime("%a, %d %b %Y %H:%M:%S GMT", time.gmtime())
            return True
    elif lazylibrarian.CONFIG['INSTALL_TYPE'] == 'source':

        # As this is a non GIT install, we assume that the comparison is
        # always to master.

        tar_download_url = 'https://github.com/%s/%s/tarball/%s' % (
            lazylibrarian.CONFIG['GIT_USER'], lazylibrarian.CONFIG['GIT_REPO'], lazylibrarian.CONFIG['GIT_BRANCH'])
        update_dir = os.path.join(lazylibrarian.PROG_DIR, 'update')
        # version_path = os.path.join(lazylibrarian.PROG_DIR, 'version.txt')

        try:
            logmsg('info', '(update) Downloading update from: ' + tar_download_url)
            headers = {'User-Agent': USER_AGENT}
            proxies = proxyList()
            timeout = check_int(lazylibrarian.CONFIG['HTTP_TIMEOUT'], 30)
            r = requests.get(tar_download_url, timeout=timeout, headers=headers, proxies=proxies)
        except requests.exceptions.Timeout:
            logmsg('error', "(update) Timeout retrieving new version from " + tar_download_url)
            return False
        except Exception as e:
            if hasattr(e, 'reason'):
                errmsg = e.reason
            else:
                errmsg = str(e)
            logmsg('error',
                   "(update) Unable to retrieve new version from " + tar_download_url + ", can't update: %s" % errmsg)
            return False

        download_name = r.url.split('/')[-1]

        tar_download_path = os.path.join(lazylibrarian.PROG_DIR, download_name)

        # Save tar to disk
        with open(tar_download_path, 'wb') as f:
            f.write(r.content)

        # Extract the tar to update folder
        logmsg('info', '(update) Extracting file ' + tar_download_path)
        try:
            with tarfile.open(tar_download_path) as tar:
                tar.extractall(update_dir)
        except Exception as e:
            logger.error('Failed to unpack tarfile %s (%s): %s' % (type(e).__name__, tar_download_path, str(e)))
            return False

        # Delete the tar.gz
        logmsg('info', '(update) Deleting file ' + tar_download_path)
        os.remove(tar_download_path)

        # Find update dir name
        update_dir_contents = [x for x in os.listdir(update_dir) if os.path.isdir(os.path.join(update_dir, x))]
        if len(update_dir_contents) != 1:
            logmsg('error', u"(update) Invalid update data, update failed: " + str(update_dir_contents))
            return False
        content_dir = os.path.join(update_dir, update_dir_contents[0])

        # walk temp folder and move files to main folder
        for dirname, dirnames, filenames in os.walk(content_dir):
            dirname = dirname[len(content_dir) + 1:]
            for curfile in filenames:
                old_path = os.path.join(content_dir, dirname, curfile)
                new_path = os.path.join(lazylibrarian.PROG_DIR, dirname, curfile)

                if os.path.isfile(new_path):
                    os.remove(new_path)
                os.renames(old_path, new_path)

        # Update version.txt
        updateVersionFile(lazylibrarian.CONFIG['LATEST_VERSION'])
        # lazylibrarian.CONFIG['GIT_UPDATED'] = time.strftime("%a, %d %b %Y %H:%M:%S GMT", time.gmtime())
        return True
    else:
        logmsg('error', "(update) Cannot perform update - Install Type not set")
        return False
