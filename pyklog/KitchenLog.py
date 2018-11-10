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

from os import remove

import datetime
import email
import re

from email.mime.text import MIMEText
from email.header import decode_header

from glob import glob
from jinja2 import Template
from os.path import join, normpath

from .LogEntry import LogEntry, parse_ymd

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
mail_end_marker = '%% END %%'
quopri_entry = re.compile(r'=\?[\w-]+\?[QB]\?[^?]+?\?=')


def normalise_subject(mail):
    return re.match(r'(.*: )*(.*)', mail['SUBJECT']).group(2)


def respond_email(mail, subject, response):
    msg = MIMEText(response)

    if 'Reply-To' in mail:
        msg['To'] = mail['Reply-To']
    else:
        msg['To'] = mail['from']

    msg['From'] = mail['To']
    msg['Subject'] = 'Re: %s' % subject
    msg['In-Reply-To'] = mail['Message-ID']
    msg['References'] = mail['Message-ID']
    msg.preamble = 'Wer das liest ist doof :-)\n'
    if 'References' in mail:
        msg['References'] += mail['References']

    return msg


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


def decode_payload(message_part):
    charset = message_part.get_content_charset()
    if charset.lower() == 'utf-8' or charset.startswith('iso-8859'):
        content = message_part.get_payload(decode=True).decode(charset)
    else:
        content = message_part.get_payload()
    return content


def serialise_multipart(mail):
    ret = []
    parts = mail.get_payload()
    for part in parts:
        if part.get_content_maintype() == 'multipart':
            ret += serialise_multipart(part)
        else:
            ret.append(part)
    return ret


def decode_multiple(encoded, _pattern=quopri_entry):
    if not quopri_entry.match(encoded):
        return encoded
    fixed = '\r\n'.join(_pattern.findall(encoded))
    output = [b.decode(c) for b, c in decode_header(fixed)]
    return ''.join(output)


class KitchenLog:
    FILES_GLOB = join('20*', '*', '*.txt')

    def __init__(self, directory):
        self._directory = normpath(directory)
        target_entries = glob(join(self._directory, KitchenLog.FILES_GLOB))
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
        # delete old data
        target_entries = glob(join(target_path, 'entry', KitchenLog.FILES_GLOB))
        target_entries += glob(join(target_path, '*.txt'))
        for target in target_entries:
            remove(target)

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

    def handle_email(self, mail):
        mail = email.message_from_bytes(mail)
        subject = normalise_subject(mail)
        update_repo = False

        def error_respond(message):
            return False, respond_email(mail, 'Error: %s' % subject, message)

        split_subject = subject.split(' ')
        if len(split_subject) == 1:
            command = split_subject[0]
            date = datetime.datetime.today()
        elif len(split_subject) == 2:
            command = split_subject[0]
            date = parse_ymd(split_subject[1])
            if not date:
                return error_respond('Invalid date format: %s' % split_subject[1])
        else:
            return error_respond('Invalid command: ' % subject)

        content = None
        attachments = list()
        if mail.get_content_type() == 'text/plain':
            content = mail.get_payload()
        elif mail.get_content_maintype() == 'multipart':
            parts = serialise_multipart(mail)
            for i, part in enumerate(parts):
                if part.get_content_type() == 'text/plain':
                    content = parts.pop(i)
                    content = decode_payload(content)
                    break
            attachments = parts

        attachments = [x for x in attachments if x.get_content_maintype() == 'image']

        if content is None:
            return error_respond('Sorry, %s not supported' % mail.get_content_type())

        # normalise content
        content = content.strip().split('\n')
        found_entry = False
        for no, line in enumerate(content):
            if line == mail_end_marker:
                content = content[0:no]
                found_entry = True
                break
        content = '\n'.join(content).strip()

        if command.lower() == 'new':
            new = self.new_entry(date)
            if found_entry:
                try:
                    new.reload(content, True)
                    for attachment in attachments:
                        attachment_raw = attachment.get_payload(decode=True)
                        filename = decode_multiple(attachment.get_filename())
                        new.attach_media(filename, attachment_raw)
                except ValueError as e:
                    return error_respond('Parser error: %s\n\nOriginal mail below\n--\n\n%s' % (str(e), content))
                response = 'Success.\n\nNew entry below\n--\n\n%s' % str(new)
                update_repo = True
            else:
                response = '# Copy text, reply to this mail, paste text and send it. \n' \
                           '# Dont remove the %s line!\n%s\n%s\n' % (mail_end_marker, str(new), mail_end_marker)
        else:
            return error_respond('Unknown command: %s' % command)

        return update_repo, respond_email(mail, 'OK: %s' % subject, response)
