// Skyrex AI Assistant - Clean Conversational AI Client Logic
// No Telegram-style buttons: Direct natural language dialogue with live parsed hardware catalog

document.addEventListener("DOMContentLoaded", () => {
    // 1. DOM Elements
    const isChatPage = document.body.id === "chat-page";
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

    // Subscription & Auth elements
    const subBadge = document.getElementById("sub-badge");
    const subStatusDesc = document.getElementById("sub-status-desc");
    const subActionBtn = document.getElementById("sub-action-btn");
    const subResetBtn = document.getElementById("sub-reset-btn");
    const adminPanelBtn = document.getElementById("admin-panel-btn");

    // Payment modal elements
    const paymentModal = document.getElementById("payment-modal");
    const paymentCloseBtn = document.getElementById("payment-modal-close-btn");
    const creditCard = document.getElementById("credit-card");
    const paymentForm = document.getElementById("payment-form");
    const cardNumberInput = document.getElementById("card-number");
    const cardExpiryInput = document.getElementById("card-expiry");
    const cardCvcInput = document.getElementById("card-cvc");
    const cardNameInput = document.getElementById("card-name");

    // Card displays
    const cardNumberDisplay = document.getElementById("card-number-display");
    const cardHolderDisplay = document.getElementById("card-holder-display");
    const cardExpiryDisplay = document.getElementById("card-expiry-display");
    const cardCvcDisplay = document.getElementById("card-cvc-display");
    const cardLogo = document.getElementById("card-logo");

    const paymentProcessing = document.getElementById("payment-processing");
    const paymentSuccess = document.getElementById("payment-success");
    const paymentSuccessBtn = document.getElementById("payment-success-btn");

    // 2. Helpers & Authentication Sync
    function checkSubscription() {
        return typeof SkyrexAuth !== "undefined" && SkyrexAuth.isSubscribed();
    }

    function syncChatLockState() {
        const lockOverlay = document.getElementById("chat-lock-overlay");
        if (lockOverlay) {
            lockOverlay.classList.remove("active");
            lockOverlay.style.display = "none";
        }
    }

    function updateSubscriptionUI() {
        if (typeof SkyrexAuth !== "undefined") {
            SkyrexAuth.updateUI();
        }
        syncChatLockState();
    }

    function showTyping(show = true) {
        if (show) {
            typingIndicator.classList.add("active");
            chatBody.scrollTop = chatBody.scrollHeight;
        } else {
            typingIndicator.classList.remove("active");
        }
    }

    // 3. Append message to chat (Clean conversational UI, no Telegram buttons)
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

    // Save/load chat history
    function saveChatHistory() {
        const messages = [];
        const msgEls = chatBody.querySelectorAll(".chat-message");
        msgEls.forEach(el => {
            const sender = el.classList.contains("bot") ? "bot" : "user";
            const contentEl = el.querySelector(".chat-message-content");
            let text = contentEl.innerHTML.replace(/<br>/g, "\n");
            messages.push({ sender, text });
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
        }, 600);
    }

    // 4. Core Message Handler -> Direct Neural Network Communication
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
                appendMessage("bot", "⚠️ Не удалось связаться с сервером AI-ассистента. Убедитесь, что сервер <code>server.py</code> запущен.");
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

    // 5. Payment Modal Handlers (Preserved for Billing/Premium Checkout)
    function openPaymentModal() {
        if (!paymentModal) return;
        paymentModal.classList.add("active");
        if (paymentProcessing) paymentProcessing.classList.remove("active");
        if (paymentSuccess) paymentSuccess.classList.remove("active");
        if (paymentForm) paymentForm.reset();

        if (cardNumberDisplay) cardNumberDisplay.textContent = "•••• •••• •••• ••••";
        if (cardHolderDisplay) cardHolderDisplay.textContent = "YOUR NAME";
        if (cardExpiryDisplay) cardExpiryDisplay.textContent = "MM/YY";
        if (cardCvcDisplay) cardCvcDisplay.textContent = "•••";
        if (creditCard) creditCard.classList.remove("flipped");
    }

    function closePaymentModal() {
        if (paymentModal) paymentModal.classList.remove("active");
    }

    if (subActionBtn) {
        subActionBtn.addEventListener("click", () => {
            if (typeof SkyrexAuth !== "undefined" && !SkyrexAuth.currentUser) {
                SkyrexAuth.openAuthModal();
                return;
            }
            openPaymentModal();
        });
    }

    const lockPayBtn = document.getElementById("lock-pay-btn");
    if (lockPayBtn) {
        lockPayBtn.addEventListener("click", () => {
            openPaymentModal();
        });
    }

    const lockAuthBtn = document.getElementById("lock-auth-btn");
    if (lockAuthBtn) {
        lockAuthBtn.addEventListener("click", () => {
            if (typeof SkyrexAuth !== "undefined") {
                SkyrexAuth.openAuthModal();
            }
        });
    }

    if (paymentCloseBtn) {
        paymentCloseBtn.addEventListener("click", closePaymentModal);
    }

    if (paymentModal) {
        paymentModal.addEventListener("click", (e) => {
            if (e.target === paymentModal) closePaymentModal();
        });
    }

    if (cardNumberInput) {
        cardNumberInput.addEventListener("input", (e) => {
            let value = e.target.value.replace(/\D/g, "");
            if (cardLogo) {
                if (value.startsWith("4")) cardLogo.textContent = "VISA";
                else if (value.startsWith("5")) cardLogo.textContent = "MC";
                else if (value.startsWith("2")) cardLogo.textContent = "MIR";
                else cardLogo.textContent = "CARD";
            }
            let formatted = value.match(/.{1,4}/g);
            if (formatted) {
                e.target.value = formatted.join(" ");
                if (cardNumberDisplay) cardNumberDisplay.textContent = e.target.value;
            } else {
                e.target.value = "";
                if (cardNumberDisplay) cardNumberDisplay.textContent = "•••• •••• •••• ••••";
            }
        });
    }

    if (cardExpiryInput) {
        cardExpiryInput.addEventListener("input", (e) => {
            let value = e.target.value.replace(/\D/g, "");
            if (value.length > 2) {
                e.target.value = value.substring(0, 2) + "/" + value.substring(2, 4);
                if (cardExpiryDisplay) cardExpiryDisplay.textContent = e.target.value;
            } else if (value.length > 0) {
                e.target.value = value;
                if (cardExpiryDisplay) cardExpiryDisplay.textContent = value + "/YY";
            } else {
                e.target.value = "";
                if (cardExpiryDisplay) cardExpiryDisplay.textContent = "MM/YY";
            }
        });
    }

    if (cardCvcInput) {
        cardCvcInput.addEventListener("focus", () => {
            if (creditCard) creditCard.classList.add("flipped");
        });
        cardCvcInput.addEventListener("blur", () => {
            if (creditCard) creditCard.classList.remove("flipped");
        });
        cardCvcInput.addEventListener("input", (e) => {
            let value = e.target.value.replace(/\D/g, "").substring(0, 3);
            e.target.value = value;
            if (cardCvcDisplay) cardCvcDisplay.textContent = value || "•••";
        });
    }

    if (cardNameInput) {
        cardNameInput.addEventListener("input", (e) => {
            let value = e.target.value.toUpperCase();
            if (cardHolderDisplay) cardHolderDisplay.textContent = value || "YOUR NAME";
        });
    }

    if (paymentForm) {
        paymentForm.addEventListener("submit", (e) => {
            e.preventDefault();
            if (paymentProcessing) paymentProcessing.classList.add("active");

            setTimeout(() => {
                if (paymentProcessing) paymentProcessing.classList.remove("active");
                if (paymentSuccess) paymentSuccess.classList.add("active");

                if (typeof SkyrexAuth !== "undefined") {
                    SkyrexAuth.activateSubscription(30);
                    updateSubscriptionUI();
                }
            }, 1800);
        });
    }

    if (paymentSuccessBtn) {
        paymentSuccessBtn.addEventListener("click", () => {
            closePaymentModal();
            if (!isChatPage) {
                window.location.href = "chat.html";
            }
        });
    }

    if (subResetBtn) {
        subResetBtn.addEventListener("click", () => {
            if (typeof SkyrexAuth !== "undefined") {
                SkyrexAuth.resetSubscription();
                updateSubscriptionUI();
            }
        });
    }

    // 6. Initialize UI & Chat
    loadChatHistory();
    updateSubscriptionUI();
});
