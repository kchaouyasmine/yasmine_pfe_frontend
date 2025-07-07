# backend/utils/helpers.py
import os
import secrets
import hashlib
from datetime import datetime
from flask import request, current_app
from werkzeug.utils import secure_filename
from PIL import Image
import uuid
import re
import logging

def escape_search_term(term):
      # Échappe les caractères spéciaux SQL LIKE
    return term.replace('%', '\\%').replace('_', '\\_')

def log_user_activity(user_id, activity_type, details=None):
    logging.info(f"User {user_id} did {activity_type} - {details}")

def generate_article_slug(title):
    slug = title.lower()
    slug = re.sub(r'[^a-z0-9]+', '-', slug)
    slug = slug.strip('-')
    return slug

def get_client_ip():
    """Récupère l'adresse IP du client"""
    if request.environ.get('HTTP_X_FORWARDED_FOR') is None:
        return request.environ['REMOTE_ADDR']
    else:
        return request.environ['HTTP_X_FORWARDED_FOR']

def get_user_agent():
    """Récupère le User-Agent du client"""
    return request.headers.get('User-Agent', 'Unknown')

def allowed_file(filename, allowed_extensions=None):
    """Vérifie si le fichier a une extension autorisée"""
    if allowed_extensions is None:
        allowed_extensions = {'pdf', 'txt', 'png', 'jpg', 'jpeg', 'gif'}
    
    return '.' in filename and \
           filename.rsplit('.', 1)[1].lower() in allowed_extensions

def save_profile_picture(file, user_id):
    """Sauvegarde la photo de profil de l'utilisateur"""
    if file and allowed_file(file.filename, {'png', 'jpg', 'jpeg', 'gif'}):
        try:
            # Générer un nom de fichier sécurisé
            filename = secure_filename(file.filename)
            file_ext = filename.rsplit('.', 1)[1].lower()
            new_filename = f"profile_{user_id}_{secrets.token_hex(8)}.{file_ext}"
            
            # Chemin de sauvegarde
            upload_folder = os.path.join(current_app.root_path, 'frontend', 'static', 'images', 'avatars')
            os.makedirs(upload_folder, exist_ok=True)
            file_path = os.path.join(upload_folder, new_filename)
            
            # Redimensionner l'image
            image = Image.open(file)
            image = resize_image(image, (200, 200))
            image.save(file_path, optimize=True, quality=85)
            
            return f"images/avatars/{new_filename}"
        except Exception as e:
            print(f"Erreur lors de la sauvegarde de l'image: {e}")
            return None
    return None

def resize_image(image, size):
    """Redimensionne une image en conservant les proportions"""
    image.thumbnail(size, Image.Resampling.LANCZOS)
    
    # Créer une nouvelle image carrée avec fond blanc
    new_image = Image.new('RGB', size, (255, 255, 255))
    
    # Centrer l'image redimensionnée
    paste_x = (size[0] - image.width) // 2
    paste_y = (size[1] - image.height) // 2
    new_image.paste(image, (paste_x, paste_y))
    
    return new_image

def generate_filename(original_filename, prefix="file"):
    """Génère un nom de fichier sécurisé et unique"""
    if original_filename:
        filename = secure_filename(original_filename)
        file_ext = filename.rsplit('.', 1)[1].lower() if '.' in filename else 'txt'
    else:
        file_ext = 'txt'
    
    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    random_hash = secrets.token_hex(6)
    
    return f"{prefix}_{timestamp}_{random_hash}.{file_ext}"

def save_uploaded_file(file, folder, allowed_extensions=None):
    """Sauvegarde un fichier uploadé dans le dossier spécifié"""
    if file and allowed_file(file.filename, allowed_extensions):
        try:
            filename = generate_filename(file.filename, "upload")
            
            # Créer le dossier s'il n'existe pas
            upload_path = os.path.join(current_app.root_path, folder)
            os.makedirs(upload_path, exist_ok=True)
            
            file_path = os.path.join(upload_path, filename)
            file.save(file_path)
            
            return filename, file_path
        except Exception as e:
            print(f"Erreur lors de la sauvegarde du fichier: {e}")
            return None, None
    return None, None

