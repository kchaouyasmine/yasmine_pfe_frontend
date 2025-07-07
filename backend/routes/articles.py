from flask import Blueprint, request, jsonify, current_app, url_for, send_file
from flask_login import login_required, current_user
from werkzeug.utils import secure_filename
import os
import json
from datetime import datetime
import tempfile
import shutil

from backend.models.database import db
from backend.models.article import Article
from backend.models.user import User, UserActivity
from backend.utils.validators import (
    validate_pdf_file,
    validate_search_query,
    validate_pagination_params,
    validate_url,
    validate_article_title,
    validate_article_description,
    validate_tags
)
from backend.utils.helpers import (
    generate_unique_filename, get_client_ip, get_user_agent,
    format_file_size, truncate_text, log_user_activity, generate_article_slug, escape_search_term
)
from backend.utils.decorators import json_required
from backend.services.summarization_service import extract_from_pdf
from backend.services.rag_system import EnhancedMUragSystem

articles_bp = Blueprint('articles', __name__)

# Configuration pour les uploads
UPLOAD_FOLDER = 'frontend/static/uploads/articles'
ALLOWED_EXTENSIONS = {'pdf', 'doc', 'docx', 'txt'}
MAX_FILE_SIZE = 50 * 1024 * 1024  # 50MB

def get_form_value(key):
    # Cherche la clé insensible à la casse dans request.form
    for k in request.form.keys():
        if k.lower() == key.lower():
            return request.form[k]
    return ''

@articles_bp.route('/')
@login_required
def index():
    """Page principale des articles de l'utilisateur"""
    # Paramètres de pagination et filtrage
    page = request.args.get('page', 1, type=int)
    per_page = min(request.args.get('per_page', 12, type=int), 50)
    search = request.args.get('search', '').strip()
    sort_by = request.args.get('sort_by', 'created_at')
    sort_order = request.args.get('sort_order', 'desc')
    tag_filter = request.args.get('tag', '').strip()
    
    # Construire la requête
    query = Article.query.filter_by(user_id=current_user.id, is_deleted=False)
    
    # Filtrage par recherche
    if search:
        search_term = f"%{escape_search_term(search)}%"
        query = query.filter(
            db.or_(
                Article.title.ilike(search_term),
                Article.description.ilike(search_term),
                Article.content.ilike(search_term)
            )
        )
    
    # Filtrage par tag
    if tag_filter:
        query = query.join(ArticleTag).filter(ArticleTag.name.ilike(f"%{tag_filter}%"))
    
    # Tri
    if sort_by == 'title':
        query = query.order_by(Article.title.asc() if sort_order == 'asc' else Article.title.desc())
    elif sort_by == 'updated_at':
        query = query.order_by(Article.updated_at.asc() if sort_order == 'asc' else Article.updated_at.desc())
    elif sort_by == 'view_count':
        query = query.order_by(Article.view_count.asc() if sort_order == 'asc' else Article.view_count.desc())
    else:  # created_at par défaut
        query = query.order_by(Article.created_at.asc() if sort_order == 'asc' else Article.created_at.desc())
    
    # Pagination
    pagination = query.paginate(
        page=page, per_page=per_page, error_out=False
    )
    
    articles = pagination.items
    
    # Récupérer les tags populaires pour les filtres
    popular_tags = db.session.query(ArticleTag.name, db.func.count(ArticleTag.article_id).label('count'))\
                            .join(Article)\
                            .filter(Article.user_id == current_user.id, Article.is_deleted == False)\
                            .group_by(ArticleTag.name)\
                            .order_by(db.func.count(ArticleTag.article_id).desc())\
                            .limit(10).all()
    
    # Statistiques
    stats = {
        'total_articles': Article.query.filter_by(user_id=current_user.id, is_deleted=False).count(),
        'total_favorites': Article.query.join(ArticleLike)\
                          .filter(ArticleLike.user_id == current_user.id).count(),
        'recent_uploads': Article.query.filter_by(user_id=current_user.id, is_deleted=False)\
                         .filter(Article.created_at >= datetime.utcnow().replace(day=1)).count()
    }
    
    if request.is_json or request.method == 'GET':
        return jsonify({
            'success': True,
            'articles': [article.to_dict() for article in articles],
            'pagination': {
                'page': page,
                'pages': pagination.pages,
                'per_page': per_page,
                'total': pagination.total,
                'has_next': pagination.has_next,
                'has_prev': pagination.has_prev
            },
            'stats': stats,
            'popular_tags': [{'name': tag.name, 'count': tag.count} for tag in popular_tags]
        })
    return jsonify({'success': False, 'message': 'Cette route est réservée à l’API.'}), 400

