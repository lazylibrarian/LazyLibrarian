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
#  You should have received a copy of the GNU General Public License
#  along with Lazylibrarian.  If not, see <http://www.gnu.org/licenses/>.

# Purpose:
#   Common, basic functions for LazyLibrary

import importlib
import logging
import os
import platform
import random
import re
import sqlite3
import ssl
import string
import subprocess
import sys
import tarfile
import time
import zipfile
from pathlib import Path

import apscheduler
import bs4
import cherrypy
import html5lib
import httplib2
import mako
import pypdf
import requests
import urllib3
import webencodings

import lazylibrarian
from lazylibrarian import database
from lazylibrarian.config2 import CONFIG
from lazylibrarian.configdefs import CONFIG_GIT
from lazylibrarian.filesystem import DIRS, path_exists, listdir, walk, setperm, remove_file, path_isfile
from lazylibrarian.formatter import get_list, make_unicode
from lazylibrarian.logconfig import LOGCONFIG


def get_user_agent() -> str:
    # Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/52.0.2743.116 Safari/537.36
    if CONFIG['USER_AGENT']:
        return CONFIG['USER_AGENT']
    else:
        return f"LazyLibrarian ({platform.system()} {platform.release()})"


def get_readinglist(table, user):
    # return a set of all bookids in a readinglist
    db = database.DBConnection()
    readinglist = []
    # status_id = 1 want-to-read, 2 currently_reading, 3 read, 4 owned, 5 dnf
    if table.lower() == 'toread':
        status = 1
    elif table.lower() == 'reading':
        status = 2
    elif table.lower() in ['haveread', 'read']:
        status = 3
    elif table.lower() in ['abandoned', 'dnf']:
        status = 5
    else:
        status = 4
    cmd = f"SELECT bookid from readinglists WHERE userid=? and status=?"
    res = db.select(cmd, (user, status))
    if res:
        for item in res:
            readinglist.append(item[0])
    db.close()
    return readinglist


def set_readinglist(table, user, booklist):
    # set the readinglist for a user
    db = database.DBConnection()
    if table.lower() == 'toread':
        status = 1
    elif table.lower() == 'reading':
        status = 2
    elif table.lower() in ['haveread', 'read']:
        status = 3
    elif table.lower() in ['abandoned', 'dnf']:
        status = 5
    else:
        status = 4
    try:
        readinglist = set(booklist)
        for book in readinglist:
            db.upsert("readinglists", {'Status': status}, {'UserID': user, 'BookID': book})
    finally:
        db.close()


def multibook(foldername, recurse=False):
    # Check for more than one book in the folder(tree). Note we can't rely on basename
    # being the same, so just check for more than one bookfile of the same type
    # Return which type we found multiples of, or empty string if no multiples
    filetypes = get_list(CONFIG['EBOOK_TYPE'])

    if recurse:
        for _, _, f in walk(foldername):
            flist = [item for item in f]
            for item in filetypes:
                counter = 0
                for fname in flist:
                    if fname.endswith(item):
                        counter += 1
                        if counter > 1:
                            return item
    else:
        flist = listdir(foldername)
        for item in filetypes:
            counter = 0
            for fname in flist:
                if fname.endswith(item):
                    counter += 1
                    if counter > 1:
                        return item
    return ''


def proxy_list():
    proxies = None
    if CONFIG['PROXY_HOST']:
        proxies = {}
        for item in get_list(CONFIG['PROXY_TYPE']):
            if item in ['http', 'https']:
                proxies.update({item: CONFIG['PROXY_HOST']})
    return proxies


def is_valid_email(emails):
    if not emails:
        return False
    elif ',' in emails:
        emails = get_list(emails)
    else:
        emails = [emails]

    for email in emails:
        if re.match(r"(^[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+$)", email) is None:
            return False
    return True


def pwd_generator(size=10, chars=string.ascii_letters + string.digits):
    return ''.join(random.choice(chars) for _ in range(size))


