"""
Service Podcast : Génération de script, audio et vidéo podcast scientifique.

Principales fonctions à utiliser :
- generate_improved_podcast_script(summary_text, lang_code, style, duration)
    => Génère un script de podcast structuré et émotionnel à partir d'un résumé scientifique.
- await generate_complete_emotional_podcast(script_text, lang_code, progress_callback=None, include_video=False)
    => Génère l'audio (mp3) et/ou la vidéo (mp4) du podcast à partir du script.

Les autres fonctions sont utilitaires (parsing, avatars, etc.).
"""

import os
import tempfile
from langdetect import detect
from .summarization_service import clean_think_blocks
import ollama
import re
import edge_tts
from pydub import AudioSegment
from pydub.effects import normalize
from PIL import Image, ImageDraw, ImageFilter, ImageFont, ImageEnhance
import shutil
import math
import random
import numpy as np
import cv2
import subprocess

def get_emotional_voice_mapping():
    """
    Mapping des voix Edge TTS qui supportent les émotions SSML
    """
    emotional_voice_map = {
        "fr": {
            "voice1": "fr-FR-DeniseNeural",      # Supporte cheerful, excited
            "voice2": "fr-FR-HenriNeural",       # Supporte friendly, calm
            "emotional_voices": {
                "excited": "fr-FR-DeniseNeural",
                "happy": "fr-FR-DeniseNeural", 
                "cheerful": "fr-FR-DeniseNeural",
                "friendly": "fr-FR-HenriNeural",
                "calm": "fr-FR-HenriNeural"
            }
        },
        "en": {
            "voice1": "en-US-AriaNeural",        # Très expressive
            "voice2": "en-US-GuyNeural",       # Voix masculine expressive
            "emotional_voices": {
                "excited": "en-US-AriaNeural",
                "happy": "en-US-AriaNeural",
                "cheerful": "en-US-AriaNeural", 
                "friendly": "en-US-JennyNeural",
                "calm": "en-US-DavisNeural",
                "enthusiastic": "en-US-AriaNeural"
            }
        },
        "de": {
            "voice1": "de-DE-KatjaNeural",
            "voice2": "de-DE-ConradNeural",
            "emotional_voices": {
                "excited": "de-DE-KatjaNeural",
                "cheerful": "de-DE-KatjaNeural",
                "friendly": "de-DE-ConradNeural"
            }
        },
        "es": {
            "voice1": "es-ES-ElviraNeural",
            "voice2": "es-ES-AlvaroNeural", 
            "emotional_voices": {
                "excited": "es-ES-ElviraNeural",
                "cheerful": "es-ES-ElviraNeural",
                "friendly": "es-ES-AlvaroNeural"
            }
        },
        "it": {
            "voice1": "it-IT-ElsaNeural",
            "voice2": "it-IT-GiuseppeNeural",
            "emotional_voices": {
                "excited": "it-IT-ElsaNeural",
                "cheerful": "it-IT-ElsaNeural", 
                "friendly": "it-IT-GiuseppeNeural"
            }
        }
    }
    return emotional_voice_map

def enhance_text_with_proper_ssml(text, emotions, lang_code):
    """Améliore le texte SANS balises SSML visibles"""
    import re
    
    # SIMPLEMENT nettoyer le texte des émotions entre parenthèses
    clean_text = re.sub(r'\([^)]*\)', '', text).strip()
    
    # Ne PAS ajouter de balises SSML - Edge TTS les gère automatiquement
    # via le choix de voix émotionnelles
    return clean_text


def select_best_voice_for_emotion(speaker, emotions, lang_code, default_voice_map):
    """Change de VOIX selon l'émotion (pas de SSML)"""
    
    # Voix de base
    base_voice = default_voice_map.get(speaker)
    is_female = (base_voice == "en-US-AriaNeural")
    
    if emotions and emotions != ['neutral']:
        primary_emotion = emotions[0]
        
        if primary_emotion in ['excited', 'enthusiastic']:
            return "en-US-AriaNeural" if is_female else "en-US-ChristopherNeural"
        elif primary_emotion in ['happy', 'cheerful']:
            return "en-US-JennyNeural" if is_female else "en-US-BrianNeural"  
        elif primary_emotion in ['calm', 'thoughtful']:
            return "en-US-SaraNeural" if is_female else "en-US-GuyNeural"
        elif primary_emotion in ['surprised']:
            return "en-US-AriaNeural" if is_female else "en-US-EricNeural"
    
    # Changer DavisNeural vers GuyNeural par défaut
    if base_voice == "en-US-DavisNeural":
        return "en-US-GuyNeural"
    
    return base_voice


async def generate_emotional_audio_segment(text, emotions, voice, lang_code):
    """Génère un segment audio SANS balises SSML problématiques"""
    try:
        # Utiliser directement le texte nettoyé
        clean_text = re.sub(r'\([^)]*\)', '', text).strip()
        
        print(f"🎤 Génération: {voice} -> {clean_text[:50]}...")
        
        # Edge TTS sans balises SSML
        communicate = edge_tts.Communicate(clean_text, voice)
        return communicate
        
    except Exception as e:
        print(f"❌ Erreur génération: {e}")
        # Fallback simple
        communicate = edge_tts.Communicate(text, voice)
        return communicate

# === FONCTIONS PRINCIPALES ===

def generate_improved_podcast_script(summary_text, lang_code="auto", style="Interview d'expert", duration="5-7 min"):
    """
    Génère un script de podcast avec formatage strict et support des émotions
    """
    if lang_code == "auto":
        lang_code = detect_language(summary_text)
        print(f"Langue détectée: {lang_code}")
    
    lang_info = get_language_info(lang_code)
    
    duration_guidelines = {
        "5-7 min": {
            "exchanges": 12,
            "words_per_exchange": "60-80 mots"
        },
        "8-12 min": {
            "exchanges": 18,
            "words_per_exchange": "80-100 mots"
        },
        "15-20 min": {
            "exchanges": 25,
            "words_per_exchange": "100-120 mots"
        }
    }
    
    duration_info = duration_guidelines.get(duration, duration_guidelines["5-7 min"])
    
    style_instructions = {
        "Conversation décontractée": "Casual and natural conversation style. Include emotions like (excited), (laughing), (smiling). Friendly and spontaneous tone with natural reactions.",
        "Interview d'expert": "Structured expert interview format. Include appropriate emotions like (nodding), (surprised), (enthusiastic). Professional yet approachable tone with detailed explanations.",
        "Débat scientifique": "Respectful scientific debate with different viewpoints. Include emotions like (concerned), (thoughtful), (convinced). Constructive discussion with evidence-based arguments.",
        "Vulgarisation": "Educational content for general audience. Include emotions like (smiling), (encouraging), (excited). Simple explanations with analogies and accessible language."
    }
    
    current_style = style_instructions.get(style, style_instructions["Interview d'expert"])
    
    language_output_instruction = {
        "fr": "The entire dialogue must be in French",
        "en": "The entire dialogue must be in English", 
        "de": "The entire dialogue must be in German",
        "es": "The entire dialogue must be in Spanish",
        "it": "The entire dialogue must be in Italian"
    }
    
    output_lang = language_output_instruction.get(lang_code, "The entire dialogue must be in English")
    
    prompt = f"""
You are an expert podcast script writer. Create a scientific podcast dialogue with natural emotions.

CRITICAL FORMATTING RULES:
- Use ONLY this format: "Speaker Name: dialogue text here"
- NO markdown, NO asterisks, NO brackets around speaker names
- Include emotions in parentheses within the dialogue text
- NO section headers, NO stage directions outside dialogue
- Start directly with the dialogue

SPEAKERS:
- {lang_info['host1']} (first speaker)
- {lang_info['host2']} (second speaker)

REQUIREMENTS:
- {output_lang}
- Style: {current_style}
- Generate exactly {duration_info['exchanges']} exchanges
- Each exchange: {duration_info['words_per_exchange']}
- Include emotions in parentheses like (excited), (nodding), (surprised), (laughing), (thoughtful)

TOPIC TO DISCUSS:
{summary_text}

EXACT FORMAT EXAMPLE:
{lang_info['host1']}: Hello everyone! (excited) Today we're exploring an amazing breakthrough in AI research.
{lang_info['host2']}: (nodding enthusiastically) That's absolutely right! This research represents a significant leap forward.

Generate the complete podcast script now, following the exact format above:
"""
    
    try:
        import ollama
        response = ollama.chat(
            model="DeepSeek-R1",
            messages=[{"role": "user", "content": prompt}],
            options={
                "temperature": 0.6,
                "top_p": 0.8,
                "num_predict": 5000
            }
        )
        raw_script = response["message"]["content"]
        cleaned_script = clean_think_blocks(raw_script)
        
        dialogue_parts = parse_enhanced_podcast_script(cleaned_script)
        print(f"Script généré: {len(dialogue_parts)} échanges (cible: {duration_info['exchanges']})")
        
        return cleaned_script
        
    except Exception as e:
        return f"Erreur lors de la génération du script: {str(e)}"

