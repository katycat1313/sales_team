"""
Demo Process End-to-End Tests
==============================
Exercises the complete Vaspi/VAPI demo flow at the HTTP handler boundary using
FastAPI's TestClient and fully mocked external integrations (Google Sheet,
Twilio SMS, SendGrid email, SQLite DB).

Test Coverage:
1) Known caller inbound call path (lookup-caller with Sheet match)
2) Unknown caller inbound call path (lookup-caller with no match)
3) Enrichment behaviour (update-prospect-info blank-fill, no overwrite)
4) Outbound outreach messaging (SMS + email template rendering, error handling)
5) Intent + emotion (prompt sections, save_notes schema fields)
"""

import json
import os
import sys
import unittest
from unittest.mock import AsyncMock, MagicMock, patch

# ── Pre-import patching (mirrors conftest.py approach) ───────────────────────
# These must be applied *before* main.py is loaded so module-level side-effects
# (file system access, heavy agent imports) are all neutralised.

# Ensure orchestrator directory is on the path.
_orch_dir = os.path.join(os.path.dirname(__file__), "..")
if _orch_dir not in sys.path:
    sys.path.insert(0, _orch_dir)

# Stub browser / playwright.
_fake_browser = MagicMock()
_fake_browser.browser_tool = MagicMock()
sys.modules.setdefault("tools.browser", _fake_browser)
sys.modules.setdefault("playwright", MagicMock())
sys.modules.setdefault("playwright.async_api", MagicMock())

# Stub every agent so their heavy imports (genai, etc.) are skipped.
for _agent in [
    "coordinator", "research", "small_biz_expert", "sales", "outreach",
    "engineer", "team_leader", "job_seeker", "scout", "networking", "coach",
    "interview_coach", "lead_gen", "marketing", "biz_dev", "automations",
    "solutions_architect", "resume_builder", "research_assistant",
]:
    sys.modules.setdefault(f"agents.{_agent}", MagicMock())

sys.modules.setdefault("scheduler", MagicMock())
sys.modules.setdefault("memory.memory", MagicMock())
sys.modules.setdefault("task_handler", MagicMock())
sys.modules.setdefault("playbooks", MagicMock())

# Use a throwaway DB + suppress Path.mkdir / Path.read_text at module level.
os.environ.setdefault("MEMORY_DB_PATH", "/tmp/test_demo_e2e_memory.db")

_mkdir_patcher = patch("pathlib.Path.mkdir", return_value=None)
_read_text_patcher = patch("pathlib.Path.read_text", return_value="")
_mkdir_patcher.start()
_read_text_patcher.start()

import main  # noqa: E402  — must come after all stubs above

_mkdir_patcher.stop()
_read_text_patcher.stop()

# Patch log_event to suppress all file I/O during tests.
_log_event_patcher = patch("main.log_event", return_value={})
_log_event_patcher.start()

# Patch log_compliance_event similarly.
_compliance_patcher = patch("main.log_compliance_event", return_value={})
_compliance_patcher.start()

# ── TestClient setup ──────────────────────────────────────────────────────────
from starlette.testclient import TestClient  # noqa: E402

# Disable the lifespan so init_db / background tasks don't fire during tests.
_client = TestClient(main.app, raise_server_exceptions=True)

# ── Patch path constants ──────────────────────────────────────────────────────
# These handlers use lazy (in-function) imports, so we patch the canonical
# module paths rather than attributes on the main module.
_GET_PROSPECTS = "memory.memory.get_prospects"
_UPDATE_PROSPECT = "memory.memory.update_prospect"
_SAVE_PROSPECT = "memory.memory.save_prospect"
_GET_AVAILABILITY = "memory.memory.get_availability"
_SEND_SMS = "tools.sms_tool.send_sms"
_SEND_EMAIL = "tools.gmail_tool.send_email"

# Default availability mock so save-notes tests don't need to set it every time.
_DEFAULT_AVAILABILITY = {"available_now": False}


# ─────────────────────────────────────────────────────────────────────────────
# Helper: VAPI function-call payload format
# ─────────────────────────────────────────────────────────────────────────────

def _vapi_body(params: dict) -> dict:
    """Wrap params in the VAPI functionCall envelope that the endpoints expect."""
    return {"message": {"functionCall": {"parameters": params}}}


# ═════════════════════════════════════════════════════════════════════════════
# 1. Known Caller Inbound Call Path
# ═════════════════════════════════════════════════════════════════════════════

