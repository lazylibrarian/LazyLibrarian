#!/usr/bin/env python
# encoding: utf-8
"""
utils.py

Created by Elliot Kroo on 2009-12-25.
Copyright (c) 2009 Elliot Kroo. All rights reserved.
"""

import sys
import os
import unittest


def toDict(tuples):
  resultsDict = {}
  for field, value in tuples:
    if len(field) > 0 and field[0] != "-":
      resultsDict[field] = value
  return resultsDict;
