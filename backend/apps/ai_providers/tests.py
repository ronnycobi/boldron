from unittest import mock

from django.contrib.auth import get_user_model
from django.test import SimpleTestCase, TestCase
from django.urls import reverse

from apps.agents.base import AgentContext, AgentResult, BaseAgent
from apps.ai_providers.anthropic_provider import AnthropicProvider
from apps.ai_providers.base import (
    CompletionRequest,
    Message,
    ProviderUnavailable,
)
from apps.ai_providers.registry import complete, get_provider, registry
from apps.ai_providers.stub import StubProvider
from apps.organizations.models import Organization
from apps.orchestrator.service import Orchestrator
from apps.projects.models import Project

User = get_user_model()


class StubProviderTests(SimpleTestCase):
    def test_is_deterministic_and_available(self):
        provider = StubProvider()
        self.assertTrue(provider.is_available())
        req = CompletionRequest(messages=[Message("user", "Hello there")])
        a = provider.complete(req)
        b = provider.complete(req)
        self.assertEqual(a.text, b.text)
        self.assertIn("Hello there", a.text)
        self.assertEqual(a.provider, "stub")
        self.assertGreater(a.usage.total_tokens, 0)


class AnthropicProviderTests(SimpleTestCase):
    @mock.patch.dict("os.environ", {"ANTHROPIC_API_KEY": ""}, clear=False)
    def test_unavailable_without_key(self):
        provider = AnthropicProvider()
        self.assertFalse(provider.is_available())

    @mock.patch.dict("os.environ", {"ANTHROPIC_API_KEY": ""}, clear=False)
    def test_complete_raises_when_unavailable(self):
        provider = AnthropicProvider()
        req = CompletionRequest(messages=[Message("user", "hi")])
        with self.assertRaises(ProviderUnavailable):
            provider.complete(req)

    def test_default_model_is_current(self):
        # Guards against a stale default sneaking in.
        self.assertEqual(AnthropicProvider().default_model(), "claude-opus-5")


class RegistryAndGatewayTests(SimpleTestCase):
    def test_registry_holds_stub_and_anthropic(self):
        self.assertIn("stub", registry)
        self.assertIn("anthropic", registry)

    def test_get_unknown_provider_raises(self):
        with self.assertRaises(ValueError):
            get_provider("ghost")

    def test_gateway_uses_default_provider_and_fills_model(self):
        # Default provider is the stub (settings AI_DEFAULT_PROVIDER).
        req = CompletionRequest(messages=[Message("user", "ping")])
        resp = complete(req)
        self.assertEqual(resp.provider, "stub")
        self.assertEqual(resp.model, "stub-1")  # default model filled in

    def test_gateway_accepts_explicit_provider_instance(self):
        req = CompletionRequest(messages=[Message("user", "ping")])
        resp = complete(req, provider=StubProvider())
        self.assertEqual(resp.provider, "stub")


class ProviderCatalogAPITests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(email="dev@x.com", password="pw12345!")

    def test_requires_authentication(self):
        self.assertEqual(
            self.client.get(reverse("ai_providers:provider-list")).status_code, 403
        )

    def test_lists_providers_without_leaking_keys(self):
        self.client.force_login(self.user)
        resp = self.client.get(reverse("ai_providers:provider-list"))
        self.assertEqual(resp.status_code, 200)
        body = resp.json()
        names = {p["name"] for p in body}
        self.assertEqual(names, {"stub", "anthropic", "openai", "gemini"})
        stub = next(p for p in body if p["name"] == "stub")
        self.assertTrue(stub["available"])
        self.assertTrue(stub["is_default"])
        # No credential material anywhere in the payload.
        self.assertNotIn("key", resp.content.decode().lower())


class ProviderThroughOrchestratorTests(TestCase):
    """End-to-end: orchestrator -> agent -> provider, fully offline via stub."""

    def setUp(self):
        self.org = Organization.objects.create(name="Acme")
        self.project = Project.objects.create(organization=self.org, name="App")

    def test_agent_completes_task_using_the_provider(self):
        class _LLMAgent(BaseAgent):
            key = "backend"  # a real catalog key

            def execute(self, context):
                resp = complete(
                    CompletionRequest(
                        messages=[Message("user", context.input.get("prompt", ""))]
                    )
                )
                return AgentResult.completed(
                    self.key,
                    output={"text": resp.text, "model": resp.model},
                )

        orch = Orchestrator(resolver=lambda key: _LLMAgent())
        task = orch.create_task(
            project=self.project,
            agent_key="backend",
            input={"prompt": "Design a health endpoint"},
        )
        orch.run_task(task)
        task.refresh_from_db()

        self.assertEqual(task.status, "completed")
        self.assertIn("Design a health endpoint", task.output["text"])
        self.assertEqual(task.output["model"], "stub-1")


