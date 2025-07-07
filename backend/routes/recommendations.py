from flask import Blueprint, request, jsonify, session
from flask_login import login_required, current_user
import time
import logging
import requests
import feedparser
import datetime
import os
import csv
import io
from backend.services.rag_system import EnhancedMUragSystem
from backend.models.article import Article
from backend.utils.validators import validate_search_query
from backend.utils.helpers import clean_text, extract_keywords
from backend.utils.decorators import require_api_key, cache_response

# Configuration du logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

recommendations_bp = Blueprint('recommendations', __name__, url_prefix='/api/recommendations')

# Instance globale du système RAG
rag_system = None

def get_rag_system():
    """Initialise le système RAG de manière lazy"""
    global rag_system
    if rag_system is None:
        try:
            rag_system = EnhancedMUragSystem()
            logger.info("✅ Système RAG initialisé pour les recommandations")
        except Exception as e:
            logger.error(f"❌ Erreur d'initialisation du système RAG: {str(e)}")
            raise
    return rag_system

@recommendations_bp.route('/generate', methods=['POST'])
@login_required
def generate_recommendations():
    """
    Génère des recommandations basées sur un texte ou un article
    """
    try:
        data = request.get_json()
        
        # Validation des données
        if not data:
            return jsonify({
                'success': False,
                'error': 'Données manquantes'
            }), 400
        
        # Sources possibles pour les recommandations
        text_content = data.get('text', '')
        article_id = data.get('article_id', None)
        query_keywords = data.get('keywords', '')
        max_results = data.get('max_results', 5)
        include_arxiv = data.get('include_arxiv', True)
        include_local = data.get('include_local', True)
        
        # Validation
        if not text_content and not article_id and not query_keywords:
            return jsonify({
                'success': False,
                'error': 'Au moins un paramètre (text, article_id, ou keywords) est requis'
            }), 400
        
        # Préparer le texte de requête
        query_text = ""
        current_filename = None
        
        if article_id:
            # Récupérer l'article depuis la base de données
            article = Article.query.filter_by(id=article_id, user_id=current_user.id).first()
            if article:
                query_text = article.summary or article.content or ""
                current_filename = article.filename
            else:
                return jsonify({
                    'success': False,
                    'error': 'Article non trouvé'
                }), 404
        
        elif text_content:
            query_text = clean_text(text_content)
        
        elif query_keywords:
            query_text = query_keywords
        
        # Obtenir le système RAG
        rag = get_rag_system()
        
        logger.info(f"🔍 Génération de recommandations pour {current_user.username}")
        
        start_time = time.time()
        
        # Utiliser la méthode existante du système RAG
        recommendations = rag.get_recommendations(
            text=query_text,
            n=max_results,
            current_filename=current_filename
        )
        
        processing_time = time.time() - start_time
        
        # Filtrer selon les préférences
        filtered_recommendations = []
        
        for rec in recommendations:
            source_type = rec.get('source', 'unknown')
            
            if source_type == 'local' and include_local:
                filtered_recommendations.append({
                    'id': rec.get('filename', f"local_{len(filtered_recommendations)}"),
                    'title': rec.get('title', 'Titre non disponible'),
                    'source': 'local',
                    'relevance_score': rec.get('relevance', 'N/A'),
                    'snippet': rec.get('snippet', ''),
                    'filename': rec.get('filename'),
                    'has_relevant_image': rec.get('has_relevant_image', False),
                    'has_relevant_figure': rec.get('has_relevant_figure', False),
                    'metadata': {
                        'image_text': rec.get('image_text', ''),
                        'figure_caption': rec.get('figure_caption', ''),
                        'figure_text': rec.get('figure_text', '')
                    }
                })
            
            elif source_type == 'arxiv' and include_arxiv:
                filtered_recommendations.append({
                    'id': rec.get('url', f"arxiv_{len(filtered_recommendations)}"),
                    'title': rec.get('title', 'Titre non disponible'),
                    'source': 'arxiv',
                    'relevance_score': rec.get('relevance', 'N/A'),
                    'snippet': rec.get('snippet', ''),
                    'url': rec.get('url'),
                    'pdf_url': rec.get('pdf_url'),
                    'year': rec.get('year'),
                    'metadata': {
                        'arxiv_id': rec.get('url', '').split('/')[-1] if rec.get('url') else None
                    }
                })
        
        return jsonify({
            'success': True,
            'data': {
                'recommendations': filtered_recommendations,
                'metadata': {
                    'total_found': len(filtered_recommendations),
                    'processing_time': round(processing_time, 2),
                    'query_text_length': len(query_text),
                    'sources_used': {
                        'local': include_local,
                        'arxiv': include_arxiv
                    }
                }
            }
        })
        
    except Exception as e:
        logger.error(f"❌ Erreur dans generate_recommendations: {str(e)}")
        return jsonify({
            'success': False,
            'error': f'Erreur lors de la génération des recommandations: {str(e)}'
        }), 500