class TestKnownCallerLookup(unittest.TestCase):
    """
    POST /vapi/lookup-caller where the prospect IS in the local DB.
    Verifies:
    - response includes found=True
    - caller name and business_name are returned
    - correct source tag is present
    """

    def _get_known_prospect(self):
        return [
            {
                "phone": "+14045551234",
                "owner_name": "Katy Smith",
                "business_name": "Katy's Bakery",
                "niche": "food",
                "location": "Atlanta GA",
                "email": "katy@example.com",
                "website": "https://katysbakery.com",
                "last_call_outcome": "interested",
                "call_temperature": "warm",
            }
        ]

    def test_known_caller_returns_found_true(self):
        """Lookup by a phone that exists → found=True in the JSON payload."""
        with patch(_GET_PROSPECTS, return_value=self._get_known_prospect()), \
             patch.dict(os.environ, {"BUSINESS_LOOKUP_URL": ""}):
            resp = _client.post("/vapi/lookup-caller", json=_vapi_body({"phone": "+14045551234"}))
        self.assertEqual(resp.status_code, 200)
        data = json.loads(resp.json()["result"])
        self.assertTrue(data["found"])

    def test_known_caller_returns_owner_name(self):
        """Response includes the prospect's name."""
        with patch(_GET_PROSPECTS, return_value=self._get_known_prospect()), \
             patch.dict(os.environ, {"BUSINESS_LOOKUP_URL": ""}):
            resp = _client.post("/vapi/lookup-caller", json=_vapi_body({"phone": "+14045551234"}))
        data = json.loads(resp.json()["result"])
        self.assertEqual(data["owner_name"], "Katy Smith")

    def test_known_caller_returns_business_name(self):
        """Response includes the prospect's business name."""
        with patch(_GET_PROSPECTS, return_value=self._get_known_prospect()), \
             patch.dict(os.environ, {"BUSINESS_LOOKUP_URL": ""}):
            resp = _client.post("/vapi/lookup-caller", json=_vapi_body({"phone": "+14045551234"}))
        data = json.loads(resp.json()["result"])
        self.assertEqual(data["business_name"], "Katy's Bakery")

    def test_known_caller_phone_with_formatting_still_matches(self):
        """Phones with formatting differences (dashes, spaces) still match."""
        prospect_with_dashes = [dict(self._get_known_prospect()[0])]
        prospect_with_dashes[0]["phone"] = "404-555-1234"
        with patch(_GET_PROSPECTS, return_value=prospect_with_dashes), \
             patch.dict(os.environ, {"BUSINESS_LOOKUP_URL": ""}):
            resp = _client.post("/vapi/lookup-caller", json=_vapi_body({"phone": "4045551234"}))
        data = json.loads(resp.json()["result"])
        self.assertTrue(data["found"])

    def test_known_caller_db_source_is_local_db(self):
        """When found in local DB (no sheet URL), source is 'local_db'."""
        with patch(_GET_PROSPECTS, return_value=self._get_known_prospect()), \
             patch.dict(os.environ, {"BUSINESS_LOOKUP_URL": ""}):
            resp = _client.post("/vapi/lookup-caller", json=_vapi_body({"phone": "+14045551234"}))
        data = json.loads(resp.json()["result"])
        self.assertEqual(data.get("source"), "local_db")

    def test_known_caller_from_google_sheet_overrides_db(self):
        """When the Sheet URL returns a match, source is updated to 'google_sheet'."""
        sheet_response = {
            "found": True,
            "owner_name": "Katy Sheet",
            "business_name": "Katy's Bakery (Sheet)",
            "niche": "food",
        }
        mock_http_resp = MagicMock()
        mock_http_resp.status_code = 200
        mock_http_resp.json.return_value = sheet_response

        mock_client = AsyncMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_client.get = AsyncMock(return_value=mock_http_resp)

        with patch(_GET_PROSPECTS, return_value=self._get_known_prospect()), \
             patch.dict(os.environ, {"BUSINESS_LOOKUP_URL": "https://sheet.example.com/lookup"}), \
             patch("httpx.AsyncClient", return_value=mock_client):
            resp = _client.post("/vapi/lookup-caller", json=_vapi_body({"phone": "+14045551234"}))
        data = json.loads(resp.json()["result"])
        self.assertTrue(data["found"])
        self.assertEqual(data.get("source"), "google_sheet")

    def test_lookup_caller_no_phone_returns_found_false(self):
        """Empty phone → found=False, no crash."""
        with patch(_GET_PROSPECTS, return_value=[]):
            resp = _client.post("/vapi/lookup-caller", json=_vapi_body({"phone": ""}))
        self.assertEqual(resp.status_code, 200)
        data = json.loads(resp.json()["result"])
        self.assertFalse(data["found"])


# ═════════════════════════════════════════════════════════════════════════════
# 2. Unknown Caller Inbound Call Path
# ═════════════════════════════════════════════════════════════════════════════

