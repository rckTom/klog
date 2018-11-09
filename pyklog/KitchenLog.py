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
from os.path import join, normpath

from jinja2 import Template

from .LogEntry import LogEntry

landing_page = Template(
"""====== Küchen-Log ======

{% for year, months in content|dictsort(reverse=true) -%}
===== {{ year }} =====
{% for month, entries in months|dictsort(reverse=true) -%}
{% raw %}  {% endraw %}* [[:kitchenlog:{{ year }}-{{ '%02d' % month }}|{{ entries[0].date_raw.strftime('%B') }}]]
{% endfor %}
{% endfor %}
""")

month_page = Template(
"""====== Küchen-Log {{ date.strftime('%B %Y') }} ======

**//If it's not in the log, it didn't happen!//**

{% raw %}{{{% endraw -%}blog>kitchenlog:entry:{{ date.year }}:{{ '%02d' % date.month }}?31&nouser&nodate&nomdate{% raw %}}}{% endraw %}

""")


def load_entry(directory, file):
    try:
        entry = LogEntry.from_file(directory, file)
    except Exception as e:
        print('Ignoring corrupt entry %s: %s' % (file, str(e)))
        return None
    return entry


def save_filename(content, file):
    with open(file, 'w') as f:
        f.write(content)


class KitchenLog:
    def __init__(self, directory):
        self._directory = normpath(directory)
        target_entries = glob(join(self._directory, '20*', '*', '*.txt'))
        target_entries = [x[(len(self._directory) + 1):] for x in target_entries]
        self._entries = [load_entry(self._directory, x) for x in target_entries]
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

        dates = {entry.date_raw for entry in self._entries}
        years = dict()
        for year in {x.year for x in dates}:
            years[year] = {
                x.month:
                    [entry for entry in self._entries
                     if entry.date_raw.year == year and entry.date_raw.month == x.month]
                for x in dates
                if x.year == year}

        for year, months in years.items():
            for month, entries in months.items():
                month_rendered = month_page.render(date=entries[0].date_raw)
                save_filename(month_rendered, join(target_path, '%d-%02d.txt'% (year, month)))

        lp = landing_page.render(content=years)
        save_filename(lp, join(target_path, 'start.txt'))
