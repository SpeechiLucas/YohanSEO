# /app.py

import os
import re
import json
from flask import Flask, render_template, request, jsonify
from openai import OpenAI
import requests
from bs4 import BeautifulSoup
from urllib.parse import urljoin

app = Flask(__name__)

# --- INITIALISATION CLIENT OPENAI ---
client = None
api_key = os.environ.get("OPENAI_API_KEY")
if not api_key:
    print("ERREUR CRITIQUE: La variable d'environnement OPENAI_API_KEY est manquante.")
else:
    try:
        client = OpenAI(api_key=api_key)
        print("Client OpenAI initialisé avec succès.")
    except Exception as e:
        print(f"Une erreur est survenue lors de l'initialisation du client OpenAI : {e}")

# --- FONCTIONS UTILITAIRES ---
def scrape_links_from_url(base_url):
    if not base_url: return "Aucune URL fournie."
    try:
        headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/58.0.3029.110 Safari/537.36'}
        response = requests.get(base_url, headers=headers, timeout=10)
        response.raise_for_status()
        soup = BeautifulSoup(response.text, 'html.parser')
        links_data = []
        for a_tag in soup.find_all('a', href=True):
            link_text = a_tag.get_text(strip=True)
            link_url = a_tag['href']
            if link_text and not link_url.startswith('#') and not link_url.startswith('mailto:'):
                absolute_url = urljoin(base_url, link_url)
                links_data.append(f"- Texte du lien : '{link_text}', URL : {absolute_url}")
        return "\n".join(links_data[:20]) if links_data else "Aucun lien pertinent trouvé sur la page."
    except requests.RequestException as e:
        print(f"Erreur de scraping pour {base_url}: {e}")
        return f"Impossible d'analyser l'URL : {base_url}."

def analyser_densite_mots_cles(html_content, keywords):
    soup = BeautifulSoup(html_content, 'html.parser')
    text = soup.get_text().lower()
    words = re.findall(r'\w+', text)
    total_words = len(words)
    if total_words == 0: return {"total_words": 0, "densities": []}
    analysis = {"total_words": total_words, "densities": []}
    for keyword in keywords:
        kw_lower = keyword.lower()
        count = text.count(kw_lower)
        density = (count / total_words) * 100 if total_words > 0 else 0
        analysis["densities"].append({"keyword": keyword, "count": count, "density": round(density, 2)})
    return analysis

def calculer_score_seo(html_content, seo_title, meta_description, keywords, total_words):
    score, recommendations = 0, []
    soup = BeautifulSoup(html_content, 'html.parser')
    main_keyword = keywords[0].lower()
    if soup.find('h1') and main_keyword in soup.find('h1').get_text().lower(): score += 20
    else: recommendations.append("Le mot-clé principal n'est pas dans le titre H1.")
    if 1200 <= total_words <= 1600: score += 15
    else: recommendations.append(f"La longueur ({total_words} mots) est hors cible (1200-1500).")
    if 40 <= len(seo_title) <= 60: score += 15
    else: recommendations.append(f"Le titre SEO ({len(seo_title)} car.) est hors cible (40-60).")
    if 120 <= len(meta_description) <= 160: score += 10
    else: recommendations.append(f"La méta-description ({len(meta_description)} car.) est hors cible (120-160).")
    if len(soup.find_all('a')) >= 4: score += 15
    else: recommendations.append("Visez au moins 4 liens (internes + externes).")
    if len(soup.find_all('h2')) >= 3: score += 15
    else: recommendations.append("Manque de sous-titres H2 pour une bonne structure.")
    secondary_found = False
    if len(keywords) > 1:
        text_content = soup.get_text().lower()
        for kw in keywords[1:]:
            if kw.lower() in text_content: secondary_found = True; break
    if secondary_found: score += 10
    elif len(keywords) > 1: recommendations.append("Mots-clés secondaires peu utilisés.")
    if not recommendations: recommendations.append("Excellent travail ! L'article respecte les bonnes pratiques.")
    return {"score": score, "recommendations": recommendations}

personas = {
    "Claire": "Adopte un ton pédagogique, clair, humain et professionnel.",
    "Chloé": "Adopte un ton direct, énergique et orienté marketing."
}

@app.route('/')
def home():
    return render_template('index.html')

