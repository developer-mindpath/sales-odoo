# -*- coding: utf-8 -*-
{
    'name': 'Email Camp',
    'version': '18.0.1.0.0',
    'category': 'Marketing',
    'summary': 'Email campaigns, contacts, open tracking, and reply-to-lead sync',
    'description': """
Email Camp (Odoo port of email_camp)
====================================
- Contacts and CSV-style fields
- Campaigns with HTML body, placeholders, attachments
- Mass send via configured outgoing mail server (Message-ID for reply matching)
- Public tracking pixel for opens
- IMAP sync: match replies to sent mail and create leads
    """,
    'author': 'Mindpath',
    'license': 'LGPL-3',
    'depends': ['base', 'web', 'mail', 'base_setup', 'crm'],
    'data': [
        'security/email_camp_security.xml',
        'security/ir.model.access.csv',
        'data/ir_cron.xml',
        'data/campaign_server_actions.xml',
        'views/contact_views.xml',
        'views/campaign_views.xml',
        'views/history_views.xml',
        'views/crm_lead_views.xml',
        'views/res_config_settings_views.xml',
        'views/contact_import_wizard_views.xml',
        'views/sync_inbox_replies_wizard_views.xml',
        'views/menus.xml',
    ],
    'installable': True,
    'application': True,
}
