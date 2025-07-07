"""
Module modèles pour ArticSpace
"""

from .database import db
from .user import User
from .article import Article

# Fonction utilitaire pour créer toutes les tables
def create_all_tables(app):
    """
    Crée toutes les tables de la base de données
    """
    with app.app_context():
        db.create_all()
        print("✅ Toutes les tables de base de données ont été créées")

# Fonction utilitaire pour supprimer toutes les tables (développement seulement)
def drop_all_tables(app):
    """
    Supprime toutes les tables de la base de données
    ATTENTION: Utiliser seulement en développement!
    """
    with app.app_context():
        db.drop_all()
        print("⚠️ Toutes les tables de base de données ont été supprimées")

# Fonction pour initialiser des données de test
def create_test_data(app):
    """
    Crée des données de test pour le développement
    """
    with app.app_context():
        # Vérifier si des utilisateurs existent déjà
        if User.query.first():
            print("📊 Données de test déjà présentes")
            return
        
        # Créer un utilisateur de test
        test_user = User(
            username='testuser',
            email='test@articspace.com',
            university='Test University',
            field='Computer Science'
        )
        test_user.set_password('password123')
        
        db.session.add(test_user)
        db.session.commit()
        
        print("✅ Utilisateur de test créé: test@articspace.com / password123")

__all__ = [
    'db',
    'User',
    'Article',
    'create_all_tables',
    'drop_all_tables',
    'create_test_data'
]