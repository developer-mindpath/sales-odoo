# -*- coding: utf-8 -*-
from odoo import fields, models


class ResConfigSettings(models.TransientModel):
    _inherit = 'res.config.settings'

    email_camp_imap_server = fields.Char(
        string='Email Camp IMAP server',
        config_parameter='email_camp.imap_server',
        default='imap.gmail.com',
        help='Used to pull replies (same login as your first outgoing SMTP server).',
    )
    email_camp_base_url = fields.Char(
        string='Email Camp public base URL',
        config_parameter='email_camp.base_url',
        help='Optional. Defaults to web.base.url. Must be reachable by recipients for open tracking.',
    )
