// Connect to WebSocket Server
const socket = io();

let currentActiveChatId = null;
let typingTimeout;

// ==========================================
// 1. DYNAMIC SIDEBAR (Presence & List Management)
// ==========================================

socket.on('refresh_contacts', () => {
    // Reload only if the user is just browsing the contact list
    if (!currentActiveChatId) {
        window.location.reload(); 
    }
});

socket.on('user_status', function(data) {
    const statusDot = document.getElementById(`status-${data.uid}`);
    if (statusDot) {
        // Updated to match Bootstrap success/secondary classes
        if (data.status === 'online') {
            statusDot.style.background = '#198754';
        } else {
            statusDot.style.background = '#6c757d';
        }
    }
});

// ==========================================
// 2. THEME INITIALIZATION
// ==========================================
function changeTheme(themeClass) {
    const wrapper = document.getElementById('chat-theme-wrapper');
    if (!wrapper) return;
    
    // Clear all possible themes
    const allThemes = [
        'theme-green', 'theme-dark-green', 'theme-blue', 'theme-dark-blue', 
        'theme-white', 'theme-cream-white', 'theme-smoke-white', 'theme-yellow'
    ];
    wrapper.classList.remove(...allThemes);
    
    wrapper.classList.add(themeClass);
    localStorage.setItem('farmerman_chat_theme', themeClass);
}

// ==========================================
// 3. CORE CHAT LOGIC (Unified Mobile/Desktop)
// ==========================================

function openChatMobile(targetUid, targetName) {
    currentActiveChatId = targetUid;
    
    // 1. UI Transitions
    const blankState = document.getElementById('chat-blank-state');
    const activeState = document.getElementById('chat-active-state');
    if(blankState) blankState.classList.add('d-none');
    if(activeState) {
        activeState.classList.remove('d-none');
        activeState.classList.add('d-flex');
    }
    
    document.getElementById('active-chat-name').innerText = targetName;
    
    // 2. Mobile Screen Swap
    if (window.innerWidth < 768) {
        document.getElementById('chat-sidebar').classList.add('d-none');
        document.getElementById('chat-sidebar').classList.remove('d-flex');
        document.getElementById('chat-main').classList.remove('d-none');
        document.getElementById('chat-main').classList.add('d-flex');
    }

    // 3. Socket Communication
    document.getElementById('chat-messages').innerHTML = '';
    socket.emit('join_chat', { target_uid: targetUid });
}

function closeChatMobile() {
    document.getElementById('chat-main').classList.add('d-none');
    document.getElementById('chat-main').classList.remove('d-flex');
    document.getElementById('chat-sidebar').classList.remove('d-none');
    document.getElementById('chat-sidebar').classList.add('d-flex');
    currentActiveChatId = null; 
}

socket.on('chat_history', function(messages) {
    const msgBox = document.getElementById('chat-messages');
    msgBox.innerHTML = ''; 
    messages.forEach(msg => appendMessage(msg));
    scrollToBottom();
});

socket.on('receive_message', function(msg) {
    appendMessage(msg);
    scrollToBottom();
    // Remove typing indicator when message arrives
    const typingDiv = document.getElementById('typing-indicator');
    if (typingDiv) typingDiv.remove();
});

function appendMessage(msg) {
    const msgBox = document.getElementById('chat-messages');
    const isSent = msg.sender_id === CURRENT_USER_ID;
    
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
    msgBox.scrollTo({ top: msgBox.scrollHeight, behavior: 'smooth' });
}

// ==========================================
// 4. TYPING INDICATOR (Backend: display_typing / hide_typing)
// ==========================================

const chatInput = document.getElementById('chat-input');
if (chatInput) {
    chatInput.addEventListener('input', () => {
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
            typingDiv.innerHTML = `<span class="spinner-grow spinner-grow-sm text-success"></span> someone is typing...`;
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
// 5. SENDING MESSAGES
// ==========================================

function sendMessage() {
    const input = document.getElementById('chat-input');
    const text = input.value.trim();
    
    if (text !== '' && currentActiveChatId) {
        socket.emit('send_message', {
            receiver_id: currentActiveChatId,
            text: text
        });
        input.value = '';
        socket.emit('stop_typing', { receiver_id: currentActiveChatId });
    }
}

const sendBtn = document.getElementById('send-btn');
if (sendBtn) sendBtn.addEventListener('click', sendMessage);

if (chatInput) {
    chatInput.addEventListener('keypress', (e) => {
        if (e.key === 'Enter') sendMessage();
    });
}

// ==========================================
// 6. CLEAR CHAT & MEDIA UPLOAD
// ==========================================

function confirmClearChat() {
    if (currentActiveChatId && confirm("Delete chat history permanently?")) {
        socket.emit('clear_chat', { target_uid: currentActiveChatId });
    }
}

socket.on('chat_cleared', () => {
    document.getElementById('chat-messages').innerHTML = 
        '<div class="text-center text-muted my-5"><em>Chat history cleared.</em></div>';
});

const mediaUpload = document.getElementById('media-upload');
if (mediaUpload) {
    mediaUpload.addEventListener('change', function(e) {
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
    });
}