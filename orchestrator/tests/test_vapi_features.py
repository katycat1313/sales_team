"""
Tests for VAPI voice agent features:
- Static SMS/email outreach templates
- Caller lookup (inbound call personalisation)
- Prospect mid-call enrichment (update_prospect_info)
- Buyer intent + emotional state logging (save_notes)
"""

import json
import os
import sys
import unittest
from unittest.mock import MagicMock, patch

# Make the orchestrator package importable without a running server.
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))


# ── SMS / Email tool stubs ────────────────────────────────────────────────────

class TestSMSTool(unittest.TestCase):
    """Unit tests for sms_tool helpers."""

    def test_normalize_us_phone_10_digits(self):
        from tools.sms_tool import _normalize_us_phone
        self.assertEqual(_normalize_us_phone("4045551234"), "+14045551234")

    def test_normalize_us_phone_11_digits(self):
        from tools.sms_tool import _normalize_us_phone
        self.assertEqual(_normalize_us_phone("14045551234"), "+14045551234")

    def test_normalize_us_phone_already_e164(self):
        from tools.sms_tool import _normalize_us_phone
        self.assertEqual(_normalize_us_phone("+14045551234"), "+14045551234")

    def test_normalize_us_phone_empty(self):
        from tools.sms_tool import _normalize_us_phone
        self.assertEqual(_normalize_us_phone(""), "")

    def test_is_configured_false_when_no_env(self):
        with patch.dict(os.environ, {}, clear=True):
            # Reimport to pick up cleared env
            import importlib
            import tools.sms_tool as sms_mod
            importlib.reload(sms_mod)
            self.assertFalse(sms_mod.is_configured())

    def test_send_sms_returns_error_when_unconfigured(self):
        from tools.sms_tool import send_sms
        with patch("tools.sms_tool.TWILIO_ACCOUNT_SID", ""), \
             patch("tools.sms_tool.TWILIO_AUTH_TOKEN", ""), \
             patch("tools.sms_tool.TWILIO_FROM_NUMBER", ""):
            result = send_sms(to_number="+14045551234", body="hi")
        self.assertFalse(result.get("sent"))
        self.assertIn("error", result)


class TestEmailTool(unittest.TestCase):
    """Unit tests for gmail_tool (SendGrid) helpers."""

    def test_is_configured_false_when_no_env(self):
        import importlib
        import tools.gmail_tool as gmail_mod
        with patch.dict(os.environ, {}, clear=True):
            importlib.reload(gmail_mod)
            self.assertFalse(gmail_mod.is_configured())

    def test_send_email_returns_error_when_unconfigured(self):
        from tools.gmail_tool import send_email
        with patch("tools.gmail_tool.SENDGRID_API_KEY", ""), \
             patch("tools.gmail_tool.GMAIL_ADDRESS", ""):
            result = send_email(to="test@example.com", subject="Hi", body="Hello")
        self.assertFalse(result.get("sent"))
        self.assertIn("error", result)

    def test_send_email_returns_error_for_invalid_address(self):
        from tools.gmail_tool import send_email
        with patch("tools.gmail_tool.SENDGRID_API_KEY", "SG.fake"), \
             patch("tools.gmail_tool.GMAIL_ADDRESS", "from@example.com"):
            result = send_email(to="not-an-email", subject="Hi", body="Hello")
        self.assertFalse(result.get("sent"))
        self.assertIn("error", result)


# ── Outreach template tests ───────────────────────────────────────────────────

