from flask import Blueprint, request, jsonify, send_file
from backend.services.summarization_service import extract_from_pdf, summarize_document_with_vision, translate_text, generate_audio, create_pdf
from backend.services.pptx_service import generate_advanced_presentation_with_visuals
from langdetect import detect
import os
import asyncio
from backend.services.podcast_service import generate_improved_podcast_script, generate_complete_emotional_podcast
import base64

summarization_bp = Blueprint('summarization', __name__)

@summarization_bp.route('/summarize', methods=['POST'])
def summarize():
    if 'pdf' not in request.files:
        return jsonify({'error': 'Aucun fichier PDF fourni.'}), 400
    pdf_file = request.files['pdf']
    lang = request.form.get('lang', 'fr')  # Langue cible, défaut français

    # Extraction texte + images
    text, image_paths, temp_dir = extract_from_pdf(pdf_file)
    if not text.strip():
        return jsonify({'error': 'Impossible d\'extraire le texte du PDF.'}), 400

    # Génération du résumé avancé
    summary = summarize_document_with_vision(text, image_paths)

    # Détection de la langue du résumé généré
    try:
        detected_lang = detect(summary)
    except Exception:
        detected_lang = 'en'

    # Traduction si nécessaire
    translated_summary = summary
    if lang and lang != detected_lang:
        translated_summary = translate_text(summary, lang)

    # Nettoyage des images temporaires
    if temp_dir and os.path.exists(temp_dir):
        import shutil
        shutil.rmtree(temp_dir)

    return jsonify({
        'summary': summary,
        'lang': detected_lang,
        'translated_summary': translated_summary,
        'target_lang': lang
    })

@summarization_bp.route('/summarize/audio', methods=['POST'])
def summarize_audio():
    data = request.form or request.json
    text = data.get('text')
    lang = data.get('lang', 'fr')
    if not text:
        return jsonify({'error': 'Aucun texte fourni pour la synthèse vocale.'}), 400
    try:
        audio_bytes = asyncio.run(generate_audio(text, lang))
        return send_file(
            audio_bytes,
            mimetype='audio/mpeg',
            as_attachment=True,
            download_name='summary.mp3'
        )
    except Exception as e:
        return jsonify({'error': f'Erreur lors de la génération audio : {e}'}), 500

@summarization_bp.route('/summarize/pdf', methods=['POST'])
def summarize_pdf():
    data = request.form or request.json
    summary = data.get('summary')
    lang = data.get('lang', 'fr')
    if not summary:
        return jsonify({'error': 'Aucun résumé fourni pour la génération PDF.'}), 400
    try:
        pdf_buffer = create_pdf(summary, lang)
        return send_file(
            pdf_buffer,
            mimetype='application/pdf',
            as_attachment=True,
            download_name='summary.pdf'
        )
    except Exception as e:
        return jsonify({'error': f'Erreur lors de la génération PDF : {e}'}), 500

@summarization_bp.route('/summarize/pptx', methods=['POST'])
def summarize_pptx():
    data = request.form or request.json
    summary = data.get('summary')
    title = data.get('title', 'Présentation Scientifique')
    theme = data.get('theme', '🧬 Scientifique Moderne')
    if not summary:
        return jsonify({'error': 'Aucun résumé fourni pour la génération PPTX.'}), 400
    try:
        pptx_buffer = generate_advanced_presentation_with_visuals(summary, title=title, theme_name=theme)
        if not pptx_buffer:
            return jsonify({'error': 'Erreur lors de la génération de la présentation.'}), 500
        return send_file(
            pptx_buffer,
            mimetype='application/vnd.openxmlformats-officedocument.presentationml.presentation',
            as_attachment=True,
            download_name='presentation.pptx'
        )
    except Exception as e:
        return jsonify({'error': f'Erreur lors de la génération PPTX : {e}'}), 500

@summarization_bp.route('/summarize/podcast', methods=['POST'])
def summarize_podcast():
    data = request.form or request.json
    summary = data.get('summary')
    lang = data.get('lang')  # Peut être None
    style = data.get('style', 'Interview d\'expert')
    duration = data.get('duration', '5-7 min')
    with_audio = data.get('with_audio', 'true').lower() == 'true'
    with_video = data.get('with_video', 'false').lower() == 'true'

    if not summary:
        return jsonify({'error': 'Aucun résumé fourni pour la génération du podcast.'}), 400

    # Détecter la langue si non fournie
    if not lang:
        try:
            lang = detect(summary)
        except Exception:
            lang = 'fr'

    # Générer le script
    script = generate_improved_podcast_script(summary, lang, style, duration)

    audio_b64 = None
    video_b64 = None
    if with_audio or with_video:
        import asyncio
        audio_bytes, video_bytes = asyncio.run(generate_complete_emotional_podcast(script, lang, include_video=with_video))
        if audio_bytes:
            audio_b64 = base64.b64encode(audio_bytes).decode('utf-8')
        if video_bytes:
            video_b64 = base64.b64encode(video_bytes).decode('utf-8')

    return jsonify({
        'script': script,
        'lang': lang,
        'audio_b64': audio_b64,
        'video_b64': video_b64
    })