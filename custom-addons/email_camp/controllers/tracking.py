# -*- coding: utf-8 -*-
from urllib.parse import unquote

from odoo import http
from odoo.http import request

_PIXEL_GIF = (
    b'\x47\x49\x46\x38\x39\x61\x01\x00\x01\x00\x80\x00\x00'
    b'\xff\xff\xff\x00\x00\x00\x21\xf9\x04\x01\x00\x00\x00'
    b'\x00\x2c\x00\x00\x00\x00\x01\x00\x01\x00\x00\x02\x02'
    b'\x44\x01\x00\x3b'
)


class EmailCampTracking(http.Controller):
    @http.route('/email_camp/track/<path:message_id>', type='http', auth='public', csrf=False)
    def track_open(self, message_id, **kwargs):
        bare = unquote(message_id or '').strip()
        request.env['email_camp.history'].sudo().mark_as_opened(bare)
        headers = [
            ('Content-Type', 'image/gif'),
            ('Cache-Control', 'no-store, no-cache, must-revalidate, proxy-revalidate'),
            ('Pragma', 'no-cache'),
            ('Expires', '0'),
        ]
        return request.make_response(_PIXEL_GIF, headers=headers)