@recommendations_bp.route('/arxiv/search', methods=['POST'])
@login_required
def search_arxiv():
    """
    Recherche spécifique sur ArXiv avec filtres avancés
    """
    try:
        data = request.get_json()
        
        if not data or 'keywords' not in data:
            return jsonify({
                'success': False,
                'error': 'Mots-clés manquants'
            }), 400
        
        keywords = data.get('keywords', '').strip()
        max_results = data.get('max_results', 10)
        start_date = data.get('start_date', '2024-01-01')  # Format YYYY-MM-DD
        end_date = data.get('end_date', datetime.datetime.now().strftime('%Y-%m-%d'))
        sort_by = data.get('sort_by', 'submittedDate')  # submittedDate, relevance
        sort_order = data.get('sort_order', 'descending')
        
        # Validation des mots-clés
        if len(keywords) < 2:
            return jsonify({
                'success': False,
                'error': 'Les mots-clés doivent contenir au moins 2 caractères'
            }), 400
        
        try:
            # Construction de la requête ArXiv
            query = keywords.replace(' ', '+AND+')
            
            # Formatage des dates pour ArXiv (YYYYMMDDHHMMSS)
            start_date_formatted = datetime.datetime.strptime(start_date, '%Y-%m-%d').strftime('%Y%m%d') + "000000"
            end_date_formatted = datetime.datetime.strptime(end_date, '%Y-%m-%d').strftime('%Y%m%d') + "235959"
            
            # Filtre de date
            date_filter = f"+AND+submittedDate:[{start_date_formatted}+TO+{end_date_formatted}]"
            
            # URL de l'API ArXiv
            arxiv_url = f"http://export.arxiv.org/api/query?search_query={query}{date_filter}&start=0&max_results={max_results}&sortBy={sort_by}&sortOrder={sort_order}"
            
            logger.info(f"🔍 Recherche ArXiv: {keywords}")
            
            # Requête à l'API ArXiv
            response = requests.get(arxiv_url, timeout=30)
            
            if response.status_code != 200:
                return jsonify({
                    'success': False,
                    'error': f'Erreur de connexion à ArXiv (code: {response.status_code})'
                }), 500
            
            # Parse du feed
            feed = feedparser.parse(response.content)
            
            if not feed.entries:
                return jsonify({
                    'success': True,
                    'data': {
                        'articles': [],
                        'metadata': {
                            'total_found': 0,
                            'query': keywords,
                            'date_range': f"{start_date} à {end_date}"
                        }
                    }
                })
            
            # Traitement des résultats
            articles = []
            for entry in feed.entries:
                try:
                    # Extraction de la date de publication
                    pub_date = datetime.datetime.strptime(entry.published, "%Y-%m-%dT%H:%M:%SZ")
                    pub_date_formatted = pub_date.strftime("%d/%m/%Y")
                    
                    # Extraction de l'ID ArXiv
                    arxiv_id = entry.id.split('/')[-1]
                    if '/' in arxiv_id:
                        arxiv_id = arxiv_id.split('/')[-1]
                    
                    # Construction du lien PDF direct
                    pdf_url = f"https://arxiv.org/pdf/{arxiv_id}.pdf"
                    
                    # Nettoyage du résumé
                    summary = entry.summary.replace('\n', ' ').strip()
                    if len(summary) > 300:
                        summary = summary[:300] + "..."
                    
                    # Extraction des auteurs
                    authors = []
                    if hasattr(entry, 'authors'):
                        authors = [author.name for author in entry.authors]
                    elif hasattr(entry, 'author'):
                        authors = [entry.author]
                    
                    # Extraction des catégories
                    categories = []
                    if hasattr(entry, 'tags'):
                        categories = [tag.term for tag in entry.tags]
                    
                    article_data = {
                        'id': arxiv_id,
                        'title': entry.title.strip(),
                        'authors': authors,
                        'summary': summary,
                        'published_date': pub_date_formatted,
                        'arxiv_url': entry.link,
                        'pdf_url': pdf_url,
                        'categories': categories,
                        'arxiv_id': arxiv_id
                    }
                    
                    articles.append(article_data)
                    
                except Exception as entry_error:
                    logger.warning(f"⚠️ Erreur de traitement d'une entrée ArXiv: {str(entry_error)}")
                    continue
            
            return jsonify({
                'success': True,
                'data': {
                    'articles': articles,
                    'metadata': {
                        'total_found': len(articles),
                        'query': keywords,
                        'date_range': f"{start_date} à {end_date}",
                        'sort_by': sort_by,
                        'api_url': arxiv_url
                    }
                }
            })
            
        except requests.RequestException as e:
            logger.error(f"❌ Erreur de requête ArXiv: {str(e)}")
            return jsonify({
                'success': False,
                'error': f'Erreur de connexion à ArXiv: {str(e)}'
            }), 500
            
    except Exception as e:
        logger.error(f"❌ Erreur dans search_arxiv: {str(e)}")
        return jsonify({
            'success': False,
            'error': f'Erreur lors de la recherche ArXiv: {str(e)}'
        }), 500