def pwd_check(password):
    # password rules:
    # At least 8 characters long with no spaces
    # we don't enforce mix of alnum as longer passwords
    # made of random words are more secure
    if len(password) < 8:
        return False
    # if not any(char.isdigit() for char in password):
    #    return False
    # if not any(char.isalpha() for char in password):
    #    return False
    if any(char.isspace() for char in password):
        return False
    return True


def mime_type(filename):
    name = make_unicode(filename).lower()
    if name.endswith('.epub'):
        return 'application/epub+zip'
    elif name.endswith('.mobi') or name.endswith('.azw'):
        return 'application/x-mobipocket-ebook'
    elif name.endswith('.azw3'):
        return 'application/x-mobi8-ebook'
    elif name.endswith('.pdf'):
        return 'application/pdf'
    elif name.endswith('.mp3'):
        return 'audio/mpeg3'
    elif name.endswith('.m4a'):
        return 'audio/mp4'
    elif name.endswith('.m4b'):
        return 'audio/mp4'
    elif name.endswith('.flac'):
        return 'audio/flac'
    elif name.endswith('.ogg'):
        return 'audio/ogg'
    elif name.endswith('.zip'):
        return 'application/x-zip-compressed'
    elif name.endswith('.xml'):
        return 'application/rss+xml'
    elif name.endswith('.cbz'):
        return 'application/x-cbz'
    elif name.endswith('.cbr'):
        return 'application/x-cbr'
    return "application/x-download"


def module_available(module_name):
    loader = importlib.util.find_spec(module_name)
    return loader is not None


def create_support_zip() -> (str, str):
    """ Create a zip file for support purposes.
    Returns a status message and the full name of the zip file """
    outfile = DIRS.get_tmpfilename('support.zip')
    with zipfile.ZipFile(outfile, 'w', compression=zipfile.ZIP_DEFLATED) as myzip:
        try:
            # Add logfiles
            logfiles = LOGCONFIG.get_redacted_logfilenames()
            if not logfiles:
                msg = 'No redacted log files included. Please enable redacted log files.'
            else:
                for logfile in logfiles:
                    myzip.write(logfile, arcname=os.path.basename(logfile))
                msg = f'Included {len(logfiles)} redacted logfiles.'
            # Add 'log header'
            header = log_header()
            myzip.writestr('systeminfo.txt', header)
            # Add config.ini, redacted
            count, configstr = CONFIG.save_config_to_string(save_all=False, redact=True)
            myzip.writestr('config-redacted.ini', configstr)
            msg += f'  Included systeminfo.txt and {count} items of redacted config.ini.'
        except IOError as e:
            msg = f'Error creating support.zip file: {type(e).__name__}, {str(e)}'
        finally:
            myzip.close()

    return msg, outfile


def docker():
    # this is from https://stackoverflow.com/questions/43878953
    if Path('/.dockerenv').is_file():
        return True
    # as is this...
    cgroup = Path("/proc/self/cgroup")
    if cgroup.is_file() and cgroup.read_text().find('docker') > -1:
        return True
    # this is from jaraco.docker library
    mountinfo = Path("/proc/self/mountinfo")
    if mountinfo.is_file():
        with open(mountinfo, 'r') as f:
            first_mount = f.readlines()[0]
        if 'docker' in first_mount or 'overlay' in first_mount:
            return True
    # this works for linuxserver docker
    if DIRS.PROG_DIR.startswith('/app/'):
        return True
    # check for environment variable
    if os.environ.get("DOCKER", "").lower() in ("yes", "y", "on", "true", "1"):
        return True
    # or value read from version.py during startup
    if 'DOCKER' in CONFIG['INSTALL_TYPE'].upper():
        return True
    return False


