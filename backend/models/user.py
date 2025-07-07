from flask_sqlalchemy import SQLAlchemy
from flask_login import UserMixin
from werkzeug.security import generate_password_hash, check_password_hash
from datetime import datetime
import uuid

from .database import db, TimestampMixin, SoftDeleteMixin, user_favorites, user_following

class User(UserMixin, db.Model, TimestampMixin, SoftDeleteMixin):
    __tablename__ = 'user'
    
    id = db.Column(db.Integer, primary_key=True)
    public_id = db.Column(db.String(50), unique=True, nullable=False, default=lambda: str(uuid.uuid4()))
    
    # Informations de base
    username = db.Column(db.String(80), unique=True, nullable=False, index=True)
    email = db.Column(db.String(120), unique=True, nullable=False, index=True)
    password_hash = db.Column(db.String(128), nullable=False)
    date_joined = db.Column(db.DateTime, default=datetime.utcnow)
    
    # Informations profil
    first_name = db.Column(db.String(50), nullable=True)
    last_name = db.Column(db.String(50), nullable=True)
    bio = db.Column(db.Text, nullable=True)
    avatar_url = db.Column(db.String(255), nullable=True)
    
    # Préférences
    preferred_language = db.Column(db.String(5), default='fr', nullable=False)
    email_notifications = db.Column(db.Boolean, default=True, nullable=False)
    public_profile = db.Column(db.Boolean, default=True, nullable=False)
    
    # Statut compte
    is_active = db.Column(db.Boolean, default=True, nullable=False)
    is_verified = db.Column(db.Boolean, default=False, nullable=False)
    last_login = db.Column(db.DateTime, nullable=True)
    login_count = db.Column(db.Integer, default=0)
    
    # Relations
    articles = db.relationship('Article', backref='author', lazy='dynamic', cascade='all, delete-orphan')
    comments = db.relationship('Comment', backref='author', lazy='dynamic', cascade='all, delete-orphan')
    chat_messages = db.relationship('ChatMessage', backref='user', lazy='dynamic', cascade='all, delete-orphan')
    
    # Favoris (many-to-many)
    favorite_articles = db.relationship('Article', 
                                      secondary=user_favorites,
                                      backref=db.backref('favorited_by', lazy='dynamic'),
                                      lazy='dynamic')
    
    # Système de follow (many-to-many avec auto-référence)
    following = db.relationship('User',
                               secondary=user_following,
                               primaryjoin=id == user_following.c.follower_id,
                               secondaryjoin=id == user_following.c.followed_id,
                               backref=db.backref('followers', lazy='dynamic'),
                               lazy='dynamic')
    # def __init__(self, username, email, password):
    #     self.username = username
    #     self.email = email
    #     self.set_password(password)   
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
    
    def set_password(self, password):
        """Hasher le mot de passe"""
        self.password_hash = generate_password_hash(password)
    
    def check_password(self, password):
        """Vérifier le mot de passe"""
        return check_password_hash(self.password_hash, password)
    
    def get_full_name(self):
        """Retourner le nom complet"""
        if self.first_name and self.last_name:
            return f"{self.first_name} {self.last_name}"
        return self.username
    
    def get_display_name(self):
        """Nom d'affichage pour l'interface"""
        return self.get_full_name()
    
    def update_last_login(self):
        """Mettre à jour la dernière connexion"""
        self.last_login = datetime.utcnow()
        self.login_count += 1
        db.session.commit()
    
    def add_favorite(self, article):
        """Ajouter un article aux favoris"""
        if not self.favorite_articles.filter_by(id=article.id).count():
            self.favorite_articles.append(article)
            db.session.commit()
            return True
        return False
    
    def remove_favorite(self, article):
        """Retirer un article des favoris"""
        if self.favorite_articles.filter_by(id=article.id).count():
            self.favorite_articles.remove(article)
            db.session.commit()
            return True
        return False
    
    def is_favorite(self, article):
        """Vérifier si un article est en favori"""
        return self.favorite_articles.filter_by(id=article.id).count() > 0
    
    def follow(self, user):
        """Suivre un utilisateur"""
        if not self.is_following(user) and user != self:
            self.following.append(user)
            db.session.commit()
            return True
        return False
    
    def unfollow(self, user):
        """Ne plus suivre un utilisateur"""
        if self.is_following(user):
            self.following.remove(user)
            db.session.commit()
            return True
        return False
    
    def is_following(self, user):
        """Vérifier si on suit un utilisateur"""
        return self.following.filter_by(id=user.id).count() > 0
    
    def get_stats(self):
        """Statistiques utilisateur"""
        return {
            'articles_count': self.articles.filter_by(is_deleted=False).count(),
            'favorites_count': self.favorite_articles.count(),
            'followers_count': self.followers.count(),
            'following_count': self.following.count(),
            'comments_count': self.comments.filter_by(is_deleted=False).count()
        }
    
    def to_dict(self, include_private=False):
        """Sérialisation pour JSON"""
        data = {
            'id': self.public_id,
            'username': self.username,
            'display_name': self.get_display_name(),
            'avatar_url': self.avatar_url,
            'bio': self.bio,
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'stats': self.get_stats()
        }
        
        if include_private:
            data.update({
                'email': self.email,
                'preferred_language': self.preferred_language,
                'email_notifications': self.email_notifications,
                'public_profile': self.public_profile,
                'last_login': self.last_login.isoformat() if self.last_login else None
            })
        
        return data
    
    def __repr__(self):
        return f'<User {self.username}>'

class UserActivity(db.Model, TimestampMixin):
    """Suivi des activités utilisateur"""
    __tablename__ = 'user_activity'
    
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    activity_type = db.Column(db.String(50), nullable=False)  # 'login', 'upload', 'summarize', etc.
    activity_data = db.Column(db.JSON, nullable=True)  # Données supplémentaires
    ip_address = db.Column(db.String(45), nullable=True)
    user_agent = db.Column(db.String(255), nullable=True)
    
    # Relations
    user = db.relationship('User', backref=db.backref('activities', lazy='dynamic'))
    
    def __repr__(self):
        return f'<UserActivity {self.user.username}: {self.activity_type}>'