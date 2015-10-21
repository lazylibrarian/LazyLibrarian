#!/usr/bin/env python
# encoding: utf-8
"""
Mobi.py

Created by Elliot Kroo on 2009-12-25.
Copyright (c) 2009 Elliot Kroo. All rights reserved.
"""

import sys
import os
import unittest
from struct import *
from pprint import pprint
import utils
from lz77 import uncompress_lz77

mobilangdict = {
		54 : {0 : 'af'}, # Afrikaans
		28 : {0 : 'sq'}, # Albanian
		 1 : {0 : 'ar' , 5 : 'ar-dz' , 15 : 'ar-bh' , 3 : 'ar-eg' , 2 : 'ar-iq',  11 : 'ar-jo' , 13 : 'ar-kw' , 12 : 'ar-lb' , 4: 'ar-ly', 6 : 'ar-ma' , 8 : 'ar-om' , 16 : 'ar-qa' , 1 : 'ar-sa' , 10 : 'ar-sy' , 7 : 'ar-tn' , 14 : 'ar-ae' , 9 : 'ar-ye'}, # Arabic,  Arabic (Algeria),  Arabic (Bahrain),  Arabic (Egypt),  Arabic (Iraq), Arabic (Jordan),  Arabic (Kuwait),  Arabic (Lebanon),  Arabic (Libya), Arabic (Morocco),  Arabic (Oman),  Arabic (Qatar),  Arabic (Saudi Arabia),  Arabic (Syria),  Arabic (Tunisia),  Arabic (United Arab Emirates),  Arabic (Yemen)
		43 : {0 : 'hy'}, # Armenian
		77 : {0 : 'as'}, # Assamese
		44 : {0 : 'az'}, # "Azeri (IANA: Azerbaijani)
		45 : {0 : 'eu'}, # Basque
		35 : {0 : 'be'}, # Belarusian
		69 : {0 : 'bn'}, # Bengali
		 2 : {0 : 'bg'}, # Bulgarian
		 3 : {0 : 'ca'}, # Catalan
		 4 : {0 : 'zh' , 3 : 'zh-hk' , 2 : 'zh-cn' , 4 : 'zh-sg' , 1 : 'zh-tw'}, # Chinese,  Chinese (Hong Kong),  Chinese (PRC),  Chinese (Singapore),  Chinese (Taiwan)
		26 : {0 : 'hr'}, # Croatian
		 5 : {0 : 'cs'}, # Czech
		 6 : {0 : 'da'}, # Danish
		19 : {1 : 'nl' , 2 : 'nl-be'}, # Dutch / Flemish,  Dutch (Belgium)
		 9 : {1 : 'en' , 3 : 'en-au' , 40 : 'en-bz' , 4 : 'en-ca' , 6 : 'en-ie' , 8 : 'en-jm' , 5 : 'en-nz' , 13 : 'en-ph' , 7 : 'en-za' , 11 : 'en-tt' , 2 : 'en-gb', 1 : 'en-us' , 12 : 'en-zw'}, # English,  English (Australia),  English (Belize),  English (Canada),  English (Ireland),  English (Jamaica),  English (New Zealand),  English (Philippines),  English (South Africa),  English (Trinidad),  English (United Kingdom),  English (United States),  English (Zimbabwe)
		37 : {0 : 'et'}, # Estonian
		56 : {0 : 'fo'}, # Faroese
		41 : {0 : 'fa'}, # Farsi / Persian
		11 : {0 : 'fi'}, # Finnish
		12 : {1 : 'fr' , 2 : 'fr-be' , 3 : 'fr-ca' , 5 : 'fr-lu' , 6 : 'fr-mc' , 4 : 'fr-ch'}, # French,  French (Belgium),  French (Canada),  French (Luxembourg),  French (Monaco),  French (Switzerland)
		55 : {0 : 'ka'}, # Georgian
		 7 : {1 : 'de' , 3 : 'de-at' , 5 : 'de-li' , 4 : 'de-lu' , 2 : 'de-ch'}, # German,  German (Austria),  German (Liechtenstein),  German (Luxembourg),  German (Switzerland)
		 8 : {0 : 'el'}, # Greek, Modern (1453-)
		71 : {0 : 'gu'}, # Gujarati
		13 : {0 : 'he'}, # Hebrew (also code 'iw'?)
		57 : {0 : 'hi'}, # Hindi
		14 : {0 : 'hu'}, # Hungarian
		15 : {0 : 'is'}, # Icelandic
		33 : {0 : 'id'}, # Indonesian
		16 : {1 : 'it' , 2 : 'it-ch'}, # Italian,  Italian (Switzerland)
		17 : {0 : 'ja'}, # Japanese
		75 : {0 : 'kn'}, # Kannada
		63 : {0 : 'kk'}, # Kazakh
		87 : {0 : 'x-kok'}, # Konkani (real language code is 'kok'?)
		18 : {0 : 'ko'}, # Korean
		38 : {0 : 'lv'}, # Latvian
		39 : {0 : 'lt'}, # Lithuanian
		47 : {0 : 'mk'}, # Macedonian
		62 : {0 : 'ms'}, # Malay
		76 : {0 : 'ml'}, # Malayalam
		58 : {0 : 'mt'}, # Maltese
		78 : {0 : 'mr'}, # Marathi
		97 : {0 : 'ne'}, # Nepali
		20 : {0 : 'no'}, # Norwegian
		72 : {0 : 'or'}, # Oriya
		21 : {0 : 'pl'}, # Polish
		22 : {2 : 'pt' , 1 : 'pt-br'}, # Portuguese,  Portuguese (Brazil)
		70 : {0 : 'pa'}, # Punjabi
		23 : {0 : 'rm'}, # "Rhaeto-Romanic" (IANA: Romansh)
		24 : {0 : 'ro'}, # Romanian
		25 : {0 : 'ru'}, # Russian
		59 : {0 : 'sz'}, # "Sami (Lappish)" (not an IANA language code)
								  # IANA code for "Northern Sami" is 'se'
								  # 'SZ' is the IANA region code for Swaziland
		79 : {0 : 'sa'}, # Sanskrit
		26 : {3 : 'sr'}, # Serbian
		27 : {0 : 'sk'}, # Slovak
		36 : {0 : 'sl'}, # Slovenian
		46 : {0 : 'sb'}, # "Sorbian" (not an IANA language code)
								  # 'SB' is IANA region code for 'Solomon Islands'
								  # Lower Sorbian = 'dsb'
								  # Upper Sorbian = 'hsb'
								  # Sorbian Languages = 'wen'
		10 : {0 : 'es' , 4 : 'es' , 44 : 'es-ar' , 64 : 'es-bo' , 52 : 'es-cl' , 36 : 'es-co' , 20 : 'es-cr' , 28 : 'es-do' , 48 : 'es-ec' , 68 : 'es-sv' , 16 : 'es-gt' , 72 : 'es-hn' , 8 : 'es-mx' , 76 : 'es-ni' , 24 : 'es-pa' , 60 : 'es-py' , 40 : 'es-pe' , 80 : 'es-pr' , 56 : 'es-uy' , 32 : 'es-ve'}, # Spanish,  Spanish (Mobipocket bug?),  Spanish (Argentina),  Spanish (Bolivia),  Spanish (Chile),  Spanish (Colombia),  Spanish (Costa Rica),  Spanish (Dominican Republic),  Spanish (Ecuador),  Spanish (El Salvador),  Spanish (Guatemala),  Spanish (Honduras),  Spanish (Mexico),  Spanish (Nicaragua),  Spanish (Panama),  Spanish (Paraguay),  Spanish (Peru),  Spanish (Puerto Rico),  Spanish (Uruguay),  Spanish (Venezuela)
		48 : {0 : 'sx'}, # "Sutu" (not an IANA language code)
								  # "Sutu" is another name for "Southern Sotho"?
								  # IANA code for "Southern Sotho" is 'st'
		65 : {0 : 'sw'}, # Swahili
		29 : {0 : 'sv' , 1 : 'sv' , 8 : 'sv-fi'}, # Swedish,  Swedish (Finland)
		73 : {0 : 'ta'}, # Tamil
		68 : {0 : 'tt'}, # Tatar
		74 : {0 : 'te'}, # Telugu
		30 : {0 : 'th'}, # Thai
		49 : {0 : 'ts'}, # Tsonga
		50 : {0 : 'tn'}, # Tswana
		31 : {0 : 'tr'}, # Turkish
		34 : {0 : 'uk'}, # Ukrainian
		32 : {0 : 'ur'}, # Urdu
		67 : {2 : 'uz'}, # Uzbek
		42 : {0 : 'vi'}, # Vietnamese
		52 : {0 : 'xh'}, # Xhosa
		53 : {0 : 'zu'}, # Zulu
}
  	

