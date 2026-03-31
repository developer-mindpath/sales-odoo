# -*- coding: utf-8 -*-
import base64
import email
import imaplib
import logging
import re

# Single {word} placeholders in campaign body (avoids str.format() failing on unknown keys).
_PLACEHOLDER_RE = re.compile(r'\{([a-zA-Z_][a-zA-Z0-9_]*)\}')
from email.utils import make_msgid, parseaddr
from urllib.parse import unquote, quote

from odoo import api, fields, models, _
from odoo.exceptions import UserError
from odoo.addons.base.models.ir_mail_server import MailDeliveryException

_logger = logging.getLogger(__name__)


def _ids_from_references(references):
    return [m.strip('<>') for m in re.findall(r'<[^>]+>', references or '')]


def _mask_email(email_addr):
    email_addr = (email_addr or '').strip()
    if not email_addr or '@' not in email_addr:
        return email_addr or '<empty>'
    local, domain = email_addr.split('@', 1)
    if len(local) <= 2:
        masked_local = local[0] + '*' if local else '*'
    else:
        masked_local = local[:2] + '*' * max(len(local) - 2, 1)
    return '%s@%s' % (masked_local, domain)


def _imap_fetch_replies(imap_server, email_addr, password, known_message_ids):
    """Return list of dicts like the standalone email_camp FastAPI service."""
    results = []
    stats = {
        'unseen_count': 0,
        'fetched_count': 0,
        'matched_count': 0,
        'skipped_no_reference': 0,
        'fetch_errors': 0,
        'parse_errors': 0,
        'mark_seen_errors': 0,
    }
    masked_email = _mask_email(email_addr)
    _logger.info('Email Camp IMAP: connecting to server=%s mailbox=%s', imap_server, masked_email)
    mail = imaplib.IMAP4_SSL(imap_server)
    try:
        _logger.info('Email Camp IMAP: logging in mailbox=%s', masked_email)
        mail.login(email_addr, password)
        _logger.info('Email Camp IMAP: login successful mailbox=%s', masked_email)
        status, _ = mail.select('inbox')
        if status != 'OK':
            _logger.warning('Email Camp IMAP: could not select inbox on %s for mailbox=%s', imap_server, masked_email)
            return results, stats
        _logger.info('Email Camp IMAP: inbox selected on server=%s mailbox=%s', imap_server, masked_email)
        status, data = mail.search(None, 'UNSEEN')
        if status != 'OK':
            _logger.warning('Email Camp IMAP: search for UNSEEN failed on %s for mailbox=%s', imap_server, masked_email)
            return results, stats
        if not data or not data[0]:
            _logger.info('Email Camp IMAP: no unread messages found on server=%s mailbox=%s', imap_server, masked_email)
            return results, stats
        unseen_nums = data[0].split()
        stats['unseen_count'] = len(unseen_nums)
        _logger.info(
            'Email Camp IMAP: found %s unread message(s) on server=%s mailbox=%s',
            stats['unseen_count'], imap_server, masked_email
        )
        for num in unseen_nums:
            try:
                status, raw_data = mail.fetch(num, '(RFC822)')
            except imaplib.IMAP4.abort as exc:
                stats['fetch_errors'] += 1
                _logger.warning('Email Camp IMAP: fetch failed for message %s: %s', num.decode(errors='ignore'), exc)
                continue
            except Exception as exc:
                stats['fetch_errors'] += 1
                _logger.warning('Email Camp IMAP: unexpected fetch error for message %s: %s', num.decode(errors='ignore'), exc)
                continue
            if status != 'OK' or not raw_data or not raw_data[0]:
                stats['fetch_errors'] += 1
                _logger.warning('Email Camp IMAP: empty/invalid fetch response for message %s', num.decode(errors='ignore'))
                continue
            stats['fetched_count'] += 1
            try:
                msg = email.message_from_bytes(raw_data[0][1])
            except Exception as exc:
                stats['parse_errors'] += 1
                _logger.warning('Email Camp IMAP: could not parse message %s: %s', num.decode(errors='ignore'), exc)
                continue
            in_reply_to = (msg.get('In-Reply-To') or '').strip()
            references = msg.get('References', '')
            matched_id = None
            if in_reply_to:
                bare = in_reply_to.strip('<>')
                if bare in known_message_ids:
                    matched_id = bare
            if not matched_id and references:
                for ref_id in _ids_from_references(references):
                    if ref_id in known_message_ids:
                        matched_id = ref_id
                        break
            if not matched_id:
                stats['skipped_no_reference'] += 1
                _logger.info(
                    'Email Camp IMAP: skipping unread message %s from=%s subject=%s because no matching Message-ID was found',
                    num.decode(errors='ignore'),
                    _mask_email(parseaddr(msg.get('From', ''))[1]),
                    msg.get('Subject', ''),
                )
                continue
            body = ''
            if msg.is_multipart():
                for part in msg.walk():
                    if part.get_content_type() == 'text/plain':
                        payload = part.get_payload(decode=True)
                        if payload:
                            body = payload.decode(errors='ignore')
                        break
            else:
                payload = msg.get_payload(decode=True)
                if payload:
                    body = payload.decode(errors='ignore')
            reply_mid = (msg.get('Message-ID') or '').strip('<>') or 'reply-imap-%s' % num.decode()
            from_email = parseaddr(msg.get('From', ''))[1]
            stats['matched_count'] += 1
            _logger.info(
                'Email Camp IMAP: matched unread message %s from=%s subject=%s original_message_id=%s reply_message_id=%s',
                num.decode(errors='ignore'),
                _mask_email(from_email),
                msg.get('Subject', ''),
                matched_id,
                reply_mid,
            )
            results.append({
                'original_message_id': matched_id,
                'reply_message_id': reply_mid,
                'from_email': from_email,
                'subject': msg.get('Subject', ''),
                'body': body[:5000],
            })
            try:
                mail.store(num, '+FLAGS', '\\Seen')
            except Exception as exc:
                stats['mark_seen_errors'] += 1
                _logger.warning('Email Camp IMAP: could not mark message %s as seen: %s', num.decode(errors='ignore'), exc)
    finally:
        try:
            mail.close()
            mail.logout()
        except Exception:
            pass
        _logger.info(
            'Email Camp IMAP: finished mailbox=%s unseen=%s fetched=%s matched=%s skipped_no_reference=%s fetch_errors=%s parse_errors=%s mark_seen_errors=%s',
            masked_email,
            stats['unseen_count'],
            stats['fetched_count'],
            stats['matched_count'],
            stats['skipped_no_reference'],
            stats['fetch_errors'],
            stats['parse_errors'],
            stats['mark_seen_errors'],
        )
    return results, stats


