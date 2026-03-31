# -*- coding: utf-8 -*-
from odoo import api, fields, models


class EmailCampHistory(models.Model):
    _name = 'email_camp.history'
    _description = 'Email Camp Message History'
    _order = 'create_date desc'

    message_id = fields.Char(string='Message-ID (bare)', required=True, index=True)
    campaign_id = fields.Many2one('email_camp.campaign', string='Campaign', ondelete='set null', index=True)
    contact_id = fields.Many2one('email_camp.contact', string='Contact', ondelete='set null', index=True)
    contact_email = fields.Char(required=True)
    status = fields.Selection(
        selection=[
            ('queued', 'Queued'),
            ('sent', 'Sent'),
            ('failed', 'Failed'),
            ('opened', 'Opened'),
            ('delivered', 'Delivered'),
            ('replied', 'Replied'),
        ],
        default='queued',
        required=True,
    )
    direction = fields.Selection(
        selection=[('outgoing', 'Outgoing'), ('incoming', 'Incoming')],
        default='outgoing',
        required=True,
    )
    parent_message_id = fields.Char(string='Parent Message-ID', index=True)

    _sql_constraints = [
        ('email_camp_history_message_id_unique', 'unique(message_id)', 'Message-ID must be unique.'),
    ]

    @api.model
    def mark_as_opened(self, bare_message_id):
        """Tracking pixel: record open once for a successful send."""
        if not bare_message_id:
            return False
        bare_message_id = bare_message_id.strip()
        original = self.sudo().search([('message_id', '=', bare_message_id)], limit=1)
        if not original or original.status not in ('sent', 'delivered'):
            return False
        open_event_id = 'open-%s' % bare_message_id
        if self.sudo().search_count([('message_id', '=', open_event_id)]):
            return False
        self.sudo().create({
            'message_id': open_event_id,
            'campaign_id': original.campaign_id.id,
            'contact_id': original.contact_id.id,
            'contact_email': original.contact_email,
            'status': 'opened',
            'direction': 'outgoing',
            'parent_message_id': bare_message_id,
        })
        return True

    @api.model
    def get_sent_message_id_set(self):
        recs = self.sudo().search([('direction', '=', 'outgoing'), ('status', '=', 'sent')])
        return set(recs.mapped('message_id'))

    def _mark_as_replied(self):
        self.ensure_one()
        replied_event_id = 'replied-%s' % self.message_id
        if self.sudo().search_count([('message_id', '=', replied_event_id)]):
            return
        self.sudo().create({
            'message_id': replied_event_id,
            'campaign_id': self.campaign_id.id,
            'contact_id': self.contact_id.id,
            'contact_email': self.contact_email,
            'status': 'replied',
            'direction': 'outgoing',
            'parent_message_id': self.message_id,
        })

    @api.model
    def save_incoming_reply(self, reply_message_id, original):
        reply_message_id = (reply_message_id or '').strip()
        if not reply_message_id or self.sudo().search_count([('message_id', '=', reply_message_id)]):
            return self.env['email_camp.history']
        return self.sudo().create({
            'message_id': reply_message_id,
            'campaign_id': original.campaign_id.id,
            'contact_id': original.contact_id.id,
            'contact_email': original.contact_email,
            'status': 'delivered',
            'direction': 'incoming',
            'parent_message_id': original.message_id,
        })