class Mobi:
 	
  def parse(self):
    """ reads in the file, then parses record tables"""
    self.contents = self.f.read();
    self.header = self.parseHeader();
    self.records = self.parseRecordInfoList();
    self.readRecord0()

  def readRecord(self, recordnum, disable_compression=False):
    if self.config:
      if self.config['palmdoc']['Compression'] == 1 or disable_compression:
        return self.contents[self.records[recordnum]['record Data Offset']:self.records[recordnum+1]['record Data Offset']];
      elif self.config['palmdoc']['Compression'] == 2:
        result = uncompress_lz77(self.contents[self.records[recordnum]['record Data Offset']:self.records[recordnum+1]['record Data Offset']-self.config['mobi']['extra bytes']])
        return result

  def readImageRecord(self, imgnum):
    if self.config:
      recordnum = self.config['mobi']['First Image index'] + imgnum;
      return self.readRecord(recordnum, disable_compression=True);

  def author(self):
    "Returns the author of the book, or "" if none provided"
    try:
      txt = self.config['exth']['records'][100]
      return txt
    except:
      return ""

  def title(self):
    "Returns the title of the book, or "" if none provided"
    try:
      txt = self.config['mobi']['Full Name']
      return txt
    except:
      return ""

  def language(self):
    "Returns the language of the book, or "" if none provided"
    try:
      langcode = int(self.config['mobi']['Language'])
      langID = langcode & 0xFF
      sublangID = (langcode >> 10) & 0xFF
      return mobilangdict.get(int(langID), {0 : 'en'}).get(int(sublangID), 'en')
    except:
      return ""

  def isbn(self):
    "Returns the isbn of the book, or "" if none provided"
    try:
      txt = self.config['exth']['records'][104]
      return txt
    except:
      return ""

