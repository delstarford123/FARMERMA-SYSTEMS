// Connect to WebSocket Server
const socket = io();

let currentActiveChatId = null;
let typingTimeout;

// ==========================================
// 1. DYNAMIC SIDEBAR (Presence & List Management)
// ==========================================

// Handle sidebar updates for new logins/logouts
socket.on('refresh_contacts', () => {
    /* Since the Python backend filters the sidebar at the template level,
       we must reload to see a NEW user join the list.
       We only reload if the user isn't currently in a chat window.
    */
    if (!currentActiveChatId) {
        window.location.reload(); 
    } else {
        console.log("Contact list update pending (waiting for chat close).");
    }
});

// Update status dots for users already visible in the sidebar
socket.on('user_status', function(data) {
    const statusDot = document.getElementById(`status-${data.uid}`);
    if (statusDot) {
        if (data.status === 'online') {
            statusDot.classList.replace('offline', 'online');
        } else {
            statusDot.classList.replace('online', 'offline');
        }
    }
});

// ==========================================
// 2. THEME & UI INITIALIZATION
// ==========================================
function changeTheme(themeClass) {
    const wrapper = document.getElementById('chat-theme-wrapper');
    if (!wrapper) return;
    wrapper.classList.remove('theme-green', 'theme-blue', 'theme-yellow');
    wrapper.classList.add(themeClass);
    localStorage.setItem('farmerman_chat_theme', themeClass);
}

window.addEventListener('DOMContentLoaded', () => {
    const saved = localStorage.getItem('farmerman_chat_theme');
    if (saved) changeTheme(saved);
});

// ==========================================
// 3. CORE CHAT LOGIC (Rooms & Messaging)
// ==========================================

function openChat(targetUid, targetName) {
    currentActiveChatId = targetUid;
    
    // UI Transitions
    document.getElementById('chat-blank-state').classList.add('d-none');
    const activeState = document.getElementById('chat-active-state');
    activeState.classList.remove('d-none');
    activeState.classList.add('d-flex');
    document.getElementById('active-chat-name').innerText = targetName;
    
    // --> MOBILE SCREEN SWAP LOGIC <--
    // If screen is smaller than 768px (Mobile), hide sidebar, show chat
    if (window.innerWidth < 768) {
        document.getElementById('chat-sidebar').classList.add('d-none');
        document.getElementById('chat-sidebar').classList.remove('d-flex');
        
        document.getElementById('chat-main').classList.remove('d-none');
        document.getElementById('chat-main').classList.add('d-flex');
    }

    // Clear view and request history from server
    document.getElementById('chat-messages').innerHTML = '';
    socket.emit('join_chat', { target_uid: targetUid });
}

// --> NEW: MOBILE BACK BUTTON LOGIC <--
function closeChatMobile() {
    // Hide the chat window, show the sidebar again
    document.getElementById('chat-main').classList.add('d-none');
    document.getElementById('chat-main').classList.remove('d-flex');
    
    document.getElementById('chat-sidebar').classList.remove('d-none');
    document.getElementById('chat-sidebar').classList.add('d-flex');
    
    // Clear the active chat so background events don't trigger weirdly
    currentActiveChatId = null; 
}

// Render history when entering a room
socket.on('chat_history', function(messages) {
    const msgBox = document.getElementById('chat-messages');
    msgBox.innerHTML = ''; 
    messages.forEach(msg => appendMessage(msg));
    scrollToBottom();
});

// Receive real-time message
socket.on('receive_message', function(msg) {
    appendMessage(msg);
    scrollToBottom();
});

function appendMessage(msg) {
    const msgBox = document.getElementById('chat-messages');
    const isSent = msg.sender_id === CURRENT_USER_ID;
    
    let mediaHtml = '';
    if (msg.media_url) {
        if (msg.media_type.startsWith('image/')) {
            mediaHtml = `<img src="${msg.media_url}" class="chat-media mb-2 rounded shadow-sm" style="max-width: 100%; cursor: pointer;" onclick="window.open(this.src)">`;
        } else if (msg.media_type.startsWith('video/')) {
            mediaHtml = `<video src="${msg.media_url}" controls class="chat-media mb-2 rounded" style="max-width: 100%;"></video>`;
        } else if (msg.media_type.startsWith('audio/')) {
            mediaHtml = `<audio src="${msg.media_url}" controls class="chat-media mb-2 w-100"></audio>`;
        }
    }

    const html = `
        <div class="d-flex ${isSent ? 'justify-content-end' : 'justify-content-start'} mb-3">
            <div class="msg-bubble ${isSent ? 'msg-sent' : 'msg-received'} shadow-sm">
                ${mediaHtml}
                ${msg.text ? `<div class="msg-text">${msg.text}</div>` : ''}
                <span class="msg-time d-block text-end mt-1">${msg.timestamp}</span>
            </div>
        </div>
    `;
    msgBox.insertAdjacentHTML('beforeend', html);
}

function scrollToBottom() {
    const msgBox = document.getElementById('chat-messages');
    msgBox.scrollTop = msgBox.scrollHeight;
}

// ==========================================
// 4. TYPING INDICATOR LOGIC
// ==========================================

const chatInput = document.getElementById('chat-input');

chatInput.addEventListener('input', () => {
    if (currentActiveChatId) {
        socket.emit('typing', { receiver_id: currentActiveChatId });

        clearTimeout(typingTimeout);
        typingTimeout = setTimeout(() => {
            socket.emit('stop_typing', { receiver_id: currentActiveChatId });
        }, 2000);
    }
});

socket.on('display_typing', (data) => {
    // Only show typing indicator if it's the person we are currently viewing
    if (data.sender_id === currentActiveChatId) {
        let typingDiv = document.getElementById('typing-indicator');
        if (!typingDiv) {
            typingDiv = document.createElement('div');
            typingDiv.id = 'typing-indicator';
            typingDiv.className = 'text-muted small ps-3 mb-2 italic';
            typingDiv.innerHTML = `<span class="spinner-grow spinner-grow-sm"></span> typing...`;
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

document.getElementById('send-btn').addEventListener('click', sendMessage);
chatInput.addEventListener('keypress', (e) => {
    if (e.key === 'Enter') sendMessage();
});

// ==========================================
// 6. CLEAR CHAT & MEDIA UPLOAD
// ==========================================

function confirmClearChat() {
    if (currentActiveChatId && confirm("Delete all messages in this chat? This cannot be undone.")) {
        socket.emit('clear_chat', { target_uid: currentActiveChatId });
    }
}

socket.on('chat_cleared', () => {
    document.getElementById('chat-messages').innerHTML = 
        '<div class="text-center text-muted my-5"><em>Chat history has been cleared.</em></div>';
});

document.getElementById('media-upload').addEventListener('change', function(e) {
    const file = e.target.files[0];
    if (!file || !currentActiveChatId) return;

    const formData = new FormData();
    formData.append('file', file);
    const statusText = document.getElementById('upload-status');
    
    statusText.classList.remove('d-none');
    statusText.innerText = "Uploading media...";

    fetch('/api/chat/upload', { method: 'POST', body: formData })
    .then(res => {
        if (!res.ok) throw new Error("Upload failed");
        return res.json();
    })
    .then(data => {
        statusText.classList.add('d-none');
        socket.emit('send_message', {
            receiver_id: currentActiveChatId,
            text: '',
            media_url: data.url,
            media_type: data.type
        });
    })
    .catch(err => {
        console.error("Upload error:", err);
        statusText.innerText = "Upload failed. Try again.";
        setTimeout(() => statusText.classList.add('d-none'), 3000);
    });
});