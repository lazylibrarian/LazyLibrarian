#!/usr/bin/python
# The parameter list passed is a list of database columns (name and data)
# for a book or magazine. Read them back into a dictionary.
# For this example, just write the dictionary to a file
import sys
err = ''
try:
    args = sys.argv[1:]
except Exception as e:
    err = str(e)
with open('notification.out', 'w') as f:
    if err:
        f.write(err)
    else:
        mydict = {}
        n = len(args)
        while n:
            try:
                mydict[args[n-2]] = args[n-1]
                n -= 2
            except IndexError:
                break

        for item in mydict:
            # column name: value
            f.write("%s: %s\n" % (item, mydict[item]))
