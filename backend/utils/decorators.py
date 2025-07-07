"""
Décorateurs personnalisés pour l'application ArticSpace
"""

from functools import wraps
from flask import request, jsonify, current_app, g
from flask_login import current_user
import time
import hashlib
import redis
import logging

logger = logging.getLogger(__name__)

# Cache Redis (optionnel)
try:
    redis_client = redis.Redis(host='localhost', port=6379, db=0, decode_responses=True)
except:
    redis_client = None

def require_api_key(f):
    """
    Décorateur pour vérifier la présence d'une clé API
    """
    @wraps(f)
    def decorated_function(*args, **kwargs):
        api_key = request.headers.get('X-API-Key')
        
        if not api_key:
            return jsonify({
                'success': False,
                'error': 'Clé API manquante'
            }), 401
        
        # Vérifier la clé API (exemple simple)
        valid_api_keys = current_app.config.get('VALID_API_KEYS', [])
        
        if api_key not in valid_api_keys:
            return jsonify({
                'success': False,
                'error': 'Clé API invalide'
            }), 401
        
        g.api_key = api_key
        return f(*args, **kwargs)
    
    return decorated_function

def rate_limit(requests_per_minute=60):
    """
    Décorateur pour limiter le taux de requêtes par utilisateur
    """
    def decorator(f):
        @wraps(f)
        def decorated_function(*args, **kwargs):
            if not current_user.is_authenticated:
                return jsonify({
                    'success': False,
                    'error': 'Authentification requise'
                }), 401
            
            # Clé unique pour l'utilisateur
            rate_limit_key = f"rate_limit:{current_user.id}:{f.__name__}"
            
            if redis_client:
                try:
                    # Vérifier le nombre de requêtes
                    current_requests = redis_client.get(rate_limit_key)
                    
                    if current_requests and int(current_requests) >= requests_per_minute:
                        return jsonify({
                            'success': False,
                            'error': 'Limite de taux dépassée. Veuillez patienter.'
                        }), 429
                    
                    # Incrémenter le compteur
                    pipeline = redis_client.pipeline()
                    pipeline.incr(rate_limit_key)
                    pipeline.expire(rate_limit_key, 60)  # Expiration en 1 minute
                    pipeline.execute()
                    
                except Exception as e:
                    logger.warning(f"Erreur Redis rate limiting: {e}")
                    # Continuer sans rate limiting si Redis échoue
            
            return f(*args, **kwargs)
        
        return decorated_function
    return decorator

def cache_response(timeout=300):
    """
    Décorateur pour mettre en cache les réponses
    """
    def decorator(f):
        @wraps(f)
        def decorated_function(*args, **kwargs):
            # Créer une clé de cache basée sur la fonction et les paramètres
            cache_key = f"cache:{f.__name__}:{hashlib.md5(str(request.args).encode()).hexdigest()}"
            
            if current_user.is_authenticated:
                cache_key += f":{current_user.id}"
            
            if redis_client:
                try:
                    # Vérifier le cache
                    cached_result = redis_client.get(cache_key)
                    if cached_result:
                        logger.info(f"Cache hit pour {f.__name__}")
                        import json
                        return json.loads(cached_result)
                    
                    # Exécuter la fonction
                    result = f(*args, **kwargs)
                    
                    # Mettre en cache si c'est une réponse JSON réussie
                    if hasattr(result, 'status_code') and result.status_code == 200:
                        redis_client.setex(cache_key, timeout, result.get_data(as_text=True))
                        logger.info(f"Résultat mis en cache pour {f.__name__}")
                    
                    return result
                    
                except Exception as e:
                    logger.warning(f"Erreur cache Redis: {e}")
                    # Continuer sans cache si Redis échoue
            
            return f(*args, **kwargs)
        
        return decorated_function
    return decorator

def log_execution_time(f):
    """
    Décorateur pour logger le temps d'exécution des fonctions
    """
    @wraps(f)
    def decorated_function(*args, **kwargs):
        start_time = time.time()
        
        try:
            result = f(*args, **kwargs)
            execution_time = time.time() - start_time
            
            logger.info(f"{f.__name__} exécuté en {execution_time:.3f}s")
            
            # Ajouter le temps d'exécution dans les headers de réponse
            if hasattr(result, 'headers'):
                result.headers['X-Execution-Time'] = str(execution_time)
            
            return result
            
        except Exception as e:
            execution_time = time.time() - start_time
            logger.error(f"{f.__name__} échoué après {execution_time:.3f}s: {str(e)}")
            raise
    
    return decorated_function

def validate_json(required_fields=None):
    """
    Décorateur pour valider les données JSON
    """
    def decorator(f):
        @wraps(f)
        def decorated_function(*args, **kwargs):
            if not request.is_json:
                return jsonify({
                    'success': False,
                    'error': 'Content-Type doit être application/json'
                }), 400
            
            data = request.get_json()
            
            if not data:
                return jsonify({
                    'success': False,
                    'error': 'Corps JSON manquant'
                }), 400
            
            # Vérifier les champs requis
            if required_fields:
                missing_fields = []
                for field in required_fields:
                    if field not in data or data[field] is None:
                        missing_fields.append(field)
                
                if missing_fields:
                    return jsonify({
                        'success': False,
                        'error': f'Champs manquants: {", ".join(missing_fields)}'
                    }), 400
            
            return f(*args, **kwargs)
        
        return decorated_function
    return decorator

