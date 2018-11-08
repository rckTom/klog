"""
klog - Binary Kitchen's log tool

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

from datetime import datetime
from jinja2 import Template
from os.path import join, isfile, split
from os import makedirs, remove
from os.path import splitext, dirname

dokuwiki_log_template = Template(
"""===== {{ topic }}: {{ date }} =====
{{ content }}
{{ media }}
""")
image_url = 'https://raw.githubusercontent.com/Binary-Kitchen/kitchenlog/master/media/'

log_entry_template = Template(
"""BEGIN: {{ today }}
END: None
TOPIC: Küchenzeit
APPENDIX: None

  * Hier kommen ein paar tolle Stichpunkte im Dokuwiki Format

"""
)


def parse_defval(value):
    if value.lower() == 'none' or not value:
        return None
    return value


def parse_ymd(value):
    value = parse_defval(value)
    if value:
        value = datetime.strptime(value, '%Y-%m-%d')
    return value


def parse_medium(value):
    value = value.split(', ')

    if len(value) == 1:
        return value[0], None
    elif len(value) == 2:
        return value[0], value[1]
    else:
        raise ValueError('Unknown media format: %s' % value)


def format_defval(value):
    if not value:
        return 'None'
    return value


def format_ymd(dt):
    if not dt:
        return format_defval(dt)
    return dt.strftime('%Y-%m-%d')


def format_german_date(dt, print_year):
    format = '%A, %d. %B'
    if print_year:
        format += ' %Y'
    return dt.strftime(format)


def generate_wikidate(begin, end):
    if end:
        begin = format_german_date(begin, False)
        end = format_german_date(end, True)
        return '%s bis %s' % (begin, end)
    return format_german_date(begin, True)


def generate_wikimedia(media):
    ret = ''
    for image, options in media:
        ret += '{{ %s/%s }}\n' % (image_url, image)
    return ret


class LogEntry:
    def __init__(self, content, directory):
        self.load(content, False)
        self._filename = None
        self._filename_date = None
        self._directory = directory

    @property
    def dirty(self):
        return self._dirty or (self._begin != self._filename_date)

    @property
    def topic(self):
        return self._headers['TOPIC']

    @property
    def date(self):
        return format_ymd(self._begin)

    @property
    def fname(self):
        return self._begin.strftime('%Y/%m/%d') + '-%d.txt' % self._no

    def set_filename(self, filename):
        self._filename = filename

        path, base = split(filename)
        base = splitext(base)[0]
        day, self._no = [int(x) for x in base.split('-')]

        path, month = split(path)
        _ , year = split(path)

        self._filename_date = parse_ymd('%s-%s-%s' % (year, month, day))

    def load(self, log_entry, dirty):
        self._dirty = dirty
        self._begin, self._end, self._headers, self._content, self._media = LogEntry.try_parse(log_entry)

    def save(self):
        if self._filename_date and self._begin != self._filename_date:
            remove(self._filename)
            self._filename = None

        if self._filename is None:
            self._no = 0
            while isfile(join(self._directory, self.fname)):
                self._no += 1

            self.set_filename(join(self._directory, self.fname))

        print('Saving %s' % self.fname)
        with open(self._filename, 'w') as f:
            f.write(str(self))

    def __str__(self):
        ret = ''
        ret += 'BEGIN: %s\n' % format_ymd(self._begin)
        ret += 'END: %s\n' % format_ymd(self._end)
        ret += 'TOPIC: %s\n' % format_defval(self._headers['TOPIC'])
        ret += 'APPENDIX: %s\n' % format_defval(self._headers['APPENDIX'])
        for filename, options in self._media:
            ret += 'MEDIA: %s' % filename
            if options:
                ret += ', %s' % options
            ret += '\n'
        ret += '\n'
        ret += self._content

        return ret

    def generate_dokuwiki(self):
        return dokuwiki_log_template.render(date = generate_wikidate(self._begin, self._end),
                                            topic = self._headers['TOPIC'],
                                            appendix = self._headers['APPENDIX'],
                                            content = self._content,
                                            media = generate_wikimedia(self._media))

    def to_dokuwiki(self, target_directory):
        target = join(target_directory, 'entry', self.fname)
        makedirs(dirname(target), exist_ok=True)

        with open(target, 'w') as f:
            f.write(self.generate_dokuwiki())

    @staticmethod
    def try_parse(log_entry):
        media = list()
        headers = dict()
        begin = None
        end = None

        headers_raw, content = log_entry.split('\n\n', 1)
        headers_raw = headers_raw.split('\n')
        headers_raw = [x for x in headers_raw if not x.startswith('# ')]
        headers_raw = [header.split(': ', 1) for header in headers_raw]

        for key, value in headers_raw:
            if key == 'BEGIN':
                begin = parse_ymd(value)
            elif key == 'END':
                end = parse_ymd(value)
            elif key == 'MEDIA':
                media.append(parse_medium(value))
            else:
                headers[key] = parse_defval(value)

        return begin, end, headers, content, media

    @staticmethod
    def from_file(directory, file):
        filename = join(directory, file)
        with open(filename, 'r') as f:
            content = f.read()

        entry = LogEntry(content, directory)
        entry.set_filename(filename)

        return entry

    @staticmethod
    def new(directory, date):
        template = log_entry_template.render(today = format_ymd(date))
        return LogEntry(template, directory)