class TestUnknownCallerLookup(unittest.TestCase):
    """
    POST /vapi/lookup-caller where the prospect is NOT in DB or Sheet.
    Verifies:
    - response includes found=False
    - the phone is echoed back for reference
    """

    def test_unknown_caller_returns_found_false(self):
        """No DB match, no sheet URL → found=False."""
        with patch(_GET_PROSPECTS, return_value=[]), \
             patch.dict(os.environ, {"BUSINESS_LOOKUP_URL": ""}):
            resp = _client.post("/vapi/lookup-caller", json=_vapi_body({"phone": "+15555559999"}))
        self.assertEqual(resp.status_code, 200)
        data = json.loads(resp.json()["result"])
        self.assertFalse(data["found"])

    def test_unknown_caller_echoes_phone(self):
        """The returned payload includes the caller's phone number."""
        with patch(_GET_PROSPECTS, return_value=[]), \
             patch.dict(os.environ, {"BUSINESS_LOOKUP_URL": ""}):
            resp = _client.post("/vapi/lookup-caller", json=_vapi_body({"phone": "+15555559999"}))
        data = json.loads(resp.json()["result"])
        self.assertEqual(data.get("phone"), "+15555559999")

    def test_unknown_caller_sheet_returns_no_match(self):
        """Even with a Sheet URL, a non-match returns found=False."""
        mock_http_resp = MagicMock()
        mock_http_resp.status_code = 200
        mock_http_resp.json.return_value = {"found": False}

        mock_client = AsyncMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_client.get = AsyncMock(return_value=mock_http_resp)

        with patch(_GET_PROSPECTS, return_value=[]), \
             patch.dict(os.environ, {"BUSINESS_LOOKUP_URL": "https://sheet.example.com/lookup"}), \
             patch("httpx.AsyncClient", return_value=mock_client):
            resp = _client.post("/vapi/lookup-caller", json=_vapi_body({"phone": "+15555559999"}))
        data = json.loads(resp.json()["result"])
        self.assertFalse(data["found"])

    def test_unknown_caller_sheet_http_failure_returns_found_false(self):
        """If the Sheet lookup HTTP call fails, endpoint still returns found=False gracefully."""
        mock_client = AsyncMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_client.get = AsyncMock(side_effect=Exception("Connection refused"))

        with patch(_GET_PROSPECTS, return_value=[]), \
             patch.dict(os.environ, {"BUSINESS_LOOKUP_URL": "https://sheet.example.com/lookup"}), \
             patch("httpx.AsyncClient", return_value=mock_client):
            resp = _client.post("/vapi/lookup-caller", json=_vapi_body({"phone": "+15555559999"}))
        self.assertEqual(resp.status_code, 200)
        data = json.loads(resp.json()["result"])
        self.assertFalse(data["found"])


class TestUnknownCallerPromptGuidance(unittest.TestCase):
    """Verify INCOMING_CALL_GUIDE and prompt content drives the correct discovery flow."""

    def setUp(self):
        import importlib
        import tools.vapi_tool as vt
        importlib.reload(vt)
        self.vt = vt

    def test_incoming_call_guide_tells_agent_to_call_lookup(self):
        """Guide must instruct Eric to call lookup_caller at call start."""
        self.assertIn("lookup_caller", self.vt.INCOMING_CALL_GUIDE)

    def test_incoming_call_guide_unknown_caller_intro_flow(self):
        """Guide must describe the intro → name → business flow for unknown callers."""
        guide = self.vt.INCOMING_CALL_GUIDE
        self.assertIn("found=false", guide)
        self.assertIn("name", guide.lower())
        self.assertIn("business", guide.lower())

    def test_incoming_call_guide_niche_discovery(self):
        """Guide must mention asking for niche when business type is unclear."""
        self.assertIn("niche", self.vt.INCOMING_CALL_GUIDE.lower())

    def test_incoming_call_guide_known_caller_personalization(self):
        """Guide must reference using {name} and {business_name} for known callers."""
        guide = self.vt.INCOMING_CALL_GUIDE
        self.assertIn("found=true", guide)
        self.assertIn("{name}", guide)
        self.assertIn("{business_name}", guide)


# ═════════════════════════════════════════════════════════════════════════════
# 3. Enrichment Behaviour — POST /vapi/update-prospect-info
# ═════════════════════════════════════════════════════════════════════════════