class TestOutreachTemplates(unittest.TestCase):
    """Tests for the configurable static outreach message templates in vapi_tool."""

    def test_default_sms_template_contains_placeholders(self):
        import importlib
        import tools.vapi_tool as vt
        importlib.reload(vt)
        rendered = vt.OUTREACH_SMS_TEMPLATE.format(name="John", business_name="Acme Plumbing")
        self.assertIn("John", rendered)
        self.assertIn("Acme Plumbing", rendered)

    def test_default_email_subject_contains_placeholder(self):
        import importlib
        import tools.vapi_tool as vt
        importlib.reload(vt)
        subject = vt.OUTREACH_EMAIL_SUBJECT.format(name="John", business_name="Acme Plumbing")
        self.assertIn("Acme Plumbing", subject)

    def test_default_email_body_contains_placeholders(self):
        import importlib
        import tools.vapi_tool as vt
        importlib.reload(vt)
        body = vt.OUTREACH_EMAIL_BODY.format(name="John", business_name="Acme Plumbing")
        self.assertIn("John", body)
        self.assertIn("Acme Plumbing", body)

    def test_custom_sms_template_from_env(self):
        custom = "Hey {name} at {business_name} — call us!"
        with patch.dict(os.environ, {"OUTREACH_SMS_TEMPLATE": custom}):
            import importlib
            import tools.vapi_tool as vt
            importlib.reload(vt)
            rendered = vt.OUTREACH_SMS_TEMPLATE.format(name="Jane", business_name="Jane's Cafe")
        self.assertEqual(rendered, "Hey Jane at Jane's Cafe — call us!")

    def test_custom_email_subject_from_env(self):
        custom = "Hi {name} — {business_name} special offer"
        with patch.dict(os.environ, {"OUTREACH_EMAIL_SUBJECT": custom}):
            import importlib
            import tools.vapi_tool as vt
            importlib.reload(vt)
            subject = vt.OUTREACH_EMAIL_SUBJECT.format(name="Bob", business_name="Bob's HVAC")
        self.assertEqual(subject, "Hi Bob — Bob's HVAC special offer")


# ── System prompt content tests ───────────────────────────────────────────────

class TestSystemPrompts(unittest.TestCase):
    """Verify key instructions are present in the VAPI system prompts."""

    def setUp(self):
        import importlib
        import tools.vapi_tool as vt
        importlib.reload(vt)
        self.vt = vt

    def test_full_system_prompt_has_buyer_intent_section(self):
        self.assertIn("BUYER INTENT SIGNAL DETECTION", self.vt.FULL_SYSTEM_PROMPT)

    def test_full_system_prompt_has_emotional_intelligence_section(self):
        self.assertIn("EMOTIONAL INTELLIGENCE", self.vt.FULL_SYSTEM_PROMPT)

    def test_full_system_prompt_has_empathy_rule(self):
        self.assertIn("EMPATHY RULE", self.vt.FULL_SYSTEM_PROMPT)

    def test_incoming_call_guide_has_lookup_caller_instruction(self):
        self.assertIn("lookup_caller", self.vt.INCOMING_CALL_GUIDE)

    def test_incoming_call_guide_handles_known_caller(self):
        self.assertIn("found=true", self.vt.INCOMING_CALL_GUIDE)

    def test_incoming_call_guide_handles_new_caller(self):
        self.assertIn("found=false", self.vt.INCOMING_CALL_GUIDE)

    def test_onboarding_discovery_has_sheet_enrichment(self):
        self.assertIn("SHEET ENRICHMENT", self.vt.ONBOARDING_DISCOVERY)
        self.assertIn("update_prospect_info", self.vt.ONBOARDING_DISCOVERY)

    def test_call_control_rules_lists_new_tools(self):
        self.assertIn("lookup_caller", self.vt.CALL_CONTROL_RULES)
        self.assertIn("send_outreach_message", self.vt.CALL_CONTROL_RULES)
        self.assertIn("update_prospect_info", self.vt.CALL_CONTROL_RULES)


# ── VAPI tool definitions ─────────────────────────────────────────────────────

