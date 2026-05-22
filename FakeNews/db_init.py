"""Database initialization script."""
import os
import sys

# Add this package directory to the import path for direct script execution.
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

try:
    from .app import app, db
    from .models import AdminUser
except ImportError:
    from app import app, db
    from models import AdminUser


def init_db():
    """Initialize database tables and create the default admin user."""
    with app.app_context():
        print("Creating database tables...")
        db.create_all()
        print("OK: Database tables created successfully")

        admin = AdminUser.query.filter_by(username='admin').first()
        if not admin:
            print("\nCreating default admin user...")
            admin = AdminUser(
                username=os.environ.get('ADMIN_USERNAME', 'admin'),
                email=os.environ.get('ADMIN_EMAIL', 'admin@fakenewsdetector.local'),
                is_active=True,
                is_super_admin=True,
            )
            admin.set_password(os.environ.get('ADMIN_PASSWORD', 'admin123'))
            db.session.add(admin)
            db.session.commit()
            print("OK: Default admin user created")
            print(f"  Username: {admin.username}")
            print("  Password: configured from ADMIN_PASSWORD or default admin123")
            print("  Please change the password after first login.")
        else:
            print("OK: Admin user already exists")

        print("\nDatabase initialization complete!")


if __name__ == '__main__':
    init_db()
