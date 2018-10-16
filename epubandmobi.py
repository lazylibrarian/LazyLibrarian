#!/usr/bin/env python
# -*- coding: UTF-8 -*-
#
from __future__ import print_function

import sys
import os
import subprocess

converter = "ebook-convert"  # if not in your "path", put the full pathname here
calibredb = "calibredb"      # and here too
books_parent_dir = '/media/eBooks' # change to your dir

for root, subFolders, files in os.walk(books_parent_dir):
    for name in files:
        for source, dest in [['.mobi', '.epub'], ['.epub', '.mobi']]:
            if name.endswith(source):
                source_file = (os.path.join(root, name))
                dest_file = source_file[:-len(source)] + dest
                if not os.path.exists(dest_file):
                    params = [converter, source_file, dest_file]
                    if dest == '.mobi':
                        params.extend(['--output-profile', 'kindle'])
                    try:
                        print("Creating %s for %s" % (dest, name))
                        res = subprocess.check_output(params, stderr=subprocess.STDOUT)

                        try:
                            calibreid = root.rsplit('(', 1)[1].split(')')[0]
                            if not calibreid.isdigit():
                                calibreid = ''
                        except IndexError:
                            calibreid = ''

                        if calibreid:
                            librarydir = os.path.dirname(os.path.dirname(root))
                            params = [calibredb, 'add_format', '--with-library=' + librarydir, calibreid, dest_file ]
                            try:
                                print("Telling calibre about new %s" % dest)
                                res = subprocess.check_output(params, stderr=subprocess.STDOUT)
                            except Exception as e:
                                print("%s\n" % e)

                    except Exception as e:
                        print("%s\n" % e)

