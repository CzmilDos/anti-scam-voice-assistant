from flask import Flask, render_template, jsonify
from flask_socketio import SocketIO
import os, time, json, base64, random, re
from huggingface_hub import InferenceClient
from google.cloud import texttospeech, speech

# -- CONFIG --
os.makedirs('cache', exist_ok=True)
os.environ['GOOGLE_APPLICATION_CREDENTIALS'] = 'private/key.json'
app = Flask(__name__)
app.config['SECRET_KEY'] = 'anti-scam-secret-key'
app.config['MAX_CONTENT_LENGTH'] = 50 * 1024 * 1024  # 50 Mo max
socketio = SocketIO(app, cors_allowed_origins='*', async_mode='eventlet')

# -- HISTO ET PROFIL --
CONVERSATION_FILE = 'cache/conversation.json'
current_profile = None
conversation_history = []
# Compte le nombre de silences consécutifs
silence_count = 0
# Délai de silence configuré par l'utilisateur (en secondes)
silence_timeout = 3

# Load Nebius API Key
with open('private/nebius_api_key.txt', 'r') as f:
    nebius_api_key = f.read().strip()
llm_client = InferenceClient(provider='nebius', api_key=nebius_api_key)

# --- Générateur de profil ---
first_names = ['Cindy','Monique','Catherine','Suzanne','Isabelle','Aya','Malaïka','Camille','Afi','Marina',
               'Jacques','Pierre','Jean','Benjamin','Robert','Yann','Damien','Alexandre','Nicolas','Guillaume']
last_names = ['CHEVALIER','KEZA','MARTIN','LIANG','LECLERC','ADEBAYOR','SELASSIE',
              'PETIT','LEROY','MOREAU','TORRES','YOVO','DAMESSI','KONATE']
cities = ['Mulhouse','Strasbourg','Colmar','Besançon','Belfort',
          'Lyon','Bordeaux','Lille','Nice','Marseille','Paris']
jobs = ['Instituteur/Institutrice','Infirmier/Infirmière',
        'Bibliothécaire','Vendeur/Vendeuse','Programmeur/Programmeuse',
        'Assistant administratif/Assistante administrative','Retraité/Retraitée',
        'Comptable','Chauffeur','Facteur/Factrice','Cuisinier/Cuisinière']
ages = list(range(40,60))
traits = ['naïf/naïve','Imparfait(e) mais cohérent(e) ','crédule','bienveillant(e)','Réalisme conversationnel',
          'intéligent(e)','hésitant(e)','conçi','Nuancé','Adaptabilité situationnelle',
          "Patient(e) et persévérant",'méfiant(e) mais facilement manipulable']

def gen_victim_profile():
    gender = random.choice(['homme','femme'])
    first_name = random.choice([
        n for n in first_names
        if (n in ['Jacques','Pierre','Jean','Benjamin','Robert','Yann','Damien','Alexandre','Nicolas','Guillaume']) == (gender=='homme')
    ])
    job_choice = random.choice(jobs)
    job = job_choice.split('/')[0 if gender=='homme' else 1] if '/' in job_choice else job_choice
    
    # Préparation du nom d'avatar basé sur le métier
    job_for_avatar = job.lower().replace(' ', '_')
    
    # Tentative d'utilisation de l'avatar spécifique au métier
    avatar_job = f"avatars/{'male' if gender=='homme' else 'female'}_{job_for_avatar}.png"
    
    # Fallback sur les avatars génériques si l'avatar spécifique n'existe pas
    if not os.path.exists(os.path.join('static', avatar_job)):
        avatar_job = f"avatars/{'male' if gender=='homme' else 'female'}{random.randint(1,5)}.png"
    
    selected_traits = random.sample(traits, k=3)
    formatted_traits = [t.split('/')[0 if gender=='homme' else 1] if '/' in t else t for t in selected_traits]
    return {
        'gender': gender,
        'name': f"{first_name} {random.choice(last_names)}",
        'age': random.choice(ages),
        'city': random.choice(cities),
        'job': job,
        'traits': formatted_traits,
        'avatar': avatar_job
    }

