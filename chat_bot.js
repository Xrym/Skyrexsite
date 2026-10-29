// Skyrex AI Assistant - Modern Conversational AI Client Logic
// Direct natural language dialogue, live streaming, markdown formatting, suggestion chips, and catalog tools

document.addEventListener("DOMContentLoaded", () => {
    // 1. DOM Elements
    const chatBody = document.getElementById("chat-body");
    const chatInput = document.getElementById("chat-input");
    const chatSendBtn = document.getElementById("chat-send-btn");
    const chatReplyKeyboard = document.getElementById("chat-reply-keyboard");
    const chatClearBtn = document.getElementById("chat-clear-btn");
    const typingIndicator = document.getElementById("typing-indicator");
    const scrollBottomBtn = document.getElementById("chat-scroll-bottom-btn");
    const unreadDot = document.getElementById("chat-unread-dot");

    if (!chatBody || !chatInput || !chatSendBtn) {
        return;
    }

    // 2. Chat State
    const state = {
        messages: [], // [{ id, sender, text, timestamp }]
        isGenerating: false,
        abortController: null,
        lastUserQuery: ""
    };

    // Quick suggestion chips
    const SUGGESTIONS = [
        { label: "🎮 Сборка за 80 000 ₽", prompt: "Собери сбалансированный игровой ПК за 80 000 рублей с актуальными ценами" },
        { label: "🚀 Топ ПК за 150 000 ₽", prompt: "Собери мощный ПК за 150 000 рублей для 2K-гейминга и работы" },
        { label: "🔍 Цены на RTX 4060", prompt: "Сколько сейчас стоит видеокарта GeForce RTX 4060 и какие варианты в наличии?" },
        { label: "⚡ Ryzen 5 7500F vs Core i5", prompt: "Что лучше выбрать для игр: AMD Ryzen 5 7500F или Intel Core i5 13400?" },
        { label: "🛠️ Апгрейд моего ПК", prompt: "Помоги спланировать апгрейд старого ПК. На что обратить внимание в первую очередь?" },
        { label: "💻 Б/У сборки SkyRex", prompt: "Покажи проверенные сборки ПК и комплектующие со вторичного рынка из каталога SkyRex" }
    ];

    // Icons for send/stop button
    const SEND_ICON_HTML = `
        <svg xmlns="http://www.w3.org/2000/svg" width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round">
            <line x1="22" y1="2" x2="11" y2="13"></line>
            <polygon points="22 2 15 22 11 13 2 9 22 2"></polygon>
        </svg>
    `;
    const STOP_ICON_HTML = `
        <svg xmlns="http://www.w3.org/2000/svg" width="18" height="18" viewBox="0 0 24 24" fill="currentColor">
            <rect x="5" y="5" width="14" height="14" rx="2" ry="2"></rect>
        </svg>
    `;

    // 3. Security & Formatting Helpers
    function escapeHtml(str) {
        if (!str) return "";
        return str
            .replace(/&/g, "&amp;")
            .replace(/</g, "&lt;")
            .replace(/>/g, "&gt;")
            .replace(/"/g, "&quot;")
            .replace(/'/g, "&#039;");
    }

    function formatTime(date = new Date()) {
        const d = (date instanceof Date) ? date : new Date(date);
        if (isNaN(d.getTime())) return "ранее";
        return d.getHours().toString().padStart(2, '0') + ":" + d.getMinutes().toString().padStart(2, '0');
    }

    function sanitizeAvitoUrl(url, linkTitle = "") {
        if (!url || !url.includes("avito.ru")) return url;
        let query = "";
        try {
            const matchQ = url.match(/[?&]q=([^&#]+)/);
            if (matchQ && matchQ[1]) {
                const rawParam = matchQ[1].replace(/\+/g, " ");
                try {
                    query = decodeURIComponent(rawParam);
                } catch (e) {
                    const sanitized = rawParam.replace(/%(?![0-9a-fA-F]{2})/g, "");
                    try {
                        query = decodeURIComponent(sanitized);
                    } catch (e2) {
                        query = "";
                    }
                }
            }
        } catch (e) {
            query = "";
        }

        const isCorrupt = !query || query.includes("%") || query.length < 2 || /(?:такогонить|па0)/i.test(query);
        if (isCorrupt && linkTitle) {
            query = linkTitle
                .replace(/<[^>]+>/g, "")
                .replace(/\(Б\/У\)/gi, "")
                .replace(/\(б\/у\)/gi, "")
                .replace(/Б\/У/gi, "")
                .trim();
        }

        if (!query) {
            query = "компьютерные комплектующие";
        }

        query = query.replace(/\s+/g, " ").trim();
        return `https://www.avito.ru/all?q=${encodeURIComponent(query)}`;
    }

    /**
     * Resilient hybrid Markdown and HTML parser for bot responses.
     * Safely handles markdown tables, bold, italics, headers, code blocks, lists, and links.
     */
    function parseBotContent(rawText) {
        if (!rawText) return "";
        let text = rawText;

        // 1. Preserve code blocks
        const codeBlocks = [];
        text = text.replace(/```([a-zA-Z0-9_-]*)\n([\s\S]*?)```/g, (match, lang, code) => {
            const token = `__CODE_BLOCK_${codeBlocks.length}__`;
            codeBlocks.push(`<pre><code class="language-${lang || 'text'}">${escapeHtml(code.trim())}</code></pre>`);
            return token;
        });

        // 2. Preserve inline code
        const inlineCodes = [];
        text = text.replace(/`([^`\n]+)`/g, (match, code) => {
            const token = `__INLINE_CODE_${inlineCodes.length}__`;
            inlineCodes.push(`<code>${escapeHtml(code)}</code>`);
            return token;
        });

        // 3. Markdown tables
        text = text.replace(/((?:^|\n)\|[^\n]+\|\r?\n\|[-: |]+\|\r?\n(?:\|[^\n]+\|\r?\n?)+)/g, (match) => {
            const lines = match.trim().split("\n").map(l => l.trim()).filter(Boolean);
            if (lines.length < 3) return match;

            const parseRow = (line) => line.split("|").slice(1, -1).map(c => c.trim());
            const headers = parseRow(lines[0]);
            const rows = lines.slice(2).map(parseRow);

            let tableHtml = "<table><thead><tr>";
            headers.forEach(h => {
                tableHtml += `<th>${h}</th>`;
            });
            tableHtml += "</tr></thead><tbody>";
            rows.forEach(r => {
                tableHtml += "<tr>";
                r.forEach(cell => {
                    tableHtml += `<td>${cell}</td>`;
                });
                tableHtml += "</tr>";
            });
            tableHtml += "</tbody></table>";
            return `\n${tableHtml}\n`;
        });

        // 4. Headers: ### Title -> <h3>Title</h3>
        text = text.replace(/^###\s+(.+)$/gm, "<h3>$1</h3>");
        text = text.replace(/^##\s+(.+)$/gm, "<h2>$1</h2>");
        text = text.replace(/^#\s+(.+)$/gm, "<h2>$1</h2>");

        // 5. Bold & Italic markdown
        text = text.replace(/\*\*([^*]+)\*\*/g, "<b>$1</b>");
        text = text.replace(/__([^_]+)__/g, "<b>$1</b>");
        text = text.replace(/(^|[^\*])\*([^\*\n]+)\*([^\*]|$)/g, "$1<i>$2</i>$3");

        // 6. Markdown links: [Title](URL) -> <a href='URL' target='_blank'>Title</a>
        text = text.replace(/\[([^\]]+)\]\((https?:\/\/[^\s\)]+)\)/g, (match, title, url) => {
            const cleanUrl = url.includes("avito.ru") ? sanitizeAvitoUrl(url, title) : url;
            return `<a href="${cleanUrl}" target="_blank" rel="noopener noreferrer">${title}</a>`;
        });

        // 6.1. Sanitize any existing HTML <a> tags pointing to Avito
        text = text.replace(/<a\s+([^>]*?)href=(['"])(https?:\/\/[^'"]*avito\.ru[^'"]*)\2([^>]*)>(.*?)<\/a>/gi, (match, before, quote, url, after, innerText) => {
            const cleanUrl = sanitizeAvitoUrl(url, innerText);
            const targetAttr = (before + after).includes("target=") ? "" : ' target="_blank" rel="noopener noreferrer"';
            return `<a ${before}href="${cleanUrl}"${after}${targetAttr}>${innerText}</a>`;
        });

        // 7. Auto-link bare URLs not inside tags
        text = text.replace(/(^|[^"'])(https?:\/\/[^\s<]+)/g, (match, prefix, url) => {
            if (prefix.includes("href=") || prefix.includes("src=")) return match;
            const cleanUrl = url.includes("avito.ru") ? sanitizeAvitoUrl(url) : url;
            return `${prefix}<a href="${cleanUrl}" target="_blank" rel="noopener noreferrer">${url}</a>`;
        });

        // 8. Unordered lists: lines starting with * or - or •
        text = text.replace(/(?:^|\n)[ \t]*[*\-•][ \t]+([^\n]+)/g, "\n<li>$1</li>");
        text = text.replace(/(?:<li>[\s\S]*?<\/li>)/g, (match) => {
            return `<ul>${match}</ul>`;
        });
        // Fix duplicate <ul><ul> wrappers
        text = text.replace(/<\/ul>\s*<ul>/g, "");

        // 9. Blockquotes: > quote
        text = text.replace(/^>\s+(.+)$/gm, "<blockquote>$1</blockquote>");

        // 10. Clean newlines: convert newlines to <br> unless adjacent to block tags
        text = text.replace(/([^\n>])\n([^\n<])/g, "$1<br>$2");

        // Restore inline code & code blocks
        inlineCodes.forEach((codeHtml, idx) => {
            text = text.replace(`__INLINE_CODE_${idx}__`, codeHtml);
        });
        codeBlocks.forEach((blockHtml, idx) => {
            text = text.replace(`__CODE_BLOCK_${idx}__`, blockHtml);
        });

        return text;
    }

    function showTyping(show = true) {
        if (!typingIndicator) return;
        if (show) {
            typingIndicator.classList.add("active");
            scrollChatToBottom();
        } else {
            typingIndicator.classList.remove("active");
        }
    }

    function scrollChatToBottom(smooth = false) {
        if (!chatBody) return;
        if (smooth) {
            chatBody.scrollTo({ top: chatBody.scrollHeight, behavior: 'smooth' });
        } else {
            chatBody.scrollTop = chatBody.scrollHeight;
        }
    }

    function isAtBottom() {
        if (!chatBody) return true;
        const threshold = 80;
        return (chatBody.scrollHeight - chatBody.scrollTop - chatBody.clientHeight) < threshold;
    }

    // 4. Render Message in DOM
    function renderMessage(msgObj, isNew = false) {
        const msgDiv = document.createElement("div");
        msgDiv.className = `chat-message ${msgObj.sender}`;
        msgDiv.dataset.id = msgObj.id;

        const contentDiv = document.createElement("div");
        contentDiv.className = "chat-message-content";

        if (msgObj.sender === "user") {
            contentDiv.innerHTML = escapeHtml(msgObj.text).replace(/\n/g, "<br>");
        } else {
            contentDiv.innerHTML = parseBotContent(msgObj.text);
        }

        const footerDiv = document.createElement("div");
        footerDiv.className = "chat-message-footer";

        // Action buttons for bot messages (e.g. Copy)
        if (msgObj.sender === "bot") {
            const actionsDiv = document.createElement("div");
            actionsDiv.className = "chat-msg-actions";

            const copyBtn = document.createElement("button");
            copyBtn.className = "msg-action-btn";
            copyBtn.title = "Копировать ответ";
            copyBtn.innerHTML = `
                <svg xmlns="http://www.w3.org/2000/svg" width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                    <rect x="9" y="9" width="13" height="13" rx="2" ry="2"></rect>
                    <path d="M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1"></path>
                </svg>
                <span>Копировать</span>
            `;
            copyBtn.addEventListener("click", () => {
                // Strip HTML tags for clean clipboard text
                const plainText = contentDiv.innerText || contentDiv.textContent || msgObj.text;
                navigator.clipboard.writeText(plainText.trim()).then(() => {
                    copyBtn.classList.add("copied");
                    copyBtn.querySelector("span").textContent = "Скопировано!";
                    setTimeout(() => {
                        copyBtn.classList.remove("copied");
                        copyBtn.querySelector("span").textContent = "Копировать";
                    }, 2000);
                }).catch(err => {
                    console.warn("Clipboard copy failed:", err);
                });
            });

            actionsDiv.appendChild(copyBtn);
            footerDiv.appendChild(actionsDiv);
        } else {
            // Spacer for user alignment
            footerDiv.appendChild(document.createElement("div"));
        }

        const timeSpan = document.createElement("span");
        timeSpan.className = "chat-message-time";
        timeSpan.textContent = formatTime(msgObj.timestamp);
        footerDiv.appendChild(timeSpan);

        msgDiv.appendChild(contentDiv);
        msgDiv.appendChild(footerDiv);
        chatBody.appendChild(msgDiv);

        if (isNew) {
            scrollChatToBottom(true);
        }
        return { msgDiv, contentDiv };
    }

    // 5. Append message to chat and state
    function appendMessage(sender, text, timestamp = new Date()) {
        const msgObj = {
            id: "msg_" + Date.now() + "_" + Math.random().toString(36).substr(2, 6),
            sender,
            text,
            timestamp: (timestamp instanceof Date) ? timestamp.toISOString() : timestamp
        };
        state.messages.push(msgObj);
        saveChatHistory();
        return renderMessage(msgObj, true);
    }

    // 6. History Storage in LocalStorage
    function saveChatHistory() {
        try {
            // Keep last 40 messages to avoid exceeding localStorage quota
            const slice = state.messages.slice(-40);
            localStorage.setItem("skyrex_chat_history", JSON.stringify(slice));
        } catch (e) {
            console.error("Failed to save chat history", e);
        }
    }

    function loadChatHistory() {
        chatBody.innerHTML = "";
        const saved = localStorage.getItem("skyrex_chat_history");
        if (saved) {
            try {
                const parsed = JSON.parse(saved);
                if (Array.isArray(parsed) && parsed.length > 0) {
                    state.messages = parsed;
                    state.messages.forEach(msg => {
                        renderMessage(msg, false);
                    });
                    scrollChatToBottom();
                    renderSuggestionChips();
                    return;
                }
            } catch (e) {
                console.error("Failed to load chat history", e);
            }
        }

        // Initial greeting if history is empty
        state.messages = [];
        sendGreeting();
    }

    // 7. Initial Greeting
    function sendGreeting() {
        showTyping(true);
        setTimeout(() => {
            showTyping(false);
            const welcomeText =
                "👋 <b>Добро пожаловать в SkyRex AI Assistant!</b>\n\n" +
                "Я интеллектуальный ИИ-консультант по компьютерному железу, сборке ПК и подбору комплектующих.\n\n" +
                "💡 <b>Чем я могу вам помочь:</b>\n" +
                "• 🛒 <b>Актуальные цены:</b> предоставлю реальные цены и прямые ссылки на новые комплектующие из ОнлайнТрейд\n" +
                "• 🛠️ <b>Индивидуальная сборка:</b> соберу идеальный сбалансированный ПК под ваш бюджет и задачи (игры, 3D, стриминг, работа)\n" +
                "• ⚖️ <b>Сравнение и аналитика:</b> оценю совместимость сокетов (AM4/AM5/LGA 1700), тип памяти и мощность блока питания\n" +
                "• 💻 <b>Вторичный рынок:</b> подберу надежные позиции со вторички из каталога SkyRex\n\n" +
                "<i>Выберите готовый запрос ниже или напишите свой своими словами!</i>";

            appendMessage("bot", welcomeText);
            renderSuggestionChips();
        }, 400);
    }

    // 8. Suggestion Chips (Reply Keyboard)
    function renderSuggestionChips() {
        if (!chatReplyKeyboard) return;
        chatReplyKeyboard.innerHTML = "";
        chatReplyKeyboard.style.display = "flex";

        SUGGESTIONS.forEach(item => {
            const chip = document.createElement("button");
            chip.type = "button";
            chip.className = "chat-chip";
            chip.textContent = item.label;
            chip.title = item.prompt;
            chip.addEventListener("click", () => {
                if (state.isGenerating) return;
                handleUserText(item.prompt);
            });
            chatReplyKeyboard.appendChild(chip);
        });
    }

    // 9. Input & Auto-resize textarea
    function autoResizeInput() {
        if (!chatInput) return;
        chatInput.style.height = "auto";
        const newHeight = Math.min(chatInput.scrollHeight, 130);
        chatInput.style.height = (newHeight > 44 ? newHeight : 44) + "px";
    }

    chatInput.addEventListener("input", autoResizeInput);

    chatInput.addEventListener("keydown", (e) => {
        if (e.key === "Enter" && !e.shiftKey) {
            e.preventDefault();
            if (!state.isGenerating) {
                handleUserText(chatInput.value);
            }
        }
    });

    // 10. Send / Stop Button State Management
    function setGeneratingState(generating) {
        state.isGenerating = generating;
        if (generating) {
            chatSendBtn.classList.add("stop-btn");
            chatSendBtn.title = "Остановить генерацию";
            chatSendBtn.innerHTML = STOP_ICON_HTML;
        } else {
            chatSendBtn.classList.remove("stop-btn");
            chatSendBtn.title = "Отправить";
            chatSendBtn.innerHTML = SEND_ICON_HTML;
            chatSendBtn.disabled = false;
            chatInput.disabled = false;
            chatInput.focus();
        }
    }

    chatSendBtn.addEventListener("click", () => {
        if (state.isGenerating) {
            // Abort running request
            if (state.abortController) {
                state.abortController.abort();
            }
            setGeneratingState(false);
            showTyping(false);
        } else {
            handleUserText(chatInput.value);
        }
    });

    // 11. Core Message Handler with Streaming Support
    async function handleUserText(text) {
        if (!text || !text.trim() || state.isGenerating) return;
        const query = text.trim();
        state.lastUserQuery = query;

        // Reset input
        chatInput.value = "";
        autoResizeInput();

        // 1. Prepare history for LLM (clean plain text without HTML)
        const historyForBackend = state.messages.slice(-15).map(m => ({
            sender: m.sender,
            text: m.text
        }));

        // 2. Append User Message
        appendMessage("user", query);

        // 3. Setup Generation State
        setGeneratingState(true);
        showTyping(true);

        state.abortController = new AbortController();
        const signal = state.abortController.signal;

        const token = (typeof SkyrexAuth !== "undefined" && SkyrexAuth.getToken) ? SkyrexAuth.getToken() : "";

        // Placeholder for the incoming bot response
        let botMsgDiv = null;
        let botContentDiv = null;
        let accumulatedText = "";
        let isFirstToken = true;

        try {
            const response = await fetch("/api/chat", {
                method: "POST",
                headers: {
                    "Content-Type": "application/json",
                    "Authorization": token ? `Bearer ${token}` : ""
                },
                body: JSON.stringify({
                    message: query,
                    history: historyForBackend,
                    stream: true
                }),
                signal
            });

            // Handle unauthorized (401)
            if (response.status === 401) {
                showTyping(false);
                setGeneratingState(false);
                const data = await response.json().catch(() => ({}));
                appendMessage("bot", data.response || "🔒 <b>Требуется авторизация</b><br>Пожалуйста, войдите в аккаунт.");
                if (typeof SkyrexAuth !== "undefined" && SkyrexAuth.openAuthModal) {
                    SkyrexAuth.openAuthModal();
                }
                return;
            }

            // Handle rate limit (429)
            if (response.status === 429) {
                showTyping(false);
                setGeneratingState(false);
                const data = await response.json().catch(() => ({}));
                appendMessage("bot", data.response || "⏳ Слишком много запросов. Пожалуйста, подождите минуту перед следующим сообщением.");
                return;
            }

            if (!response.ok) {
                throw new Error("HTTP error " + response.status);
            }

            const contentType = response.headers.get("Content-Type") || "";

            // A. STREAMING RESPONSE (Server-Sent Events)
            if (contentType.includes("text/event-stream") && response.body) {
                const reader = response.body.getReader();
                const decoder = new TextDecoder("utf-8");
                let buffer = "";

                while (true) {
                    const { done, value } = await reader.read();
                    if (done) break;

                    buffer += decoder.decode(value, { stream: true });
                    const lines = buffer.split("\n");
                    buffer = lines.pop(); // keep last unfinished line

                    for (const line of lines) {
                        const trimmed = line.trim();
                        if (!trimmed || !trimmed.startsWith("data:")) continue;

                        const dataStr = trimmed.slice(5).trim();
                        if (dataStr === "[DONE]") {
                            break;
                        }

                        try {
                            const parsed = JSON.parse(dataStr);
                            if (parsed.error) {
                                throw new Error(parsed.error);
                            }
                            if (parsed.chunk) {
                                if (isFirstToken) {
                                    showTyping(false);
                                    // Create bot message element
                                    const rendered = appendMessage("bot", "");
                                    botMsgDiv = rendered.msgDiv;
                                    botContentDiv = rendered.contentDiv;
                                    isFirstToken = false;
                                }
                                accumulatedText += parsed.chunk;
                                if (botContentDiv) {
                                    botContentDiv.innerHTML = parseBotContent(accumulatedText);
                                    if (isAtBottom()) {
                                        scrollChatToBottom();
                                    }
                                }
                            }
                        } catch (pe) {
                            // Non-json or raw chunk
                        }
                    }
                }

                // Finalize streamed message
                if (isFirstToken) {
                    showTyping(false);
                    appendMessage("bot", accumulatedText || "⚠️ Ассистент не сформировал ответ.");
                } else {
                    // Update state with final text
                    const lastBotMsg = state.messages[state.messages.length - 1];
                    if (lastBotMsg && lastBotMsg.sender === "bot") {
                        lastBotMsg.text = accumulatedText;
                        saveChatHistory();
                    }
                    if (botContentDiv) {
                        botContentDiv.innerHTML = parseBotContent(accumulatedText);
                    }
                }
            } else {
                // B. STANDARD JSON RESPONSE FALLBACK
                const data = await response.json();
                showTyping(false);
                if (data && data.response) {
                    appendMessage("bot", data.response);
                } else {
                    appendMessage("bot", "⚠️ К сожалению, не удалось получить ответ от ассистента.");
                }
            }
        } catch (err) {
            showTyping(false);
            if (err.name === "AbortError") {
                // Generation cancelled by user
                if (accumulatedText && botContentDiv) {
                    botContentDiv.innerHTML = parseBotContent(accumulatedText + " <i>[Остановлено пользователем]</i>");
                    const lastBotMsg = state.messages[state.messages.length - 1];
                    if (lastBotMsg && lastBotMsg.sender === "bot") {
                        lastBotMsg.text = accumulatedText;
                        saveChatHistory();
                    }
                }
            } else {
                console.error("Chat API Error:", err);
                const errMsg = "⚠️ Не удалось связаться с сервером AI-ассистента. Убедитесь, что сервер запущен.";
                const rendered = appendMessage("bot", errMsg);
                // Attach Retry button
                if (rendered && rendered.contentDiv) {
                    const retryBtn = document.createElement("button");
                    retryBtn.className = "chat-retry-btn";
                    retryBtn.innerHTML = `
                        <svg xmlns="http://www.w3.org/2000/svg" width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round">
                            <polyline points="1 4 1 10 7 10"></polyline>
                            <path d="M3.51 15a9 9 0 1 0 2.13-9.36L1 10"></path>
                        </svg>
                        <span>Повторить запрос</span>
                    `;
                    retryBtn.addEventListener("click", () => {
                        retryBtn.remove();
                        if (state.lastUserQuery) {
                            handleUserText(state.lastUserQuery);
                        }
                    });
                    rendered.contentDiv.appendChild(retryBtn);
                }
            }
        } finally {
            setGeneratingState(false);
            showTyping(false);
            state.abortController = null;
        }
    }

    // 12. Floating Scroll-to-bottom button logic
    if (scrollBottomBtn) {
        chatBody.addEventListener("scroll", () => {
            const distanceFromBottom = chatBody.scrollHeight - chatBody.scrollTop - chatBody.clientHeight;
            if (distanceFromBottom > 120) {
                scrollBottomBtn.classList.add("visible");
            } else {
                scrollBottomBtn.classList.remove("visible");
                scrollBottomBtn.classList.remove("has-unread");
            }
        });

        scrollBottomBtn.addEventListener("click", () => {
            scrollChatToBottom(true);
            scrollBottomBtn.classList.remove("has-unread");
        });
    }

    // 13. Clear Chat History Button
    if (chatClearBtn) {
        chatClearBtn.addEventListener("click", () => {
            if (confirm("Вы действительно хотите очистить историю сообщений?")) {
                localStorage.removeItem("skyrex_chat_history");
                state.messages = [];
                chatBody.innerHTML = "";
                sendGreeting();
            }
        });
    }

    // 14. Initialize UI & Chat
    loadChatHistory();
});
