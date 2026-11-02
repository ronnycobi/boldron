"""Transactional email legal footer (spec §59) and the dynamic footer links (§58)."""
from django.test import TestCase, override_settings

from apps.notifications.email import legal_footer_text


class EmailFooterTests(TestCase):
    def test_footer_uses_the_configured_app_identity_only(self):
        # Uses the configured app name (default "Application") — never fabricated
        # company details — and marks itself a service message.
        footer = legal_footer_text()
        self.assertIn("service message", footer)
        self.assertNotIn("help@", footer)   # no invented support address

    @override_settings(APP_COMPANY_NAME="Acme Inc", APP_SUPPORT_EMAIL="help@acme.test")
    def test_footer_uses_configured_identity(self):
        footer = legal_footer_text()
        self.assertIn("Acme Inc", footer)
        self.assertIn("help@acme.test", footer)
        self.assertIn("service message", footer)
