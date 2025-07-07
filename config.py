import os
from datetime import timedelta

class Config:
    # Configuration Flask
    SECRET_KEY = os.environ.get('SECRET_KEY') or 'votre-clé-secrète-très-sécurisée-pour-production'
    
    # Base de données
    # SQLALCHEMY_DATABASE_URI = os.environ.get('DATABASE_URL') or 'sqlite:///articspace.db'
    basedir = os.path.abspath(os.path.dirname(__file__))
    SQLALCHEMY_DATABASE_URI = os.environ.get('DATABASE_URL') or \
    'sqlite:///' + os.path.join(basedir, 'data', 'articspace.db')
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    
    # Uploads
    UPLOAD_FOLDER = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'frontend', 'static', 'uploads')
    MAX_CONTENT_LENGTH = 50 * 1024 * 1024  # 50MB max file size
    ALLOWED_EXTENSIONS = {'pdf', 'txt', 'doc', 'docx'}
    
    # Session
    PERMANENT_SESSION_LIFETIME = timedelta(days=7)
    SESSION_COOKIE_SECURE = False  # True en production avec HTTPS
    SESSION_COOKIE_HTTPONLY = True
    SESSION_COOKIE_SAMESITE = 'Lax'
    
    # RAG System - Chemins vers tes données existantes
    RAG_PDF_FOLDER = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'data', 'pdfs')
    RAG_CHROMA_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'data', 'chroma2')
    RAG_LEXICAL_INDEX = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'data', 'lexical_index_1.pkl')
    RAG_CONVERSATION_MEMORY = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'data', 'conversation_memory.pkl')
    RAG_TEMP_IMAGES = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'data', 'temp_images')
    
    # Modèles IA
    OLLAMA_BASE_URL = os.environ.get('OLLAMA_BASE_URL') or 'http://localhost:11434'
    DEFAULT_SUMMARIZATION_MODEL = 'DeepSeek-R1'
    DEFAULT_VISION_MODEL = 'granite3.2-vision'
    DEFAULT_VERIFICATION_MODEL = 'nous-hermes'
    
    # Langues supportées
    SUPPORTED_LANGUAGES = {
        'fr': 'Français',
        'en': 'English', 
        'de': 'Deutsch',
        'es': 'Español',
        'it': 'Italiano'
    }
    
    # Pagination
    ARTICLES_PER_PAGE = 12
    RECOMMENDATIONS_PER_PAGE = 10
    
    # Cache
    CACHE_TYPE = 'simple'
    CACHE_DEFAULT_TIMEOUT = 300
    
    # Rate limiting
    RATELIMIT_STORAGE_URL = 'memory://'
    RATELIMIT_DEFAULT = '100 per hour'
    
    # Email (optionnel pour notifications)
    MAIL_SERVER = os.environ.get('MAIL_SERVER')
    MAIL_PORT = int(os.environ.get('MAIL_PORT') or 587)
    MAIL_USE_TLS = os.environ.get('MAIL_USE_TLS', 'true').lower() in ['true', 'on', '1']
    MAIL_USERNAME = os.environ.get('MAIL_USERNAME')
    MAIL_PASSWORD = os.environ.get('MAIL_PASSWORD')
    
    # Palette de couleurs ArticSpace
    BRAND_COLORS = {
        'light_blue': '#d2edff',
        'medium_blue': '#91c3fe', 
        'dark_blue': '#2360a6',
        'light_pink': '#ec709a',
        'medium_pink': '#e998bb',
        'light_green': '#a4e473'
    }

class DevelopmentConfig(Config):
    DEBUG = True
    TESTING = False

class ProductionConfig(Config):
    DEBUG = False
    TESTING = False
    SESSION_COOKIE_SECURE = True
    
    # Configuration de sécurité renforcée pour la production
    SQLALCHEMY_DATABASE_URI = os.environ.get('DATABASE_URL') or 'postgresql://user:password@localhost/articspace_prod'

class TestingConfig(Config):
    TESTING = True
    SQLALCHEMY_DATABASE_URI = 'sqlite:///:memory:'
    WTF_CSRF_ENABLED = False

# Configuration par défaut
config = {
    'development': DevelopmentConfig,
    'production': ProductionConfig,
    'testing': TestingConfig,
    'default': DevelopmentConfig
}