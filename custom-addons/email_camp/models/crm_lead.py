# -*- coding: utf-8 -*-
from odoo import api, fields, models, _


class CrmLead(models.Model):
    _inherit = 'crm.lead'

    email_camp_campaign_id = fields.Many2one('email_camp.campaign', string='Email Camp Campaign', index=True)
    email_camp_contact_id = fields.Many2one('email_camp.contact', string='Email Camp Contact', index=True)
    email_camp_original_message_id = fields.Char(string='Email Camp Original Message-ID')
    email_camp_reply_message_id = fields.Char(string='Email Camp Reply Message-ID')
    email_camp_reply_subject = fields.Char(string='Reply Subject')
    email_camp_reply_body = fields.Text(string='Reply Message')

    @api.model
    def create_from_email_camp_reply(self, campaign, contact, original_message_id, reply_message_id, reply_subject=False, reply_body=False):
        domain = [
            ('email_camp_campaign_id', '=', campaign.id),
            ('email_camp_contact_id', '=', contact.id),
        ]
        existing = self.sudo().search(domain, limit=1)
        if existing:
            vals = {}
            if reply_message_id and not existing.email_camp_reply_message_id:
                vals['email_camp_reply_message_id'] = reply_message_id
            if reply_subject:
                vals['email_camp_reply_subject'] = reply_subject
            if reply_body:
                vals['email_camp_reply_body'] = reply_body
            if vals:
                existing.write(vals)
            return existing

        contact_name = ' '.join(part for part in [contact.firstname or '', contact.lastname or ''] if part).strip()
        lead_name = _('Reply from %s') % (contact_name or contact.email)
        return self.sudo().create({
            'name': lead_name,
            'type': 'lead',
            'user_id': False,
            'contact_name': contact_name or False,
            'email_from': contact.email,
            'phone': contact.phone or False,
            'description': _('Created from Email Camp reply for campaign "%s".') % campaign.name,
            'email_camp_campaign_id': campaign.id,
            'email_camp_contact_id': contact.id,
            'email_camp_original_message_id': original_message_id,
            'email_camp_reply_message_id': reply_message_id,
            'email_camp_reply_subject': reply_subject or False,
            'email_camp_reply_body': reply_body or False,
        })
