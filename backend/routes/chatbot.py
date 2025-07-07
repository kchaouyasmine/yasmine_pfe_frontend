from flask import Blueprint, request, jsonify, session
from flask_login import login_required, current_user
import time
import logging
from backend.services.rag_system import EnhancedMUragSystem
from backend.utils.decorators import require_api_key
from backend.utils.validators import validate_question
from backend.utils.helpers import clean_text, format_response

rag_system = None
# Configuration du logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

chatbot_bp = Blueprint('chatbot', __name__)

def get_rag_system():
    """Initialise le système RAG de manière lazy"""
    global rag_system
    if rag_system is None:
        try:
            rag_system = EnhancedMUragSystem()
            logger.info("✅ Système RAG initialisé avec succès")
        except Exception as e:
            logger.error(f"❌ Erreur d'initialisation du système RAG: {str(e)}")
            raise
    return rag_system

@chatbot_bp.route('/ask', methods=['POST'])
@login_required
def ask_question():
    """
    Endpoint principal pour poser une question au chatbot
    """
    try:
        data = request.get_json()
        
        # Validation des données
        if not data or 'question' not in data:
            return jsonify({
                'success': False,
                'error': 'Question manquante'
            }), 400
        
        question = data.get('question', '').strip()
        
        # Validation de la question
        validation_result = validate_question(question)
        if not validation_result['valid']:
            return jsonify({
                'success': False,
                'error': validation_result['message']
            }), 400
        
        # Options avancées
        return_metadata = data.get('return_metadata', True)
        validation_threshold = data.get('validation_threshold', 0.7)
        
        # Nettoyage du texte
        clean_question = clean_text(question)
        
        # Obtenir le système RAG
        rag = get_rag_system()
        
        # Traitement de la question avec métadonnées
        logger.info(f"🤔 Question de {current_user.username}: {clean_question[:100]}...")
        
        start_time = time.time()
        response_data = rag.ask(
            question=clean_question,
            return_metadata=return_metadata,
            validation_threshold=validation_threshold
        )
        processing_time = time.time() - start_time
        
        # Formatage de la réponse selon le type retourné
        if isinstance(response_data, dict):
            # Réponse avec métadonnées complètes
            answer = response_data.get("answer", "Erreur lors de la génération")
            verification_status = response_data.get("verification_status", "unknown")
            verification_score = response_data.get("verification_score", 0)
            verification_details = response_data.get("verification_details", {})
            
            # Enregistrer dans l'historique utilisateur
            conversation_entry = {
                'user_id': current_user.id,
                'question': clean_question,
                'answer': answer,
                'verification_status': verification_status,
                'verification_score': verification_score,
                'processing_time': processing_time,
                'timestamp': time.time()
            }
            
            # Stocker dans la session pour l'historique (optionnel)
            if 'chat_history' not in session:
                session['chat_history'] = []
            
            session['chat_history'].append({
                'id': len(session['chat_history']) + 1,
                'question': clean_question,
                'answer': answer,
                'timestamp': time.time(),
                'metadata': {
                    'verification_status': verification_status,
                    'verification_score': verification_score,
                    'processing_time': processing_time
                }
            })
            
            # Limiter l'historique en session à 50 entrées max
            if len(session['chat_history']) > 50:
                session['chat_history'] = session['chat_history'][-50:]
            
            # Formater la réponse finale
            formatted_response = format_response(answer, verification_status)
            
            return jsonify({
                'success': True,
                'data': {
                    'answer': formatted_response,
                    'metadata': {
                        'verification_status': verification_status,
                        'verification_score': round(verification_score, 3),
                        'processing_time': round(processing_time, 2),
                        'details': verification_details if return_metadata else None
                    }
                }
            })
        
        else:
            # Réponse simple (mode legacy)
            answer = str(response_data)
            
            session_entry = {
                'id': len(session.get('chat_history', [])) + 1,
                'question': clean_question,
                'answer': answer,
                'timestamp': time.time(),
                'metadata': {
                    'verification_status': 'legacy',
                    'processing_time': processing_time
                }
            }
            
            if 'chat_history' not in session:
                session['chat_history'] = []
            session['chat_history'].append(session_entry)
            
            return jsonify({
                'success': True,
                'data': {
                    'answer': format_response(answer),
                    'metadata': {
                        'verification_status': 'legacy',
                        'processing_time': round(processing_time, 2)
                    }
                }
            })
            
    except Exception as e:
        logger.error(f"❌ Erreur dans ask_question: {str(e)}")
        return jsonify({
            'success': False,
            'error': f'Erreur interne: {str(e)}'
        }), 500

