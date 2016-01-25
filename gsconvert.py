#!/usr/bin/python

import os
import sys
import subprocess

if len(sys.argv) != 3:
    print "Usage: gsconvert input.pdf output.jpg"
else:
    params = ["which", "gs"]
    try:
        GS = subprocess.check_output(params, stderr=subprocess.STDOUT).strip()        
        if os.path.isfile(GS):
            try:
                jpeg = sys.argv[2]
                pdf = sys.argv[1]
                if '[' in pdf:
                    pdf = pdf.split('[')[0]
                params = [GS, "-sDEVICE=jpeg", "-dNOPAUSE", "-dBATCH", "-dSAFER", "-dFirstPage=1", "-dLastPage=1",
                          "-sOutputFile=" + jpeg, pdf ]
                res = subprocess.check_output(params, stderr=subprocess.STDOUT)
                if not os.path.isfile(jpeg):
                    print("Failed: %s" % res)
            except subprocess.CalledProcessError as e:
                print("Failed: %s" % e)
        else:
            print ("Cannot find gs, [%s] unable to continue" % GS)
    except:
        print ("Cannot find gs, unable to continue")    

