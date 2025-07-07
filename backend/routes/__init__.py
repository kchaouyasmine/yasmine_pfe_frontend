"""
Module routes pour ArticSpace
"""

# Import des blueprints pour un enregistrement facile
from .auth import auth_bp
from .articles import articles_bp
from .summarization import summarization_bp
from .chatbot import chatbot_bp
from .recommendations import recommendations_bp

# Liste de tous les blueprints
BLUEPRINTS = [
    auth_bp,
    articles_bp,
    summarization_bp,
    chatbot_bp,
    recommendations_bp
]

def register_blueprints(app):
    """
    Enregistre tous les blueprints sur l'application Flask
    """
    for blueprint in BLUEPRINTS:
        app.register_blueprint(blueprint)
        print(f"✅ Blueprint '{blueprint.name}' enregistré")

__all__ = [
    'auth_bp',
    'articles_bp', 
    'summarization_bp',
    'chatbot_bp',
    'recommendations_bp',
    'BLUEPRINTS',
    'register_blueprints'
]