@articles_bp.route('/upload', methods=['GET', 'POST'])
@login_required
def upload():
    """Upload d'un nouvel article"""
    if request.method == 'POST':
        upload_type = request.form.get('upload_type', 'file')
        if upload_type == 'file':
            return handle_file_upload()
        elif upload_type == 'url':
            return handle_url_upload()
        elif upload_type == 'text':
            return handle_text_upload()
        else:
            error_msg = "Type d'upload non supporté"
            return jsonify({'success': False, 'message': error_msg}), 400
    # GET fallback: API only
    return jsonify({'success': False, 'message': 'Cette route est réservée à l’API.'}), 400

def handle_file_upload():
    """Gère l'upload de fichiers"""
    if 'file' not in request.files:
        error_msg = "Aucun fichier sélectionné"
        return jsonify({'success': False, 'message': error_msg}), 400
    
    file = request.files['file']
    title = get_form_value('title').strip()
    description = get_form_value('description').strip()
    tags_str = get_form_value('tags').strip()
    is_public = bool(get_form_value('is_public'))
    
    # Validation du fichier
    is_valid, error_msg = validate_pdf_file(file)
    if not is_valid:
        return jsonify({'success': False, 'message': error_msg}), 400
    
    # Validation du titre
    if not title:
        title = os.path.splitext(file.filename)[0]
    
    is_valid, error_msg = validate_article_title(title)
    if not is_valid:
        return jsonify({'success': False, 'message': error_msg}), 400
    
    # Validation de la description
    is_valid, error_msg = validate_article_description(description)
    if not is_valid:
        return jsonify({'success': False, 'message': error_msg}), 400
    
    # Validation des tags
    is_valid, tags_list, error_msg = validate_tags(tags_str)
    if not is_valid:
        return jsonify({'success': False, 'message': error_msg}), 400
    
    try:
        # Créer le dossier d'upload
        os.makedirs(UPLOAD_FOLDER, exist_ok=True)
        
        # Générer un nom de fichier unique
        filename = generate_unique_filename(file.filename, UPLOAD_FOLDER)
        filepath = os.path.join(UPLOAD_FOLDER, filename)
        
        # Sauvegarder le fichier
        file.save(filepath)
        
        # Traiter le PDF et extraire le contenu
        try:
            # content = extract_from_pdf(filepath)
            with open(filepath, 'rb') as f:
                content, image_paths, temp_dir = extract_from_pdf(f)
            if not content.strip():
                content = "Contenu non extractible automatiquement"
        except Exception as e:
            print(f"Erreur extraction PDF: {e}")
            content = "Erreur lors de l'extraction du contenu"
        
        # Créer l'article
        article = Article(
            title=title,
            original_filename=file.filename,
            description=description,
            content=content,
            user_id=current_user.id,
            article_type='file',
            file_path=filepath,
            filename=filename,
            file_size=os.path.getsize(filepath),
            is_public=is_public,
            slug=generate_article_slug(title)
        )
        
        db.session.add(article)
        db.session.flush()  # Pour obtenir l'ID
        
        # Ajouter les tags
        for tag_name in tags_list:
            tag = ArticleTag(article_id=article.id, name=tag_name)
            db.session.add(tag)
        
        # Ajouter à la base de connaissances RAG
        try:
            with open(filepath, 'rb') as f:
                pdf_bytes = f.read()
            rag_system = EnhancedMUragSystem()
            rag_system.add_document(pdf_bytes, filename)
        except Exception as e:
            print(f"Erreur ajout RAG: {e}")
        
        db.session.commit()
        
        # Logger l'activité
        log_user_activity(
            current_user.id,
            'article_upload',
            {
                'article_id': article.id,
                'title': title,
                'type': 'file',
                'file_size': format_file_size(article.file_size)
            }
        )
        
        success_msg = f"Article '{title}' uploadé avec succès!"
        
        return jsonify({
            'success': True,
            'message': success_msg,
            'article': article.to_dict(),
            'redirect_url': url_for('articles.view', id=article.id)
        })
        
    except Exception as e:
        db.session.rollback()
        
        # Supprimer le fichier en cas d'erreur
        if 'filepath' in locals() and os.path.exists(filepath):
            os.remove(filepath)
        
        error_msg = "Erreur lors de l'upload de l'article"
        print(f"Erreur upload: {e}")
        
        return jsonify({'success': False, 'message': error_msg}), 500

