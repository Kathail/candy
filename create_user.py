#!/usr/bin/env python3
"""
Manage user accounts from the command line.

Usage:
  python3 create_user.py create <username> <email> [--admin]
  python3 create_user.py reset-password <username>
  python3 create_user.py list
"""

import getpass
import sys

from app import create_app, db
from app.models import User


def main():
    app = create_app()

    if len(sys.argv) < 2:
        print(__doc__.strip())
        sys.exit(1)

    command = sys.argv[1]

    with app.app_context():
        from app.init_db import init_db
        init_db(app)

        if command == "create":
            create_user()
        elif command == "reset-password":
            reset_password()
        elif command == "list":
            list_users()
        else:
            print(f"Unknown command: {command}")
            print(__doc__.strip())
            sys.exit(1)


def create_user():
    if len(sys.argv) < 4:
        print("Usage: python3 create_user.py create <username> <email> [--admin]")
        sys.exit(1)

    username = sys.argv[2].strip()
    email = sys.argv[3].strip()
    role = "admin" if "--admin" in sys.argv else "sales"

    if User.query.filter_by(username=username).first():
        print(f"Error: Username '{username}' already exists.")
        sys.exit(1)

    if User.query.filter_by(email=email).first():
        print(f"Error: Email '{email}' already exists.")
        sys.exit(1)

    if "@" not in email:
        print("Error: Invalid email address.")
        sys.exit(1)

    password = getpass.getpass("Password (min 12 chars): ")
    if len(password) < 12:
        print("Error: Password must be at least 12 characters.")
        sys.exit(1)

    confirm = getpass.getpass("Confirm password: ")
    if password != confirm:
        print("Error: Passwords don't match.")
        sys.exit(1)

    user = User(username=username, email=email, role=role)
    user.set_password(password)
    db.session.add(user)
    db.session.commit()
    print(f"Created user '{username}' (role: {role})")


def reset_password():
    if len(sys.argv) < 3:
        print("Usage: python3 create_user.py reset-password <username>")
        sys.exit(1)

    username = sys.argv[2].strip()
    user = User.query.filter_by(username=username).first()

    if not user:
        print(f"Error: User '{username}' not found.")
        sys.exit(1)

    password = getpass.getpass("New password (min 12 chars): ")
    if len(password) < 12:
        print("Error: Password must be at least 12 characters.")
        sys.exit(1)

    confirm = getpass.getpass("Confirm password: ")
    if password != confirm:
        print("Error: Passwords don't match.")
        sys.exit(1)

    user.set_password(password)
    db.session.commit()
    print(f"Password reset for '{username}'.")


def list_users():
    users = User.query.order_by(User.username).all()
    if not users:
        print("No users found.")
        return

    print(f"{'Username':<20} {'Email':<30} {'Role':<8} {'Active'}")
    print("-" * 70)
    for u in users:
        active = "Yes" if getattr(u, 'is_active_user', True) else "No"
        print(f"{u.username:<20} {u.email:<30} {u.role:<8} {active}")


if __name__ == "__main__":
    main()
