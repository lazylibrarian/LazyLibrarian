#  This file is part of Lazylibrarian.
#  Lazylibrarian is free software':'you can redistribute it and/or modify
#  it under the terms of the GNU General Public License as published by
#  the Free Software Foundation, either version 3 of the License, or
#  (at your option) any later version.
#  Lazylibrarian is distributed in the hope that it will be useful,
#  but WITHOUT ANY WARRANTY; without even the implied warranty of
#  MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
#  GNU General Public License for more details.
#  You should have received a copy of the GNU General Public License
#  along with Lazylibrarian.  If not, see <http://www.gnu.org/licenses/>.


import datetime
import hashlib
import os
import re
import string
import unicodedata

import lazylibrarian
from lib.six import PY2, text_type
# noinspection PyUnresolvedReferences
from lib.six.moves.urllib_parse import quote_plus, quote, urlencode, urlsplit, urlunsplit


def url_fix(s, charset='utf-8'):
    if PY2 and isinstance(s, text_type):
        s = s.encode(charset, 'ignore')
    elif not PY2 and not isinstance(s, text_type):
        s = s.decode(charset)
    scheme, netloc, path, qs, anchor = urlsplit(s)
    path = quote(path, '/%')
    qs = quote_plus(qs, ':&=')
    return urlunsplit((scheme, netloc, path, qs, anchor))


def multibook(foldername, recurse=False):
    # Check for more than one book in the folder(tree). Note we can't rely on basename
    # being the same, so just check for more than one bookfile of the same type
    # Return which type we found multiples of, or empty string if no multiples
    filetypes = getList(lazylibrarian.CONFIG['EBOOK_TYPE'])

    if recurse:
        for r, d, f in os.walk(makeBytestr(foldername)):
            flist = [makeUnicode(item) for item in f]
            for item in filetypes:
                counter = 0
                for fname in flist:
                    if fname.endswith(item):
                        counter += 1
                        if counter > 1:
                            return item
    else:
        flist = os.listdir(makeBytestr(foldername))
        flist = [makeUnicode(item) for item in flist]
        for item in filetypes:
            counter = 0
            for fname in flist:
                if fname.endswith(item):
                    counter += 1
                    if counter > 1:
                        return item
    return ''


def bookSeries(bookname):
    """
    Try to get a book series/seriesNum from a bookname, or return empty string
    See if book is in multiple series first, if so return first one
    eg "The Shepherds Crown (Discworld, #41; Tiffany Aching, #5)"
    if no match, try single series, eg Mrs Bradshaws Handbook (Discworld, #40.5)

    \(            Must have (
    ([\S\s]+      followed by a group of one or more non whitespace
    [^)])        not ending in )
    ,? #?         followed by optional comma, then space optional hash
    (             start next group
    \d+           must have one or more digits
    \.?           then optional decimal point, (. must be escaped)
    -?            optional dash for a range
    \d{0,}        zero or more digits
    [;,]          a semicolon or comma if multiple series
    )             end group
    """
    series = ""
    seriesNum = ""
    # These are words that don't indicate a following series name/number eg "FIRST 3 chapters"
    non_series_words = ['series', 'unabridged', 'volume', 'phrase', 'from', 'chapters', 'season',
                        'the first', 'includes', 'paperback', 'first', 'books', 'large print', 'of',
                        'rrp', '2 in', '&', 'v.']

    result = re.search(r"\(([\S\s]+[^)]),? #?(\d+\.?-?\d*[;,])", bookname)
    if result:
        series = result.group(1)
        while series[-1] in ',)':
            series = series[:-1]
        seriesNum = result.group(2)
        while seriesNum[-1] in ';,':
            seriesNum = seriesNum[:-1]
    else:
        result = re.search(r"\(([\S\s]+[^)]),? #?(\d+\.?-?\d*)", bookname)
        if result:
            series = result.group(1)
            while series[-1] in ',)':
                series = series[:-1]
            seriesNum = result.group(2)

    if series and series.lower().endswith(' novel'):
        series = series[:-6]
    if series and series.lower().endswith(' book'):
        series = series[:-5]
    if series and series.lower().endswith(' part'):
        series = series[:-5]
    if series and series.lower().endswith(' -'):
        series = series[:-2]

    for word in non_series_words:
        if series.lower().startswith(word):
            return "", ""

    series = cleanName(unaccented(series))
    series = series.strip()
    seriesNum = seriesNum.strip()
    if series.lower().strip('.') == 'vol':
        series = ''
    if series.lower().strip('.').endswith('vol'):
        series = series.strip('.')
        series = series[:-3].strip()
    return series, seriesNum


