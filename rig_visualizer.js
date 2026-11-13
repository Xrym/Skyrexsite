/**
 * Skyrex Computers - Interactive PC Build Rig Visualizer
 * Renders an interactive PC chassis schematic with component outlines, live price counters,
 * hover tooltips with direct store links, and real-time synchronization with AI chat responses.
 */

(function () {
    'use strict';

    // 1. Initial Empty Configuration (Shown on first load until user asks for a build in chat)
    const INITIAL_EMPTY_BUILD = {
        total: "?",
        isCustomized: false,
        budget_label: "Ожидание запроса",
        items: {
            cpu: {
                id: "cpu",
                category: "Процессор",
                code: "CPU",
                name: "?",
                price: "?",
                shop: "—",
                url: "",
                tag: "Ожидание подбора",
                icon: "⚡"
            },
            gpu: {
                id: "gpu",
                category: "Видеокарта",
                code: "GPU",
                name: "?",
                price: "?",
                shop: "—",
                url: "",
                tag: "Ожидание подбора",
                icon: "🎮"
            },
            mb: {
                id: "mb",
                category: "Материнская плата",
                code: "MB",
                name: "?",
                price: "?",
                shop: "—",
                url: "",
                tag: "Ожидание подбора",
                icon: "🖲️"
            },
            ram: {
                id: "ram",
                category: "Оперативная память",
                code: "RAM",
                name: "?",
                price: "?",
                shop: "—",
                url: "",
                tag: "Ожидание подбора",
                icon: "🧠"
            },
            ssd: {
                id: "ssd",
                category: "SSD накопитель",
                code: "SSD",
                name: "?",
                price: "?",
                shop: "—",
                url: "",
                tag: "Ожидание подбора",
                icon: "💾"
            },
            cooler: {
                id: "cooler",
                category: "Кулер для процессора",
                code: "COOLER",
                name: "?",
                price: "?",
                shop: "—",
                url: "",
                tag: "Ожидание подбора",
                icon: "❄️"
            },
            psu: {
                id: "psu",
                category: "Блок питания",
                code: "PSU",
                name: "?",
                price: "?",
                shop: "—",
                url: "",
                tag: "Ожидание подбора",
                icon: "🔌"
            },
            case: {
                id: "case",
                category: "Корпус для ПК",
                code: "CASE",
                name: "?",
                price: "?",
                shop: "—",
                url: "",
                tag: "Ожидание подбора",
                icon: "🖥️"
            }
        }
    };

    // Global Visualizer Controller
    const SkyrexRig = {
        state: JSON.parse(JSON.stringify(INITIAL_EMPTY_BUILD)),
        container: null,
        tooltipEl: null,

        init() {
            this.container = document.getElementById("skyrex-pc-visualizer");
            if (!this.container) return;

            // Load saved build from localStorage if user previously customized it
            const saved = localStorage.getItem("skyrex_active_build");
            if (saved) {
                try {
                    const parsed = JSON.parse(saved);
                    // Only restore if it was genuinely parsed from an AI build (not legacy static build)
                    if (parsed && parsed.isCustomized === true && parsed.items && parsed.total !== "85 884") {
                        this.state = parsed;
                    } else {
                        this.state = JSON.parse(JSON.stringify(INITIAL_EMPTY_BUILD));
                        localStorage.removeItem("skyrex_active_build");
                    }
                } catch (e) {
                    this.state = JSON.parse(JSON.stringify(INITIAL_EMPTY_BUILD));
                }
            } else {
                this.state = JSON.parse(JSON.stringify(INITIAL_EMPTY_BUILD));
            }

            this.createTooltip();
            this.render();
            this.bindEvents();

            // Check if chat history already has an existing PC build recommendation
            setTimeout(() => {
                this.checkExistingChatHistory();
            }, 100);
            setTimeout(() => {
                this.checkExistingChatHistory();
            }, 500);
            setTimeout(() => {
                this.checkExistingChatHistory();
            }, 1500);
        },

        createTooltip() {
            let el = document.getElementById("rig-component-tooltip");
            if (!el) {
                el = document.createElement("div");
                el.id = "rig-component-tooltip";
                el.className = "rig-floating-tooltip";
                document.body.appendChild(el);
            }
            this.tooltipEl = el;
        },

        render() {
            if (!this.container) {
                this.container = document.getElementById("skyrex-pc-visualizer");
            }
            if (!this.container) return;

            const items = this.state.items;
            const isCustomized = this.state.isCustomized === true;

            // Compute total display: "?" if uncustomized, or "XX XXX ₽" if customized (never "не число")
            let totalDisplay = "?";
            if (isCustomized) {
                let sum = 0;
                Object.values(items).forEach(itm => {
                    if (itm && itm.price && itm.price !== "?") {
                        const digits = String(itm.price).replace(/\D/g, '');
                        if (digits) {
                            const p = parseInt(digits, 10);
                            if (!isNaN(p) && p > 0) sum += p;
                        }
                    }
                });
                if (sum > 0) {
                    totalDisplay = sum.toLocaleString('ru-RU') + " ₽";
                } else if (this.state.total && this.state.total !== "?") {
                    const rawDigits = String(this.state.total).replace(/\D/g, '');
                    const num = parseInt(rawDigits, 10);
                    if (!isNaN(num) && num > 0) {
                        totalDisplay = num.toLocaleString('ru-RU') + " ₽";
                    }
                }
            }

            const headerTitle = isCustomized ? "Спецификация системы" : "Конфигурация ПК";

            this.container.innerHTML = `
                <div class="pc-rig-card" id="pc-rig-card">
                    <!-- Scanline effect for dynamic updating -->
                    <div class="rig-scan-beam" id="rig-scan-beam"></div>

                    <!-- Rig Card Header -->
                    <div class="pc-rig-header">
                        <div class="pc-rig-header-left">
                            <div class="rig-status-pill">
                                <span class="rig-status-dot"></span>
                                <span class="rig-status-text">AI Live Rig</span>
                            </div>
                            <span class="pc-rig-title">${headerTitle}</span>
                        </div>
                        <div class="pc-rig-header-right">
                            <span class="rig-total-label">Итого сборка:</span>
                            <span class="rig-total-val" id="rig-total-counter">${totalDisplay}</span>
                        </div>
                    </div>

                    <!-- Rig Visual Stage: Interactive Blueprint Schematic + HUD -->
                    <div class="pc-rig-stage-wrapper">
                        <!-- Left: SVG PC Chassis Blueprint with Interactive Component Outlines -->
                        <div class="pc-chassis-stage" id="pc-chassis-stage">
                            ${this.getChassisSvg()}
                        </div>

                        <!-- Right: Interactive Component Cards Grid -->
                        <div class="pc-components-list" id="pc-components-list">
                            ${this.renderComponentCards(items)}
                        </div>
                    </div>

                    <!-- Rig Card Footer: Clean subtle hint (without copy button) -->
                    <div class="pc-rig-footer">
                        <div class="pc-rig-footer-info">
                            <span class="rig-info-icon">💡</span>
                            <span>Наведите на деталь для подсветки контура или кликните для перехода к товару.</span>
                        </div>
                    </div>
                </div>
            `;

            this.bindInteractiveHotspots();
        },

        getChassisSvg() {
            return `
            <svg class="pc-chassis-svg" viewBox="0 0 460 540" xmlns="http://www.w3.org/2000/svg">
                <defs>
                    <!-- Cyber Gradients -->
                    <linearGradient id="gradPcb" x1="0%" y1="0%" x2="100%" y2="100%">
                        <stop offset="0%" stop-color="#0f111a" />
                        <stop offset="100%" stop-color="#181726" />
                    </linearGradient>
                    <linearGradient id="gradGpu" x1="0%" y1="0%" x2="100%" y2="0%">
                        <stop offset="0%" stop-color="#1e1b2e" />
                        <stop offset="50%" stop-color="#2d264a" />
                        <stop offset="100%" stop-color="#1e1b2e" />
                    </linearGradient>
                    <linearGradient id="gradCooler" x1="0%" y1="0%" x2="0%" y2="100%">
                        <stop offset="0%" stop-color="#241e3a" />
                        <stop offset="100%" stop-color="#131120" />
                    </linearGradient>
                    <linearGradient id="gradFanRgb" x1="0%" y1="0%" x2="100%" y2="100%">
                        <stop offset="0%" stop-color="#06b6d4" />
                        <stop offset="50%" stop-color="#8b5cf6" />
                        <stop offset="100%" stop-color="#d946ef" />
                    </linearGradient>
                    <pattern id="pcbGrid" width="20" height="20" patternUnits="userSpaceOnUse">
                        <path d="M 20 0 L 0 0 0 20" fill="none" stroke="rgba(139, 92, 246, 0.08)" stroke-width="1"/>
                        <circle cx="20" cy="20" r="1.5" fill="rgba(6, 182, 212, 0.15)"/>
                    </pattern>
                </defs>

                <!-- 1. CHASSIS OUTER FRAME (Case) - NO SCREW CIRCLES -->
                <g class="rig-part" id="part-case" data-part="case">
                    <!-- Case Outer Body -->
                    <rect x="20" y="20" width="420" height="500" rx="20" class="rig-case-outer" />
                    <!-- Tempered Glass Window Inner Frame -->
                    <rect x="35" y="35" width="390" height="470" rx="14" class="rig-case-glass" />
                    <!-- Chassis Feet -->
                    <rect x="50" y="520" width="60" height="12" rx="4" fill="#1e1b2e" stroke="#8b5cf6" stroke-width="1.5"/>
                    <rect x="350" y="520" width="60" height="12" rx="4" fill="#1e1b2e" stroke="#8b5cf6" stroke-width="1.5"/>
                    <!-- Power Button & Top I/O -->
                    <circle cx="65" cy="28" r="4" fill="#06b6d4"/>
                    <rect x="80" y="26" width="8" height="4" rx="1" fill="#64748b"/>
                    <rect x="94" y="26" width="8" height="4" rx="1" fill="#64748b"/>
                    <rect x="108" y="26" width="12" height="4" rx="1" fill="#8b5cf6"/>
                    <!-- Front Ventilation Slits -->
                    <line x1="415" y1="50" x2="415" y2="490" stroke="rgba(6, 182, 212, 0.3)" stroke-width="3" stroke-dasharray="6 4" />
                </g>

                <!-- 2. MOTHERBOARD (PCB Tray) - NO TEXT LABELS -->
                <g class="rig-part" id="part-mb" data-part="mb">
                    <!-- Motherboard Board Outline -->
                    <rect x="55" y="80" width="280" height="315" rx="8" fill="url(#gradPcb)" class="rig-mb-board" />
                    <rect x="55" y="80" width="280" height="315" rx="8" fill="url(#pcbGrid)" />
                    <!-- Circuit Trace Lines -->
                    <path d="M 65 100 L 110 100 L 125 120" fill="none" stroke="rgba(6, 182, 212, 0.4)" stroke-width="1.5"/>
                    <path d="M 65 150 L 100 150 L 115 170" fill="none" stroke="rgba(139, 92, 246, 0.4)" stroke-width="1.5"/>
                    <path d="M 280 110 L 315 110 L 315 170" fill="none" stroke="rgba(6, 182, 212, 0.4)" stroke-width="1.5"/>
                    <!-- I/O Armor Shield (Top-Left) -->
                    <rect x="58" y="83" width="36" height="95" rx="4" class="rig-mb-shield" fill="#171926" stroke="#334155" stroke-width="1.5"/>
                    <line x1="66" y1="95" x2="86" y2="95" stroke="#06b6d4" stroke-width="2"/>
                    <line x1="66" y1="105" x2="86" y2="105" stroke="#334155" stroke-width="1.5"/>
                    <line x1="66" y1="115" x2="86" y2="115" stroke="#334155" stroke-width="1.5"/>
                    <!-- PCIe Expansion Slots -->
                    <rect x="95" y="335" width="220" height="8" rx="2" fill="#13111c" stroke="#64748b" stroke-width="1"/>
                    <rect x="95" y="375" width="160" height="6" rx="2" fill="#13111c" stroke="#475569" stroke-width="1"/>
                </g>

                <!-- 3. CPU COOLER (Top Liquid Radiator + Dual ARGB Fans + Tubes) -->
                <!-- Positioned at top ceiling so it DOES NOT overlap the CPU socket -->
                <g class="rig-part" id="part-cooler" data-part="cooler">
                    <!-- Top Radiator Body -->
                    <rect x="85" y="42" width="185" height="32" rx="5" class="rig-cooler-body" />
                    <!-- Radiator Fin Matrix Lines -->
                    <line x1="95" y1="46" x2="95" y2="70" stroke="rgba(255,255,255,0.12)" stroke-width="1"/>
                    <line x1="105" y1="46" x2="105" y2="70" stroke="rgba(255,255,255,0.12)" stroke-width="1"/>
                    <line x1="115" y1="46" x2="115" y2="70" stroke="rgba(255,255,255,0.12)" stroke-width="1"/>
                    <line x1="185" y1="46" x2="185" y2="70" stroke="rgba(255,255,255,0.12)" stroke-width="1"/>
                    <line x1="255" y1="46" x2="255" y2="70" stroke="rgba(255,255,255,0.12)" stroke-width="1"/>
                    <!-- Radiator Fan 1 (Left) -->
                    <circle cx="140" cy="58" r="14" class="rig-fan-outer" />
                    <circle cx="140" cy="58" r="5" fill="#0f111a" stroke="#06b6d4" stroke-width="1.5"/>
                    <circle cx="140" cy="58" r="11" class="rig-fan-ring" fill="none" stroke="#06b6d4" stroke-width="1.5"/>
                    <!-- Radiator Fan 2 (Right) -->
                    <circle cx="215" cy="58" r="14" class="rig-fan-outer" />
                    <circle cx="215" cy="58" r="5" fill="#0f111a" stroke="#8b5cf6" stroke-width="1.5"/>
                    <circle cx="215" cy="58" r="11" class="rig-fan-ring" fill="none" stroke="#8b5cf6" stroke-width="1.5"/>
                    <!-- Braided Liquid Cooling Tubes connecting Radiator to CPU -->
                    <path d="M 130 74 C 130 90 140 94 150 102" fill="none" stroke="#06b6d4" stroke-width="2.5" stroke-linecap="round"/>
                    <path d="M 148 74 C 148 88 156 92 166 102" fill="none" stroke="#6366f1" stroke-width="2.5" stroke-linecap="round"/>
                </g>

                <!-- 4. CPU PROCESSOR (Prominent LGA/AM5 Socket + Metallic IHS Chip) -->
                <!-- Fully visible, unobstructed, and easy to hover! -->
                <g class="rig-part" id="part-cpu" data-part="cpu">
                    <!-- LGA / AM5 Socket Retention Frame -->
                    <rect x="135" y="102" width="76" height="76" rx="8" class="rig-cpu-frame" />
                    <!-- Metal Socket Latch Lever on Right -->
                    <rect x="212" y="106" width="4" height="68" rx="2" fill="#64748b" stroke="#334155" stroke-width="1"/>
                    <circle cx="214" cy="172" r="3" fill="#94a3b8"/>
                    <!-- CPU Integrated Heat Spreader (IHS) -->
                    <rect x="144" y="111" width="58" height="58" rx="4" class="rig-cpu-ihs" />
                    <!-- Silicon Die Core Accent -->
                    <rect x="156" y="123" width="34" height="34" rx="3" class="rig-cpu-core" />
                    <line x1="160" y1="140" x2="186" y2="140" stroke="rgba(6, 182, 212, 0.7)" stroke-width="1.5"/>
                    <line x1="173" y1="127" x2="173" y2="153" stroke="rgba(139, 92, 246, 0.7)" stroke-width="1.5"/>
                    <!-- Gold Triangle Pin 1 Indicator -->
                    <polygon points="146,113 153,113 146,120" fill="#eab308" />
                    <!-- Corner Socket Screw Studs -->
                    <circle cx="140" cy="107" r="1.5" fill="#38bdf8"/>
                    <circle cx="206" cy="107" r="1.5" fill="#38bdf8"/>
                    <circle cx="140" cy="173" r="1.5" fill="#38bdf8"/>
                    <circle cx="206" cy="173" r="1.5" fill="#38bdf8"/>
                </g>

                <!-- 5. RAM (Memory Modules) -->
                <g class="rig-part" id="part-ram" data-part="ram">
                    <!-- Slot 1 -->
                    <rect x="245" y="95" width="10" height="110" rx="3" class="rig-ram-stick" />
                    <rect x="246" y="96" width="8" height="20" rx="2" fill="url(#gradFanRgb)" />
                    <!-- Slot 2 -->
                    <rect x="261" y="95" width="10" height="110" rx="3" class="rig-ram-stick" />
                    <rect x="262" y="96" width="8" height="20" rx="2" fill="url(#gradFanRgb)" />
                    <!-- Slot 3 & 4 (dimmed) -->
                    <rect x="277" y="97" width="8" height="106" rx="2" fill="#1e1b2e" stroke="rgba(255,255,255,0.1)"/>
                    <rect x="291" y="97" width="8" height="106" rx="2" fill="#1e1b2e" stroke="rgba(255,255,255,0.1)"/>
                </g>

                <!-- 6. SSD M.2 NVMe Slot with Armor Heatsink - NO TEXT, CRISP ALIGNMENT -->
                <g class="rig-part" id="part-ssd" data-part="ssd">
                    <!-- M.2 Slot Connector (Left) -->
                    <rect x="115" y="195" width="8" height="20" rx="1" fill="#0f172a" stroke="#475569" stroke-width="1"/>
                    <!-- M.2 2280 PCB & Armor Heatsink -->
                    <rect x="123" y="195" width="106" height="20" rx="3" class="rig-ssd-shield" />
                    <!-- Thermal Armor Grooves -->
                    <line x1="130" y1="201" x2="216" y2="201" stroke="rgba(6, 182, 212, 0.7)" stroke-width="1.5"/>
                    <line x1="130" y1="209" x2="216" y2="209" stroke="rgba(139, 92, 246, 0.5)" stroke-width="1.5"/>
                    <!-- Activity Indicator Dot -->
                    <circle cx="221" cy="205" r="2" fill="#06b6d4" />
                </g>

                <!-- 7. GPU (Graphics Card - Dual Slot) - NO TEXT LABELS -->
                <g class="rig-part" id="part-gpu" data-part="gpu">
                    <!-- GPU Main Shroud -->
                    <rect x="75" y="240" width="310" height="82" rx="10" fill="url(#gradGpu)" class="rig-gpu-body" />
                    <!-- GPU Backplate Top Line -->
                    <rect x="75" y="238" width="310" height="5" rx="2" fill="#8b5cf6" />
                    <!-- GPU Fan 1 -->
                    <circle cx="160" cy="281" r="27" class="rig-gpu-fan" />
                    <circle cx="160" cy="281" r="9" fill="#13111c" stroke="#06b6d4" stroke-width="2"/>
                    <!-- GPU Fan 2 -->
                    <circle cx="250" cy="281" r="27" class="rig-gpu-fan" />
                    <circle cx="250" cy="281" r="9" fill="#13111c" stroke="#8b5cf6" stroke-width="2"/>
                    <!-- GPU Exhaust Vent Grid on Right -->
                    <rect x="300" y="255" width="65" height="52" rx="6" fill="#13111c" stroke="rgba(255,255,255,0.1)" stroke-width="1"/>
                    <line x1="310" y1="265" x2="355" y2="265" stroke="#475569" stroke-width="1"/>
                    <line x1="310" y1="275" x2="355" y2="275" stroke="#475569" stroke-width="1"/>
                    <line x1="310" y1="285" x2="355" y2="285" stroke="#475569" stroke-width="1"/>
                    <line x1="310" y1="295" x2="355" y2="295" stroke="#475569" stroke-width="1"/>
                    <!-- GPU PCIe Power Cable Routing -->
                    <rect x="330" y="228" width="22" height="12" rx="2" fill="#0f172a" stroke="#06b6d4" stroke-width="1"/>
                    <path d="M 335 228 C 335 210 370 210 370 190" fill="none" stroke="#334155" stroke-width="3"/>
                    <path d="M 345 228 C 345 210 380 210 380 190" fill="none" stroke="#334155" stroke-width="3"/>
                    <!-- Geometric RGB Accent Light Bar (NO TEXT) -->
                    <rect x="90" y="278" width="35" height="6" rx="2" fill="#06b6d4"/>
                    <line x1="90" y1="290" x2="120" y2="290" stroke="#8b5cf6" stroke-width="2"/>
                </g>

                <!-- 8. PSU & BOTTOM SHROUD (Power Supply Unit) - NO BRAND TEXT -->
                <g class="rig-part" id="part-psu" data-part="psu">
                    <!-- Lower PSU Chamber Shroud -->
                    <rect x="35" y="415" width="390" height="90" rx="10" class="rig-psu-shroud" />
                    <!-- PSU Cut-out Window showing PSU Hardware (NO TEXT) -->
                    <rect x="55" y="430" width="160" height="60" rx="6" class="rig-psu-unit" />
                    <!-- AC Power Inlet Socket outline -->
                    <rect x="68" y="445" width="22" height="30" rx="3" fill="#1e2235" stroke="#475569" stroke-width="1.5"/>
                    <circle cx="79" cy="453" r="2" fill="#334155"/>
                    <circle cx="74" cy="463" r="2" fill="#334155"/>
                    <circle cx="84" cy="463" r="2" fill="#334155"/>
                    <!-- Power Switch Rocker -->
                    <rect x="98" y="450" width="14" height="20" rx="2" fill="#0f111a" stroke="#06b6d4" stroke-width="1.5"/>
                    <line x1="105" y1="454" x2="105" y2="466" stroke="#06b6d4" stroke-width="1.5"/>
                    <!-- Hex Ventilation Honeycomb Matrix -->
                    <path d="M 125 445 L 195 445 M 125 455 L 195 455 M 125 465 L 195 465 M 125 475 L 195 475" stroke="#334155" stroke-width="1.5" stroke-dasharray="3 3"/>
                    <!-- Cable Management Grommets -->
                    <ellipse cx="260" cy="425" rx="25" ry="8" fill="#13111c" stroke="#334155" stroke-width="1.5"/>
                    <ellipse cx="340" cy="425" rx="20" ry="8" fill="#13111c" stroke="#334155" stroke-width="1.5"/>
                    <!-- Bottom Intake Grill Pattern -->
                    <line x1="280" y1="445" x2="385" y2="445" stroke="#334155" stroke-width="2"/>
                    <line x1="280" y1="460" x2="385" y2="460" stroke="#334155" stroke-width="2"/>
                    <line x1="280" y1="475" x2="385" y2="475" stroke="#334155" stroke-width="2"/>
                </g>
            </svg>
            `;
        },

        renderComponentCards(items) {
            const order = ['cpu', 'gpu', 'mb', 'ram', 'ssd', 'cooler', 'psu', 'case'];
            let html = '';

            order.forEach(key => {
                const item = items[key];
                if (!item) return;

                const isPlaceholder = !this.state.isCustomized || item.name === "?" || !item.name;

                let shopBadgeClass = 'badge-empty';
                let shopText = '—';
                if (!isPlaceholder && item.shop) {
                    if (item.shop.includes('Авито')) {
                        shopBadgeClass = 'badge-avito';
                        shopText = item.shop;
                    } else if (item.shop.includes('Wildberries')) {
                        shopBadgeClass = 'badge-wb';
                        shopText = item.shop;
                    } else if (item.shop.includes('ОнлайнТрейд')) {
                        shopBadgeClass = 'badge-ot';
                        shopText = item.shop;
                    }
                }

                const displayName = isPlaceholder ? '?' : item.name;
                const displayPrice = isPlaceholder ? '?' : item.price;
                const displayTag = isPlaceholder ? 'Ожидание параметров' : (item.tag || '');

                html += `
                    <div class="pc-part-card ${isPlaceholder ? 'part-card-placeholder' : ''}" id="card-${key}" data-part="${key}">
                        <div class="part-card-left">
                            <span class="part-card-icon">${item.icon || '⚡'}</span>
                            <div class="part-card-details">
                                <div class="part-card-meta">
                                    <span class="part-category-tag">${item.category}</span>
                                    <span class="part-shop-badge ${shopBadgeClass}">${shopText}</span>
                                </div>
                                <span class="part-card-name" title="${displayName}">${displayName}</span>
                                ${displayTag ? `<span class="part-spec-tag">${displayTag}</span>` : ''}
                            </div>
                        </div>
                        <div class="part-card-right">
                            <span class="part-card-price">${displayPrice}</span>
                            ${!isPlaceholder && item.url ? `
                                <a href="${item.url}" target="_blank" rel="noopener noreferrer" class="part-card-link-btn" title="Перейти к товару">
                                    <svg xmlns="http://www.w3.org/2000/svg" width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round">
                                        <line x1="7" y1="17" x2="17" y2="7"></line>
                                        <polyline points="7 7 17 7 17 17"></polyline>
                                    </svg>
                                </a>
                            ` : ''}
                        </div>
                    </div>
                `;
            });

            return html;
        },

        bindEvents() {
            // No extra buttons in footer to bind
        },

        bindInteractiveHotspots() {
            const parts = ['cpu', 'gpu', 'mb', 'ram', 'ssd', 'cooler', 'psu', 'case'];

            parts.forEach(partKey => {
                const svgPart = document.getElementById(`part-${partKey}`);
                const cardEl = document.getElementById(`card-${partKey}`);

                // SVG Hover & Click
                if (svgPart) {
                    svgPart.addEventListener("mouseenter", (e) => {
                        this.highlightPart(partKey, true);
                        this.showTooltip(partKey, e);
                    });
                    svgPart.addEventListener("mousemove", (e) => {
                        this.moveTooltip(e);
                    });
                    svgPart.addEventListener("mouseleave", () => {
                        this.highlightPart(partKey, false);
                        this.hideTooltip();
                    });
                    svgPart.addEventListener("click", () => {
                        const item = this.state.items[partKey];
                        if (item && item.url && this.state.isCustomized && item.name !== "?") {
                            window.open(item.url, "_blank", "noopener,noreferrer");
                        }
                    });
                }

                // Card Hover & Click
                if (cardEl) {
                    cardEl.addEventListener("mouseenter", () => {
                        this.highlightPart(partKey, true);
                    });
                    cardEl.addEventListener("mouseleave", () => {
                        this.highlightPart(partKey, false);
                    });
                    cardEl.addEventListener("click", (e) => {
                        if (e.target.closest("a")) return;
                        const item = this.state.items[partKey];
                        if (item && item.url && this.state.isCustomized && item.name !== "?") {
                            window.open(item.url, "_blank", "noopener,noreferrer");
                        }
                    });
                }
            });
        },

        highlightPart(partKey, isHovered) {
            const svgPart = document.getElementById(`part-${partKey}`);
            const cardEl = document.getElementById(`card-${partKey}`);

            if (isHovered) {
                if (svgPart) svgPart.classList.add("rig-part-active");
                if (cardEl) cardEl.classList.add("part-card-active");
            } else {
                if (svgPart) svgPart.classList.remove("rig-part-active");
                if (cardEl) cardEl.classList.remove("part-card-active");
            }
        },

        showTooltip(partKey, e) {
            if (!this.tooltipEl) return;
            const item = this.state.items[partKey];
            if (!item) return;

            const isPlaceholder = !this.state.isCustomized || item.name === "?" || !item.name;

            if (isPlaceholder) {
                this.tooltipEl.innerHTML = `
                    <div class="tooltip-header">
                        <span class="tooltip-cat">${item.category}</span>
                        <span class="tooltip-shop badge-empty">Ожидание</span>
                    </div>
                    <div class="tooltip-name">Компонент еще не подобран</div>
                    <div class="tooltip-footer">
                        <span class="tooltip-price">Задайте бюджет в чате</span>
                    </div>
                `;
            } else {
                const shopColor = item.shop.includes('Авито') ? '#3b82f6' :
                                 (item.shop.includes('Wildberries') ? '#ec4899' : '#06b6d4');

                this.tooltipEl.innerHTML = `
                    <div class="tooltip-header">
                        <span class="tooltip-cat">${item.category}</span>
                        <span class="tooltip-shop" style="color: ${shopColor}; border-color: ${shopColor};">${item.shop}</span>
                    </div>
                    <div class="tooltip-name">${item.name}</div>
                    <div class="tooltip-footer">
                        <span class="tooltip-price">${item.price}</span>
                        ${item.url ? `
                            <a href="${item.url}" target="_blank" rel="noopener noreferrer" class="tooltip-btn">
                                Перейти к товару ↗
                            </a>
                        ` : ''}
                    </div>
                `;
            }

            this.tooltipEl.style.display = "block";
            this.moveTooltip(e);
        },

        moveTooltip(e) {
            if (!this.tooltipEl || this.tooltipEl.style.display !== "block") return;
            const x = e.pageX + 15;
            const y = e.pageY - 20;
            this.tooltipEl.style.left = `${x}px`;
            this.tooltipEl.style.top = `${y}px`;
        },

        hideTooltip() {
            if (this.tooltipEl) {
                this.tooltipEl.style.display = "none";
            }
        },

        resetToDefault() {
            localStorage.removeItem("skyrex_active_build");
            this.state = JSON.parse(JSON.stringify(INITIAL_EMPTY_BUILD));
            this.render();
        },

        /**
         * Parses LLM response text, updates rig state, and plays visual scan effect
         */
        updateFromAiResponse(responseText) {
            if (!responseText || typeof responseText !== "string") return;

            if (!this.container) {
                this.container = document.getElementById("skyrex-pc-visualizer");
            }

            // Pre-normalize text: strip list tags and ensure numbered items start on fresh line even if glued
            let norm = responseText.replace(/<\/?(?:ul|ol|li)[^>]*>/gi, "\n");
            norm = norm.replace(/<br\s*\/?>/gi, "\n");
            norm = norm.replace(/([^\n>])\s*(\b\d+[\.\)]\s*(?:<b>)?[А-ЯA-Z])/g, "$1\n$2");

            const lines = norm.split("\n");
            const newItems = {};
            let foundCount = 0;

            const catPatterns = [
                { key: 'cooler', regex: /(?:кулер|охлажд|сжо|cooler)/i },
                { key: 'cpu', regex: /(?:процессор|cpu)/i },
                { key: 'mb', regex: /(?:материнск|плата|motherboard)/i },
                { key: 'ram', regex: /(?:оперативн|памят|ram)/i },
                { key: 'gpu', regex: /(?:видеокарт|gpu)/i },
                { key: 'ssd', regex: /(?:накопител|ssd|m\.2|nvme)/i },
                { key: 'psu', regex: /(?:блок питания|psu)/i },
                { key: 'case', regex: /(?:корпус|case)/i },
            ];

            for (const line of lines) {
                const lineClean = line.trim();
                if (!lineClean) continue;

                // Check numbered list format: e.g. "1. Процессор..." or "2) Видеокарта..."
                for (const cat of catPatterns) {
                    if (new RegExp(`^\\s*\\d+[\\.\\)]\\s*.*?${cat.regex.source}`, 'i').test(lineClean)) {
                        // Extract Link & Name (support both HTML <a> and Markdown [Title](URL))
                        let url = "";
                        let name = "";
                        const mLink = lineClean.match(/<a\s+href=['"]([^'"]+)['"][^>]*>(.*?)<\/a>/i);
                        const mMd = lineClean.match(/\[([^\]]+)\]\((https?:\/\/[^\s\)]+)\)/i);

                        if (mLink) {
                            url = mLink[1];
                            name = mLink[2].replace(/<[^>]+>/g, '').trim();
                        } else if (mMd) {
                            name = mMd[1].replace(/<[^>]+>/g, '').trim();
                            url = mMd[2].trim();
                        } else {
                            const mName = lineClean.match(/:\s*(?:<\/b>)?\s*(.*?)(?:—|-|\d+\s*(?:руб|₽))/i);
                            name = mName ? mName[1].replace(/<[^>]+>/g, '').trim() : '';
                        }

                        // Extract Price
                        const mPrice = lineClean.match(/(?:—|-)?\s*([\d\s\xa0,.]+)\s*(?:руб|₽)/i);
                        let price = "";
                        if (mPrice) {
                            const rawP = mPrice[1].replace(/[\s\xa0]/g, '').replace(/,/g, '');
                            const numP = parseInt(rawP, 10);
                            price = !isNaN(numP) ? numP.toLocaleString('ru-RU') + " ₽" : mPrice[1].trim() + " ₽";
                        }

                        // Detect Shop
                        let shop = "Маркетплейс";
                        if (url.includes("avito.ru")) shop = "Авито (Б/У)";
                        else if (url.includes("wildberries.ru")) shop = "Wildberries";
                        else if (url.includes("onlinetrade.ru")) shop = "ОнлайнТрейд";

                        const currentPart = this.state.items[cat.key] || {};
                        newItems[cat.key] = {
                            id: cat.key,
                            category: currentPart.category || cat.key.toUpperCase(),
                            code: currentPart.code || cat.key.toUpperCase(),
                            name: name || currentPart.name,
                            price: price || currentPart.price,
                            shop: shop,
                            url: url || currentPart.url,
                            tag: currentPart.tag || "",
                            icon: currentPart.icon || "⚡"
                        };
                        foundCount++;
                        break;
                    }
                }
            }

            // Extract Total Price if present or calculate (pick the final match in case of recalculation)
            const allTotals = [...responseText.matchAll(/(?:суммарная стоимость|итого|стоимость сборки).*?([\d\s\xa0]{4,})\s*(?:руб|₽)/gi)];
            let total = allTotals.length > 0 ? allTotals[allTotals.length - 1][1].replace(/[\s\xa0]/g, '') : null;

            // If at least 1 component was parsed, update the rig dynamically!
            if (foundCount >= 1) {
                this.state.isCustomized = true;

                // Merge with existing state for any unmentioned parts
                Object.keys(newItems).forEach(k => {
                    this.state.items[k] = newItems[k];
                });

                // Calculate total sum directly from components
                let sum = 0;
                Object.values(this.state.items).forEach(itm => {
                    if (itm.price && itm.price !== "?") {
                        const digits = String(itm.price).replace(/\D/g, '');
                        if (digits) {
                            const p = parseInt(digits, 10);
                            if (!isNaN(p) && p > 0) sum += p;
                        }
                    }
                });

                if (sum > 0) {
                    this.state.total = String(sum);
                } else if (total) {
                    this.state.total = total;
                }

                // Save to localStorage
                localStorage.setItem("skyrex_active_build", JSON.stringify(this.state));

                // Trigger Scanline Cyber Animation
                this.playScanAnimation();

                // Re-render UI
                this.render();
            }
        },

        playScanAnimation() {
            const card = document.getElementById("pc-rig-card");
            if (!card) return;
            card.classList.remove("rig-updating");
            void card.offsetWidth; // trigger reflow
            card.classList.add("rig-updating");
            setTimeout(() => {
                card.classList.remove("rig-updating");
            }, 1800);
        },

        checkExistingChatHistory() {
            try {
                const savedHistory = localStorage.getItem("skyrex_chat_history");
                if (savedHistory) {
                    const messages = JSON.parse(savedHistory);
                    if (Array.isArray(messages)) {
                        // Scan from newest to oldest for the latest build recommendation
                        for (let i = messages.length - 1; i >= 0; i--) {
                            const msg = messages[i];
                            if (msg.sender === "bot" && (msg.text.includes("Процессор") || msg.text.includes("Видеокарта"))) {
                                this.updateFromAiResponse(msg.text);
                                break;
                            }
                        }
                    }
                }
            } catch (e) {
                console.warn("Could not check chat history for rig sync", e);
            }
        }
    };

    // Export to window
    window.SkyrexRig = SkyrexRig;

    // Auto-init on DOMContentLoaded
    document.addEventListener("DOMContentLoaded", () => {
        SkyrexRig.init();
    });

})();
