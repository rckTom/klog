#!/usr/bin/env python3

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

import os

from datetime import datetime

from flask_wtf import FlaskForm
from wtforms import StringField
from wtforms.validators import DataRequired

from pyklog.LogEntry import LogEntry
from pyklog.KitchenLog import Config, KitchenLog
from locale import setlocale, LC_ALL

from flask import Flask, render_template, request

setlocale(LC_ALL, 'de_DE.UTF-8')

f_config = os.path.join(os.environ['HOME'], '.config', 'klogrc')
cfg = Config(f_config, needs_email=False, sync=True)

klog = KitchenLog(cfg.repo)
app = Flask('klog')


class EntryForm(FlaskForm):
    begin = StringField('begin', validators=[DataRequired()])
    end = StringField('end')
    topic = StringField('topic', validators=[DataRequired()])
    appendix = StringField('appendix')
    content = StringField('content', validators=[DataRequired()])

    def __init__(self, *args, **kwargs):
        FlaskForm.__init__(self, *args, **kwargs)

    def validate(self):
        if not FlaskForm.validate(self):
            return False

        if not self.end.data or self.end.data == self.begin.data:
            self.end.data = 'None'

        return True

    def convert(self):
        entry_raw = \
"""BEGIN: %s
END: %s
TOPIC: %s
APPENDIX: %s

%s
""" % (self.begin.data,
       self.end.data,
       self.topic.data,
       self.appendix.data,
       self.content.data)
        return LogEntry.sanitise_entry(entry_raw)


@app.route('/')
def home():
    return render_template('index.html')


@app.route('/modify', methods=['POST', 'GET'])
def modify():
    id = request.args.get('id')
    info = None

    if id is None:
        return list()

    try:
        id = int(id)
    except ValueError:
        return list()

    entry = klog.get_no(id)
    if not entry:
        return list()

    removals = [x.replace('remove_', '') for x in request.form.keys() if x.startswith('remove_')]
    try:
        removals = [int(x) for x in removals]
        removals = [x for x in removals if x < len(entry.media)]
    except ValueError:
        removals = list()

    entry_form = EntryForm(request.form, csrf_enabled=False)
    if entry_form.validate():
        entry_raw = entry_form.convert()

        if 'remove' in request.form:
            entry.remove()
            klog.commit('Removed %s' % entry.shortlog)
            cfg.update_trigger()
            info = 'Entry successfully removed', 'success'
            return render_template('list.html', info=info, content=klog.years_dict())
        elif entry_raw == str(entry) and len(removals) == 0:
            info = 'Nothing changed', 'warning'
        else:
            try:
                for removal in removals:
                    entry.remove_media(removal)
                entry.reload(entry_raw, True)
                info = 'success', 'success'
                klog.commit('Modified %s ' % entry.shortlog)
                cfg.update_trigger()
            except ValueError as e:
                info = str(e), 'danger'

    return render_template('modify.html', id=id, entry=entry, info=info)


@app.route('/list')
def list():
    return render_template('list.html', content=klog.years_dict())


@app.route('/new', methods=['POST', 'GET'])
def new():
    entry_form = EntryForm(request.form, csrf_enabled=False)
    info = None

    if entry_form.validate():
        entry = klog.new_entry(datetime.today())
        entry_raw = entry_form.convert()
        try:
            entry.reload(entry_raw, True)
            info = 'success', 'success'
            klog.commit('Modified %s ' % entry.shortlog)
            cfg.update_trigger()
            return render_template('list.html', info=info, content=klog.years_dict())
        except ValueError as e:
            info = str(e), 'danger'

    template = LogEntry.new(cfg.d_repo, datetime.today())
    return render_template('new.html', info=info, template=template)


app.run(debug=True, host='0.0.0.0', port=8080)