class EmailCampCampaign(models.Model):
    _name = 'email_camp.campaign'
    _description = 'Email Camp Campaign'
    _order = 'create_date desc'

    name = fields.Char(string='Subject / Name', required=True)
    body = fields.Html(string='Body', sanitize=False)
    status = fields.Selection(
        selection=[('draft', 'Draft'), ('active', 'Active')],
        default='draft',
        required=True,
    )
    contact_ids = fields.Many2many(
        'email_camp.contact',
        'email_camp_campaign_contact_rel',
        'campaign_id', 'contact_id',
        string='Contacts',
    )
    attachment_ids = fields.Many2many(
        'ir.attachment',
        'email_camp_campaign_ir_attachment_rel',
        'campaign_id', 'attachment_id',
        string='Attachments',
    )
    history_ids = fields.One2many('email_camp.history', 'campaign_id', string='History')
    total_sent = fields.Integer(string='Total Sent', compute='_compute_analytics_metrics', store=True)
    total_failed = fields.Integer(string='Total Failed', compute='_compute_analytics_metrics', store=True)
    total_replies = fields.Integer(string='Total Replies', compute='_compute_analytics_metrics', store=True)
    total_seen = fields.Integer(string='Total Seen', compute='_compute_analytics_metrics', store=True)
    total_contacts = fields.Integer(string='Total Contacts', compute='_compute_analytics_metrics', store=True)
    total_events = fields.Integer(string='History Events', compute='_compute_analytics_metrics', store=True)
    open_rate = fields.Float(string='Open Rate (%)', compute='_compute_analytics_metrics', digits=(16, 2), store=True)
    reply_rate = fields.Float(string='Reply Rate (%)', compute='_compute_analytics_metrics', digits=(16, 2), store=True)
    failure_rate = fields.Float(string='Failure Rate (%)', compute='_compute_analytics_metrics', digits=(16, 2), store=True)
    create_date = fields.Datetime(string='Created on', readonly=True)
    write_date = fields.Datetime(string='Last Updated on', readonly=True)

    @api.depends('contact_ids', 'history_ids.status', 'history_ids.direction')
    def _compute_analytics_metrics(self):
        counts_map = {campaign_id: {} for campaign_id in self.ids}
        if self.ids:
            groups = self.env['email_camp.history'].sudo().read_group(
                [('campaign_id', 'in', self.ids)],
                ['campaign_id', 'status'],
                ['campaign_id', 'status'],
                lazy=False,
            )
            for row in groups:
                campaign_id = row['campaign_id'][0]
                status = row['status']
                counts_map.setdefault(campaign_id, {})[status] = row['__count']

        for campaign in self:
            counts = counts_map.get(campaign.id, {})
            campaign.total_sent = counts.get('sent', 0)
            campaign.total_failed = counts.get('failed', 0)
            campaign.total_replies = counts.get('replied', 0)
            campaign.total_seen = counts.get('opened', 0)
            campaign.total_events = sum(counts.values())
            campaign.total_contacts = len(campaign.contact_ids)
            sent_base = campaign.total_sent or 0
            total_attempted = campaign.total_sent + campaign.total_failed
            campaign.open_rate = (campaign.total_seen * 100.0 / sent_base) if sent_base else 0.0
            campaign.reply_rate = (campaign.total_replies * 100.0 / sent_base) if sent_base else 0.0
            campaign.failure_rate = (campaign.total_failed * 100.0 / total_attempted) if total_attempted else 0.0

    def _history_action(self, extra_domain=None, title=None, default_view_mode='tree,graph,pivot'):
        self.ensure_one()
        domain = [('campaign_id', '=', self.id)]
        if extra_domain:
            domain.extend(extra_domain)
        return {
            'type': 'ir.actions.act_window',
            'name': title or _('Campaign History'),
            'res_model': 'email_camp.history',
            'view_mode': default_view_mode,
            'domain': domain,
            'context': {
                'search_default_group_by_status': 1,
                'default_campaign_id': self.id,
            },
        }

    def action_view_history(self):
        self.ensure_one()
        return self._history_action(title=_('Campaign History'))

    def action_view_sent_history(self):
        self.ensure_one()
        return self._history_action([('status', '=', 'sent')], _('Sent Emails'))

    def action_view_failed_history(self):
        self.ensure_one()
        return self._history_action([('status', '=', 'failed')], _('Failed Emails'))

    def action_view_reply_history(self):
        self.ensure_one()
        return self._history_action([('status', '=', 'replied')], _('Replies'))

    def action_view_seen_history(self):
        self.ensure_one()
        return self._history_action([('status', '=', 'opened')], _('Opened Emails'))

    def action_view_analytics_breakdown(self):
        self.ensure_one()
        return self._history_action(title=_('Analytics Breakdown'), default_view_mode='graph,pivot,tree')

    def _email_camp_base_url(self):
        icp = self.env['ir.config_parameter'].sudo()
        custom = icp.get_param('email_camp.base_url') or ''
        if custom.strip():
            return custom.strip().rstrip('/')
        return (icp.get_param('web.base.url') or '').rstrip('/')

    @staticmethod
    def _build_html_body(body_template, contact, tracking_url):
        template = body_template or ''
        fn = (contact.firstname or '').strip()
        ln = (contact.lastname or '').strip()
        mapping = {
            'firstname': fn,
            'lastname': ln,
            'first_name': fn,
            'last_name': ln,
            'email': contact.email or '',
            'country': contact.country or '',
            'address': contact.address or '',
            'phone': contact.phone or '',
        }

        def _repl(match):
            key = match.group(1)
            if key not in mapping:
                return match.group(0)
            return str(mapping[key])

        html = _PLACEHOLDER_RE.sub(_repl, template)
        if not (html or '').strip().startswith('<'):
            html = '<p>%s</p>' % html
        pixel = '<img src="%s" width="1" height="1" style="display:none;" alt="">' % tracking_url
        return '<html><body>%s%s</body></html>' % (html, pixel)

    def _prepare_attachments_tuples(self):
        self.ensure_one()
        out = []
        for att in self.attachment_ids:
            if not att.datas:
                continue
            content = base64.b64decode(att.datas)
            mime = att.mimetype or 'application/octet-stream'
            out.append((att.name or 'file', content, mime))
        return out

    def _get_default_mail_server(self):
        server = self.env['ir.mail_server'].sudo().search([('active', '=', True)], order='sequence', limit=1)
        if not server:
            raise UserError(_('Configure an outgoing mail server under Settings → Technical → Outgoing Mail Servers.'))
        return server

    @staticmethod
    def _resolve_email_from(mail_server):
        from_filter_parts = [part.strip() for part in (mail_server.from_filter or '').split(',') if part.strip()]
        explicit_from = next((part for part in from_filter_parts if '@' in part), False)
        if explicit_from:
            return explicit_from
        if mail_server.smtp_user and '@' in mail_server.smtp_user:
            return mail_server.smtp_user
        try:
            return mail_server._get_test_email_from()
        except UserError:
            raise UserError(
                _('Set a valid sender email on the outgoing mail server. Use FROM Filtering or a username that is a full email address.')
            ) from None

    def write(self, vals):
        if 'attachment_ids' in vals:
            for rec in self:
                if rec.status != 'draft':
                    raise UserError(_('Attachments can only be changed while the campaign is in draft state.'))
        return super().write(vals)

    def action_run_campaign(self):
        History = self.env['email_camp.history'].sudo()
        for campaign in self:
            if campaign.status != 'draft':
                raise UserError(_('Only draft campaigns can be sent. Current status: %s') % campaign.status)
            if not campaign.contact_ids:
                raise UserError(_('Add at least one contact before running the campaign.'))
            mail_server = campaign._get_default_mail_server()
            email_from = campaign._resolve_email_from(mail_server)
            attachments = campaign._prepare_attachments_tuples()
            base_url = campaign._email_camp_base_url()
            if not base_url:
                raise UserError(_('Set the system base URL (web.base.url) or Email Camp public URL in settings.'))

            for contact in campaign.contact_ids:
                raw_mid = make_msgid(domain='emailcamp.local')
                bare_mid = raw_mid.strip('<>')
                tracking_url = '%s/email_camp/track/%s' % (base_url, quote(bare_mid, safe=''))
                body_html = campaign._build_html_body(campaign.body or '', contact, tracking_url)
                try:
                    msg = mail_server.build_email(
                        email_from,
                        contact.email,
                        campaign.name,
                        body_html,
                        subtype='html',
                        message_id=raw_mid,
                        attachments=attachments or None,
                    )
                    mail_server.send_email(msg, mail_server_id=mail_server.id)
                    History.create({
                        'message_id': bare_mid,
                        'campaign_id': campaign.id,
                        'contact_id': contact.id,
                        'contact_email': contact.email,
                        'status': 'sent',
                        'direction': 'outgoing',
                    })
                except MailDeliveryException as err:
                    _logger.warning('Email Camp send failed for %s: %s', contact.email, err)
                    History.create({
                        'message_id': bare_mid,
                        'campaign_id': campaign.id,
                        'contact_id': contact.id,
                        'contact_email': contact.email,
                        'status': 'failed',
                        'direction': 'outgoing',
                    })
                except Exception as err:
                    _logger.exception('Email Camp unexpected send error')
                    History.create({
                        'message_id': bare_mid,
                        'campaign_id': campaign.id,
                        'contact_id': contact.id,
                        'contact_email': contact.email,
                        'status': 'failed',
                        'direction': 'outgoing',
                    })
            campaign.status = 'active'
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': _('Campaign'),
                'message': _('Emails were sent. The campaign is now active. Check Email history for per-recipient status.'),
                'type': 'success',
                'sticky': False,
            },
        }

    @api.model
    def action_sync_inbox_replies(self):
        res = self.with_context(email_camp_sync_raise=True)._sync_inbox_replies_impl()
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': _('Reply sync'),
                'message': res.get('message', ''),
                'type': 'success',
                'sticky': False,
            },
        }

    @api.model
    def cron_sync_inbox_replies(self):
        self._sync_inbox_replies_impl()
        return True

    @api.model
    def _sync_inbox_replies_impl(self):
        _logger.info('Email Camp sync: starting inbox reply sync')
        mail_server = self.env['ir.mail_server'].sudo().search([('active', '=', True)], order='sequence', limit=1)
        if not mail_server or not mail_server.smtp_user or not mail_server.smtp_pass:
            _logger.info('Email Camp IMAP sync skipped: missing mail server or credentials.')
            return {'synced': 0, 'message': _('No mail server credentials for IMAP.')}
        History = self.env['email_camp.history'].sudo()
        Lead = self.env['crm.lead']
        known_ids = History.get_sent_message_id_set()
        _logger.info(
            'Email Camp sync: using outgoing server id=%s name=%s smtp_user=%s known_sent_message_ids=%s',
            mail_server.id,
            mail_server.name,
            _mask_email(mail_server.smtp_user),
            len(known_ids),
        )
        if not known_ids:
            _logger.info('Email Camp sync: stopping because there are no sent message IDs to match')
            return {'synced': 0, 'message': _('No sent messages to match replies against.')}
        icp = self.env['ir.config_parameter'].sudo()
        imap_server = icp.get_param('email_camp.imap_server') or 'imap.gmail.com'
        email_addr = mail_server.smtp_user
        password = mail_server.smtp_pass
        _logger.info(
            'Email Camp sync: connecting to IMAP server=%s with mailbox=%s',
            imap_server,
            _mask_email(email_addr),
        )
        try:
            replies, imap_stats = _imap_fetch_replies(imap_server, email_addr, password, known_ids)
        except Exception as exc:
            _logger.exception('Email Camp IMAP sync failed')
            if self.env.context.get('email_camp_sync_raise'):
                raise UserError(_('IMAP connection failed: %s') % exc) from exc
            return {'synced': 0, 'message': _('IMAP error (see server log): %s') % exc}
        _logger.info(
            'Email Camp sync: IMAP fetch completed replies=%s unseen=%s fetched=%s matched=%s skipped_no_reference=%s',
            len(replies),
            imap_stats.get('unseen_count', 0),
            imap_stats.get('fetched_count', 0),
            imap_stats.get('matched_count', 0),
            imap_stats.get('skipped_no_reference', 0),
        )
        synced = 0
        matched_originals = 0
        missing_originals = 0
        lead_upserts = 0
        incoming_duplicates = 0
        for reply in replies:
            _logger.info(
                'Email Camp sync: processing reply original_message_id=%s reply_message_id=%s from=%s subject=%s',
                reply['original_message_id'],
                reply['reply_message_id'],
                _mask_email(reply.get('from_email')),
                reply.get('subject', ''),
            )
            original = History.search([('message_id', '=', reply['original_message_id'])], limit=1)
            if not original:
                missing_originals += 1
                _logger.warning(
                    'Email Camp sync: no history row found for original_message_id=%s reply_message_id=%s',
                    reply['original_message_id'],
                    reply['reply_message_id'],
                )
                continue
            matched_originals += 1
            original._mark_as_replied()
            saved = History.save_incoming_reply(reply['reply_message_id'], original)
            if original.campaign_id and original.contact_id:
                Lead.create_from_email_camp_reply(
                    original.campaign_id,
                    original.contact_id,
                    original.message_id,
                    reply['reply_message_id'],
                    reply.get('subject'),
                    reply.get('body'),
                )
                lead_upserts += 1
                _logger.info(
                    'Email Camp sync: lead updated/created for campaign_id=%s contact_id=%s reply_message_id=%s',
                    original.campaign_id.id,
                    original.contact_id.id,
                    reply['reply_message_id'],
                )
            if saved:
                synced += 1
                _logger.info(
                    'Email Camp sync: saved incoming reply history id=%s parent_message_id=%s',
                    saved.id,
                    original.message_id,
                )
            else:
                incoming_duplicates += 1
                _logger.info(
                    'Email Camp sync: incoming reply already existed reply_message_id=%s',
                    reply['reply_message_id'],
                )
        _logger.info(
            'Email Camp sync: finished replies=%s matched_originals=%s missing_originals=%s saved_incoming=%s duplicate_incoming=%s lead_upserts=%s',
            len(replies),
            matched_originals,
            missing_originals,
            synced,
            incoming_duplicates,
            lead_upserts,
        )
        return {
            'synced': synced,
            'message': _('Processed %(count)s reply email(s), saved %(synced)s new incoming row(s).')
            % {'count': len(replies), 'synced': synced},
        }