###########  Private API ###########################

  def __init__(self, filename):
    try:
      if isinstance(filename, str):
        self.f = open(filename, "rb");
      else:
        self.f = filename;
    except IOError,e:
      sys.stderr.write("Could not open %s! " % filename);
      raise e;
    self.offset = 0;

  def __iter__(self):
    if not self.config: return;
    for record in range(1, self.config['mobi']['First Non-book index'] - 1):
      yield self.readRecord(record);

  def parseRecordInfoList(self):
    records = {};
    # read in all records in info list
    for recordID in range(self.header['number of records']):
      headerfmt = '>II'
      headerlen = calcsize(headerfmt)
      fields = [
        "record Data Offset",
        "UniqueID",
      ]
      # create tuple with info
      results = zip(fields, unpack(headerfmt, self.contents[self.offset:self.offset+headerlen]))

      # increment offset into file
      self.offset += headerlen

      # convert tuple to dictionary
      resultsDict = utils.toDict(results);

      # futz around with the unique ID record, as the uniqueID's top 8 bytes are
      # really the "record attributes":
      resultsDict['record Attributes'] = (resultsDict['UniqueID'] & 0xFF000000) >> 24;
      resultsDict['UniqueID'] = resultsDict['UniqueID'] & 0x00FFFFFF;

      # store into the records dict
      records[resultsDict['UniqueID']] = resultsDict;

    return records;

  def parseHeader(self):
    headerfmt = '>32shhIIIIII4s4sIIH'
    headerlen = calcsize(headerfmt)
    fields = [
      "name",
      "attributes",
      "version",
      "created",
      "modified",
      "backup",
      "modnum",
      "appInfoId",
      "sortInfoID",
      "type",
      "creator",
      "uniqueIDseed",
      "nextRecordListID",
      "number of records"
    ]

    # unpack header, zip up into list of tuples
    results = zip(fields, unpack(headerfmt, self.contents[self.offset:self.offset+headerlen]))

    # increment offset into file
    self.offset += headerlen

    # convert tuple array to dictionary
    resultsDict = utils.toDict(results);

    return resultsDict

  def readRecord0(self):
    palmdocHeader = self.parsePalmDOCHeader();
    MobiHeader = self.parseMobiHeader();
    exthHeader = None
    if MobiHeader['Has EXTH Header']:
      exthHeader = self.parseEXTHHeader();

    self.config = {
      'palmdoc': palmdocHeader,
      'mobi' : MobiHeader,
      'exth' : exthHeader
    }

  def parseEXTHHeader(self):
    headerfmt = '>III'
    headerlen = calcsize(headerfmt)

    fields = [
      'identifier',
      'header length',
      'record Count'
    ]

    # unpack header, zip up into list of tuples
    results = zip(fields, unpack(headerfmt, self.contents[self.offset:self.offset+headerlen]))

    # convert tuple array to dictionary
    resultsDict = utils.toDict(results);

    self.offset += headerlen;
    resultsDict['records'] = {};
    for record in range(resultsDict['record Count']):
      recordType, recordLen = unpack(">II", self.contents[self.offset:self.offset+8]);
      recordData = self.contents[self.offset+8:self.offset+recordLen];
      resultsDict['records'][recordType] = recordData;
      self.offset += recordLen;

    return resultsDict;

  def parseMobiHeader(self):
    headerfmt = '> IIII II 40s III IIIII IIII I 36s IIII 8s HHIIIII'
    headerlen = calcsize(headerfmt)

    fields = [
      "identifier",
      "header length",
      "Mobi type",
      "text Encoding",

      "Unique-ID",
      "Generator version",

      "-Reserved",

      "First Non-book index",
      "Full Name Offset",
      "Full Name Length",

      "Language",
      "Input Language",
      "Output Language",
      "Format version",
      "First Image index",

      "First Huff Record",
      "Huff Record Count",
      "First DATP Record",
      "DATP Record Count",

      "EXTH flags",

      "-36 unknown bytes, if Mobi is long enough",

      "DRM Offset",
      "DRM Count",
      "DRM Size",
      "DRM Flags",

      "-Usually Zeros, unknown 8 bytes",

      "-Unknown",
      "Last Image Record",
      "-Unknown",
      "FCIS record",
      "-Unknown",
      "FLIS record",
      "Unknown"
    ]

    # unpack header, zip up into list of tuples
    results = zip(fields, unpack(headerfmt, self.contents[self.offset:self.offset+headerlen]))

    # convert tuple array to dictionary
    resultsDict = utils.toDict(results);

    resultsDict['Start Offset'] = self.offset;

    resultsDict['Full Name'] = (self.contents[
      self.records[0]['record Data Offset'] + resultsDict['Full Name Offset'] :
      self.records[0]['record Data Offset'] + resultsDict['Full Name Offset'] + resultsDict['Full Name Length']])

    resultsDict['Has DRM'] = resultsDict['DRM Offset'] != 0xFFFFFFFF;

    resultsDict['Has EXTH Header'] = (resultsDict['EXTH flags'] & 0x40) != 0;

    self.offset += resultsDict['header length'];

    def onebits(x, width=16):
        return len(filter(lambda x: x == "1", (str((x>>i)&1) for i in xrange(width-1,-1,-1))));

    resultsDict['extra bytes'] = 2*onebits(unpack(">H", self.contents[self.offset-2:self.offset])[0] & 0xFFFE)

    return resultsDict;

  def parsePalmDOCHeader(self):
    headerfmt = '>HHIHHHH'
    headerlen = calcsize(headerfmt)
    fields = [
      "Compression",
      "Unused",
      "text length",
      "record count",
      "record size",
      "Encryption Type",
      "Unknown"
    ]
    offset = self.records[0]['record Data Offset'];
    # create tuple with info
    results = zip(fields, unpack(headerfmt, self.contents[offset:offset+headerlen]))

    # convert tuple array to dictionary
    resultsDict = utils.toDict(results);

    self.offset = offset+headerlen;
    return resultsDict

class MobiTests(unittest.TestCase):
  def setUp(self):
    self.mobitest = Mobi("../test/CharlesDarwin.mobi");
  def testParse(self):
    self.mobitest.parse();
    pprint (self.mobitest.config)
  def testRead(self):
    self.mobitest.parse();
    content = ""
    for i in range(1,5):
      content += self.mobitest.readRecord(i);
  def testImage(self):
    self.mobitest.parse();
    pprint (self.mobitest.records);
    for record in range(4):
      f = open("imagerecord%d.jpg" % record, 'w')
      f.write(self.mobitest.readImageRecord(record));
      f.close();
  def testAuthorTitle(self):
    self.mobitest.parse()
    self.assertEqual(self.mobitest.author(), 'Charles Darwin')
    self.assertEqual(self.mobitest.title(), 'The Origin of Species by means '+
        'of Natural Selection, 6th Edition')

if __name__ == '__main__':
  unittest.main()
