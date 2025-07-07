"""
Fonctions de validation pour l'application ArticSpace
"""

import re
import os
from typing import Dict, Any, List, Optional
from werkzeug.datastructures import FileStorage

def validate_email(email: str) -> Dict[str, Any]:
    """
    Valide une adresse email
    """
    if not email:
        return {'valid': False, 'message': 'Email requis'}
    
    if len(email) > 255:
        return {'valid': False, 'message': 'Email trop long (max 255 caractères)'}
    
    # Pattern regex pour email
    email_pattern = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'
    
    if not re.match(email_pattern, email):
        return {'valid': False, 'message': 'Format d\'email invalide'}
    
    return {'valid': True, 'message': 'Email valide'}

def validate_password(password: str) -> Dict[str, Any]:
    """
    Valide un mot de passe selon les critères de sécurité
    """
    if not password:
        return {'valid': False, 'message': 'Mot de passe requis'}
    
    if len(password) < 8:
        return {'valid': False, 'message': 'Mot de passe trop court (minimum 8 caractères)'}
    
    if len(password) > 128:
        return {'valid': False, 'message': 'Mot de passe trop long (maximum 128 caractères)'}
    
    # Vérifier la complexité
    has_lower = re.search(r'[a-z]', password)
    has_upper = re.search(r'[A-Z]', password)
    has_digit = re.search(r'\d', password)
    has_special = re.search(r'[!@#$%^&*(),.?":{}|<>]', password)
    
    complexity_score = sum([bool(has_lower), bool(has_upper), bool(has_digit), bool(has_special)])
    
    if complexity_score < 3:
        return {
            'valid': False, 
            'message': 'Mot de passe trop simple. Utilisez des minuscules, majuscules, chiffres et caractères spéciaux'
        }
    
    # Vérifier les mots de passe courants
    common_passwords = ['password', '123456', 'qwerty', 'admin', 'letmein', 'welcome']
    if password.lower() in common_passwords:
        return {'valid': False, 'message': 'Mot de passe trop commun'}
    
    return {'valid': True, 'message': 'Mot de passe valide'}

def validate_username(username: str) -> Dict[str, Any]:
    """
    Valide un nom d'utilisateur
    """
    if not username:
        return {'valid': False, 'message': 'Nom d\'utilisateur requis'}
    
    if len(username) < 3:
        return {'valid': False, 'message': 'Nom d\'utilisateur trop court (minimum 3 caractères)'}
    
    if len(username) > 30:
        return {'valid': False, 'message': 'Nom d\'utilisateur trop long (maximum 30 caractères)'}
    
    # Seuls lettres, chiffres, points et underscores autorisés
    if not re.match(r'^[a-zA-Z0-9._]+$', username):
        return {'valid': False, 'message': 'Nom d\'utilisateur invalide (lettres, chiffres, . et _ seulement)'}
    
    # Ne peut pas commencer ou finir par un point ou underscore
    if username.startswith('.') or username.startswith('_') or username.endswith('.') or username.endswith('_'):
        return {'valid': False, 'message': 'Nom d\'utilisateur ne peut pas commencer/finir par . ou _'}
    
    # Vérifier les noms réservés
    reserved_names = ['admin', 'root', 'system', 'api', 'www', 'mail', 'support', 'test']
    if username.lower() in reserved_names:
        return {'valid': False, 'message': 'Nom d\'utilisateur réservé'}
    
    return {'valid': True, 'message': 'Nom d\'utilisateur valide'}

