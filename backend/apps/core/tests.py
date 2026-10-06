import tempfile
from pathlib import Path

from django.test import SimpleTestCase, TestCase
from django.urls import reverse

from config.settings import load_env_file


class LoadEnvFileTests(SimpleTestCase):
    def _write(self, text: str) -> str:
        f = tempfile.NamedTemporaryFile("w", suffix=".env", delete=False)
        f.write(text)
        f.close()
        self.addCleanup(lambda: Path(f.name).unlink(missing_ok=True))
        return f.name

    def test_sets_missing_keys_and_parses_formats(self):
        path = self._write(
            "# a comment\n"
            "\n"
            "ANTHROPIC_API_KEY=sk-ant-123\n"
            "export OPENAI_API_KEY=sk-oai-456\n"
            'GEMINI_API_KEY="quoted-key"\n'
            "MALFORMED_LINE_NO_EQUALS\n"
        )
        env: dict = {}
        count = load_env_file(path, environ=env)
        self.assertEqual(count, 3)
        self.assertEqual(env["ANTHROPIC_API_KEY"], "sk-ant-123")
        self.assertEqual(env["OPENAI_API_KEY"], "sk-oai-456")
        self.assertEqual(env["GEMINI_API_KEY"], "quoted-key")
        self.assertNotIn("MALFORMED_LINE_NO_EQUALS", env)

    def test_real_env_wins_over_file(self):
        path = self._write("ANTHROPIC_API_KEY=from-file\n")
        env = {"ANTHROPIC_API_KEY": "from-shell"}
        load_env_file(path, environ=env)
        self.assertEqual(env["ANTHROPIC_API_KEY"], "from-shell")

    def test_missing_file_is_noop(self):
        self.assertEqual(load_env_file("/no/such/.env", environ={}), 0)


class HealthEndpointTests(TestCase):
    def test_health_returns_ok(self):
        resp = self.client.get(reverse("core:health"))
        self.assertEqual(resp.status_code, 200)
        body = resp.json()
        self.assertEqual(body["service"], "application")  # slug of default APP_NAME
        self.assertEqual(body["status"], "ok")
        # Tech-confidentiality: the probe must not leak the framework or its version.
        self.assertNotIn("django", body)
        self.assertNotIn("version", body)

    def test_health_is_public(self):
        # No authentication set up; the probe must still be reachable.
        resp = self.client.get("/api/v1/health/")
        self.assertEqual(resp.status_code, 200)
