import datetime
import re
import lazylibrarian
import shlex
import time
import os
import string
import unicodedata


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
    now = time.time()
    when_run = time.strptime(when_run, '%Y-%m-%d %H:%M:%S')
    when_run = time.mktime(when_run)
    diff = when_run - now  # time difference in seconds
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


def nzbdate2format(nzbdate):
    mmname = nzbdate.split()[2].zfill(2)
    day = nzbdate.split()[1]
    # nzbdates are mostly english short month names, but not always
    # month = str(strptime(mmname, '%b').tm_mon).zfill(2)
    month = month2num(mmname)
    if month == "Invalid":
        month = "01"  # hopefully won't hit this, but return a default value rather than error
    year = nzbdate.split()[3]
    return year + '-' + month + '-' + day


def month2num(month):
    # return month number given month name (long or short) in requested locales
    # or season name (only in English currently)

    month = month.lower()
    for f in range(1, 13):
        if month in lazylibrarian.MONTHNAMES[f]:
            return str(f).zfill(2)

    if month == "winter":
        return "01"
    elif month == "spring":
        return "04"
    elif month == "summer":
        return "07"
    elif month == "fall":
        return "10"
    elif month == "autumn":
        return "10"
    else:
        return "00"


def datecompare(nzbdate, control_date):
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
    try:
        return int(var)
    except (ValueError, TypeError):
        return default


def is_valid_isbn(isbn):
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