class TestEnrichmentBehaviour(unittest.TestCase):
    """
    Verifies that update-prospect-info:
    - fills blank fields on an existing prospect
    - does NOT overwrite already-populated fields
    - creates a new record for an unknown phone
    """

    _EXISTING_PROSPECT = {
        "phone": "+14045551234",
        "business_name": "Katy's Bakery",
        "owner_name": "Katy Smith",
        "location": "Atlanta GA",
        "niche": "",       # blank — should be filled
        "email": "",       # blank — should be filled
        "website": "https://katysbakery.com",  # set — must NOT be overwritten
    }

    def test_enrichment_fills_blank_niche(self):
        """When niche is blank, update-prospect-info fills it."""
        mock_update = MagicMock()
        with patch(_GET_PROSPECTS, return_value=[self._EXISTING_PROSPECT]), \
             patch(_UPDATE_PROSPECT, mock_update):
            _client.post(
                "/vapi/update-prospect-info",
                json=_vapi_body({
                    "prospect_phone": "+14045551234",
                    "niche": "food",
                }),
            )
        # update_prospect must have been called
        mock_update.assert_called_once()
        call_kwargs = mock_update.call_args[1]
        self.assertEqual(call_kwargs.get("niche"), "food")

    def test_enrichment_fills_blank_email(self):
        """When email is blank, update-prospect-info fills it."""
        mock_update = MagicMock()
        with patch(_GET_PROSPECTS, return_value=[self._EXISTING_PROSPECT]), \
             patch(_UPDATE_PROSPECT, mock_update):
            _client.post(
                "/vapi/update-prospect-info",
                json=_vapi_body({
                    "prospect_phone": "+14045551234",
                    "email": "katy@example.com",
                }),
            )
        call_kwargs = mock_update.call_args[1]
        self.assertEqual(call_kwargs.get("email"), "katy@example.com")

    def test_enrichment_does_not_overwrite_existing_website(self):
        """Existing website must not appear as an update kwarg (blank-fill only)."""
        mock_update = MagicMock()
        existing = dict(self._EXISTING_PROSPECT)
        existing["website"] = "https://katysbakery.com"
        with patch(_GET_PROSPECTS, return_value=[existing]), \
             patch(_UPDATE_PROSPECT, mock_update):
            _client.post(
                "/vapi/update-prospect-info",
                json=_vapi_body({
                    "prospect_phone": "+14045551234",
                    "website": "https://malicious-override.com",
                }),
            )
        # update_prospect should NOT be called with the new website
        # (existing field → skipped by the blank-fill logic)
        if mock_update.called:
            call_kwargs = mock_update.call_args[1]
            self.assertNotEqual(
                call_kwargs.get("website"),
                "https://malicious-override.com",
                "Existing website must not be overwritten",
            )

    def test_enrichment_new_prospect_calls_save(self):
        """When phone is unknown, save_prospect is called to create a new record."""
        mock_save = MagicMock()
        with patch(_GET_PROSPECTS, return_value=[]), \
             patch(_SAVE_PROSPECT, mock_save):
            resp = _client.post(
                "/vapi/update-prospect-info",
                json=_vapi_body({
                    "prospect_phone": "+19995550001",
                    "business_name": "New Biz",
                    "owner_name": "John Doe",
                }),
            )
        self.assertEqual(resp.status_code, 200)
        mock_save.assert_called_once()

    def test_enrichment_new_prospect_pipeline_stage(self):
        """New prospects discovered mid-call get pipeline_stage='inbound_discovery'."""
        mock_save = MagicMock()
        with patch(_GET_PROSPECTS, return_value=[]), \
             patch(_SAVE_PROSPECT, mock_save):
            _client.post(
                "/vapi/update-prospect-info",
                json=_vapi_body({
                    "prospect_phone": "+19995550001",
                    "business_name": "New Biz",
                }),
            )
        call_kwargs = mock_save.call_args[1]
        self.assertEqual(call_kwargs.get("pipeline_stage"), "inbound_discovery")

    def test_enrichment_missing_phone_returns_ok(self):
        """If prospect_phone is absent, endpoint still returns ok (never blocks call)."""
        resp = _client.post(
            "/vapi/update-prospect-info",
            json=_vapi_body({"business_name": "Some Biz"}),
        )
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.json().get("result"), "ok")

    def test_enrichment_fields_mapped_to_correct_keys(self):
        """All recognised fields (niche, email, owner_name, services) are passed through."""
        mock_update = MagicMock()
        with patch(_GET_PROSPECTS, return_value=[self._EXISTING_PROSPECT]), \
             patch(_UPDATE_PROSPECT, mock_update):
            _client.post(
                "/vapi/update-prospect-info",
                json=_vapi_body({
                    "prospect_phone": "+14045551234",
                    "niche": "bakery",
                    "email": "hello@example.com",
                    "services": "Wedding cakes",
                }),
            )
        call_kwargs = mock_update.call_args[1]
        self.assertEqual(call_kwargs.get("niche"), "bakery")
        self.assertEqual(call_kwargs.get("email"), "hello@example.com")
        self.assertEqual(call_kwargs.get("services"), "Wedding cakes")


