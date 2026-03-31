# -*- coding: utf-8 -*-
from odoo import api, fields, models


class EmailCampSyncInboxRepliesWizard(models.TransientModel):
    _name = 'email_camp.sync.inbox.replies.wizard'
    _description = 'Sync Email Camp inbox replies'

    synced_count = fields.Integer(string='Synced replies', readonly=True)
    result_message = fields.Text(string='Last result', readonly=True)

    def _run_sync(self):
        self.ensure_one()
        res = self.env['email_camp.campaign'].with_context(email_camp_sync_raise=True)._sync_inbox_replies_impl()
        self.write({
            'synced_count': res.get('synced', 0),
            'result_message': res.get('message', ''),
        })
        return res

    @api.model_create_multi
    def create(self, vals_list):
        records = super().create(vals_list)
        for record in records:
            record._run_sync()
        return records

    def action_run_sync(self):
        self.ensure_one()
        res = self._run_sync()
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': 'Reply sync',
                'message': res.get('message', ''),
                'type': 'success',
                'sticky': False,
            },
        }
