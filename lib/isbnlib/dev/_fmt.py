# -*- coding: utf-8 -*-
# flake8: noqa
# pylint: skip-file
"""Format canonical in bibliographic formats."""

import re
import uuid
from string import Template

from ._helpers import last_first

bibtex = r"""@book{$ISBN,
     title = {$Title},
    author = {$AUTHORS},
      isbn = {$ISBN},
      year = {$Year},
 publisher = {$Publisher}
}"""

endnote = r"""%0 Book
%T $Title
%A $AUTHORS
%@ $ISBN
%D $Year
%I $Publisher """

refworks = r"""TY  - BOOK
T1  - $Title
A1  - $AUTHORS
SN  - $ISBN
Y1  - $Year
PB  - $Publisher
ER  - """

msword = r'''<b:Source xmlns:b="http://schemas.microsoft.com/office/'''\
         r'''word/2004/10/bibliography">
<b:Tag>$uid</b:Tag>
<b:SourceType>Book</b:SourceType>
<b:Author>
<b:NameList>$AUTHORS
</b:NameList>
</b:Author>
<b:Title>$Title</b:Title>
<b:Year>$Year</b:Year>
<b:City></b:City>
<b:Publisher>$Publisher</b:Publisher>
</b:Source>'''

json = r'''{"type": "book",
     "title": "$Title",
    "author": [$AUTHORS],
      "year": "$Year",
"identifier": [{"type": "ISBN", "id": "$ISBN"}],
 "publisher": "$Publisher"}'''

csl = r'''{"type":"book",
        "id":"$ISBN",
     "title":"$Title",
    "author": [$AUTHORS],
    "issued": {"date_parts": [[$Year]]},
      "ISBN":"$ISBN",
 "publisher":"$Publisher"}'''

opf = r"""<?xml version='1.0' encoding='utf-8'?>
<package version="2.0" xmlns="http://www.idpf.org/2007/opf" unique-identifier="uuid_id">
  <metadata xmlns:dc="http://purl.org/dc/elements/1.1/" xmlns:opf="http://www.idpf.org/2007/opf">
    <dc:type>Book</dc:type>
    <dc:identifier opf:scheme="uuid" id="uuid_id">$uid</dc:identifier>
    <dc:identifier opf:scheme="ISBN" id="isbn_id">$ISBN</dc:identifier>
    <dc:title>$Title</dc:title>
    $AUTHORS
    <dc:publisher>$Publisher</dc:publisher>
    <dc:date>$Year</dc:date>
    <dc:contributor opf:file-as="isbnlib" opf:role="mdc">isbnlib [http://github.com/xlcnd/isbnlib]</dc:contributor>
  </metadata>
</package>"""

labels = r"""Type:      BOOK
Title:     $Title
Author:    $AUTHORS
ISBN:      $ISBN
Year:      $Year
Publisher: $Publisher"""

templates = {
    'labels': labels,
    'bibtex': bibtex,
    'endnote': endnote,
    'refworks': refworks,
    'msword': msword,
    'json': json,
    'csl': csl,
    'opf': opf
}

_fmts = list(templates.keys())


def _gen_proc(name, canonical):
    if 'ISBN-13' in canonical:
        canonical['ISBN'] = canonical.pop('ISBN-13')
    tpl = templates[name]
    return Template(tpl).safe_substitute(canonical)


def _spec_proc(name, fmtrec, authors):
    """Fix the Authors records."""
    if name not in _fmts:
        return
    if name == 'labels':
        AUTHORS = '\nAuthor:    '.join(authors)
    elif name == 'bibtex':
        AUTHORS = ' and '.join(authors)
    elif name == 'refworks':
        AUTHORS = '\nA1  - '.join(authors)
    elif name == 'endnote':
        AUTHORS = '\n%A '.join(authors)
    elif name == 'msword':
        fmtrec = fmtrec.replace('$uid', str(uuid.uuid4()))
        person = r"<b:Person><b:Last>$last</b:Last>"\
                 r"<b:First>$first</b:First></b:Person>"
        AUTHORS = '\n'.join(
            Template(person).safe_substitute(last_first(a)) for a in authors)
    elif name == 'json':
        AUTHORS = ', '.join('{"name": "$"}'.replace("$", a) for a in authors)
    elif name == 'csl':
        AUTHORS = ', '.join(
            '{"literal": "$"}'.replace("$", a) for a in authors)
    elif name == 'opf':
        fmtrec = fmtrec.replace('$uid', str(uuid.uuid4()))
        creator = r'<dc:creator opf:file-as="$last, $first"'\
                  r' opf:role="aut">$first $last</dc:creator>'
        AUTHORS = '\n    '.join(
            Template(creator).safe_substitute(last_first(author))
            for author in authors)
    return re.sub(r'\$AUTHORS', AUTHORS, fmtrec)


def _fmtbib(fmtname, canonical):
    """Return a canonical record in the selected format."""
    return _spec_proc(fmtname, _gen_proc(fmtname, canonical),
                      canonical['Authors'])