def parse_enhanced_podcast_script(script_text):
    """
    Parse le script avec support des émotions et nettoyage amélioré
    """
    dialogue_parts = []
    lines = script_text.strip().split('\n')
    
    ignore_patterns = [
        r'^#{1,6}\s',
        r'^\*{1,3}\[.*?\]\*{1,3}$',
        r'^---+$',
        r'^\*{2,}.*?\*{2,}$',
        r'^### Podcast Script:',
        r'^Dr\. .* and Prof\. .* on .*$',
        r'^\[.*\]$',
        r'^Podcast Script:',
        r'^\*{2,}\[.*?\]\*{2,}$',
        r'^\*\*\[.*?\]\*\*$',
        r'^\d+\.\s*$',
        r'^\s*\*\*Podcast Script:\*\*\s*$'
    ]
    
    for line in lines:
        line = line.strip()
        if not line:
            continue
            
        should_ignore = False
        for pattern in ignore_patterns:
            if re.match(pattern, line, re.IGNORECASE):
                should_ignore = True
                break
        
        if should_ignore:
            continue
            
        speaker, text = extract_enhanced_dialogue(line)
        
        if speaker and text and len(text) > 10:
            cleaned_text = clean_emotions_from_script(text)
            
            dialogue_parts.append({
                'speaker': speaker,
                'text': cleaned_text,
                'original_text': text
            })
    
    print(f"Script parsé: {len(dialogue_parts)} segments trouvés")
    return dialogue_parts

def extract_enhanced_dialogue(line):
    """
    Extraction améliorée du dialogue avec support des formats variés
    """
    line = re.sub(r'^\*+', '', line)
    line = re.sub(r'\*+$', '', line)
    
    speaker = None
    text = None
    
    if re.match(r'^\*[^*]+\]:\*', line):
        match = re.match(r'^\*([^*]+)\]:\*\s*(.*)', line)
        if match:
            speaker = match.group(1).strip()
            text = match.group(2).strip()
    elif line.startswith('[') and ']:' in line:
        bracket_end = line.find(']:')
        if bracket_end != -1:
            speaker = line[1:bracket_end].strip()
            text = line[bracket_end + 2:].strip()
    elif ':' in line and not line.startswith('http'):
        parts = line.split(':', 1)
        if len(parts) == 2:
            raw_speaker = parts[0].strip()
            text = parts[1].strip()
            speaker = clean_speaker_name(raw_speaker)
    
    return speaker, text


def clean_emotions_from_script(text):
    """Nettoie TOUT le formatage pour la synthèse vocale"""
    import re
    
    # Supprimer les émotions entre parenthèses
    clean_text = re.sub(r'\([^)]*\)', '', text).strip()
    
    # ✅ AJOUTER : Supprimer TOUT le formatage markdown
    clean_text = re.sub(r'\*\*([^*]+)\*\*', r'\1', clean_text)  # **texte** → texte
    clean_text = re.sub(r'\*([^*]+)\*', r'\1', clean_text)      # *texte* → texte
    clean_text = re.sub(r'__([^_]+)__', r'\1', clean_text)      # __texte__ → texte
    clean_text = re.sub(r'_([^_]+)_', r'\1', clean_text)        # _texte_ → texte
    clean_text = re.sub(r'`([^`]+)`', r'\1', clean_text)        # `texte` → texte
    
    # Supprimer tous les astérisques et underscores isolés
    clean_text = re.sub(r'\*+', '', clean_text)
    clean_text = re.sub(r'_+', '', clean_text)
    clean_text = re.sub(r'`+', '', clean_text)
    
    # Nettoyer les espaces multiples
    clean_text = re.sub(r'\s+', ' ', clean_text)
    
    return clean_text.strip()

# === FONCTIONS UTILITAIRES (parsing, avatars, audio, etc.) ===