def validate_file_upload(file: FileStorage, allowed_extensions: List[str] = None, max_size_mb: int = 10) -> Dict[str, Any]:
    """
    Valide un fichier uploadé
    """
    if not file:
        return {'valid': False, 'message': 'Aucun fichier fourni'}
    
    if file.filename == '':
        return {'valid': False, 'message': 'Nom de fichier vide'}
    
    # Vérifier l'extension
    if allowed_extensions:
        file_ext = file.filename.rsplit('.', 1)[1].lower() if '.' in file.filename else ''
        if file_ext not in [ext.lower() for ext in allowed_extensions]:
            return {'valid': False, 'message': f'Extension non autorisée. Extensions acceptées: {", ".join(allowed_extensions)}'}
    
    # Vérifier la taille du fichier
    file.seek(0, os.SEEK_END)  # Aller à la fin du fichier
    file_size = file.tell()    # Obtenir la position (taille)
    file.seek(0)               # Retourner au début
    
    max_size_bytes = max_size_mb * 1024 * 1024
    if file_size > max_size_bytes:
        return {'valid': False, 'message': f'Fichier trop volumineux (max {max_size_mb}MB)'}
    
    if file_size == 0:
        return {'valid': False, 'message': 'Fichier vide'}
    
    # Vérifier le nom de fichier pour les caractères dangereux
    dangerous_chars = ['..', '/', '\\', ':', '*', '?', '"', '<', '>', '|']
    if any(char in file.filename for char in dangerous_chars):
        return {'valid': False, 'message': 'Nom de fichier contient des caractères non autorisés'}
    
    return {'valid': True, 'message': 'Fichier valide', 'size': file_size}

def validate_pdf_file(file: FileStorage) -> Dict[str, Any]:
    """
    Validation spécifique pour les fichiers PDF
    """
    # Validation de base
    basic_validation = validate_file_upload(file, ['pdf'], max_size_mb=50)
    if not basic_validation['valid']:
        return basic_validation
    
    # Vérifier la signature PDF
    file.seek(0)
    header = file.read(5)
    file.seek(0)
    
    if header != b'%PDF-':
        return {'valid': False, 'message': 'Fichier PDF invalide (signature manquante)'}
    
    return {'valid': True, 'message': 'Fichier PDF valide'}

def validate_article_title(title):
    if not title or not title.strip():
        return False, "Le titre de l'article ne peut pas être vide."
    if len(title) > 255:
        return False, "Le titre de l'article est trop long (max 255 caractères)."
         # Add more rules as needed
    return True, ""

def validate_article_description(description):
    if not description or not description.strip():
        return False, "La description de l'article ne peut pas être vide."
    if len(description) > 1000:
        return False, "La description de l'article est trop longue (max 1000 caractères)."
    return True, ""

def validate_tags(tags_str):
    if not tags_str:
        return True, [], ""  # Les tags sont optionnels
    tags = [tag.strip() for tag in tags_str.split(',') if tag.strip()]
    if len(tags) > 10:
        return False, [], "Vous ne pouvez pas ajouter plus de 10 tags."
    for tag in tags:
        if len(tag) > 30:
            return False, [], f"Le tag '{tag}' est trop long (max 30 caractères)."
    return True, tags, ""
    
def validate_question(question: str) -> Dict[str, Any]:
    """
    Valide une question pour le chatbot
    """
    if not question:
        return {'valid': False, 'message': 'Question vide'}
    
    question = question.strip()
    
    if len(question) < 3:
        return {'valid': False, 'message': 'Question trop courte (minimum 3 caractères)'}
    
    if len(question) > 1000:
        return {'valid': False, 'message': 'Question trop longue (maximum 1000 caractères)'}
    
    # Vérifier qu'il y a au moins une lettre
    if not re.search(r'[a-zA-ZàâäéèêëïîôöùûüÿçÀÂÄÉÈÊËÏÎÔÖÙÛÜŸÇ]', question):
        return {'valid': False, 'message': 'Question doit contenir au moins une lettre'}
    
    # Vérifier les caractères répétitifs
    if re.search(r'(.)\1{10,}', question):  # Plus de 10 caractères identiques consécutifs
        return {'valid': False, 'message': 'Question contient trop de caractères répétitifs'}
    
    return {'valid': True, 'message': 'Question valide'}

