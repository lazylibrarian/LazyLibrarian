#!/usr/bin/python

import os
import sys
import subprocess

if len(sys.argv) != 3:
    print "Usage: gsconvert input.pdf output.jpg"
else:
    GS = os.path.join(os.getcwd(), "gs")
    if not os.path.isfile(GS):
        params = ["which", "gs"]
        try:
            GS = subprocess.check_output(params, stderr=subprocess.STDOUT).strip()        
        except:
            print("Cannot find gs, unable to continue")
    if os.path.isfile(GS):
        try:
            params = [GS, "--version"]
            res = subprocess.check_output(params, stderr=subprocess.STDOUT)
            print("Using gs [%s] version %s" % (GS, res))
            jpeg = sys.argv[2]
            pdf = sys.argv[1]
            if '[' in pdf:
                pdf = pdf.split('[')[0]
            params = [GS, "-sDEVICE=jpeg", "-dNOPAUSE", "-dBATCH", "-dSAFER", "-dFirstPage=1", "-dLastPage=1",
                      "-sOutputFile=%s" % jpeg, pdf ]
            res = subprocess.check_output(params, stderr=subprocess.STDOUT)
            if not os.path.isfile(jpeg):
                print("Failed: %s" % res)
        except subprocess.CalledProcessError as e:
            print("Failed: %s" % e)
    else:
        print ("Cannot find gs, [%s] unable to continue" % GS)