# noinspection PyUnresolvedReferences,PyPep8Naming
def log_header(online=True) -> str:
    logger = logging.getLogger(__name__)
    popen_list = [sys.executable, DIRS.FULL_PATH]
    popen_list += DIRS.ARGS
    header = f"Startup cmd: {str(popen_list)}\n"
    header += f"config file: {CONFIG.configfilename}\n"
    header += f"Interface: {CONFIG['HTTP_LOOK']}\n"
    header += f'Loglevel: {logging.getLevelName(logger.getEffectiveLevel())}\n'
    header += f'Sys_Encoding: {lazylibrarian.SYS_ENCODING}\n'
    for item in CONFIG_GIT:
        if item == 'GIT_UPDATED':
            timestamp = CONFIG.get_int(item)
            header += f'{item.lower()}: {time.ctime(timestamp)}\n'
        else:
            header += f'{item.lower()}: {CONFIG[item]}\n'
    try:
        header += f'package version: {lazylibrarian.version.PACKAGE_VERSION}\n'
    except AttributeError:
        pass
    try:
        header += f'packaged by: {lazylibrarian.version.PACKAGED_BY}\n'
    except AttributeError:
        pass

    db_version = 0
    db = database.DBConnection()
    try:
        result = db.match('PRAGMA user_version')
    finally:
        db.close()
    if result and result[0]:
        value = str(result[0])
        if value.isdigit():
            db_version = int(value)
    uname = platform.uname()
    header += f"db version: {db_version}\n"
    header += "Python version: %s\n" % sys.version.split('\n')
    header += f"uname: {str(uname)}\n"
    header += f"Platform: {platform.platform(aliased=True)}\n"
    if uname[0] == 'Darwin':
        header += f"mac_ver: {str(platform.mac_ver())}\n"
    elif uname[0] == 'Windows':
        header += f"win_ver: {str(platform.win32_ver())}\n"
    header += f"apscheduler: {getattr(apscheduler, '__version__', None)}\n"
    header += f"httplib2: {getattr(httplib2, '__version__', None)}\n"
    if 'urllib3' in globals():
        header += f"urllib3: {getattr(urllib3, '__version__', None)}\n"
    else:
        header += "urllib3: not found\n"
    header += f"requests: {getattr(requests, '__version__', None)}\n"
    if online:
        try:
            if CONFIG.get_bool('SSL_VERIFY'):
                tls_version = requests.get('https://www.howsmyssl.com/a/check', timeout=30,
                                           verify=CONFIG['SSL_CERTS']
                                           if CONFIG['SSL_CERTS'] else True).json()['tls_version']
            else:
                logger.info('Checking TLS version')
                requests.packages.urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
                tls_version = requests.get('https://www.howsmyssl.com/a/check', timeout=30,
                                           verify=False).json()['tls_version']
            if '1.2' not in tls_version and '1.3' not in tls_version:
                header += 'tls: missing required functionality. Try upgrading to v1.2 or newer. You have '
        except Exception as err:
            tls_version = str(err)
        header += f"tls: {tls_version}\n"

    header += f"cherrypy: {getattr(cherrypy, '__version__', None)}\n"
    header += f"sqlite3: {getattr(sqlite3, 'sqlite_version', None)}\n"
    header += f"mako: {getattr(mako, '__version__', None)}\n"
    header += f"webencodings: {getattr(webencodings, 'VERSION', None)}\n"
    header += f"pypdf: {getattr(pypdf, '__version__', None)}\n"
    from lazylibrarian.notifiers import APPRISE_VER
    if APPRISE_VER and APPRISE_VER[0].isdigit():
        header += f"apprise: {APPRISE_VER}\n"
    else:
        header += "apprise: not found\n"
    if lazylibrarian.UNRARLIB == 1:
        vers = lazylibrarian.RARFILE.unrarlib.RARGetDllVersion()
        header += f"unrar: {vers}\n"
    elif lazylibrarian.UNRARLIB == 2:
        import lib.UnRAR2 as UnRAR2
        vers = getattr(UnRAR2, '__version__', None)
        header += f"unrar2: {vers}\n"
        if os.name == 'nt':
            vers = UnRAR2.windows.RARGetDllVersion()
            header += f"unrar dll: {vers}\n"
    else:
        header += "unrar: not found\n"

    header += f"bs4: {getattr(bs4, '__version__', None)}\n"
    header += f"html5lib: {getattr(html5lib, '__version__', None)}\n"

    try:
        import PIL
        vers = getattr(PIL, '__version__', None)
        header += f"python imaging: {vers}\n"
        import lib.icrawler as icrawler
        header += f"icrawler: {getattr(icrawler, '__version__', None)}\n"
    except ImportError:
        header += "python imaging: not found, unable to use icrawler\n"

    header += f"openssl: {getattr(ssl, 'OPENSSL_VERSION', None)}\n"
    X509 = None
    cryptography = None
    try:
        # pyOpenSSL 0.14 and above use cryptography for OpenSSL bindings. The _x509
        # attribute is only present on those versions.
        # noinspection PyUnresolvedReferences
        import OpenSSL
    except (ImportError, AttributeError):
        header += "pyOpenSSL: not found\n"
        OpenSSL = None

    if OpenSSL:
        try:
            # noinspection PyUnresolvedReferences
            from OpenSSL.crypto import X509
        except ImportError:
            header += "pyOpenSSL.crypto X509: not found\n"

    if X509:
        # noinspection PyCallingNonCallable
        x509 = X509()
        if getattr(x509, "_x509", None) is None:
            header += "pyOpenSSL: module missing required functionality. Try upgrading to v0.14 or newer. You have "
        header += f"pyOpenSSL: {getattr(OpenSSL, '__version__', None)}\n"

    if OpenSSL:
        try:
            import OpenSSL.SSL
        except (ImportError, AttributeError) as err:
            header += f'pyOpenSSL missing SSL module/attribute: {err}\n'

    if OpenSSL:
        try:
            # get_extension_for_class method added in `cryptography==1.1`; not available in older versions
            # but need cryptography >= 1.3.4 for access from pyopenssl >= 0.14
            # noinspection PyUnresolvedReferences
            import cryptography
        except ImportError:
            header += "cryptography: not found\n"

    if cryptography:
        try:
            # noinspection PyUnresolvedReferences
            from cryptography.x509.extensions import Extensions
            if getattr(Extensions, "get_extension_for_class", None) is None:
                header += "cryptography: module missing required functionality."
                header += " Try upgrading to v1.3.4 or newer. You have "
            header += f"cryptography: {getattr(cryptography, '__version__', None)}\n"
        except ImportError:
            header += "cryptography Extensions: not found\n"

    # noinspection PyBroadException
    try:
        import rapidfuzz
        vers = getattr(rapidfuzz, "__version__", None)
        if not vers:
            vers = "installed"
    except Exception:
        vers = "not found"
    header += f"Rapidfuzz: {vers}\n"
    try:
        import magic
        try:
            if hasattr(magic, "magic_version"):
                vers = magic.magic_version()
            else:
                # noinspection PyProtectedMember
                vers = magic.libmagic._name
        except AttributeError:
            vers = 'not found'
    except Exception:  # magic might fail for multiple reasons
        vers = 'not found'
    header += f"magic: {vers}\n"

    return header