def validate_search_query(query: str) -> Dict[str, Any]:
    """
    Valide une requête de recherche
    """
    if not query:
        return {'valid': False, 'message': 'Requête de recherche vide'}
    
    query = query.strip()
    
    if len(query) < 2:
        return {'valid': False, 'message': 'Requête trop courte (minimum 2 caractères)'}
    
    if len(query) > 200:
        return {'valid': False, 'message': 'Requête trop longue (maximum 200 caractères)'}
    
    # Vérifier les caractères dangereux pour injection
    dangerous_patterns = [
        r'<script', r'javascript:', r'data:', r'vbscript:',
        r'on\w+\s*=', r'expression\s*\('
    ]
    
    for pattern in dangerous_patterns:
        if re.search(pattern, query, re.IGNORECASE):
            return {'valid': False, 'message': 'Requête contient des caractères non autorisés'}
    
    return {'valid': True, 'message': 'Requête valide'}

def validate_article_data(data: Dict[str, Any]) -> Dict[str, Any]:
    """
    Valide les données d'un article
    """
    errors = []
    
    # Titre requis
    title = data.get('title', '').strip()
    if not title:
        errors.append('Titre requis')
    elif len(title) < 5:
        errors.append('Titre trop court (minimum 5 caractères)')
    elif len(title) > 200:
        errors.append('Titre trop long (maximum 200 caractères)')
    
    # Auteurs
    authors = data.get('authors', '').strip()
    if authors and len(authors) > 500:
        errors.append('Liste d\'auteurs trop longue (maximum 500 caractères)')
    
    # Journal
    journal = data.get('journal', '').strip()
    if journal and len(journal) > 100:
        errors.append('Nom de journal trop long (maximum 100 caractères)')
    
    # Année
    year = data.get('year')
    if year:
        try:
            year_int = int(year)
            if year_int < 1900 or year_int > 2030:
                errors.append('Année invalide (doit être entre 1900 et 2030)')
        except (ValueError, TypeError):
            errors.append('Année doit être un nombre')
    
    # Résumé
    summary = data.get('summary', '').strip()
    if summary and len(summary) > 5000:
        errors.append('Résumé trop long (maximum 5000 caractères)')
    
    if errors:
        return {'valid': False, 'message': '; '.join(errors)}
    
    return {'valid': True, 'message': 'Données d\'article valides'}

def validate_language_code(lang_code: str) -> Dict[str, Any]:
    """
    Valide un code de langue
    """
    if not lang_code:
        return {'valid': False, 'message': 'Code de langue requis'}
    
    # Codes de langue supportés
    supported_languages = ['fr', 'en', 'de', 'es', 'it', 'pt', 'ru', 'zh', 'ja', 'ar']
    
    if lang_code not in supported_languages:
        return {'valid': False, 'message': f'Code de langue non supporté. Langues disponibles: {", ".join(supported_languages)}'}
    
    return {'valid': True, 'message': 'Code de langue valide'}

def validate_pagination_params(page: int, per_page: int) -> Dict[str, Any]:
    """
    Valide les paramètres de pagination
    """
    errors = []
    
    if page < 1:
        errors.append('Page doit être >= 1')
    
    if page > 1000:
        errors.append('Page trop élevée (maximum 1000)')
    
    if per_page < 1:
        errors.append('per_page doit être >= 1')
    
    if per_page > 100:
        errors.append('per_page trop élevé (maximum 100)')
    
    if errors:
        return {'valid': False, 'message': '; '.join(errors)}
    
    return {'valid': True, 'message': 'Paramètres de pagination valides'}

