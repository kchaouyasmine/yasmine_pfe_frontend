from flask import Blueprint, request, render_template, redirect, url_for, flash, jsonify, session
from flask_login import login_user, logout_user, login_required, current_user
from werkzeug.security import check_password_hash
from werkzeug.utils import secure_filename
import re
import os
from PIL import Image
# from flask_bcrypt import Bcrypt
from werkzeug.security import check_password_hash
from flask_login import LoginManager, UserMixin

from backend.models.database import db
from backend.models.user import User, UserActivity
from backend.utils.validators import validate_email, validate_password, validate_username
from backend.utils.helpers import get_client_ip, get_user_agent, allowed_file, save_profile_picture
from backend.utils.decorators import json_required

# bcrypt = Bcrypt()
login_manager = LoginManager()
auth_bp = Blueprint('auth', __name__)

@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))

# Configuration pour les uploads d'images de profil
UPLOAD_FOLDER = 'frontend/static/uploads/avatars'
ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif'}
MAX_IMAGE_SIZE = (200, 200)  # Taille max pour les avatars

@auth_bp.route('/login', methods=['GET','POST'])
def login():
    """Page de connexion avec support API et formulaire HTML"""
    if current_user.is_authenticated:
        if request.is_json:
            return jsonify({
                'success': True,
                'message': 'Déjà connecté',
                'redirect_url': url_for('dashboard.index')
            })
        return redirect(url_for('dashboard.index'))
    
    if request.method == 'POST':
        if request.is_json:
            # API JSON
            data = request.get_json()
            username_or_email = data.get('username_or_email', '').strip()
            password = data.get('password', '')
            remember_me = data.get('remember_me', False)
        else:
            # Formulaire HTML
            username_or_email = request.form.get('username_or_email', '').strip()
            password = request.form.get('password', '')
            remember_me = bool(request.form.get('remember_me'))
        
        # Validation des champs
        if not username_or_email or not password:
            error_msg = "Veuillez remplir tous les champs"
            if request.is_json:
                return jsonify({'success': False, 'message': error_msg}), 400
            flash(error_msg, 'error')
            return render_template('auth/login.html')
        
        # Chercher l'utilisateur par username ou email
        user = None
        if '@' in username_or_email:
            user = User.query.filter_by(email=username_or_email, is_deleted=False).first()
        else:
            user = User.query.filter_by(username=username_or_email, is_deleted=False).first()
        
        # Vérifier utilisateur et mot de passe
        if user and check_password_hash(user.password_hash, password):
            if not user.is_active:
                error_msg = "Votre compte est désactivé. Contactez l'administration."
                if request.is_json:
                    return jsonify({'success': False, 'message': error_msg}), 403
                flash(error_msg, 'error')
                return render_template('auth/login.html')
            
            # Connexion réussie
            login_user(user, remember=remember_me)
            user.update_last_login()
            
            # Enregistrer l'activité
            activity = UserActivity(
                user_id=user.id,
                activity_type='login',
                activity_data={
                    'method': 'web',
                    'remember_me': remember_me,
                    'user_agent': get_user_agent()[:255]
                },
                ip_address=get_client_ip(),
                user_agent=get_user_agent()
            )
            db.session.add(activity)
            db.session.commit()
            
            success_msg = f"Bienvenue sur ArticSpace, {user.get_display_name()}!"
            
            if request.is_json:
                return jsonify({
                    'success': True,
                    'message': success_msg,
                    'user': user.to_dict(),
                    'redirect_url': url_for('dashboard.index')
                })
            
            flash(success_msg, 'success')
            
            # Redirection après connexion
            next_page = request.args.get('next')
            if next_page and next_page.startswith('/'):
                return redirect(next_page)
            return redirect(url_for('dashboard.index'))
        
        else:
            error_msg = "Nom d'utilisateur/email ou mot de passe incorrect"
            if request.is_json:
                return jsonify({'success': False, 'message': error_msg}), 401
            flash(error_msg, 'error')
    
    # return render_template('auth/login.html')
    return jsonify({
    'success': False,
    'message': 'Veuillez vous connecter',
    'requires_login': True
    }), 401