def create_enhanced_avatar(name, gender, color_scheme, size=(300, 400)):
    """
    Crée un avatar plus détaillé et expressif
    """
    width, height = size
    img = Image.new('RGBA', (width, height), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    
    head_center_x = width // 2
    head_center_y = height // 3
    head_radius = 80
    
    # Corps
    body_width = 60
    body_height = 150
    body_x = head_center_x - body_width // 2
    body_y = head_center_y + head_radius + 10
    
    draw.rectangle([body_x, body_y, body_x + body_width, body_y + body_height], 
                   fill=color_scheme["clothing"], outline=(0, 0, 0), width=2)
    
    # Cou
    neck_width = 30
    neck_height = 20
    neck_x = head_center_x - neck_width // 2
    neck_y = head_center_y + head_radius - 5
    draw.rectangle([neck_x, neck_y, neck_x + neck_width, neck_y + neck_height], 
                   fill=color_scheme["skin"])
    
    # Cheveux en arrière-plan
    hair_color = color_scheme["hair"]
    if gender == "female":
        draw.ellipse([head_center_x - head_radius - 15, head_center_y - head_radius - 15, 
                     head_center_x + head_radius + 15, head_center_y + head_radius + 40], 
                     fill=hair_color)
    else:
        draw.ellipse([head_center_x - head_radius - 5, head_center_y - head_radius - 10, 
                     head_center_x + head_radius + 5, head_center_y + head_radius - 20], 
                     fill=hair_color)
    
    # Tête
    draw.ellipse([head_center_x - head_radius, head_center_y - head_radius, 
                  head_center_x + head_radius, head_center_y + head_radius], 
                 fill=color_scheme["skin"], outline=(0, 0, 0), width=3)
    
    base_img = img.copy()
    
    return {
        "base": base_img,
        "size": size,
        "head_center": (head_center_x, head_center_y),
        "color_scheme": color_scheme,
        "gender": gender
    }

def create_animated_frame(avatar_data, expression, is_speaking=False, speak_intensity=0.5):
    """
    Crée un frame animé de l'avatar avec l'expression donnée
    """
    frame = avatar_data["base"].copy()
    draw = ImageDraw.Draw(frame)
    
    center_x, center_y = avatar_data["head_center"]
    
    # Créer l'expression appropriée
    if expression == "speaking":
        create_speaking_animation(draw, center_x, center_y, speak_intensity)
    elif expression == "excited":
        create_excited_face(draw, center_x, center_y)
    elif expression == "happy":
        create_happy_face(draw, center_x, center_y)
    elif expression == "surprised":
        create_surprised_face(draw, center_x, center_y)
    elif expression == "thoughtful":
        create_thoughtful_face(draw, center_x, center_y)
    else:
        create_neutral_face(draw, center_x, center_y)
    
    # Micro-mouvements si en train de parler
    if is_speaking:
        if random.random() < 0.1:
            add_blink_animation(draw, center_x, center_y)
    
    return frame

def create_neutral_face(draw, center_x, center_y):
    """Visage neutre"""
    eye_y = center_y - 20
    left_eye_x = center_x - 25
    right_eye_x = center_x + 25
    
    # Yeux
    draw.ellipse([left_eye_x - 12, eye_y - 8, left_eye_x + 12, eye_y + 8], fill=(255, 255, 255))
    draw.ellipse([right_eye_x - 12, eye_y - 8, right_eye_x + 12, eye_y + 8], fill=(255, 255, 255))
    draw.ellipse([left_eye_x - 5, eye_y - 5, left_eye_x + 5, eye_y + 5], fill=(0, 0, 0))
    draw.ellipse([right_eye_x - 5, eye_y - 5, right_eye_x + 5, eye_y + 5], fill=(0, 0, 0))
    
    # Sourcils
    draw.arc([left_eye_x - 15, eye_y - 20, left_eye_x + 15, eye_y - 10], 0, 180, fill=(101, 67, 33), width=3)
    draw.arc([right_eye_x - 15, eye_y - 20, right_eye_x + 15, eye_y - 10], 0, 180, fill=(101, 67, 33), width=3)
    
    # Nez
    nose_y = center_y
    draw.ellipse([center_x - 3, nose_y - 5, center_x + 3, nose_y + 5], outline=(0, 0, 0), width=1)
    
    # Bouche
    mouth_y = center_y + 25
    draw.line([center_x - 15, mouth_y, center_x + 15, mouth_y], fill=(0, 0, 0), width=2)

def create_speaking_animation(draw, center_x, center_y, intensity):
    """Animation de parole avec intensité variable"""
    create_neutral_face(draw, center_x, center_y)
    
    mouth_y = center_y + 25
    mouth_width = int(8 + intensity * 10)
    mouth_height = int(4 + intensity * 8)
    
    # Effacer l'ancienne bouche
    draw.rectangle([center_x - 20, mouth_y - 8, center_x + 20, mouth_y + 12], 
                  fill=(255, 220, 177))
    
    # Nouvelle bouche animée
    draw.ellipse([center_x - mouth_width, mouth_y - mouth_height//2, 
                  center_x + mouth_width, mouth_y + mouth_height], 
                fill=(50, 50, 50), outline=(0, 0, 0), width=2)
    
    if intensity > 0.3:
        teeth_width = mouth_width - 2
        teeth_height = max(1, mouth_height//2)
        draw.ellipse([center_x - teeth_width, mouth_y - teeth_height//2, 
                      center_x + teeth_width, mouth_y + teeth_height//2], 
                    fill=(255, 255, 255))

def create_excited_face(draw, center_x, center_y):
    """Visage excité avec grands yeux et sourire"""
    eye_y = center_y - 20
    left_eye_x = center_x - 25
    right_eye_x = center_x + 25
    
    # Grands yeux
    draw.ellipse([left_eye_x - 15, eye_y - 12, left_eye_x + 15, eye_y + 12], fill=(255, 255, 255))
    draw.ellipse([right_eye_x - 15, eye_y - 12, right_eye_x + 15, eye_y + 12], fill=(255, 255, 255))
    draw.ellipse([left_eye_x - 7, eye_y - 7, left_eye_x + 7, eye_y + 7], fill=(0, 0, 0))
    draw.ellipse([right_eye_x - 7, eye_y - 7, right_eye_x + 7, eye_y + 7], fill=(0, 0, 0))
    
    # Reflets
    draw.ellipse([left_eye_x - 2, eye_y - 4, left_eye_x + 2, eye_y], fill=(255, 255, 255))
    draw.ellipse([right_eye_x - 2, eye_y - 4, right_eye_x + 2, eye_y], fill=(255, 255, 255))
    
    # Sourcils levés
    draw.arc([left_eye_x - 15, eye_y - 25, left_eye_x + 15, eye_y - 15], 0, 180, fill=(101, 67, 33), width=3)
    draw.arc([right_eye_x - 15, eye_y - 25, right_eye_x + 15, eye_y - 15], 0, 180, fill=(101, 67, 33), width=3)
    
    # Nez
    nose_y = center_y
    draw.ellipse([center_x - 3, nose_y - 5, center_x + 3, nose_y + 5], outline=(0, 0, 0), width=1)
    
    # Grand sourire
    mouth_y = center_y + 25
    draw.arc([center_x - 20, mouth_y - 10, center_x + 20, mouth_y + 10], 0, 180, fill=(255, 0, 100), width=4)

def create_thoughtful_face(draw, center_x, center_y):
    """Visage pensif"""
    create_neutral_face(draw, center_x, center_y)
    
    # Sourcils froncés
    eye_y = center_y - 20
    left_eye_x = center_x - 25
    right_eye_x = center_x + 25
    
    draw.line([left_eye_x - 10, eye_y - 18, left_eye_x + 5, eye_y - 15], fill=(101, 67, 33), width=3)
    draw.line([right_eye_x - 5, eye_y - 15, right_eye_x + 10, eye_y - 18], fill=(101, 67, 33), width=3)

def create_happy_face(draw, center_x, center_y):
    """Visage heureux"""
    create_neutral_face(draw, center_x, center_y)
    
    mouth_y = center_y + 25
    draw.arc([center_x - 15, mouth_y - 5, center_x + 15, mouth_y + 10], 0, 180, fill=(255, 0, 100), width=3)

def create_surprised_face(draw, center_x, center_y):
    """Visage surpris"""
    eye_y = center_y - 20
    left_eye_x = center_x - 25
    right_eye_x = center_x + 25
    
    # Yeux très ouverts
    draw.ellipse([left_eye_x - 18, eye_y - 15, left_eye_x + 18, eye_y + 15], fill=(255, 255, 255))
    draw.ellipse([right_eye_x - 18, eye_y - 15, right_eye_x + 18, eye_y + 15], fill=(255, 255, 255))
    draw.ellipse([left_eye_x - 8, eye_y - 8, left_eye_x + 8, eye_y + 8], fill=(0, 0, 0))
    draw.ellipse([right_eye_x - 8, eye_y - 8, right_eye_x + 8, eye_y + 8], fill=(0, 0, 0))
    
    # Sourcils très hauts
    draw.arc([left_eye_x - 15, eye_y - 30, left_eye_x + 15, eye_y - 20], 0, 180, fill=(101, 67, 33), width=3)
    draw.arc([right_eye_x - 15, eye_y - 30, right_eye_x + 15, eye_y - 20], 0, 180, fill=(101, 67, 33), width=3)
    
    # Nez
    nose_y = center_y
    draw.ellipse([center_x - 3, nose_y - 5, center_x + 3, nose_y + 5], outline=(0, 0, 0), width=1)
    
    # Bouche surprise
    mouth_y = center_y + 25
    draw.ellipse([center_x - 6, mouth_y - 3, center_x + 6, mouth_y + 12], 
                fill=(50, 50, 50), outline=(0, 0, 0), width=2)

def add_blink_animation(draw, center_x, center_y):
    """Ajoute un clignement d'yeux"""
    eye_y = center_y - 20
    left_eye_x = center_x - 25
    right_eye_x = center_x + 25
    
    draw.line([left_eye_x - 12, eye_y, left_eye_x + 12, eye_y], fill=(0, 0, 0), width=3)
    draw.line([right_eye_x - 12, eye_y, right_eye_x + 12, eye_y], fill=(0, 0, 0), width=3)

def create_enhanced_podcast_avatars(lang_code):
    """
    Crée des avatars améliorés pour les speakers
    """
    avatars = {}
    speaker_info = get_language_info(lang_code)
    
    avatar1 = create_enhanced_avatar(
        name=speaker_info["host1"],
        gender="female",
        color_scheme={
            "hair": (139, 69, 19),
            "skin": (255, 220, 177),
            "clothing": (70, 130, 180)
        }
    )
    
    avatar2 = create_enhanced_avatar(
        name=speaker_info["host2"],
        gender="male", 
        color_scheme={
            "hair": (101, 67, 33),
            "skin": (255, 219, 172),
            "clothing": (128, 128, 128)
        }
    )
    
    avatars[speaker_info["host1"]] = avatar1
    avatars[speaker_info["host2"]] = avatar2
    
    return avatars

async def generate_complete_emotional_podcast(script_text, lang_code="auto", progress_callback=None, include_video=False):
    """
    Génère l'audio du podcast avec émotions ET optionnellement la vidéo avec avatars animés
    """
    if lang_code == "auto":
        sample_text = script_text[:300]
        lang_code = detect_language(sample_text)
    
    # Utiliser les voix émotionnelles
    emotional_voices = get_emotional_voice_mapping()
    voices = emotional_voices.get(lang_code, emotional_voices["en"])
    
    dialogue_parts = parse_enhanced_podcast_script(script_text)
    
    if not dialogue_parts:
        if progress_callback:
            progress_callback(0, "Erreur: Script mal formaté")
        return None, None
    
    temp_dir = tempfile.mkdtemp()
    
    try:
        if progress_callback:
            progress_callback(0.1, "Génération des segments audio émotionnels...")
        
        speaker_voice_map = create_consistent_voice_mapping(dialogue_parts, voices, lang_code)
        audio_segments = []
        video_info = [] if include_video else None
        
        total_parts = len(dialogue_parts)
        
        for i, part in enumerate(dialogue_parts):
            try:
                progress = 0.1 + (i / total_parts) * 0.6
                if progress_callback:
                    progress_callback(progress, f"Génération segment émotionnel {i+1}/{total_parts}...")
                
                # Extraire les émotions
                emotions = extract_emotions_from_text(part.get('original_text', part['text']))
                
                # Sélectionner la meilleure voix pour cette émotion
                voice = speaker_voice_map.get(part['speaker'])
                if not voice:
                    print(f"❌ ERREUR: Pas de voix pour {part['speaker']}")
                    voice = voices['voice1']  # Fallback

                # AJOUTER DEBUG pour vérifier l'alternance
                voice_type = "👩 FEMME" if voice == voices['voice1'] else "👨 HOMME"
                print(f"🎤 Segment {i+1}: '{part['speaker']}' → {voice_type} ({voice})")
                
                # Générer l'audio émotionnel
                communicate = await generate_emotional_audio_segment(
                    part['text'], emotions, voice, lang_code
                )
                
                segment_path = os.path.join(temp_dir, f"segment_{i:03d}.wav")
                await communicate.save(segment_path)
                
                if not os.path.exists(segment_path):
                    raise Exception(f"Échec de la création du segment {i}")
                
                segment = AudioSegment.from_file(segment_path)
                segment = normalize(segment)
                
                # Pause réduite entre segments
                if i > 0:
                    pause = AudioSegment.silent(duration=600)  # 600ms
                    audio_segments.append(pause)
                    if include_video:
                        video_info.append({"type": "pause", "duration": 0.6})
                
                audio_segments.append(segment)
                
                # Information pour la vidéo
                if include_video:
                    video_info.append({
                        "type": "speech",
                        "speaker": part['speaker'],
                        "duration": len(segment) / 1000.0,
                        "emotions": emotions,
                        "text": part['text']
                    })
                
            except Exception as segment_error:
                print(f"Erreur segment {i}: {segment_error}")
                continue
        
        if not audio_segments:
            raise Exception("Aucun segment audio généré avec succès")
        
        if progress_callback:
            progress_callback(0.75, "Mixage audio...")
        
        # Combiner tous les segments
        final_audio = AudioSegment.empty()
        for segment in audio_segments:
            final_audio += segment
        
        final_audio = post_process_audio(final_audio)
        
        print(f"Durée finale de l'audio: {len(final_audio) / 1000:.1f} secondes")
        
        # Exporter en MP3
        output_path = os.path.join(temp_dir, "podcast_final.mp3")
        final_audio.export(output_path, format="mp3", bitrate="128k")
        
        if not os.path.exists(output_path):
            raise Exception("Échec de l'exportation MP3")
        
        # Lire le fichier final
        with open(output_path, "rb") as f:
            audio_bytes = f.read()
        
        # Générer la vidéo si demandée
        video_bytes = None
        if include_video and video_info:
            if progress_callback:
                progress_callback(0.80, "Génération de la vidéo animée...")
            video_bytes = await generate_enhanced_podcast_video(
                video_info, final_audio, temp_dir, lang_code, progress_callback
            )
        
        if progress_callback:
            progress_callback(1.0, "Terminé!")
        
        return audio_bytes, video_bytes
        
    except Exception as e:
        error_msg = f"Erreur génération audio: {str(e)}"
        print(error_msg)
        if progress_callback:
            progress_callback(0, error_msg)
        return None, None
    finally:
        try:
            shutil.rmtree(temp_dir, ignore_errors=True)
        except:
            pass

# ==================== GÉNÉRATION VIDÉO AVEC AVATARS ====================

async def generate_enhanced_podcast_video(video_info, audio, temp_dir, lang_code, progress_callback=None):
    """
    Génère une vidéo MP4 avec animations fluides et synchronisation audio
    """
    try:
        if progress_callback:
            progress_callback(0.85, "Création des avatars animés...")
        
        # Créer les avatars améliorés
        avatars = create_enhanced_podcast_avatars(lang_code)
        
        # Paramètres vidéo
        width, height = 1280, 720
        fps = 30
        
        # Calculer la durée totale
        total_duration = len(audio) / 1000.0  # en secondes
        total_frames = int(total_duration * fps)
        
        if progress_callback:
            progress_callback(0.90, "Génération des frames vidéo...")
        
        # Créer le writer vidéo
        fourcc = cv2.VideoWriter_fourcc(*'mp4v')
        video_path = os.path.join(temp_dir, "podcast_video.mp4")
        out = cv2.VideoWriter(video_path, fourcc, fps, (width, height))
        
        current_time = 0
        current_speaker = None
        current_segment = None
        
        for frame_num in range(total_frames):
            # Calculer le temps actuel
            current_time = frame_num / fps
            
            # Déterminer quel segment est actif
            segment_time = 0
            for segment in video_info:
                if segment["type"] == "speech":
                    if segment_time <= current_time < segment_time + segment["duration"]:
                        current_segment = segment
                        current_speaker = segment["speaker"]
                        break
                elif segment["type"] == "pause":
                    if segment_time <= current_time < segment_time + segment["duration"]:
                        current_segment = {"type": "pause", "speaker": current_speaker}
                        break
                segment_time += segment["duration"]
            
            # Calculer l'intensité de la parole
            speak_intensity = 0.5
            if current_segment and current_segment["type"] == "speech":
                speak_intensity = 0.3 + 0.4 * abs(math.sin(current_time * 8))  # 8 Hz pour la parole
            
            # Créer le frame
            frame = create_enhanced_video_frame(
                avatars, current_speaker, current_segment, 
                width, height, speak_intensity, frame_num
            )
            
            # Convertir PIL en OpenCV
            frame_cv = cv2.cvtColor(np.array(frame), cv2.COLOR_RGB2BGR)
            out.write(frame_cv)
            
            # Mise à jour du progrès
            if frame_num % 30 == 0 and progress_callback:  # Chaque seconde
                progress = 0.90 + (frame_num / total_frames) * 0.05
                progress_callback(progress, f"Frame {frame_num}/{total_frames}")
        
        out.release()
        
        if progress_callback:
            progress_callback(0.98, "Synchronisation audio-vidéo...")
        
        # Combiner audio et vidéo avec FFmpeg
        final_video_path = os.path.join(temp_dir, "podcast_final.mp4")
        audio_path = os.path.join(temp_dir, "podcast_final.wav")
        audio.export(audio_path, format="wav")
        
        # Commande FFmpeg améliorée
        cmd = f'ffmpeg -y -i "{video_path}" -i "{audio_path}" -c:v libx264 -c:a aac -pix_fmt yuv420p -shortest "{final_video_path}"'
        
        try:
            import subprocess
            result = subprocess.run(cmd, shell=True, capture_output=True, text=True)
            
            if result.returncode == 0 and os.path.exists(final_video_path):
                with open(final_video_path, "rb") as f:
                    return f.read()
            else:
                print(f"Erreur FFmpeg: {result.stderr}")
                # Fallback: retourner la vidéo sans audio
                with open(video_path, "rb") as f:
                    return f.read()
        except Exception as e:
            print(f"Erreur lors de la combinaison audio-vidéo: {e}")
            with open(video_path, "rb") as f:
                return f.read()
        
    except Exception as e:
        print(f"Erreur génération vidéo: {e}")
        return None

def create_enhanced_video_frame(avatars, current_speaker, active_segment, width, height, speak_intensity, frame_num):
    """
    Crée un frame vidéo amélioré avec animations fluides
    """
    # Créer le fond avec dégradé
    frame = Image.new('RGB', (width, height))
    draw = ImageDraw.Draw(frame)
    
    # Dégradé de fond
    for y in range(height):
        color_ratio = y / height
        r = int(240 + (248 - 240) * color_ratio)
        g = int(248 + (255 - 248) * color_ratio)
        b = int(255 + (255 - 255) * color_ratio)
        draw.line([(0, y), (width, y)], fill=(r, g, b))
    
    # Titre avec ombre
    try:
        title_font = ImageFont.truetype("arial.ttf", 50)
        subtitle_font = ImageFont.truetype("arial.ttf", 24)
    except:
        title_font = ImageFont.load_default()
        subtitle_font = ImageFont.load_default()
    
    # Ombre du titre
    draw.text((width//2 - 198, 52), "Scientific Podcast", fill=(150, 150, 150), font=title_font)
    # Titre principal
    draw.text((width//2 - 200, 50), "Scientific Podcast", fill=(70, 130, 180), font=title_font)
    
    # Sous-titre
    draw.text((width//2 - 120, 110), "AI-Generated Discussion", fill=(100, 100, 100), font=subtitle_font)
    
    # Positions des avatars
    avatar1_pos = (200, 200)
    avatar2_pos = (880, 200)
    
    # Dessiner les avatars avec animations
    for i, (speaker_name, avatar_data) in enumerate(avatars.items()):
        is_speaking = (speaker_name == current_speaker and 
                      active_segment and active_segment.get("type") == "speech")
        
        # Déterminer l'expression
        expression = "neutral"
        if is_speaking:
            if active_segment and "excited" in active_segment.get("emotions", []):
                expression = "excited"
            elif active_segment and "happy" in active_segment.get("emotions", []):
                expression = "happy"
            elif active_segment and "surprised" in active_segment.get("emotions", []):
                expression = "surprised"
            else:
                expression = "speaking"
        
        # Créer le frame animé
        avatar_frame = create_animated_frame(
            avatar_data, expression, is_speaking, speak_intensity
        )
        
        # Redimensionner selon l'état
        if is_speaking:
            # Avatar actif plus grand avec effet de "pulse"
            pulse_factor = 1.0 + 0.05 * math.sin(frame_num * 0.2)  # Pulse lent
            new_size = (int(300 * pulse_factor), int(400 * pulse_factor))
            avatar_frame = avatar_frame.resize(new_size, Image.Resampling.LANCZOS)
        else:
            # Avatar inactif normal
            avatar_frame = avatar_frame.resize((250, 350), Image.Resampling.LANCZOS)
        
        # Position
        pos = avatar1_pos if i == 0 else avatar2_pos
        
        # Ajouter une ombre douce
        shadow_offset = 5
        shadow_color = (200, 200, 200, 128)
        shadow = Image.new('RGBA', avatar_frame.size, (0, 0, 0, 0))
        shadow_draw = ImageDraw.Draw(shadow)
        shadow_draw.ellipse([shadow_offset, shadow_offset, 
                           avatar_frame.size[0] + shadow_offset, 
                           avatar_frame.size[1] + shadow_offset], 
                          fill=shadow_color)
        
        # Dessiner l'ombre
        frame.paste(shadow, (pos[0] - shadow_offset, pos[1] - shadow_offset), shadow)
        
        # Dessiner l'avatar
        frame.paste(avatar_frame, pos, avatar_frame if avatar_frame.mode == 'RGBA' else None)
        
        # Nom du speaker avec fond
        name_y = pos[1] + avatar_frame.size[1] + 10
        name_bg_width = len(speaker_name) * 12 + 20
        draw.rectangle([pos[0], name_y, pos[0] + name_bg_width, name_y + 30], 
                      fill=(255, 255, 255, 200))
        draw.text((pos[0] + 10, name_y + 5), speaker_name, fill=(0, 0, 0), font=subtitle_font)
        
        # Indicateur de parole animé
        if is_speaking:
            # Onde sonore animée
            wave_x = pos[0] - 30
            wave_y = pos[1] + 100
            for j in range(5):
                wave_height = 20 + 15 * math.sin(frame_num * 0.3 + j)
                draw.ellipse([wave_x - 5, wave_y - wave_height//2, 
                             wave_x + 5, wave_y + wave_height//2], 
                            fill=(255, 0, 100))
                wave_x -= 15
    
    # Barre de progression en bas
    progress_width = width - 100
    progress_height = 8
    progress_x = 50
    progress_y = height - 50
    
    # Fond de la barre
    draw.rectangle([progress_x, progress_y, progress_x + progress_width, progress_y + progress_height], 
                  fill=(200, 200, 200))
    
    # Progression (basée sur le numéro de frame)
    if active_segment:
        # Calculer le progrès approximatif
        total_frames_approx = 30 * 300  # Estimation
        progress_ratio = min(frame_num / total_frames_approx, 1.0)
        progress_fill_width = int(progress_width * progress_ratio)
        draw.rectangle([progress_x, progress_y, progress_x + progress_fill_width, progress_y + progress_height], 
                      fill=(70, 130, 180))
    
    return frame

def get_language_info(lang_code):
    """Retourne les informations de langue pour le podcast"""
    language_prompts = {
        "fr": {
            "host1": "Dr. Marie",
            "host2": "Prof. Thomas", 
            "intro": "Bonjour et bienvenue dans notre podcast scientifique",
            "outro": "Merci de nous avoir écoutés, à bientôt !",
            "language_name": "français"
        },
        "en": {
            "host1": "Dr. Sarah",
            "host2": "Prof. Michael",
            "intro": "Hello and welcome to our science podcast",
            "outro": "Thank you for listening, see you next time!",
            "language_name": "English"
        },
        "de": {
            "host1": "Dr. Anna",
            "host2": "Prof. Klaus",
            "intro": "Hallo und willkommen zu unserem Wissenschafts-Podcast",
            "outro": "Vielen Dank fürs Zuhören, bis zum nächsten Mal!",
            "language_name": "Deutsch"
        },
        "es": {
            "host1": "Dra. Carmen",
            "host2": "Prof. Ricardo",
            "intro": "Hola y bienvenidos a nuestro podcast científico",
            "outro": "Gracias por escucharnos, ¡hasta la próxima!",
            "language_name": "español"
        },
        "it": {
            "host1": "Dr.ssa Elena",
            "host2": "Prof. Marco",
            "intro": "Ciao e benvenuti al nostro podcast scientifico",
            "outro": "Grazie per averci ascoltato, alla prossima!",
            "language_name": "italiano"
        }
    }
    return language_prompts.get(lang_code, language_prompts["en"])






def post_process_script(script_text):
    """
    Post-traite le script pour s'assurer qu'il respecte le format attendu
    """
    lines = script_text.strip().split('\n')
    processed_lines = []
    
    for line in lines:
        line = line.strip()
        
        # Ignorer les lignes vides et les métadonnées
        if not line or line.startswith('**') or line.startswith('#') or line.startswith('---'):
            continue
        
        # Nettoyer le formatage markdown
        line = re.sub(r'^\*+', '', line)  # Supprimer * au début
        line = re.sub(r'\*+$', '', line)  # Supprimer * à la fin
        line = re.sub(r'\*\*([^*]+)\*\*', r'\1', line)  # **texte** -> texte
        
        # S'assurer que la ligne contient un speaker et du dialogue
        if ':' in line and not line.startswith('http'):
            # Nettoyer les crochets autour du nom du speaker si présents
            line = re.sub(r'^\[([^\]]+)\]:', r'\1:', line)
            line = re.sub(r'^\*([^*]+)\]:\*', r'\1:', line)
            
            processed_lines.append(line)
    
    return '\n'.join(processed_lines)

def validate_and_fix_script(script_text):
    """
    Valide et corrige automatiquement les problèmes de formatage du script
    """
    dialogue_parts = parse_enhanced_podcast_script(script_text)
    
    if len(dialogue_parts) < 5:
        print("⚠️ Script trop court, tentative de correction...")
        
        # Essayer de corriger le parsing
        lines = script_text.strip().split('\n')
        corrected_lines = []
        
        for line in lines:
            line = line.strip()
            if not line:
                continue
                
            # Détecter les patterns problématiques et les corriger
            if re.match(r'^\*[^*]+\]:\*', line):
                # Format *Speaker]:* -> Speaker:
                line = re.sub(r'^\*([^*]+)\]:\*', r'\1:', line)
            elif re.match(r'^\[([^\]]+)\]:', line):
                # Format [Speaker]: -> Speaker:
                line = re.sub(r'^\[([^\]]+)\]:', r'\1:', line)
            
            # Nettoyer tout formatage résiduel
            line = re.sub(r'\*+', '', line)
            
            corrected_lines.append(line)
        
        return '\n'.join(corrected_lines)
    
    return script_text

# Fonction pour tester le parsing d'un script
def test_script_parsing(script_text):
    """
    Fonction de test pour vérifier si un script sera correctement parsé
    """
    print("=== TEST DE PARSING DU SCRIPT ===")
    
    dialogue_parts = parse_enhanced_podcast_script(script_text)
    
    print(f"Nombre de segments détectés: {len(dialogue_parts)}")
    
    if len(dialogue_parts) == 0:
        print("❌ ERREUR: Aucun segment détecté!")
        print("\nPremières lignes du script:")
        for i, line in enumerate(script_text.split('\n')[:10]):
            print(f"{i+1}: {repr(line)}")
        return False
    
    print("\n✅ Segments détectés:")
    for i, part in enumerate(dialogue_parts[:5]):
        print(f"{i+1}. {part['speaker']}: {part['text'][:50]}...")
        if 'original_text' in part:
            emotions = extract_emotions_from_text(part['original_text'])
            if emotions and 'neutral' not in emotions:
                print(f"   🎭 Émotions: {', '.join(emotions)}")
    
    if len(dialogue_parts) > 5:
        print(f"   ... et {len(dialogue_parts) - 5} autres segments")
    
    return True

def clean_think_blocks(text):
    """Nettoie les blocs de réflexion du modèle"""
    import re
    # Supprimer les blocs <think>...</think>
    text = re.sub(r'<think>.*?</think>', '', text, flags=re.DOTALL)
    # Supprimer les multiples lignes vides
    text = re.sub(r'\n\s*\n\s*\n', '\n\n', text)
    return text.strip()

def extract_emotions_from_text(text):
    """
    Extrait les émotions du texte original pour l'animation des avatars
    """
    emotions = []
    emotion_patterns = {
        "excited": r"\(.*excit.*\)",
        "happy": r"\(.*happy.*\)|(\(.*smil.*\))",
        "nodding": r"\(.*nod.*\)",
        "surprised": r"\(.*surprise.*\)",
        "thoughtful": r"\(.*thought.*\)",
        "laughing": r"\(.*laugh.*\)",
        "concerned": r"\(.*concern.*\)"
    }
    
    for emotion, pattern in emotion_patterns.items():
        if re.search(pattern, text, re.IGNORECASE):
            emotions.append(emotion)
    
    return emotions if emotions else ["neutral"]


def create_speaking_face(draw, center_x, center_y):
    """Visage en train de parler - bouche ouverte"""
    create_neutral_face(draw, center_x, center_y)
    
    # Remplacer la bouche par une bouche ouverte
    mouth_y = center_y + 25
    # Effacer l'ancienne bouche (approximation)
    draw.rectangle([center_x - 20, mouth_y - 5, center_x + 20, mouth_y + 5], fill=(255, 220, 177))
    
    # Nouvelle bouche ouverte
    draw.ellipse([center_x - 8, mouth_y - 4, center_x + 8, mouth_y + 8], 
                fill=(50, 50, 50), outline=(0, 0, 0), width=2)
    
    # Dents
    draw.ellipse([center_x - 6, mouth_y - 2, center_x + 6, mouth_y + 2], fill=(255, 255, 255))


def reduce_pause_duration(pause_duration=800):  # Réduit de 1500ms à 800ms
    """
    Fonction pour ajuster la durée des pauses entre les segments
    """
    return AudioSegment.silent(duration=pause_duration)

async def generate_enhanced_podcast_audio_UPDATED(script_text, lang_code="auto", progress_callback=None, include_video=False):
    """
    Version mise à jour avec la nouvelle génération vidéo améliorée
    """
    if lang_code == "auto":
        sample_text = script_text[:300]
        lang_code = detect_language(sample_text)
    
    voice_map = {
        "fr": {"voice1": "fr-FR-DeniseNeural", "voice2": "fr-FR-HenriNeural"},
        "en": {"voice1": "en-US-JennyNeural", "voice2": "en-US-GuyNeural"},
        "de": {"voice1": "de-DE-KatjaNeural", "voice2": "de-DE-ConradNeural"},
        "es": {"voice1": "es-ES-ElviraNeural", "voice2": "es-ES-AlvaroNeural"},
        "it": {"voice1": "it-IT-ElsaNeural", "voice2": "it-IT-GiuseppeNeural"}
    }
    
    voices = voice_map.get(lang_code, voice_map["en"])
    dialogue_parts = parse_enhanced_podcast_script(script_text)
    
    if not dialogue_parts:
        if progress_callback:
            progress_callback(0, "Erreur: Script mal formaté")
        return None, None
    
    temp_dir = tempfile.mkdtemp()
    
    try:
        if progress_callback:
            progress_callback(0.1, "Génération des segments audio...")
        
        speaker_voice_map = create_consistent_voice_mapping(dialogue_parts, voices, lang_code)
        audio_segments = []
        video_info = [] if include_video else None
        
        total_parts = len(dialogue_parts)
        
        for i, part in enumerate(dialogue_parts):
            try:
                progress = 0.1 + (i / total_parts) * 0.6
                if progress_callback:
                    progress_callback(progress, f"Génération segment {i+1}/{total_parts}...")
                
                voice = speaker_voice_map.get(part['speaker'])
                if not voice:
                    voice = voices['voice1']
                
                # Utiliser le texte nettoyé des émotions
                enhanced_text = enhance_text_for_speech(part['text'], i == 0, i == len(dialogue_parts) - 1)
                
                # Générer l'audio avec SSML pour les émotions
                communicate = edge_tts.Communicate(enhanced_text, voice)
                segment_path = os.path.join(temp_dir, f"segment_{i:03d}.wav")
                await communicate.save(segment_path)
                
                if not os.path.exists(segment_path):
                    raise Exception(f"Échec de la création du segment {i}")
                
                segment = AudioSegment.from_file(segment_path)
                segment = normalize(segment)
                
                # Réduire la pause entre les segments (800ms au lieu de 1500ms)
                if i > 0:
                    pause = AudioSegment.silent(duration=800)
                    audio_segments.append(pause)
                    if include_video:
                        video_info.append({"type": "pause", "duration": 0.8})
                
                audio_segments.append(segment)
                
                # Information pour la vidéo
                if include_video:
                    emotions = extract_emotions_from_text(part.get('original_text', part['text']))
                    video_info.append({
                        "type": "speech",
                        "speaker": part['speaker'],
                        "duration": len(segment) / 1000.0,
                        "emotions": emotions,
                        "text": part['text']
                    })
                
            except Exception as segment_error:
                print(f"Erreur segment {i}: {segment_error}")
                continue
        
        if not audio_segments:
            raise Exception("Aucun segment audio généré avec succès")
        
        if progress_callback:
            progress_callback(0.75, "Mixage audio...")
        
        # Combiner tous les segments
        final_audio = AudioSegment.empty()
        for segment in audio_segments:
            final_audio += segment
        
        final_audio = post_process_audio(final_audio)
        
        # Exporter en MP3
        output_path = os.path.join(temp_dir, "podcast_final.mp3")
        final_audio.export(output_path, format="mp3", bitrate="128k")
        
        with open(output_path, "rb") as f:
            audio_bytes = f.read()
        
        # Générer la vidéo si demandée (NOUVELLE VERSION)
        video_bytes = None
        if include_video and video_info:
            if progress_callback:
                progress_callback(0.80, "Génération de la vidéo animée...")
            video_bytes = await generate_enhanced_podcast_video(
                video_info, final_audio, temp_dir, lang_code, progress_callback
            )
        
        if progress_callback:
            progress_callback(1.0, "Terminé!")
        
        return audio_bytes, video_bytes
        
    except Exception as e:
        error_msg = f"Erreur génération audio: {str(e)}"
        print(error_msg)
        if progress_callback:
            progress_callback(0, error_msg)
        return None, None
    finally:
        try:
            shutil.rmtree(temp_dir, ignore_errors=True)
        except:
            pass



def create_consistent_voice_mapping(dialogue_parts, voices, lang_code):
    """Crée un mapping FORCÉ alternant entre 2 voix différentes"""
    
    # Obtenir tous les orateurs uniques dans l'ordre d'apparition
    speakers_in_order = []
    for part in dialogue_parts:
        if part['speaker'] not in speakers_in_order:
            speakers_in_order.append(part['speaker'])
    
    print(f"🎭 Orateurs détectés dans l'ordre: {speakers_in_order}")
    
    speaker_voice_map = {}
    
    # FORCER l'alternance : Premier speaker = voix1, Deuxième = voix2
    for i, speaker in enumerate(speakers_in_order):
        if i % 2 == 0:
            # Speaker pair (0, 2, 4...) = Voix féminine
            speaker_voice_map[speaker] = voices["voice1"]
            print(f"✓ {speaker} → VOIX FÉMININE ({voices['voice1']})")
        else:
            # Speaker impair (1, 3, 5...) = Voix masculine  
            speaker_voice_map[speaker] = voices["voice2"]
            print(f"✓ {speaker} → VOIX MASCULINE ({voices['voice2']})")
    
    # VÉRIFICATION FINALE
    unique_voices = set(speaker_voice_map.values())
    print(f"🔍 Nombre de voix uniques utilisées: {len(unique_voices)}")
    
    if len(unique_voices) < 2 and len(speakers_in_order) >= 2:
        print("⚠️ CORRECTION FORCÉE: Assigner 2 voix différentes")
        speaker_voice_map[speakers_in_order[0]] = voices["voice1"]
        speaker_voice_map[speakers_in_order[1]] = voices["voice2"]
    
    return speaker_voice_map

def verify_voice_mapping(script_text, lang_code="auto"):
    """
    Fonction utilitaire pour vérifier le mapping des voix avant génération
    """
    if lang_code == "auto":
        lang_code = detect_language(script_text[:300])
    
    voice_map = {
        "fr": {"voice1": "fr-FR-DeniseNeural", "voice2": "fr-FR-HenriNeural"},
        "en": {"voice1": "en-US-JennyNeural", "voice2": "en-US-GuyNeural"},
        "de": {"voice1": "de-DE-KatjaNeural", "voice2": "de-DE-ConradNeural"},
        "es": {"voice1": "es-ES-ElviraNeural", "voice2": "es-ES-AlvaroNeural"},
        "it": {"voice1": "it-IT-ElsaNeural", "voice2": "it-IT-GiuseppeNeural"}
    }
    
    voices = voice_map.get(lang_code, voice_map["en"])
    dialogue_parts = parse_podcast_script(script_text)
    speaker_voice_map = create_consistent_voice_mapping(dialogue_parts, voices, lang_code)
    
    print("\n=== VÉRIFICATION DU MAPPING DES VOIX ===")
    print(f"Langue: {lang_code}")
    print(f"Voix disponibles: {voices}")
    print("\nMapping final:")
    for speaker, voice in speaker_voice_map.items():
        gender = "👩 Féminine" if voice == voices["voice1"] else "👨 Masculine"
        print(f"  {speaker} → {voice} ({gender})")
    
    print(f"\nPremiers segments:")
    for i, part in enumerate(dialogue_parts[:3]):
        voice = speaker_voice_map.get(part['speaker'], 'ERREUR')
        print(f"  {i+1}. {part['speaker']} → {voice}")
        print(f"      Texte: {part['text'][:60]}...")
    
    return speaker_voice_map

def parse_podcast_script(script_text):
    """
    Parse le script du podcast pour extraire les dialogues
    AMÉLIORÉ: Filtre complètement les titres, balises et formatage
    """
    import re
    dialogue_parts = []
    lines = script_text.strip().split('\n')
    
    # Patterns à ignorer complètement
    ignore_patterns = [
        r'^#{1,6}\s',  # Titres markdown (# ## ###)
        r'^\*{1,3}\[.*?\]\*{1,3}$',  # Balises de section comme *[INTRODUCTION]*
        r'^---+$',  # Séparateurs
        r'^\*{2,}.*?\*{2,}$',  # Texte entouré d'astérisques multiples
        r'^### Podcast Script:',  # Titre de script
        r'^Dr\. .* and Prof\. .* on .*$',  # Titres avec noms
        r'^\[.*\]$',  # Balises pures comme [INTRODUCTION]
        r'^Podcast Script:',  # Variantes de titres
        r'^\*{2,}\[.*?\]\*{2,}$'  # **[SECTION]**
    ]
    
    for line in lines:
        line = line.strip()
        if not line:
            continue
            
        # Vérifier si la ligne doit être ignorée
        should_ignore = False
        for pattern in ignore_patterns:
            if re.match(pattern, line, re.IGNORECASE):
                should_ignore = True
                break
        
        if should_ignore:
            continue
            
        # Extraire le dialogue en nettoyant complètement le formatage
        speaker, text = extract_clean_dialogue(line)
        
        if speaker and text and len(text) > 10:  # Au moins 10 caractères
            dialogue_parts.append({
                'speaker': speaker,
                'text': text
            })
    
    print(f"Script parsé: {len(dialogue_parts)} segments trouvés")
    return dialogue_parts

def extract_clean_dialogue(line):
    """
    Extrait le nom de l'orateur et le texte en nettoyant complètement le formatage
    """
    import re
    
    # Nettoyer d'abord tous les formatages markdown/astérisques du début
    line = re.sub(r'^\*+', '', line)  # Supprimer * au début
    line = re.sub(r'\*+$', '', line)  # Supprimer * à la fin
    
    speaker = None
    text = None
    
    # Format [Nom]: Texte
    if line.startswith ('[') and (']:') in line:
        bracket_end = line.find(']:')
        if bracket_end != -1:
            speaker = line[1:bracket_end].strip()
            text = line[bracket_end + 2:].strip()
    
    # Format *Nom:* Texte ou Nom: Texte
    elif ':' in line and not line.startswith('http'):
        parts = line.split(':', 1)
        if len(parts) == 2:
            raw_speaker = parts[0].strip()
            text = parts[1].strip()
            
            # Nettoyer complètement le nom de l'orateur
            speaker = clean_speaker_name(raw_speaker)
    
    # Nettoyer le texte de tout formatage résiduel
    if text:
        text = clean_speech_text(text)
    
    return speaker, text

def clean_speaker_name(raw_speaker):
    """
    Nettoie complètement le nom de l'orateur de tout formatage
    """
    import re
    
    # Supprimer tous les astérisques et formatage
    speaker = re.sub(r'\*+', '', raw_speaker)
    speaker = re.sub(r'_+', '', speaker)  # Supprimer underscores
    speaker = re.sub(r'`+', '', speaker)  # Supprimer backticks
    speaker = speaker.strip()
    
    # Valider que c'est bien un nom d'orateur valide
    valid_speakers = ['Dr. Marie', 'Prof. Thomas', 'Dr. Sarah', 'Prof. Michael', 
                     'Dr. Anna', 'Prof. Klaus', 'Dra. Carmen', 'Prof. Ricardo',
                     'Dr.ssa Elena', 'Prof. Marco']
    
    # Vérifier si c'est un nom d'orateur reconnu
    for valid in valid_speakers:
        if speaker.lower() == valid.lower() or speaker.lower() in valid.lower():
            return valid
    
    # Si pas reconnu mais ressemble à un nom d'orateur
    if any(title in speaker for title in ['Dr.', 'Prof.', 'Dra.', 'Dr.ssa']):
        return speaker
    
    return None

def clean_speech_text(text):
    """
    Nettoie le texte de tout formatage qui pourrait être lu par la synthèse vocale
    """
    import re
    
    # Supprimer tous les formatages markdown
    text = re.sub(r'\*+([^*]+)\*+', r'\1', text)  # *texte* ou **texte**
    text = re.sub(r'_+([^_]+)_+', r'\1', text)    # _texte_
    text = re.sub(r'`+([^`]+)`+', r'\1', text)    # `texte`
    text = re.sub(r'#+\s*', '', text)             # # titre
    
    # Supprimer les balises résiduelles
    text = re.sub(r'\[([^\]]+)\]', r'\1', text)   # [texte]
    text = re.sub(r'<[^>]+>', '', text)           # <balise>
    
    # Nettoyer les caractères spéciaux problématiques
    text = re.sub(r'^\s*[-•]\s*', '', text)       # Puces
    text = re.sub(r'\s+', ' ', text)              # Espaces multiples
    
    # Supprimer les séquences d'astérisques isolées
    text = re.sub(r'\*+', '', text)
    
    return text.strip()

def enhance_text_for_speech(text, is_first=False, is_last=False):
    """
    Améliore le texte pour une meilleure synthèse vocale
    AMÉLIORÉ: Nettoyage supplémentaire pour éviter la lecture de formatage
    """
    # Nettoyer d'abord avec la fonction dédiée
    text = clean_speech_text(text)
    
    # Nettoyer le texte d'abord
    text = text.strip()
    
    # Supprimer définitivement tous les astérisques résiduels
    text = text.replace('*', '')
    
    # Ajouter des pauses naturelles
    text = text.replace(', ', ', ')  # Pause naturelle
    text = text.replace('. ', '. ')  # Pause naturelle  
    text = text.replace('! ', '! ')  # Pause naturelle
    text = text.replace('? ', '? ')  # Pause naturelle
    text = text.replace(' : ', ' : ')  # Pause avant les deux-points
    
    # Améliorer la prononciation de certains mots techniques
    replacements = {
        'API': 'A-P-I',
        'ML': 'M-L',
        'AI': 'A-I',
        'IA': 'I-A',
        'URL': 'U-R-L',
        'HTTP': 'H-T-T-P',
        'ChunkRAG': 'Chunk-RAG',  # Ajout spécifique pour votre cas
        'PopQA': 'Pop-Q-A'
    }
    
    for old, new in replacements.items():
        text = text.replace(old, new)
    
    return text

# Fonction utilitaire pour déboguer et vérifier le parsing
def debug_script_parsing(script_text):
    """
    Fonction de débogage pour vérifier ce qui sera lu par la synthèse vocale
    """
    dialogue_parts = parse_podcast_script(script_text)
    
    print("=== APERÇU DE CE QUI SERA LU ===")
    for i, part in enumerate(dialogue_parts):
        print(f"\n{i+1}. {part['speaker']}:")
        print(f"   Texte: {part['text'][:100]}{'...' if len(part['text']) > 100 else ''}")
        
        # Vérifier s'il y a encore du formatage problématique
        if '*' in part['text'] or '[' in part['text'] or '#' in part['text']:
            print(f"   ⚠️  ATTENTION: Formatage détecté dans le texte!")
    
    return dialogue_parts


def update_progress(progress_bar, status_text, progress, status):
    """Met à jour la barre de progression"""
    try:
        progress_bar.progress(min(max(progress, 0), 1))  # S'assurer que progress est entre 0 et 1
        status_text.text(status)
    except:
        pass  # Éviter les erreurs si les widgets n'existent plus

def post_process_audio(audio):
    """
    Post-traitement audio pour améliorer la qualité
    """
    try:
        from pydub.effects import normalize
        
        # Normaliser le volume
        audio = normalize(audio)
        
        # Ajouter un léger fade in/out
        audio = audio.fade_in(1000).fade_out(1000)  # 1 seconde
        
        # Légèrement ajuster le volume final
        if len(audio) > 0:
            audio = audio + 2  # +2 dB
        
        return audio
    except Exception as e:
        print(f"Erreur post-processing: {e}")
        return audio
    