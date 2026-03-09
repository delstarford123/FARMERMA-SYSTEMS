// Connect to WebSocket Server
const socket = io();

let currentActiveChatId = null;

// 1. Theme Switcher
function changeTheme(themeClass) {
    const wrapper = document.getElementById('chat-theme-wrapper');
    wrapper.classList.remove('theme-green', 'theme-blue', 'theme-yellow');
    wrapper.classList.add(themeClass);
    localStorage.setItem('farmerman_chat_theme', themeClass);
}

// Load saved theme on load
window.onload = () => {
    const saved = localStorage.getItem('farmerman_chat_theme');
    if (saved) changeTheme(saved);
};

// 2. Socket: Online Status Updates
socket.on('user_status', function(data) {
    const dot = document.getElementById(`status-${data.uid}`);
    if (dot) {
        if (data.status === 'online') {
            dot.classList.remove('offline');
            dot.classList.add('online');
        } else {
            dot.classList.remove('online');
            dot.classList.add('offline');
        }
    }
});

// 3. Open a Chat
function openChat(targetUid, targetName) {
    currentActiveChatId = targetUid;
    
    // UI Toggle
    document.getElementById('chat-blank-state').classList.add('d-none');
    document.getElementById('chat-active-state').classList.remove('d-none');
    document.getElementById('chat-active-state').classList.add('d-flex');
    document.getElementById('active-chat-name').innerText = targetName;
    
    // Clear current window and tell server to join room
    document.getElementById('chat-messages').innerHTML = '';
    socket.emit('join_chat', { target_uid: targetUid });
}

// 4. Render Message History
socket.on('chat_history', function(messages) {
    const msgBox = document.getElementById('chat-messages');
    messages.forEach(msg => appendMessage(msg));
    msgBox.scrollTop = msgBox.scrollHeight;
});

// 5. Receive Real-Time Message
socket.on('receive_message', function(msg) {
    appendMessage(msg);
    const msgBox = document.getElementById('chat-messages');
    msgBox.scrollTop = msgBox.scrollHeight;
});

function appendMessage(msg) {
    const msgBox = document.getElementById('chat-messages');
    const isSent = msg.sender_id === CURRENT_USER_ID;
    
    let mediaHtml = '';
    if (msg.media_url) {
        if (msg.media_type.startsWith('image/')) {
            mediaHtml = `<img src="${msg.media_url}" class="chat-media mb-2">`;
        } else if (msg.media_type.startsWith('video/')) {
            mediaHtml = `<video src="${msg.media_url}" controls class="chat-media mb-2"></video>`;
        } else if (msg.media_type.startsWith('audio/')) {
            mediaHtml = `<audio src="${msg.media_url}" controls class="chat-media mb-2 w-100"></audio>`;
        }
    }

    const html = `
        <div class="msg-bubble ${isSent ? 'msg-sent' : 'msg-received'}">
            ${mediaHtml}
            ${msg.text ? `<div>${msg.text}</div>` : ''}
            <span class="msg-time">${msg.timestamp}</span>
        </div>
    `;
    msgBox.innerHTML += html;
}

// 6. Send Text Message
document.getElementById('send-btn').addEventListener('click', sendMessage);
document.getElementById('chat-input').addEventListener('keypress', function(e) {
    if (e.key === 'Enter') sendMessage();
});

function sendMessage() {
    const input = document.getElementById('chat-input');
    const text = input.value.trim();
    
    if (text !== '' && currentActiveChatId) {
        socket.emit('send_message', {
            receiver_id: currentActiveChatId,
            text: text
        });
        input.value = '';
    }
}

// 7. Media Upload Handling (AJAX to Flask)
document.getElementById('media-upload').addEventListener('change', function(e) {
    const file = e.target.files[0];
    if (!file || !currentActiveChatId) return;

    const formData = new FormData();
    formData.append('file', file);

    const statusText = document.getElementById('upload-status');
    statusText.classList.remove('d-none');

    fetch('/api/chat/upload', {
        method: 'POST',
        body: formData
    })
    .then(response => response.json())
    .then(data => {
        statusText.classList.add('d-none');
        // Send the uploaded URL to the socket
        socket.emit('send_message', {
            receiver_id: currentActiveChatId,
            text: '',
            media_url: data.url,
            media_type: data.type
        });
    })
    .catch(err => {
        statusText.innerText = "Upload failed!";
        setTimeout(() => statusText.classList.add('d-none'), 3000);
    });
});