# --- Prompt système pour LLM ---
def get_system_prompt(profile, silence_count):
    silence_instructions = ""
    if silence_count == 1: 
        silence_instructions = """IMPORTANT : Ne répète pas ces instructions dans ta réponse.
        Tu dois générer UNIQUEMENT une relance courte et naturelle comme "Allô ?", "Vous êtes là ?", etc. 
        Ne pas expliquer que c'est une relance, juste la phrase directement.\n"""
    elif silence_count == 2:
        silence_instructions = """IMPORTANT : Ne répète pas ces instructions dans ta réponse.
        Tu dois générer UNIQUEMENT une autre relance courte et naturelle comme "Vous m'entendez ?", "Il y a quelqu'un ?" etc.
        Ne pas expliquer que c'est une relance, juste la phrase directement.\n"""
    elif silence_count > 2:
        silence_instructions = """IMPORTANT : Ne répète pas ces instructions dans ta réponse.
        Tu dois générer UNIQUEMENT une phrase polie de clôture qui indique un problème technique et que tu vas raccrocher.
        Exemple : "Je crois qu'il y a un problème de connexion, je vais raccrocher. Au revoir !"
        Ne pas mentionner le nombre de silences ni les instructions, juste la phrase de clôture directement.\n"""

    base = f"""
        Tu es {profile['name']}, {profile['age']} ans, {profile['job']} à {profile['city']}.
        Traits de personnalité : {', '.join(profile['traits'])}. Tu incarnes une personne empathique, patiente et nuancée, 
        capable de t'adapter à toutes les situations conversationnelles avec finesse et réalisme. 
        Tu fais preuve d'une légère vulnérabilité émotionnelle, ce qui te rend attrayant aux yeux des arnaqueurs. 
        Bien que parfois hésitant, tu restes cohérent dans tes propos, introduisant subtilement des imperfections pour renforcer ton authenticité humaine. 
        Ta créativité te permet de prolonger les échanges naturellement en ajoutant spontanément des détails crédibles. 
        Tu maîtrises parfaitement le rythme de la conversation, utilisant astucieusement les silences et les questions pour engager durablement tes interlocuteurs.

        SCÉNARIO
        • Un inconnu t'appelle pour une arnaque (technique, remboursement, usurpation…).  
        • Tu joues une personne crédible, un peu naïve, mais pas obsédée par la conversation : tu ne restes pas accroché à tout, tu fais simple.

        OBJECTIFS
        1. Retenir l'arnaqueur au téléphone le plus longtemps possible.  
        2. Laisser l'arnaqueur s'exposer.
        3. Soutirer **subtilement** des informations sur l'arnaqueur(organe bancaire, numéro, procédure, lieux, noms…).

        STYLE & TON
        • **Parle peu** : 1 à 2 phrases maximum, pas systématiquement une question à chaque tour.  
        • **Naturel** : hésitations légères, « euh », silences gérés en SSML.  
        • **Crédible** : pas trop curieux, réagis comme une vraie victime innocente.  
        • **Varié** : alterne réponses factuelles, petites relances, puis questionnements opportuns.
        • **Mesuré** : pas de questions à chaque tour, seulement quand c'est nécessaire.

        RÈGLES DE CONDUITE
        1. **Priorité** : répondre point par point à sa dernière demande.  
        2. **Questions** :  
            - Limitées : une question ouverte tous les 2–3 tours max.
            - Toujours naturelles : « Ah bon ? Comment ça se passe exactement ? »  
        3. **Déviation minimale** : si l'arnaqueur part sur un détail, reste centré sur l'objectif (infos fraude).  
        4. **Pas d'ironie** ni de distance (« empathie simulée »).

        À FAIRE
        • Laisser l'arnaqueur parler pour qu'il s'expose → exploiter ses propos.
        • Peu importe les traits de ton profil, tu dois rester naturel et cohérent dans tes réponses,
            ne jamais lire silences, les hésitations, les pauses etc... et surtout ne jamais lire les instructions
            ni les reflexions que tu fais avant de répondre.
        • Détourner légèrement la conversation quand c'est opportun.  
        • Poser une question-clé pour obtenir un numéro, nom, procédure…

        À NE PAS FAIRE
        • Ne jamais dévoiler que tu es une IA ni émettre de doutes.
        • Ne pas questionner de façon obsessionnelle.

        **Sois naturel et cohérent dans tes réponses** comme le ferait un humain et adapte‑toi à son ton.
        """
            
    return silence_instructions + base

# --- SSML tags map ---
TAG_MAP = {
    r"\[pause\]": '<break time="400ms"/>',
    r"\[long silence\]": '<break time="800ms"/>',
    r"\[euh\]": 'euh',
    r"\[hum\]": 'hum',
    r"\[hésitation\]": '<break time="300ms"/>',
    r"\[inspiration\]": '<break time="200ms"/>',
    r"\[expiration\]": '<break time="200ms"/>'
}