def next_run(when_run):
    """
    Give a readable approximation of how long until a job will be run
    """
    try:
        when_run = datetime.datetime.strptime(when_run, '%Y-%m-%d %H:%M:%S')
        timenow = datetime.datetime.now()
        td = when_run - timenow
        diff = td.seconds  # time difference in seconds
    except ValueError as e:
        lazylibrarian.logger.error("Error getting next run for [%s] %s" % (when_run, str(e)))
        diff = 0
        td = ''

    td = str(td)
    if 's,' in td:
        return td.split('s,')[0] + 's'

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
    Return todays date in format yyyymmdd
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


def check_year(num, past=1900, future=1):
    # See if num looks like a valid year
    # for a magazine allow forward dated by a year, eg Jan 2017 issues available in Dec 2016
    n = check_int(num, 0)
    if past < n <= int(datetime.date.today().strftime("%Y")) + future:
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
    except IndexError:
        return "1970-01-01"


def dateFormat(datestr, formatstr):
    # return date formatted in requested style
    # $d	Day of the month as a zero-padded decimal number
    # $b	Month as abbreviated name
    # $B	Month as full name
    # $m	Month as a zero-padded decimal number
    # $y	Year without century as a zero-padded decimal number
    # $Y	Year with century as a decimal number
    # datestr are stored in lazylibrarian as YYYY-MM-DD or YYYY-MM-DD HH:MM:SS or nnnn for issue number

    if not datestr:
        return ""
    if datestr.isdigit():
        return datestr
    if not formatstr or formatstr == '$Y-$m-$d':  # shortcut for default values
        return datestr[:11]

    # noinspection PyBroadException
    try:
        return formatstr.replace(
            '$Y', datestr[0:4]).replace(
            '$y', datestr[2:4]).replace(
            '$m', datestr[5:7]).replace(
            '$d', datestr[8:10]).replace(
            '$B', lazylibrarian.MONTHNAMES[int(datestr[5:7])][0].title()).replace(
            '$b', lazylibrarian.MONTHNAMES[int(datestr[5:7])][1].title())
    except Exception:
        return datestr


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
    elif month in ["fall", "autumn"]:
        return 10
    elif month == "christmas":
        return 12
    else:
        return 0


def datecompare(nzbdate, control_date):
    """
    Return how many days between two dates given in yy-mm-dd format or yyyy-mm-dd format
    or zero if error (not a valid date)
    """
    try:
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
    except (AttributeError, IndexError, TypeError, ValueError):
        return 0


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


def size_in_bytes(size):
    """
    Take a size string with units eg 10 Mb, 5.3Kb
    and return integer bytes
    """
    if not size:
        return 0
    mult = 1
    try:
        if 'K' in size:
            size = size.split('K')[0]
            mult = 1024
        elif 'M' in size:
            size = size.split('M')[0]
            mult = 1024 * 1024
        elif 'G' in size:
            size = size.split('G')[0]
            mult = 1024 * 1024 * 1024
        size = int(float(size) * mult)
    except (ValueError, IndexError):
        size = 0
    return size


def md5_utf8(txt):
    if isinstance(txt, text_type):
        txt = txt.encode('utf-8')
    return hashlib.md5(txt).hexdigest()


def makeUnicode(txt):
    # convert a bytestring to unicode, don't know what encoding it might be so try a few
    # it could be a file on a windows filesystem, unix...
    if txt is None or not txt:
        return u''
    elif isinstance(txt, text_type):
        return txt
    for encoding in [lazylibrarian.SYS_ENCODING, 'latin-1', 'utf-8']:
        try:
            txt = txt.decode(encoding)
            return txt
        except UnicodeError:
            pass
    lazylibrarian.logger.debug("Unable to decode name [%s]" % repr(txt))
    return txt


def makeBytestr(txt):
    # convert unicode to bytestring, needed for os.walk and os.listdir
    # listdir falls over if given unicode startdir and a filename in a subdir can't be decoded to ascii
    if txt is None or not txt:
        return b''
    elif not isinstance(txt, text_type):  # nothing to do if already bytestring
        return txt
    for encoding in [lazylibrarian.SYS_ENCODING, 'latin-1', 'utf-8']:
        try:
            txt = txt.encode(encoding)
            return txt
        except UnicodeError:
            pass
    lazylibrarian.logger.debug("Unable to encode name [%s]" % repr(txt))
    return txt


