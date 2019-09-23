#!/usr/bin/python
# The parameter list passed is a list of database columns (name and data)
# for a book or magazine. Read them back into a dictionary.
# For this example, just return the formatted dictionary
import sys

mydict = {}
try:
    args = sys.argv[1:]
    while len(args) > 1:
        mydict[args[0]] = args[1]
        args = args[2:]
except Exception as err:
    sys.stderr.write("%s\n" % err)
    exit(1)

res = ''
for item in mydict:
    # column name: value
    res = res + "%s: %s\n" % (item, mydict[item])

print(res)
exit(0)
