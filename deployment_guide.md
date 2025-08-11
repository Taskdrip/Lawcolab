# LawFirmOS Deployment Guide for Contabo VPS

## System Requirements
- Ubuntu 20.04 LTS or higher
- Python 3.8+
- PostgreSQL 12+
- Nginx (recommended)
- SSL certificate (Let's Encrypt recommended)

## Quick Deployment Steps

### 1. Server Setup
```bash
# Update system
sudo apt update && sudo apt upgrade -y

# Install required packages
sudo apt install python3-pip python3-venv nginx postgresql postgresql-contrib -y

# Install supervisord for process management
sudo apt install supervisor -y
```

### 2. Database Setup
```bash
# Switch to postgres user
sudo -u postgres psql

# Create database and user
CREATE DATABASE lawfirmos_db;
CREATE USER lawfirmos_user WITH PASSWORD 'your_secure_password_here';
GRANT ALL PRIVILEGES ON DATABASE lawfirmos_db TO lawfirmos_user;
\q
```

### 3. Application Deployment
```bash
# Create application directory
sudo mkdir -p /var/www/lawfirmos
cd /var/www/lawfirmos

# Extract your application files here
# Upload and extract the deployment zip file

# Create virtual environment
python3 -m venv venv
source venv/bin/activate

# Install dependencies
pip install -r requirements.txt

# Set file permissions
sudo chown -R www-data:www-data /var/www/lawfirmos
sudo chmod -R 755 /var/www/lawfirmos
```

### 4. Environment Configuration
Create `/var/www/lawfirmos/.env` file:
```bash
DATABASE_URL=postgresql://lawfirmos_user:your_secure_password_here@localhost/lawfirmos_db
SESSION_SECRET=your_very_secure_session_secret_here_at_least_32_characters
FLASK_ENV=production
```

### 5. Database Migration
```bash
# Activate virtual environment
source /var/www/lawfirmos/venv/bin/activate

# Initialize database tables
cd /var/www/lawfirmos
python3 -c "from app import app, db; app.app_context().push(); db.create_all(); print('Database initialized')"
```

### 6. Gunicorn Configuration
Create `/var/www/lawfirmos/gunicorn.conf.py`:
```python
bind = "127.0.0.1:8000"
workers = 3
worker_class = "sync"
worker_connections = 1000
timeout = 30
keepalive = 2
max_requests = 1000
max_requests_jitter = 100
preload_app = True
```

### 7. Supervisor Configuration
Create `/etc/supervisor/conf.d/lawfirmos.conf`:
```ini
[program:lawfirmos]
command=/var/www/lawfirmos/venv/bin/gunicorn --config /var/www/lawfirmos/gunicorn.conf.py wsgi:app
directory=/var/www/lawfirmos
user=www-data
autostart=true
autorestart=true
redirect_stderr=true
stdout_logfile=/var/log/lawfirmos.log
environment=PATH="/var/www/lawfirmos/venv/bin"
```

### 8. Nginx Configuration
Create `/etc/nginx/sites-available/lawfirmos`:
```nginx
server {
    listen 80;
    server_name your-domain.com www.your-domain.com;

    location / {
        proxy_pass http://127.0.0.1:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }

    location /static {
        alias /var/www/lawfirmos/static;
        expires 30d;
        add_header Cache-Control "public, no-transform";
    }

    location /uploads {
        alias /var/www/lawfirmos/uploads;
        expires 30d;
        add_header Cache-Control "public, no-transform";
    }
}
```

### 9. SSL Certificate (Let's Encrypt)
```bash
# Install certbot
sudo apt install certbot python3-certbot-nginx -y

# Get SSL certificate
sudo certbot --nginx -d your-domain.com -d www.your-domain.com
```

### 10. Start Services
```bash
# Enable and start services
sudo systemctl enable nginx
sudo systemctl start nginx

sudo systemctl enable supervisor
sudo systemctl start supervisor

# Enable site
sudo ln -s /etc/nginx/sites-available/lawfirmos /etc/nginx/sites-enabled/
sudo nginx -t
sudo systemctl reload nginx

# Start application
sudo supervisorctl reread
sudo supervisorctl update
sudo supervisorctl start lawfirmos
```

## Admin Account Setup
After deployment, create an admin account:
```bash
cd /var/www/lawfirmos
source venv/bin/activate
python3 -c "
from app import app, db
from models import User
import uuid

with app.app_context():
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
"
```

## Monitoring and Maintenance

### Log Files
- Application logs: `/var/log/lawfirmos.log`
- Nginx access logs: `/var/log/nginx/access.log`
- Nginx error logs: `/var/log/nginx/error.log`

### Service Management
```bash
# Check application status
sudo supervisorctl status lawfirmos

# Restart application
sudo supervisorctl restart lawfirmos

# View logs
sudo tail -f /var/log/lawfirmos.log

# Restart nginx
sudo systemctl restart nginx
```

### Database Backup
```bash
# Create backup
sudo -u postgres pg_dump lawfirmos_db > backup_$(date +%Y%m%d_%H%M%S).sql

# Restore backup
sudo -u postgres psql lawfirmos_db < backup_file.sql
```

## Security Recommendations
1. Change default passwords immediately
2. Configure firewall (UFW)
3. Regular security updates
4. Monitor log files for suspicious activity
5. Use strong SESSION_SECRET
6. Enable HTTPS only in production

## Troubleshooting
- Check supervisor logs: `sudo supervisorctl tail lawfirmos`
- Check nginx logs: `sudo tail -f /var/log/nginx/error.log`
- Test database connection: `sudo -u postgres psql lawfirmos_db`
- Check permissions: `sudo chown -R www-data:www-data /var/www/lawfirmos`

For support, contact: taskdrip@gmail.com