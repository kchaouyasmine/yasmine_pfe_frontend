"""
Module services pour ArticSpace
"""

from .rag_system import EnhancedMUragSystem

# Instance globale du système RAG (singleton)
_rag_instance = None

def get_rag_system():
    """
    Retourne l'instance globale du système RAG (pattern singleton)
    """
    global _rag_instance
    if _rag_instance is None:
        try:
            _rag_instance = EnhancedMUragSystem()
            print("✅ Système RAG initialisé")
        except Exception as e:
            print(f"❌ Erreur d'initialisation du système RAG: {str(e)}")
            raise
    return _rag_instance

def reset_rag_system():
    """
    Remet à zéro l'instance du système RAG (utile pour les tests)
    """
    global _rag_instance
    _rag_instance = None
    print("🔄 Système RAG remis à zéro")

# Services disponibles
AVAILABLE_SERVICES = [
    'rag_system',
    'pdf_processor',
    'audio_service', 
    'vision_service',
    'recommendation_service'
]

def check_service_health():
    """
    Vérifie l'état de santé des services
    """
    health_status = {}
    
    # Vérifier le système RAG
    try:
        rag = get_rag_system()
        health_status['rag_system'] = {
            'status': 'healthy',
            'details': {
                'vectorstore_initialized': hasattr(rag, 'vectorstore') and rag.vectorstore is not None,
                'lexical_index_size': len(rag.lexical_index) if hasattr(rag, 'lexical_index') else 0
            }
        }
    except Exception as e:
        health_status['rag_system'] = {
            'status': 'unhealthy',
            'error': str(e)
        }
    
    # Vérifier Ollama (service externe)
    try:
        import ollama
        # Test simple de connectivité
        models = ollama.list()
        health_status['ollama'] = {
            'status': 'healthy',
            'details': {
                'models_available': len(models.get('models', [])) if isinstance(models, dict) else 0
            }
        }
    except Exception as e:
        health_status['ollama'] = {
            'status': 'unhealthy',
            'error': str(e)
        }
    
    # Vérifier les dossiers de données
    import os
    data_folders = ['data/chroma2', 'data/pdfs', 'data']
    for folder in data_folders:
        health_status[f'folder_{folder.replace("/", "_")}'] = {
            'status': 'healthy' if os.path.exists(folder) else 'missing',
            'exists': os.path.exists(folder)
        }
    
    return health_status

def initialize_all_services():
    """
    Initialise tous les services nécessaires
    """
    print("🚀 Initialisation des services ArticSpace...")
    
    # Initialiser le système RAG
    try:
        rag = get_rag_system()
        print("✅ Système RAG prêt")
    except Exception as e:
        print(f"❌ Échec initialisation RAG: {e}")
    
    # Vérifier la santé des services
    health = check_service_health()
    
    healthy_services = sum(1 for service, status in health.items() 
                          if status.get('status') == 'healthy')
    total_services = len(health)
    
    print(f"📊 Services opérationnels: {healthy_services}/{total_services}")
    
    return health

__all__ = [
    'EnhancedMUragSystem',
    'get_rag_system',
    'reset_rag_system',
    'check_service_health',
    'initialize_all_services',
    'AVAILABLE_SERVICES'
]