def zip_audio(source, zipname, bookid):
    """ Zip up all the audiobook parts in source folder to zipname
        Check if zipfile already exists, if not create a new one
        Doesn't actually check for audiobook parts, just zips everything
        including any .jpg etc.
        Return full path to zipfile
    """
    logger = logging.getLogger(__name__)
    zip_file = os.path.join(source, f"{zipname}.zip")
    if not path_exists(zip_file):
        logger.debug(f'Zipping up {zipname}')
        namevars = lazylibrarian.bookrename.name_vars(bookid)
        singlefile = namevars['AudioSingleFile']

        cnt = 0
        with zipfile.ZipFile(zip_file, 'w', zipfile.ZIP_DEFLATED) as myzip:
            for rootdir, _, filenames in walk(source):
                for filename in filenames:
                    # don't include self or our special index file
                    if not filename.endswith('.zip') and not filename.endswith('.ll'):
                        bname, extn = os.path.splitext(filename)
                        # don't include singlefile
                        if bname != singlefile:
                            cnt += 1
                            myzip.write(os.path.join(rootdir, filename), filename)
        logger.debug(f'Zipped up {cnt} files')
        _ = setperm(zip_file)
    return zip_file


def run_script(params):
    logger = logging.getLogger(__name__)
    if os.name == 'nt' and params[0].endswith('.py'):
        params.insert(0, sys.executable)
    logger.debug(str(params))
    try:
        if os.name != 'nt':
            p = subprocess.Popen(params, preexec_fn=lambda: os.nice(10),
                                 stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        else:
            p = subprocess.Popen(params, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        res, err = p.communicate()
        dlcommslogger = logging.getLogger('special.dlcomms')
        dlcommslogger.debug(make_unicode(res))
        dlcommslogger.debug(make_unicode(err))
        return p.returncode, make_unicode(res), make_unicode(err)
    except Exception as er:
        err = f"run_script exception: {type(er).__name__} {str(er)}"
        logger.error(err)
        return 1, '', err


def calibre_prg(prgname):
    # Try to locate a calibre ancilliary program
    # Try explicit path or in the calibredb location
    # or in current path or system path
    logger = logging.getLogger(__name__)
    target = ''
    if prgname == 'ebook-convert':
        target = CONFIG['EBOOK_CONVERT']
    elif CONFIG['EBOOK_CONVERT']:
        target = os.path.join(os.path.dirname(CONFIG['EBOOK_CONVERT']), prgname)
    elif CONFIG['IMP_CALIBREDB']:
        target = os.path.join(os.path.dirname(CONFIG['IMP_CALIBREDB']), prgname)

    if not target or not os.path.exists(target):
        target = os.path.join(os.getcwd(), prgname)
        if not os.path.exists(target):
            logger.debug(f"{target} not found")
            if os.name == 'nt':
                try:
                    params = ["where", prgname]
                    res = subprocess.check_output(params, stderr=subprocess.STDOUT)
                    target = make_unicode(res).strip()
                except Exception as err:
                    logger.debug(f"where {prgname} failed: {type(err).__name__} {str(err)}")
                    target = ''
            else:
                try:
                    params = ["which", prgname]
                    res = subprocess.check_output(params, stderr=subprocess.STDOUT)
                    target = make_unicode(res).strip()
                except Exception as err:
                    logger.debug(f"which {prgname} failed: {type(err).__name__} {str(err)}")
                    target = ''
    if target:
        logger.debug(f"Using {target}")
        try:
            params = [target, "--version"]
            res = subprocess.check_output(params, stderr=subprocess.STDOUT)
            res = make_unicode(res).strip().split("(")[1].split(")")[0]
            logger.debug(f"Found {prgname} version {res}")
        except Exception as err:
            logger.debug(f"{prgname} --version failed: {type(err).__name__} {str(err)}")
            target = ''
    return target


def only_punctuation(value):
    for c in value:
        if c not in string.punctuation and c not in string.whitespace:
            return False
    return True


def cron_dbbackup():
    db = database.DBConnection()
    try:
        db.upsert("jobs", {'Start': time.time()}, {'Name': 'BACKUP'})
        dbbackup('scheduled')
    finally:
        db.upsert("jobs", {'Finish': time.time()}, {'Name': 'BACKUP'})
        db.close()


def dbbackup(source='lazylibrarian'):
    db = database.DBConnection()
    fname, err = db.backup()
    backup_file = ''
    err = ''
    if fname:
        backup_file = f"{source}_{time.asctime().replace(' ', '_').replace(':', '_')}.tgz"
        backup_file = os.path.join(DIRS.DATADIR, backup_file)
        zf = tarfile.open(backup_file, mode='w:gz')
        zf.add(fname, arcname=DIRS.DBFILENAME)
        remove_file(fname)
        for f in ['config.ini', 'dicts.json', 'genres.json', 'filetemplate.text', 'logintemplate.text']:
            target = os.path.join(DIRS.DATADIR, f)
            if path_isfile(target):
                zf.add(target, arcname=f)
    return backup_file, err


def extract_series_number(text):
    """Extract series number - supports normal, Roman, spelled (1-9999, I-C, one-hundred)"""
    import re
    if not text:
        return None
    
    def word_to_number(word_text):
        ones = {'one': 1, 'two': 2, 'three': 3, 'four': 4, 'five': 5, 'six': 6, 'seven': 7, 'eight': 8, 'nine': 9, 'ten': 10, 'eleven': 11, 'twelve': 12, 'thirteen': 13, 'fourteen': 14, 'fifteen': 15, 'sixteen': 16, 'seventeen': 17, 'eighteen': 18, 'nineteen': 19}
        tens = {'twenty': 20, 'thirty': 30, 'forty': 40, 'fifty': 50, 'sixty': 60, 'seventy': 70, 'eighty': 80, 'ninety': 90}
        word_lower = word_text.lower().replace('-', ' ').strip()
        if 'hundred' in word_lower:
            parts = word_lower.split()
            if len(parts) == 1 or (len(parts) == 2 and parts[0] == 'one'):
                return 100
            return None
        parts = word_lower.split()
        if len(parts) == 2 and parts[0] in tens and parts[1] in ones:
            return tens[parts[0]] + ones[parts[1]]
        if len(parts) == 1 and parts[0] in tens:
            return tens[parts[0]]
        if len(parts) == 1 and parts[0] in ones:
            return ones[parts[0]]
        return None
    
    def roman_to_number(roman):
        values = {'I': 1, 'V': 5, 'X': 10, 'L': 50, 'C': 100}
        total = 0
        prev = 0
        for char in reversed(roman.upper()):
            val = values.get(char, 0)
            if val == 0:
                return None
            if val < prev:
                total -= val
            else:
                total += val
            prev = val
        return total
    
    match = re.search(r'^(\d{4})\b', text)
    if match:
        return match.group(1)
    match = re.search(r'\b(?:book|vol|volume|part|chapter|series|number|no|#)\s+(\d{1,4})\b', text, re.IGNORECASE)
    if match:
        return match.group(1)
    match = re.search(r'\b(?:book|vol|volume|part|chapter|series|number|no)\s+([a-z]+(?:[\s-][a-z]+)?)\b', text, re.IGNORECASE)
    if match:
        num = word_to_number(match.group(1))
        if num:
            return str(num)
    match = re.search(r'\b([IVXLC]{1,10})\b', text.upper())
    if match:
        roman = match.group(1)
        if all(c in 'IVXLC' for c in roman):
            num = roman_to_number(roman)
            if num and 1 <= num <= 100:
                return str(num)
    match = re.search(r'^(\d{1,3})\b', text)
    if match:
        num = int(match.group(1))
        if not (1900 <= num <= 2099) and num > 0:
            return match.group(1)
    match = re.search(r'^([a-z]+(?:[\s-][a-z]+)?)\b', text, re.IGNORECASE)
    if match:
        num = word_to_number(match.group(1))
        if num:
            return str(num)
    match = re.search(r'\b(\d{1,4})\b', text)
    if match:
        num = int(match.group(1))
        if not (1900 <= num <= 2099) and 1 <= num <= 9999:
            return match.group(1)
    return None


def validate_series_match(search_query, result_title, bookid=None):
    """Validate series numbers match - returns (should_match, confidence)"""
    import logging
    logger = logging.getLogger('lazylibrarian')
    search_num = extract_series_number(search_query)
    result_num = extract_series_number(result_title)
    logger.debug("Series validation - Search: '{}' (num: {}), Result: '{}' (num: {})".format(search_query, search_num, result_title, result_num))
    if search_num and result_num:
        if search_num == result_num:
            logger.debug("Series numbers match ({}) - boosting".format(search_num))
            return (True, 1.2)
        else:
            logger.debug("Series mismatch ({} vs {}) - rejecting".format(search_num, result_num))
            return (False, 0.0)
    if search_num and not result_num:
        logger.debug("Search has number ({}) but result doesn't - rejecting".format(search_num))
        return (False, 0.0)
    if result_num and not search_num:
        logger.debug("Result has number ({}) but search doesn't - penalty".format(result_num))
        return (True, 0.9)
    logger.debug("No series numbers - standard matching")
    return (True, 1.0)
