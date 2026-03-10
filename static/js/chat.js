const socket = io();
let currentActiveChatId = null;
let typingTimeout;

// --- 1. KEYBOARD FIX & 20 THEMES ---
const allThemes = [
    'theme-green', 'theme-dark-green', 'theme-light-green', 
    'theme-blue', 'theme-dark-blue', 'theme-cyan', 'theme-teal', 'theme-midnight',
    'theme-orange', 'theme-crimson', 'theme-yellow', 'theme-brown',
    'theme-purple', 'theme-dark-purple', 'theme-pink', 'theme-magenta', 'theme-rose',
    'theme-white', 'theme-cream-white', 'theme-slate'
];

function changeTheme(themeClass) {
    const wrapper = document.getElementById('chat-theme-wrapper');
    if (!wrapper) return;
    wrapper.classList.remove(...allThemes);
    wrapper.classList.add(themeClass);
    localStorage.setItem('farmerman_chat_theme', themeClass);
}

document.addEventListener('DOMContentLoaded', () => {
    changeTheme(localStorage.getItem('farmerman_chat_theme') || 'theme-green');

    // Visual Viewport API: Keeps input exactly above the Android/iOS keyboard
    if (window.visualViewport) {
        window.visualViewport.addEventListener('resize', () => {
            document.body.style.height = window.visualViewport.height + 'px';
            scrollToBottom();
        });
    }

    if (window.AUTO_OPEN_UID && window.AUTO_OPEN_NAME) {
        setTimeout(() => openChatMobile(window.AUTO_OPEN_UID, window.AUTO_OPEN_NAME), 300);
    }

    const chatInput = document.getElementById('chat-input');
    if (chatInput) {
        chatInput.addEventListener('focus', () => setTimeout(() => scrollToBottom(), 300));
        chatInput.addEventListener('keypress', (e) => { if (e.key === 'Enter') sendMessage(); });
        
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

    const sendBtn = document.getElementById('send-btn');
    if (sendBtn) sendBtn.addEventListener('click', sendMessage);
    
    const mediaUpload = document.getElementById('media-upload');
    if (mediaUpload) mediaUpload.addEventListener('change', handleMediaUpload);
});

// --- 2. SOCKET EVENTS ---
socket.on('refresh_contacts', () => {
    if (!currentActiveChatId && !window.location.pathname.includes('dashboard')) {
        window.location.reload(); 
    }
});

socket.on('user_status', function(data) {
    const statusDot = document.getElementById(`status-${data.uid}`);
    if (statusDot) {
        statusDot.style.background = data.status === 'online' ? '#198754' : '#6c757d';
    }
});

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

// NEW: Listener for Real-Time Unread Badges
socket.on('update_unread_badge', function(data) {
    // If we are ALREADY looking at this exact chat, ignore the badge update
    // (Because we are reading it right now)
    if (currentActiveChatId === data.sender_id) return;
    
    const badge = document.getElementById(`unread-badge-${data.sender_id}`);
    if (badge) {
        // Update the number inside the red bubble
        badge.innerText = data.count;
        // Make the bubble visible
        badge.classList.remove('d-none');
        
        // Add a quick visual "pop" animation using CSS classes
        badge.classList.add('badge-pop');
        setTimeout(() => badge.classList.remove('badge-pop'), 300);
    }
});

socket.on('chat_cleared', (data) => {
    const msgBox = document.getElementById('chat-messages');
    if (msgBox) {
        let msg = data.mode === 'all' 
            ? "Chat history was permanently cleared for everyone." 
            : "You cleared this chat history from your device.";
        msgBox.innerHTML = `<div class="text-center text-muted my-5"><em>${msg}</em></div>`;
    }
});

socket.on('display_typing', (data) => {
    if (data.sender_id === currentActiveChatId) {
        let typingDiv = document.getElementById('typing-indicator');
        if (!typingDiv) {
            typingDiv = document.createElement('div');
            typingDiv.id = 'typing-indicator';
            typingDiv.className = 'text-muted small ps-3 mb-2 italic';
            typingDiv.innerHTML = `<span class="spinner-grow spinner-grow-sm text-success"></span> typing...`;
            const msgBox = document.getElementById('chat-messages');
            if(msgBox) { msgBox.appendChild(typingDiv); scrollToBottom(); }
        }
    }
});

socket.on('hide_typing', (data) => {
    if (data.sender_id === currentActiveChatId) {
        const typingDiv = document.getElementById('typing-indicator');
        if (typingDiv) typingDiv.remove();
    }
});

// --- 3. CORE FUNCTIONS ---
function openChatMobile(targetUid, targetName) {
    currentActiveChatId = targetUid;
    
    // NEW: Instantly hide the red unread badge when you click their name
    const badge = document.getElementById(`unread-badge-${targetUid}`);
    if (badge) {
        badge.innerText = '0';
        badge.classList.add('d-none');
    }
    
    document.getElementById('chat-blank-state').classList.add('d-none');
    
    // IMPORTANT: Adds d-flex to activate the column layout
    const activeState = document.getElementById('chat-active-state');
    activeState.classList.remove('d-none');
    activeState.classList.add('d-flex'); 
    
    document.getElementById('active-chat-name').innerText = targetName;
    
    if (window.innerWidth < 768) {
        document.getElementById('chat-sidebar').classList.add('d-none');
        document.getElementById('chat-sidebar').classList.remove('d-flex');
        document.getElementById('chat-main').classList.remove('d-none');
        document.getElementById('chat-main').classList.add('d-flex');
    }

    document.getElementById('chat-messages').innerHTML = '';
    
    // This tells the backend you entered the room (and the backend will reset the DB count to 0)
    socket.emit('join_chat', { target_uid: targetUid });
}

function closeChatMobile() {
    document.getElementById('chat-main').classList.add('d-none');
    document.getElementById('chat-main').classList.remove('d-flex');
    document.getElementById('chat-sidebar').classList.remove('d-none');
    document.getElementById('chat-sidebar').classList.add('d-flex');
    currentActiveChatId = null; 
}

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
    if(msgBox) {
        // Enforce the scroll top
        msgBox.scrollTop = msgBox.scrollHeight;
    }
}

function sendMessage() {
    const input = document.getElementById('chat-input');
    if(!input) return;
    const text = input.value.trim();
    
    if (text !== '' && currentActiveChatId) {
        socket.emit('send_message', { receiver_id: currentActiveChatId, text: text });
        input.value = '';
        socket.emit('stop_typing', { receiver_id: currentActiveChatId });
    }
}

function confirmClearChat(mode) {
    if (!currentActiveChatId) return;
    
    const confirmMessage = mode === 'all' 
        ? "Warning: This will delete the chat history for EVERYONE. Continue?" 
        : "Delete this chat history for yourself? (The other person will still see it)";
        
    if (confirm(confirmMessage)) {
        socket.emit('clear_chat', { target_uid: currentActiveChatId, mode: mode });
    }
}

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