@app.route('/generer-article', methods=['POST'])
def generer_article():
    if client is None:
        return jsonify({'error': "Client OpenAI non initialisé."}), 500

    try:
        # 1. Récupérer les données
        auteur_choisi = request.form.get('auteur', 'Claire')
        url_externe_a_analyser = request.form.get('url_externe_a_analyser')
        url_interne_a_analyser = request.form.get('url_interne_a_analyser')
        mots_clefs_bruts = request.form.get('mots_clefs', '').split(',')
        mots_clefs_propres = [mot.strip() for mot in mots_clefs_bruts if mot.strip()]
        
        if not mots_clefs_propres:
            return jsonify({'error': "Veuillez fournir au moins un mot-clé."}), 400

        mot_clef_principal = mots_clefs_propres[0]
        mots_clefs_secondaires = ", ".join(mots_clefs_propres[1:])

        # 2. Scraper les liens
        liste_liens_externes = scrape_links_from_url(url_externe_a_analyser)
        liste_liens_internes = scrape_links_from_url(url_interne_a_analyser)

        # 3. Construire le prompt final de manière robuste
        persona_instructions = personas.get(auteur_choisi)
        
        json_structure_example = """
        {
          "titre_seo": "Un titre SEO optimisé de moins de 60 caractères.",
          "meta_description": "Une méta-description engageante et optimisée de moins de 160 caractères.",
          "article_html": "Le contenu complet de l'article en code HTML brut.",
          "json_ld_schema": {
            "@context": "https://schema.org",
            "@type": "BlogPosting",
            "headline": "Le titre H1 de l'article",
            "author": { "@type": "Person", "name": "Le nom de l'auteur choisi (Claire ou Chloé)" },
            "keywords": "liste des mots-clés séparés par des virgules"
          },
          "idees_mots_cles_futurs": [
              "Idée de mot-clé connexe 1", "Idée de mot-clé longue-traîne 2", "Une question que les utilisateurs se posent 3", "Un sujet adjacent pour un futur article 4"
          ]
        }
        """

        prompt_final = f"""
        Tu es un expert SEO et un rédacteur web de classe mondiale. Ta tâche est de générer un ensemble complet de contenus pour un article de blog.
        Ta réponse DOIT être un objet JSON unique et valide, sans aucun texte avant ou après, en respectant la structure suivante :
        {json_structure_example}

        Maintenant, voici les instructions pour remplir ce JSON :
        1. ARTICLE HTML : Persona: {persona_instructions}, Longueur: 1200-1500 mots, SEO: mot-clé principal "{mot_clef_principal}" et secondaires "{mots_clefs_secondaires}", Maillage externe: 1 lien de la liste "{liste_liens_externes}", Maillage interne: 3-4 liens de la liste "{liste_liens_internes}".
        2. TITRE SEO & MÉTA-DESCRIPTION : Uniques, attractifs, max 60/160 car.
        3. SCHÉMA JSON-LD : Remplis avec les infos de l'article généré. Auteur: "{auteur_choisi}".
        4. IDÉES DE MOTS-CLÉS FUTURS : Propose 4 idées d'articles connexes basées sur "{mot_clef_principal}".
        """

        # 4. Appeler l'API OpenAI
        chat_completion = client.chat.completions.create(
            model="gpt-5-mini",
            messages=[{"role": "user", "content": prompt_final}],
            response_format={"type": "json_object"}
        )
        response_content = chat_completion.choices[0].message.content
        
        ia_data = json.loads(response_content)
        article_html = ia_data.get("article_html", "<p>Erreur.</p>")
        
        keyword_analysis = analyser_densite_mots_cles(article_html, mots_clefs_propres)
        
        seo_score_data = calculer_score_seo(
            article_html,
            ia_data.get("titre_seo", ""),
            ia_data.get("meta_description", ""),
            mots_clefs_propres,
            keyword_analysis.get("total_words", 0)
        )

        final_response = {
            "article_html": article_html,
            "seo_title": ia_data.get("titre_seo", ""),
            "meta_description": ia_data.get("meta_description", ""),
            "json_ld_schema": json.dumps(ia_data.get("json_ld_schema", {}), indent=2),
            "keyword_analysis": keyword_analysis,
            "keyword_ideas": ia_data.get("idees_mots_cles_futurs", []),
            "seo_score_data": seo_score_data
        }
        
    except Exception as e:
        print(f"Erreur majeure : {e}")
        return jsonify({'error': f"Une erreur est survenue : {e}"}), 500

    return jsonify(final_response)

if __name__ == '__main__':
    app.run(debug=True)