@recommendations_bp.route('/local/search', methods=['POST'])
@login_required
def search_local():
    """
    Recherche dans les documents locaux du système
    """
    try:
        data = request.get_json()
        
        if not data or 'query' not in data:
            return jsonify({
                'success': False,
                'error': 'Requête de recherche manquante'
            }), 400
        
        query = data.get('query', '').strip()
        max_results = data.get('max_results', 10)
        
        # Validation
        if len(query) < 2:
            return jsonify({
                'success': False,
                'error': 'La requête doit contenir au moins 2 caractères'
            }), 400
        
        # Obtenir le système RAG
        rag = get_rag_system()
        
        logger.info(f"🔍 Recherche locale: {query}")
        
        # Utiliser la recherche lexicale du système RAG
        start_time = time.time()
        results = rag.lexical_search(query, n=max_results)
        processing_time = time.time() - start_time
        
        # Formater les résultats
        formatted_results = []
        for result in results:
            formatted_result = {
                'id': result.get('filename', f"local_{len(formatted_results)}"),
                'title': result.get('title', 'Document local'),
                'filename': result.get('filename', ''),
                'snippet': result.get('snippet', ''),
                'score': result.get('score', 0),
                'has_relevant_image': result.get('has_relevant_image', False),
                'has_relevant_figure': result.get('has_relevant_figure', False),
                'metadata': {
                    'image_text': result.get('image_text', ''),
                    'figure_caption': result.get('figure_caption', ''),
                    'figure_text': result.get('figure_text', '')
                }
            }
            formatted_results.append(formatted_result)
        
        return jsonify({
            'success': True,
            'data': {
                'documents': formatted_results,
                'metadata': {
                    'total_found': len(formatted_results),
                    'processing_time': round(processing_time, 3),
                    'query': query,
                    'search_type': 'lexical'
                }
            }
        })
        
    except Exception as e:
        logger.error(f"❌ Erreur dans search_local: {str(e)}")
        return jsonify({
            'success': False,
            'error': f'Erreur lors de la recherche locale: {str(e)}'
        }), 500

@recommendations_bp.route('/similar/<int:article_id>', methods=['GET'])
@login_required
def get_similar_articles(article_id):
    """
    Trouve des articles similaires à un article donné
    """
    try:
        # Récupérer l'article de référence
        article = Article.query.filter_by(id=article_id, user_id=current_user.id).first()
        
        if not article:
            return jsonify({
                'success': False,
                'error': 'Article non trouvé'
            }), 404
        
        # Paramètres
        max_results = request.args.get('max_results', 5, type=int)
        include_arxiv = request.args.get('include_arxiv', 'true').lower() == 'true'
        include_local = request.args.get('include_local', 'true').lower() == 'true'
        
        # Utiliser le résumé ou le contenu comme base
        query_text = article.summary or article.content or article.title
        
        # Obtenir le système RAG
        rag = get_rag_system()
        
        logger.info(f"🔍 Recherche d'articles similaires à: {article.title}")
        
        # Générer les recommandations
        start_time = time.time()
        recommendations = rag.get_recommendations(
            text=query_text,
            n=max_results,
            current_filename=article.filename
        )
        processing_time = time.time() - start_time
        
        # Filtrer selon les préférences
        similar_articles = []
        
        for rec in recommendations:
            source_type = rec.get('source', 'unknown')
            
            if source_type == 'local' and include_local:
                similar_articles.append({
                    'id': rec.get('filename', f"similar_{len(similar_articles)}"),
                    'title': rec.get('title', 'Titre non disponible'),
                    'source': 'local',
                    'relevance_score': rec.get('relevance', 'N/A'),
                    'snippet': rec.get('snippet', ''),
                    'filename': rec.get('filename'),
                    'similarity_type': 'content_based'
                })
            
            elif source_type == 'arxiv' and include_arxiv:
                similar_articles.append({
                    'id': rec.get('url', f"similar_arxiv_{len(similar_articles)}"),
                    'title': rec.get('title', 'Titre non disponible'),
                    'source': 'arxiv',
                    'relevance_score': rec.get('relevance', 'N/A'),
                    'snippet': rec.get('snippet', ''),
                    'url': rec.get('url'),
                    'pdf_url': rec.get('pdf_url'),
                    'year': rec.get('year'),
                    'similarity_type': 'semantic_based'
                })
        
        return jsonify({
            'success': True,
            'data': {
                'reference_article': {
                    'id': article.id,
                    'title': article.title,
                    'filename': article.filename
                },
                'similar_articles': similar_articles,
                'metadata': {
                    'total_found': len(similar_articles),
                    'processing_time': round(processing_time, 2),
                    'query_length': len(query_text),
                    'search_parameters': {
                        'include_arxiv': include_arxiv,
                        'include_local': include_local,
                        'max_results': max_results
                    }
                }
            }
        })
        
    except Exception as e:
        logger.error(f"❌ Erreur dans get_similar_articles: {str(e)}")
        return jsonify({
            'success': False,
            'error': f'Erreur lors de la recherche d\'articles similaires: {str(e)}'
        }), 500

