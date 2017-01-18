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

import datetime
import os
import re
import shlex
import string
import time
import unicodedata

import lazylibrarian


def bookSeries(bookname):
    """
    Try to get a book series/seriesNum from a bookname, or return None
    See if book is in multiple series first, if so return first one
    eg "The Shepherds Crown (Discworld, #41; Tiffany Aching, #5)"
    if no match, try single series, eg Mrs Bradshaws Handbook (Discworld, #40.5)

    \(            Must have (
    ([\S\s]+)     followed by a group of one or more non whitespace
    ,? #?         followed by optional comma, then space optional hash
    (             start next group
    \d+           must have one or more digits
    \.?           then optional decimal point, (. must be escaped)
    -?            optional dash for a range
    \d{0,}        zero or more digits
    [;,]          a semicolon or comma if multiple series
    )             end group
    """
    series = None
    seriesNum = None

    result = re.search(r"\(([\S\s]+),? #?(\d+\.?-?\d{0,}[;,])", bookname)
    if result:
        series = result.group(1)
        if series[-1] == ',':
            series = series[:-1]
        seriesNum = result.group(2)
        if seriesNum[-1] in ';,':
            seriesNum = seriesNum[:-1]
    else:
        result = re.search(r"\(([\S\s]+),? #?(\d+\.?-?\d{0,})", bookname)
        if result:
            series = result.group(1)
            if series[-1] == ',':
                series = series[:-1]
            seriesNum = result.group(2)

    if series and series.lower().endswith(' novel'):
        series = series[:-6]
    if series and series.lower().endswith(' book'):
        series = series[:-5]

    return series, seriesNum


def next_run(when_run):
    """
    Give a readable approximation of how long until a job will be run
    """
    timenow = time.time()
    when_run = time.strptime(when_run, '%Y-%m-%d %H:%M:%S')
    when_run = time.mktime(when_run)
    diff = when_run - timenow  # time difference in seconds
    # calculate whole units, plus round up by adding 1(true) if remainder >= half
    days = int(diff / 86400) + (diff % 86400 >= 43200)
    hours = int(diff / 3600) + (diff % 3600 >= 1800)
    minutes = int(diff / 60) + (diff % 60 >= 30)
    seconds = int(diff)

    if days > 1:
        return "%i days" % days
    elif hours > 1:
        return "%i hours" % hours
    elif minutes > 1:
        return "%i minutes" % minutes
    else:
        return "%i seconds" % seconds


def now():
    dtnow = datetime.datetime.now()
    return dtnow.strftime("%Y-%m-%d %H:%M:%S")


def today():
    """
    Return todays date in format yyyy-mm-dd
    """
    dttoday = datetime.date.today()
    yyyymmdd = datetime.date.isoformat(dttoday)
    return yyyymmdd


def age(histdate):
    """
    Return how many days since histdate
    histdate = yyyy-mm-dd
    return 0 for today, or if invalid histdate
    """
    nowdate = datetime.date.isoformat(datetime.date.today())
    y1, m1, d1 = (int(x) for x in nowdate.split('-'))
    try:
        y2, m2, d2 = (int(x) for x in histdate.split('-'))
        date1 = datetime.date(y1, m1, d1)
        date2 = datetime.date(y2, m2, d2)
        dtage = date1 - date2
        return dtage.days
    except ValueError:
        return 0


def check_year(num):
    # See if num looks like a valid year for a magazine
    # Allow forward dated by a year, eg Jan 2017 issues available in Dec 2016
    n = check_int(num, 0)
    if n > 1900 and n < int(datetime.date.today().strftime("%Y")) + 2:
        return n
    return 0


def nzbdate2format(nzbdate):
    try:
        mmname = nzbdate.split()[2].zfill(2)
        day = nzbdate.split()[1]
        # nzbdates are mostly english short month names, but not always
        month = month2num(mmname)
        if month == 0:
            month = 1  # hopefully won't hit this, but return a default value rather than error
        year = nzbdate.split()[3]
        return "%s-%02d-%s" % (year, month, day)
    except Exception:
        return "1970-01-01"


def month2num(month):
    # return month number given month name (long or short) in requested locales
    # or season name (only in English currently)

    month = month.lower()
    for f in range(1, 13):
        if month in lazylibrarian.MONTHNAMES[f]:
            return f

    if month == "winter":
        return 1
    elif month == "spring":
        return 4
    elif month == "summer":
        return 7
    elif month == "fall" or month == "autumn":
        return 10
    else:
        return 0


