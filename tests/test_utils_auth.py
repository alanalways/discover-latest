"""Tests for utils/auth.py"""

from utils.auth import collect_admin_emails, is_admin_user


def test_collect_admin_emails_includes_default():
    emails = collect_admin_emails()
    assert isinstance(emails, set)
    assert len(emails) >= 1  # At least the default email


def test_is_admin_user_by_email():
    admin_emails = {"admin@example.com"}
    user = {"email": "admin@example.com"}
    assert is_admin_user(user, admin_emails) is True


def test_is_admin_user_not_admin():
    admin_emails = {"admin@example.com"}
    user = {"email": "user@example.com"}
    assert is_admin_user(user, admin_emails) is False


def test_is_admin_user_by_metadata_role():
    admin_emails = set()
    user = {"email": "x@x.com", "user_metadata": {"role": "admin"}}
    assert is_admin_user(user, admin_emails) is True


def test_is_admin_user_by_app_metadata_is_admin():
    admin_emails = set()
    user = {"email": "x@x.com", "app_metadata": {"is_admin": True}}
    assert is_admin_user(user, admin_emails) is True


def test_is_admin_user_by_roles_list():
    admin_emails = set()
    user = {"email": "x@x.com", "user_metadata": {"roles": ["editor", "owner"]}}
    assert is_admin_user(user, admin_emails) is True