def handle_url_upload():
    """Gère l'upload par URL"""
    url = get_form_value('url').strip()
    title = get_form_value('title').strip()
    description = get_form_value('description').strip()
    tags_str = get_form_value('tags').strip()
    is_public = bool(get_form_value('is_public'))
    
    # Validation de l'URL
    is_valid, error_msg = validate_url(url)
    if not is_valid:
        return jsonify({'success': False, 'message': error_msg}), 400
    
    # Validation du titre
    is_valid, error_msg = validate_article_title(title)
    if not is_valid:
        return jsonify({'success': False, 'message': error_msg}), 400
    
    # Validation de la description
    is_valid, error_msg = validate_article_description(description)
    if not is_valid:
        return jsonify({'success': False, 'message': error_msg}), 400
    
    # Validation des tags
    is_valid, tags_list, error_msg = validate_tags(tags_str)
    if not is_valid:
        return jsonify({'success': False, 'message': error_msg}), 400
    
    try:
        # Tenter de télécharger le contenu de l'URL
        content = "Contenu de l'article accessible via l'URL fournie"
        
        # TODO: Implémenter l'extraction de contenu depuis l'URL
        # Peut utiliser requests, BeautifulSoup, etc.
        
        # Créer l'article
        article = Article(
            title=title,
            description=description,
            content=content,
            user_id=current_user.id,
            article_type='url',
            source_url=url,
            is_public=is_public,
            slug=generate_article_slug(title)
        )
        
        db.session.add(article)
        db.session.flush()
        
        # Ajouter les tags
        for tag_name in tags_list:
            tag = ArticleTag(article_id=article.id, name=tag_name)
            db.session.add(tag)
        
        db.session.commit()
        
        # Logger l'activité
        log_user_activity(
            current_user.id,
            'article_upload',
            {
                'article_id': article.id,
                'title': title,
                'type': 'url',
                'url': url
            }
        )
        
        success_msg = f"Article '{title}' ajouté avec succès!"
        
        return jsonify({
            'success': True,
            'message': success_msg,
            'article': article.to_dict(),
            'redirect_url': url_for('articles.view', id=article.id)
        })
        
    except Exception as e:
        db.session.rollback()
        error_msg = "Erreur lors de l'ajout de l'article"
        print(f"Erreur upload URL: {e}")
        
        return jsonify({'success': False, 'message': error_msg}), 500

