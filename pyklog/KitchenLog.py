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

from glob import glob
from os.path import join

from .LogEntry import LogEntry


def load_entry(directory, file):
    try:
        entry = LogEntry.from_file(directory, file)
    except Exception as e:
        print('Ignoring corrupt entry %s: %s' % (file, str(e)))
        return None
    return entry


class KitchenLog:
    def __init__(self, directory):
        self._directory = directory
        target_entries = glob(join(self._directory, '20*', '*', '*.txt'))
        target_entries = [x[(len(directory) + 1):] for x in target_entries]
        self._entries = [load_entry(directory, x) for x in target_entries]
        self._entries = list(filter(None, self._entries))

    def commit(self):
        list(map(lambda x: x.save(), [x for x in self._entries if x.dirty]))

    def get(self, date):
        return [x for x in self._entries if x._begin == date]

    def new_entry(self, date):
        entry = LogEntry.new(self._directory, date)
        self._entries.append(entry)
        return entry

    def export_dokuwiki(self, target_path):
        for entry in self._entries:
            entry.to_dokuwiki(target_path)
