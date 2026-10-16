// Skyrex AI Assistant - Clean Conversational AI Client Logic
// Direct natural language dialogue with live parsed hardware catalog from OnlineTrade

document.addEventListener("DOMContentLoaded", () => {
    // 1. DOM Elements
    const chatBody = document.getElementById("chat-body");
    const chatInput = document.getElementById("chat-input");
    const chatSendBtn = document.getElementById("chat-send-btn");
    const chatReplyKeyboard = document.getElementById("chat-reply-keyboard");
    const chatClearBtn = document.getElementById("chat-clear-btn");
    const typingIndicator = document.getElementById("typing-indicator");

    // Hide reply keyboard completely
    if (chatReplyKeyboard) {
        chatReplyKeyboard.style.display = "none";
    }

    if (!chatBody || !chatInput || !chatSendBtn) {
        return;
    }

    // 2. Helpers
    function showTyping(show = true) {
        if (!typingIndicator) return;
        if (show) {
            typingIndicator.classList.add("active");
            chatBody.scrollTop = chatBody.scrollHeight;
        } else {
            typingIndicator.classList.remove("active");
        }
    }

    // 3. Append message to chat (Clean conversational UI)
    function appendMessage(sender, text) {
        const msgDiv = document.createElement("div");
        msgDiv.className = `chat-message ${sender}`;

        const contentDiv = document.createElement("div");
        contentDiv.className = "chat-message-content";
        contentDiv.innerHTML = text.replace(/\n/g, "<br>");

        const timeSpan = document.createElement("span");
        timeSpan.className = "chat-message-time";
        const now = new Date();
        timeSpan.textContent = now.getHours().toString().padStart(2, '0') + ":" + now.getMinutes().toString().padStart(2, '0');

        msgDiv.appendChild(contentDiv);
        msgDiv.appendChild(timeSpan);
        chatBody.appendChild(msgDiv);

        // Scroll to bottom
        chatBody.scrollTop = chatBody.scrollHeight;

        // Save history in local storage
        saveChatHistory();
    }

    // 4. Save/load chat history
    function saveChatHistory() {
        const messages = [];
        const msgEls = chatBody.querySelectorAll(".chat-message");
        msgEls.forEach(el => {
            const sender = el.classList.contains("bot") ? "bot" : "user";
            const contentEl = el.querySelector(".chat-message-content");
            if (contentEl) {
                let text = contentEl.innerHTML.replace(/<br>/g, "\n");
                messages.push({ sender, text });
            }
        });
        localStorage.setItem("skyrex_chat_history", JSON.stringify(messages));
    }

    function loadChatHistory() {
        chatBody.innerHTML = "";
        const saved = localStorage.getItem("skyrex_chat_history");
        if (saved) {
            try {
                const messages = JSON.parse(saved);
                if (messages.length > 0) {
                    messages.forEach(msg => {
                        const msgDiv = document.createElement("div");
                        msgDiv.className = `chat-message ${msg.sender}`;
                        const contentDiv = document.createElement("div");
                        contentDiv.className = "chat-message-content";
                        contentDiv.innerHTML = msg.text.replace(/\n/g, "<br>");

                        const timeSpan = document.createElement("span");
                        timeSpan.className = "chat-message-time";
                        timeSpan.textContent = "ранее";

                        msgDiv.appendChild(contentDiv);
                        msgDiv.appendChild(timeSpan);
                        chatBody.appendChild(msgDiv);
                    });
                    chatBody.scrollTop = chatBody.scrollHeight;
                    return;
                }
            } catch (e) {
                console.error("Failed to load chat history", e);
            }
        }

        // Initial greeting if history is empty
        sendGreeting();
    }

    function sendGreeting() {
        showTyping(true);
        setTimeout(() => {
            showTyping(false);
            const welcomeText =
                "👋 <b>Добро пожаловать в SkyRex AI Assistant!</b><br><br>" +
                "Я интеллектуальный ИИ-консультант по компьютерному железу, сборке ПК и подбору комплектующих.<br><br>" +
                "💡 <b>Чем я могу вам помочь:</b><br>" +
                "• 🛒 <b>Актуальные цены:</b> предоставлю реальные цены и прямые ссылки на новые комплектующие из каталога <b>ОнлайнТрейд</b><br>" +
                "• 🛠️ <b>Индивидуальная сборка:</b> соберу идеальный сбалансированный ПК под ваш точный бюджет и любые задачи (игры, 3D, стриминг, работа)<br>" +
                "• ⚖️ <b>Сравнение и аналитика:</b> подскажу, стоит ли переплачивать за конкретную видеокарту или процессор, и оценю совместимость<br>" +
                "• 💻 <b>Вторичный рынок:</b> сравню новые позиции с проверенными сборками SkyRex со вторички<br><br>" +
                "<i>Напишите ваш запрос обычным текстом (например: «Собери игровой ПК за 80 000 руб с ценами из ОнлайнТрейда» или «Сколько стоит видеокарта RTX 4060?») — и я мгновенно помогу!</i>";
            appendMessage("bot", welcomeText);
        }, 500);
    }

    // 5. Core Message Handler -> Direct Neural Network Communication
    function handleUserText(text) {
        if (!text || !text.trim()) return;
        const query = text.trim();

        // Append user message
        appendMessage("user", query);
        chatInput.value = "";

        // Show typing animation
        showTyping(true);

        // Gather history for context
        let history = [];
        const saved = localStorage.getItem("skyrex_chat_history");
        if (saved) {
            try {
                history = JSON.parse(saved);
            } catch (e) {
                console.error("Failed to parse history", e);
            }
        }

        // Call Backend AI Endpoint
        const token = (typeof SkyrexAuth !== "undefined" && SkyrexAuth.getToken) ? SkyrexAuth.getToken() : "";
        fetch("/api/chat", {
            method: "POST",
            headers: {
                "Content-Type": "application/json",
                "Authorization": token ? `Bearer ${token}` : ""
            },
            body: JSON.stringify({
                message: query,
                history: history.slice(-15) // last 15 messages for conversational context
            })
        })
            .then(async res => {
                const data = await res.json().catch(() => ({}));
                if (res.status === 401) {
                    showTyping(false);
                    appendMessage("bot", data.response || "🔒 <b>Требуется авторизация</b><br>Пожалуйста, войдите в аккаунт.");
                    if (typeof SkyrexAuth !== "undefined" && SkyrexAuth.openAuthModal) {
                        SkyrexAuth.openAuthModal();
                    }
                    return null;
                }
                if (!res.ok) {
                    throw new Error("HTTP error " + res.status);
                }
                return data;
            })
            .then(data => {
                if (!data) return;
                showTyping(false);
                if (data && data.response) {
                    appendMessage("bot", data.response);
                } else {
                    appendMessage("bot", "⚠️ К сожалению, не удалось получить ответ от ассистента.");
                }
            })
            .catch(err => {
                showTyping(false);
                console.error("Chat API Error:", err);
                appendMessage("bot", "⚠️ Не удалось связаться с сервером AI-ассистента. Убедитесь, что сервер запущен.");
            });
    }

    // Send Button and Enter Key
    chatSendBtn.addEventListener("click", () => {
        handleUserText(chatInput.value);
    });

    chatInput.addEventListener("keydown", (e) => {
        if (e.key === "Enter" && !e.shiftKey) {
            e.preventDefault();
            handleUserText(chatInput.value);
        }
    });

    // Clear Chat History Button
    if (chatClearBtn) {
        chatClearBtn.addEventListener("click", () => {
            if (confirm("Вы действительно хотите очистить историю сообщений?")) {
                localStorage.removeItem("skyrex_chat_history");
                chatBody.innerHTML = "";
                sendGreeting();
            }
        });
    }

    // 6. Initialize UI & Chat
    loadChatHistory();
});
