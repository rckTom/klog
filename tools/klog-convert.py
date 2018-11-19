#!/usr/bin/env python3

"""
klog-convert - Convert the Dokuwiki kitchenlog sites to an abstract format

Copyright (c) Binary Kitchen e.V., 2018

Author:
  Ralf Ramsauer <ralf@binary-kitchen.de>

This work is licensed under the terms of the GNU GPL, version 2.  See
the LICENSE file in the top-level directory.

This program is distributed in the hope that it will be useful, but WITHOUT
ANY WARRANTY; without even the implied warranty of MERCHANTABILITY or FITNESS
FOR A PARTICULAR PURPOSE.  See the GNU General Public License for more
details.
"""

import dateparser
import glob
import re
import os

from shutil import copyfile

wiki = '/mnt/lokal/@tmp/wiki'
pages = 'data/pages/kitchenlog'
output = '/home/ralf/.cache/klog/kitchenlog'

target_media = os.path.join(output, 'media')

log_entry_regex = r'^===== (.*) =====$'
media_regex = r'({{.*?}})'
header_regex = r'(.*): (.*)'

date_range_appendix_regex   = r'.*?, (.*) bis .*?, (.*) (.*), (.*)'
date_range_simple_regex     = r'.*?, (.*) bis .*?, (.*) (.*)'
date_regular_appendix_regex = r'.*?, (.*), (.*)'
date_regular_simple_regex   = r'.*?, (.*)'

medium_regex = r'{{\s*(.*?)\s?\|?\s*}}'


def parse_format_date(string):
    return dateparser.parse(string).strftime('%Y-%m-%d')


def parse_range_date(match, appendix):
    begin = match.group(1)
    end = match.group(2)
    year = match.group(3)

    begin = parse_format_date(begin + ' ' + year)
    end = parse_format_date(end + ' ' + year)

    return begin, end, appendix

def parse_regular_date(match, appendix):
    begin = parse_format_date(match.group(1))

    return begin, None, appendix

def parse_date(string):
    test = re.match(date_range_appendix_regex, string)
    if test:
        return parse_range_date(test, test.group(4))

    test = re.match(date_range_simple_regex, string)
    if test:
        return parse_range_date(test, None)

    test = re.match(date_regular_appendix_regex, string)
    if test:
        return parse_regular_date(test, test.group(2))

    test = re.match(date_regular_simple_regex, string)
    if test:
        return parse_regular_date(test, None)

    print('Unknown date format: %s' % string)
    quit()


def convert_medium(medium):
    medium = re.match(medium_regex, medium)
    if not medium:
        print('Potzdonner!')
        quit()
    medium = medium.group(1).split('?')
    file = medium[0]

    options = ''
    if len(medium) == 2:
        for width in medium[1].split('&'):
            try:
                options = int(width)
            except ValueError:
                continue
            break

    # Locate the file.
    file = re.sub(r':', '/', file[1:])

    return file, options

def convert_entry(entry):
    header, content = entry

    media = re.findall(media_regex, content)

    header = re.search(header_regex, header)
    topic, date = header.group(1), header.group(2)

    content = re.sub(media_regex, '', content)
    content = content.rstrip('\n').lstrip('\n')
    # remove duplicate linebreaks
    content = re.sub(r'\n+', r'\n', content)
    # Remove Mogli's plenks
    content = re.sub(r' !', r'!', content)
    content = re.sub(r' \.', r' \.', content)

    date = parse_date(date)

    media = [convert_medium(x) for x in media]

    return date, topic, content, media


def convert_file(filename):
    ret = []

    with open(filename, 'r') as f:
        content = f.read()

    fragments = re.split(log_entry_regex, content, flags=re.MULTILINE)
    if len(fragments) < 3:
        print('Invalid input %s' % filename)
        return ret
    fragments.pop(0)
    if len(fragments) % 2 != 0:
        print('Invalid input length %s' % filename)
        return ret
    it = iter(fragments)
    fragments = list(zip(it, it))

    # Iterate over entries, parse date and factor out media
    for fragment in fragments:
        ret.append(convert_entry(fragment))

    return ret

def generate_medium(index, date, medium):
    filename, options = medium

    real_file = os.path.join(wiki, 'data/media', filename)
    if not os.path.isfile(real_file):
        print('File does not exist: %s' % real_file)
        quit()

    base = os.path.basename(real_file)

    target_dir = os.path.join(target_media, date.replace('-', '/'), str(index))
    os.makedirs(target_dir, exist_ok=True)
    copyfile(real_file, os.path.join(target_dir, base))

    if options == '':
        return filename
    return '%s, %s' % (base, options)

def generate_entry(index, entry):
    date, topic, content, media = entry

    for medium in media:
        generate_medium(index, date[0], medium)

    ret = \
"""BEGIN: %s
END: %s
TOPIC: %s
APPENDIX: %s

%s
""" % (date[0], date[1], topic, date[2], content)

    return ret


targets = glob.glob(os.path.join(wiki, pages, '201?-*.txt'))
targets += glob.glob(os.path.join(wiki, pages, 'entry', '*/*/*.txt'))
log_entries = dict()

for target in targets:
    #print('Parsing %s...' % target)
    entries = convert_file(target)
    for entry in entries:
        begin = entry[0][0]
        if begin not in log_entries:
            log_entries[begin] = list()
        log_entries[begin].append(entry)

os.makedirs(os.path.join(target_media), exist_ok=True)
for date, entries in log_entries.items():
    #print('Generating abstract entry for %s: %d kitchenlog entries' % (date, len(entries)))
    y, m, d = date.split('-')
    target_dir = os.path.join(output, y, m)
    os.makedirs(target_dir, exist_ok=True)
    for index, entry in enumerate(entries):
        filename = '%s-%d.txt' % (d, index)
        with open(os.path.join(target_dir, filename), 'w') as f:
            f.write(generate_entry(index, entry))
