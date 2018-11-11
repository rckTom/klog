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

mail_greeting = 'Hi %s,\n'

mail_template_info = \
"""
Hi %s,
"""

mail_template_new = \
"""
this is the klog bot. It seems you attempt to create a new entry in the log
system. Let me assist! Please find your template below.
First, copy the content of this email to your clipboard, then reply to the
email, and paste the template.

Please amend headers. Note that you must not remove the last line that
denotes the end of the entry."""

mail_footer = \
"""
Yours sincerely,
  the klog bot
"""

mail_info_template = \
"""
this is the info page of the almighty klog bot -- a bot that assists to easily
manage entries in the kitchen log. Generally, you control the klob bot with the
subject line of your email, which contains a command and an optional date, and,
depending on the command, some formatted content in the body of the mail.

This is the list of available commands:
  info / help
  list
  new [date in Y-m-d format]

info:
  shows you this page

list:
  return a list of all entries

new:
  create a new entry.

  If you want to create a new entry, simply compose an email to the bot with
  the subject "new" or "new date" to the kitchen log bot. The bot will then
  reply with a template for the new entry. Copy the content to your clipoard,
  reply to the mail and amend changes as needed.

  Additional images may be attached as simple mail attachments.
"""

mail_success_template = \
"""
your entry was successfully added and will appear on the wiki soon. Thanks for
choosing Deutsche Bahn again! Exit on the left hand side.
"""

mail_list_template = \
"""
Please choose one of the following entries:
"""


def mail_list(recipient, entries):
    ret = (mail_greeting % recipient + mail_list_template).split('\n')
    ret += ['  %d: %s' % x for x in entries]
    ret.append(mail_footer)
    return '\n'.join(ret)


def mail_success(recipient, new):
    return mail_greeting % recipient + mail_success_template + mail_footer + '\n\n--\n' + new


def mail_new(recipient, template):
    new = (mail_greeting % recipient + mail_template_new + '\n' + mail_footer).split('\n')
    new = ['# %s' % x for x in new]
    new.append('\n')
    new += template.split('\n')
    new.append(mail_end_marker)

    return '\n'.join(new)


def mail_info(recipient):
    return mail_greeting % recipient + mail_info_template + mail_footer


def normalise_subject(mail):
    return re.match(r'(.*: )*(.*)', mail['SUBJECT']).group(2)


def respond_email(address_from, mail, subject, response):
    msg = MIMEText(response)

    if 'Reply-To' in mail:
        msg['To'] = mail['Reply-To']
    else:
        msg['To'] = mail['from']

    msg['From'] = address_from
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
        self._entries.sort(key=lambda x: x.date, reverse=True)

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

    def handle_email(self, address_from, mail):
        mail = email.message_from_bytes(mail)
        subject = normalise_subject(mail)
        update_repo = False

        recipient = mail['From']
        if recipient:
            recipient = re.sub(r' <.*@.*>', '', recipient)
        if not recipient:
            recipient = 'stranger'

        def error_respond(message):
            return False, respond_email(address_from, mail, 'Error: %s' % subject, message)

        split_subject = subject.split(' ')
        if len(split_subject) == 1:
            command = split_subject[0]
            argument = None
        elif len(split_subject) == 2:
            command = split_subject[0]
            argument = split_subject[1]
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
            if line.strip() == mail_end_marker:
                content = content[0:no]
                found_entry = True
                break
        content = '\n'.join(content).strip()

        command = command.lower()
        if command in ['info', 'help']:
            response = mail_info(recipient)
        elif command == 'list':
            entries = list()
            for i, entry in enumerate(self._entries):
                entries.append((i, entry.shortlog))

            response = mail_list(recipient, entries)
        elif command == 'new':
            if argument:
                date = parse_ymd(split_subject[1])
                if not date:
                    return error_respond('Invalid date format: %s' % split_subject[1])
            else:
                date = datetime.datetime.today()

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
                response = mail_success(recipient, str(new))
                update_repo = True
            else:
                response = mail_new(recipient, str(new))
        else:
            return error_respond('Unknown command: %s' % command)

        return update_repo, respond_email(address_from, mail, 'OK: %s' % subject, response)
