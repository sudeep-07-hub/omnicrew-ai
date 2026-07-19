#!/usr/bin/env python3
"""
OmniCrew AI — Seed test user accounts in Firebase Authentication.

Creates one account per staff role with custom claims (role, gate).
Idempotent: skips accounts that already exist.

Usage:
    # First, authenticate with Google Cloud:
    gcloud auth application-default login

    # Then run:
    python scripts/seed_users.py
"""

from __future__ import annotations

import firebase_admin
from firebase_admin import auth

# Initialize Firebase Admin SDK (uses Application Default Credentials).
if not firebase_admin._apps:
    firebase_admin.initialize_app()

TEST_USERS = [
    {
        "email": "medic@omnicrew.test",
        "password": "OmniMedic2026!",
        "display_name": "Test Medic",
        "claims": {"role": "medic", "gate": "Gate-A"},
    },
    {
        "email": "usher@omnicrew.test",
        "password": "OmniUsher2026!",
        "display_name": "Test Usher",
        "claims": {"role": "usher", "gate": "Gate-C"},
    },
    {
        "email": "security@omnicrew.test",
        "password": "OmniSecurity2026!",
        "display_name": "Test Security",
        "claims": {"role": "security", "gate": "Gate-B"},
    },
    {
        "email": "cmdctr@omnicrew.test",
        "password": "OmniCommand2026!",
        "display_name": "Test Command Center",
        "claims": {"role": "command-center", "gate": "HQ"},
    },
]


def seed_users() -> None:
    """Create test users and set their custom claims."""
    for user_data in TEST_USERS:
        email = user_data["email"]
        try:
            # Check if user already exists.
            existing = auth.get_user_by_email(email)
            print(f"  ✓ {email} already exists (uid={existing.uid})")
            # Always update claims in case they changed.
            auth.set_custom_user_claims(existing.uid, user_data["claims"])
            print(f"    → Updated claims: {user_data['claims']}")
        except auth.UserNotFoundError:
            # Create the user.
            user = auth.create_user(
                email=email,
                password=user_data["password"],
                display_name=user_data["display_name"],
                email_verified=True,
            )
            auth.set_custom_user_claims(user.uid, user_data["claims"])
            print(f"  ✓ Created {email} (uid={user.uid})")
            print(f"    → Claims: {user_data['claims']}")


if __name__ == "__main__":
    print("=" * 60)
    print(" OmniCrew AI — Seeding Test Users")
    print("=" * 60)
    seed_users()
    print()
    print("Done! Test credentials:")
    print()
    for u in TEST_USERS:
        print(f"  {u['email']} / {u['password']}  → {u['claims']['role']}")
    print()
