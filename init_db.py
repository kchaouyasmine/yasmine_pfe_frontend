# init_db.py
import os
import sys

# Ajouter le répertoire du projet au path Python
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

# Créer l'application Flask
from flask import Flask
from backend.models.database import db
from config import Config

def create_app():
    """Créer l'application Flask pour l'initialisation DB"""
    app = Flask(__name__)
    app.config.from_object(Config)
    
    # Initialiser la base de données
    db.init_app(app)
    
    return app

def init_database():
    """Initialiser la base de données avec les tables et données de test"""
    app = create_app()
    
    with app.app_context():
        try:
            # Importer les modèles
            from backend.models.user import User
            from backend.models.article import Article
            db_path = app.config['SQLALCHEMY_DATABASE_URI'].replace('sqlite:///', '')
            os.makedirs(os.path.dirname(db_path), exist_ok=True)
            print(f"🛠️ Chemin DB: {db_path}")
            # Créer toutes les tables
            print("📄 Création des tables...")
            db.create_all()
            print("✅ Tables créées avec succès!")
            
            # Vérifier si l'utilisateur admin existe déjà
            existing_admin = User.query.filter_by(email='admin@articspace.com').first()
            
            if not existing_admin:
                print("👤 Création de l'utilisateur administrateur...")
                
                # Créer un utilisateur administrateur
                admin_user = User(
                    username='admin',
                    email='admin@articspace.com',
                    password_hash='admin123'
                )
                admin_user.first_name = 'Administrateur'
                admin_user.last_name = 'ArticSpace'
                admin_user.bio = 'Administrateur de la plateforme ArticSpace'

                # admin_user.set_password('admin123')
                
                db.session.add(admin_user)
                db.session.commit()
                
                print("✅ Utilisateur admin créé avec succès!")
                print("📧 Email: admin@articspace.com")
                print("🔐 Mot de passe: admin123")
            else:
                print("ℹ️ L'utilisateur admin existe déjà")
            
            # Créer un utilisateur de test
            existing_test = User.query.filter_by(email='test@articspace.com').first()
            
            if not existing_test:
                print("👤 Création de l'utilisateur de test...")
                
                test_user = User(
                    username='testuser',
                    email='test@articspace.com',
                    password_hash='test123'
                )
                test_user.first_name = 'Utilisateur'
                test_user.last_name = 'Test'
                test_user.bio = 'Utilisateur de test pour la plateforme'

                # test_user.set_password('test123')
                
                db.session.add(test_user)
                db.session.commit()
                
                print("✅ Utilisateur de test créé avec succès!")
                print("📧 Email: test@articspace.com")
                print("🔐 Mot de passe: test123")
            else:
                print("ℹ️ L'utilisateur de test existe déjà")
            
            print("\n" + "="*50)
            print("🎉 BASE DE DONNÉES INITIALISÉE AVEC SUCCÈS!")
            print("="*50)
            print("Vous pouvez maintenant démarrer l'application avec:")
            print("python app.py")
            print("\nComptes disponibles:")
            print("👑 Admin: admin@articspace.com / admin123")
            print("👤 Test:  test@articspace.com / test123")
            
        except Exception as e:
            print(f"❌ Erreur lors de l'initialisation de la base de données: {e}")
            import traceback
            traceback.print_exc()
            return False
    
    return True

def create_required_directories():
    """Créer les dossiers nécessaires au fonctionnement de l'application"""
    required_dirs = [
        'data',
        'data/chroma2',
        'data/pdfs',
        'data/temp_images',
        'frontend/static/uploads',
        'frontend/static/images',
        'frontend/static/images/avatars',
        'frontend/static/images/backgrounds'
    ]
    
    print("📁 Création des dossiers nécessaires...")
    
    for directory in required_dirs:
        try:
            os.makedirs(directory, exist_ok=True)
            print(f"✅ Dossier créé/vérifié: {directory}")
        except Exception as e:
            print(f"❌ Erreur création dossier {directory}: {e}")

if __name__ == '__main__':
    print("🚀 Initialisation d'ArticSpace...")
    print("="*50)
    
    # Créer les dossiers nécessaires
    create_required_directories()
    
    print("\n📄 Initialisation de la base de données...")
    print("-"*30)
    
    # Initialiser la base de données
    success = init_database()
    
    if success:
        print("\n🎉 Initialisation terminée avec succès!")
        print("Vous pouvez maintenant lancer l'application.")
    else:
        print("\n❌ Erreur lors de l'initialisation.")
        sys.exit(1)