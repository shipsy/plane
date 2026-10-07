# Python imports
import json
import os
from unittest import mock

# Django imports
from django.test import SimpleTestCase, TestCase, override_settings
from django.utils import timezone

# Third party imports
from rest_framework.test import APIClient

# Module imports
from plane.api.serializers import StateSerializer as V1StateSerializer
from plane.app.serializers import WebhookSerializer
from plane.bgtasks.webhook_task import post_webhook
from plane.db.models import (
    IssueComment,
    Project,
    ProjectMember,
    State,
    User,
    Workspace,
    WorkspaceMember,
)
from plane.license.models import Instance
from plane.settings.redis import redis_instance
from plane.utils.html_sanitizer import sanitize_html
from plane.utils.url_validator import BlockedURLError, validate_outbound_url


class OutboundURLValidationTest(SimpleTestCase):
    """Webhook SSRF (VAPT 3.1)"""

    def test_internal_destinations_are_blocked(self):
        for url in [
            "http://10.0.0.1/",
            "http://172.16.0.1/",
            "http://192.168.0.1/",
            "http://169.254.169.254/latest/meta-data/",
            "http://127.0.0.1/",
            "http://127.1/",
            "http://0x7f000001/",
            "http://0.0.0.0/",
            "http://[::1]/",
            "http://[::ffff:a00:1]/",
            "http://localhost:80/",
            "http://api.localhost/",
            "ftp://8.8.8.8/",
        ]:
            with self.subTest(url=url):
                with self.assertRaises(BlockedURLError):
                    validate_outbound_url(url)

    def test_public_destination_is_allowed(self):
        self.assertEqual(validate_outbound_url("https://8.8.8.8/hook"), "8.8.8.8")

    def test_blocked_domains(self):
        with self.assertRaises(BlockedURLError):
            validate_outbound_url("https://app.plane.so/", blocked_domains=["plane.so"])

    def test_delivery_revalidates_destination(self):
        with mock.patch("plane.bgtasks.webhook_task.requests.post") as post:
            with self.assertRaises(BlockedURLError):
                post_webhook("http://169.254.169.254/", {}, {})
            post.assert_not_called()

    def test_delivery_does_not_follow_redirects(self):
        with mock.patch("plane.bgtasks.webhook_task.requests.post") as post:
            post_webhook("https://8.8.8.8/hook", {}, {})
            self.assertFalse(post.call_args.kwargs["allow_redirects"])

    def test_serializer_rejects_internal_url(self):
        serializer = WebhookSerializer(data={"url": "http://169.254.169.254/"})
        self.assertFalse(serializer.is_valid())
        self.assertIn("url", serializer.errors)


class HTMLSanitizerTest(SimpleTestCase):
    """Stored XSS (VAPT 3.7)"""

    def test_vapt_payload_is_removed(self):
        payload = ".<iframe srcdoc='&lt;body onload=prompt&lpar;1&rpar;&gt;'>."
        self.assertNotIn("iframe", sanitize_html(payload))

    def test_unsafe_markup_is_removed(self):
        for payload, forbidden in [
            ("<p>hi<script>alert(1)</script></p>", "script"),
            ('<img src="x" onerror="alert(1)">', "onerror"),
            ('<a href="javascript:alert(1)">x</a>', "javascript"),
            ('<a href=" javascript:alert(1)">x</a>', "javascript"),
            ("<svg onload=alert(1)></svg>", "onload"),
            ('<span style="background-image:url(javascript:x)">t</span>', "javascript"),
        ]:
            with self.subTest(payload=payload):
                self.assertNotIn(forbidden, sanitize_html(payload))

    def test_editor_markup_is_kept(self):
        for html in [
            '<p>Hi <mention-component id="abc" label="R" target="users" '
            'entity_identifier="u1" entity_name="user_mention"></mention-component></p>',
            '<image-component src="/api/assets/v2/x.png" id="1" width="35%"></image-component>',
            '<ul data-type="taskList"><li data-type="taskItem" data-checked="true"><p>do</p></li></ul>',
            '<pre><code class="language-python">x=1</code></pre>',
        ]:
            with self.subTest(html=html):
                cleaned = sanitize_html(html)
                for marker in ("mention-component", "image-component", "taskItem", "language-python"):
                    if marker in html:
                        self.assertIn(marker, cleaned)


