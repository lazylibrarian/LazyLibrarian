import time, datetime

import lazylibrarian


def now():
    now = datetime.datetime.now()
    return now.strftime("%Y-%m-%d %H:%M:%S")

def today():
    today = datetime.date.today()
    yyyymmdd = datetime.date.isoformat(today)
    return yyyymmdd

def checked(variable):
    if variable:
        return 'Checked'
    else:
        return ''