# ═════════════════════════════════════════════════════════════════════════════
# 4. Outbound Outreach Messaging — POST /vapi/send-outreach
# ═════════════════════════════════════════════════════════════════════════════

class TestOutboundSMSOutreach(unittest.TestCase):
    """
    Verifies SMS delivery path:
    - Template rendering of {name} and {business_name}
    - Correct parameters passed to send_sms
    - Graceful error handling when provider returns error
    """

    def test_sms_template_name_rendered(self):
        """The SMS body delivered to Twilio contains the prospect's name."""
        captured = {}

        def fake_send_sms(to_number, body):
            captured["body"] = body
            return {"sent": True}

        with patch(_SEND_SMS, side_effect=fake_send_sms):
            _client.post(
                "/vapi/send-outreach",
                json=_vapi_body({
                    "delivery_method": "sms",
                    "prospect_phone": "+14045551234",
                    "contact_name": "Katy",
                    "business_name": "Katy's Bakery",
                }),
            )
        self.assertIn("Katy", captured.get("body", ""))

    def test_sms_template_business_name_rendered(self):
        """The SMS body contains the prospect's business name."""
        captured = {}

        def fake_send_sms(to_number, body):
            captured["body"] = body
            return {"sent": True}

        with patch(_SEND_SMS, side_effect=fake_send_sms):
            _client.post(
                "/vapi/send-outreach",
                json=_vapi_body({
                    "delivery_method": "sms",
                    "prospect_phone": "+14045551234",
                    "contact_name": "Katy",
                    "business_name": "Katy's Bakery",
                }),
            )
        self.assertIn("Katy's Bakery", captured.get("body", ""))

    def test_sms_correct_recipient_phone(self):
        """send_sms is called with the exact prospect phone from the request."""
        captured = {}

        def fake_send_sms(to_number, body):
            captured["to"] = to_number
            return {"sent": True}

        with patch(_SEND_SMS, side_effect=fake_send_sms):
            _client.post(
                "/vapi/send-outreach",
                json=_vapi_body({
                    "delivery_method": "sms",
                    "prospect_phone": "+14045551234",
                    "contact_name": "Katy",
                    "business_name": "Katy's Bakery",
                }),
            )
        self.assertEqual(captured.get("to"), "+14045551234")

    def test_sms_success_response(self):
        """On success, the response result indicates the message was sent."""
        with patch(_SEND_SMS, return_value={"sent": True}):
            resp = _client.post(
                "/vapi/send-outreach",
                json=_vapi_body({
                    "delivery_method": "sms",
                    "prospect_phone": "+14045551234",
                    "contact_name": "Katy",
                    "business_name": "Katy's Bakery",
                }),
            )
        self.assertEqual(resp.status_code, 200)
        result = resp.json()["result"]
        self.assertIn("text", result.lower())

    def test_sms_provider_error_returns_graceful_message(self):
        """When Twilio returns an error, Eric responds with a fallback—not a crash."""
        with patch(_SEND_SMS, return_value={"sent": False, "error": "Twilio outage"}):
            resp = _client.post(
                "/vapi/send-outreach",
                json=_vapi_body({
                    "delivery_method": "sms",
                    "prospect_phone": "+14045551234",
                    "contact_name": "Katy",
                    "business_name": "Katy's Bakery",
                }),
            )
        self.assertEqual(resp.status_code, 200)
        result = resp.json()["result"]
        # Should offer an alternative rather than exposing the raw error
        self.assertFalse("Twilio outage" in result)

    def test_sms_missing_phone_returns_prompt_for_number(self):
        """If prospect_phone is absent, Eric politely asks for the number."""
        resp = _client.post(
            "/vapi/send-outreach",
            json=_vapi_body({
                "delivery_method": "sms",
                "prospect_phone": "",
                "contact_name": "Katy",
                "business_name": "Katy's Bakery",
            }),
        )
        self.assertEqual(resp.status_code, 200)
        result = resp.json()["result"].lower()
        self.assertTrue("number" in result or "text" in result or "phone" in result)

    def test_sms_exception_returns_graceful_error(self):
        """An unexpected exception from send_sms is caught and returns a safe message."""
        with patch(_SEND_SMS, side_effect=RuntimeError("boom")):
            resp = _client.post(
                "/vapi/send-outreach",
                json=_vapi_body({
                    "delivery_method": "sms",
                    "prospect_phone": "+14045551234",
                    "contact_name": "Katy",
                    "business_name": "Katy's Bakery",
                }),
            )
        self.assertEqual(resp.status_code, 200)
        # Must not expose internal error details
        result = resp.json()["result"]
        self.assertNotIn("boom", result)


