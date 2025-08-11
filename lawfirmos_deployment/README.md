# LawFirmOS - Professional Legal Practice Management System

## Built by Taskdrip for Legal Professionals Worldwide

LawFirmOS is a comprehensive legal practice management platform that enables law firms and legal practitioners to seamlessly manage all their operations from one dashboard.

### Quick Start

1. **Extract Files**: Unzip this package to your server directory (e.g., `/var/www/lawfirmos`)

2. **Run Setup**: Execute the startup script
   ```bash
   chmod +x startup.sh
   ./startup.sh
   ```

3. **Configure Environment**: Copy `env_template.txt` to `.env` and update with your database credentials

4. **Start Application**:
   - Development: `python3 run.py`
   - Production: `gunicorn --bind 0.0.0.0:5000 wsgi:app`

### Default Admin Account
- Email: `admin@lawfirmos.com`
- Password: `admin123`
- **IMPORTANT**: Change this password immediately after first login!

### Key Features
- Role-based access (Admin, Team Member, Client)
- Project/case management with assignments
- Client communication and file sharing
- Team collaboration with messaging system
- Secure file upload and document management
- Professional dashboard for each user type

### Technical Stack
- **Backend**: Python Flask with SQLAlchemy ORM
- **Database**: PostgreSQL (production) / SQLite (development)
- **Frontend**: Bootstrap 5 with professional UI
- **Authentication**: Custom email/password authentication
- **File Storage**: Local file system with secure handling

### Support
- Email: taskdrip@gmail.com
- WhatsApp: +234 803 662 2568
- Telegram: https://t.me/taskdrip
- Instagram: https://www.instagram.com/taskdrip

### Deployment Guide
See `deployment_guide.md` for detailed production deployment instructions including:
- Server setup and configuration
- Database setup and migration
- SSL certificate installation
- Process management with Supervisor
- Nginx reverse proxy configuration

---

**LawFirmOS** - Streamlining legal practice management globally.
*Powered by Taskdrip*