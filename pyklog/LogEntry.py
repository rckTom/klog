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
from glob import glob

from jinja2 import Template
from os.path import join, isfile, split
from os import makedirs, remove
from os.path import splitext, dirname, basename

dokuwiki_log_template = Template(
"""===== {{ content.topic }}: {{ content.wikidate }} {% if content.appendix %}({{ content.appendix }}){% endif %} =====
{{ content.content }}
{% if content.has_media %}
==== Bilder ====
{{ content.gallery }}
{% endif %}
""")
image_url = 'https://raw.githubusercontent.com/Binary-Kitchen/kitchenlog/master/'

log_entry_template = Template(
"""# Nach den headern muss eine Leerzeile folgen. Alle header sind anpassbar.
# Das Speichern einer leeren Datei löscht den Eintrag.
BEGIN: {{ today }}
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
        try:
            value = datetime.strptime(value, '%Y-%m-%d')
        except ValueError:
            return None
    return value


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


def mediadir(date, index):
    return join('media', date.strftime('%Y/%m/%d'), str(index))


class LogEntry:
    def __init__(self, content, index, directory):
        self._remove = False
        self._filename = None
        self._filename_date = None
        self._dirty = False
        self._directory = directory
        self._removed_media = set()
        self._added_media = set()
        self._index = index
        self._begin, self._end, self._headers, self._content, = LogEntry.try_parse(content)

        media = glob(join(self._directory, self.mediadir, '*'))
        self._media = [basename(x) for x in media]


    @property
    def dirty(self):
        return self._dirty or (self._begin != self._filename_date)

    @property
    def has_media(self):
        return len(self._media) > 0

    @property
    def media(self):
        return self._media

    @property
    def topic(self):
        return self._headers['TOPIC']

    @property
    def appendix(self):
        return self._headers['APPENDIX']

    @property
    def begin_ymd(self):
        return format_ymd(self._begin)

    @property
    def end_ymd(self):
        return format_ymd(self._end)

    @property
    def begin(self):
        return self._begin

    @property
    def end(self):
        return self._end

    @property
    def shortlog(self):
        return '%s: %s' % (self.begin_ymd, self.topic)

    @property
    def content(self):
        return self._content

    @property
    def mediadir(self):
        return mediadir(self._begin, self._index)

    @property
    def fname(self):
        return self._begin.strftime('%Y/%m/%d') + '-%d.txt' % self._index

    @property
    def gallery(self):
        return '{{gallery>:kitchenlog:%s:%d?direct&lightbox}}' % \
               (format_ymd(self.begin).replace('-', ':'), self._index)

    @property
    def wikidate(self):
        if self.end:
            begin = format_german_date(self.begin, False)
            end = format_german_date(self.end, True)
            return '%s bis %s' % (begin, end)
        return format_german_date(self.begin, True)


    def set_filename(self, filename):
        self._filename = filename

        path, base = split(filename)
        base = splitext(base)[0]
        day, self._index = [int(x) for x in base.split('-')]

        path, month = split(path)
        _ , year = split(path)

        self._filename_date = parse_ymd('%s-%s-%s' % (year, month, day))

    def reload(self, log_entry, dirty):
        self._dirty = dirty
        self._begin, self._end, self._headers, self._content = LogEntry.try_parse(log_entry)

    def save(self):
        mdir = join(self._directory, self.mediadir)
        if self._remove:
            if not self._filename:
                return
            for media in self._media:
                print('Removing media %s' % media)
                remove(join(mdir, media))
            print('Removing %s' % self.fname)
            remove(self._filename)
            return

        if self._filename_date and self._begin != self._filename_date:
            for media in self._media:
                victim = join(self._directory, mediadir(self._filename_date, self._index), media)
                with open(victim, 'rb') as content:
                    self._added_media.add((media, content.read()))
                remove(victim)
            remove(self._filename)
            self._filename = None

        if self._filename is None:
            self._index = 0
            while isfile(join(self._directory, self.fname)):
                self._index += 1

            self.set_filename(join(self._directory, self.fname))
            mdir = join(self._directory, self.mediadir)

        print('Saving %s' % self.fname)
        # ensure the underlying directory is existing
        makedirs(dirname(self._filename), exist_ok=True)
        with open(self._filename, 'w') as f:
            f.write(str(self))

        for media in self._removed_media:
            print('Removing media %s' % media)
            remove(join(mdir, media))

        if len(self._added_media):
            makedirs(mdir, exist_ok=True)

        for name, content in self._added_media:
            filename = join(mdir, name)
            with open(filename, 'wb') as f:
                f.write(content)

        self._added_media = set()
        self._removed_media = set()

    def remove_media(self, no):
        if no >= len(self._media):
            return

        victim = self._media.pop(no)
        self._removed_media.add(victim)

    def remove(self):
        self._dirty = True
        self._remove = True

    def attach_media(self, name, content):
        # TBD support attachment options
        self._media.append(name)
        self._added_media.add((name, content))

    def attach_media_by_file(self, filename):
        with open(filename, 'rb') as f:
            content = f.read()
        return self.attach_media(basename(filename), content)

    def __str__(self):
        ret = ''
        ret += 'BEGIN: %s\n' % format_ymd(self._begin)
        ret += 'END: %s\n' % format_ymd(self._end)
        ret += 'TOPIC: %s\n' % format_defval(self._headers['TOPIC'])
        ret += 'APPENDIX: %s\n' % format_defval(self._headers['APPENDIX'])
        ret += '\n'
        ret += self._content

        return ret

    def media_url(self, media):
        return '%s/%s/%s' % (image_url, self.mediadir, media)

    def generate_dokuwiki(self):
        return dokuwiki_log_template.render(content=self)

    def to_dokuwiki(self, target_directory):
        target = join(target_directory, 'entry', self.fname)
        makedirs(dirname(target), exist_ok=True)

        with open(target, 'w') as f:
            f.write(self.generate_dokuwiki())

    @staticmethod
    def sanitise_entry(log_entry):
        log_entry = log_entry.replace('\r', '')
        log_entry = '\n'.join([x.rstrip() for x in log_entry.split('\n')])
        log_entry = log_entry.rstrip() + '\n'
        return log_entry

    @staticmethod
    def try_parse(log_entry):
        headers = dict()
        begin = None
        end = None

        if not log_entry:
            raise ValueError('file is empty')

        log_entry = LogEntry.sanitise_entry(log_entry)

        try:
            headers_raw, content = log_entry.split('\n\n', 1)
            headers_raw = headers_raw.split('\n')
            headers_raw = [x for x in headers_raw if not x.startswith('# ')]
            headers_raw = [header.split(': ', 1) for header in headers_raw]
        except Exception as e:
            raise ValueError('unable to split header and content: %s' % str(e))

        for key, value in headers_raw:
            if key == 'BEGIN':
                begin = parse_ymd(value)
            elif key == 'END':
                end = parse_ymd(value)
            else:
                headers[key] = parse_defval(value)

        # sanity checks
        if begin is None:
            raise ValueError('Missing header: BEGIN')
        if 'TOPIC' not in headers:
            raise ValueError('Missing header: TOPIC')
        if 'APPENDIX' not in headers:
            raise ValueError('Missing header: APPENDIX')
        if not content:
            raise ValueError('Empty content')

        return begin, end, headers, content

    @staticmethod
    def from_file(directory, file):
        filename = join(directory, file)
        with open(filename, 'r') as f:
            content = f.read()

        index = int(file.rstrip('.txt').split('/')[2].split('-')[1])

        entry = LogEntry(content, index, directory)
        entry.set_filename(filename)

        return entry

    @staticmethod
    def new(directory, date):
        template = log_entry_template.render(today = format_ymd(date))
        return LogEntry(template, 0, directory)
