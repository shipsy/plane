# Python imports
import time
from datetime import timedelta
from unittest import mock

# Django imports
from django.test import TestCase, override_settings
from django.utils import timezone

# Third party imports
from rest_framework.test import APIClient

# Module imports
from plane.bgtasks.session_cleanup_task import delete_expired_sessions
from plane.db.models import Session, User


@override_settings(STATIC_API_TOKEN="service-token")
class UserSessionRevokeTest(TestCase):
    """Ending Plane sessions when the user logs out of the Ops Dashboard (VAPT 3.8)"""

    url = "/api/v1/users/sessions/revoke/"

    def setUp(self):
        User.objects.create(email="admin@shipsy.io", username="admin", is_superuser=True)
        self.user = User.objects.create(email="ops@shipsy.io", username="ops")
        self.other = User.objects.create(email="other@shipsy.io", username="other")

    def login(self, user):
        client = APIClient()
        client.force_login(user)
        return client

    def revoke(self, email, api_key="service-token"):
        return APIClient().post(
            self.url, {"email": email}, format="json", HTTP_X_API_KEY=api_key
        )

    def test_revokes_all_sessions_of_the_user_only(self):
        self.login(self.user)
        self.login(self.user)
        self.login(self.other)

        response = self.revoke("OPS@shipsy.io ")

        self.assertEqual(response.status_code, 200)
        self.assertFalse(Session.objects.filter(user_id=str(self.user.id)).exists())
        self.assertEqual(Session.objects.filter(user_id=str(self.other.id)).count(), 1)

    def test_revoked_session_can_no_longer_be_used(self):
        client = self.login(self.user)
        self.assertEqual(client.get("/api/users/me/").status_code, 200)

        self.revoke(self.user.email)

        self.assertIn(client.get("/api/users/me/").status_code, (401, 403))

    def test_unknown_email_gets_the_same_response(self):
        response = self.revoke("nobody@shipsy.io")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {"status": "ok"})

    def test_requires_service_token(self):
        self.login(self.user)
        self.assertIn(self.revoke(self.user.email, api_key="wrong").status_code, (401, 403))
        self.assertTrue(Session.objects.filter(user_id=str(self.user.id)).exists())

    def test_email_is_required(self):
        self.assertEqual(self.revoke("").status_code, 400)


class SessionExpiryTest(TestCase):
    """30 minute sessions, renewed while the user is active"""

    def setUp(self):
        self.user = User.objects.create(email="ops@shipsy.io", username="ops")
        self.client = APIClient()
        self.client.force_login(self.user)

    def session_row(self):
        return Session.objects.get(user_id=str(self.user.id))

    def test_session_lifetime_is_30_minutes(self):
        self.client.get("/api/users/me/")
        remaining = self.session_row().expire_date - timezone.now()
        self.assertLessEqual(remaining, timedelta(minutes=30))
        self.assertGreater(remaining, timedelta(minutes=29))

    def test_expiry_is_renewed_only_after_half_the_lifetime(self):
        self.client.get("/api/users/me/")
        first_expiry = self.session_row().expire_date
        now = time.time()

        # Within 15 minutes: no write, expiry unchanged
        with mock.patch("plane.authentication.middleware.session.time.time", return_value=now + 60):
            self.client.get("/api/users/me/")
        self.assertEqual(self.session_row().expire_date, first_expiry)

        # After 15 minutes: expiry is pushed forward
        with mock.patch("plane.authentication.middleware.session.time.time", return_value=now + 16 * 60):
            self.client.get("/api/users/me/")
        self.assertGreater(self.session_row().expire_date, first_expiry)


class ExpiredSessionCleanupTest(TestCase):
    def test_deletes_only_expired_sessions(self):
        user = User.objects.create(email="ops@shipsy.io", username="ops")
        APIClient().force_login(user)
        APIClient().force_login(user)
        expired = Session.objects.filter(user_id=str(user.id)).first()
        Session.objects.filter(pk=expired.pk).update(
            expire_date=timezone.now() - timedelta(minutes=1)
        )

        delete_expired_sessions()

        self.assertFalse(Session.objects.filter(pk=expired.pk).exists())
        self.assertEqual(Session.objects.filter(user_id=str(user.id)).count(), 1)