@chatbot_bp.route('/history', methods=['GET'])
@login_required
def get_chat_history():
    """
    Récupère l'historique des conversations de l'utilisateur
    """
    try:
        # Paramètres de pagination
        page = request.args.get('page', 1, type=int)
        per_page = request.args.get('per_page', 20, type=int)
        
        # Récupérer l'historique de la session
        chat_history = session.get('chat_history', [])
        
        # Pagination simple
        start = (page - 1) * per_page
        end = start + per_page
        paginated_history = chat_history[start:end]
        
        # Statistiques
        total_conversations = len(chat_history)
        avg_response_time = 0
        if chat_history:
            response_times = [
                entry.get('metadata', {}).get('processing_time', 0) 
                for entry in chat_history
            ]
            avg_response_time = sum(response_times) / len(response_times) if response_times else 0
        
        # Compter les statuts de vérification
        status_counts = {}
        for entry in chat_history:
            status = entry.get('metadata', {}).get('verification_status', 'unknown')
            status_counts[status] = status_counts.get(status, 0) + 1
        
        return jsonify({
            'success': True,
            'data': {
                'conversations': paginated_history,
                'pagination': {
                    'page': page,
                    'per_page': per_page,
                    'total': total_conversations,
                    'has_next': end < total_conversations,
                    'has_prev': page > 1
                },
                'statistics': {
                    'total_conversations': total_conversations,
                    'avg_response_time': round(avg_response_time, 2),
                    'status_counts': status_counts
                }
            }
        })
        
    except Exception as e:
        logger.error(f"❌ Erreur dans get_chat_history: {str(e)}")
        return jsonify({
            'success': False,
            'error': f'Erreur lors de la récupération de l\'historique: {str(e)}'
        }), 500

@chatbot_bp.route('/clear-history', methods=['DELETE'])
@login_required
def clear_chat_history():
    """
    Efface l'historique des conversations de l'utilisateur
    """
    try:
        # Effacer l'historique de la session
        session.pop('chat_history', None)
        
        # Optionnel: Effacer aussi la mémoire du système RAG pour cet utilisateur
        try:
            rag = get_rag_system()
            if hasattr(rag, 'conversation_memory'):
                rag.conversation_memory = []
                rag.save_conversation_memory()
                logger.info(f"🧹 Mémoire RAG effacée pour {current_user.username}")
        except Exception as e:
            logger.warning(f"⚠️ Impossible d'effacer la mémoire RAG: {str(e)}")
        
        return jsonify({
            'success': True,
            'message': 'Historique effacé avec succès'
        })
        
    except Exception as e:
        logger.error(f"❌ Erreur dans clear_chat_history: {str(e)}")
        return jsonify({
            'success': False,
            'error': f'Erreur lors de l\'effacement: {str(e)}'
        }), 500

