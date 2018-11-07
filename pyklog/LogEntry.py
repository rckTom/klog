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


def parse_defval(value):
    if value.lower() == 'none' or not value:
        return None
    return value


def parse_ymd(value):
    value = parse_defval(value)
    if value:
        value = datetime.strptime(value, '%Y-%m-%d')
    return value


def format_defval(value):
    if not value:
        return 'None'
    return value


def format_ymd(dt):
    if not dt:
        return format_defval(dt)
    return dt.strftime('%Y-%m-%d')


class LogEntry:
    def __init__(self, log_entry):
        self.headers = dict()
        self.headers['MEDIA'] = list()

        headers, self.content = log_entry.split('\n\n', 1)
        headers = headers.split('\n')
        headers = [header.split(': ', 1) for header in headers]

        for key, value in headers:
            if key == 'BEGIN':
                self.headers[key] = parse_ymd(value)
            elif key == 'END':
                self.headers[key] = parse_ymd(value)
            elif key == 'MEDIA':
                self.headers[key].append(value)
            else:
                self.headers[key] = parse_defval(value)

    def __str__(self):
        ret = ''
        ret += 'BEGIN: %s\n' % format_ymd(self.headers['BEGIN'])
        ret += 'END: %s\n' % format_ymd(self.headers['END'])
        ret += 'TOPIC: %s\n' % format_defval(self.headers['TOPIC'])
        ret += 'APPENDIX: %s\n' % format_defval(self.headers['APPENDIX'])
        ret += '\n'
        ret += self.content

        return ret

    @staticmethod
    def from_file(filename):
        with open(filename, 'r') as f:
            return LogEntry(f.read())

    def to_file(self, filename):
        with open(filename, 'w') as f:
            f.write(str(self))
