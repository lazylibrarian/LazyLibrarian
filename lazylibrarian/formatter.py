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

def is_valid_isbn(isbn):
    last = 10 if isbn[-1] in ["X", "x"] else int(isbn[-1])
    weighted = [int(num)*weight for num, weight in
              zip(isbn[:-1], reversed(range(2, 11)))]
    return (sum(weighted) + last) %11==0
