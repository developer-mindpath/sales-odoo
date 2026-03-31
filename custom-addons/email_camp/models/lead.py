# -*- coding: utf-8 -*-
from odoo import api, fields, models, _


class EmailCampLead(models.Model):
    _name = 'email_camp.lead'
    _description = 'Email Camp Lead'
    _order = 'create_date desc'

    campaign_id = fields.Many2one('email_camp.campaign', string='Campaign', ondelete='set null', index=True)
    contact_id = fields.Many2one('email_camp.contact', string='Contact', ondelete='set null', index=True)
    contact_email = fields.Char(required=True)
    original_message_id = fields.Char(string='Original Message-ID')
    reply_message_id = fields.Char(string='Reply Message-ID')
    status = fields.Selection(
        selection=[
            ('new', 'New'),
            ('contacted', 'Contacted'),
            ('qualified', 'Qualified'),
            ('converted', 'Converted'),
            ('closed', 'Closed'),
        ],
        default='new',
        required=True,
    )
    create_date = fields.Datetime(string='Created on', readonly=True)
    write_date = fields.Datetime(string='Last Updated on', readonly=True)

    _sql_constraints = [
        (
            'email_camp_lead_campaign_contact_uniq',
            'unique(campaign_id, contact_id)',
            _('There is already a lead for this campaign and contact.'),
        ),
    ]

    @api.model
    def create_if_not_exists(self, campaign_id, contact_id, contact_email, original_message_id, reply_message_id):
        domain = [('campaign_id', '=', campaign_id), ('contact_id', '=', contact_id)]
        if self.sudo().search_count(domain):
            return self.env['email_camp.lead']
        return self.sudo().create({
            'campaign_id': campaign_id,
            'contact_id': contact_id,
            'contact_email': contact_email,
            'original_message_id': original_message_id,
            'reply_message_id': reply_message_id,
            'status': 'new',
        })
