#!/bin/bash

# LawFirmOS Startup Script for Production
# Make executable with: chmod +x startup.sh

echo "=== LawFirmOS Production Startup ==="

# Check if virtual environment exists
if [ ! -d "venv" ]; then
    echo "Creating virtual environment..."
    python3 -m venv venv
fi

# Activate virtual environment
echo "Activating virtual environment..."
source venv/bin/activate

# Install/upgrade dependencies
echo "Installing dependencies..."
pip install --upgrade pip
pip install flask flask-sqlalchemy flask-login flask-wtf wtforms email-validator werkzeug gunicorn psycopg2-binary python-dotenv pillow

# Check if .env file exists
if [ ! -f ".env" ]; then
    echo "WARNING: .env file not found! Please copy env_template.txt to .env and configure it."
    echo "Continuing with default environment..."
fi

# Initialize database tables
echo "Initializing database tables..."
python3 -c "from app import app, db; app.app_context().push(); db.create_all(); print('Database tables created successfully')"

# Create admin user if it doesn't exist
echo "Creating admin user..."
python3 -c "
import uuid
from app import app, db
from models import User

with app.app_context():
    admin = User.query.filter_by(email='admin@lawfirmos.com').first()
    if not admin:
        admin = User()
        admin.id = str(uuid.uuid4())
        admin.first_name = 'Admin'
        admin.last_name = 'User'
        admin.email = 'admin@lawfirmos.com'
        admin.role = 'admin'
        admin.set_password('admin123')
        admin.active = True
        
        db.session.add(admin)
        db.session.commit()
        print('Admin account created: admin@lawfirmos.com / admin123')
    else:
        print('Admin account already exists')
"

echo ""
echo "=== Startup Complete ==="
echo "Admin Login: admin@lawfirmos.com / admin123"
echo ""
echo "To start the application:"
echo "  Development: python3 run.py"
echo "  Production:  gunicorn --bind 0.0.0.0:5000 wsgi:app"
echo ""
echo "Application will be available at: http://your-domain.com:5000"
echo "Remember to change the admin password after first login!"
echo ""