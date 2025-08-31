#!/usr/bin/env python3
"""
Initialize super admin user for testing verification system
"""

from app import app, db
from models import User, ROLE_SUPER_ADMIN
import secrets

def create_super_admin():
    """Create a super admin user for testing"""
    
    with app.app_context():
        print("Creating super admin user...")
        
        # Check if super admin already exists
        existing_super_admin = User.query.filter_by(role=ROLE_SUPER_ADMIN).first()
        
        if existing_super_admin:
            print(f"Super admin already exists: {existing_super_admin.email}")
            return existing_super_admin
        
        # Create super admin user
        super_admin = User(
            id=secrets.token_urlsafe(16),
            email='superadmin@lawcolab.com',
            first_name='Super',
            last_name='Admin',
            role=ROLE_SUPER_ADMIN,
            law_firm_id=None,  # Super admin doesn't belong to any specific firm
            active=True,
            is_verified=True
        )
        
        # Set password for super admin
        super_admin.set_password('superadmin123')
        
        db.session.add(super_admin)
        db.session.commit()
        
        print(f"Super admin created successfully!")
        print(f"Email: {super_admin.email}")
        print(f"ID: {super_admin.id}")
        print(f"Role: {super_admin.role}")
        print("\nYou can now use this account to manage law firm verifications from the super admin dashboard.")
        
        return super_admin

if __name__ == "__main__":
    create_super_admin()