def is_valid_isbn(isbn):
    """
    Return True if parameter looks like a valid isbn
    either 13 digits, 10 digits, or 9 digits followed by 'x'
    """
    isbn = isbn.replace('-', '').replace(' ', '')
    if len(isbn) == 13:
        if isbn.isdigit():
            return True
    elif len(isbn) == 10:
        if isbn[:9].isdigit():
            return True
        elif isbn[9] in ["Xx"] and isbn[:8].isdigit():
            return True
    return False


def is_valid_type(filename, extras='jpg, opf'):
    type_list = list(set(getList(lazylibrarian.CONFIG['MAG_TYPE']) +
                         getList(lazylibrarian.CONFIG['AUDIOBOOK_TYPE']) +
                         getList(lazylibrarian.CONFIG['EBOOK_TYPE']) +
                         getList(extras)))
    extn = os.path.splitext(filename)[1].lstrip('.')
    if extn and extn.lower() in type_list:
        return True
    return False


def is_valid_booktype(filename, booktype=None):
    """
    Check if filename extension is one we want
    """
    if booktype == 'mag':  # default is book
        booktype_list = getList(lazylibrarian.CONFIG['MAG_TYPE'])
    elif booktype == 'audiobook':
        booktype_list = getList(lazylibrarian.CONFIG['AUDIOBOOK_TYPE'])
    else:
        booktype_list = getList(lazylibrarian.CONFIG['EBOOK_TYPE'])
    extn = os.path.splitext(filename)[1].lstrip('.')
    if extn and extn.lower() in booktype_list:
        return True
    return False


def getList(st, c=None):
    # split a string/unicode into a list on whitespace or plus or comma
    # or single character split eg filenames with spaces split on comma only
    # Returns list of same type as st
    lst = []
    if st:
        if c is not None and len(c) == 1:
            x = st.split(c)
            for item in x:
                lst.append(item.strip())
        else:
            st = st.replace(',', ' ').replace('+', ' ')
            lst = ' '.join(st.split()).split()
    return lst


# noinspection PyArgumentList
def safe_unicode(obj, *args):
    """ return the unicode representation of obj """
    if not PY2:
        return str(obj, *args)
    try:
        # noinspection PyCompatibility,PyUnresolvedReferences
        return unicode(obj, *args)
    except UnicodeDecodeError:
        # obj is byte string
        ascii_text = str(obj).encode('string_escape')
        # noinspection PyCompatibility,PyUnresolvedReferences
        return unicode(ascii_text)


def split_title(author, book):
    # Strip title at colon if starts with author, eg Tom Clancy: Ghost Protocol
    if book.startswith(author + ':'):
        book = book.split(author + ':')[1].strip()
    brace = book.find('(')
    # .find() returns position in string (0 to len-1) or -1 if not found
    # change position to 1 to len, or zero if not found so we can use boolean if
    brace += 1
    if brace and book.endswith(')'):
        # if title ends with words in braces, split on last brace
        # as this always seems to be a subtitle or series info
        parts = book.rsplit('(', 1)
        parts[1] = '(' + parts[1]
        bookname = parts[0].strip()
        booksub = parts[1]
        return bookname, booksub
    # if not (words in braces at end of string)
    # split subtitle on whichever comes first, ':' or '('
    # unless the part in braces is one word, eg (TM) or (Annotated) or (Unabridged)
    # Might need to expand this to be a list of allowed words?
    colon = book.find(':')
    colon += 1
    bookname = book
    booksub = ''
    parts = ''
    if brace:
        endbrace = book.find(')')
        endbrace += 1
        if endbrace:
            if ' ' not in book[brace:endbrace - 1]:
                brace = 0
    if colon and brace:
        if colon < brace:
            parts = book.split(':', 1)
        else:
            parts = book.split('(', 1)
            parts[1] = '(' + parts[1]
    elif colon:
        parts = book.split(':', 1)
    elif brace:
        parts = book.split('(', 1)
        parts[1] = '(' + parts[1]
    if parts:
        bookname = parts[0].strip()
        booksub = parts[1]
    return bookname, booksub