def handle_text_upload():
    """Gère l'upload de texte brut"""
    title = get_form_value('title').strip()
    content = get_form_value('content').strip()
    description = get_form_value('description').strip()
    tags_str = get_form_value('tags').strip()
    is_public = bool(get_form_value('is_public'))
    
    # Validation du titre
    is_valid, error_msg = validate_article_title(title)
    if not is_valid:
        return jsonify({'success': False, 'message': error_msg}), 400
    
    # Validation du contenu
    if not content or len(content.strip()) < 50:
        error_msg = "Le contenu doit contenir au moins 50 caractères"
        return jsonify({'success': False, 'message': error_msg}), 400
    
    if len(content) > 100000:  # 100k caractères max
        error_msg = "Le contenu ne peut pas dépasser 100,000 caractères"
        return jsonify({'success': False, 'message': error_msg}), 400
    
    # Validation de la description
    is_valid, error_msg = validate_article_description(description)
    if not is_valid:
        return jsonify({'success': False, 'message': error_msg}), 400
    
    # Validation des tags
    is_valid, tags_list, error_msg = validate_tags(tags_str)
    if not is_valid:
        return jsonify({'success': False, 'message': error_msg}), 400
    
    try:
        # Créer l'article
        article = Article(
            title=title,
            description=description,
            content=content,
            user_id=current_user.id,
            article_type='text',
            is_public=is_public,
            slug=generate_article_slug(title)
        )
        
        db.session.add(article)
        db.session.flush()
        
        # Ajouter les tags
        for tag_name in tags_list:
            tag = ArticleTag(article_id=article.id, name=tag_name)
            db.session.add(tag)
        
        db.session.commit()
        
        # Logger l'activité
        log_user_activity(
            current_user.id,
            'article_upload',
            {
                'article_id': article.id,
                'title': title,
                'type': 'text',
                'content_length': len(content)
            }
        )
        
        success_msg = f"Article '{title}' créé avec succès!"
        
        return jsonify({
            'success': True,
            'message': success_msg,
            'article': article.to_dict(),
            'redirect_url': url_for('articles.view', id=article.id)
        })
        
    except Exception as e:
        db.session.rollback()
        error_msg = "Erreur lors de la création de l'article"
        print(f"Erreur upload texte: {e}")
        
        return jsonify({'success': False, 'message': error_msg}), 500

@articles_bp.route('/<int:id>')
@login_required
def view(id):
    """Affichage détaillé d'un article"""
    article = Article.query.filter_by(id=id, is_deleted=False).first_or_404()
    
    # Vérifier les permissions
    if article.user_id != current_user.id and not article.is_public:
        return jsonify({'success': False, 'message': 'Article non accessible'}), 403
    
    # Incrémenter le nombre de vues (seulement si ce n'est pas le propriétaire)
    if article.user_id != current_user.id:
        article.view_count += 1
        db.session.commit()
        
        # Logger l'activité de vue
        log_user_activity(
            current_user.id,
            'article_view',
            {
                'article_id': article.id,
                'article_title': article.title,
                'owner_id': article.user_id
            }
        )
    
    # Récupérer les informations supplémentaires
    tags = ArticleTag.query.filter_by(article_id=article.id).all()
    likes_count = ArticleLike.query.filter_by(article_id=article.id).count()
    user_liked = ArticleLike.query.filter_by(article_id=article.id, user_id=current_user.id).first() is not None
    
    # Récupérer les commentaires
    comments = ArticleComment.query.filter_by(article_id=article.id)\
                                  .order_by(ArticleComment.created_at.desc())\
                                  .limit(10).all()
    
    # Articles similaires (basique pour l'instant)
    similar_articles = Article.query.filter(
        Article.id != article.id,
        Article.is_deleted == False,
        Article.is_public == True
    ).limit(5).all()
    
    return jsonify({
        'success': True,
        'article': article.to_dict(include_content=True),
        'tags': [tag.name for tag in tags],
        'likes_count': likes_count,
        'user_liked': user_liked,
        'comments': [comment.to_dict() for comment in comments],
        'similar_articles': [art.to_dict() for art in similar_articles]
    })

