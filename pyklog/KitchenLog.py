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


class KitchenLog:
    def __init__(self, directory):
        self._directory = directory
        target_entries = glob(join(self._directory, '20*', '*', '*.txt'))
        self._entries = [LogEntry(x) for x in target_entries]

    def commit(self):
        list(map(lambda x: x.save(), [x for x in self._entries if x.dirty]))

    def export_dokuwiki(self, target_path):
        for entry in self._entries:
            entry.to_dokuwiki(target_path)