@recommendations_bp.route('/personalized', methods=['GET'])
@login_required
def get_personalized_recommendations():
    """
    Génère des recommandations personnalisées basées sur l'activité de l'utilisateur
    """
    try:
        # Paramètres
        max_results = request.args.get('max_results', 8, type=int)
        
        # Récupérer les articles de l'utilisateur
        user_articles = Article.query.filter_by(user_id=current_user.id).limit(10).all()
        
        if not user_articles:
            return jsonify({
                'success': True,
                'data': {
                    'recommendations': [],
                    'message': 'Ajoutez des articles pour recevoir des recommandations personnalisées'
                }
            })
        
        # Construire un profil utilisateur basé sur ses articles
        user_interests = []
        for article in user_articles:
            if article.summary:
                user_interests.append(article.summary)
            elif article.content:
                user_interests.append(article.content[:500])  # Premiers 500 caractères
        
        # Combiner les intérêts
        combined_interests = " ".join(user_interests)
        
        # Extraire des mots-clés représentatifs (fonction simple)
        keywords = []
        words = combined_interests.lower().split()
        word_freq = {}
        for word in words:
            if len(word) > 4:  # Mots de plus de 4 caractères
                word_freq[word] = word_freq.get(word, 0) + 1
        
        # Prendre les 10 mots les plus fréquents
        keywords = sorted(word_freq.items(), key=lambda x: x[1], reverse=True)[:10]
        keywords = [word for word, freq in keywords]
        
        # Obtenir le système RAG
        rag = get_rag_system()
        
        logger.info(f"🎯 Recommandations personnalisées pour {current_user.username}")
        
        # Générer des recommandations basées sur le profil
        start_time = time.time()
        recommendations = rag.get_recommendations(
            text=combined_interests[:2000],  # Limiter la taille
            n=max_results
        )
        processing_time = time.time() - start_time
        
        # Formater les recommandations
        formatted_recommendations = []
        
        for rec in recommendations:
            # Exclure les articles déjà possédés par l'utilisateur
            if rec.get('source') == 'local':
                filename = rec.get('filename', '')
                if any(article.filename == filename for article in user_articles):
                    continue  # Skip cet article car l'utilisateur l'a déjà
            
            formatted_rec = {
                'id': rec.get('filename') or rec.get('url', f"rec_{len(formatted_recommendations)}"),
                'title': rec.get('title', 'Titre non disponible'),
                'source': rec.get('source', 'unknown'),
                'relevance_score': rec.get('relevance', 'N/A'),
                'snippet': rec.get('snippet', ''),
                'recommendation_reason': 'Basé sur vos intérêts',
                'metadata': {}
            }
            
            # Ajouter des métadonnées spécifiques selon la source
            if rec.get('source') == 'local':
                formatted_rec['filename'] = rec.get('filename')
                formatted_rec['metadata']['type'] = 'local_document'
            elif rec.get('source') == 'arxiv':
                formatted_rec['url'] = rec.get('url')
                formatted_rec['pdf_url'] = rec.get('pdf_url')
                formatted_rec['year'] = rec.get('year')
                formatted_rec['metadata']['type'] = 'arxiv_paper'
            
            formatted_recommendations.append(formatted_rec)
        
        return jsonify({
            'success': True,
            'data': {
                'recommendations': formatted_recommendations,
                'user_profile': {
                    'total_articles': len(user_articles),
                    'keywords': keywords,
                    'interests_analyzed': len(combined_interests)
                },
                'metadata': {
                    'total_recommendations': len(formatted_recommendations),
                    'processing_time': round(processing_time, 2),
                    'recommendation_type': 'personalized'
                }
            }
        })
        
    except Exception as e:
        logger.error(f"❌ Erreur dans get_personalized_recommendations: {str(e)}")
        return jsonify({
            'success': False,
            'error': f'Erreur lors de la génération des recommandations personnalisées: {str(e)}'
        }), 500