class TestAssistantTools(unittest.TestCase):
    """Verify _assistant_tools includes the new tool definitions."""

    def _get_tools(self):
        import importlib
        import tools.vapi_tool as vt
        importlib.reload(vt)
        return vt._assistant_tools("http://localhost:8000", "+15551234567", enable_transfer=False)

    def _tool_names(self):
        tools = self._get_tools()
        return [t.get("function", {}).get("name") for t in tools if "function" in t]

    def test_lookup_caller_tool_present(self):
        self.assertIn("lookup_caller", self._tool_names())

    def test_send_outreach_message_tool_present(self):
        self.assertIn("send_outreach_message", self._tool_names())

    def test_update_prospect_info_tool_present(self):
        self.assertIn("update_prospect_info", self._tool_names())

    def test_save_notes_has_emotional_state_field(self):
        tools = self._get_tools()
        save_notes = next(
            (t for t in tools if t.get("function", {}).get("name") == "save_notes"), None
        )
        self.assertIsNotNone(save_notes)
        props = save_notes["function"]["parameters"]["properties"]
        self.assertIn("emotional_state", props)

    def test_save_notes_has_buyer_intent_level_field(self):
        tools = self._get_tools()
        save_notes = next(
            (t for t in tools if t.get("function", {}).get("name") == "save_notes"), None
        )
        self.assertIsNotNone(save_notes)
        props = save_notes["function"]["parameters"]["properties"]
        self.assertIn("buyer_intent_level", props)

    def test_save_notes_has_discovered_info_field(self):
        tools = self._get_tools()
        save_notes = next(
            (t for t in tools if t.get("function", {}).get("name") == "save_notes"), None
        )
        self.assertIsNotNone(save_notes)
        props = save_notes["function"]["parameters"]["properties"]
        self.assertIn("discovered_info", props)

    def test_lookup_caller_server_url(self):
        tools = self._get_tools()
        lc = next((t for t in tools if t.get("function", {}).get("name") == "lookup_caller"), None)
        self.assertIsNotNone(lc)
        self.assertIn("/vapi/lookup-caller", lc["server"]["url"])

    def test_send_outreach_server_url(self):
        tools = self._get_tools()
        so = next((t for t in tools if t.get("function", {}).get("name") == "send_outreach_message"), None)
        self.assertIsNotNone(so)
        self.assertIn("/vapi/send-outreach", so["server"]["url"])

    def test_update_prospect_server_url(self):
        tools = self._get_tools()
        up = next((t for t in tools if t.get("function", {}).get("name") == "update_prospect_info"), None)
        self.assertIsNotNone(up)
        self.assertIn("/vapi/update-prospect-info", up["server"]["url"])


# ── Sheets tool tests ─────────────────────────────────────────────────────────

class TestSheetsTool(unittest.TestCase):
    """Tests for the Google Sheets sync tool."""

    def test_prospect_payload_maps_fields(self):
        from tools.sheets_tool import _prospect_payload
        p = {
            "business_name": "Acme",
            "phone": "4045551234",
            "location": "Atlanta GA",
            "niche": "plumbing",
            "owner_name": "Bob",
        }
        payload = _prospect_payload(p)
        self.assertEqual(payload["business_name"], "Acme")
        self.assertEqual(payload["phone"], "4045551234")
        self.assertEqual(payload["niche"], "plumbing")

    def test_push_prospect_sync_fails_gracefully_when_unconfigured(self):
        from tools.sheets_tool import push_prospect_sync
        with patch("tools.sheets_tool.SHEETS_WEBAPP_URL", ""), \
             patch("tools.sheets_tool.CREDS_PATH", "/nonexistent/path/creds.json"):
            result = push_prospect_sync({"business_name": "Test Co", "phone": "+14045551234"})
        self.assertFalse(result)


# ── Phone matching helper tests ───────────────────────────────────────────────

class TestPhoneMatching(unittest.TestCase):
    """Tests for the _phones_match helper in main.py."""

    def _phones_match(self, a, b):
        """Replicate the logic from main.py for isolated testing."""
        def _clean(p):
            return "".join(ch for ch in str(p or "") if ch.isdigit())[-10:]

        return bool(_clean(a) and _clean(b) and _clean(a) == _clean(b))

    def test_match_with_country_code(self):
        self.assertTrue(self._phones_match("+14045551234", "4045551234"))

    def test_match_plain_10_digits(self):
        self.assertTrue(self._phones_match("4045551234", "4045551234"))

    def test_no_match_different_numbers(self):
        self.assertFalse(self._phones_match("4045551234", "4045559999"))

    def test_no_match_empty(self):
        self.assertFalse(self._phones_match("", "4045551234"))


if __name__ == "__main__":
    unittest.main()
