from flask_sqlalchemy import SQLAlchemy
from datetime import datetime
import uuid
import os

from .database import db, TimestampMixin, SoftDeleteMixin, article_tags

class Article(db.Model, TimestampMixin, SoftDeleteMixin):
    __tablename__ = 'article'
    
    id = db.Column(db.Integer, primary_key=True)
    public_id = db.Column(db.String(50), unique=True, nullable=False, default=lambda: str(uuid.uuid4()))
    
    # Informations de base
    title = db.Column(db.String(255), nullable=False, index=True)
    description = db.Column(db.Text, nullable=True)
    original_filename = db.Column(db.String(255), nullable=False)
    file_path = db.Column(db.String(500), nullable=False)
    file_size = db.Column(db.Integer, nullable=True)
    
    # Contenu extrait
    extracted_text = db.Column(db.Text, nullable=True)
    page_count = db.Column(db.Integer, nullable=True)
    
    # Résumé et traductions
    summary = db.Column(db.Text, nullable=True)
    summary_language = db.Column(db.String(5), nullable=True)
    original_language = db.Column(db.String(5), nullable=True)
    
    # Métadonnées AI
    has_images = db.Column(db.Boolean, default=False)
    has_figures = db.Column(db.Boolean, default=False)
    processing_status = db.Column(db.String(20), default='pending')  # pending, processing, completed, error
    
    # Contenu généré
    podcast_script = db.Column(db.Text, nullable=True)
    podcast_audio_path = db.Column(db.String(500), nullable=True)
    podcast_video_path = db.Column(db.String(500), nullable=True)
    presentation_path = db.Column(db.String(500), nullable=True)
    
    # Statut et permissions
    is_public = db.Column(db.Boolean, default=False, nullable=False)
    allow_comments = db.Column(db.Boolean, default=True, nullable=False)
    
    # Statistiques
    view_count = db.Column(db.Integer, default=0)
    download_count = db.Column(db.Integer, default=0)
    like_count = db.Column(db.Integer, default=0)
    
    # Relations
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    category_id = db.Column(db.Integer, db.ForeignKey('category.id'), nullable=True)
    
    # Relations many-to-many
    tags = db.relationship('Tag', secondary=article_tags, backref=db.backref('articles', lazy='dynamic'))
    
    # Relations one-to-many
    comments = db.relationship('Comment', backref='article', lazy='dynamic', cascade='all, delete-orphan')
    chat_messages = db.relationship('ChatMessage', backref='article', lazy='dynamic', cascade='all, delete-orphan')
    
    # New fields
    content = db.Column(db.Text)
    pdf_path = db.Column(db.String(255))
    audio_path = db.Column(db.String(255))  # Nouveau champ pour l'audio
    pptx_path = db.Column(db.String(255))  # Nouveau champ pour le PPTX
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    user = db.relationship('User')
    
    # def __init__(self, title, original_filename, file_path, user_id):
    def __init__(self, title, original_filename, file_path, user_id, description=None, **kwargs):
        self.title = title
        self.original_filename = original_filename
        self.file_path = file_path
        self.user_id = user_id
        self.description = description
        
        # Gérer les autres paramètres optionnels
        for key, value in kwargs.items():
            if hasattr(self, key):
                setattr(self, key, value)
    
    def increment_view(self):
        """Incrémenter le nombre de vues"""
        self.view_count += 1
        db.session.commit()
    
    def increment_download(self):
        """Incrémenter le nombre de téléchargements"""
        self.download_count += 1
        db.session.commit()
    
    def add_tag(self, tag_name):
        """Ajouter un tag"""
        tag = Tag.query.filter_by(name=tag_name.lower()).first()
        if not tag:
            tag = Tag(name=tag_name.lower(), display_name=tag_name)
            db.session.add(tag)
        
        if tag not in self.tags:
            self.tags.append(tag)
            db.session.commit()
            return True
        return False
    
    def remove_tag(self, tag_name):
        """Retirer un tag"""
        tag = Tag.query.filter_by(name=tag_name.lower()).first()
        if tag and tag in self.tags:
            self.tags.remove(tag)
            db.session.commit()
            return True
        return False
    
    def get_file_extension(self):
        """Obtenir l'extension du fichier"""
        return os.path.splitext(self.original_filename)[1].lower()
    
    def is_pdf(self):
        """Vérifier si c'est un PDF"""
        return self.get_file_extension() == '.pdf'
    
    def get_summary_languages(self):
        """Obtenir les langues de résumé disponibles"""
        # Pour l'instant simple, mais peut être étendu pour plusieurs résumés
        return [self.summary_language] if self.summary_language else []
    
    def can_edit(self, user):
        """Vérifier si un utilisateur peut modifier l'article"""
        return self.user_id == user.id
    
    def can_view(self, user=None):
        """Vérifier si un utilisateur peut voir l'article"""
        if self.is_public:
            return True
        return user and (self.user_id == user.id)
    
    def to_dict(self, include_content=False, user=None):
        """Sérialisation pour JSON"""
        data = {
            'id': self.public_id,
            'title': self.title,
            'description': self.description,
            'original_filename': self.original_filename,
            'file_size': self.file_size,
            'page_count': self.page_count,
            'original_language': self.original_language,
            'summary_language': self.summary_language,
            'processing_status': self.processing_status,
            'is_public': self.is_public,
            'is_favorite': user.is_favorite(self) if user else False,
            'allow_comments': self.allow_comments,
            'has_images': self.has_images,
            'has_figures': self.has_figures,
            'view_count': self.view_count,
            'download_count': self.download_count,
            'like_count': self.like_count,
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'updated_at': self.updated_at.isoformat() if self.updated_at else None,
            'author': {
                'id': self.author.public_id,
                'username': self.author.username,
                'display_name': self.author.get_display_name(),
                'avatar_url': self.author.avatar_url
            },
            'tags': [{'name': tag.name, 'display_name': tag.display_name} for tag in self.tags],
            'category': {
                'id': self.category.id,
                'name': self.category.name,
                'display_name': self.category.display_name
            } if self.category else None
        }
        
        if include_content:
            data.update({
                'extracted_text': self.extracted_text,
                'summary': self.summary,
                'podcast_script': self.podcast_script,
                'has_podcast_audio': bool(self.podcast_audio_path),
                'has_podcast_video': bool(self.podcast_video_path),
                'has_presentation': bool(self.presentation_path)
            })
        
        return data
    
    def __repr__(self):
        return f'<Article {self.title}>'