@articles_bp.route('/<int:id>/edit', methods=['GET', 'POST'])
@login_required
def edit(id):
    """Modification d'un article"""
    article = Article.query.filter_by(id=id, user_id=current_user.id, is_deleted=False).first_or_404()
    
    if request.method == 'POST':
        title = get_form_value('title').strip()
        description = get_form_value('description').strip()
        content = get_form_value('content').strip()
        tags_str = get_form_value('tags').strip()
        is_public = bool(get_form_value('is_public'))
        
        # Validation du titre
        is_valid, error_msg = validate_article_title(title)
        if not is_valid:
            return jsonify({'success': False, 'message': error_msg}), 400
        
        # Validation de la description
        is_valid, error_msg = validate_article_description(description)
        if not is_valid:
            return jsonify({'success': False, 'message': error_msg}), 400
        
        # Validation du contenu (pour les articles texte)
        if article.article_type == 'text':
            if not content or len(content.strip()) < 50:
                error_msg = "Le contenu doit contenir au moins 50 caractères"
                return jsonify({'success': False, 'message': error_msg}), 400
        
        # Validation des tags
        is_valid, tags_list, error_msg = validate_tags(tags_str)
        if not is_valid:
            return jsonify({'success': False, 'message': error_msg}), 400
        
        try:
            # Mettre à jour l'article
            article.title = title
            article.description = description
            article.is_public = is_public
            article.slug = generate_article_slug(title)
            
            if article.article_type == 'text':
                article.content = content
            
            # Supprimer les anciens tags
            ArticleTag.query.filter_by(article_id=article.id).delete()
            
            # Ajouter les nouveaux tags
            for tag_name in tags_list:
                tag = ArticleTag(article_id=article.id, name=tag_name)
                db.session.add(tag)
            
            db.session.commit()
            
            # Logger l'activité
            log_user_activity(
                current_user.id,
                'article_update',
                {
                    'article_id': article.id,
                    'title': title,
                    'changes': ['title', 'description', 'tags', 'privacy']
                }
            )
            
            success_msg = f"Article '{title}' mis à jour avec succès!"
            
            return jsonify({
                'success': True,
                'message': success_msg,
                'article': article.to_dict(),
                'redirect_url': url_for('articles.view', id=article.id)
            })
            
        except Exception as e:
            db.session.rollback()
            error_msg = "Erreur lors de la mise à jour de l'article"
            print(f"Erreur update article: {e}")
            
            return jsonify({'success': False, 'message': error_msg}), 500
    
    # Récupérer les tags actuels pour le formulaire
    current_tags = [tag.name for tag in ArticleTag.query.filter_by(article_id=article.id).all()]
    
    return jsonify({
        'success': True,
        'article': article.to_dict(include_content=True),
        'current_tags': current_tags
    })

@articles_bp.route('/<int:id>/delete', methods=['POST'])
@login_required
def delete(id):
    """Suppression (soft delete) d'un article"""
    article = Article.query.filter_by(id=id, user_id=current_user.id, is_deleted=False).first_or_404()
    
    try:
        # Soft delete
        article.is_deleted = True
        article.deleted_at = datetime.utcnow()
        
        db.session.commit()
        
        # Logger l'activité
        log_user_activity(
            current_user.id,
            'article_delete',
            {
                'article_id': article.id,
                'title': article.title,
                'type': article.article_type
            }
        )
        
        success_msg = f"Article '{article.title}' supprimé avec succès"
        
        return jsonify({
            'success': True,
            'message': success_msg,
            'redirect_url': url_for('articles.index')
        })
        
    except Exception as e:
        db.session.rollback()
        error_msg = "Erreur lors de la suppression de l'article"
        print(f"Erreur delete article: {e}")
        
        return jsonify({'success': False, 'message': error_msg}), 500

