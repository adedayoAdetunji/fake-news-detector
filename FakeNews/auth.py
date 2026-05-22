"""Authentication utilities for admin panel"""
import jwt
from functools import wraps
from datetime import datetime, timedelta
from flask import request, jsonify, current_app
try:
    from .models import AdminUser
except ImportError:
    from models import AdminUser


def generate_auth_token(user_id, expires_in=86400):
    """Generate JWT token for admin user"""
    try:
        payload = {
            'user_id': user_id,
            'exp': datetime.utcnow() + timedelta(seconds=expires_in),
            'iat': datetime.utcnow()
        }
        token = jwt.encode(
            payload,
            current_app.config['JWT_SECRET_KEY'],
            algorithm='HS256'
        )
        return token
    except Exception as e:
        return None


def verify_auth_token(token):
    """Verify JWT token and return user_id"""
    try:
        payload = jwt.decode(
            token,
            current_app.config['JWT_SECRET_KEY'],
            algorithms=['HS256']
        )
        user_id = payload.get('user_id')
        return user_id
    except jwt.ExpiredSignatureError:
        return None
    except jwt.InvalidTokenError:
        return None


def token_required(f):
    """Decorator to require valid JWT token"""
    @wraps(f)
    def decorated(*args, **kwargs):
        token = None
        
        # Check for token in headers
        if 'Authorization' in request.headers:
            auth_header = request.headers['Authorization']
            try:
                token = auth_header.split(' ')[1]
            except IndexError:
                return jsonify({'error': 'Invalid token format'}), 401
        
        # Check for token in cookies
        if not token:
            token = request.cookies.get('auth_token')
        
        if not token:
            return jsonify({'error': 'Token is missing'}), 401
        
        user_id = verify_auth_token(token)
        if not user_id:
            return jsonify({'error': 'Invalid or expired token'}), 401
        
        # Get the admin user
        admin = AdminUser.query.get(user_id)
        if not admin or not admin.is_active:
            return jsonify({'error': 'User not found or inactive'}), 401
        
        # Update last login
        admin.last_login = datetime.utcnow()
        try:
            try:
                from .models import db
            except ImportError:
                from models import db
            db.session.commit()
        except Exception:
            pass
        
        request.admin_user = admin
        return f(*args, **kwargs)
    
    return decorated


def admin_only(f):
    """Decorator to require super admin privileges"""
    @wraps(f)
    def decorated(*args, **kwargs):
        if not hasattr(request, 'admin_user'):
            return jsonify({'error': 'Not authenticated'}), 401
        
        if not request.admin_user.is_super_admin:
            return jsonify({'error': 'Insufficient privileges'}), 403
        
        return f(*args, **kwargs)
    
    return decorated