class Category(db.Model, TimestampMixin):
    __tablename__ = 'category'
    
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(50), unique=True, nullable=False, index=True)
    display_name = db.Column(db.String(100), nullable=False)
    description = db.Column(db.Text, nullable=True)
    color = db.Column(db.String(7), default='#2360a6')  # Couleur hexadécimale
    icon = db.Column(db.String(50), nullable=True)  # Icône Font Awesome
    
    # Relations
    articles = db.relationship('Article', backref='category', lazy='dynamic')
    
    def get_article_count(self):
        """Nombre d'articles dans cette catégorie"""
        return self.articles.filter_by(is_deleted=False).count()
    
    def __repr__(self):
        return f'<Category {self.display_name}>'


class Tag(db.Model, TimestampMixin):
    __tablename__ = 'tag'
    
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(50), unique=True, nullable=False, index=True)  # Version lowercase
    display_name = db.Column(db.String(50), nullable=False)  # Version pour affichage
    description = db.Column(db.Text, nullable=True)
    color = db.Column(db.String(7), default='#91c3fe')
    
    # Statistiques
    usage_count = db.Column(db.Integer, default=0)
    
    def increment_usage(self):
        """Incrémenter l'utilisation"""
        self.usage_count += 1
        db.session.commit()
    
    def get_article_count(self):
        """Nombre d'articles avec ce tag"""
        return len([a for a in self.articles if not a.is_deleted])
    
    def __repr__(self):
        return f'<Tag {self.display_name}>'


class Comment(db.Model, TimestampMixin, SoftDeleteMixin):
    __tablename__ = 'comment'
    
    id = db.Column(db.Integer, primary_key=True)
    content = db.Column(db.Text, nullable=False)
    
    # Relations
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    article_id = db.Column(db.Integer, db.ForeignKey('article.id'), nullable=False)
    parent_id = db.Column(db.Integer, db.ForeignKey('comment.id'), nullable=True)  # Pour les réponses
    
    # Relations
    replies = db.relationship('Comment', backref=db.backref('parent', remote_side=[id]), lazy='dynamic')
    
    def can_edit(self, user):
        """Vérifier si un utilisateur peut modifier le commentaire"""
        return self.user_id == user.id
    
    def to_dict(self):
        """Sérialisation pour JSON"""
        return {
            'id': self.id,
            'content': self.content,
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'author': {
                'id': self.author.public_id,
                'username': self.author.username,
                'display_name': self.author.get_display_name(),
                'avatar_url': self.author.avatar_url
            },
            'parent_id': self.parent_id,
            'replies_count': self.replies.filter_by(is_deleted=False).count()
        }
    
    def __repr__(self):
        return f'<Comment by {self.author.username}>'


class ChatMessage(db.Model, TimestampMixin):
    """Messages du chatbot pour chaque article"""
    __tablename__ = 'chat_message'
    
    id = db.Column(db.Integer, primary_key=True)
    message_type = db.Column(db.String(20), nullable=False)  # 'user' ou 'assistant'
    content = db.Column(db.Text, nullable=False)
    
    # Métadonnées pour le chatbot
    verification_score = db.Column(db.Float, nullable=True)
    verification_status = db.Column(db.String(50), nullable=True)
    response_time = db.Column(db.Float, nullable=True)  # Temps de réponse en secondes
    
    # Relations
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    article_id = db.Column(db.Integer, db.ForeignKey('article.id'), nullable=False)
    
    def to_dict(self):
        """Sérialisation pour JSON"""
        return {
            'id': self.id,
            'message_type': self.message_type,
            'content': self.content,
            'verification_score': self.verification_score,
            'verification_status': self.verification_status,
            'response_time': self.response_time,
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'user': {
                'id': self.user.public_id,
                'username': self.user.username
            }
        }
    
    def __repr__(self):
        return f'<ChatMessage {self.message_type}: {self.content[:50]}>'