def generate_hash(text):
    """Génère un hash SHA-256 d'un texte"""
    return hashlib.sha256(text.encode('utf-8')).hexdigest()

def truncate_text(text, max_length=100, suffix="..."):
    """Tronque un texte à la longueur maximale spécifiée"""
    if len(text) <= max_length:
        return text
    return text[:max_length - len(suffix)] + suffix

def format_file_size(size_bytes):
    """Formate la taille d'un fichier en unités lisibles"""
    if size_bytes == 0:
        return "0 B"
    
    size_names = ["B", "KB", "MB", "GB", "TB"]
    i = 0
    while size_bytes >= 1024 and i < len(size_names) - 1:
        size_bytes /= 1024.0
        i += 1
    
    return f"{size_bytes:.1f} {size_names[i]}"

def get_file_extension(filename):
    """Récupère l'extension d'un fichier"""
    return filename.rsplit('.', 1)[1].lower() if '.' in filename else ''

def is_safe_url(target):
    """Vérifie si une URL de redirection est sûre"""
    from urllib.parse import urlparse, urljoin
    
    ref_url = urlparse(request.host_url)
    test_url = urlparse(urljoin(request.host_url, target))
    
    return test_url.scheme in ('http', 'https') and ref_url.netloc == test_url.netloc

def generate_unique_id():
    """Génère un ID unique"""
    return str(uuid.uuid4())

def clean_filename(filename):
    """Nettoie un nom de fichier pour le rendre sûr"""
    import re
    
    # Garder seulement les caractères alphanumériques, points, tirets et underscores
    filename = re.sub(r'[^\w\-_\.]', '_', filename)
    
    # Éviter les noms de fichiers réservés Windows
    reserved_names = {
        'CON', 'PRN', 'AUX', 'NUL', 'COM1', 'COM2', 'COM3', 'COM4', 
        'COM5', 'COM6', 'COM7', 'COM8', 'COM9', 'LPT1', 'LPT2', 
        'LPT3', 'LPT4', 'LPT5', 'LPT6', 'LPT7', 'LPT8', 'LPT9'
    }
    
    name_without_ext = filename.rsplit('.', 1)[0] if '.' in filename else filename
    if name_without_ext.upper() in reserved_names:
        filename = f"file_{filename}"
    
    return filename

def validate_email(email):
    """Valide un format d'email"""
    import re
    pattern = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'
    return re.match(pattern, email) is not None

def clean_text(text):
    """Nettoie un texte en supprimant les espaces superflus et les caractères spéciaux simples"""
    import re
    if not text:
        return ""
    text = re.sub(r'[^\w\s]', '', text)  # supprime la ponctuation
    text = re.sub(r'\s+', ' ', text)     # réduit les espaces
    return text.strip().lower()

from flask import jsonify

# def format_response(success=True, message="", data=None, status_code=200):
#     """Format standardisé pour les réponses API"""
#     response = {
#         "success": success,
#         "message": message,
#         "data": data
#     }
#     return jsonify(response), status_code
def format_response(answer, verification_status=None):
    if verification_status:
        return f"{answer}\n\n[Status: {verification_status}]"
    return answer

def generate_unique_filename(original_filename, prefix="file"):
    """Génère un nom de fichier unique sécurisé"""
    import uuid
    from werkzeug.utils import secure_filename
    ext = original_filename.rsplit('.', 1)[1].lower() if '.' in original_filename else 'txt'
    unique_name = f"{prefix}_{uuid.uuid4().hex}.{ext}"
    return secure_filename(unique_name)

