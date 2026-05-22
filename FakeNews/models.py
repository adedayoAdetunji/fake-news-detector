from datetime import datetime
from flask_sqlalchemy import SQLAlchemy
from werkzeug.security import generate_password_hash, check_password_hash

db = SQLAlchemy()


class PredictionHistory(db.Model):
    """Model for storing prediction history"""
    __tablename__ = 'prediction_history'
    
    id = db.Column(db.Integer, primary_key=True)
    timestamp = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    source_type = db.Column(db.String(10), nullable=False)  # 'url' or 'text'
    input_text = db.Column('query', db.Text, nullable=False)
    analyzed_text = db.Column(db.Text, nullable=True)
    status = db.Column(db.String(20), nullable=False)  # 'Real', 'Fake', 'Unreliable'
    confidence_score = db.Column(db.Float, nullable=False)
    domain = db.Column(db.String(255), nullable=True)
    risk_score = db.Column(db.Integer, nullable=True)
    matched_tokens = db.Column(db.JSON, nullable=True)  # JSON array
    clickbait_matches = db.Column(db.JSON, nullable=True)  # JSON array
    summary = db.Column(db.Text, nullable=True)
    model_results = db.Column(db.JSON, nullable=False)  # JSON array of model results
    
    def to_dict(self):
        """Convert model to dictionary"""
        return {
            'id': self.id,
            'timestamp': self.timestamp.strftime('%Y-%m-%d %H:%M:%S UTC'),
            'source_type': self.source_type,
            'query': self.input_text,
            'analyzed_text': self.analyzed_text,
            'status': self.status,
            'confidence_score': self.confidence_score,
            'domain': self.domain,
            'risk_score': self.risk_score,
            'matched_tokens': self.matched_tokens,
            'clickbait_matches': self.clickbait_matches,
            'summary': self.summary,
            'model_results': self.model_results,
        }


class AdminUser(db.Model):
    """Model for storing admin users"""
    __tablename__ = 'admin_users'
    
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False, index=True)
    email = db.Column(db.String(120), unique=True, nullable=False, index=True)
    password_hash = db.Column(db.String(255), nullable=False)
    is_active = db.Column(db.Boolean, default=True)
    is_super_admin = db.Column(db.Boolean, default=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    last_login = db.Column(db.DateTime, nullable=True)
    
    def set_password(self, password):
        """Hash and set password"""
        self.password_hash = generate_password_hash(password)
    
    def check_password(self, password):
        """Check if provided password matches hash"""
        return check_password_hash(self.password_hash, password)
    
    def to_dict(self):
        """Convert model to dictionary"""
        return {
            'id': self.id,
            'username': self.username,
            'email': self.email,
            'is_active': self.is_active,
            'is_super_admin': self.is_super_admin,
            'created_at': self.created_at.strftime('%Y-%m-%d %H:%M:%S UTC'),
            'last_login': self.last_login.strftime('%Y-%m-%d %H:%M:%S UTC') if self.last_login else None,
        }


class User(db.Model):
    """Model for regular application users."""
    __tablename__ = 'users'

    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False, index=True)
    email = db.Column(db.String(120), unique=True, nullable=False, index=True)
    password_hash = db.Column(db.String(255), nullable=False)
    is_active = db.Column(db.Boolean, default=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    last_login = db.Column(db.DateTime, nullable=True)

    def set_password(self, password):
        self.password_hash = generate_password_hash(password)

    def check_password(self, password):
        return check_password_hash(self.password_hash, password)

    def to_dict(self):
        return {
            'id': self.id,
            'username': self.username,
            'email': self.email,
            'is_active': self.is_active,
            'created_at': self.created_at.strftime('%Y-%m-%d %H:%M:%S UTC'),
            'last_login': self.last_login.strftime('%Y-%m-%d %H:%M:%S UTC') if self.last_login else None,
        }


class FakeNewsReport(db.Model):
    """Model for storing fake news reports"""
    __tablename__ = 'fake_news_reports'
    
    id = db.Column(db.Integer, primary_key=True)
    timestamp = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    article_url = db.Column(db.String(500), nullable=True)
    article_title = db.Column(db.String(255), nullable=True)
    article_text = db.Column(db.Text, nullable=True)
    reporter_email = db.Column(db.String(120), nullable=True)
    reason = db.Column(db.Text, nullable=False)
    status = db.Column(db.String(20), default='pending')  # pending, reviewed, verified
    admin_notes = db.Column(db.Text, nullable=True)
    
    def to_dict(self):
        """Convert model to dictionary"""
        return {
            'id': self.id,
            'timestamp': self.timestamp.strftime('%Y-%m-%d %H:%M:%S UTC'),
            'article_url': self.article_url,
            'article_title': self.article_title,
            'reporter_email': self.reporter_email,
            'reason': self.reason,
            'status': self.status,
            'admin_notes': self.admin_notes,
        }
