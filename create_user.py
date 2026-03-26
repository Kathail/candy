#!/usr/bin/env python3
"""
Create a user account.
Usage: python3 create_user.py <username> <email> <password> [--admin]
"""

import sys

from app import create_app, db
from app.models import User


def main():
    if len(sys.argv) < 4:
        print("Usage: python3 create_user.py <username> <email> <password> [--admin]")
        sys.exit(1)

    username = sys.argv[1]
    email = sys.argv[2]
    password = sys.argv[3]
    role = "admin" if "--admin" in sys.argv else "sales"

    app = create_app()
    with app.app_context():
        if User.query.filter_by(username=username).first():
            print(f"User '{username}' already exists.")
            sys.exit(0)

        user = User(username=username, email=email, role=role)
        user.set_password(password)
        db.session.add(user)
        db.session.commit()
        print(f"Created user '{username}' (role: {role})")


if __name__ == "__main__":
    main()
