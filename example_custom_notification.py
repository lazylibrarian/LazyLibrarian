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
        try:
            n = len(args)
            mydict = {}
            while n:
                mydict[args[n-2]] = args[n-1]
            	n -= 2
        except Exception as e:
            f.write(str(e))

    for item in mydict:
        f.write("%s: %s\n" % (item, mydict[item]))