@recommendations_bp.route('/trending', methods=['GET'])
@login_required
def get_trending_articles():
    """
    Récupère les articles tendance depuis ArXiv (articles récents populaires)
    """
    try:
        # Paramètres
        max_results = request.args.get('max_results', 10, type=int)
        days_back = request.args.get('days_back', 7, type=int)  # Articles des 7 derniers jours
        category = request.args.get('category', '')  # Catégorie spécifique (optionnel)
        
        # Calcul de la date de début
        end_date = datetime.datetime.now()
        start_date = end_date - datetime.timedelta(days=days_back)
        
        try:
            # Construction de la requête pour les articles récents
            query = "all"  # Requête large pour récupérer tous les articles récents
            if category:
                query = f"cat:{category}"
            
            # Formatage des dates
            start_date_formatted = start_date.strftime('%Y%m%d') + "000000"
            end_date_formatted = end_date.strftime('%Y%m%d') + "235959"
            
            # Filtre de date
            date_filter = f"+AND+submittedDate:[{start_date_formatted}+TO+{end_date_formatted}]"
            
            # URL de l'API ArXiv pour les articles récents
            arxiv_url = f"http://export.arxiv.org/api/query?search_query={query}{date_filter}&start=0&max_results={max_results * 2}&sortBy=submittedDate&sortOrder=descending"
            
            logger.info(f"📈 Récupération des articles tendance")
            
            # Requête à l'API ArXiv
            response = requests.get(arxiv_url, timeout=30)
            
            if response.status_code != 200:
                return jsonify({
                    'success': False,
                    'error': f'Erreur de connexion à ArXiv (code: {response.status_code})'
                }), 500
            
            # Parse du feed
            feed = feedparser.parse(response.content)
            
            if not feed.entries:
                return jsonify({
                    'success': True,
                    'data': {
                        'trending_articles': [],
                        'metadata': {
                            'total_found': 0,
                            'date_range': f"Derniers {days_back} jours"
                        }
                    }
                })
            
            # Traitement et scoring des articles
            trending_articles = []
            
            for entry in feed.entries:
                try:
                    # Extraction des informations
                    pub_date = datetime.datetime.strptime(entry.published, "%Y-%m-%dT%H:%M:%SZ")
                    arxiv_id = entry.id.split('/')[-1]
                    
                    # Score de tendance basé sur la récence et autres facteurs
                    days_old = (end_date - pub_date).days
                    trending_score = max(0, (days_back - days_old) / days_back)  # Score entre 0 et 1
                    
                    # Bonus pour certains mots-clés populaires
                    title_lower = entry.title.lower()
                    popular_keywords = ['ai', 'machine learning', 'deep learning', 'neural', 'transformer', 'llm', 'gpt']
                    keyword_bonus = sum(1 for keyword in popular_keywords if keyword in title_lower) * 0.1
                    trending_score += keyword_bonus
                    
                    trending_score = min(1.0, trending_score)  # Cap à 1.0
                    
                    article_data = {
                        'id': arxiv_id,
                        'title': entry.title.strip(),
                        'authors': [author.name for author in entry.authors] if hasattr(entry, 'authors') else [],
                        'summary': entry.summary.replace('\n', ' ').strip()[:300] + "...",
                        'published_date': pub_date.strftime("%d/%m/%Y"),
                        'arxiv_url': entry.link,
                        'pdf_url': f"https://arxiv.org/pdf/{arxiv_id}.pdf",
                        'categories': [tag.term for tag in entry.tags] if hasattr(entry, 'tags') else [],
                        'trending_score': round(trending_score, 3),
                        'days_old': days_old
                    }
                    
                    trending_articles.append(article_data)
                    
                except Exception as entry_error:
                    logger.warning(f"⚠️ Erreur de traitement d'une entrée tendance: {str(entry_error)}")
                    continue
            
            # Trier par score de tendance décroissant
            trending_articles.sort(key=lambda x: x['trending_score'], reverse=True)
            
            # Limiter au nombre demandé
            trending_articles = trending_articles[:max_results]
            
            return jsonify({
                'success': True,
                'data': {
                    'trending_articles': trending_articles,
                    'metadata': {
                        'total_found': len(trending_articles),
                        'date_range': f"Derniers {days_back} jours",
                        'category': category or 'all',
                        'scoring_method': 'recency_and_keywords'
                    }
                }
            })
            
        except requests.RequestException as e:
            logger.error(f"❌ Erreur de requête ArXiv pour trending: {str(e)}")
            return jsonify({
                'success': False,
                'error': f'Erreur de connexion à ArXiv: {str(e)}'
            }), 500
            
    except Exception as e:
        logger.error(f"❌ Erreur dans get_trending_articles: {str(e)}")
        return jsonify({
            'success': False,
            'error': f'Erreur lors de la récupération des articles tendance: {str(e)}'
        }), 500