@articles_bp.route('/<int:id>/like', methods=['POST'])
@login_required
def toggle_like(id):
    """Ajouter/retirer un like sur un article"""
    article = Article.query.filter_by(id=id, is_deleted=False).first_or_404()
    
    # Vérifier les permissions (articles publics ou propres articles)
    if article.user_id != current_user.id and not article.is_public:
        return jsonify({'success': False, 'message': 'Article non accessible'}), 403
    
    try:
        existing_like = ArticleLike.query.filter_by(
            article_id=id, user_id=current_user.id
        ).first()
        
        if existing_like:
            # Retirer le like
            db.session.delete(existing_like)
            liked = False
            action = 'unlike'
        else:
            # Ajouter le like
            like = ArticleLike(article_id=id, user_id=current_user.id)
            db.session.add(like)
            liked = True
            action = 'like'
        
        db.session.commit()
        
        # Compter les likes
        likes_count = ArticleLike.query.filter_by(article_id=id).count()
        
        # Logger l'activité
        log_user_activity(
            current_user.id,
            f'article_{action}',
            {
                'article_id': article.id,
                'article_title': article.title,
                'owner_id': article.user_id
            }
        )
        
        return jsonify({
            'success': True,
            'liked': liked,
            'likes_count': likes_count,
            'message': 'Like ajouté' if liked else 'Like retiré'
        })
        
    except Exception as e:
        db.session.rollback()
        error_msg = "Erreur lors de la mise à jour du like"
        print(f"Erreur toggle like: {e}")
        
        return jsonify({'success': False, 'message': error_msg}), 500

@articles_bp.route('/<int:id>/comment', methods=['POST'])
@login_required
def add_comment(id):
    """Ajouter un commentaire sur un article"""
    article = Article.query.filter_by(id=id, is_deleted=False).first_or_404()
    
    # Vérifier les permissions
    if article.user_id != current_user.id and not article.is_public:
        return jsonify({'success': False, 'message': 'Article non accessible'}), 403
    
    if request.is_json:
        data = request.get_json()
        content = data.get('content', '').strip()
    else:
        content = request.form.get('content', '').strip()
    
    # Validation du commentaire
    if not content:
        error_msg = "Le commentaire ne peut pas être vide"
        return jsonify({'success': False, 'message': error_msg}), 400
    
    if len(content) > 1000:
        error_msg = "Le commentaire ne peut pas dépasser 1000 caractères"
        return jsonify({'success': False, 'message': error_msg}), 400
    
    try:
        comment = ArticleComment(
            article_id=id,
            user_id=current_user.id,
            content=content
        )
        
        db.session.add(comment)
        db.session.commit()
        
        # Logger l'activité
        log_user_activity(
            current_user.id,
            'article_comment',
            {
                'article_id': article.id,
                'comment_id': comment.id,
                'article_title': article.title,
                'owner_id': article.user_id
            }
        )
        
        success_msg = "Commentaire ajouté avec succès"
        
        return jsonify({
            'success': True,
            'message': success_msg,
            'comment': comment.to_dict()
        })
        
    except Exception as e:
        db.session.rollback()
        error_msg = "Erreur lors de l'ajout du commentaire"
        print(f"Erreur add comment: {e}")
        
        return jsonify({'success': False, 'message': error_msg}), 500

@articles_bp.route('/<int:id>/download')
@login_required
def download(id):
    """Téléchargement d'un fichier article"""
    article = Article.query.filter_by(id=id, is_deleted=False).first_or_404()
    
    # Vérifier les permissions
    if article.user_id != current_user.id and not article.is_public:
        return jsonify({'success': False, 'message': 'Article non accessible'}), 403
    
    # Vérifier que c'est un article fichier
    if article.article_type != 'file' or not article.file_path:
        return jsonify({'success': False, 'message': 'Aucun fichier à télécharger'}), 400
    
    # Vérifier que le fichier existe
    if not os.path.exists(article.file_path):
        return jsonify({'success': False, 'message': 'Fichier introuvable'}), 400
    
    try:
        # Logger l'activité
        log_user_activity(
            current_user.id,
            'article_download',
            {
                'article_id': article.id,
                'article_title': article.title,
                'filename': article.filename
            }
        )
        
        return send_file(
            article.file_path,
            as_attachment=True,
            download_name=article.filename or f"article_{id}.pdf"
        )
        
    except Exception as e:
        print(f"Erreur download: {e}")
        return jsonify({'success': False, 'message': 'Erreur lors du téléchargement'}), 500

