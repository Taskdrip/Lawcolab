# LawFirmOS

## Overview
LawFirmOS is a comprehensive legal practice management system built with Flask, designed to streamline law firm operations. It provides role-based access for administrators, team members, and clients, enabling efficient project management, client communication, and firm administration. The system includes features for law firm profile management, team coordination, client case tracking, document management, and public-facing firm presentation.

## User Preferences
Preferred communication style: Simple, everyday language.
Profile image preferences: Beautiful square profile images with clear role-based icons for visual distinction between admins, clients, and lawyers.
UI Design preference: Clean, simple white background interfaces - avoid dark themes.

## Recent Changes
- **August 13, 2025**: MULTI-TIERED CHAT SYSTEM - Implemented comprehensive messaging with law firm-super admin support chat, project-based team isolation, super admin broadcast messaging, verified badges, and seamless subscription requests with pricing ($70/1mo, $190/3mo, $400/6mo, $750/1yr)
- **August 13, 2025**: CSS STYLING FIXES - Fixed blurry/faint text appearance with aggressive CSS overrides ensuring all text appears bright and crisp with maximum contrast
- **August 13, 2025**: SUPER ADMIN SYSTEM - Added platform-wide super admin role with law firm management capabilities, created super admin dashboard, and granted law firm admin creation privileges
- **August 11, 2025**: DEPLOYMENT READY - Created comprehensive About Us and Contact Us pages for Taskdrip with full team profiles, Abraham's story, social media integration
- **August 11, 2025**: Added professional About Us page featuring Abraham (Founder/CEO - lawyer since 2015, tech entrepreneur) and complete team including Wiam Tahbat (Co-Founder/COO)
- **August 11, 2025**: Implemented Contact Us page with inquiry forms, WhatsApp contact (+234 803 662 2568), social media links (Telegram, Instagram, TikTok, YouTube: https://www.youtube.com/@Taskdriper)
- **August 11, 2025**: Created deployment package (LawFirmOS_Deployment_Package.tar.gz) ready for Contabo VPS hosting with complete setup scripts
- **August 11, 2025**: Fixed all routing issues - About and Contact pages fully functional with professional content and Abraham's profile photo
- **August 11, 2025**: Generated deployment documentation, startup scripts, environment templates for production hosting
- Fixed navigation links for Projects and Clients pages with full functionality
- Added project assignment system allowing admins/lawyers to assign team members and clients to projects
- Implemented project-based chat system for team collaboration and client communication
- Enhanced project detail pages with file upload capabilities and user management
- Added comprehensive messaging system between all users (lawyers, admins, clients)
- Fixed all template routing errors and database relationship issues
- Navigation includes Projects, Clients, and Messages for seamless workflow
- Project chat allows real-time communication between assigned team members and clients
- File management system fully operational with secure uploads and organization
- Admin account: admin@lawfirmos.com / admin123 (fully functional with all features)
- Complete About Us and Contact Us pages with team profiles, social media integration, and professional content
- Production-ready deployment package with setup scripts and comprehensive documentation
- Contact information: taskdrip@gmail.com, WhatsApp +234 803 662 2568, social media links integrated

## System Architecture

### Frontend Architecture
- **Template Engine**: Jinja2 templates with Flask
- **CSS Framework**: Bootstrap 5 for responsive design
- **JavaScript**: Vanilla JavaScript with Bootstrap components
- **Static Assets**: Organized CSS, JavaScript, and upload handling
- **Responsive Design**: Mobile-first approach with professional legal industry styling

### Backend Architecture
- **Web Framework**: Flask with modular blueprint structure
- **Database ORM**: SQLAlchemy with declarative base model
- **Authentication**: Custom Replit Auth integration with Flask-Login
- **File Upload**: Werkzeug secure file handling with configurable upload limits
- **Role-Based Access**: Decorator-based authorization system (admin, team_member, client)
- **Session Management**: Flask sessions with proxy fix for deployment

### Database Design
- **User Management**: Centralized user model with role-based permissions
- **Project Structure**: Projects with assignments linking users and cases
- **Client Relations**: Client notes, project assignments, and profile management
- **File Storage**: Project file associations with secure upload handling
- **Firm Data**: Law firm profile information and public page content

### Blueprint Organization
- **Admin Blueprint**: Firm profile management and team administration
- **Client Blueprint**: Client profile viewing and note management
- **Dashboard Blueprint**: Role-specific dashboards with metrics and recent activity
- **Project Blueprint**: Case/project management with file uploads and collaboration
- **Team Blueprint**: Team member listing and management
- **Public Blueprint**: Public-facing law firm landing pages

### Security & Authorization
- **Role Hierarchy**: Three-tier system (admin > team_member > client)
- **Route Protection**: Decorator-based access control with 403 error handling
- **File Security**: Secure filename handling and type validation
- **Session Security**: Secret key configuration and permanent sessions

## External Dependencies

### Core Dependencies
- **Flask**: Web application framework
- **Flask-SQLAlchemy**: Database ORM integration
- **Flask-Login**: User session management
- **Flask-Dance**: OAuth integration framework
- **Werkzeug**: WSGI utilities and secure file handling

### Frontend Dependencies
- **Bootstrap 5**: CSS framework via CDN
- **Font Awesome 6**: Icon library via CDN
- **Custom CSS**: Professional legal industry styling

### Database Integration
- **SQLAlchemy**: ORM with support for SQLite (easily upgradeable to PostgreSQL)
- **Database URL**: Environment-based configuration
- **Connection Pooling**: Pre-ping and recycle configuration for production

### Authentication Services
- **Replit Auth**: OAuth-based authentication system
- **JWT**: Token handling for secure authentication
- **Custom Storage**: Database-backed OAuth token storage

### File Management
- **Local Storage**: Configurable upload directory
- **File Validation**: Type and size restrictions (16MB limit)
- **Secure Processing**: Filename sanitization and validation

### Environment Configuration
- **SESSION_SECRET**: Session encryption key
- **DATABASE_URL**: Database connection string
- **Upload Configuration**: File handling and storage settings