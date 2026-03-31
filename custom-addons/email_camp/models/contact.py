# -*- coding: utf-8 -*-
from odoo import api, fields, models, _


class EmailCampContact(models.Model):
    _name = 'email_camp.contact'
    _description = 'Email Camp Contact'
    _order = 'email'

    email = fields.Char(required=True, index=True)
    firstname = fields.Char(string='First name', required=True)
    lastname = fields.Char(string='Last name')
    country = fields.Char()
    address = fields.Char()
    phone = fields.Char()
    create_date = fields.Datetime(string='Created on', readonly=True)
    write_date = fields.Datetime(string='Last Updated on', readonly=True)

    _sql_constraints = [
        ('email_camp_contact_email_unique', 'unique(email)', _('A contact with this email already exists.')),
    ]

    def name_get(self):
        res = []
        for rec in self:
            name = (rec.firstname or '') + (' ' + rec.lastname if rec.lastname else '')
            name = (name.strip() or rec.email)
            res.append((rec.id, '%s <%s>' % (name, rec.email)))
        return res

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get('email'):
                vals['email'] = vals['email'].strip().lower()
        return super().create(vals_list)

    def write(self, vals):
        if vals.get('email'):
            vals = dict(vals)
            vals['email'] = vals['email'].strip().lower()
        return super().write(vals)

    @api.model
    def action_open_import_wizard(self):
        return {
            'type': 'ir.actions.act_window',
            'name': _('Import contacts from CSV'),
            'res_model': 'email_camp.contact.import.wizard',
            'view_mode': 'form',
            'target': 'new',
        }