@auth_bp.route('/register', methods=['POST'])
def register():
    data = request.get_json()
    username = data.get('username', '').strip()
    email = data.get('email', '').strip()
    password = data.get('password', '')
    password_confirm = data.get('password_confirm', '')
    first_name = data.get('first_name', '').strip()
    last_name = data.get('last_name', '').strip()
    language = data.get('language', 'fr')
    accept_terms = data.get('accept_terms', False)

    # Validation des champs obligatoires
    if not accept_terms:
        return jsonify({'success': False, 'message': "Vous devez accepter les conditions d'utilisation."}), 400
    if not username or not email or not password or not password_confirm:
        return jsonify({'success': False, 'message': 'Tous les champs obligatoires doivent être remplis.'}), 400
    if password != password_confirm:
        return jsonify({'success': False, 'message': 'Les mots de passe ne correspondent pas.'}), 400

    # Autres validations (email, username, etc.) à ajouter ici si besoin

    try:
        user = User(
            username=username,
            email=email,
            first_name=first_name or None,
            last_name=last_name or None,
            preferred_language=language
        )
        user.set_password(password)
        db.session.add(user)
        db.session.commit()
        return jsonify({'success': True, 'message': 'Inscription réussie.'}), 201
    except Exception as e:
        return jsonify({'success': False, 'message': f'Erreur inscription: {e}'}), 500

@auth_bp.route('/logout', methods=['GET'])
@login_required
def logout():
    """Déconnexion avec enregistrement d'activité"""
    user_name = current_user.get_display_name()
    user_id = current_user.id
    
    # Enregistrer l'activité de déconnexion
    try:
        activity = UserActivity(
            user_id=user_id,
            activity_type='logout',
            activity_data={
                'method': 'web',
                'session_duration': (user_name)  # Placeholder - vous pouvez calculer la vraie durée
            },
            ip_address=get_client_ip(),
            user_agent=get_user_agent()
        )
        db.session.add(activity)
        db.session.commit()
    except Exception as e:
        print(f"Erreur enregistrement déconnexion: {e}")
    
    logout_user()
    
    if request.is_json:
        return jsonify({
            'success': True,
            'message': f"Au revoir, {user_name}!",
            'redirect_url': url_for('auth.login')
        })
    
    flash(f"Au revoir, {user_name}! À bientôt sur ArticSpace.", 'info')
    return redirect(url_for('auth.login'))

@auth_bp.route('/profile')
@login_required
def profile():
    """Page de profil utilisateur avec statistiques"""
    # Récupérer les statistiques utilisateur
    stats = current_user.get_stats()
    
    # Récupérer les activités récentes
    recent_activities = UserActivity.query.filter_by(user_id=current_user.id)\
                                         .order_by(UserActivity.created_at.desc())\
                                         .limit(10).all()
    
    # Récupérer les articles récents
    from backend.models.article import Article
    recent_articles = Article.query.filter_by(user_id=current_user.id, is_deleted=False)\
                                  .order_by(Article.created_at.desc())\
                                  .limit(5).all()
    
    return render_template('auth/profile.html', 
                         user=current_user, 
                         stats=stats,
                         recent_activities=recent_activities,
                         recent_articles=recent_articles)

@auth_bp.route('/profile/edit', methods=['GET', 'POST'])
@login_required
def edit_profile():
    """Modifier le profil utilisateur"""
    if request.method == 'POST':
        if request.is_json:
            data = request.get_json()
        else:
            data = request.form.to_dict()
        
        # Champs modifiables
        first_name = data.get('first_name', '').strip()
        last_name = data.get('last_name', '').strip()
        bio = data.get('bio', '').strip()
        preferred_language = data.get('preferred_language', 'fr')
        email_notifications = bool(data.get('email_notifications'))
        public_profile = bool(data.get('public_profile'))
        
        errors = []
        
        # Validation
        if first_name and (len(first_name) < 2 or len(first_name) > 50):
            errors.append("Le prénom doit contenir entre 2 et 50 caractères")
        
        if last_name and (len(last_name) < 2 or len(last_name) > 50):
            errors.append("Le nom doit contenir entre 2 et 50 caractères")
        
        if len(bio) > 500:
            errors.append("La bio ne peut pas dépasser 500 caractères")
        
        if preferred_language not in ['fr', 'en', 'de', 'es', 'it']:
            errors.append("Langue non supportée")
        
        if errors:
            if request.is_json:
                return jsonify({'success': False, 'message': '; '.join(errors)}), 400
            for error in errors:
                flash(error, 'error')
            return render_template('auth/profile.html')
        
        # Mise à jour
        try:
            current_user.first_name = first_name or None
            current_user.last_name = last_name or None
            current_user.bio = bio
            current_user.preferred_language = preferred_language
            current_user.email_notifications = email_notifications
            current_user.public_profile = public_profile
            
            db.session.commit()
            
            # Enregistrer l'activité
            activity = UserActivity(
                user_id=current_user.id,
                activity_type='profile_update',
                activity_data={
                    'updated_fields': [k for k, v in data.items() if v],
                    'language': preferred_language
                },
                ip_address=get_client_ip(),
                user_agent=get_user_agent()
            )
            db.session.add(activity)
            db.session.commit()
            
            success_msg = "Profil mis à jour avec succès!"
            
            if request.is_json:
                return jsonify({
                    'success': True,
                    'message': success_msg,
                    'user': current_user.to_dict()
                })
            
            flash(success_msg, 'success')
            return redirect(url_for('auth.profile'))
            
        except Exception as e:
            db.session.rollback()
            error_msg = "Erreur lors de la mise à jour du profil"
            print(f"Erreur mise à jour profil: {e}")
            
            if request.is_json:
                return jsonify({'success': False, 'message': error_msg}), 500
            flash(error_msg, 'error')
    
    return render_template('auth/edit_profile.html', user=current_user)