class TestOutboundEmailOutreach(unittest.TestCase):
    """
    Verifies email delivery path:
    - Template rendering of {name} and {business_name} in subject and body
    - Correct routing to send_email when delivery_method='email'
    - Error handling when provider fails
    """

    def test_email_subject_name_and_business_rendered(self):
        """The email subject contains business_name."""
        captured = {}

        def fake_send_email(to, subject, body, **kwargs):
            captured["subject"] = subject
            captured["body"] = body
            return {"sent": True}

        with patch(_SEND_EMAIL, side_effect=fake_send_email):
            _client.post(
                "/vapi/send-outreach",
                json=_vapi_body({
                    "delivery_method": "email",
                    "prospect_email": "prospect@example.com",
                    "contact_name": "Bob",
                    "business_name": "Bob's HVAC",
                }),
            )
        self.assertIn("Bob's HVAC", captured.get("subject", ""))

    def test_email_body_name_rendered(self):
        """The email body contains the contact's name."""
        captured = {}

        def fake_send_email(to, subject, body, **kwargs):
            captured["body"] = body
            return {"sent": True}

        with patch(_SEND_EMAIL, side_effect=fake_send_email):
            _client.post(
                "/vapi/send-outreach",
                json=_vapi_body({
                    "delivery_method": "email",
                    "prospect_email": "prospect@example.com",
                    "contact_name": "Bob",
                    "business_name": "Bob's HVAC",
                }),
            )
        self.assertIn("Bob", captured.get("body", ""))

    def test_email_correct_recipient(self):
        """send_email is called with the exact prospect email from the request."""
        captured = {}

        def fake_send_email(to, subject, body, **kwargs):
            captured["to"] = to
            return {"sent": True}

        with patch(_SEND_EMAIL, side_effect=fake_send_email):
            _client.post(
                "/vapi/send-outreach",
                json=_vapi_body({
                    "delivery_method": "email",
                    "prospect_email": "prospect@example.com",
                    "contact_name": "Bob",
                    "business_name": "Bob's HVAC",
                }),
            )
        self.assertEqual(captured.get("to"), "prospect@example.com")

    def test_email_success_response(self):
        """On success, the response indicates the email was sent."""
        with patch(_SEND_EMAIL, return_value={"sent": True}):
            resp = _client.post(
                "/vapi/send-outreach",
                json=_vapi_body({
                    "delivery_method": "email",
                    "prospect_email": "prospect@example.com",
                    "contact_name": "Bob",
                    "business_name": "Bob's HVAC",
                }),
            )
        self.assertEqual(resp.status_code, 200)
        result = resp.json()["result"].lower()
        self.assertIn("sent", result)

    def test_email_provider_error_returns_graceful_message(self):
        """When SendGrid returns an error, Eric responds with a fallback."""
        with patch(_SEND_EMAIL, return_value={"sent": False, "error": "API key invalid"}):
            resp = _client.post(
                "/vapi/send-outreach",
                json=_vapi_body({
                    "delivery_method": "email",
                    "prospect_email": "prospect@example.com",
                    "contact_name": "Bob",
                    "business_name": "Bob's HVAC",
                }),
            )
        self.assertEqual(resp.status_code, 200)
        result = resp.json()["result"]
        self.assertNotIn("API key invalid", result)

    def test_email_missing_address_returns_prompt(self):
        """If prospect_email is absent, Eric politely asks for it."""
        resp = _client.post(
            "/vapi/send-outreach",
            json=_vapi_body({
                "delivery_method": "email",
                "prospect_email": "",
                "contact_name": "Bob",
                "business_name": "Bob's HVAC",
            }),
        )
        self.assertEqual(resp.status_code, 200)
        result = resp.json()["result"].lower()
        self.assertTrue("email" in result or "address" in result)

    def test_delivery_method_defaults_to_sms(self):
        """When delivery_method is omitted or unrecognised, the SMS path is taken."""
        captured = {}

        def fake_send_sms(to_number, body):
            captured["called"] = True
            return {"sent": True}

        with patch(_SEND_SMS, side_effect=fake_send_sms):
            _client.post(
                "/vapi/send-outreach",
                json=_vapi_body({
                    "prospect_phone": "+14045551234",
                    "contact_name": "Alice",
                    "business_name": "Alice's Spa",
                }),
            )
        self.assertTrue(captured.get("called"), "SMS path was not taken for missing delivery_method")


# ═════════════════════════════════════════════════════════════════════════════
# 5. Intent + Emotion — Prompt content and save_notes schema
# ═════════════════════════════════════════════════════════════════════════════

