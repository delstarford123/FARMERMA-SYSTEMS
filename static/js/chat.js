// Connect to WebSocket Server globally
const socket = io();

let currentActiveChatId = null;
let typingTimeout;

// ==========================================
// 1. INITIALIZATION & THEMES
// ==========================================
const allThemes = [
    'theme-green', 'theme-dark-green', 'theme-blue', 'theme-dark-blue', 
    'theme-white', 'theme-cream-white', 'theme-smoke-white', 'theme-yellow'
];

function changeTheme(themeClass) {
    const wrapper = document.getElementById('chat-theme-wrapper');
    if (!wrapper) return;
    
    wrapper.classList.remove(...allThemes);
    wrapper.classList.add(themeClass);
    localStorage.setItem('farmerman_chat_theme', themeClass);
}

// Run on page load
document.addEventListener('DOMContentLoaded', () => {
    // 1. Load Theme
    const savedTheme = localStorage.getItem('farmerman_chat_theme');
    if (savedTheme && allThemes.includes(savedTheme)) {
        changeTheme(savedTheme);
    } else {
        changeTheme('theme-green'); // Default fallback
    }

    // 2. Auto-Open Chat (if coming from dashboard)
    if (window.AUTO_OPEN_UID && window.AUTO_OPEN_NAME) {
        setTimeout(() => {
            openChatMobile(window.AUTO_OPEN_UID, window.AUTO_OPEN_NAME);
        }, 300);
    }

    // 3. Mobile Keyboard Scroll Fix
    const chatInput = document.getElementById('chat-input');
    if (chatInput) {
        chatInput.addEventListener('focus', () => {
            setTimeout(() => {
                const msgBox = document.getElementById('chat-messages');
                if (msgBox) msgBox.scrollTop = msgBox.scrollHeight;
            }, 300);
        });
        
        chatInput.addEventListener('keypress', (e) => {
            if (e.key === 'Enter') sendMessage();
        });
    }

    // 4. Send Button Listener
    const sendBtn = document.getElementById('send-btn');
    if (sendBtn) sendBtn.addEventListener('click', sendMessage);
    
    // 5. Media Upload Listener
    const mediaUpload = document.getElementById('media-upload');
    if (mediaUpload) mediaUpload.addEventListener('change', handleMediaUpload);
});


// ==========================================
// 2. REAL-TIME PRESENCE (Dots turning green/grey)
// ==========================================
socket.on('refresh_contacts', () => {
    // Reload only if the user is just browsing the contact list (no active chat)
    if (!currentActiveChatId && !window.location.pathname.includes('dashboard')) {
        window.location.reload(); 
    }
});

socket.on('user_status', function(data) {
    const statusDot = document.getElementById(`status-${data.uid}`);
    if (statusDot) {
        if (data.status === 'online') {
            statusDot.style.background = '#198754';
            statusDot.classList.add('status-pulse'); // Adds pulse effect if on dashboard
        } else {
            statusDot.style.background = '#6c757d';
            statusDot.classList.remove('status-pulse'); // Removes pulse
        }
    }
});

// ==========================================
// 3. UI TRANSITIONS & MOBILE SWAP
// ==========================================
function openChatMobile(targetUid, targetName) {
    currentActiveChatId = targetUid;
    
    // UI Transitions
    const blankState = document.getElementById('chat-blank-state');
    const activeState = document.getElementById('chat-active-state');
    if(blankState) blankState.classList.add('d-none');
    if(activeState) {
        activeState.classList.remove('d-none');
        activeState.classList.add('d-flex');
    }
    
    const nameLabel = document.getElementById('active-chat-name');
    if(nameLabel) nameLabel.innerText = targetName;
    
    // Mobile Screen Swap
    if (window.innerWidth < 768) {
        const sidebar = document.getElementById('chat-sidebar');
        const mainChat = document.getElementById('chat-main');
        if (sidebar) { sidebar.classList.add('d-none'); sidebar.classList.remove('d-flex'); }
        if (mainChat) { mainChat.classList.remove('d-none'); mainChat.classList.add('d-flex'); }
    }

    // Socket Communication
    const msgBox = document.getElementById('chat-messages');
    if (msgBox) msgBox.innerHTML = '';
    socket.emit('join_chat', { target_uid: targetUid });
}

function closeChatMobile() {
    const sidebar = document.getElementById('chat-sidebar');
    const mainChat = document.getElementById('chat-main');
    
    if (mainChat) { mainChat.classList.add('d-none'); mainChat.classList.remove('d-flex'); }
    if (sidebar) { sidebar.classList.remove('d-none'); sidebar.classList.add('d-flex'); }
    
    currentActiveChatId = null; 
}

// ==========================================
// 4. MESSAGING LOGIC
// ==========================================
socket.on('chat_history', function(messages) {
    const msgBox = document.getElementById('chat-messages');
    if(msgBox) msgBox.innerHTML = ''; 
    messages.forEach(msg => appendMessage(msg));
    scrollToBottom();
});

