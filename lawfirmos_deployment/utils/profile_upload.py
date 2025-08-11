import os
import uuid
from werkzeug.utils import secure_filename
from flask import current_app

ALLOWED_IMAGE_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif', 'webp'}

def allowed_image_file(filename):
    """Check if the file extension is allowed for images"""
    return '.' in filename and \
           filename.rsplit('.', 1)[1].lower() in ALLOWED_IMAGE_EXTENSIONS

def save_profile_image(file, user_id):
    """Save uploaded profile image and return the filename"""
    if not file or not allowed_image_file(file.filename):
        return None
    
    # Create secure filename
    filename = secure_filename(file.filename)
    file_extension = filename.rsplit('.', 1)[1].lower()
    
    # Generate unique filename
    unique_filename = f"profile_{user_id}_{uuid.uuid4().hex[:8]}.{file_extension}"
    
    # Ensure profile images directory exists
    profile_dir = os.path.join(current_app.config['UPLOAD_FOLDER'], 'profiles')
    os.makedirs(profile_dir, exist_ok=True)
    
    # Save file
    file_path = os.path.join(profile_dir, unique_filename)
    file.save(file_path)
    
    # Return relative path for database storage
    return f"profiles/{unique_filename}"

def get_profile_image_url(filename):
    """Get the full URL for a profile image"""
    if not filename:
        return None
    return f"/uploads/{filename}"