@articles_bp.route('/search')
@login_required
def search():
    """Recherche avancée d'articles"""
    query = request.args.get('q', '').strip()
    page = request.args.get('page', 1, type=int)
    per_page = min(request.args.get('per_page', 12, type=int), 50)
    article_type = request.args.get('type', '')
    date_from = request.args.get('date_from', '')
    date_to = request.args.get('date_to', '')
    author = request.args.get('author', '')
    tags = request.args.get('tags', '')
    sort_by = request.args.get('sort_by', 'relevance')
    
    # Validation de la requête
    if query:
        is_valid, error_msg = validate_search_query(query)
        if not is_valid:
            return jsonify({'success': False, 'message': error_msg}), 400
    
    # Construire la requête de base
    search_query = Article.query.filter(Article.is_deleted == False)
    
    # Filtrer par accessibilité (articles publics ou propres articles)
    search_query = search_query.filter(
        db.or_(
            Article.is_public == True,
            Article.user_id == current_user.id
        )
    )
    
    # Appliquer les filtres
    if query:
        search_term = f"%{escape_search_term(query)}%"
        search_query = search_query.filter(
            db.or_(
                Article.title.ilike(search_term),
                Article.description.ilike(search_term),
                Article.content.ilike(search_term)
            )
        )
    
    if article_type:
        search_query = search_query.filter(Article.article_type == article_type)
    
    if author:
        search_query = search_query.join(User).filter(
            db.or_(
                User.username.ilike(f"%{author}%"),
                User.first_name.ilike(f"%{author}%"),
                User.last_name.ilike(f"%{author}%")
            )
        )
    
    if tags:
        search_query = search_query.join(ArticleTag).filter(
            ArticleTag.name.ilike(f"%{tags}%")
        )
    
    # Tri
    if sort_by == 'date':
        search_query = search_query.order_by(Article.created_at.desc())
    elif sort_by == 'title':
        search_query = search_query.order_by(Article.title.asc())
    elif sort_by == 'views':
        search_query = search_query.order_by(Article.view_count.desc())
    else:  # relevance
        search_query = search_query.order_by(Article.created_at.desc())
    
    # Pagination
    pagination = search_query.paginate(
        page=page, per_page=per_page, error_out=False
    )
    
    articles = pagination.items
    
    return jsonify({
        'success': True,
        'articles': [article.to_dict() for article in articles],
        'pagination': {
            'page': page,
            'pages': pagination.pages,
            'per_page': per_page,
            'total': pagination.total
        },
        'query': query
    })

@articles_bp.route('/favorites')
@login_required
def favorites_list():
    """Articles favoris de l'utilisateur"""
    page = request.args.get('page', 1, type=int)
    per_page = min(request.args.get('per_page', 12, type=int), 50)
    
    # Récupérer les articles likés
    pagination = Article.query.join(ArticleLike)\
                             .filter(ArticleLike.user_id == current_user.id)\
                             .filter(Article.is_deleted == False)\
                             .order_by(ArticleLike.created_at.desc())\
                             .paginate(page=page, per_page=per_page, error_out=False)
    
    articles = pagination.items
    
    return jsonify({
        'success': True,
        'articles': [article.to_dict() for article in articles],
        'pagination': {
            'page': page,
            'pages': pagination.pages,
            'per_page': per_page,
            'total': pagination.total
        }
    })

# @articles_bp.route('/articles/favorites')
# @login_required
# def user_favorites():
#     """Articles favoris de l'utilisateur"""
#     page = request.args.get('page', 1, type=int)
#     per_page = min(request.args.get('per_page', 12, type=int), 50)
    