@recommendations_bp.route('/stats', methods=['GET'])
@login_required
def get_recommendation_stats():
    """
    Fournit des statistiques sur le système de recommandations
    """
    try:
        # Obtenir le système RAG
        rag = get_rag_system()
        
        # Statistiques du système RAG
        rag_stats = {
            'local_documents': 0,
            'vectorstore_initialized': False,
            'lexical_index_size': 0
        }
        
        if hasattr(rag, 'lexical_index'):
            rag_stats['local_documents'] = len(rag.lexical_index)
            rag_stats['lexical_index_size'] = len(rag.lexical_index)
        
        if hasattr(rag, 'vectorstore') and rag.vectorstore:
            rag_stats['vectorstore_initialized'] = True
        
        # Statistiques utilisateur
        user_articles_count = Article.query.filter_by(user_id=current_user.id).count()
        
        # Statistiques de performance (exemple)
        performance_stats = {
            'avg_response_time': 2.5,  # Secondes (à calculer réellement)
            'success_rate': 0.95,      # Pourcentage de requêtes réussies
            'cache_hit_rate': 0.70     # Taux de cache hit
        }
        
        return jsonify({
            'success': True,
            'data': {
                'system_stats': rag_stats,
                'user_stats': {
                    'articles_uploaded': user_articles_count,
                    'can_get_personalized': user_articles_count > 0
                },
                'performance_stats': performance_stats,
                'available_sources': {
                    'local_search': True,
                    'arxiv_search': True,
                    'semantic_similarity': rag_stats['vectorstore_initialized'],
                    'lexical_search': rag_stats['lexical_index_size'] > 0
                }
            }
        })
        
    except Exception as e:
        logger.error(f"❌ Erreur dans get_recommendation_stats: {str(e)}")
        return jsonify({
            'success': False,
            'error': f'Erreur lors de la récupération des statistiques: {str(e)}'
        }), 500

@recommendations_bp.route('/categories', methods=['GET'])
@login_required
def get_arxiv_categories():
    """
    Retourne les catégories ArXiv disponibles pour filtrer les recherches
    """
    try:
        # Catégories ArXiv populaires organisées par domaine
        categories = {
            'computer_science': {
                'name': 'Informatique',
                'categories': {
                    'cs.AI': 'Intelligence Artificielle',
                    'cs.LG': 'Machine Learning',
                    'cs.CV': 'Vision par Ordinateur',
                    'cs.CL': 'Traitement du Langage Naturel',
                    'cs.CR': 'Cryptographie et Sécurité',
                    'cs.DC': 'Calcul Distribué',
                    'cs.SE': 'Génie Logiciel',
                    'cs.IR': 'Recherche d\'Information',
                    'cs.RO': 'Robotique',
                    'cs.SI': 'Interaction Homme-Machine'
                }
            },
            'mathematics': {
                'name': 'Mathématiques',
                'categories': {
                    'math.ST': 'Statistiques',
                    'math.PR': 'Probabilités',
                    'math.OC': 'Optimisation',
                    'math.NA': 'Analyse Numérique',
                    'math.CO': 'Combinatoire',
                    'math.IT': 'Théorie de l\'Information'
                }
            },
            'physics': {
                'name': 'Physique',
                'categories': {
                    'physics.comp-ph': 'Physique Computationnelle',
                    'physics.data-an': 'Analyse de Données',
                    'astro-ph': 'Astrophysique',
                    'cond-mat': 'Matière Condensée',
                    'quant-ph': 'Physique Quantique'
                }
            },
            'statistics': {
                'name': 'Statistiques',
                'categories': {
                    'stat.ML': 'Machine Learning (Stat)',
                    'stat.AP': 'Statistiques Appliquées',
                    'stat.CO': 'Calcul Statistique',
                    'stat.ME': 'Méthodologie',
                    'stat.TH': 'Théorie Statistique'
                }
            },
            'economics': {
                'name': 'Économie',
                'categories': {
                    'econ.EM': 'Économétrie',
                    'econ.TH': 'Théorie Économique',
                    'q-fin': 'Finance Quantitative'
                }
            }
        }
        
        return jsonify({
            'success': True,
            'data': {
                'categories': categories,
                'total_domains': len(categories),
                'usage_tip': 'Utilisez le code de catégorie (ex: cs.AI) dans vos recherches pour filtrer par domaine'
            }
        })
        
    except Exception as e:
        logger.error(f"❌ Erreur dans get_arxiv_categories: {str(e)}")
        return jsonify({
            'success': False,
            'error': f'Erreur lors de la récupération des catégories: {str(e)}'
        }), 500