@auth_bp.route('/profile/upload-avatar', methods=['POST'])
@login_required
def upload_avatar():
    """Upload d'avatar utilisateur"""
    if 'avatar' not in request.files:
        error_msg = "Aucun fichier sélectionné"
        if request.is_json:
            return jsonify({'success': False, 'message': error_msg}), 400
        flash(error_msg, 'error')
        return redirect(url_for('auth.profile'))
    
    file = request.files['avatar']
    
    if file.filename == '':
        error_msg = "Aucun fichier sélectionné"
        if request.is_json:
            return jsonify({'success': False, 'message': error_msg}), 400
        flash(error_msg, 'error')
        return redirect(url_for('auth.profile'))
    
    if file and allowed_file(file.filename, ALLOWED_EXTENSIONS):
        try:
            # Créer le dossier s'il n'existe pas
            os.makedirs(UPLOAD_FOLDER, exist_ok=True)
            
            # Générer un nom de fichier sécurisé
            filename = f"user_{current_user.id}_{secure_filename(file.filename)}"
            filepath = os.path.join(UPLOAD_FOLDER, filename)
            
            # Sauvegarder et redimensionner l'image
            image = Image.open(file.stream)
            
            # Convertir en RGB si nécessaire
            if image.mode in ('RGBA', 'LA', 'P'):
                image = image.convert('RGB')
            
            # Redimensionner en gardant les proportions
            image.thumbnail(MAX_IMAGE_SIZE, Image.Resampling.LANCZOS)
            
            # Sauvegarder
            image.save(filepath, 'JPEG', quality=90)
            
            # Supprimer l'ancien avatar s'il existe
            if current_user.avatar_filename:
                old_filepath = os.path.join(UPLOAD_FOLDER, current_user.avatar_filename)
                if os.path.exists(old_filepath):
                    os.remove(old_filepath)
            
            # Mettre à jour en base
            current_user.avatar_filename = filename
            db.session.commit()
            
            # Enregistrer l'activité
            activity = UserActivity(
                user_id=current_user.id,
                activity_type='avatar_update',
                activity_data={'filename': filename},
                ip_address=get_client_ip(),
                user_agent=get_user_agent()
            )
            db.session.add(activity)
            db.session.commit()
            
            success_msg = "Avatar mis à jour avec succès!"
            
            if request.is_json:
                return jsonify({
                    'success': True,
                    'message': success_msg,
                    'avatar_url': url_for('static', filename=f'uploads/avatars/{filename}')
                })
            
            flash(success_msg, 'success')
            return redirect(url_for('auth.profile'))
            
        except Exception as e:
            error_msg = "Erreur lors du téléchargement de l'avatar"
            print(f"Erreur upload avatar: {e}")
            
            if request.is_json:
                return jsonify({'success': False, 'message': error_msg}), 500
            flash(error_msg, 'error')
            return redirect(url_for('auth.profile'))
    
    else:
        error_msg = "Format de fichier non supporté. Utilisez PNG, JPG, JPEG ou GIF."
        if request.is_json:
            return jsonify({'success': False, 'message': error_msg}), 400
        flash(error_msg, 'error')
        return redirect(url_for('auth.profile'))

