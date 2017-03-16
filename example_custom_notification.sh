#!/bin/bash
# The parameter list passed is a list of database columns (name and data)
# for a book or magazine.
# For this example, just write the arguments to a file

ofile='notification.out'
echo -n "" > $ofile
arg=1
numargs=$#
while (( arg < numargs)); do
    # column name
    echo -n "${!arg}: " >> $ofile
    (( arg += 1 ))
    # value
    echo "${!arg}" >> $ofile
    (( arg += 1 ))
done
