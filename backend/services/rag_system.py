import os
import pickle
import time
import re
from pathlib import Path
from typing import List, Dict, Any, Optional

from langchain.text_splitter import RecursiveCharacterTextSplitter
from langchain_community.document_loaders import PyPDFLoader
from langchain_community.vectorstores import Chroma
from langchain_ollama import OllamaEmbeddings
from langchain.docstore.document import Document
import ollama
import requests
import feedparser
import datetime
from sentence_transformers import util
import torch

from flask import current_app
from backend.models.article import Article
from backend.models.user import User

class EnhancedMUragSystem:
    """Système RAG adapté pour Flask utilisant tes données existantes"""
    
    def __init__(self, user_id: Optional[int] = None):
        self.user_id = user_id
        
        # Chemins vers tes données existantes (définis dans config.py)
        self.pdf_path = current_app.config['RAG_PDF_FOLDER']
        self.chroma_path = current_app.config['RAG_CHROMA_PATH']
        self.lexical_index_path = current_app.config['RAG_LEXICAL_INDEX']
        self.conversation_memory_path = current_app.config['RAG_CONVERSATION_MEMORY']
        
        # Créer les dossiers si nécessaire
        os.makedirs(self.pdf_path, exist_ok=True)
        
        # Charger l'index lexical existant
        self.lexical_index = {}
        self._load_lexical_index()
        
        # Initialiser les embeddings
        self.embeddings = OllamaEmbeddings(model="nomic-embed-text")
        
        # Charger ou créer le vectorstore
        self.vectorstore = self._load_vectorstore()
        self.retriever = self.vectorstore.as_retriever(
            search_type="mmr",
            search_kwargs={"k": 5, "lambda_mult": 0.6}
        )
        
        # Agent de vérification
        self.verification_model = self._create_verification_agent()
        
        # Mémoire de conversation par utilisateur
        self.conversation_memory = []
        self._load_conversation_memory()
    
    def _load_lexical_index(self):
        """Charger l'index lexical existant"""
        try:
            if os.path.exists(self.lexical_index_path):
                with open(self.lexical_index_path, "rb") as f:
                    self.lexical_index = pickle.load(f)
                print(f"✅ Index lexical chargé: {len(self.lexical_index)} documents")
            else:
                print("⚠️ Aucun index lexical trouvé, création d'un nouveau")
                self.lexical_index = {}
        except Exception as e:
            print(f"⚠️ Erreur chargement index lexical: {e}")
            self.lexical_index = {}
    
    def _save_lexical_index(self):
        """Sauvegarder l'index lexical"""
        try:
            with open(self.lexical_index_path, "wb") as f:
                pickle.dump(self.lexical_index, f)
            print("✅ Index lexical sauvegardé")
        except Exception as e:
            print(f"❌ Erreur sauvegarde index lexical: {e}")
    
    def _load_vectorstore(self):
        """Charger le vectorstore existant ou en créer un nouveau"""
        try:
            if os.path.exists(self.chroma_path) and os.listdir(self.chroma_path):
                print("📦 Chargement du vectorstore existant...")
                vectorstore = Chroma(
                    persist_directory=self.chroma_path,
                    embedding_function=self.embeddings
                )
                print(f"✅ Vectorstore chargé depuis {self.chroma_path}")
                return vectorstore
            else:
                print("🆕 Création d'un nouveau vectorstore...")
                vectorstore = Chroma(
                    embedding_function=self.embeddings,
                    persist_directory=self.chroma_path
                )
                vectorstore.persist()
                print(f"✅ Nouveau vectorstore créé dans {self.chroma_path}")
                return vectorstore
        except Exception as e:
            print(f"❌ Erreur vectorstore: {e}")
            # Fallback: créer un nouveau vectorstore
            vectorstore = Chroma(
                embedding_function=self.embeddings,
                persist_directory=self.chroma_path
            )
            return vectorstore
    
    def _create_verification_agent(self):
        """Créer l'agent de vérification"""
        try:
            verification_model = current_app.config.get('DEFAULT_VERIFICATION_MODEL', 'DeepSeek-R1')
            
            # Test du modèle
            test_response = ollama.chat(
                model=verification_model,
                messages=[{'role': 'user', 'content': 'Test'}]
            )
            print(f"✅ Agent de vérification initialisé: {verification_model}")
            return verification_model
        except Exception as e:
            print(f"⚠️ Erreur agent de vérification: {e}")
            return "DeepSeek-R1"  # Fallback
    
    def _load_conversation_memory(self):
        """Charger la mémoire de conversation pour l'utilisateur"""
        try:
            memory_file = f"{self.conversation_memory_path}_{self.user_id}.pkl" if self.user_id else self.conversation_memory_path
            
            if os.path.exists(memory_file):
                with open(memory_file, "rb") as f:
                    self.conversation_memory = pickle.load(f)
                print(f"✅ Mémoire de conversation chargée: {len(self.conversation_memory)} échanges")
            else:
                self.conversation_memory = []
                print("📝 Nouvelle mémoire de conversation initialisée")
        except Exception as e:
            print(f"⚠️ Erreur chargement mémoire: {e}")
            self.conversation_memory = []
    
    def _save_conversation_memory(self):
        """Sauvegarder la mémoire de conversation"""
        try:
            memory_file = f"{self.conversation_memory_path}_{self.user_id}.pkl" if self.user_id else self.conversation_memory_path
            
            with open(memory_file, "wb") as f:
                pickle.dump(self.conversation_memory, f)
            print("💾 Mémoire de conversation sauvegardée")
        except Exception as e:
            print(f"⚠️ Erreur sauvegarde mémoire: {e}")
    
    def add_document_from_article(self, article: Article) -> bool:
        """Ajouter un document au système RAG depuis un objet Article"""
        try:
            if not os.path.exists(article.file_path):
                print(f"❌ Fichier introuvable: {article.file_path}")
                return False
            
            # Charger le document
            loader = PyPDFLoader(article.file_path)
            docs = loader.load()
            
            if not docs:
                print("❌ Aucun contenu extrait du PDF")
                return False
            
            # Traitement multimodal (utilise tes fonctions existantes)
            images = self._extract_images_from_pdf(article.file_path)
            figures_tables = self._extract_figures_tables_from_pdf(article.file_path)
            
            # Préparer tous les documents
            all_docs = docs.copy()
            
            # Ajouter les images comme documents
            for img in images:
                image_doc = Document(
                    page_content=f"[IMAGE] {img['text_content']}",
                    metadata={
                        "source": article.file_path,
                        "page": img["page_num"],
                        "type": "image",
                        "article_id": article.id,
                        "user_id": article.user_id
                    }
                )
                all_docs.append(image_doc)
            
            # Ajouter figures et tableaux
            for elem in figures_tables:
                elem_doc = Document(
                    page_content=f"[{elem['type'].upper()}] {elem['caption']} {elem['text_content']}",
                    metadata={
                        "source": article.file_path,
                        "page": elem["page_num"],
                        "type": elem["type"],
                        "article_id": article.id,
                        "user_id": article.user_id
                    }
                )
                all_docs.append(elem_doc)
            
            # Chunking
            splitter = RecursiveCharacterTextSplitter(chunk_size=1000, chunk_overlap=200)
            chunks = splitter.split_documents(all_docs)
            
            # Nettoyer le texte
            for chunk in chunks:
                chunk.page_content = chunk.page_content.encode("utf-8", "ignore").decode("utf-8", "ignore")
                # Ajouter métadonnées article
                chunk.metadata.update({
                    "article_id": article.id,
                    "user_id": article.user_id,
                    "article_title": article.title
                })
            
            # Ajouter au vectorstore
            self.vectorstore.add_documents(chunks)
            self.vectorstore.persist()
            
            # Indexer pour recherche lexicale
            self._index_document_for_lexical_search(docs, article.original_filename, images, figures_tables)
            self._save_lexical_index()
            
            print(f"✅ Article '{article.title}' ajouté au système RAG")
            return True
            
        except Exception as e:
            print(f"❌ Erreur ajout article au RAG: {e}")
            return False
    
    def _extract_images_from_pdf(self, pdf_path):
        """Extrait les images d'un fichier PDF"""
        images = []
        try:
            doc = fitz.open(pdf_path)
            for page_num in range(len(doc)):
                page = doc.load_page(page_num)
                
                # Extraire les images de la page
                image_list = page.get_images(full=True)
                
                for img_idx, img_info in enumerate(image_list):
                    xref = img_info[0]
                    base_image = doc.extract_image(xref)
                    image_bytes = base_image["image"]
                    
                    try:
                        # Convertir les bytes de l'image en objet PIL
                        image = Image.open(BytesIO(image_bytes))
                        
                        # Extraire le texte de l'image si possible (OCR)
                        try:
                            image_text = pytesseract.image_to_string(image)
                        except:
                            image_text = ""
                        
                        # Convertir l'image en base64 pour stockage
                        buffered = BytesIO()
                        image.save(buffered, format=image.format if image.format else "PNG")
                        img_base64 = base64.b64encode(buffered.getvalue()).decode()
                        
                        # Créer une entrée pour cette image
                        image_entry = {
                            "page_num": page_num + 1,
                            "image_idx": img_idx,
                            "text_content": image_text,
                            "image_data": img_base64,
                            "width": image.width,
                            "height": image.height
                        }
                        
                        images.append(image_entry)
                    except Exception as e:
                        print(f"⚠️ Erreur de traitement d'image sur la page {page_num+1}: {str(e)}")
                        continue
            
            return images
        except Exception as e:
            print(f"⚠️ Erreur d'extraction d'images du PDF: {str(e)}")
            return []

    def _extract_figures_tables_from_pdf(self, pdf_path):
        """Extrait les figures et tableaux d'un fichier PDF"""
        elements = []
        try:
            doc = fitz.open(pdf_path)
            for page_num in range(len(doc)):
                page = doc.load_page(page_num)
                
                # Analyse du texte pour détecter des marqueurs de figure/tableau
                text_blocks = page.get_text("blocks")
                for block in text_blocks:
                    block_text = block[4]
                    
                    # Détecter les légendes de figure ou de tableau
                    if re.search(r'(figure|fig\.|tableau|table)\s+\d+', block_text.lower()):
                        # Extraire la zone autour du bloc qui pourrait contenir une figure/tableau
                        x0, y0, x1, y1 = block[0], block[1], block[2], block[3]
                        # Élargir légèrement la zone
                        margin = 20
                        figure_rect = fitz.Rect(x0-margin, y0-margin, x1+margin, y1+margin)
                        
                        # Capturer cette zone comme une image
                        pix = page.get_pixmap(clip=figure_rect)
                        img_data = pix.tobytes()
                        
                        # Convertir en image PIL
                        try:
                            image = Image.frombytes("RGB", [pix.width, pix.height], img_data)
                            
                            # OCR sur la figure/tableau potentiel
                            try:
                                element_text = pytesseract.image_to_string(image)
                            except:
                                element_text = block_text  # Utiliser la légende si l'OCR échoue
                            
                            # Convertir en base64
                            buffered = BytesIO()
                            image.save(buffered, format="PNG")
                            img_base64 = base64.b64encode(buffered.getvalue()).decode()
                            
                            element_entry = {
                                "type": "figure" if "fig" in block_text.lower() else "table",
                                "page_num": page_num + 1,
                                "caption": block_text,
                                "text_content": element_text,
                                "image_data": img_base64,
                                "width": pix.width,
                                "height": pix.height
                            }
                            
                            elements.append(element_entry)
                        except Exception as e:
                            print(f"⚠️ Erreur de traitement d'élément sur la page {page_num+1}: {str(e)}")
                            continue
            
            return elements
        except Exception as e:
            print(f"⚠️ Erreur d'extraction de figures/tableaux du PDF: {str(e)}")
            return []
    
    def _index_document_for_lexical_search(self, docs, filename, images=None, figures_tables=None):
        """Indexer un document pour la recherche lexicale"""
        # Copie exacte de ta fonction existante
        full_text = " ".join(doc.page_content for doc in docs)
        
        # Ajouter textes des images et figures
        if images:
            for img in images:
                if img["text_content"]:
                    full_text += f" Image: {img['text_content']}"
        
        if figures_tables:
            for elem in figures_tables:
                if elem["text_content"]:
                    full_text += f" {elem['type'].capitalize()}: {elem['caption']} - {elem['text_content']}"
        
        self.lexical_index[filename] = {
            "content": full_text,
            "chunks": [doc.page_content for doc in docs],
            "images": images if images else [],
            "figures_tables": figures_tables if figures_tables else []
        }
    
    def ask(self, question: str, article_id: Optional[int] = None, return_metadata: bool = False, validation_threshold: float = 0.7):
        """
        Poser une question au système RAG
        
        Args:
            question: La question
            article_id: ID d'article spécifique (optionnel)
            return_metadata: Retourner les métadonnées de vérification
            validation_threshold: Seuil de validation
        """
        try:
            # Construire les filtres pour la recherche
            search_filters = {}
            if self.user_id:
                search_filters["user_id"] = self.user_id
            if article_id:
                search_filters["article_id"] = article_id
            
            # Récupérer le contexte
            if search_filters:
                # Recherche avec filtres (nécessite une implémentation custom)
                docs = self._filtered_search(question, search_filters)
            else:
                docs = self.retriever.invoke(question)
            
            if not docs:
                response_data = {
                    "answer": "Aucune information pertinente trouvée dans les documents.",
                    "verification_status": "no_context",
                    "verification_details": None
                }
                self._add_to_conversation_memory(question, response_data["answer"])
                return response_data if return_metadata else response_data["answer"]
            
            # Préparer le contexte multimodal
            context_parts = []
            for doc in docs:
                context_parts.append(doc.page_content)
                
                if hasattr(doc, 'metadata'):
                    if doc.metadata.get('type') == 'image':
                        context_parts.append(f"[INFORMATION VISUELLE] {doc.metadata.get('text_content', '')}")
                    elif doc.metadata.get('type') in ['figure', 'table']:
                        context_parts.append(f"[{doc.metadata.get('type').upper()}] {doc.metadata.get('caption', '')} - {doc.metadata.get('text_content', '')}")
            
            context = "\n\n".join(context_parts)
            
            # Vérifications qualité (utilise tes fonctions existantes)
            if return_metadata:
                context_verification = self._verify_context_relevance(question, context)
                if context_verification["score"] <= 0.5:
                    # Recherche supplémentaire
                    additional_docs = self.vectorstore.similarity_search(question, k=5)
                    additional_context = "\n\n".join([doc.page_content for doc in additional_docs if doc not in docs])
                    if additional_context:
                        context += "\n\n" + additional_context
                        context_verification = self._verify_context_relevance(question, context)
            
            # Construire le prompt avec mémoire
            memory_context = self._build_memory_context()
            full_context = f"{memory_context}\n=== DOCUMENT CONTEXT ===\n{context}\n=== END OF CONTEXT ==="
            
            prompt = self._build_prompt(question, full_context)
            
            # Générer la réponse
            response = ollama.chat(
                model=current_app.config.get('DEFAULT_SUMMARIZATION_MODEL', 'DeepSeek-R1'),
                messages=[
                    {'role': 'system', 'content': "Vous devez maintenir la continuité de la conversation."},
                    {'role': 'user', 'content': prompt}
                ]
            )
            
            answer = self._clean_think_blocks(response['message']['content'])
            
            # Vérifications qualité si demandées
            verification_result = None
            final_answer = answer
            status = "generated"
            final_score = 0.5
            
            if return_metadata:
                faithfulness_verification = self._verify_answer_faithfulness(context, answer)
                relevance_verification = self._verify_answer_relevance(question, answer)
                
                verification_result = {
                    "context_relevance": context_verification,
                    "answer_faithfulness": faithfulness_verification,
                    "answer_relevance": relevance_verification
                }
                
                final_score = (
                    context_verification["score"] * 0.2 +
                    faithfulness_verification["score"] * 0.4 +
                    relevance_verification["score"] * 0.4
                )
                
                is_valid = final_score >= validation_threshold
                status = "validated" if is_valid else "needs_improvement"
                
                if not is_valid:
                    improved_answer = self._suggest_improved_answer(question, context, answer, verification_result)
                    if improved_answer:
                        final_answer = improved_answer
                        status = "corrected"
            
            # Ajouter à la mémoire
            self._add_to_conversation_memory(question, final_answer)
            
            # Retourner résultat
            result_dict = {
                "answer": final_answer,
                "verification_status": status,
                "verification_score": final_score,
                "verification_details": verification_result
            }
            
            return result_dict if return_metadata else final_answer
            
        except Exception as e:
            error_msg = f"❌ Erreur génération réponse: {str(e)}"
            print(error_msg)
            error_result = {
                "answer": error_msg,
                "verification_status": "error",
                "verification_details": None
            }
            return error_result if return_metadata else error_result["answer"]
    
    def _filtered_search(self, question: str, filters: dict, k: int = 5):
        """Recherche avec filtres sur les métadonnées"""
        try:
            # Pour l'instant, recherche simple puis filtrage
            # Tu peux améliorer avec des filtres Chroma natifs
            all_docs = self.vectorstore.similarity_search(question, k=k*3)
            
            filtered_docs = []
            for doc in all_docs:
                if hasattr(doc, 'metadata'):
                    match = True
                    for key, value in filters.items():
                        if doc.metadata.get(key) != value:
                            match = False
                            break
                    if match:
                        filtered_docs.append(doc)
                        if len(filtered_docs) >= k:
                            break
            
            return filtered_docs[:k]
        except Exception as e:
            print(f"⚠️ Erreur recherche filtrée: {e}")
            return self.vectorstore.similarity_search(question, k=k)
    
    def _build_memory_context(self):
        """Construire le contexte de mémoire conversationnelle"""
        if not self.conversation_memory:
            return ""
        
        memory_entries = []
        for idx, entry in enumerate(self.conversation_memory[-5:]):  # 5 derniers échanges
            memory_entries.append(f"Échange {idx+1}:\nQuestion: {entry['question']}\nRéponse: {entry['answer']}")
        
        return "=== HISTORIQUE DES CONVERSATIONS PRÉCÉDENTES ===\n" + "\n\n".join(memory_entries) + "\n\n=== FIN DE L'HISTORIQUE ===\n\n"
    
    def _build_prompt(self, question: str, full_context: str):
        """Construire le prompt pour la génération"""
        return f"""You are an AI assistant with access to textual and visual information from documents.
Your mission is to answer the user's question based ONLY on the provided context and the history of previous conversations.

IMPORTANT INSTRUCTIONS:
1. Use previous conversation history to keep continuity and coherence.
2. If the question refers to a past message, take that into account.
3. ALWAYS respond in the language of the question.
4. NEVER invent facts — only use what is present in the context or history.
5. Do NOT mention 'context' or 'source' unless asked to.

{full_context}

CURRENT QUESTION: {question}

Respond concisely and clearly, as if speaking naturally to the user."""
    
    def _add_to_conversation_memory(self, question: str, answer: str):
        """Ajouter un échange à la mémoire conversationnelle"""
        self.conversation_memory.append({
            "question": question,
            "answer": answer,
            "timestamp": time.time()
        })
        
        # Limiter la mémoire (garder les 50 derniers échanges)
        if len(self.conversation_memory) > 50:
            self.conversation_memory = self.conversation_memory[-50:]
        
        self._save_conversation_memory()
    
    def _verify_context_relevance(self, question: str, context: str):
        """Vérifier la pertinence du contexte (copie de ta fonction)"""
        try:
            prompt = f"""
            You are an expert in information retrieval systems. 
            Evaluate whether the provided context is helpful for answering the question.

            Question: {question}
            Context: {context}

            Respond with a numerical score between 0 and 1:
            - 0.0: Completely irrelevant
            - 0.5: Moderate relevance 
            - 1.0: Highly relevant

            Format: [SCORE: X.X] Explanation...
            """
            
            response = ollama.chat(
                model=self.verification_model,
                messages=[{'role': 'user', 'content': prompt}]
            )
            
            result = response['message']['content']
            score_match = re.search(r'\[SCORE:\s*(\d+\.\d+|\d+)\]', result)
            
            if score_match:
                score = float(score_match.group(1))
                score = max(0.0, min(score, 1.0))
            else:
                score = 0.5
            
            return {
                "score": score,
                "is_relevant": score >= 0.5,
                "explanation": result.strip()
            }
        except Exception as e:
            print(f"❌ Erreur vérification contexte: {e}")
            return {"score": 0.5, "is_relevant": True, "explanation": "Erreur de vérification"}
    
    def _verify_answer_faithfulness(self, context: str, answer: str):
        """Vérifier la fidélité de la réponse"""
        try:
            prompt = f"""
            Evaluate whether the answer is accurate and based on the provided context.

            Context: {context}
            Answer: {answer}

            Score from 0 to 1:
            - 0.0: Complete hallucination
            - 0.5: Mix of supported and unsupported information
            - 1.0: Completely faithful

            Format: [SCORE: X.X] Explanation...
            """
            
            response = ollama.chat(
                model=self.verification_model,
                messages=[{'role': 'user', 'content': prompt}]
            )
            
            result = response['message']['content']
            score_match = re.search(r'\[SCORE:\s*(\d+\.\d+|\d+)\]', result)
            
            if score_match:
                score = float(score_match.group(1))
                score = max(0.0, min(score, 1.0))
            else:
                score = 0.5
            
            return {
                "score": score,
                "is_faithful": score >= 0.5,
                "explanation": result.strip()
            }
        except Exception as e:
            print(f"❌ Erreur vérification fidélité: {e}")
            return {"score": 0.5, "is_faithful": True, "explanation": "Erreur de vérification"}
    
    def _verify_answer_relevance(self, question: str, answer: str):
        """Vérifier la pertinence de la réponse"""
        try:
            prompt = f"""
            Evaluate whether the answer effectively responds to the question.

            Question: {question}
            Answer: {answer}

            Score from 0 to 1:
            - 0.0: Completely off-topic
            - 0.5: Partially addresses the question
            - 1.0: Fully addresses the question

            Format: [SCORE: X.X] Explanation...
            """
            
            response = ollama.chat(
                model=self.verification_model,
                messages=[{'role': 'user', 'content': prompt}]
            )
            
            result = response['message']['content']
            score_match = re.search(r'\[SCORE:\s*(\d+\.\d+|\d+)\]', result)
            
            if score_match:
                score = float(score_match.group(1))
                score = max(0.0, min(score, 1.0))
            else:
                score = 0.5
            
            return {
                "score": score,
                "is_relevant": score >= 0.5,
                "explanation": result.strip()
            }
        except Exception as e:
            print(f"❌ Erreur vérification pertinence: {e}")
            return {"score": 0.5, "is_relevant": True, "explanation": "Erreur de vérification"}
    
    def _suggest_improved_answer(self, question: str, context: str, answer: str, verification_result: dict):
        """Suggérer une réponse améliorée"""
        try:
            issues = []
            if verification_result["context_relevance"]["score"] < 0.7:
                issues.append(f"Contexte peu pertinent: {verification_result['context_relevance']['explanation']}")
            if verification_result["answer_faithfulness"]["score"] < 0.7:
                issues.append(f"Réponse infidèle: {verification_result['answer_faithfulness']['explanation']}")
            if verification_result["answer_relevance"]["score"] < 0.7:
                issues.append(f"Réponse peu pertinente: {verification_result['answer_relevance']['explanation']}")
            
            prompt = f"""
            As a scientific expert, correct the following answer based on the issues identified.

            Your correction must:
            1. Use ONLY information found in the provided context
            2. Stay logically faithful (even if rephrased)
            3. Directly answer the question
            4. Avoid any hallucinations or invented facts

            Question: {question}

            Available context:
            {context}

            Original answer:
            {answer}

            Identified issues:
            {'; '.join(issues)}

            Write a corrected answer below (without mentioning the corrections or issues):
            """
            
            response = ollama.chat(
                model=current_app.config.get('DEFAULT_SUMMARIZATION_MODEL', 'DeepSeek-R1'),
                messages=[{'role': 'user', 'content': prompt}]
            )
            
            return self._clean_think_blocks(response['message']['content'])
        except Exception as e:
            print(f"❌ Erreur amélioration réponse: {e}")
            return answer
    
    def _clean_think_blocks(self, text: str) -> str:
        """Nettoyer les blocs de réflexion"""
        text = re.sub(r'<think>.*?</think>', '', text, flags=re.DOTALL)
        text = re.sub(r'<reasoning>.*?</reasoning>', '', text, flags=re.DOTALL)
        return text.strip()
    
    def get_recommendations(self, text: str, n: int = 3, current_filename: Optional[str] = None):
        """Obtenir des recommandations basées sur un texte"""
        results = []
        
        try:
            # 1. Recherche vectorielle
            embedding = self.embeddings.embed_query(text[:1000])
            chroma_results = self.vectorstore.similarity_search_by_vector(embedding, k=n+5)
            
            for doc in chroma_results:
                if hasattr(doc, 'metadata') and 'source' in doc.metadata:
                    filename = os.path.basename(doc.metadata['source'])
                    if current_filename and filename == current_filename:
                        continue
                    
                    # Récupérer l'article correspondant depuis la DB
                    article = None
                    if 'article_id' in doc.metadata:
                        article = Article.query.get(doc.metadata['article_id'])
                    
                    results.append({
                        'title': article.title if article else f"Document: {filename}",
                        'snippet': doc.page_content[:200] + "...",
                        'source': 'local',
                        'relevance': 'élevée',
                        'filename': filename,
                        'article': article.to_dict() if article else None
                    })
            
            # 2. Recherche lexicale
            lexical_results = self._lexical_search(text[:1000], n)
            for result in lexical_results:
                if current_filename and result['filename'] == current_filename:
                    continue
                if not any(r.get('filename') == result['filename'] for r in results):
                    results.append(result)
            
            # 3. Recherche ArXiv pour compléter
            if len(results) < n:
                arxiv_results = self._search_arxiv(text, n - len(results))
                results.extend(arxiv_results)
            
            return self._rerank_results(results, text)[:n]
            
        except Exception as e:
            print(f"❌ Erreur recommandations: {e}")
            return []
    
    def _lexical_search(self, query: str, n: int = 3):
        """Recherche lexicale dans l'index"""
        results = []
        query_lower = query.lower()
        keywords = query_lower.split()
        
        for filename, data in self.lexical_index.items():
            score = sum(1 for keyword in keywords if keyword in data["content"].lower())
            
            if score > 0:
                best_chunk = ""
                best_score = 0
                
                for chunk in data["chunks"]:
                    chunk_score = sum(1 for keyword in keywords if keyword in chunk.lower())
                    if chunk_score > best_score:
                        best_score = chunk_score
                        best_chunk = chunk
                
                results.append({
                    "filename": filename,
                    "score": score,
                    "snippet": best_chunk[:200] + "...",
                    "title": f"Document: {filename}",
                    "source": "local",
                    "relevance": f"lexical: {score}"
                })
        
        results.sort(key=lambda x: x["score"], reverse=True)
        return results[:n]
    
    def _search_arxiv(self, text: str, n: int = 3):
        """Recherche sur ArXiv"""
        try:
            # Extraire mots-clés
            prompt = f"""Extract 5 academic keywords from this text for ArXiv search. Return only keywords separated by commas: {text[:500]}"""
            
            response = ollama.chat(
                model=current_app.config.get('DEFAULT_SUMMARIZATION_MODEL', 'DeepSeek-R1'),
                messages=[{'role': 'user', 'content': prompt}]
            )
            
            keywords = self._clean_think_blocks(response['message']['content'])
            
            # Recherche ArXiv avec filtre récent
            current_year = datetime.datetime.now().year
            date_filter = f"+AND+submittedDate:[{current_year-1}0101+TO+{current_year}1231]"
            query = keywords.replace(',', '+OR+') + date_filter
            
            arxiv_url = f"http://export.arxiv.org/api/query?search_query={query}&start=0&max_results={n*2}"
            
            response = requests.get(arxiv_url, timeout=10)
            if response.status_code == 200:
                feed = feedparser.parse(response.content)
                
                results = []
                for entry in feed.entries:
                    if 'published' in entry:
                        year = int(entry.published.split('-')[0])
                        if year >= 2024:
                            arxiv_id = entry.id.split('/')[-1]
                            if '/' in arxiv_id:
                                arxiv_id = arxiv_id.split('/')[-1]
                            
                            results.append({
                                'title': entry.title,
                                'snippet': entry.summary[:200].replace('\n', ' ') + "...",
                                'source': 'arxiv',
                                'relevance': f'récent ({year})',
                                'url': entry.link,
                                'pdf_url': f"https://arxiv.org/pdf/{arxiv_id}.pdf",
                                'year': year
                            })
                            
                            if len(results) >= n:
                                break
                
                return results
            
        except Exception as e:
            print(f"⚠️ Erreur recherche ArXiv: {e}")
        
        return []
    
    def _rerank_results(self, results: list, query_text: str):
        """Réordonner les résultats par pertinence"""
        try:
            SOURCE_WEIGHTS = {'local': 1.0, 'arxiv': 0.6}
            
            # Éliminer doublons
            unique_results = []
            seen_identifiers = set()
            
            for result in results:
                identifier = None
                if result.get('source') == 'local' and 'filename' in result:
                    identifier = f"local:{result['filename']}"
                elif 'title' in result:
                    identifier = f"{result.get('source', 'unknown')}:{result['title']}"
                
                if identifier and identifier not in seen_identifiers:
                    seen_identifiers.add(identifier)
                    unique_results.append(result)
            
            # Calculer scores
            scored_results = []
            query_embedding = self.embeddings.embed_query(query_text[:1000])
            
            for result in unique_results:
                base_score = SOURCE_WEIGHTS.get(result['source'], 0.5)
                
                # Bonus pour articles récents
                if result.get('source') == 'arxiv' and result.get('year', 0) >= 2024:
                    base_score += 1.0 if result['year'] == datetime.datetime.now().year else 0.8
                
                # Score sémantique
                try:
                    content = result.get('snippet', '')
                    if content:
                        content_embedding = self.embeddings.embed_query(content)
                        tensor1 = torch.tensor([query_embedding])
                        tensor2 = torch.tensor([content_embedding])
                        similarity = float(util.pytorch_cos_sim(tensor1, tensor2)[0][0])
                        semantic_score = similarity * 2.0
                    else:
                        semantic_score = 0.0
                except:
                    semantic_score = 0.0
                
                final_score = base_score + semantic_score
                scored_results.append((result, final_score))
            
            # Trier par score
            scored_results.sort(key=lambda x: x[1], reverse=True)
            return [item[0] for item in scored_results]
            
        except Exception as e:
            print(f"⚠️ Erreur reranking: {e}")
            return results
    
    def get_user_articles(self) -> List[Dict]:
        """Obtenir les articles de l'utilisateur actuel"""
        if not self.user_id:
            return []
        
        try:
            articles = Article.query.filter_by(
                user_id=self.user_id,
                is_deleted=False
            ).order_by(Article.created_at.desc()).all()
            
            return [article.to_dict() for article in articles]
        except Exception as e:
            print(f"❌ Erreur récupération articles: {e}")
            return []
    
    def clear_user_memory(self):
        """Vider la mémoire conversationnelle de l'utilisateur"""
        self.conversation_memory = []
        self._save_conversation_memory()
        print("🗑️ Mémoire conversationnelle vidée")


# Factory function pour créer une instance RAG
def create_rag_system(user_id: Optional[int] = None) -> EnhancedMUragSystem:
    """Créer une instance du système RAG pour un utilisateur"""
    return EnhancedMUragSystem(user_id=user_id)