class TestIntentAndEmotionPrompts(unittest.TestCase):
    """
    Verify that FULL_SYSTEM_PROMPT, INCOMING_CALL_GUIDE, and ONBOARDING_DISCOVERY
    contain the structured guidance required for intent/emotion detection.
    """

    def setUp(self):
        import importlib
        import tools.vapi_tool as vt
        importlib.reload(vt)
        self.vt = vt

    def test_prompt_has_buyer_intent_section(self):
        self.assertIn("BUYER INTENT SIGNAL DETECTION", self.vt.FULL_SYSTEM_PROMPT)

    def test_prompt_has_high_intent_signals(self):
        self.assertIn("HIGH", self.vt.FULL_SYSTEM_PROMPT)

    def test_prompt_has_medium_intent_signals(self):
        self.assertIn("MEDIUM", self.vt.FULL_SYSTEM_PROMPT)

    def test_prompt_has_low_intent_signals(self):
        self.assertIn("LOW", self.vt.FULL_SYSTEM_PROMPT)

    def test_prompt_has_emotional_intelligence_section(self):
        self.assertIn("EMOTIONAL INTELLIGENCE", self.vt.FULL_SYSTEM_PROMPT)

    def test_prompt_has_empathy_rule(self):
        self.assertIn("EMPATHY RULE", self.vt.FULL_SYSTEM_PROMPT)

    def test_prompt_emotional_states_covered(self):
        """Prompt should address at least the four key emotional states."""
        prompt = self.vt.FULL_SYSTEM_PROMPT.lower()
        for state in ("frustrated", "excited", "skeptical", "rushed"):
            self.assertIn(state, prompt, f"Emotional state '{state}' missing from prompt")

    def test_onboarding_discovery_has_enrichment_guidance(self):
        self.assertIn("SHEET ENRICHMENT", self.vt.ONBOARDING_DISCOVERY)
        self.assertIn("update_prospect_info", self.vt.ONBOARDING_DISCOVERY)


class TestSaveNotesSchema(unittest.TestCase):
    """
    Verify the save_notes VAPI tool includes fields for buyer_intent_level,
    emotional_state, and discovered_info so they can be captured mid-call.
    """

    def _get_save_notes_tool(self):
        import importlib
        import tools.vapi_tool as vt
        importlib.reload(vt)
        tools = vt._assistant_tools("http://localhost:8000", "+15551234567", enable_transfer=False)
        return next(
            (t for t in tools if t.get("function", {}).get("name") == "save_notes"),
            None,
        )

    def test_save_notes_tool_exists(self):
        self.assertIsNotNone(self._get_save_notes_tool())

    def test_save_notes_has_buyer_intent_level(self):
        props = self._get_save_notes_tool()["function"]["parameters"]["properties"]
        self.assertIn("buyer_intent_level", props)

    def test_save_notes_has_emotional_state(self):
        props = self._get_save_notes_tool()["function"]["parameters"]["properties"]
        self.assertIn("emotional_state", props)

    def test_save_notes_has_discovered_info(self):
        props = self._get_save_notes_tool()["function"]["parameters"]["properties"]
        self.assertIn("discovered_info", props)

    def test_save_notes_endpoint_accepts_intent_fields(self):
        """
        POST /vapi/save-notes with buyer_intent_level and emotional_state should
        return 200 and not error (persistence is mocked at the prospect level).
        """
        with patch(_GET_PROSPECTS, return_value=[]), \
             patch(_SAVE_PROSPECT, MagicMock()), \
             patch(_UPDATE_PROSPECT, MagicMock()), \
             patch(_GET_AVAILABILITY, return_value=_DEFAULT_AVAILABILITY):
            resp = _client.post(
                "/vapi/save-notes",
                json=_vapi_body({
                    "prospect_phone": "+14045551234",
                    "notes": "Prospect sounds interested",
                    "buyer_intent_level": "HIGH",
                    "emotional_state": "excited",
                    "discovered_info": {"niche": "plumbing"},
                }),
            )
        self.assertEqual(resp.status_code, 200)

    def test_intent_fields_propagated_to_update_prospect(self):
        """
        When save_notes is called with emotion/intent fields for a known prospect,
        update_prospect is invoked so the data is persisted.
        """
        existing = [{"phone": "+14045551234", "business_name": "Acme", "location": "GA"}]
        mock_update = MagicMock()
        with patch(_GET_PROSPECTS, return_value=existing), \
             patch(_UPDATE_PROSPECT, mock_update), \
             patch(_GET_AVAILABILITY, return_value=_DEFAULT_AVAILABILITY):
            _client.post(
                "/vapi/save-notes",
                json=_vapi_body({
                    "prospect_phone": "+14045551234",
                    "notes": "Very excited, asked about pricing",
                    "buyer_intent_level": "HIGH",
                    "emotional_state": "excited",
                }),
            )
        mock_update.assert_called_once()


# ═════════════════════════════════════════════════════════════════════════════
# Full Demo Flow Integration Scenario
# ═════════════════════════════════════════════════════════════════════════════