socket.on('receive_message', function(msg) {
    appendMessage(msg);
    scrollToBottom();
    const typingDiv = document.getElementById('typing-indicator');
    if (typingDiv) typingDiv.remove();
});

function appendMessage(msg) {
    const msgBox = document.getElementById('chat-messages');
    if (!msgBox) return;
    
    const isSent = msg.sender_id === window.CURRENT_USER_ID;
    
    let mediaHtml = '';
    if (msg.media_url) {
        if (msg.media_type && msg.media_type.startsWith('image/')) {
            mediaHtml = `<img src="${msg.media_url}" class="chat-media mb-2 rounded shadow-sm" style="max-width: 250px; cursor: pointer;" onclick="window.open(this.src)">`;
        } else if (msg.media_type && msg.media_type.startsWith('video/')) {
            mediaHtml = `<video src="${msg.media_url}" controls class="chat-media mb-2 rounded" style="max-width: 250px;"></video>`;
        } else if (msg.media_type && msg.media_type.startsWith('audio/')) {
            mediaHtml = `<audio src="${msg.media_url}" controls class="chat-media mb-2 w-100"></audio>`;
        }
    }

    const html = `
        <div class="d-flex ${isSent ? 'justify-content-end' : 'justify-content-start'} mb-3">
            <div class="msg-bubble ${isSent ? 'msg-sent' : 'msg-received'} shadow-sm p-3 rounded-4" 
                 style="max-width: 75%; background: ${isSent ? 'var(--theme-primary)' : '#ffffff'}; color: ${isSent ? 'var(--theme-text)' : '#212529'};">
                ${mediaHtml}
                ${msg.text ? `<div class="msg-text">${msg.text}</div>` : ''}
                <span class="msg-time d-block text-end mt-1 opacity-75" style="font-size: 0.7rem;">${msg.timestamp}</span>
            </div>
        </div>
    `;
    msgBox.insertAdjacentHTML('beforeend', html);
}

function scrollToBottom() {
    const msgBox = document.getElementById('chat-messages');
    if(msgBox) msgBox.scrollTo({ top: msgBox.scrollHeight, behavior: 'smooth' });
}

function sendMessage() {
    const input = document.getElementById('chat-input');
    const text = input.value.trim();
    
    if (text !== '' && currentActiveChatId) {
        socket.emit('send_message', { receiver_id: currentActiveChatId, text: text });
        input.value = '';
        socket.emit('stop_typing', { receiver_id: currentActiveChatId });
    }
}

// ==========================================
// 5. TYPING INDICATORS
// ==========================================
const inputField = document.getElementById('chat-input');
if (inputField) {
    inputField.addEventListener('input', () => {
        if (currentActiveChatId) {
            socket.emit('typing', { receiver_id: currentActiveChatId });
            clearTimeout(typingTimeout);
            typingTimeout = setTimeout(() => {
                socket.emit('stop_typing', { receiver_id: currentActiveChatId });
            }, 2000);
        }
    });
}

socket.on('display_typing', (data) => {
    if (data.sender_id === currentActiveChatId) {
        let typingDiv = document.getElementById('typing-indicator');
        if (!typingDiv) {
            typingDiv = document.createElement('div');
            typingDiv.id = 'typing-indicator';
            typingDiv.className = 'text-muted small ps-3 mb-2 italic';
            typingDiv.innerHTML = `<span class="spinner-grow spinner-grow-sm text-success"></span> typing...`;
            document.getElementById('chat-messages').appendChild(typingDiv);
            scrollToBottom();
        }
    }
});

socket.on('hide_typing', (data) => {
    if (data.sender_id === currentActiveChatId) {
        const typingDiv = document.getElementById('typing-indicator');
        if (typingDiv) typingDiv.remove();
    }
});

// ==========================================
// 6. MEDIA UPLOAD & CLEAR CHAT
// ==========================================
function confirmClearChat() {
    if (currentActiveChatId && confirm("Delete chat history permanently?")) {
        socket.emit('clear_chat', { target_uid: currentActiveChatId });
    }
}

socket.on('chat_cleared', () => {
    const msgBox = document.getElementById('chat-messages');
    if (msgBox) msgBox.innerHTML = '<div class="text-center text-muted my-5"><em>Chat history cleared.</em></div>';
});

function handleMediaUpload(e) {
    const file = e.target.files[0];
    if (!file || !currentActiveChatId) return;

    const formData = new FormData();
    formData.append('file', file);
    const statusText = document.getElementById('upload-status');
    
    if (statusText) {
        statusText.classList.remove('d-none');
        statusText.innerText = "Encrypting & Uploading...";
    }

    fetch('/api/chat/upload', { method: 'POST', body: formData })
    .then(res => res.json())
    .then(data => {
        if (statusText) statusText.classList.add('d-none');
        socket.emit('send_message', {
            receiver_id: currentActiveChatId,
            text: '',
            media_url: data.url,
            media_type: data.type
        });
        e.target.value = '';
    })
    .catch(err => {
        if (statusText) statusText.innerText = "Upload failed.";
        e.target.value = '';
    });
}