@auth_bp.route('/change-password', methods=['POST'])
@login_required
def change_password():
    """Changer le mot de passe"""
    if request.is_json:
        data = request.get_json()
    else:
        data = request.form.to_dict()
    
    current_password = data.get('current_password', '')
    new_password = data.get('new_password', '')
    confirm_password = data.get('confirm_password', '')
    
    errors = []
    
    # Validation
    if not current_password:
        errors.append("Mot de passe actuel requis")
    elif not current_user.check_password(current_password):
        errors.append("Mot de passe actuel incorrect")
    
    if not new_password:
        errors.append("Nouveau mot de passe requis")
    elif not validate_password(new_password):
        errors.append("Le nouveau mot de passe doit contenir au moins 8 caractères, une majuscule, une minuscule et un chiffre")
    
    if new_password != confirm_password:
        errors.append("Les nouveaux mots de passe ne correspondent pas")
    
    if current_password == new_password:
        errors.append("Le nouveau mot de passe doit être différent de l'ancien")
    
    if errors:
        if request.is_json:
            return jsonify({'success': False, 'message': '; '.join(errors)}), 400
        for error in errors:
            flash(error, 'error')
        return redirect(url_for('auth.profile'))
    
    # Mise à jour
    try:
        current_user.set_password(new_password)
        db.session.commit()
        
        # Enregistrer l'activité
        activity = UserActivity(
            user_id=current_user.id,
            activity_type='password_change',
            activity_data={'method': 'web'},
            ip_address=get_client_ip(),
            user_agent=get_user_agent()
        )
        db.session.add(activity)
        db.session.commit()
        
        success_msg = "Mot de passe modifié avec succès!"
        
        if request.is_json:
            return jsonify({'success': True, 'message': success_msg})
        
        flash(success_msg, 'success')
        return redirect(url_for('auth.profile'))
        
    except Exception as e:
        db.session.rollback()
        error_msg = "Erreur lors de la modification du mot de passe"
        print(f"Erreur changement mot de passe: {e}")
        
        if request.is_json:
            return jsonify({'success': False, 'message': error_msg}), 500
        flash(error_msg, 'error')
        return redirect(url_for('auth.profile'))

@auth_bp.route('/delete-account', methods=['POST'])
@login_required
def delete_account():
    """Suppression (soft delete) du compte utilisateur"""
    if request.is_json:
        data = request.get_json()
    else:
        data = request.form.to_dict()
    
    password = data.get('password', '')
    confirm_deletion = bool(data.get('confirm_deletion', False))
    
    # Validation
    if not password:
        error_msg = "Mot de passe requis pour confirmer la suppression"
        if request.is_json:
            return jsonify({'success': False, 'message': error_msg}), 400
        flash(error_msg, 'error')
        return redirect(url_for('auth.profile'))
    
    if not current_user.check_password(password):
        error_msg = "Mot de passe incorrect"
        if request.is_json:
            return jsonify({'success': False, 'message': error_msg}), 401
        flash(error_msg, 'error')
        return redirect(url_for('auth.profile'))
    
    if not confirm_deletion:
        error_msg = "Vous devez confirmer la suppression de votre compte"
        if request.is_json:
            return jsonify({'success': False, 'message': error_msg}), 400
        flash(error_msg, 'error')
        return redirect(url_for('auth.profile'))
    
    try:
        user_name = current_user.get_display_name()
        user_id = current_user.id
        
        # Enregistrer l'activité de suppression
        activity = UserActivity(
            user_id=user_id,
            activity_type='account_deletion',
            activity_data={'method': 'web'},
            ip_address=get_client_ip(),
            user_agent=get_user_agent()
        )
        db.session.add(activity)
        
        # Soft delete
        current_user.soft_delete()
        db.session.commit()
        
        # Déconnexion
        logout_user()
        
        success_msg = f"Compte de {user_name} supprimé avec succès. Nous sommes désolés de vous voir partir."
        
        if request.is_json:
            return jsonify({
                'success': True,
                'message': success_msg,
                'redirect_url': url_for('main.landing')
            })
        
        flash(success_msg, 'info')
        return redirect(url_for('main.landing'))
        
    except Exception as e:
        db.session.rollback()
        error_msg = "Erreur lors de la suppression du compte"
        print(f"Erreur suppression compte: {e}")
        
        if request.is_json:
            return jsonify({'success': False, 'message': error_msg}), 500
        flash(error_msg, 'error')
        return redirect(url_for('auth.profile'))

# Routes API pour l'authentification
@auth_bp.route('/api/check-auth', methods=['GET'])
def check_auth():
    """Vérifier l'état d'authentification (API)"""
    if current_user.is_authenticated:
        return jsonify({
            'authenticated': True,
            'user': current_user.to_dict()
        })
    else:
        return jsonify({'authenticated': False}), 401

@auth_bp.route('/api/user-stats', methods=['GET'])
@login_required
def user_stats():
    """Récupérer les statistiques utilisateur (API)"""
    stats = current_user.get_stats()
    return jsonify({
        'success': True,
        'stats': stats
    })

@auth_bp.route('/me', methods=['GET'])
@login_required
def me():
    return jsonify({
        'id': current_user.id,
        'username': current_user.username,
        'email': current_user.email,
        'date_joined': current_user.date_joined
    })