class WorkspaceFixtureMixin:
    def create_member(self, email, role):
        user = User.objects.create(email=email, username=email.split("@")[0])
        WorkspaceMember.objects.create(workspace=self.workspace, member=user, role=role)
        ProjectMember.objects.create(project=self.project, member=user, role=role)
        return user

    def setUp(self):
        self.owner = User.objects.create(
            email="owner@shipsy.io", username="owner", is_superuser=True
        )
        self.workspace = Workspace.objects.create(
            name="Delta", slug="delta", owner=self.owner
        )
        self.project = Project.objects.create(
            name="TICKET", identifier="TICKET", workspace=self.workspace
        )


class UserSelfServiceFieldsTest(WorkspaceFixtureMixin, TestCase):
    """Self-promotion to super admin (P0.1)"""

    def test_access_control_fields_are_read_only(self):
        user = self.create_member("ops@shipsy.io", 15)
        client = APIClient()
        client.force_authenticate(user)
        response = client.patch(
            "/api/users/me/",
            {
                "is_super_admin": True,
                "hub_codes": ["ALL"],
                "employee_permissions": ["VIEW_NO_HUB_TICKETS_IN_PLANE"],
            },
            format="json",
        )
        self.assertEqual(response.status_code, 200)
        user.refresh_from_db()
        self.assertFalse(user.is_super_admin)
        self.assertNotEqual(user.hub_codes, ["ALL"])
        self.assertNotIn("VIEW_NO_HUB_TICKETS_IN_PLANE", user.employee_permissions or [])


class ProtectedStateTest(WorkspaceFixtureMixin, TestCase):
    """Protected states can be unprotected (VAPT 3.6)"""

    def setUp(self):
        super().setUp()
        self.state = State.objects.create(
            name="Closed",
            group="completed",
            project=self.project,
            workspace=self.workspace,
            is_protected=True,
        )

    def test_is_protected_is_read_only(self):
        serializer = V1StateSerializer(
            self.state, data={"is_protected": False}, partial=True
        )
        self.assertTrue(serializer.is_valid())
        serializer.save()
        self.state.refresh_from_db()
        self.assertTrue(self.state.is_protected)

    @override_settings(STATIC_API_TOKEN="service-token")
    def test_v1_patch_of_protected_state_is_forbidden(self):
        member = self.create_member("ops@shipsy.io", 15)
        client = APIClient()
        response = client.patch(
            f"/api/v1/workspaces/delta/projects/{self.project.id}/states/{self.state.id}/",
            {"name": "Renamed", "is_protected": False},
            format="json",
            HTTP_X_API_KEY="service-token",
            HTTP_X_ASSUME_ROLE=member.username,
        )
        self.assertEqual(response.status_code, 403)
        self.state.refresh_from_db()
        self.assertEqual(self.state.name, "Closed")
        self.assertTrue(self.state.is_protected)


class MemberEmailDisclosureTest(WorkspaceFixtureMixin, TestCase):
    """Members API discloses emails (VAPT 3.10)"""

    def list_members(self, user):
        client = APIClient()
        client.force_authenticate(user)
        response = client.get("/api/workspaces/delta/members/")
        self.assertEqual(response.status_code, 200)
        return response.json()

    def test_member_does_not_see_emails(self):
        member = self.create_member("ops@shipsy.io", 15)
        self.create_member("other@shipsy.io", 15)
        for row in self.list_members(member):
            self.assertNotIn("email", row["member"])

    def test_admin_sees_emails(self):
        admin = self.create_member("admin@shipsy.io", 20)
        self.assertTrue(all("email" in row["member"] for row in self.list_members(admin)))


