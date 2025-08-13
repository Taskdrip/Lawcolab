"""
Production-ready Flask app runner for LawColab
"""
import os
from app import app

if __name__ == '__main__':
    # For production deployment
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port, debug=False)