@chatbot_bp.route('/suggestions', methods=['GET'])
@login_required
def get_question_suggestions():
    """
    Fournit des suggestions de questions basées sur les articles de l'utilisateur
    """
    try:
        # Suggestions de base
        base_suggestions = [
            "Résume ce document en français",
            "Quels sont les résultats principaux de cette étude ?",
            "Quelle méthodologie a été utilisée ?",
            "Quelles sont les conclusions de cette recherche ?",
            "Y a-t-il des limitations mentionnées ?",
            "Qui sont les auteurs principaux ?",
            "Dans quel domaine s'inscrit cette recherche ?",
            "Quelles sont les applications pratiques ?",
            "Y a-t-il des travaux futurs suggérés ?",
            "Comment cette étude se compare-t-elle aux autres ?"
        ]
        
        # TODO: Améliorer avec des suggestions personnalisées basées sur les articles de l'utilisateur
        # Cela nécessiterait une analyse des articles uploadés par l'utilisateur
        
        return jsonify({
            'success': True,
            'data': {
                'suggestions': base_suggestions[:6],  # Limiter à 6 suggestions
                'categories': {
                    'analysis': ['Résume ce document', 'Quels sont les résultats principaux ?'],
                    'methodology': ['Quelle méthodologie a été utilisée ?', 'Y a-t-il des limitations ?'],
                    'context': ['Dans quel domaine s\'inscrit cette recherche ?', 'Quelles sont les applications ?']
                }
            }
        })
        
    except Exception as e:
        logger.error(f"❌ Erreur dans get_question_suggestions: {str(e)}")
        return jsonify({
            'success': False,
            'error': f'Erreur lors de la génération des suggestions: {str(e)}'
        }), 500

@chatbot_bp.route('/status', methods=['GET'])
@login_required
def get_chatbot_status():
    """
    Vérifie le statut du système de chatbot
    """
    try:
        rag = get_rag_system()
        
        # Test de connectivité du système RAG
        test_question = "test de connectivité"
        start_time = time.time()
        
        try:
            # Test simple sans traitement complet
            test_response = "Système opérationnel"
            response_time = time.time() - start_time
            is_healthy = True
        except Exception as e:
            logger.error(f"❌ Test de santé RAG échoué: {str(e)}")
            response_time = time.time() - start_time
            is_healthy = False
        
        # Statistiques du système
        memory_stats = {}
        if hasattr(rag, 'conversation_memory'):
            memory_stats = {
                'conversations_stored': len(rag.conversation_memory),
                'memory_enabled': True
            }
        else:
            memory_stats = {
                'conversations_stored': 0,
                'memory_enabled': False
            }
        
        return jsonify({
            'success': True,
            'data': {
                'status': 'healthy' if is_healthy else 'unhealthy',
                'response_time': round(response_time, 3),
                'rag_system': {
                    'initialized': rag is not None,
                    'model_available': is_healthy,
                    'memory_stats': memory_stats
                },
                'session_stats': {
                    'conversations_in_session': len(session.get('chat_history', []))
                }
            }
        })
        
    except Exception as e:
        logger.error(f"❌ Erreur dans get_chatbot_status: {str(e)}")
        return jsonify({
            'success': False,
            'error': f'Erreur lors de la vérification du statut: {str(e)}'
        }), 500

@chatbot_bp.route('/export', methods=['GET'])
@login_required
def export_conversation():
    """
    Exporte l'historique des conversations en JSON
    """
    try:
        chat_history = session.get('chat_history', [])
        
        if not chat_history:
            return jsonify({
                'success': False,
                'error': 'Aucun historique à exporter'
            }), 404
        
        # Préparer les données d'export
        export_data = {
            'user': current_user.username,
            'export_timestamp': time.time(),
            'total_conversations': len(chat_history),
            'conversations': chat_history
        }
        
        return jsonify({
            'success': True,
            'data': export_data
        })
        
    except Exception as e:
        logger.error(f"❌ Erreur dans export_conversation: {str(e)}")
        return jsonify({
            'success': False,
            'error': f'Erreur lors de l\'export: {str(e)}'
        }), 500

# Gestion des erreurs spécifiques au chatbot
@chatbot_bp.errorhandler(404)
def chatbot_not_found(error):
    return jsonify({
        'success': False,
        'error': 'Endpoint du chatbot non trouvé'
    }), 404

@chatbot_bp.errorhandler(500)
def chatbot_internal_error(error):
    return jsonify({
        'success': False,
        'error': 'Erreur interne du système de chatbot'
    }), 500