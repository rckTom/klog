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

from os import remove, makedirs

import configparser
import datetime
import email
import git
import re

from email.mime.text import MIMEText
from email.header import decode_header

from glob import glob
from jinja2 import Template
from os.path import join, normpath, expanduser, isdir

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
  delete no
  info / help
  list
  modify no
  new [date in Y-m-d format]

delete:
  Will remove the kitchen log entry that is provided as an argument.

info:
  shows you this page. The ids can be used for other commands.

list:
  return a list of all entries

modify:
  modifies the specified kitchen log entry. Returns the entry if no content is
  provided.

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

mail_delete_ok_template = \
"""
entry succesfully deleted. Find the content of the old entry below.
"""


def mail_delete_ok(recipient, old):
    return mail_greeting % recipient + mail_delete_ok_template + mail_footer + '\n--\n' + str(old)


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


class Config:
    def __init__(self, filename, needs_email):
        config = configparser.ConfigParser()
        config.read(filename)
        try:
            self.d_cache = config.get('klog', 'cache')
            self.kitchenlog_uri = config.get('klog', 'kitchenlog')
            self.update_trigger = config.get('klog', 'update_trigger')

            if needs_email:
                self.smtp_server = config.get('klog', 'smtp_server')
                self.email_name = config.get('klog', 'email_name')
        except configparser.NoOptionError as e:
            print('Missing %s in your config' % e.message)
            quit(-1)

        self.d_cache = expanduser(self.d_cache)
        self.d_repo = join(self.d_cache, 'kitchenlog')

        makedirs(self.d_cache, exist_ok=True)

        # Check if local repo clone exists
        if not isdir(self.d_repo):
            print('Cloning into %s...' % self.kitchenlog_uri)
            self.repo = git.Repo.clone_from(self.kitchenlog_uri, self.d_repo)
        else:
            self.repo = git.Repo(self.d_repo)


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

    def get_no(self, no):
        if no < len(self._entries):
            return self._entries[no]
        return None

    def new_entry(self, date):
        entry = LogEntry.new(self._directory, date)
        self._entries.append(entry)
        return entry

    def years_dict(self):
        dates = {entry.date_raw for entry in self._entries}
        years = dict()
        for year in {x.year for x in dates}:
            years[year] = {
                x.month:
                    [entry for entry in self._entries
                     if entry.date_raw.year == year and entry.date_raw.month == x.month]
                for x in dates
                if x.year == year}
        return years

    def export_dokuwiki(self, target_path):
        # delete old data
        target_entries = glob(join(target_path, 'entry', KitchenLog.FILES_GLOB))
        target_entries += glob(join(target_path, '*.txt'))
        for target in target_entries:
            remove(target)

        for entry in self._entries:
            entry.to_dokuwiki(target_path)

        years = self.years_dict()

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

        def replace_entry(entry, content, attachments):
            try:
                entry.reload(content, True)
                for attachment in attachments:
                    attachment_raw = attachment.get_payload(decode=True)
                    filename = decode_multiple(attachment.get_filename())
                    entry.attach_media(filename, attachment_raw)
            except ValueError as e:
                return False, error_respond('Parser error: %s\n\nOriginal mail below\n--\n\n%s' % (str(e), content))
            return True, mail_success(recipient, str(entry))

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
        elif command == 'delete' or command == 'modify':
            if False in [x.isnumeric() for x in argument]:
                error_respond('Not an integer: %s' % argument)

            no = int(argument)
            if no >= len(self._entries):
                error_respond('Index out of bound: %d' % no)

            entry = self._entries[no]

            if command == 'delete':
                entry.remove()
                response = mail_delete_ok(recipient, str(entry))
            elif command == 'modify':
                if found_entry:
                    update_repo, response = replace_entry(entry, content, attachments)
                else:
                    response = str(entry) + '\n' + mail_end_marker
            update_repo = True
        elif command == 'new':
            if argument:
                date = parse_ymd(split_subject[1])
                if not date:
                    return error_respond('Invalid date format: %s' % split_subject[1])
            else:
                date = datetime.datetime.today()

            new = self.new_entry(date)
            if found_entry:
                update_repo, response = replace_entry(new, content, attachments)
            else:
                response = mail_new(recipient, str(new))
        else:
            return error_respond('Unknown command: %s' % command)

        return update_repo, respond_email(address_from, mail, 'OK: %s' % subject, response)
