#!/usr/bin/python
# The parameter list is type, folder
# where "type" is one of 'ebook', 'audiobook', 'mag', 'test'
# and "folder" is the folder ready to be processed
# This example uses "ebook-convert" from calibre to make sure we have both epub and mobi of the new book.
# Note it is not fully error trapped, just a basic working example.
# Error messages appear as errors in the lazylibrarian log
# Anything you print to stdout appears as debug messages in the log
# The exit code and messages get passed back to the "test" button
# Always exit zero on success, non-zero on fail

import sys
import os
import subprocess

converter = "ebook-convert"  # if not in your "path", put the full pathname here
# set these to your preferences
wanted_formats = ['.epub', '.mobi']
keep_opf = True
keep_jpg = True
delete_others = False  # use with care, deletes everything except wanted formats (and opf/jpg if keep is True)


def makeBytestr(txt):
    # convert unicode to bytestring, needed for os.walk and os.listdir
    # listdir falls over if given unicode startdir and a filename in a subdir can't be decoded to ascii
    if txt is None or not txt:
        return b''
    elif not isinstance(txt, text_type):  # nothing to do if already bytestring
        return txt
    for encoding in ['utf-8', 'latin-1']:
        try:
            txt = txt.encode(encoding)
            return txt
        except UnicodeError:
            pass
    return txt


def makeUnicode(txt):
    # convert a bytestring to unicode, don't know what encoding it might be so try a few
    # it could be a file on a windows filesystem, unix...
    if txt is None or not txt:
        return u''
    elif isinstance(txt, text_type):
        return txt
    for encoding in ['utf-8', 'latin-1']:
        try:
            txt = txt.decode(encoding)
            return txt
        except UnicodeError:
            pass
    return txt


if len(sys.argv) != 3:
    sys.stderr.write("%s %s\n" % ("Invalid parameters", len(sys.argv)))
    exit(1)

if sys.version_info[0] == 3:
    text_type = str
else:
    text_type = unicode

booktype = sys.argv[1]
bookfolder = sys.argv[2]

if not booktype or booktype not in ['ebook', 'audiobook', 'mag', 'test']:
    sys.stderr.write("%s %s\n" % ("Invalid booktype", booktype))
    exit(1)
if not os.path.exists(bookfolder) and booktype != 'test':
    sys.stderr.write("%s %s\n" % ("Invalid bookfolder", bookfolder))
    exit(1)

if booktype == 'test':
    if not os.path.exists(bookfolder):
        bookfolder = os.path.dirname(os.path.abspath(__file__))

if booktype == 'book' or booktype == 'test':
    sourcefile = None
    created = ''
    for fname in os.listdir(makeBytestr(bookfolder)):
        fname = makeUnicode(fname)
        filename, extn = os.path.splitext(fname)
        if extn == '.epub':
            sourcefile = fname
            break
        elif extn == '.mobi':
            sourcefile = fname
            break
    if not sourcefile:
        sys.stderr.write("%s %s\n" % ("No suitable sourcefile found in", bookfolder))
        exit(1)

    basename, source_extn = os.path.splitext(sourcefile)

    for ftype in wanted_formats:
        if not os.path.exists(os.path.join(bookfolder, basename + ftype)):
            params = [converter, os.path.join(bookfolder, sourcefile), os.path.join(bookfolder, basename + ftype)]
            try:
                res = subprocess.check_output(params, stderr=subprocess.STDOUT)
                if created:
                    created += ' '
                created += ftype
            except Exception as e:
                sys.stderr.write("%s\n" % e)
                exit(1)

    if delete_others:
        if keep_opf:
            wanted_formats.append('.opf')
        if keep_jpg:
            wanted_formats.append('.jpg')
        for fname in os.listdir(makeBytestr(bookfolder)):
            fname = makeUnicode(fname)
            filename, extn = os.path.splitext(fname)
            if not extn or extn.lower() not in wanted_formats:
                if booktype == 'test':
                    print("Would delete %s" % fname)
                else:
                    print("Deleting %s" % fname)
                    try:
                        os.remove(os.path.join(bookfolder, fname))
                    except OSError:
                        pass
    if created:
        print("Created %s from %s" % (created, source_extn))
    else:
        print("No extra ebook formats created")
elif booktype == 'audio':
    # maybe you want a zip archive of the audiobook, or create a playlist?
    print("This example preprocessor only preprocesses eBooks")
elif booktype == 'mag':
    # maybe you want to split the pages and turn them into jpeg like a comic?
    print("This example preprocessor only preprocesses eBooks")

exit(0)