class TestFullDemoFlowKnownCaller(unittest.TestCase):
    """
    Simulates the complete happy path for a KNOWN caller:
    1. Inbound call → lookup-caller → found=True, name + business returned
    2. Mid-call enrichment → update-prospect-info fills blank email
    3. Caller asks for follow-up → send-outreach SMS sent with correct template
    """

    _PROSPECT = {
        "phone": "+14045551234",
        "owner_name": "Katy Smith",
        "business_name": "Katy's Bakery",
        "niche": "food",
        "location": "Atlanta GA",
        "email": "",   # will be filled mid-call
        "website": "https://katysbakery.com",
    }

    def test_step1_known_caller_lookup(self):
        with patch(_GET_PROSPECTS, return_value=[self._PROSPECT]), \
             patch.dict(os.environ, {"BUSINESS_LOOKUP_URL": ""}):
            resp = _client.post(
                "/vapi/lookup-caller",
                json=_vapi_body({"phone": "+14045551234"}),
            )
        data = json.loads(resp.json()["result"])
        self.assertTrue(data["found"])
        self.assertEqual(data["owner_name"], "Katy Smith")
        self.assertEqual(data["business_name"], "Katy's Bakery")

    def test_step2_mid_call_email_enrichment(self):
        mock_update = MagicMock()
        with patch(_GET_PROSPECTS, return_value=[self._PROSPECT]), \
             patch(_UPDATE_PROSPECT, mock_update):
            resp = _client.post(
                "/vapi/update-prospect-info",
                json=_vapi_body({
                    "prospect_phone": "+14045551234",
                    "email": "katy@example.com",
                }),
            )
        self.assertEqual(resp.json()["result"], "ok")
        mock_update.assert_called_once()
        self.assertEqual(mock_update.call_args[1].get("email"), "katy@example.com")

    def test_step3_outreach_sms_sent(self):
        captured = {}

        def fake_sms(to_number, body):
            captured["to"] = to_number
            captured["body"] = body
            return {"sent": True}

        with patch(_SEND_SMS, side_effect=fake_sms):
            resp = _client.post(
                "/vapi/send-outreach",
                json=_vapi_body({
                    "delivery_method": "sms",
                    "prospect_phone": "+14045551234",
                    "contact_name": "Katy Smith",
                    "business_name": "Katy's Bakery",
                }),
            )
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(captured["to"], "+14045551234")
        self.assertIn("Katy Smith", captured["body"])
        self.assertIn("Katy's Bakery", captured["body"])


class TestFullDemoFlowUnknownCaller(unittest.TestCase):
    """
    Simulates the complete flow for an UNKNOWN caller:
    1. Inbound call → lookup-caller → found=False
    2. Agent collects info mid-call → update-prospect-info creates new record
    3. Agent sends follow-up email
    """

    def test_step1_unknown_caller_lookup(self):
        with patch(_GET_PROSPECTS, return_value=[]), \
             patch.dict(os.environ, {"BUSINESS_LOOKUP_URL": ""}):
            resp = _client.post(
                "/vapi/lookup-caller",
                json=_vapi_body({"phone": "+15555550001"}),
            )
        data = json.loads(resp.json()["result"])
        self.assertFalse(data["found"])

    def test_step2_new_prospect_created_from_discovery(self):
        mock_save = MagicMock()
        with patch(_GET_PROSPECTS, return_value=[]), \
             patch(_SAVE_PROSPECT, mock_save):
            resp = _client.post(
                "/vapi/update-prospect-info",
                json=_vapi_body({
                    "prospect_phone": "+15555550001",
                    "business_name": "Brand New Biz",
                    "owner_name": "Jane Doe",
                    "niche": "wellness",
                }),
            )
        self.assertEqual(resp.json()["result"], "ok")
        mock_save.assert_called_once()
        call_kwargs = mock_save.call_args[1]
        self.assertEqual(call_kwargs.get("business_name"), "Brand New Biz")
        self.assertEqual(call_kwargs.get("owner_name"), "Jane Doe")

    def test_step3_follow_up_email_sent(self):
        captured = {}

        def fake_email(to, subject, body, **kwargs):
            captured["to"] = to
            captured["subject"] = subject
            captured["body"] = body
            return {"sent": True}

        with patch(_SEND_EMAIL, side_effect=fake_email):
            resp = _client.post(
                "/vapi/send-outreach",
                json=_vapi_body({
                    "delivery_method": "email",
                    "prospect_email": "jane@example.com",
                    "contact_name": "Jane Doe",
                    "business_name": "Brand New Biz",
                }),
            )
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(captured["to"], "jane@example.com")
        self.assertIn("Jane Doe", captured["body"])
        self.assertIn("Brand New Biz", captured["body"])


if __name__ == "__main__":
    unittest.main()
