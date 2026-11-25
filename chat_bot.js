// Skyrex AI Assistant - Modern Conversational AI Client Logic
// Direct natural language dialogue, live streaming, markdown formatting, suggestion chips, and catalog tools

document.addEventListener("DOMContentLoaded", () => {
    // 1. DOM Elements
    const chatBody = document.getElementById("chat-body");
    const chatInput = document.getElementById("chat-input");
    const chatSendBtn = document.getElementById("chat-send-btn");
    const chatAutocomplete = document.getElementById("chat-autocomplete");
    const chatReplyKeyboard = document.getElementById("chat-reply-keyboard") || chatAutocomplete;
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

    // Autocomplete dictionary for interactive typing suggestions
    const AUTOCOMPLETE_ITEMS = [
        { title: "Сборка за 50 000 ₽", prompt: "Собери бюджетный игровой ПК за 50 000 рублей с актуальными ценами", icon: "🎮", tags: ["сборка", "бюджет", "50000", "50к", "пк", "дешевый"] },
        { title: "Сборка за 70 000 ₽", prompt: "Собери сбалансированный игровой ПК за 70 000 рублей с актуальными ценами", icon: "🎮", tags: ["сборка", "70000", "70к", "пк", "базовый"] },
        { title: "Сборка за 80 000 ₽", prompt: "Собери сбалансированный игровой ПК за 80 000 рублей с актуальными ценами", icon: "🎮", tags: ["сборка", "80000", "80к", "пк", "оптимальный"] },
        { title: "Сборка за 100 000 ₽", prompt: "Собери оптимальный игровой ПК за 100 000 рублей с актуальными ценами", icon: "🎮", tags: ["сборка", "100000", "100к", "пк"] },
        { title: "Сборка за 120 000 ₽", prompt: "Собери мощный игровой ПК за 120 000 рублей с актуальными ценами", icon: "🚀", tags: ["сборка", "120000", "120к", "пк"] },
        { title: "Сборка за 150 000 ₽", prompt: "Собери мощный ПК за 150 000 рублей для 2K-гейминга и работы", icon: "🚀", tags: ["сборка", "150000", "150к", "2к", "пк"] },
        { title: "Сборка за 200 000 ₽", prompt: "Собери топовый ПК за 200 000 рублей для 4K гейминга и тяжелых задач", icon: "👑", tags: ["сборка", "200000", "200к", "4к", "топ", "пк"] },
        { title: "Сборка для CS2 и Dota 2", prompt: "Подбери недорогой и надежный ПК специально для CS2, Dota 2 и онлайн-игр", icon: "🎯", tags: ["сборка", "cs", "cs2", "кс", "дота", "dota", "онлайн", "киберспорт"] },
        { title: "Сборка для 2K гейминга", prompt: "Собери ПК для стабильного ультра-гейминга в разрешении 1440p (2K)", icon: "🖥️", tags: ["сборка", "2k", "2к", "1440p", "гейминг", "ультра"] },
        { title: "Сборка для стриминга и монтажа", prompt: "Подбери рабочую станцию для стримов и видеомонтажа в Premiere и DaVinci", icon: "🎬", tags: ["сборка", "стрим", "монтаж", "работа", "видео", "контент"] },
        { title: "Сборка со встроенной графикой", prompt: "Собери недорогой ПК со встроенной графикой (APU) с возможностью будущего апгрейда видеокарты", icon: "📦", tags: ["сборка", "встройка", "apu", "без видеокарты", "бюджет"] },
        { title: "Цены на RTX 4060", prompt: "Сколько сейчас стоит видеокарта GeForce RTX 4060 и какие варианты в наличии?", icon: "🔍", tags: ["цена", "цены", "rtx", "4060", "видеокарта", "nvidia"] },
        { title: "Цены на RTX 4070 Super", prompt: "Сколько стоит GeForce RTX 4070 Super и какой блок питания под неё нужен?", icon: "🔍", tags: ["цена", "цены", "rtx", "4070", "super", "видеокарта", "nvidia"] },
        { title: "Цены на Radeon RX 7700 XT", prompt: "Сколько сейчас стоит Radeon RX 7700 XT и как она в играх по сравнению с RTX 4060 Ti?", icon: "🔍", tags: ["цена", "цены", "rx", "7700", "radeon", "amd", "видеокарта"] },
        { title: "Ryzen 5 7500F vs Core i5 13400", prompt: "Что лучше выбрать для игр: AMD Ryzen 5 7500F или Intel Core i5 13400?", icon: "⚡", tags: ["ryzen", "райзен", "i5", "интел", "intel", "сравнение", "процессор", "7500f", "13400"] },
        { title: "Ryzen 7 7800X3D vs Core i7 14700K", prompt: "Сравни топовые игровые процессоры Ryzen 7 7800X3D и Core i7 14700K", icon: "⚡", tags: ["ryzen", "райзен", "7800x3d", "i7", "14700k", "процессор", "топ"] },
        { title: "Апгрейд старого ПК", prompt: "Помоги спланировать апгрейд старого ПК. На что обратить внимание в первую очередь?", icon: "🛠️", tags: ["апгрейд", "обновление", "модернизация", "старый", "пк"] },
        { title: "Апгрейд видеокарты", prompt: "Какую видеокарту выбрать на замену старой GTX 1060 / 1660 Super?", icon: "🛠️", tags: ["апгрейд", "видеокарта", "замена", "gtx", "1060", "1660"] },
        { title: "Б/У сборки SkyRex", prompt: "Покажи проверенные сборки ПК и комплектующие со вторичного рынка из каталога SkyRex", icon: "💻", tags: ["бу", "б/у", "каталог", "вторичка", "skyrex", "скайрекс"] },
        { title: "Проверка совместимости комплектующих", prompt: "Проверь совместимость выбранных комплектующих и рассчитай мощность БП", icon: "⚖️", tags: ["совместимость", "проверка", "сокет", "память", "блок питания"] },
        { title: "Какой блок питания выбрать", prompt: "Как правильно подобрать мощность и сертификат блока питания для игровой системы?", icon: "🔌", tags: ["блок питания", "бп", "ватт", "питание", "power"] },
        { title: "DDR4 vs DDR5: что выбрать?", prompt: "Стоит ли сейчас переплачивать за память DDR5 или остаться на DDR4?", icon: "💾", tags: ["ddr4", "ddr5", "память", "озу", "ram"] }
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

    // Modern Chat Toast Notification System
    function showToast(text, type = "info", duration = 4000) {
        let container = document.getElementById("chat-toast-container");
        if (!container) {
            container = document.createElement("div");
            container.id = "chat-toast-container";
            container.className = "chat-toast-container";
            const parent = document.querySelector(".hero-chat-container") || chatBody || document.body;
            parent.appendChild(container);
        }

        const toast = document.createElement("div");
        toast.className = `chat-toast chat-toast-${type}`;
        const iconHtml = type === "warning" ? "⚠️" : (type === "success" ? "✅" : "💡");

        toast.innerHTML = `
            <div class="chat-toast-content">
                <span class="chat-toast-icon">${iconHtml}</span>
                <span class="chat-toast-text">${text}</span>
            </div>
            <button class="chat-toast-close" title="Закрыть" aria-label="Закрыть">&times;</button>
        `;

        const closeBtn = toast.querySelector(".chat-toast-close");
        if (closeBtn) {
            closeBtn.addEventListener("click", () => {
                toast.classList.add("chat-toast-hiding");
                setTimeout(() => toast.remove(), 250);
            });
        }

        container.appendChild(toast);

        setTimeout(() => {
            if (toast.parentNode) {
                toast.classList.add("chat-toast-hiding");
                setTimeout(() => toast.remove(), 250);
            }
        }, duration);
    }

    function formatTime(date = new Date()) {
        const d = (date instanceof Date) ? date : new Date(date);
        if (isNaN(d.getTime())) return "ранее";
        return d.getHours().toString().padStart(2, '0') + ":" + d.getMinutes().toString().padStart(2, '0');
    }

    function sanitizeMarketplaceUrl(url, linkTitle = "") {
        if (!url) return url;

        let query = (linkTitle || "")
            .replace(/<[^>]+>/g, "")
            .replace(/\(Б\/У\)/gi, "")
            .replace(/\(б\/у\)/gi, "")
            .replace(/Б\/У/gi, "")
            .replace(/\b(компьютерный|компьютерная|компьютерное|для компьютера|для пк)\b/gi, "")
            .trim();

        // If linkTitle is empty or invalid, try to extract from query parameters or URL path
        if (!query || query.length < 2) {
            try {
                const matchQ = url.match(/[?&](?:q|search|query)=([^&#]+)/);
                if (matchQ && matchQ[1]) {
                    query = decodeURIComponent(matchQ[1].replace(/\+/g, " "));
                }
            } catch (e) {}
        }

        if (!query || query.length < 2 || /(?:такогонить|па0)/i.test(query)) {
            query = "комплектующие для пк";
        }

        query = query.replace(/\s+/g, " ").trim();
        const encoded = encodeURIComponent(query);

        if (url.includes("wildberries.ru")) {
            return `https://www.wildberries.ru/catalog/0/search.aspx?search=${encoded}`;
        }
        if (url.includes("onlinetrade.ru")) {
            return `https://www.onlinetrade.ru/catalogue/?query=${encoded}`;
        }
        if (url.includes("dns-shop.ru")) {
            return `https://www.dns-shop.ru/search/?q=${encoded}`;
        }
        if (url.includes("avito.ru")) {
            return `https://www.avito.ru/all?q=${encoded}`;
        }

        return url;
    }

    const sanitizeAvitoUrl = sanitizeMarketplaceUrl;

    function collapseMultipleBuildDrafts(raw) {
        if (!raw) return raw;
        const regex = /(?:<br\s*\/?>|\n|^)\s*(?:<li>)?\s*(?:<b>)?\s*1\.\s*(?:<b>)?\s*(?:Процессор|CPU)/gi;
        const matches = [...raw.matchAll(regex)];
        if (matches.length <= 1) return raw;

        const firstIndex = matches[0].index;
        const lastIndex = matches[matches.length - 1].index;

        let intro = raw.substring(0, firstIndex).trim();
        intro = intro.replace(/(?:<br\s*\/?>|\n)*\s*(?:Вот|Ниже|Конфигурация).*?:\s*$/i, '').trim();

        let finalBuild = raw.substring(lastIndex).trim();
        return `${intro}\n\n<b>Вот оптимальная конфигурация ПК под ваш бюджет:</b>\n${finalBuild}`;
    }

    /**
     * Resilient hybrid Markdown and HTML parser for bot responses.
     * Safely handles markdown tables, bold, italics, headers, code blocks, lists, and links.
     */
    function parseBotContent(rawText) {
        if (!rawText) return "";
        let text = collapseMultipleBuildDrafts(rawText);

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

        // 5.1. Normalize GamerStorm PSUs (eliminate Deepcool brand mentions for GamerStorm PF series)
        text = text.replace(/deepcool\s+gamerstorm/gi, 'GamerStorm');
        text = text.replace(/deepcool\s*(pf[- ]?\d+[xd]?)/gi, 'GamerStorm $1');

        // 6. Markdown links: [Title](URL) -> <a href='URL' target='_blank'>Title</a>
        text = text.replace(/\[([^\]]+)\]\((https?:\/\/[^\s\)]+)\)/g, (match, title, url) => {
            const cleanUrl = sanitizeMarketplaceUrl(url, title);
            return `<a href="${cleanUrl}" target="_blank" rel="noopener noreferrer">${title}</a>`;
        });

        // 6.1. Sanitize any existing HTML <a> tags pointing to marketplaces
        text = text.replace(/<a\s+([^>]*?)href=(['"])(https?:\/\/[^'"]+)\2([^>]*)>(.*?)<\/a>/gi, (match, before, quote, url, after, innerText) => {
            const cleanUrl = sanitizeMarketplaceUrl(url, innerText);
            const targetAttr = (before + after).includes("target=") ? "" : ' target="_blank" rel="noopener noreferrer"';
            return `<a ${before}href="${cleanUrl}"${after}${targetAttr}>${innerText}</a>`;
        });

        // 7. Auto-link bare URLs not inside tags
        text = text.replace(/(^|[^"'])(https?:\/\/[^\s<]+)/g, (match, prefix, url) => {
            if (prefix.includes("href=") || prefix.includes("src=")) return match;
            const cleanUrl = sanitizeMarketplaceUrl(url, "");
            return `${prefix}<a href="${cleanUrl}" target="_blank" rel="noopener noreferrer">${url}</a>`;
        });

        // 7.1. Auto-link unlinked RAM in build positions (e.g. "4. Оперативная память (RAM): Комплект 16 ГБ DDR4... — ...")
        text = text.replace(/((?:^|\n)\s*\d+\.\s*(?:<b>)?(?:Оперативная память|RAM)[^:\n]*:\s*(?:<\/b>)?)(?!<a\s)([^—\n<]+?)\s*(—|-)/gi, (match, prefix, compName, sep) => {
            const trimmed = compName.trim();
            if (trimmed.length >= 3 && /ddr/i.test(trimmed)) {
                const avitoUrl = sanitizeAvitoUrl("https://www.avito.ru/all", trimmed);
                return `${prefix}<a href="${avitoUrl}" target="_blank" rel="noopener noreferrer">${trimmed}</a> ${sep}`;
            }
            return match;
        });


        // Clean any pseudo-buttons with emoji dots (e.g. • «🟢 Да, можно Б/У...»)
        text = text.replace(/(?:<br\s*\/?>|\n)?\s*[•\*\-]?[ \t]*[«"']?[🟢🔵][^\n<]+/gi, "");

        // 8. Unordered lists: lines starting with * or - or •
        text = text.replace(/(?:^|\n)[ \t]*[*\-•][ \t]+([^\n]+)/g, "\n<li>$1</li>");
        text = text.replace(/(?:<li>[\s\S]*?<\/li>)/g, (match) => {
            return `<ul>${match}</ul>`;
        });
        // Fix duplicate <ul><ul> wrappers and empty lists
        text = text.replace(/<\/ul>\s*<ul>/g, "");
        text = text.replace(/<ul>\s*(?:<li>\s*<\/li>\s*)*<\/ul>/gi, "");

        // 9. Blockquotes: > quote
        text = text.replace(/^>\s+(.+)$/gm, "<blockquote>$1</blockquote>");

        // 9.1. Prevent glued numbered items and headers (e.g. "руб.2. Материнская плата" -> "руб.<br>2. Материнская плата")
        text = text.replace(/([^\n>])\s*((?:[1-9]|10)\.\s*(?:<b>)?[А-ЯA-Z])/g, "$1<br>$2");
        text = text.replace(/((?:руб\.?|₽|\))\s*)((?:[1-9]|10)\.\s*(?:<b>)?[А-ЯA-Z])/g, "$1<br>$2");
        text = text.replace(/((?:руб\.?|₽))\s*(Точная|Итого|Остаток|Примечание)/gi, "$1<br><br>$2");
        text = text.replace(/([^\n>])\s*(Конфигурация ПК под ваш бюджет|Вот сбалансированная|Вот оптимальная|Точная суммарная стоимость|Примечание эксперта|Примечание)/gi, "$1<br><br>$2");

        // 9.2. Exact mathematical synchronization of total build price:
        // Ensure the summary in chat text strictly matches the single mathematically calculated variable
        if (window.SkyrexRig && window.SkyrexRig.state && window.SkyrexRig.state.isCustomized && window.SkyrexRig.state.total && window.SkyrexRig.state.total !== "?") {
            const rawExact = String(window.SkyrexRig.state.total).replace(/\D/g, '');
            const exactNum = parseInt(rawExact, 10);
            if (!isNaN(exactNum) && exactNum > 0) {
                const formatted = exactNum.toLocaleString('ru-RU') + " руб.";
                const totalBlockPattern = /(?:<b>)?\s*(?:Точная суммарная стоимость|Итого(?:вая)? стоимость|Суммарная стоимость|Стоимость сборки|Итого)(?:<\/b>)?\s*[:—–-]?\s*(?:<\/b>)?(?:\s*<br\s*\/?>|\s*\n|\s)*(?:(?:<b>)?\s*[\d\s\xa0]{3,}(?:\s*руб\.?|₽)?\s*(?:<\/b>)?(?:\s*<br\s*\/?>|\s)*)+/gi;
                let replaced = false;
                text = text.replace(totalBlockPattern, () => {
                    if (!replaced) {
                        replaced = true;
                        return `<b>Точная суммарная стоимость:</b> <b>${formatted}</b>`;
                    }
                    return "";
                });
            }
        }

        // Clean any duplicate adjacent prices (e.g. "98 000 руб.98 000 руб." or "98 000 руб. 98 000 руб.")
        const priceDupPattern = /((?:<b>)?\s*[\d\s\xa0]{3,}\s*(?:руб\.?|₽)\s*(?:<\/b>)?)\s*(?:<br\s*\/?>)?\s*(?:<b>)?\s*([\d\s\xa0]{3,}\s*(?:руб\.?|₽))\s*(?:<\/b>)?/gi;
        const replDup = (m, g1, g2) => {
            const p1 = g1.replace(/\D/g, '');
            const p2 = g2.replace(/\D/g, '');
            if (p1 && p2 && p1 === p2) {
                return g1;
            }
            return m;
        };
        text = text.replace(priceDupPattern, replDup).replace(priceDupPattern, replDup);


        // 10. Clean newlines: convert newlines to <br> unless adjacent to block tags
        text = text.replace(/([^\n>])\n([^\n<])/g, "$1<br>$2");

        // Restore inline code & code blocks
        inlineCodes.forEach((codeHtml, idx) => {
            text = text.replace(`__INLINE_CODE_${idx}__`, codeHtml);
        });
        codeBlocks.forEach((blockHtml, idx) => {
            text = text.replace(`__CODE_BLOCK_${idx}__`, blockHtml);
        });

        // 11. Security sanitizer: strip any potentially dangerous tags, event handlers or javascript: protocols
        text = text.replace(/<\s*(?:script|iframe|object|embed|style|link|meta|form|input|button|svg|canvas|base|applet)[^>]*>[\s\S]*?<\s*\/\s*(?:script|iframe|object|embed|style|link|meta|form|input|button|svg|canvas|base|applet)\s*>/gi, "");
        text = text.replace(/<\s*(?:script|iframe|object|embed|style|link|meta|form|input|button|svg|canvas|base|applet|img)[^>]*\/?>/gi, "");
        text = text.replace(/\s+on[a-zA-Z]+\s*=\s*(?:"[^"]*"|'[^']*'|[^\s>]+)/gi, "");
        text = text.replace(/(href\s*=\s*['"])(?:javascript|data|vbscript):[^'"]*(['"])/gi, "$1#$2");

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

        // Action buttons container (Gemini-style actions)
        const actionsDiv = document.createElement("div");
        actionsDiv.className = "chat-msg-actions" + (msgObj.sender === "user" ? " user-msg-actions" : "");

        if (msgObj.sender === "bot") {
            // 1. Copy Bot Response
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
                const plainText = contentDiv.innerText || contentDiv.textContent || msgObj.text;
                navigator.clipboard.writeText(plainText.trim()).then(() => {
                    copyBtn.classList.add("copied");
                    copyBtn.querySelector("span").textContent = "Скопировано!";
                    setTimeout(() => {
                        copyBtn.classList.remove("copied");
                        copyBtn.querySelector("span").textContent = "Копировать";
                    }, 2000);
                    showToast("Ответ скопирован в буфер", "success", 2000);
                }).catch(err => {
                    console.warn("Clipboard copy failed:", err);
                });
            });
            actionsDiv.appendChild(copyBtn);

            // 2. Regenerate Response Button (🔄)
            const regenBtn = document.createElement("button");
            regenBtn.className = "msg-action-btn";
            regenBtn.title = "Сгенерировать ответ заново";
            regenBtn.innerHTML = `
                <svg xmlns="http://www.w3.org/2000/svg" width="11" height="11" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round">
                    <polyline points="23 4 23 10 17 10"></polyline>
                    <polyline points="1 20 1 14 7 14"></polyline>
                    <path d="M3.51 9a9 9 0 0 1 14.85-3.36L23 10M1 14l4.64 4.36A9 9 0 0 0 20.49 15"></path>
                </svg>
                <span>Повторить</span>
            `;
            regenBtn.addEventListener("click", () => {
                if (state.isGenerating) return;
                let targetQuery = "";
                const msgIdx = state.messages.findIndex(m => m.id === msgObj.id);
                if (msgIdx > 0) {
                    for (let j = msgIdx - 1; j >= 0; j--) {
                        if (state.messages[j].sender === "user") {
                            targetQuery = state.messages[j].text;
                            break;
                        }
                    }
                }
                if (!targetQuery) targetQuery = state.lastUserQuery;
                if (targetQuery) {
                    handleUserText(targetQuery);
                }
            });
            actionsDiv.appendChild(regenBtn);

            footerDiv.appendChild(actionsDiv);
        } else {
            // User message actions: Edit Prompt (✏️) and Copy (📋)
            const editBtn = document.createElement("button");
            editBtn.className = "msg-action-btn";
            editBtn.title = "Редактировать запрос";
            editBtn.innerHTML = `
                <svg xmlns="http://www.w3.org/2000/svg" width="11" height="11" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round">
                    <path d="M11 4H4a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h14a2 2 0 0 0 2-2v-7"></path>
                    <path d="M18.5 2.5a2.121 2.121 0 0 1 3 3L12 15l-4 1 1-4 9.5-9.5z"></path>
                </svg>
                <span>Редактировать</span>
            `;
            editBtn.addEventListener("click", () => {
                chatInput.value = msgObj.text;
                autoResizeInput();
                chatInput.focus();
                chatInput.selectionStart = chatInput.selectionEnd = chatInput.value.length;
                chatInput.scrollIntoView({ behavior: "smooth", block: "center" });
                showToast("Текст запроса загружен в поле ввода", "info", 2000);
            });
            actionsDiv.appendChild(editBtn);

            const copyUserBtn = document.createElement("button");
            copyUserBtn.className = "msg-action-btn";
            copyUserBtn.title = "Копировать текст запроса";
            copyUserBtn.innerHTML = `
                <svg xmlns="http://www.w3.org/2000/svg" width="11" height="11" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                    <rect x="9" y="9" width="13" height="13" rx="2" ry="2"></rect>
                    <path d="M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1"></path>
                </svg>
                <span>Копировать</span>
            `;
            copyUserBtn.addEventListener("click", () => {
                navigator.clipboard.writeText(msgObj.text).then(() => {
                    copyUserBtn.classList.add("copied");
                    copyUserBtn.querySelector("span").textContent = "Скопировано!";
                    setTimeout(() => {
                        copyUserBtn.classList.remove("copied");
                        copyUserBtn.querySelector("span").textContent = "Копировать";
                    }, 2000);
                    showToast("Запрос скопирован в буфер", "success", 2000);
                });
            });
            actionsDiv.appendChild(copyUserBtn);

            footerDiv.appendChild(actionsDiv);
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
        const rendered = renderMessage(msgObj, true);
        return { ...rendered, msgObj };
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
                    if (window.SkyrexRig && typeof window.SkyrexRig.updateFromAiResponse === "function") {
                        for (let i = state.messages.length - 1; i >= 0; i--) {
                            const m = state.messages[i];
                            if (m.sender === "bot" && (m.text.includes("Процессор") || m.text.includes("Видеокарта"))) {
                                window.SkyrexRig.updateFromAiResponse(m.text);
                                break;
                            }
                        }
                    }
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
            const token = (typeof SkyrexAuth !== "undefined" && SkyrexAuth.getToken) ? SkyrexAuth.getToken() : "";
            const authPrompt = token
                ? "<i>Начните вводить ваш вопрос или бюджет (например, «сборка за 80000»), чтобы увидеть умные подсказки!</i>"
                : "🔒 <i>Для общения с ИИ-консультантом и отправки запросов, пожалуйста, <a href='javascript:void(0)' onclick='window.SkyrexAuth && window.SkyrexAuth.openAuthModal()' style='color: var(--neon-accent, #8b5cf6); text-decoration: underline; font-weight: 600;'>войдите в аккаунт</a> или <a href='javascript:void(0)' onclick='window.SkyrexAuth && (window.SkyrexAuth.openAuthModal(), window.SkyrexAuth.switchAuthTab(\"register\"))' style='color: var(--neon-cyan, #06b6d4); text-decoration: underline; font-weight: 600;'>зарегистрируйтесь</a>.</i>";

            const welcomeText =
                "👋 <b>Добро пожаловать в SkyRex AI Assistant!</b>\n\n" +
                "Я интеллектуальный ИИ-консультант по компьютерному железу, сборке ПК и подбору комплектующих.\n\n" +
                "💡 <b>Чем я могу вам помочь:</b>\n" +
                "• 🛒 <b>Актуальные цены:</b> предоставлю реальные цены и прямые ссылки на новые комплектующие из ОнлайнТрейд\n" +
                "• 🛠️ <b>Индивидуальная сборка:</b> соберу идеальный сбалансированный ПК под ваш бюджет и задачи (игры, 3D, стриминг, работа)\n" +
                "• ⚖️ <b>Сравнение и аналитика:</b> оценю совместимость сокетов (AM4/AM5/LGA 1700), тип памяти и мощность блока питания\n" +
                "• 💻 <b>Вторичный рынок:</b> подберу надежные позиции со вторички из каталога SkyRex\n\n" +
                authPrompt;

            appendMessage("bot", welcomeText);
        }, 400);
    }

    // 8. Autocomplete Suggestions Engine
    let activeSuggestionIndex = -1;
    let currentMatches = [];

    function getAutocompleteMatches(rawQuery) {
        const query = (rawQuery || "").trim().toLowerCase();
        if (!query || query.length < 1) return [];

        const tokens = query.split(/\s+/).filter(t => t.length > 0);

        return AUTOCOMPLETE_ITEMS.filter(item => {
            const titleLower = item.title.toLowerCase();
            const promptLower = (item.prompt || "").toLowerCase();
            const tags = (item.tags || []).map(t => t.toLowerCase());

            return tokens.every(token => {
                if (titleLower.includes(token) || promptLower.includes(token)) return true;
                if (tags.some(tag => tag.includes(token) || token.includes(tag))) return true;
                if (token.length >= 4) {
                    const stem = token.slice(0, 4);
                    if (titleLower.includes(stem) || tags.some(tag => tag.includes(stem))) return true;
                }
                return false;
            });
        }).slice(0, 6);
    }

    function highlightMatch(text, query) {
        if (!query || !query.trim()) return escapeHtml(text);
        const tokens = query.trim().split(/\s+/).filter(t => t.length > 0);
        if (tokens.length === 0) return escapeHtml(text);

        const safeText = escapeHtml(text);
        const escaped = tokens.map(t => t.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')).join('|');
        const regex = new RegExp('(' + escaped + ')', 'gi');
        return safeText.replace(regex, '<span class="ac-match">$1</span>');
    }

    function showAutocomplete(matches, query) {
        if (!chatAutocomplete) return;
        currentMatches = matches;
        activeSuggestionIndex = -1;

        if (matches.length === 0) {
            hideAutocomplete();
            return;
        }

        chatAutocomplete.innerHTML = "";
        matches.forEach((item, idx) => {
            const itemEl = document.createElement("div");
            itemEl.className = "chat-autocomplete-item";
            itemEl.setAttribute("role", "option");
            itemEl.dataset.index = idx;

            const highlightedTitle = highlightMatch(item.title, query);

            itemEl.innerHTML = `
                <div class="ac-main">
                    <span class="ac-icon">${item.icon || "💡"}</span>
                    <span class="ac-text">${highlightedTitle}</span>
                </div>
                <div class="ac-actions">
                    <span class="ac-hint">Tab ⇥</span>
                    <button type="button" class="ac-send-btn" title="Отправить сразу" aria-label="Отправить">
                        <svg xmlns="http://www.w3.org/2000/svg" width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round">
                            <line x1="22" y1="2" x2="11" y2="13"></line>
                            <polygon points="22 2 15 22 11 13 2 9 22 2"></polygon>
                        </svg>
                    </button>
                </div>
            `;

            // Prevent blur of chatInput when clicking suggestion
            itemEl.addEventListener("mousedown", (e) => {
                e.preventDefault();
            });

            const sendBtn = itemEl.querySelector(".ac-send-btn");
            if (sendBtn) {
                sendBtn.addEventListener("click", (e) => {
                    e.stopPropagation();
                    selectAutocompleteItem(item, true);
                });
            }

            itemEl.addEventListener("click", () => {
                selectAutocompleteItem(item, false);
            });

            itemEl.addEventListener("mouseenter", () => {
                setActiveAutocompleteIndex(idx);
            });

            chatAutocomplete.appendChild(itemEl);
        });

        chatAutocomplete.style.display = "flex";
    }

    function hideAutocomplete() {
        if (!chatAutocomplete) return;
        chatAutocomplete.style.display = "none";
        chatAutocomplete.innerHTML = "";
        currentMatches = [];
        activeSuggestionIndex = -1;
    }

    function setActiveAutocompleteIndex(index) {
        if (!chatAutocomplete) return;
        const items = chatAutocomplete.querySelectorAll(".chat-autocomplete-item");
        items.forEach(el => el.classList.remove("active"));

        if (index >= 0 && index < items.length) {
            activeSuggestionIndex = index;
            items[index].classList.add("active");
            items[index].scrollIntoView({ block: "nearest", behavior: "smooth" });
        } else {
            activeSuggestionIndex = -1;
        }
    }

    function selectAutocompleteItem(item, sendImmediately = false) {
        if (!item) return;
        if (sendImmediately) {
            hideAutocomplete();
            chatInput.value = "";
            autoResizeInput();
            handleUserText(item.prompt || item.title);
        } else {
            chatInput.value = item.title;
            autoResizeInput();
            hideAutocomplete();
            chatInput.focus();
            chatInput.selectionStart = chatInput.selectionEnd = chatInput.value.length;
        }
    }

    // Dismiss autocomplete when clicking outside
    document.addEventListener("click", (e) => {
        if (chatAutocomplete && chatAutocomplete.style.display !== "none") {
            if (!chatAutocomplete.contains(e.target) && e.target !== chatInput) {
                hideAutocomplete();
            }
        }
    });

    // 9. Input & Auto-resize textarea
    function autoResizeInput() {
        if (!chatInput) return;
        chatInput.style.height = "auto";
        const maxHeight = 130;
        const scrollH = chatInput.scrollHeight;
        const newHeight = Math.min(scrollH, maxHeight);
        chatInput.style.height = (newHeight > 44 ? newHeight : 44) + "px";
        chatInput.style.overflowY = scrollH > maxHeight ? "auto" : "hidden";
    }

    autoResizeInput();

    // User Prompt History Stack (Gemini/Terminal style ↑ / ↓ prompt recall)
    let inputHistoryIndex = -1;
    let savedDraftText = "";

    chatInput.addEventListener("input", () => {
        inputHistoryIndex = -1;
        savedDraftText = "";
        autoResizeInput();
        if (state.isGenerating) {
            hideAutocomplete();
            return;
        }
        const val = chatInput.value;
        if (val.trim().length >= 1) {
            const matches = getAutocompleteMatches(val);
            showAutocomplete(matches, val);
        } else {
            hideAutocomplete();
        }
    });

    chatInput.addEventListener("focus", () => {
        if (state.isGenerating) return;
        const val = chatInput.value;
        if (val.trim().length >= 1) {
            const matches = getAutocompleteMatches(val);
            showAutocomplete(matches, val);
        }
    });

    chatInput.addEventListener("keydown", (e) => {
        const isAcVisible = chatAutocomplete && chatAutocomplete.style.display !== "none" && currentMatches.length > 0;

        if (e.key === "ArrowDown") {
            if (isAcVisible) {
                e.preventDefault();
                const nextIdx = (activeSuggestionIndex + 1) % currentMatches.length;
                setActiveAutocompleteIndex(nextIdx);
                return;
            }
            // Navigate forward in user prompt history
            const userHistory = state.messages.filter(m => m.sender === "user").map(m => m.text);
            if (inputHistoryIndex !== -1 && userHistory.length > 0) {
                e.preventDefault();
                if (inputHistoryIndex < userHistory.length - 1) {
                    inputHistoryIndex++;
                    chatInput.value = userHistory[inputHistoryIndex];
                } else {
                    inputHistoryIndex = -1;
                    chatInput.value = savedDraftText;
                }
                autoResizeInput();
                chatInput.selectionStart = chatInput.selectionEnd = chatInput.value.length;
                return;
            }
        }

        if (e.key === "ArrowUp") {
            if (isAcVisible) {
                e.preventDefault();
                const prevIdx = activeSuggestionIndex <= 0 ? currentMatches.length - 1 : activeSuggestionIndex - 1;
                setActiveAutocompleteIndex(prevIdx);
                return;
            }
            // Recall previous user prompt from history (Gemini style)
            const userHistory = state.messages.filter(m => m.sender === "user").map(m => m.text);
            if (userHistory.length > 0 && (chatInput.selectionStart === 0 || chatInput.value.trim() === "" || inputHistoryIndex !== -1)) {
                e.preventDefault();
                if (inputHistoryIndex === -1) {
                    savedDraftText = chatInput.value;
                    inputHistoryIndex = userHistory.length - 1;
                } else if (inputHistoryIndex > 0) {
                    inputHistoryIndex--;
                }
                chatInput.value = userHistory[inputHistoryIndex];
                autoResizeInput();
                chatInput.selectionStart = chatInput.selectionEnd = chatInput.value.length;
                return;
            }
        }

        if (e.key === "Escape") {
            if (isAcVisible) {
                e.preventDefault();
                hideAutocomplete();
                return;
            }
            if (chatInput.value.length > 0) {
                e.preventDefault();
                chatInput.value = "";
                inputHistoryIndex = -1;
                savedDraftText = "";
                autoResizeInput();
                return;
            }
        }

        if (e.key === "Tab" && isAcVisible) {
            e.preventDefault();
            const target = activeSuggestionIndex >= 0 ? currentMatches[activeSuggestionIndex] : currentMatches[0];
            selectAutocompleteItem(target, false);
            return;
        }

        if (e.key === "Enter" && !e.shiftKey) {
            e.preventDefault();
            if (isAcVisible && activeSuggestionIndex >= 0) {
                const item = currentMatches[activeSuggestionIndex];
                if (chatInput.value.trim().toLowerCase() === item.title.toLowerCase()) {
                    selectAutocompleteItem(item, true);
                } else {
                    selectAutocompleteItem(item, false);
                }
                return;
            }

            hideAutocomplete();
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

    // 11. Core Message Handler with Streaming Support and Automatic Error Rollback
    async function handleUserText(text) {
        if (!text || !text.trim() || state.isGenerating) return;
        const query = text.trim();

        // Reset history stack
        inputHistoryIndex = -1;
        savedDraftText = "";

        // 0. Enforce authentication: strictly require logged-in user
        const token = (typeof SkyrexAuth !== "undefined" && SkyrexAuth.getToken) ? SkyrexAuth.getToken() : "";
        if (!token) {
            hideAutocomplete();
            chatInput.value = query;
            autoResizeInput();
            chatInput.focus();
            showToast("🔒 Для общения с ИИ-консультантом необходимо войти или зарегистрироваться.", "warning", 5000);
            if (typeof SkyrexAuth !== "undefined" && SkyrexAuth.openAuthModal) {
                SkyrexAuth.openAuthModal();
            }
            return;
        }

        state.lastUserQuery = query;

        // Reset input
        chatInput.value = "";
        autoResizeInput();
        hideAutocomplete();

        // 1. Prepare history for LLM (clean plain text without HTML)
        const historyForBackend = state.messages.slice(-15).map(m => ({
            sender: m.sender,
            text: m.text
        }));

        // 2. Append User Message
        const userRendered = appendMessage("user", query);
        const userMsgDiv = userRendered ? userRendered.msgDiv : null;
        const userMsgObj = userRendered ? userRendered.msgObj : null;

        // 3. Setup Generation State
        setGeneratingState(true);
        showTyping(true);

        state.abortController = new AbortController();
        const signal = state.abortController.signal;

        // Placeholder for the incoming bot response
        let botMsgDiv = null;
        let botContentDiv = null;
        let accumulatedText = "";
        let isFirstToken = true;

        // Rollback helper: removes user message from DOM & state, restores query back into chatInput
        function rollbackUserMessage(errorMessage) {
            if (userMsgDiv && userMsgDiv.parentNode) {
                userMsgDiv.remove();
            }
            if (userMsgObj) {
                const idx = state.messages.findIndex(m => m.id === userMsgObj.id);
                if (idx !== -1) {
                    state.messages.splice(idx, 1);
                    saveChatHistory();
                }
            }
            if (botMsgDiv && botMsgDiv.parentNode) {
                botMsgDiv.remove();
                if (state.messages.length > 0 && state.messages[state.messages.length - 1].sender === "bot") {
                    state.messages.pop();
                    saveChatHistory();
                }
            }

            showTyping(false);
            setGeneratingState(false);

            chatInput.value = query;
            autoResizeInput();
            chatInput.focus();
            chatInput.selectionStart = chatInput.selectionEnd = query.length;

            showToast(errorMessage || "⚠️ Не удалось получить ответ. Текст сообщения возвращен в поле ввода — нажмите Enter для повтора.", "warning", 6000);
        }

        try {
            const response = await fetch("/api/chat", {
                method: "POST",
                headers: {
                    "Content-Type": "application/json",
                    "Authorization": `Bearer ${token}`
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
                if (typeof SkyrexAuth !== "undefined" && SkyrexAuth.logout) {
                    SkyrexAuth.logout();
                }
                rollbackUserMessage("🔒 Сессия истекла или требуется авторизация. Текст сохранен — войдите и нажмите Enter.");
                if (typeof SkyrexAuth !== "undefined" && SkyrexAuth.openAuthModal) {
                    SkyrexAuth.openAuthModal();
                }
                return;
            }

            // Handle rate limit (429)
            if (response.status === 429) {
                rollbackUserMessage("⏳ Слишком много запросов. Текст возвращен в поле ввода — подождите немного и нажмите Enter.");
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
                                // Live sync to Rig Visualizer as parts appear in real-time
                                if (window.SkyrexRig && typeof window.SkyrexRig.updateFromAiResponse === "function") {
                                    window.SkyrexRig.updateFromAiResponse(accumulatedText);
                                }
                                if (botContentDiv) {
                                    botContentDiv.innerHTML = parseBotContent(accumulatedText);
                                    if (isAtBottom()) {
                                        scrollChatToBottom();
                                    }
                                }
                            }
                            if (parsed.final) {
                                accumulatedText = parsed.final;
                                if (botContentDiv) {
                                    botContentDiv.innerHTML = parseBotContent(accumulatedText);
                                    if (isAtBottom()) {
                                        scrollChatToBottom();
                                    }
                                }
                                if (window.SkyrexRig && typeof window.SkyrexRig.updateFromAiResponse === "function") {
                                    window.SkyrexRig.updateFromAiResponse(accumulatedText);
                                }
                            }
                        } catch (pe) {
                            if (pe.message && !pe.message.includes("JSON")) {
                                throw pe;
                            }
                        }
                    }
                }

                // Finalize streamed message
                if (isFirstToken || !accumulatedText.trim()) {
                    rollbackUserMessage("⚠️ Ассистент не сформировал ответ. Текст возвращен в поле ввода — нажмите Enter для повтора.");
                    return;
                } else {
                    // Update state with final text
                    const lastBotMsg = state.messages[state.messages.length - 1];
                    if (lastBotMsg && lastBotMsg.sender === "bot") {
                        lastBotMsg.text = accumulatedText;
                        saveChatHistory();
                    }
                    if (window.SkyrexRig && typeof window.SkyrexRig.updateFromAiResponse === "function") {
                        window.SkyrexRig.updateFromAiResponse(accumulatedText);
                    }
                    if (botContentDiv) {
                        botContentDiv.innerHTML = parseBotContent(accumulatedText);
                    }
                }
            } else {
                // B. STANDARD JSON RESPONSE FALLBACK
                const data = await response.json().catch(() => null);
                showTyping(false);
                if (data && data.response) {
                    if (window.SkyrexRig && typeof window.SkyrexRig.updateFromAiResponse === "function") {
                        window.SkyrexRig.updateFromAiResponse(data.response);
                    }
                    appendMessage("bot", data.response);
                } else {
                    rollbackUserMessage("⚠️ Не удалось получить ответ от ассистента. Текст возвращен в поле ввода — нажмите Enter для повтора.");
                    return;
                }
            }
        } catch (err) {
            showTyping(false);
            if (accumulatedText && window.SkyrexRig && typeof window.SkyrexRig.updateFromAiResponse === "function") {
                window.SkyrexRig.updateFromAiResponse(accumulatedText);
            }
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
                rollbackUserMessage("⚠️ Ошибка связи с сервером AI. Текст сообщения возвращен в поле ввода — нажмите Enter для повтора.");
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
                if (window.SkyrexRig && typeof window.SkyrexRig.resetToDefault === "function") {
                    window.SkyrexRig.resetToDefault();
                }
            }
        });
    }

    // 14. Initialize UI & Chat
    loadChatHistory();

    // 15. Listen for authentication state changes
    document.addEventListener("skyrex-auth-changed", (e) => {
        const user = e.detail;
        if (user && chatInput) {
            chatInput.focus();
        }
    });
});