def admin_required(f):
    """
    Décorateur pour restreindre l'accès aux administrateurs
    """
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not current_user.is_authenticated:
            return jsonify({
                'success': False,
                'error': 'Authentification requise'
            }), 401
        
        if not getattr(current_user, 'is_admin', False):
            return jsonify({
                'success': False,
                'error': 'Privilèges administrateur requis'
            }), 403
        
        return f(*args, **kwargs)
    
    return decorated_function

def handle_exceptions(f):
    """
    Décorateur pour gérer les exceptions de manière uniforme
    """
    @wraps(f)
    def decorated_function(*args, **kwargs):
        try:
            return f(*args, **kwargs)
        
        except ValueError as e:
            logger.warning(f"Erreur de validation dans {f.__name__}: {str(e)}")
            return jsonify({
                'success': False,
                'error': f'Données invalides: {str(e)}'
            }), 400
        
        except PermissionError as e:
            logger.warning(f"Erreur de permission dans {f.__name__}: {str(e)}")
            return jsonify({
                'success': False,
                'error': 'Permissions insuffisantes'
            }), 403
        
        except FileNotFoundError as e:
            logger.warning(f"Fichier non trouvé dans {f.__name__}: {str(e)}")
            return jsonify({
                'success': False,
                'error': 'Ressource non trouvée'
            }), 404
        
        except Exception as e:
            logger.error(f"Erreur inattendue dans {f.__name__}: {str(e)}")
            return jsonify({
                'success': False,
                'error': 'Erreur interne du serveur'
            }), 500
    
    return decorated_function

def cors_enabled(origins=None):
    """
    Décorateur pour ajouter les headers CORS
    """
    def decorator(f):
        @wraps(f)
        def decorated_function(*args, **kwargs):
            response = f(*args, **kwargs)
            
            # Si c'est une réponse Flask
            if hasattr(response, 'headers'):
                if origins:
                    response.headers['Access-Control-Allow-Origin'] = ', '.join(origins)
                else:
                    response.headers['Access-Control-Allow-Origin'] = '*'
                
                response.headers['Access-Control-Allow-Methods'] = 'GET, POST, PUT, DELETE, OPTIONS'
                response.headers['Access-Control-Allow-Headers'] = 'Content-Type, Authorization, X-API-Key'
            
            return response
        
        return decorated_function
    return decorator

def measure_performance(f):
    """
    Décorateur pour mesurer les performances détaillées
    """
    @wraps(f)
    def decorated_function(*args, **kwargs):
        start_time = time.time()
        start_memory = None
        
        try:
            import psutil
            process = psutil.Process()
            start_memory = process.memory_info().rss
        except ImportError:
            pass
        
        try:
            result = f(*args, **kwargs)
            
            end_time = time.time()
            execution_time = end_time - start_time
            
            performance_data = {
                'function': f.__name__,
                'execution_time': round(execution_time, 3),
                'timestamp': start_time
            }
            
            if start_memory:
                end_memory = process.memory_info().rss
                memory_used = end_memory - start_memory
                performance_data['memory_used'] = memory_used
            
            # Logger les performances
            if execution_time > 1.0:  # Si > 1 seconde
                logger.warning(f"Performance lente: {f.__name__} - {execution_time:.3f}s")
            else:
                logger.debug(f"Performance: {f.__name__} - {execution_time:.3f}s")
            
            # Ajouter aux headers de réponse
            if hasattr(result, 'headers'):
                result.headers['X-Performance-Data'] = str(performance_data)
            
            return result
            
        except Exception as e:
            end_time = time.time()
            execution_time = end_time - start_time
            logger.error(f"Erreur de performance dans {f.__name__} après {execution_time:.3f}s: {str(e)}")
            raise
    
    return decorated_function

# Décorateur combiné pour les endpoints API courants
def api_endpoint(rate_limit_requests=60, cache_timeout=0, log_performance=True):
    """
    Décorateur combiné pour les endpoints API standard
    """
    def decorator(f):
        # Appliquer les décorateurs dans l'ordre approprié
        decorated = f
        
        if log_performance:
            decorated = log_execution_time(decorated)
        
        if cache_timeout > 0:
            decorated = cache_response(cache_timeout)(decorated)
        
        if rate_limit_requests > 0:
            decorated = rate_limit(rate_limit_requests)(decorated)
        
        decorated = handle_exceptions(decorated)
        
        return decorated
    
    return decorator
from functools import wraps
from flask import request, jsonify

def json_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not request.is_json:
            return jsonify({"error": "Request must be JSON"}), 400
        return f(*args, **kwargs)
    return decorated_function