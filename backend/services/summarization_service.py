import os
import re
import io
import shutil
import base64
import hashlib
import logging
from PIL import Image
import fitz  # PyMuPDF
import cv2
from concurrent.futures import ThreadPoolExecutor
import ollama
import tempfile
import edge_tts
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer
from reportlab.lib.enums import TA_JUSTIFY
from reportlab.lib.units import cm

logging.basicConfig(level=logging.INFO)

def clean_think_blocks(text: str) -> str:
    text = re.sub(r'<think>.*?</think>', '', text, flags=re.DOTALL)
    text = re.sub(r'<reasoning>.*?</reasoning>', '', text, flags=re.DOTALL)
    return text.strip()

def hash_image(image_bytes):
    return hashlib.md5(image_bytes).hexdigest()

def extract_from_pdf(pdf_file, use_opencv=True):
    temp_dir = "temp_images"
    if os.path.exists(temp_dir):
        shutil.rmtree(temp_dir)
    os.makedirs(temp_dir, exist_ok=True)

    pdf_bytes = pdf_file.read()
    doc = fitz.open(stream=pdf_bytes, filetype="pdf")

    text = ""
    image_paths = []
    image_hashes = set()

    for page_num in range(len(doc)):
        page = doc.load_page(page_num)
        text += page.get_text()
        image_list = page.get_images(full=True)
        for img_index, img in enumerate(image_list):
            xref = img[0]
            base_image = doc.extract_image(xref)
            image_bytes = base_image["image"]
            try:
                img_hash = hash_image(image_bytes)
                if img_hash not in image_hashes:
                    image_hashes.add(img_hash)
                    pil_image = Image.open(io.BytesIO(image_bytes))
                    if pil_image.width > 100 and pil_image.height > 100:
                        image_filename = f"{temp_dir}/page{page_num+1}_img{img_index+1}.png"
                        pil_image.save(image_filename, "PNG")
                        image_paths.append(image_filename)
            except Exception as e:
                logging.warning(f"[Page {page_num+1}] Erreur conversion image: {e}")
        if use_opencv:
            try:
                pix = page.get_pixmap(matrix=fitz.Matrix(300/72, 300/72))
                page_img_path = f"{temp_dir}/page{page_num+1}_full.png"
                pix.save(page_img_path)
                img = cv2.imread(page_img_path)
                if img is None:
                    continue
                gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
                blur = cv2.GaussianBlur(gray, (5, 5), 0)
                edges = cv2.Canny(blur, 50, 150)
                contours, _ = cv2.findContours(edges, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
                for i, contour in enumerate(contours):
                    area = cv2.contourArea(contour)
                    if area > 10000:
                        x, y, w, h = cv2.boundingRect(contour)
                        if 0.2 < w/h < 5 and w > 100 and h > 100:
                            roi = img[y:y+h, x:x+w]
                            _, buffer = cv2.imencode('.png', roi)
                            img_hash = hashlib.md5(buffer).hexdigest()
                            if img_hash not in image_hashes:
                                image_hashes.add(img_hash)
                                figure_path = f"{temp_dir}/page{page_num+1}_figure{i+1}.png"
                                cv2.imwrite(figure_path, roi)
                                image_paths.append(figure_path)
                os.remove(page_img_path)
            except Exception as e:
                logging.error(f"[Page {page_num+1}] Erreur OpenCV: {e}")
    pdf_file.seek(0)
    return text, image_paths, temp_dir

def read_image_binary(image_path):
    with open(image_path, "rb") as img_file:
        binary_data = img_file.read()
        return base64.b64encode(binary_data).decode('utf-8')

def describe_image(image_path, image_number):
    try:
        image_binary = read_image_binary(image_path)
        prompt = f"""
        You are an expert in interpreting scientific figures from academic papers.
        You are shown a standalone image from a scientific paper. Describe the **visual content and structure** of the figure, and if possible, **infer its role or type** (e.g., pipeline diagram, comparison table, algorithm illustration), only based on visual elements (titles, labels, arrows, layout, visible terms).
        Guidelines:
        1. Focus on what is visibly present: arrows, blocks, labels, axes, tables, percentages, nodes, and textual annotations.
        2. If the figure clearly depicts a process, comparison, or architecture, say so — but never speculate if it's unclear.
        3. Do NOT invent terminology or data not visible.
        4. Keep your description concise and professional (max 150 words).
        Now describe the image.
        """
        response = ollama.chat(
            model="granite3.2-vision",
            messages=[{
                "role": "user",
                "content": prompt,
                "images": [image_binary]
            }],
            options={
                "temperature": 0.2,
                "top_p": 0.9,
            }
        )
        return response["message"]["content"]
    except Exception as e:
        return f"Impossible de décrire l'image {image_number}: {str(e)}"

def process_images_in_parallel(image_paths, max_workers=3):
    image_descriptions = {}
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        future_to_image = {
            executor.submit(describe_image, image_path, i+1): (image_path, i+1)
            for i, image_path in enumerate(image_paths)
        }
        for future in future_to_image:
            image_path, image_number = future_to_image[future]
            try:
                description = future.result()
                image_descriptions[image_number] = description
            except Exception as e:
                print(f"Erreur lors du traitement de l'image {image_number}: {e}")
    return image_descriptions

def summarize_text(text):
    prompt = f"""
    You are an advanced language model specialized in detailed and insightful summarization.
    Your task is to read the text below and generate a comprehensive and structured summary.
    - The summary should be written in the same language as the input (French or English).
    - Do not make it too short — include all relevant details, arguments, facts, and examples.
    - Preserve the tone and style of the original text.
    - Emphasize the key points, context, motivations, and conclusions.
    - If applicable, structure the summary in sections or paragraphs (e.g., Introduction, Main Ideas, Conclusion).
    - Avoid overly general or vague phrasing. Be as specific as possible.
    Article text:
    {text}
    """
    try:
        response = ollama.chat(
            model="llama3.2",
            messages=[{
                "role": "user",
                "content": prompt
            }],
            options={
                "temperature": 0.2,
                "top_p": 0.9,
                "num_predict": 2048
            }
        )
        return response["message"]["content"]
    except Exception as e:
        return f"Erreur lors de la génération du résumé du texte: {str(e)}"

def create_final_summary(text_summary, image_descriptions):
    image_descriptions_formatted = ""
    for img_num, description in sorted(image_descriptions.items()):
        image_descriptions_formatted += f"{description.strip()}\n\n"
    prompt = f"""
    You are a scientific writing expert.
    You have received:
    1- A structured summary of a scientific article (with sections like Introduction, Methods, etc.).
    2- Descriptions of images and figures illustrating or supporting key parts of the study.
    Your task is to generate a final, unified scientific summary that follows a clear academic structure and integrates both textual and visual insights.
    Instructions:
    - Structure the output using these mandatory headings:
    Introduction, Methodology, Results, Discussion, Conclusion.
    - Embed insights from figures directly within the relevant sections (e.g., integrate results from a graph into the "Results" section), but do not refer to figure numbers or use phrases like "as shown in Figure 1".
    - Maintain a professional academic tone throughout the summary.
    - Use only information present in the provided text and image descriptions. Do not invent or speculate.
    - Do not list figure descriptions separately. Integrate them meaningfully and selectively, avoiding literal or redundant image details.
    - If an image is unclear or adds no useful scientific information, omit it entirely.
    Your output should be a cohesive and well-written scientific summary that reads as if it were written by the original authors of the paper.
    Here is the text summary:
    {text_summary}
    Here are the figure descriptions:
    {image_descriptions_formatted}
    Now generate the final scientific summary, integrating all information into a single coherent document.
    """
    try:
        response = ollama.chat(
            model="DeepSeek-R1",
            messages=[{
                "role": "user",
                "content": prompt
            }],
            options={
                "temperature": 0.2,
                "top_p": 0.9,
                "num_predict": 3072
            }
        )
        raw_answer = response['message']['content']
        cleaned_answer = clean_think_blocks(raw_answer)
        return cleaned_answer
    except Exception as e:
        return f"Erreur lors de la génération du résumé final: {str(e)}"

def summarize_document_with_vision(text, image_paths):
    text_summary = summarize_text(text)
    image_descriptions = process_images_in_parallel(image_paths)
    final_summary = create_final_summary(text_summary, image_descriptions)
    return final_summary

def translate_text(text, target_lang_code):
    language_name = {
        "fr": "French",
        "en": "English",
        "de": "German",
        "es": "Spanish",
        "it": "Italian"
    }.get(target_lang_code, "English")
    prompt = f"""
You are a professional translator.
Please translate the following text into {language_name}.
Only return the translated version. Do not add explanations.

Text to translate:
{text}
    """.strip()
    try:
        response = ollama.chat(
            model="DeepSeek-R1",
            messages=[{"role": "user", "content": prompt}]
        )
        result = response["message"]["content"].strip()
        cleaned_answer = clean_think_blocks(result)
        return cleaned_answer
    except Exception as e:
        return f"❌ Une erreur est survenue lors de la traduction : {e}"

async def generate_audio(summary_text, lang_code):
    voice_map = {
        "fr": "fr-FR-DeniseNeural",
        "en": "en-US-JennyNeural",
        "de": "de-DE-KatjaNeural",
        "es": "es-ES-ElviraNeural",
        "it": "it-IT-ElsaNeural"
    }
    voice = voice_map.get(lang_code, "en-US-JennyNeural")
    communicate = edge_tts.Communicate(summary_text, voice)

    with tempfile.NamedTemporaryFile(delete=False, suffix=".mp3") as tmp:
        path = tmp.name

    await communicate.save(path)

    with open(path, "rb") as f:
        mp3_bytes = f.read()

    return io.BytesIO(mp3_bytes)

def create_pdf(summary_text, lang_code):
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=A4,
                            rightMargin=2*cm, leftMargin=2*cm,
                            topMargin=2*cm, bottomMargin=2*cm)
    elements = []
    styles = getSampleStyleSheet()
    custom_style = ParagraphStyle(
        'Custom',
        parent=styles['Normal'],
        fontSize=12,
        leading=18,
        alignment=TA_JUSTIFY
    )
    title_style = styles['Title']
    first_line = summary_text.strip().split("\n")[0]
    title = first_line.strip().strip(" :.")
    elements.append(Paragraph(title, title_style))
    elements.append(Spacer(1, 12))

    cleaned_lines = []
    for line in summary_text.strip().split("\n"):
        line = line.strip()
        if line.startswith("*"):
            cleaned_lines.append(Paragraph(line, custom_style))
            cleaned_lines.append(Spacer(1, 6))
        elif line != first_line:
            cleaned_lines.append(Paragraph(line, custom_style))
            cleaned_lines.append(Spacer(1, 12))
    elements.extend(cleaned_lines)
    doc.build(elements)
    buffer.seek(0)
    return buffer 