#!/usr/bin/python
# The parameter list is a list of database columns (column_name and data)
# for the snatched or downloaded book/mag
# This example reads the parameters back into a dictionary, then uses "ebook-convert"
# program from calibre to make sure we have both epub and mobi of the new book.
# Note it is not fully error trapped, just a basic working example.
# Would be better to check "res" return value from the converter too
# The result returned (in this case "msg") is passed back to the "test" button
# and gets displayed as an error message (telling you why the test failed).
# Returning "msg" at this point is useful for testing the notifier script
# Always exit zero.

import sys
import os
import subprocess

converter = "ebook-convert"  # if not in your "path", put the full pathname here

args = sys.argv[1:]
n = len(args)
mydict = {}

while n:
    mydict[args[n-2]] = args[n-1]
    n -= 2

# mydict is now a dictionary of the book/magazine table entry for the relevant book/magazine
# You can look up available fields in the database structure, or print mydict here to list them
# This example just uses "Event" "BookFile"  and "BookName"

msg = ''
# if it was a "download" event (not just "snatched")
if 'Event' in mydict and mydict['Event'] == 'Added to Library':
    # if it was a book (not a magazine) and there is a filename
    if 'BookFile' in mydict and mydict['BookFile']:
        basename, extn = os.path.splitext(mydict['BookFile'])
        have_epub = os.path.exists(basename + '.epub')
        have_mobi = os.path.exists(basename + '.mobi')
        if have_epub and not have_mobi:
            params = [converter, basename + '.epub', basename + '.mobi']
            try:
                res = subprocess.check_output(params, stderr=subprocess.STDOUT)
                msg = "Created mobi for %s" % mydict['BookName']
            except Exception as e:
                msg = str(e)
        if have_mobi and not have_epub:
            params = [converter, basename + '.mobi', basename + '.epub']
            try:
                res = subprocess.check_output(params, stderr=subprocess.STDOUT)
                msg = "Created epub for %s" % mydict['BookName']
            except Exception as e:
                msg = str(e)
    else:
        msg = "No bookfile found"
else:
    msg = "Not a download event"
if len(msg):
    sys.stderr.write("%s\n" % msg)
exit(0)
