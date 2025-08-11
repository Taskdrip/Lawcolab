# LawFirmOS

## Overview
LawFirmOS is a comprehensive legal practice management system built with Flask, designed to streamline law firm operations. It provides role-based access for administrators, team members, and clients, enabling efficient project management, client communication, and firm administration. The system includes features for law firm profile management, team coordination, client case tracking, document management, and public-facing firm presentation.

## User Preferences
Preferred communication style: Simple, everyday language.

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