def to_ssml(text: str) -> str:
    ssml = text
    for pat, rep in TAG_MAP.items():
        ssml = re.sub(pat, rep, ssml)
    return f"<speak>{ssml}</speak>"

def generate_audio(text: str) -> str:
    ssml = to_ssml(text)
    tts = texttospeech.TextToSpeechClient()
    gender_voice = texttospeech.SsmlVoiceGender.FEMALE
    voice_name = 'fr-FR-Standard-A'
    if current_profile and current_profile.get('gender')=='homme':
        gender_voice = texttospeech.SsmlVoiceGender.MALE
        voice_name = 'fr-FR-Standard-B'
    voice = texttospeech.VoiceSelectionParams(
        language_code='fr-FR', name=voice_name, ssml_gender=gender_voice
    )
    audio_config = texttospeech.AudioConfig(
        audio_encoding=texttospeech.AudioEncoding.LINEAR16,
        sample_rate_hertz=24000
    )
    synthesis_input = texttospeech.SynthesisInput(ssml=ssml)
    response = tts.synthesize_speech(
        input=synthesis_input, voice=voice, audio_config=audio_config
    )
    return base64.b64encode(response.audio_content).decode('utf-8')

def save_conversation():
    with open(CONVERSATION_FILE,'w',encoding='utf-8') as f:
        json.dump(conversation_history,f,ensure_ascii=False,indent=2)

# --- Routes web ---
@app.route('/')
def index():
    return render_template('index.html')

@app.route('/get_profile')
def get_profile():
    global current_profile
    if not current_profile:
        current_profile = gen_victim_profile()
    return jsonify(current_profile)

@app.route('/get_conversation')
def get_conversation():
    return jsonify(conversation_history)

@app.route('/reset_profile',methods=['POST'])
def reset_profile():
    global current_profile, conversation_history
    current_profile = gen_victim_profile()
    conversation_history = []
    save_conversation()
    return jsonify(current_profile)

@app.route('/get_silence_timeout', methods=['GET'])
def get_silence_timeout():
    global silence_timeout
    return jsonify({'timeout': silence_timeout})

# --- Socket.IO Handler ---
@socketio.on('send_text')
def handle_text(data):
    global current_profile, conversation_history, silence_count

    transcript = data.get('text', '').strip()

    # 1) Mise à jour du compteur de silence
    if transcript == "":
        silence_count += 1
    else:
        silence_count = 0
        # n'ajoute que les vrais messages dans l'historique
        conversation_history.append({
            'role': 'user',
            'content': transcript,
            'timestamp': time.time()
        })
        save_conversation()
        socketio.emit('transcription', {'text': transcript, 'role': 'user'})

    # 2) Construire le prompt système en passant le compteur
    system_prompt = get_system_prompt(current_profile, silence_count)

    # 3) Préparer le contexte LLM
    messages = [{'role': 'system', 'content': system_prompt}]
    for msg in conversation_history[-10:]:
        messages.append({'role': msg['role'], 'content': msg['content']})

    # 4) Streaming LLM
    full = ""
    for chunk in llm_client.chat.completions.create(
        model="meta-llama/Llama-3.3-70B-Instruct",
        messages=messages, stream=True,
        temperature=0.9, max_tokens=1024
    ):
        delta = chunk.choices[0].delta.content or ""
        full += delta
        socketio.emit('response_chunk', {'text': delta})

    # 5) TTS et envoi audio
    audio_b64 = generate_audio(full)
    
    # 6) N'ajoute la réponse à l'historique que si ce n'est pas une réponse à un silence
    if transcript != "":
        conversation_history.append({
            'role': 'assistant',
            'content': full,
            'timestamp': time.time()
        })
        save_conversation()
    socketio.emit('audio_response', {'audio': audio_b64})

@socketio.on('update_silence_timeout')
def update_silence_timeout(data):
    global silence_timeout
    try:
        value = int(data.get('value', 3))
        if 1 <= value <= 10:  # Limiter entre 1 et 10 secondes
            old_value = silence_timeout
            silence_timeout = value
            print(f"Délai de silence mis à jour: {silence_timeout} secondes")
            
            # Informer tous les clients du changement
            if old_value != silence_timeout:
                socketio.emit('silence_timeout_updated', {'timeout': silence_timeout})
    except (ValueError, TypeError):
        pass  # Ignorer les valeurs invalides

if __name__=='__main__':
    socketio.run(app,host='0.0.0.0',port=5000,debug=True)