class OpenAIProviderTests(SimpleTestCase):
    @mock.patch.dict("os.environ", {"OPENAI_API_KEY": ""}, clear=False)
    def test_unavailable_without_key(self):
        from apps.ai_providers.openai_provider import OpenAIProvider
        p = OpenAIProvider()
        self.assertFalse(p.is_available())
        with self.assertRaises(ProviderUnavailable):
            p.complete(CompletionRequest(messages=[Message("user", "hi")]))

    def test_registered_and_in_catalog(self):
        self.assertIn("openai", registry)
        from apps.model_router.catalog import profile_for
        self.assertIsNotNone(profile_for("openai", "gpt-4o"))

    def test_complete_maps_request_to_sdk(self):
        import sys, types
        from apps.ai_providers.openai_provider import OpenAIProvider

        captured = {}

        class _Msg: content = "Generated code."
        class _Choice:
            message = _Msg(); finish_reason = "stop"
        class _Usage:
            prompt_tokens = 12; completion_tokens = 7
        class _Resp:
            choices = [_Choice()]; usage = _Usage(); model = "gpt-4o"
        class _Completions:
            def create(self, **kw):
                captured.update(kw); return _Resp()
        class _Chat:
            completions = _Completions()
        class _Client:
            def __init__(self, api_key=None): self.chat = _Chat()

        fake = types.ModuleType("openai"); fake.OpenAI = _Client
        with mock.patch.dict(sys.modules, {"openai": fake}), \
             mock.patch.dict("os.environ", {"OPENAI_API_KEY": "sk-test"}, clear=False):
            p = OpenAIProvider()
            self.assertTrue(p.is_available())
            r = p.complete(CompletionRequest(messages=[Message("user", "build")],
                                             system="You are helpful.", max_tokens=50))
        self.assertEqual(r.text, "Generated code.")
        self.assertEqual(r.provider, "openai")
        self.assertEqual(r.usage.input_tokens, 12)
        self.assertEqual(captured["messages"][0], {"role": "system", "content": "You are helpful."})


class GeminiProviderTests(SimpleTestCase):
    @mock.patch.dict("os.environ", {"GOOGLE_API_KEY": "", "GEMINI_API_KEY": ""}, clear=False)
    def test_unavailable_without_key(self):
        from apps.ai_providers.gemini_provider import GeminiProvider
        p = GeminiProvider()
        self.assertFalse(p.is_available())
        with self.assertRaises(ProviderUnavailable):
            p.complete(CompletionRequest(messages=[Message("user", "hi")]))

    def test_registered_and_in_catalog(self):
        self.assertIn("gemini", registry)
        from apps.model_router.catalog import profile_for
        self.assertIsNotNone(profile_for("gemini", "gemini-2.5-flash"))

    def test_complete_maps_request_to_sdk(self):
        import sys, types as pytypes
        from apps.ai_providers.gemini_provider import GeminiProvider

        captured = {}

        class _Part:
            @staticmethod
            def from_text(text): return {"text": text}
        class _Content:
            def __init__(self, role, parts): self.role = role; self.parts = parts
        class _Config:
            def __init__(self, **kw): self.kw = kw
        class _Meta:
            prompt_token_count = 9; candidates_token_count = 4
        class _Resp:
            text = "Generated code."; usage_metadata = _Meta()
        class _Models:
            def generate_content(self, model, contents, config):
                captured.update(model=model, contents=contents, config=config)
                return _Resp()
        class _Client:
            def __init__(self, api_key=None): self.models = _Models()

        google_mod = pytypes.ModuleType("google")
        genai_mod = pytypes.ModuleType("google.genai")
        types_mod = pytypes.ModuleType("google.genai.types")
        types_mod.Part = _Part
        types_mod.Content = _Content
        types_mod.GenerateContentConfig = _Config
        genai_mod.Client = _Client
        genai_mod.types = types_mod
        google_mod.genai = genai_mod

        fakes = {"google": google_mod, "google.genai": genai_mod,
                 "google.genai.types": types_mod}
        with mock.patch.dict(sys.modules, fakes), \
             mock.patch.dict("os.environ", {"GEMINI_API_KEY": "key-test"}, clear=False):
            p = GeminiProvider()
            self.assertTrue(p.is_available())
            r = p.complete(CompletionRequest(
                messages=[Message("user", "build")], system="Be helpful.",
                model="gemini-2.5-pro", max_tokens=50))
        self.assertEqual(r.text, "Generated code.")
        self.assertEqual(r.provider, "gemini")
        self.assertEqual(r.model, "gemini-2.5-pro")
        self.assertEqual(r.usage.input_tokens, 9)
        self.assertEqual(captured["config"].kw["system_instruction"], "Be helpful.")
        self.assertEqual(captured["contents"][0].role, "user")


class GenerationStatusTests(SimpleTestCase):
    def test_demo_mode_when_no_live_provider(self):
        from apps.ai_providers.registry import generation_status
        with mock.patch("apps.ai_providers.registry.live_providers", return_value=[]):
            s = generation_status()
        self.assertFalse(s["live"])
        self.assertIn("demo mode", s["message"].lower())

    def test_live_when_a_real_provider_available(self):
        from apps.ai_providers.registry import generation_status
        from apps.ai_providers.openai_provider import OpenAIProvider
        fake = OpenAIProvider()
        with mock.patch("apps.ai_providers.registry.live_providers", return_value=[fake]):
            s = generation_status()
        self.assertTrue(s["live"])
        self.assertEqual(s["provider"], "openai")
