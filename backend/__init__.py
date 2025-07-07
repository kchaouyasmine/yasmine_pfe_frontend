"""
Module backend pour ArticSpace
"""

__version__ = "1.0.0"
__author__ = "ArticSpace Team"

# Import des modules principaux
from flask import Flask
from flask_login import LoginManager
from flask_cors import CORS
from flask_bcrypt import Bcrypt

# Import des modèles
from backend.models.database import db
from backend.models.user import User
from backend.models.article import Article
import os
# Import des services
from backend.services.rag_system import EnhancedMUragSystem
# from config import config  # Ajoute cette ligne en haut du fichier

def create_app(config_name='default'):
    """
    Factory pour créer l'application Flask
    """
    app = Flask(__name__)
    
    # Configuration de base
    app.config['SECRET_KEY'] = 'your-secret-key-here'  # À changer en production
    app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///../data/articspace.db'
    app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
    app.config['MAX_CONTENT_LENGTH'] = 50 * 1024 * 1024  # 50MB max file size

    # app = Flask(__name__)
    # app.config.from_object(config[config_name])

    app.config['RAG_PDF_FOLDER'] = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'data', 'pdfs')
    app.config['RAG_CHROMA_PATH'] = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'data', 'chroma2')
    app.config['RAG_LEXICAL_INDEX'] = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'data', 'lexical_index_1.pkl')
    app.config['RAG_CONVERSATION_MEMORY'] = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'data', 'conversation_memory.pkl')
    # Initialiser les extensions
    db.init_app(app)
    CORS(app, origins=['http://localhost:3000'])  # Pour React en développement
    bcrypt = Bcrypt(app)
    
    # Configurer Flask-Login
    login_manager = LoginManager()
    login_manager.init_app(app)
    login_manager.login_view = 'auth.login'
    login_manager.login_message = 'Veuillez vous connecter pour accéder à cette page.'
    
    @login_manager.user_loader
    def load_user(user_id):
        return User.query.get(int(user_id))
    
    # Enregistrer les blueprints
    from backend.routes.auth import auth_bp
    try:
        from backend.routes.articles import articles_bp
        app.register_blueprint(articles_bp, url_prefix='/articles')
    except ImportError:
        pass
    try:
        from backend.routes.summarization import summarization_bp
        app.register_blueprint(summarization_bp)
    except ImportError:
        pass
    try:
        from backend.routes.chatbot import chatbot_bp
        app.register_blueprint(chatbot_bp, url_prefix='/chatbot')
    except ImportError:
        pass
    try:
        from backend.routes.recommendations import recommendations_bp
        app.register_blueprint(recommendations_bp)
    except ImportError:
        pass
    try:
        from backend.routes.dashboard import dashboard_bp
        app.register_blueprint(dashboard_bp, url_prefix='/dashboard')
    except ImportError:
        pass
    app.register_blueprint(auth_bp, url_prefix='/auth')
    
    # Créer les tables si elles n'existent pas
    with app.app_context():
        db.create_all()
    
    return app