def formatAuthorName(author):
    """ get authorname in a consistent format """
    author = makeUnicode(author)

    if "," in author:
        postfix = getList(lazylibrarian.CONFIG['NAME_POSTFIX'])
        words = author.split(',')
        if len(words) == 2:
            # Need to handle names like "L. E. Modesitt, Jr." or "J. Springmann, Phd"
            # use an exceptions list for now, there might be a better way...
            if words[1].strip().strip('.').strip('_').lower() in postfix:
                surname = words[1].strip()
                forename = words[0].strip()
            else:
                # guess its "surname, forename" or "surname, initial(s)" so swap them round
                forename = words[1].strip()
                surname = words[0].strip()
            if author != forename + ' ' + surname:
                lazylibrarian.logger.debug('Formatted authorname [%s] to [%s %s]' % (author, forename, surname))
                author = forename + ' ' + surname
    # reformat any initials, we want to end up with L.E. Modesitt Jr
    if len(author) > 2 and author[1] in '. ':
        surname = author
        forename = ''
        while len(surname) > 2 and surname[1] in '. ':
            forename = forename + surname[0] + '.'
            surname = surname[2:].strip()
        if author != forename + ' ' + surname:
            lazylibrarian.logger.debug('Stripped authorname [%s] to [%s %s]' % (author, forename, surname))
            author = forename + ' ' + surname

    return ' '.join(author.split())  # ensure no extra whitespace


def sortDefinite(title):
    if not title:
        return ''
    if title[:4] == 'The ':
        return title[4:] + ', The'
    if title[2:] == 'A ':
        return title[2:] + ', A'
    return title


def surnameFirst(authorname):
    """ swap authorname round into surname, forenames for display and sorting"""
    if not authorname:
        return ''
    words = getList(authorname)

    if len(words) < 2:
        return authorname
    res = words.pop()

    if res.strip('.').lower in getList(lazylibrarian.CONFIG['NAME_POSTFIX']):
        res = words.pop() + ' ' + res
    return res + ', ' + ' '.join(words)


def cleanName(name, extras=None):
    if not name:
        return u''
    validNameChars = u"-_.() %s%s%s" % (string.ascii_letters, string.digits, extras)
    try:
        cleanedName = unicodedata.normalize('NFKD', name).encode('ASCII', 'ignore')
    except TypeError:
        cleanedName = unicodedata.normalize('NFKD', name.decode(lazylibrarian.SYS_ENCODING)).encode('ASCII', 'ignore')
    if not PY2:
        cleanedName = cleanedName.decode('utf-8')
    cleaned = u''.join(c for c in cleanedName if c in validNameChars)
    return cleaned.strip()


def unaccented(str_or_unicode):
    if not str_or_unicode:
        return u''
    if not PY2:
        return unaccented_str(str_or_unicode)
    return unaccented_str(str_or_unicode).decode(lazylibrarian.SYS_ENCODING)
    # returns unicode


def unaccented_str(str_or_unicode):
    if not str_or_unicode:
        return ''.encode('ASCII')  # ensure bytestring for python3
    try:
        cleaned = unicodedata.normalize('NFKD', str_or_unicode)
    except TypeError:
        cleaned = unicodedata.normalize('NFKD', str_or_unicode.decode('utf-8', 'replace'))

    # turn accented chars into non-accented
    stripped = u''.join([c for c in cleaned if not unicodedata.combining(c)])
    # replace all non-ascii quotes/apostrophes with ascii ones eg "Collector's"
    dic = {u'\u2018': u"'", u'\u2019': u"'", u'\u201c': u'"', u'\u201d': u'"'}
    # Other characters not converted by unicodedata.combining
    # c6 Ae, d0 Eth, d7 multiply, d8 Ostroke, de Thorn, df sharpS
    dic.update({u'\xc6': 'A', u'\xd0': 'D', u'\xd7': '*', u'\xd8': 'O', u'\xde': 'P', u'\xdf': 's'})
    # e6 ae, f0 eth, f7 divide, f8 ostroke, fe thorn
    dic.update({u'\xe6': 'a', u'\xf0': 'o', u'\xf7': '/', u'\xf8': 'o', u'\xfe': 'p'})
    stripped = replace_all(stripped, dic)
    # now get rid of any other non-ascii
    stripped = stripped.encode('ASCII', 'ignore')
    if PY2:
        return stripped  # return bytestring
    else:
        return stripped.decode(lazylibrarian.SYS_ENCODING)  # return unicode


def replace_all(text, dic):
    if not text:
        return ''
    for item in dic:
        text = text.replace(item, dic[item])
    return text
