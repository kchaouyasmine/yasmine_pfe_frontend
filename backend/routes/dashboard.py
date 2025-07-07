# backend/routes/dashboard.py
from flask import Blueprint, render_template, request, redirect, url_for, flash, jsonify
from flask_login import login_required, current_user
from backend.models.article import Article
from backend.models.user import User
from backend.models.database import db
from backend.utils.helpers import get_current_timestamp
from sqlalchemy import desc, func
import logging

logger = logging.getLogger(__name__)

dashboard_bp = Blueprint('dashboard', __name__)

@dashboard_bp.route('/')
@dashboard_bp.route('/index')
@login_required
def index():
    """Page principale du dashboard"""
    try:
        # Statistiques utilisateur
        user_articles_count = Article.query.filter_by(user_id=current_user.id).count()
        user_favorites_count = len(current_user.favorites) if hasattr(current_user, 'favorites') else 0
        
        # Articles récents de l'utilisateur
        recent_articles = Article.query.filter_by(user_id=current_user.id)\
                                     .order_by(desc(Article.created_at))\
                                     .limit(5).all()
        
        # Statistiques globales
        total_articles = Article.query.count()
        total_users = User.query.count()
        
        # Articles populaires (simulation)
        popular_articles = Article.query.order_by(desc(Article.created_at)).limit(5).all()
        
        stats = {
            'user_articles': user_articles_count,
            'user_favorites': user_favorites_count,
            'total_articles': total_articles,
            'total_users': total_users,
            'recent_articles': recent_articles,
            'popular_articles': popular_articles
        }
        
        return render_template('dashboard/index.html', stats=stats)
        
    except Exception as e:
        logger.error(f"Erreur dashboard index: {e}")
        flash('Erreur lors du chargement du dashboard', 'error')
        return render_template('dashboard/index.html', stats={})

@dashboard_bp.route('/articles')
@login_required
def articles():
    """Page de gestion des articles de l'utilisateur"""
    try:
        page = request.args.get('page', 1, type=int)
        per_page = 10
        
        # Récupérer les articles de l'utilisateur avec pagination
        articles_pagination = Article.query.filter_by(user_id=current_user.id)\
                                          .order_by(desc(Article.created_at))\
                                          .paginate(
                                              page=page,
                                              per_page=per_page,
                                              error_out=False
                                          )
        
        return render_template('dashboard/articles.html', 
                             articles=articles_pagination.items,
                             pagination=articles_pagination)
        
    except Exception as e:
        logger.error(f"Erreur dashboard articles: {e}")
        flash('Erreur lors du chargement des articles', 'error')
        return render_template('dashboard/articles.html', articles=[], pagination=None)

@dashboard_bp.route('/favorites')
@login_required 
def favorites():
    """Page des articles favoris de l'utilisateur"""
    try:
        # Si vous avez un système de favoris implémenté
        favorite_articles = []
        
        # Exemple de récupération des favoris
        # favorite_articles = current_user.get_favorites()
        
        return render_template('dashboard/favorites.html', articles=favorite_articles)
        
    except Exception as e:
        logger.error(f"Erreur dashboard favorites: {e}")
        flash('Erreur lors du chargement des favoris', 'error')
        return render_template('dashboard/favorites.html', articles=[])

@dashboard_bp.route('/community')
@login_required
def community():
    """Page de la communauté"""
    try:
        page = request.args.get('page', 1, type=int)
        category = request.args.get('category', '')
        search = request.args.get('search', '')
        
        # Base query pour tous les articles publics
        query = Article.query.filter_by(is_public=True)
        
        # Filtres
        if category:
            query = query.filter_by(category=category)
        
        if search:
            query = query.filter(Article.title.contains(search) | 
                               Article.content.contains(search))
        
        # Pagination
        articles_pagination = query.order_by(desc(Article.created_at))\
                                  .paginate(
                                      page=page,
                                      per_page=12,
                                      error_out=False
                                  )
        
        # Statistiques pour la communauté
        community_stats = {
            'total_articles': Article.query.filter_by(is_public=True).count(),
            'total_contributors': User.query.count(),
            'categories': ['Intelligence Artificielle', 'Médecine', 'Physique', 'Biologie', 'Chimie']
        }
        
        return render_template('dashboard/community.html',
                             articles=articles_pagination.items,
                             pagination=articles_pagination,
                             stats=community_stats,
                             current_category=category,
                             current_search=search)
        
    except Exception as e:
        logger.error(f"Erreur dashboard community: {e}")
        flash('Erreur lors du chargement de la communauté', 'error')
        return render_template('dashboard/community.html', articles=[], stats={})

@dashboard_bp.route('/api/stats')
@login_required
def api_stats():
    """API pour récupérer les statistiques en temps réel"""
    try:
        stats = {
            'user_articles': Article.query.filter_by(user_id=current_user.id).count(),
            'total_articles': Article.query.count(),
            'total_users': User.query.count(),
            'recent_activity': Article.query.order_by(desc(Article.created_at)).limit(5).count()
        }
        return jsonify(stats)
    except Exception as e:
        logger.error(f"Erreur API stats: {e}")
        return jsonify({'error': 'Erreur serveur'}), 500

@dashboard_bp.route('/settings')
@login_required
def settings():
    """Page des paramètres utilisateur"""
    return render_template('dashboard/settings.html')

@dashboard_bp.route('/profile')
@login_required
def profile():
    """Page de profil utilisateur"""
    return render_template('auth/profile.html', user=current_user)