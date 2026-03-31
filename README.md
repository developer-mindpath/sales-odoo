# sales-odoo

## Environment setup

1. Create your local env file:

```bash
cp .env.example .env
```

2. Update `.env` values for your machine (DB credentials, addons path, log path).

3.0 Install depepndencies.
./venv/bin/pip install -r odoo18/requirements.txt
3.1 cmd to run :./odoo18/odoo-bin --config ./odoo.conf
4. Default URL: http://127.0.0.1:8069/
## Notes

- `.env` is gitignored to avoid committing secrets.
- `EMAIL_CAMP_IMAP_SERVER` and `EMAIL_CAMP_BASE_URL` are operational references here; set them in Odoo system parameters for runtime behavior:
  - `email_camp.imap_server`
  - `email_camp.base_url`

