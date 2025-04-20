// static/js/app.js

document.addEventListener('DOMContentLoaded', () => {
    // ----- Sélecteurs -----
    const micBtn        = document.getElementById('mic-btn');
    const resetBtn      = document.getElementById('reset-btn');
    const statusDot     = document.querySelector('.status-dot');
    const statusText    = document.querySelector('.status-text');
    const conversation  = document.getElementById('conversation-container');
    const welcomeMsg    = document.getElementById('welcome-message');
    const profileName   = document.getElementById('profile-name');
    const profileAgeCity= document.getElementById('profile-age-city');
    const profileJob    = document.getElementById('profile-job');
    const overlay       = document.getElementById('connection-overlay');
    const connLostMsg   = document.getElementById('connection-lost-message');
    const settingsBtn   = document.getElementById('settings-btn');
    const settingsModal = document.getElementById('settings-modal');
    const closeModalBtn = document.getElementById('close-modal');
    const themeToggle   = document.getElementById('theme-toggle');
    
    // ----- Sélecteurs pour les réglages -----
    const voiceVolumeSlider = document.getElementById('voice-volume');
    const speechSpeedSlider = document.getElementById('speech-speed');
    const autoListenToggle = document.getElementById('auto-listen');
    const silenceTimeoutSlider = document.getElementById('silence-timeout');
    const silenceTimeoutValue = document.querySelector('.range-value');
  
    // ----- State -----
    let recognition    = null;
    let isPaused       = true;     // true tant que la conversation n'a pas démarré ou est en pause
    let isListening    = false;
    let pendingMsgEl   = null;
    let pendingMsgText = '';
    let silenceCount   = 0;
    let lastTranscript = null;
    let isDarkTheme    = true;     // Par défaut theme sombre
  
    // Affiche l'overlay 1.5s au chargement
    overlay.classList.remove('hidden');
    setTimeout(() => overlay.classList.add('hidden'), 300);
  
    // ----- Socket.IO -----
    const socket = io();
    socket.on('connect', () => {
      updateStatus('connecté','connected');
      connLostMsg.style.display = 'none';
    });
    socket.on('disconnect', () => {
      updateStatus('déconnecté','disconnected');
      // Afficher le message de perte de connexion avec une animation
      connLostMsg.style.display = 'block';
    });
  
    socket.on('transcription', ({ text }) => {
      if (isPaused) return;
      appendMessage(text,'user');
    });
  
    socket.on('response_chunk', ({ text }) => {
      if (isPaused) return;
      if (!pendingMsgEl) {
        pendingMsgText = text;
        pendingMsgEl   = appendMessage(text,'assistant');
      } else {
        pendingMsgText += text;
        pendingMsgEl.querySelector('p').textContent = pendingMsgText;
      }
    });
  
    socket.on('audio_response', ({ audio }) => {
      if (isPaused) return;
      pendingMsgText = '';
      pendingMsgEl   = null;
      const player = new Audio(`data:audio/wav;base64,${audio}`);
      
      // Appliquer le volume
      const volume = voiceVolumeSlider.value / 100;
      player.volume = volume;
      
      // Appliquer la vitesse de lecture (si supportée)
      if ('playbackRate' in player) {
        player.playbackRate = parseFloat(speechSpeedSlider.value);
      }
      
      player.play();
      updateStatus('connecté','connected');
      player.onended = () => {
        if (!isPaused && silenceCount < 3) {
          // Ne démarre l'écoute que si autoListen est activé
          if (autoListenToggle.checked) {
            startListening();
          } else {
            // Si l'écoute automatique est désactivée, désactiver le micro après la réponse
            pauseConversation();
          }
        } else if (silenceCount >= 3) {
          updateStatus('appel terminé','ended');
          pauseConversation();
        }
      };
    });
  
    // Écouter les mises à jour du délai de silence
    socket.on('silence_timeout_updated', (data) => {
      if (data && data.timeout) {
        silenceTimeoutSlider.value = data.timeout;
        silenceTimeoutValue.textContent = data.timeout;
        localStorage.setItem('silenceTimeout', data.timeout);
      }
    });
  
    // ----- UI Helpers -----
    function updateStatus(txt, state) {
      // state ∈ { connected, listening, disconnected, ended }
      statusText.textContent = txt;
      statusDot.className    = `status-dot ${state}`;
    }
  
    function appendMessage(txt, role) {
      welcomeMsg.style.display   = 'none';
      conversation.style.display = 'block';
      const div = document.createElement('div');
      div.className = `message ${role}`;
      
      // Créer la bulle avec avatar et nom différents selon le rôle
      if (role === 'assistant') {
        // Récupérer l'avatar et le nom du profil
        const avatarSrc = document.querySelector('.profile-image img')?.src || '/static/avatars/default.png';
        const name = document.getElementById('profile-name').textContent;
        
        div.innerHTML = `
          <div class="message-avatar">
            <img src="${avatarSrc}" alt="Avatar">
          </div>
          <div class="message-content">
            <div class="message-sender">${name}</div>
            <p>${txt}</p>
            <div class="message-time">
              ${new Date().toLocaleTimeString('fr-FR',{hour:'2-digit',minute:'2-digit'})}
            </div>
          </div>
        `;
      } else {
        // Pour l'utilisateur (escroc)
        div.innerHTML = `
          <div class="message-content">
            <div class="message-sender">Escroc</div>
            <p>${txt}</p>
            <div class="message-time">
              ${new Date().toLocaleTimeString('fr-FR',{hour:'2-digit',minute:'2-digit'})}
            </div>
          </div>
          <div class="message-avatar">
            <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5">
              <path d="M20 21v-2a4 4 0 0 0-4-4H8a4 4 0 0 0-4 4v2"></path>
              <circle cx="12" cy="7" r="4"></circle>
            </svg>
          </div>
        `;
      }
      
      conversation.appendChild(div);
      conversation.scrollTop = conversation.scrollHeight;
      return div;
    }
  
    // ----- Chargement du profil -----
    async function loadProfile() {
      const res = await fetch('/get_profile');
      const p   = await res.json();
      profileName.textContent    = p.name;
      profileAgeCity.textContent = `${p.age} ans • ${p.city}`;
      profileJob.textContent     = p.job;
      
      // Mise à jour de l'avatar
      const profileImage = document.querySelector('.profile-image');
      profileImage.innerHTML = `<img src="${p.avatar ? '/static/' + p.avatar : '/static/avatars/default.png'}" alt="Avatar">`;
    }
    loadProfile();
  
    // ----- Chargement des réglages -----
    async function loadSettings() {
      // Silence timeout - d'abord essayer de récupérer du serveur
      try {
        const response = await fetch('/get_silence_timeout');
        const data = await response.json();
        if (data && data.timeout) {
          silenceTimeoutSlider.value = data.timeout;
          silenceTimeoutValue.textContent = data.timeout;
        }
      } catch (e) {
        // Si échec, utiliser localStorage
        const savedSilenceTimeout = localStorage.getItem('silenceTimeout');
        if (savedSilenceTimeout) {
          silenceTimeoutSlider.value = savedSilenceTimeout;
          silenceTimeoutValue.textContent = savedSilenceTimeout;
        }
      }
      
      // Voice volume
      const savedVoiceVolume = localStorage.getItem('voiceVolume');
      if (savedVoiceVolume) {
        voiceVolumeSlider.value = savedVoiceVolume;
      }
      
      // Speech speed
      const savedSpeechSpeed = localStorage.getItem('speechSpeed');
      if (savedSpeechSpeed) {
        speechSpeedSlider.value = savedSpeechSpeed;
      }
      
      // Auto listen
      const savedAutoListen = localStorage.getItem('autoListen');
      if (savedAutoListen !== null) {
        autoListenToggle.checked = savedAutoListen === 'true';
      }
    };
    
    // Timer pour gérer le délai de silence manuellement
    let silenceTimer = null;
    
    // ----- Reconnaissance vocale -----
    function startListening() {
      if (isListening || isPaused) return;
      const SR = window.SpeechRecognition || window.webkitSpeechRecognition;
      if (!SR) return alert('Reconnaissance vocale non supportée');
      recognition = new SR();
      recognition.lang           = 'fr-FR';
      recognition.interimResults = false;
      recognition.continuous     = false;
      
      // Configurer le délai de silence
      const silenceDelay = parseInt(silenceTimeoutSlider.value) * 1000; // Convertir en ms
      
      lastTranscript = null;
  
      recognition.onstart = () => {
        isListening = true;
        updateStatus('écoute','listening');
        
        // Arrêter un timer précédent si existant
        if (silenceTimer) {
          clearTimeout(silenceTimer);
        }
        
        // Démarrer un timer pour détecter le silence
        silenceTimer = setTimeout(() => {
          // Si on est toujours en écoute après le délai et sans transcript, c'est un silence
          if (isListening && !lastTranscript) {
            recognition.stop();
          }
        }, silenceDelay);
      };
      
      recognition.onresult = e => {
        const text = Array.from(e.results)
          .map(r=>r[0].transcript)
          .join('').trim();
        lastTranscript = text;
        silenceCount = 0;
        socket.emit('send_text',{ text });
        
        // Réinitialiser le timer de silence car on a détecté de la parole
        if (silenceTimer) {
          clearTimeout(silenceTimer);
        }
      };
      
      recognition.onerror = () => {
        // pas d'envoi ici
        if (silenceTimer) {
          clearTimeout(silenceTimer);
        }
      };
      
      recognition.onend = () => {
        isListening = false;
        if (silenceTimer) {
          clearTimeout(silenceTimer);
          silenceTimer = null;
        }
        
        if (!lastTranscript && !isPaused) {
          silenceCount++;
          socket.emit('send_text',{ text: '' });
        }
      };
  
      recognition.start();
    }
  
    function stopListening() {
      if (recognition && isListening) {
        recognition.stop();
        isListening = false;
      }
    }
  
    function resumeConversation() {
      isPaused = false;
      micBtn.classList.add('recording');
      updateStatus('connecté','connected');
      startListening();
    }
  
    function pauseConversation() {
      isPaused = true;
      micBtn.classList.remove('recording');
      stopListening();
      updateStatus('connecté','connected');
    }
  
    // ----- Boutons -----
    micBtn.addEventListener('click', () => {
      if (isPaused) resumeConversation();
      else pauseConversation();
    });
  
    resetBtn.addEventListener('click', async () => {
      await fetch('/reset_profile',{ method:'POST' });
      window.location.reload();
    });
  
    // ----- Réglages Modal -----
    settingsBtn.addEventListener('click', () => {
      settingsModal.classList.add('show');
    });
    
    closeModalBtn.addEventListener('click', () => {
      settingsModal.classList.remove('show');
    });
    
    // Fermer le modal en cliquant en dehors
    settingsModal.addEventListener('click', (e) => {
      if (e.target === settingsModal) {
        settingsModal.classList.remove('show');
      }
    });
    
    // Amélioration des toggles pour qu'ils fonctionnent en cliquant sur le slider
    document.querySelectorAll('.toggle-switch').forEach(toggle => {
      toggle.addEventListener('click', (e) => {
        if (e.target.classList.contains('toggle-slider')) {
          const checkbox = e.target.previousElementSibling;
          checkbox.checked = !checkbox.checked;
          checkbox.dispatchEvent(new Event('change'));
        }
      });
    });
    
    // Toggle theme clair/sombre
    themeToggle.addEventListener('change', () => {
      isDarkTheme = !isDarkTheme;
      document.body.classList.toggle('light-theme');
      localStorage.setItem('theme', isDarkTheme ? 'dark' : 'light');
    });
    
    // Charger le thème sauvegardé
    const savedTheme = localStorage.getItem('theme');
    if (savedTheme === 'light') {
      isDarkTheme = false;
      document.body.classList.add('light-theme');
      themeToggle.checked = true;
    }
    
    // Mise à jour de la valeur affichée près du slider
    silenceTimeoutSlider.addEventListener('input', (e) => {
      silenceTimeoutValue.textContent = e.target.value;
    });
    
    // Mise à jour des réglages
    silenceTimeoutSlider.addEventListener('change', (e) => {
      const value = parseInt(e.target.value);
      localStorage.setItem('silenceTimeout', value);
      // Mettre à jour la valeur dans le backend
      socket.emit('update_silence_timeout', { value });
    });
    
    voiceVolumeSlider.addEventListener('change', (e) => {
      localStorage.setItem('voiceVolume', e.target.value);
    });
    
    speechSpeedSlider.addEventListener('change', (e) => {
      localStorage.setItem('speechSpeed', e.target.value);
    });
    
    autoListenToggle.addEventListener('change', (e) => {
      localStorage.setItem('autoListen', e.target.checked);
    });
    
    // Charger les réglages au démarrage
    loadSettings();
  });
  