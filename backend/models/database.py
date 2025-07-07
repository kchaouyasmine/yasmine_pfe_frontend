from flask_sqlalchemy import SQLAlchemy
from datetime import datetime
from flask import Flask
import os

db = SQLAlchemy()

def init_db(app: Flask):
    app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///../../data/articspace.db'
    app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
    db.init_app(app)

class TimestampMixin:
    """Mixin pour ajouter des timestamps automatiques"""
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

class SoftDeleteMixin:
    """Mixin pour la suppression logique"""
    is_deleted = db.Column(db.Boolean, default=False, nullable=False)
    deleted_at = db.Column(db.DateTime, nullable=True)
    
    def soft_delete(self):
        """Marquer comme supprimé"""
        self.is_deleted = True
        self.deleted_at = datetime.utcnow()
        db.session.commit()
    
    def restore(self):
        """Restaurer un élément supprimé"""
        self.is_deleted = False
        self.deleted_at = None
        db.session.commit()

# Tables d'association many-to-many
article_tags = db.Table('article_tags',
    db.Column('article_id', db.Integer, db.ForeignKey('article.id'), primary_key=True),
    db.Column('tag_id', db.Integer, db.ForeignKey('tag.id'), primary_key=True)
)

user_favorites = db.Table('user_favorites',
    db.Column('user_id', db.Integer, db.ForeignKey('user.id'), primary_key=True),
    db.Column('article_id', db.Integer, db.ForeignKey('article.id'), primary_key=True),
    db.Column('favorited_at', db.DateTime, default=datetime.utcnow)
)

user_following = db.Table('user_following',
    db.Column('follower_id', db.Integer, db.ForeignKey('user.id'), primary_key=True),
    db.Column('followed_id', db.Integer, db.ForeignKey('user.id'), primary_key=True),
    db.Column('followed_at', db.DateTime, default=datetime.utcnow)
)