def sanitize_input(text, max_length=1000):
    """Nettoie et limite un input utilisateur"""
    if not text:
        return ""
    
    # Supprimer les caractères de contrôle
    import re
    text = re.sub(r'[\x00-\x1f\x7f-\x9f]', '', text)
    
    # Limiter la longueur
    text = text[:max_length]
    
    # Nettoyer les espaces multiples
    text = re.sub(r'\s+', ' ', text).strip()
    
    return text

def get_current_timestamp():
    """Récupère le timestamp actuel"""
    return datetime.now()

def format_datetime(dt, format_str='%d/%m/%Y %H:%M'):
    """Formate une datetime en string"""
    if dt:
        return dt.strftime(format_str)
    return ""

def calculate_reading_time(text, words_per_minute=200):
    """Calcule le temps de lecture estimé d'un texte"""
    word_count = len(text.split())
    reading_time = max(1, round(word_count / words_per_minute))
    return reading_time

def extract_keywords(text, max_keywords=10):
    """Extrait les mots-clés d'un texte (version simple)"""
    import re
    from collections import Counter
    
    # Mots vides français et anglais (liste simple)
    stop_words = {
        'le', 'la', 'les', 'un', 'une', 'des', 'du', 'de', 'et', 'ou', 'où', 
        'mais', 'donc', 'car', 'ni', 'or', 'ce', 'cette', 'ces', 'son', 'sa',
        'ses', 'mon', 'ma', 'mes', 'ton', 'ta', 'tes', 'notre', 'nos', 'votre',
        'vos', 'leur', 'leurs', 'je', 'tu', 'il', 'elle', 'nous', 'vous', 'ils',
        'elles', 'que', 'qui', 'dont', 'sur', 'avec', 'dans', 'par', 'pour',
        'sans', 'sous', 'vers', 'chez', 'entre', 'jusqu', 'pendant', 'avant',
        'après', 'depuis', 'the', 'and', 'or', 'but', 'in', 'on', 'at', 'to',
        'for', 'of', 'with', 'by', 'a', 'an', 'is', 'are', 'was', 'were'
    }
    
    # Nettoyer et diviser le texte
    words = re.findall(r'\b[a-zA-Zàâäéèêëïîôöùûüÿñç]{3,}\b', text.lower())
    
    # Filtrer les mots vides
    keywords = [word for word in words if word not in stop_words]
    
    # Compter les occurrences
    word_counts = Counter(keywords)
    
    # Retourner les mots les plus fréquents
    return [word for word, count in word_counts.most_common(max_keywords)]

def create_breadcrumb(path_info):
    """Crée un fil d'Ariane basé sur les informations de chemin"""
    breadcrumb = []
    parts = path_info.strip('/').split('/')
    
    breadcrumb_map = {
        '': 'Accueil',
        'dashboard': 'Tableau de bord',
        'articles': 'Articles',
        'tools': 'Outils',
        'community': 'Communauté',
        'profile': 'Profil',
        'settings': 'Paramètres',
        'upload': 'Upload',
        'edit': 'Modifier',
        'view': 'Voir',
        'chatbot': 'Chatbot',
        'recommendations': 'Recommandations',
        'podcast': 'Podcast',
        'presentation': 'Présentation'
    }
    
    current_path = ''
    for part in parts:
        if part:
            current_path += f'/{part}'
            breadcrumb.append({
                'name': breadcrumb_map.get(part, part.title()),
                'url': current_path
            })
    
    return breadcrumb
def create_error_response(message="Une erreur est survenue", data=None, status_code=400):
    """Renvoie une réponse JSON standard pour une erreur"""
    response = {
        "success": False,
        "message": message,
        "data": data
    }
    return jsonify(response), status_code
from flask import jsonify

def create_success_response(message="Succès", data=None, status_code=200):
    """Renvoie une réponse JSON standard pour un succès"""
    response = {
        "success": True,
        "message": message,
        "data": data
    }
    return jsonify(response), status_code
