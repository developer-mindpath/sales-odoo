# -*- coding: utf-8 -*-
import base64
import csv
import io

from odoo import fields, models, _
from odoo.exceptions import UserError


class EmailCampContactImportWizard(models.TransientModel):
    _name = 'email_camp.contact.import.wizard'
    _description = 'Import Email Camp contacts from CSV'

    data_file = fields.Binary(string='CSV file', required=True)
    filename = fields.Char(string='Filename')

    def action_import(self):
        self.ensure_one()
        if not self.data_file:
            raise UserError(_('Choose a CSV file.'))
        raw = base64.b64decode(self.data_file)
        try:
            text = raw.decode('utf-8-sig')
        except UnicodeDecodeError:
            text = raw.decode('latin-1')
        reader = csv.DictReader(io.StringIO(text))
        reader.fieldnames = [h.strip().lower() for h in (reader.fieldnames or [])]
        Contact = self.env['email_camp.contact'].sudo()
        errors = []
        to_create = []
        for i, row in enumerate(reader, start=2):
            email = (row.get('email') or '').strip()
            firstname = (row.get('firstname') or row.get('first_name') or '').strip()
            if not email or not firstname:
                errors.append(_('Row %s: missing email or firstname.') % i)
                continue
            to_create.append({
                'email': email.lower(),
                'firstname': firstname,
                'lastname': (row.get('lastname') or row.get('last_name') or '').strip() or False,
                'country': (row.get('country') or '').strip() or False,
                'address': (row.get('address') or '').strip() or False,
                'phone': (row.get('phone') or '').strip() or False,
            })
        if not to_create:
            raise UserError(_('No valid rows. %s') % ('; '.join(errors[:5]) or ''))
        try:
            Contact.create(to_create)
        except Exception as exc:
            raise UserError(_('Import failed (duplicate email?). %s') % exc) from exc
        return {'type': 'ir.actions.act_window_close'}
