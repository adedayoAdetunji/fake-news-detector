import os
from datetime import timedelta

DEFAULT_SQLITE_URI = 'sqlite:///fake_news_detector.db'
EXAMPLE_DATABASE_URL = 'mysql+pymysql://root:password@localhost:3306/fake_news_detector'


def get_database_uri(default=DEFAULT_SQLITE_URI):
    """Return a usable database URI, ignoring the copied example placeholder."""
    database_url = os.environ.get('DATABASE_URL', '').strip()
    if not database_url or database_url == EXAMPLE_DATABASE_URL:
        return default
    return database_url


class Config:
    """Base configuration"""
    # Flask
    SECRET_KEY = os.environ.get('SECRET_KEY') or 'dev-key-change-in-production'
    
    # Database
    SQLALCHEMY_DATABASE_URI = get_database_uri()
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    SQLALCHEMY_ECHO = False
    
    # JWT
    JWT_SECRET_KEY = os.environ.get('JWT_SECRET_KEY') or 'jwt-secret-key'
    JWT_ACCESS_TOKEN_EXPIRES = timedelta(hours=24)
    
    # File upload
    MAX_CONTENT_LENGTH = 16 * 1024 * 1024  # 16MB


class DevelopmentConfig(Config):
    """Development configuration"""
    DEBUG = True
    SQLALCHEMY_ECHO = False


class ProductionConfig(Config):
    """Production configuration"""
    DEBUG = False
    SQLALCHEMY_DATABASE_URI = get_database_uri(EXAMPLE_DATABASE_URL)


class TestingConfig(Config):
    """Testing configuration"""
    TESTING = True
    SQLALCHEMY_DATABASE_URI = 'sqlite:///:memory:'


config = {
    'development': DevelopmentConfig,
    'production': ProductionConfig,
    'testing': TestingConfig,
    'default': DevelopmentConfig
}