#     # Récupérer les articles likés
#     pagination = Article.query.join(ArticleLike)\
#                              .filter(ArticleLike.user_id == current_user.id)\
#                              .filter(Article.is_deleted == False)\
#                              .order_by(ArticleLike.created_at.desc())\
#                              .paginate(page=page, per_page=per_page, error_out=False)
    
#     articles = pagination.items
    
#     return jsonify({
#         'success': True,
#         'articles': [article.to_dict() for article in articles],
#         'pagination': {
#             'page': page,
#             'pages': pagination.pages,
#             'per_page': per_page,
#             'total': pagination.total
#         }
#     })

# Routes API pour les statistiques
@articles_bp.route('/api/stats')
@login_required
def api_stats():
    """Statistiques des articles (API)"""
    stats = {
        'total_articles': Article.query.filter_by(user_id=current_user.id, is_deleted=False).count(),
        'public_articles': Article.query.filter_by(user_id=current_user.id, is_deleted=False, is_public=True).count(),
        'total_views': db.session.query(db.func.sum(Article.view_count))\
                                .filter_by(user_id=current_user.id, is_deleted=False).scalar() or 0,
        'total_likes': db.session.query(db.func.count(ArticleLike.id))\
                                .join(Article)\
                                .filter(Article.user_id == current_user.id, Article.is_deleted == False).scalar() or 0,
        'recent_articles': Article.query.filter_by(user_id=current_user.id, is_deleted=False)\
                                       .filter(Article.created_at >= datetime.utcnow().replace(day=1)).count()
    }
    
    return jsonify({'success': True, 'stats': stats})

@articles_bp.route('/articles/save', methods=['POST'])
@login_required
def save_article():
    title = request.form.get('title')
    summary = request.form.get('summary')
    if not title or not summary:
        return jsonify({'error': 'Titre et résumé obligatoires.'}), 400

    # Gestion des fichiers audio/pdf
    audio_path = None
    pdf_path = None
    data_dir = os.path.join(current_app.root_path, '..', 'data')
    os.makedirs(data_dir, exist_ok=True)

    if 'audio' in request.files:
        audio_file = request.files['audio']
        audio_filename = secure_filename(audio_file.filename)
        audio_path = os.path.join('data', audio_filename)
        audio_file.save(os.path.join(data_dir, audio_filename))

    if 'pdf' in request.files:
        pdf_file = request.files['pdf']
        pdf_filename = secure_filename(pdf_file.filename)
        pdf_path = os.path.join('data', pdf_filename)
        pdf_file.save(os.path.join(data_dir, pdf_filename))

    article = Article(
        user_id=current_user.id,
        title=title,
        summary=summary,
        pdf_path=pdf_path,
        audio_path=audio_path
    )
    db.session.add(article)
    db.session.commit()
    return jsonify({'message': 'Article sauvegardé avec succès.', 'article_id': article.id})

@articles_bp.route('/<int:id>/favorite', methods=['POST'])
@login_required
def add_favorite(id):
    article = Article.query.get_or_404(id)
    if not current_user.is_favorite(article):
        current_user.add_favorite(article)
        return jsonify({'success': True, 'message': 'Ajouté aux favoris'})
    return jsonify({'success': False, 'message': 'Déjà en favoris'}), 400

@articles_bp.route('/<int:id>/favorite', methods=['DELETE'])
@login_required
def remove_favorite(id):
    article = Article.query.get_or_404(id)
    if current_user.is_favorite(article):
        current_user.remove_favorite(article)
        return jsonify({'success': True, 'message': 'Retiré des favoris'})
    return jsonify({'success': False, 'message': 'Pas dans les favoris'}), 400

# @articles_bp.route('/favorites', methods=['GET'])
# @login_required
# def favorites():
#     articles = current_user.favorite_articles.all()
#     return jsonify({
#         'success': True,
#         'favorites': [article.to_dict(user=current_user) for article in articles]
#     })