@recommendations_bp.route('/user-activity', methods=['POST'])
@login_required
def track_user_activity():
    """
    Enregistre l'activité de l'utilisateur pour améliorer les recommandations futures
    """
    try:
        data = request.get_json()
        
        if not data:
            return jsonify({
                'success': False,
                'error': 'Données d\'activité manquantes'
            }), 400
        
        activity_type = data.get('activity_type')  # 'view', 'download', 'like', 'share'
        item_id = data.get('item_id')
        item_type = data.get('item_type')  # 'local_article', 'arxiv_paper'
        metadata = data.get('metadata', {})
        
        # Validation
        if not all([activity_type, item_id, item_type]):
            return jsonify({
                'success': False,
                'error': 'Paramètres requis: activity_type, item_id, item_type'
            }), 400
        
        # Enregistrer l'activité (ici on peut l'envoyer au système RAG ou le stocker en base)
        activity_entry = {
            'user_id': current_user.id,
            'activity_type': activity_type,
            'item_id': item_id,
            'item_type': item_type,
            'metadata': metadata,
            'timestamp': time.time()
        }
        
        # Pour l'instant, on stocke dans la session
        # Dans une vraie implémentation, on pourrait stocker en base de données
        if 'user_activity' not in session:
            session['user_activity'] = []
        
        session['user_activity'].append(activity_entry)
        
        # Limiter l'historique d'activité
        if len(session['user_activity']) > 100:
            session['user_activity'] = session['user_activity'][-100:]
        
        logger.info(f"📊 Activité enregistrée: {current_user.username} - {activity_type} - {item_type}")
        
        return jsonify({
            'success': True,
            'message': 'Activité enregistrée avec succès',
            'data': {
                'activity_id': len(session['user_activity']),
                'timestamp': activity_entry['timestamp']
            }
        })
        
    except Exception as e:
        logger.error(f"❌ Erreur dans track_user_activity: {str(e)}")
        return jsonify({
            'success': False,
            'error': f'Erreur lors de l\'enregistrement de l\'activité: {str(e)}'
        }), 500

@recommendations_bp.route('/batch-download', methods=['POST'])
@login_required
def batch_download_recommendations():
    """
    Permet de télécharger plusieurs articles recommandés en lot
    """
    try:
        data = request.get_json()
        
        if not data or 'items' not in data:
            return jsonify({
                'success': False,
                'error': 'Liste d\'éléments à télécharger manquante'
            }), 400
        
        items = data.get('items', [])
        max_items = 10  # Limite pour éviter la surcharge
        
        if len(items) > max_items:
            return jsonify({
                'success': False,
                'error': f'Maximum {max_items} éléments autorisés par batch'
            }), 400
        
        download_results = []
        
        for item in items:
            item_id = item.get('id')
            item_type = item.get('type')  # 'local', 'arxiv'
            
            if not item_id or not item_type:
                download_results.append({
                    'id': item_id,
                    'success': False,
                    'error': 'ID ou type manquant'
                })
                continue
            
            try:
                if item_type == 'local':
                    # Pour les fichiers locaux, vérifier qu'ils existent
                    filename = item.get('filename')
                    if filename:
                        pdf_path = os.path.join('data/pdfs', filename)
                        if os.path.exists(pdf_path):
                            download_results.append({
                                'id': item_id,
                                'success': True,
                                'download_url': f'/api/articles/download/{filename}',
                                'type': 'local'
                            })
                        else:
                            download_results.append({
                                'id': item_id,
                                'success': False,
                                'error': 'Fichier local non trouvé'
                            })
                    else:
                        download_results.append({
                            'id': item_id,
                            'success': False,
                            'error': 'Nom de fichier manquant'
                        })
                
                elif item_type == 'arxiv':
                    # Pour ArXiv, construire l'URL de téléchargement direct
                    arxiv_id = item_id
                    pdf_url = f"https://arxiv.org/pdf/{arxiv_id}.pdf"
                    
                    download_results.append({
                        'id': item_id,
                        'success': True,
                        'download_url': pdf_url,
                        'type': 'arxiv'
                    })
                
                else:
                    download_results.append({
                        'id': item_id,
                        'success': False,
                        'error': 'Type non supporté'
                    })
                    
            except Exception as item_error:
                download_results.append({
                    'id': item_id,
                    'success': False,
                    'error': str(item_error)
                })
        
        # Statistiques
        successful_downloads = sum(1 for result in download_results if result['success'])
        
        return jsonify({
            'success': True,
            'data': {
                'downloads': download_results,
                'statistics': {
                    'total_requested': len(items),
                    'successful': successful_downloads,
                    'failed': len(items) - successful_downloads
                }
            }
        })
        
    except Exception as e:
        logger.error(f"❌ Erreur dans batch_download_recommendations: {str(e)}")
        return jsonify({
            'success': False,
            'error': f'Erreur lors du téléchargement en lot: {str(e)}'
        }), 500

