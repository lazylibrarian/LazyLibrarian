#!/usr/bin/python
# The parameter list is a list of database columns (column_name and data)
# for the snatched or downloaded book/mag
# This example reads the parameters back into a dictionary, then uses "ebook-convert"
# program from calibre to make sure we have both epub and mobi of the new book.
# Note it is not fully error trapped, just a basic working example.
# Would be better to check "res" return value from the converter too
# Error messages appear as errors in the lazylibrarian log
# Anything you print to stdout appears as debug messages in the log
# The exit code is passed back to the "test" button
# Always exit zero on success, non-zero on fail

import sys
import os
import subprocess

converter = "ebook-convert"  # if not in your "path", put the full pathname here
calibredb = "calibredb"  # and here if needed
calibrelib = "http://192.168.1.2:9000"  # --with-library value, either server or library name

mydict = {}
try:
    args = sys.argv[1:]
    while len(args) > 1:
        mydict[args[0]] = args[1]
        args = args[2:]
except Exception as err:
    sys.stderr.write("%s\n" % err)
    exit(1)

# mydict is now a dictionary of the book/magazine table entry
# and the wanted table entry for the relevant book/magazine
# You can look up available fields in the database structure,
# or just print mydict here to list them
# This example just uses "Event" "BookFile"  and "BookName"

msg = ''
if 'Event' in mydict and mydict['Event'] == 'Test':
    print("Test passed")
    exit(0)
elif 'Event' in mydict and mydict['Event'] == 'Added to Library':
    # if it was a book (not a magazine) and there is a filename
    if 'BookFile' in mydict and mydict['BookFile']:
        basename, extn = os.path.splitext(mydict['BookFile'])
        have_epub = os.path.exists(basename + '.epub')
        have_mobi = os.path.exists(basename + '.mobi')
        try:
            calibreid = basename.rsplit('(', 1)[1].split(')')[0]
            if not calibreid.isdigit():
                calibreid = ''
        except IndexError:
            calibreid = ''

        if not calibrelib or not calibredb:
            calibreid = ''

        if have_epub and not have_mobi:
            params = [converter, basename + '.epub', basename + '.mobi']
            try:
                res = subprocess.check_output(params, stderr=subprocess.STDOUT)
                print("Created mobi for %s" % mydict['BookName'])
                if calibreid:  # tell calibre about the new format
                    params = [calibredb, "add_format", "--with-library", "%s" % calibrelib, calibreid,
                              "%s" % basename + '.mobi']
                    res = subprocess.check_output(params, stderr=subprocess.STDOUT)
                exit(0)
            except Exception as e:
                sys.stderr.write("%s\n" % e)
                exit(1)

        if have_mobi and not have_epub:
            params = [converter, basename + '.mobi', basename + '.epub']
            try:
                res = subprocess.check_output(params, stderr=subprocess.STDOUT)
                print("Created epub for %s" % mydict['BookName'])
                if calibreid:  # tell calibre about the new format
                    params = [calibredb, "add_format", "--with-library", "%s" % calibrelib, calibreid,
                              "%s" % basename + '.epub']
                    res = subprocess.check_output(params, stderr=subprocess.STDOUT)
                exit(0)
            except Exception as e:
                sys.stderr.write("%s\n" % e)
                exit(1)
    else:
        sys.stderr.write("%s\n" % "No bookfile found")
        exit(1)
else:
    sys.stderr.write("%s\n" % "Not a download event")
    exit(1)