class CommentSanitizationTest(WorkspaceFixtureMixin, TestCase):
    """Stored XSS is removed before comments are saved (VAPT 3.7)"""

    def test_comment_html_is_sanitized_on_save(self):
        from plane.db.models import Issue

        state = State.objects.create(
            name="Open", group="backlog", project=self.project,
            workspace=self.workspace, default=True,
        )
        issue = Issue.objects.create(
            name="Ticket", project=self.project, workspace=self.workspace, state=state
        )
        comment = IssueComment.objects.create(
            issue=issue,
            project=self.project,
            workspace=self.workspace,
            comment_html="<p>hi</p><iframe srcdoc='<body onload=prompt(1)>'></iframe>",
        )
        comment.refresh_from_db()
        self.assertEqual(comment.comment_html, "<p>hi</p>")


@override_settings(SKIP_ENV_VAR=False, STATIC_API_TOKEN="service-token")
class MagicLoginTrustTest(WorkspaceFixtureMixin, TestCase):
    """Ops Dashboard magic login (P0.3) and self registration (VAPT 3.2)"""

    def setUp(self):
        super().setUp()
        Instance.objects.create(
            instance_name="test",
            instance_id="test-instance",
            current_version="0.23.1",
            last_checked_at=timezone.now(),
            is_setup_done=True,
        )
        self.email = "ops__42@plane-shipsy.com"
        redis_instance().delete(f"magic_{self.email}")

    def generate(self, api_key, **claims):
        return APIClient().post(
            "/auth/magic-generate/",
            {"username": "ops__42", **claims},
            format="json",
            HTTP_X_API_KEY=api_key,
        )

    def sign_in(self, code, **form):
        return self.client.post(
            "/auth/magic-sign-in/",
            {"email": self.email, "code": code, **form},
            HTTP_USER_AGENT="plane/test",
        )

    def test_generate_requires_service_token(self):
        self.assertIn(self.generate("not-a-token").status_code, (401, 403))

    @mock.patch.dict(os.environ, {"ENABLE_SIGNUP": "0"})
    def test_new_employee_can_sign_in_with_signup_disabled(self):
        response = self.generate("service-token", workspace="delta")
        self.assertEqual(response.status_code, 200)
        self.sign_in(response.json()["token"], workspace="delta")
        self.assertTrue(User.objects.filter(email=self.email).exists())

    @mock.patch.dict(os.environ, {"ENABLE_SIGNUP": "0"})
    def test_untrusted_code_cannot_sign_up(self):
        # A code not issued through the service endpoint (e.g. space login)
        redis_instance().set(
            f"magic_{self.email}",
            json.dumps({
                "current_attempt": 0,
                "email": self.email,
                "token": "aaaa-bbbb-cccc",
                "username": "ops__42",
            }),
            ex=600,
        )
        response = self.sign_in("aaaa-bbbb-cccc", workspace="delta")
        self.assertIn("SIGNUP_DISABLED", response.url)
        self.assertFalse(User.objects.filter(email=self.email).exists())

    def test_server_claims_override_form_claims(self):
        Workspace.objects.create(name="Other", slug="other-org", owner=self.owner)
        response = self.generate(
            "service-token",
            workspace="delta",
            is_super_admin=False,
            hub_list=[{"code": "BLR", "name": "Bangalore"}],
        )
        self.sign_in(
            response.json()["token"],
            workspace="other-org",
            is_super_admin="true",
            hub_list=json.dumps([{"code": "ALL", "name": "All"}]),
        )
        user = User.objects.get(email=self.email)
        self.assertFalse(user.is_super_admin)
        self.assertEqual(user.hub_codes, ["BLR"])
        self.assertTrue(
            WorkspaceMember.objects.filter(member=user, workspace__slug="delta").exists()
        )
        self.assertFalse(
            WorkspaceMember.objects.filter(member=user, workspace__slug="other-org").exists()
        )
