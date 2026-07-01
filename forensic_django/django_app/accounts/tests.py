from django.contrib.auth.models import User
from django.test import TestCase
from django.urls import reverse

from accounts.models import Notification


class NotificationTests(TestCase):
    def setUp(self):
        self.admin = User.objects.create_superuser("admin", "admin@example.com", "pass12345")
        self.user = User.objects.create_user("investigator", password="pass12345")
        self.user.profile.is_approved = True
        self.user.profile.save(update_fields=["is_approved"])
        self.other = User.objects.create_user("analyst", password="pass12345")
        self.other.profile.is_approved = True
        self.other.profile.role = "analyst"
        self.other.profile.save(update_fields=["is_approved", "role"])

    def test_registration_creates_pending_profile_and_notifies_admin(self):
        response = self.client.post(reverse("register"), {
            "username": "newuser",
            "first_name": "New",
            "last_name": "User",
            "email": "new@example.com",
            "password1": "StrongPass123",
            "password2": "StrongPass123",
            "role": "investigator",
        })
        self.assertEqual(response.status_code, 200)
        new_user = User.objects.get(username="newuser")
        self.assertFalse(new_user.profile.is_approved)
        self.assertTrue(Notification.objects.filter(user=self.admin, notification_type="user").exists())

    def test_user_cannot_read_another_users_notification(self):
        notification = Notification.objects.create(user=self.other, title="Secret", message="Private")
        self.client.login(username="investigator", password="pass12345")
        response = self.client.post(reverse("notification_read", args=[notification.id]))
        self.assertEqual(response.status_code, 404)

    def test_mark_all_read_marks_only_current_user_notifications(self):
        mine = Notification.objects.create(user=self.user, title="Mine", message="Mine")
        other = Notification.objects.create(user=self.other, title="Other", message="Other")
        self.client.login(username="investigator", password="pass12345")
        response = self.client.post(reverse("notifications_read_all"))
        self.assertEqual(response.status_code, 200)
        mine.refresh_from_db()
        other.refresh_from_db()
        self.assertTrue(mine.is_read)
        self.assertFalse(other.is_read)

    def test_admin_broadcast_to_analysts(self):
        self.client.login(username="admin", password="pass12345")
        response = self.client.post(reverse("admin_send_notification"), {
            "audience": "analysts",
            "title": "Briefing",
            "message": "Review queue",
            "priority": "normal",
        })
        self.assertEqual(response.status_code, 302)
        self.assertFalse(Notification.objects.filter(user=self.user, title="Briefing").exists())
        self.assertTrue(Notification.objects.filter(user=self.other, title="Briefing").exists())