def datecompare(nzbdate, control_date):
    """
    Return how many days between two dates given in yy-mm-dd format
    """
    y1 = int(nzbdate.split('-')[0])
    m1 = int(nzbdate.split('-')[1])
    d1 = int(nzbdate.split('-')[2])
    y2 = int(control_date.split('-')[0])
    m2 = int(control_date.split('-')[1])
    d2 = int(control_date.split('-')[2])
    date1 = datetime.date(y1, m1, d1)
    date2 = datetime.date(y2, m2, d2)
    dtage = date1 - date2
    return dtage.days


def plural(var):
    """
    Convenience function for log messages, if var = 1 return ''
    if var is anything else return 's'
    so book -> books, seeder -> seeders  etc
    """
    if check_int(var, 0) == 1:
        return ''
    return 's'


def check_int(var, default):
    """
    Return an integer representation of var
    or return default value if var is not integer
    """
    try:
        return int(var)
    except (ValueError, TypeError):
        return default


def is_valid_isbn(isbn):
    """
    Return True if parameter looks like a valid isbn
    either 13 digits, 10 digits, or 9 digits followed by 'x'
    """
    isbn = re.sub('[- ]', '', isbn)
    if len(isbn) == 13:
        if isbn.isdigit():
            return True
        elif len(isbn) == 10:
            if isbn[:9].isdigit():
                return True
            else:
                if isbn[9] in ["Xx"] and isbn[:8].isdigit():
                    return True
    return False


def is_valid_booktype(filename, booktype=None):
    """
    Check if filename extension is one we want
    """
    if booktype == 'mag':  # default is book
        booktype_list = getList(lazylibrarian.MAG_TYPE)
    else:
        booktype_list = getList(lazylibrarian.EBOOK_TYPE)
    extn = os.path.splitext(filename)[1].lstrip('.')
    if extn and extn.lower() in booktype_list:
        return True
    return False


def getList(st):
    # split a string into a list
    # changed posix to "false" to not baulk at apostrophes
    if st:
        my_splitter = shlex.shlex(st, posix=False)
        my_splitter.whitespace += ','
        my_splitter.whitespace_split = True
        return list(my_splitter)
    return []


def safe_unicode(obj, *args):
    """ return the unicode representation of obj """
    try:
        return unicode(obj, *args)
    except UnicodeDecodeError:
        # obj is byte string
        ascii_text = str(obj).encode('string_escape')
        return unicode(ascii_text)


def split_title(author, book):
    # Strip title at colon if starts with author, eg Tom Clancy: Ghost Protocol
    if book.startswith(author + ':'):
        book = book.split(author + ':')[1].strip()
    colon = book.find(':')
    brace = book.find('(')
    # split subtitle on whichever comes first, ':' or '('
    # .find() returns position in string (0 to len-1) or -1 if not found
    # change position to 1 to len, or zero if not found
    colon += 1
    brace += 1
    bookname = book
    booksub = ''
    parts = ''
    if colon and brace:
        if colon < brace:
            parts = book.split(':')
        else:
            parts = book.split('(')
            parts[1] = '(' + parts[1]
    elif colon:
        parts = book.split(':')
    elif brace:
        parts = book.split('(')
        parts[1] = '(' + parts[1]
    if parts:
        bookname = parts[0]
        booksub = parts[1]
    return bookname, booksub


def cleanName(name):
    validNameChars = u"-_.() %s%s" % (string.ascii_letters, string.digits)
    try:
        cleanedName = unicodedata.normalize('NFKD', name).encode('ASCII', 'ignore')
    except TypeError:
        cleanedName = unicodedata.normalize('NFKD', name.decode(lazylibrarian.SYS_ENCODING)).encode('ASCII', 'ignore')
    cleaned = u''.join(c for c in cleanedName if c in validNameChars)
    return cleaned.strip()


def unaccented(str_or_unicode):
    return unaccented_str(str_or_unicode).decode(lazylibrarian.SYS_ENCODING)
    # returns unicode


def unaccented_str(str_or_unicode):
    try:
        nfkd_form = unicodedata.normalize('NFKD', str_or_unicode)
    except TypeError:
        nfkd_form = unicodedata.normalize('NFKD', str_or_unicode.decode(lazylibrarian.SYS_ENCODING, 'replace'))
    # turn accented chars into non-accented
    stripped = ''.join([c for c in nfkd_form if not unicodedata.combining(c)])
    # replace all non-ascii quotes/apostrophes with ascii ones eg "Collector's"
    dic = {u'\u2018': u"'", u'\u2019': u"'", u'\u201c': u'"', u'\u201d': u'"'}
    stripped = replace_all(stripped, dic)
    # now get rid of any other non-ascii
    return stripped.encode('ASCII', 'ignore')
    # returns str


def replace_all(text, dic):
    for i, j in dic.iteritems():
        text = text.replace(i, j)
    return text