@recommendations_bp.route('/export', methods=['GET'])
@login_required
def export_recommendations():
    """
    Exporte les recommandations de l'utilisateur en format JSON/CSV
    """
    try:
        export_format = request.args.get('format', 'json').lower()
        
        if export_format not in ['json', 'csv']:
            return jsonify({
                'success': False,
                'error': 'Format supporté: json, csv'
            }), 400
        
        # Récupérer l'activité de l'utilisateur
        user_activity = session.get('user_activity', [])
        
        # Récupérer les articles de l'utilisateur pour le contexte
        user_articles = Article.query.filter_by(user_id=current_user.id).all()
        
        export_data = {
            'user_info': {
                'username': current_user.username,
                'export_date': datetime.datetime.now().isoformat(),
                'total_articles': len(user_articles)
            },
            'user_activity': user_activity,
            'recommendations_history': []  # Pourrait être étendu
        }
        
        if export_format == 'json':
            return jsonify({
                'success': True,
                'data': export_data,
                'format': 'json'
            })
        
        elif export_format == 'csv':
            # Convertir en format CSV (simplifié)
            csv_data = []
            csv_data.append(['timestamp', 'activity_type', 'item_id', 'item_type'])
            
            for activity in user_activity:
                csv_data.append([
                    activity.get('timestamp', ''),
                    activity.get('activity_type', ''),
                    activity.get('item_id', ''),
                    activity.get('item_type', '')
                ])
            
            # Convertir en string CSV
            output = io.StringIO()
            writer = csv.writer(output)
            for row in csv_data:
                writer.writerow(row)
            
            csv_content = output.getvalue()
            output.close()
            
            return jsonify({
                'success': True,
                'data': {
                    'csv_content': csv_content,
                    'filename': f'recommendations_export_{current_user.username}_{datetime.datetime.now().strftime("%Y%m%d")}.csv'
                },
                'format': 'csv'
            })
        
    except Exception as e:
        logger.error(f"❌ Erreur dans export_recommendations: {str(e)}")
        return jsonify({
            'success': False,
            'error': f'Erreur lors de l\'export: {str(e)}'
        }), 500

@recommendations_bp.route('/feedback', methods=['POST'])
@login_required
def recommendation_feedback():
    """
    Permet aux utilisateurs de donner un feedback sur les recommandations
    """
    try:
        data = request.get_json()
        
        if not data:
            return jsonify({
                'success': False,
                'error': 'Données de feedback manquantes'
            }), 400
        
        recommendation_id = data.get('recommendation_id')
        feedback_type = data.get('feedback_type')  # 'helpful', 'not_helpful', 'irrelevant'
        rating = data.get('rating')  # 1-5
        comment = data.get('comment', '')
        
        # Validation
        if not recommendation_id or not feedback_type:
            return jsonify({
                'success': False,
                'error': 'recommendation_id et feedback_type requis'
            }), 400
        
        if feedback_type not in ['helpful', 'not_helpful', 'irrelevant']:
            return jsonify({
                'success': False,
                'error': 'feedback_type doit être: helpful, not_helpful, ou irrelevant'
            }), 400
        
        if rating and (not isinstance(rating, int) or rating < 1 or rating > 5):
            return jsonify({
                'success': False,
                'error': 'rating doit être un entier entre 1 et 5'
            }), 400
        
        # Enregistrer le feedback
        feedback_entry = {
            'user_id': current_user.id,
            'recommendation_id': recommendation_id,
            'feedback_type': feedback_type,
            'rating': rating,
            'comment': comment[:500],  # Limiter la longueur
            'timestamp': time.time()
        }
        
        # Stocker dans la session (en production, utiliser une base de données)
        if 'recommendation_feedback' not in session:
            session['recommendation_feedback'] = []
        
        session['recommendation_feedback'].append(feedback_entry)
        
        logger.info(f"💬 Feedback reçu: {current_user.username} - {feedback_type} pour {recommendation_id}")
        
        return jsonify({
            'success': True,
            'message': 'Feedback enregistré avec succès',
            'data': {
                'feedback_id': len(session['recommendation_feedback']),
                'thank_you_message': 'Merci pour votre retour ! Cela nous aide à améliorer nos recommandations.'
            }
        })
        
    except Exception as e:
        logger.error(f"❌ Erreur dans recommendation_feedback: {str(e)}")
        return jsonify({
            'success': False,
            'error': f'Erreur lors de l\'enregistrement du feedback: {str(e)}'
        }), 500

# Gestion des erreurs spécifiques aux recommandations
@recommendations_bp.errorhandler(404)
def recommendations_not_found(error):
    return jsonify({
        'success': False,
        'error': 'Endpoint de recommandations non trouvé'
    }), 404

@recommendations_bp.errorhandler(500)
def recommendations_internal_error(error):
    return jsonify({
        'success': False,
        'error': 'Erreur interne du système de recommandations'
    }), 500

@recommendations_bp.errorhandler(429)
def recommendations_rate_limit(error):
    return jsonify({
        'success': False,
        'error': 'Trop de requêtes, veuillez patienter'
    }), 429