def validate_date_range(start_date: str, end_date: str) -> Dict[str, Any]:
    """
    Valide une plage de dates
    """
    from datetime import datetime
    
    try:
        start = datetime.strptime(start_date, '%Y-%m-%d')
        end = datetime.strptime(end_date, '%Y-%m-%d')
        
        if start > end:
            return {'valid': False, 'message': 'Date de début doit être antérieure à la date de fin'}
        
        # Vérifier que la plage n'est pas trop large (max 10 ans)
        if (end - start).days > 3650:
            return {'valid': False, 'message': 'Plage de dates trop large (maximum 10 ans)'}
        
        # Vérifier que les dates ne sont pas trop anciennes ou futures
        now = datetime.now()
        if start.year < 1900:
            return {'valid': False, 'message': 'Date de début trop ancienne (minimum 1900)'}
        
        if end > now:
            end = now  # Ajuster automatiquement à aujourd'hui
        
        return {'valid': True, 'message': 'Plage de dates valide', 'adjusted_end': end.strftime('%Y-%m-%d')}
        
    except ValueError:
        return {'valid': False, 'message': 'Format de date invalide (utilisez YYYY-MM-DD)'}

def validate_url(url: str) -> Dict[str, Any]:
    """
    Valide une URL
    """
    if not url:
        return {'valid': False, 'message': 'URL requise'}
    
    url_pattern = re.compile(
        r'^https?://'  # http:// ou https://
        r'(?:(?:[A-Z0-9](?:[A-Z0-9-]{0,61}[A-Z0-9])?\.)+[A-Z]{2,6}\.?|'  # domaine
        r'localhost|'  # localhost
        r'\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3})'  # IP
        r'(?::\d+)?'  # port optionnel
        r'(?:/?|[/?]\S+)$', re.IGNORECASE)
    
    if not url_pattern.match(url):
        return {'valid': False, 'message': 'Format d\'URL invalide'}
    
    if len(url) > 2000:
        return {'valid': False, 'message': 'URL trop longue (maximum 2000 caractères)'}
    
    return {'valid': True, 'message': 'URL valide'}

def sanitize_filename(filename: str) -> str:
    """
    Nettoie un nom de fichier pour le rendre sûr
    """
    # Remplacer les caractères dangereux
    safe_filename = re.sub(r'[<>:"/\\|?*]', '_', filename)
    
    # Supprimer les espaces multiples et les remplacer par un seul
    safe_filename = re.sub(r'\s+', ' ', safe_filename).strip()
    
    # Limiter la longueur
    if len(safe_filename) > 255:
        name, ext = os.path.splitext(safe_filename)
        safe_filename = name[:255-len(ext)] + ext
    
    return safe_filename

def validate_json_structure(data: Dict[str, Any], required_structure: Dict[str, Any]) -> Dict[str, Any]:
    """
    Valide que les données JSON correspondent à une structure attendue
    """
    def check_structure(data_part, structure_part, path=""):
        errors = []
        
        if isinstance(structure_part, dict):
            if not isinstance(data_part, dict):
                errors.append(f"{path}: attendu dict, reçu {type(data_part).__name__}")
                return errors
            
            for key, expected_type in structure_part.items():
                if key not in data_part:
                    errors.append(f"{path}.{key}: champ manquant")
                else:
                    errors.extend(check_structure(data_part[key], expected_type, f"{path}.{key}"))
        
        elif isinstance(structure_part, list) and len(structure_part) > 0:
            if not isinstance(data_part, list):
                errors.append(f"{path}: attendu list, reçu {type(data_part).__name__}")
                return errors
            
            for i, item in enumerate(data_part):
                errors.extend(check_structure(item, structure_part[0], f"{path}[{i}]"))
        
        elif structure_part == str:
            if not isinstance(data_part, str):
                errors.append(f"{path}: attendu str, reçu {type(data_part).__name__}")
        
        elif structure_part == int:
            if not isinstance(data_part, int):
                errors.append(f"{path}: attendu int, reçu {type(data_part).__name__}")
        
        elif structure_part == float:
            if not isinstance(data_part, (int, float)):
                errors.append(f"{path}: attendu float/int, reçu {type(data_part).__name__}")
        
        elif structure_part == bool:
            if not isinstance(data_part, bool):
                errors.append(f"{path}: attendu bool, reçu {type(data_part).__name__}")
        
        return errors
    
    errors = check_structure(data, required_structure)
    
    if errors:
        return {'valid': False, 'message': '; '.join(errors)}
    
    return {'valid': True, 'message': 'Structure JSON valide'}