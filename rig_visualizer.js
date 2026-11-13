/**
 * Skyrex Computers - Interactive PC Build Rig Visualizer
 * Renders an interactive PC chassis schematic with component outlines, live price counters,
 * hover tooltips with direct store links, and real-time synchronization with AI chat responses.
 */

(function () {
    'use strict';

    // 1. Default Balanced Configuration (Shown on first load before user chat)
    const DEFAULT_BUILD = {
        total: "85 884",
        budget_label: "Сбалансированная сборка",
        items: {
            cpu: {
                id: "cpu",
                category: "Процессор",
                code: "CPU",
                name: "AMD Ryzen 5 7500F OEM",
                price: "11 700 ₽",
                shop: "Авито (Б/У)",
                url: "https://www.avito.ru/all?q=AMD+Ryzen+5+7500F",
                tag: "AM5 • 6 ядер / 12 потоков • DDR5",
                icon: "⚡"
            },
            mb: {
                id: "mb",
                category: "Материнская плата",
                code: "MB",
                name: "Gigabyte B650M GAMING WIFI",
                price: "9 142 ₽",
                shop: "Wildberries",
                url: "https://www.wildberries.ru/catalog/562018817/detail.aspx",
                tag: "Socket AM5 • DDR5 • Wi-Fi 6",
                icon: "🖲️"
            },
            cooler: {
                id: "cooler",
                category: "Кулер для процессора",
                code: "COOLER",
                name: "ID-COOLING SE-224-XTS Black",
                price: "1 950 ₽",
                shop: "ОнлайнТрейд",
                url: "https://www.onlinetrade.ru/catalogue/kulery_dlya_protsessorov-c1492/id_cooling/kuler_dlya_protsessora_id_cooling_se_224_xts_black-3351230.html",
                tag: "180W TDP • 4 трубки • 120мм PWM",
                icon: "❄️"
            },
            ram: {
                id: "ram",
                category: "Оперативная память",
                code: "RAM",
                name: "DDR5 16GB 5600MHz GUDGA",
                price: "18 003 ₽",
                shop: "Wildberries",
                url: "https://www.wildberries.ru/catalog/1122606326/detail.aspx",
                tag: "16GB DDR5 • 5600MHz • XMP",
                icon: "🧠"
            },
            gpu: {
                id: "gpu",
                category: "Видеокарта",
                code: "GPU",
                name: "Palit GeForce RTX 3060 12GB Dual",
                price: "30 000 ₽",
                shop: "Авито (Б/У)",
                url: "https://www.avito.ru/all?q=RTX+3060+12GB",
                tag: "12GB GDDR6 • DLSS • Ray Tracing",
                icon: "🎮"
            },
            ssd: {
                id: "ssd",
                category: "SSD накопитель",
                code: "SSD",
                name: "SSD M.2 NVMe 1TB PCIe",
                price: "3 990 ₽",
                shop: "Авито (Б/У)",
                url: "https://www.avito.ru/all?q=SSD+M.2+NVMe+1TB",
                tag: "1000 ГБ • NVMe M.2 2280",
                icon: "💾"
            },
            psu: {
                id: "psu",
                category: "Блок питания",
                code: "PSU",
                name: "1STPLAYER NGDP, 750W, 80+ Gold, ATX 3.1",
                price: "8 099 ₽",
                shop: "ОнлайнТрейд",
                url: "https://www.onlinetrade.ru/catalogue/bloki_pitaniya_dlya_kompyutera-c339/1stplayer/blok_pitaniya_1stplayer_ngdp_750w_80_gold_atx_3.1_ha_750ba4-4048378.html",
                tag: "750W • 80+ Gold • ATX 3.1 / PCIe 5.1",
                icon: "🔌"
            },
            case: {
                id: "case",
                category: "Корпус для ПК",
                code: "CASE",
                name: "Powercase Mistral Micro Z3B Mesh",
                price: "3 000 ₽",
                shop: "ОнлайнТрейд",
                url: "https://www.onlinetrade.ru/catalogue/kompyuternye_korpusa-c1323/",
                tag: "Закаленное стекло • 3x ARGB кулера",
                icon: "🖥️"
            }
        }
    };

    // Global Visualizer Controller
    const SkyrexRig = {
        state: JSON.parse(JSON.stringify(DEFAULT_BUILD)),
        container: null,
        tooltipEl: null,

        init() {
            this.container = document.getElementById("skyrex-pc-visualizer");
            if (!this.container) return;

            // Load saved build from localStorage if present
            const saved = localStorage.getItem("skyrex_active_build");
            if (saved) {
                try {
                    const parsed = JSON.parse(saved);
                    if (parsed && parsed.items) {
                        this.state = parsed;
                    }
                } catch (e) {
                    console.warn("Failed to load saved rig state", e);
                }
            }

            this.createTooltip();
            this.render();
            this.bindEvents();

            // Try reading any already existing build from chat history
            setTimeout(() => {
                this.checkExistingChatHistory();
            }, 500);
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
            if (!this.container) return;

            const items = this.state.items;
            const totalDisplay = this.state.total ? Number(this.state.total).toLocaleString('ru-RU') + " ₽" : "85 884 ₽";

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
                            <span class="pc-rig-title">Спецификация системы</span>
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

                    <!-- Rig Card Footer: Quick Actions -->
                    <div class="pc-rig-footer">
                        <div class="pc-rig-footer-info">
                            <span class="rig-info-icon">💡</span>
                            <span>Наведите на компонент для подсветки контура или кликните для перехода к товару.</span>
                        </div>
                        <button class="rig-copy-spec-btn" id="rig-copy-spec-btn" title="Скопировать список комплектующих">
                            <svg xmlns="http://www.w3.org/2000/svg" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                                <rect x="9" y="9" width="13" height="13" rx="2" ry="2"></rect>
                                <path d="M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1"></path>
                            </svg>
                            <span>Скопировать</span>
                        </button>
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
                    <filter id="neonGlow" x="-30%" y="-30%" width="160%" height="160%">
                        <feGaussianBlur stdDeviation="5" result="blur" />
                        <feMerge>
                            <feMergeNode in="blur" />
                            <feMergeNode in="SourceGraphic" />
                        </feMerge>
                    </filter>
                    <pattern id="pcbGrid" width="20" height="20" patternUnits="userSpaceOnUse">
                        <path d="M 20 0 L 0 0 0 20" fill="none" stroke="rgba(139, 92, 246, 0.08)" stroke-width="1"/>
                        <circle cx="20" cy="20" r="1.5" fill="rgba(6, 182, 212, 0.15)"/>
                    </pattern>
                </defs>

                <!-- 1. CHASSIS OUTER FRAME (Case) -->
                <g class="rig-part" id="part-case" data-part="case">
                    <!-- Case Outer Body -->
                    <rect x="20" y="20" width="420" height="500" rx="20" class="rig-case-outer" />
                    <!-- Tempered Glass Window Inner Frame -->
                    <rect x="35" y="35" width="390" height="470" rx="14" class="rig-case-glass" />
                    <!-- Chassis Feet -->
                    <rect x="50" y="520" width="60" height="12" rx="4" fill="#1e1b2e" stroke="#8b5cf6" stroke-width="1.5"/>
                    <rect x="350" y="520" width="60" height="12" rx="4" fill="#1e1b2e" stroke="#8b5cf6" stroke-width="1.5"/>
                    <!-- Power Button & Top I/O -->
                    <circle cx="65" cy="28" r="4" fill="#06b6d4" filter="url(#neonGlow)"/>
                    <rect x="80" y="26" width="8" height="4" rx="1" fill="#64748b"/>
                    <rect x="94" y="26" width="8" height="4" rx="1" fill="#64748b"/>
                    <rect x="108" y="26" width="12" height="4" rx="1" fill="#8b5cf6"/>
                    <!-- Case Front Intake Mesh Indicator -->
                    <line x1="415" y1="50" x2="415" y2="490" stroke="rgba(6, 182, 212, 0.3)" stroke-width="4" stroke-dasharray="6 4" />
                </g>

                <!-- 2. MOTHERBOARD (PCB Tray) -->
                <g class="rig-part" id="part-mb" data-part="mb">
                    <!-- Motherboard Board Outline -->
                    <rect x="55" y="55" width="280" height="340" rx="8" fill="url(#gradPcb)" class="rig-mb-board" />
                    <rect x="55" y="55" width="280" height="340" rx="8" fill="url(#pcbGrid)" />
                    <!-- Circuit Trace Lines -->
                    <path d="M 65 80 L 110 80 L 130 110" fill="none" stroke="rgba(6, 182, 212, 0.4)" stroke-width="1.5"/>
                    <path d="M 65 140 L 100 140 L 115 160" fill="none" stroke="rgba(139, 92, 246, 0.4)" stroke-width="1.5"/>
                    <path d="M 280 90 L 315 90 L 315 170" fill="none" stroke="rgba(6, 182, 212, 0.4)" stroke-width="1.5"/>
                    <!-- I/O Armor Shield (Top-Left) -->
                    <rect x="58" y="58" width="36" height="110" rx="4" class="rig-mb-shield" />
                    <text x="64" y="115" transform="rotate(-90 64,115)" fill="#64748b" font-size="9" font-family="'Outfit', sans-serif" letter-spacing="1">SKYREX</text>
                    <!-- PCIe Slots -->
                    <rect x="95" y="325" width="220" height="8" rx="2" fill="#13111c" stroke="#64748b" stroke-width="1"/>
                    <rect x="95" y="375" width="160" height="6" rx="2" fill="#13111c" stroke="#475569" stroke-width="1"/>
                </g>

                <!-- 3. RAM (Memory Modules) -->
                <g class="rig-part" id="part-ram" data-part="ram">
                    <!-- Slot 1 -->
                    <rect x="250" y="85" width="10" height="110" rx="3" class="rig-ram-stick" />
                    <rect x="251" y="86" width="8" height="20" rx="2" fill="url(#gradFanRgb)" filter="url(#neonGlow)" />
                    <!-- Slot 2 -->
                    <rect x="266" y="85" width="10" height="110" rx="3" class="rig-ram-stick" />
                    <rect x="267" y="86" width="8" height="20" rx="2" fill="url(#gradFanRgb)" filter="url(#neonGlow)" />
                    <!-- Slot 3 & 4 (dimmed) -->
                    <rect x="282" y="87" width="8" height="106" rx="2" fill="#1e1b2e" stroke="rgba(255,255,255,0.1)"/>
                    <rect x="296" y="87" width="8" height="106" rx="2" fill="#1e1b2e" stroke="rgba(255,255,255,0.1)"/>
                    <!-- RAM Hotspot Pin -->
                    <circle cx="261" cy="73" r="5" class="rig-pin-pulse" />
                    <circle cx="261" cy="73" r="2.5" fill="#06b6d4" />
                </g>

                <!-- 4. CPU & COOLER (Tower Heatsink + RGB Fan) -->
                <!-- CPU Socket Base Under Cooler -->
                <g class="rig-part" id="part-cpu" data-part="cpu">
                    <rect x="135" y="95" width="90" height="90" rx="6" class="rig-cpu-socket" />
                    <!-- CPU Heatspreader Details -->
                    <rect x="145" y="105" width="70" height="70" rx="4" fill="#2d2b40" stroke="#8b5cf6" stroke-width="1.2"/>
                    <circle cx="145" cy="105" r="4" fill="#06b6d4"/>
                </g>

                <!-- Tower Air Cooler / Liquid Block Over CPU -->
                <g class="rig-part" id="part-cooler" data-part="cooler">
                    <!-- Heatsink Fin Stack -->
                    <rect x="130" y="80" width="100" height="115" rx="8" class="rig-cooler-body" />
                    <!-- Horizontal Fin Lines -->
                    <line x1="135" y1="95" x2="225" y2="95" stroke="rgba(255,255,255,0.1)" stroke-width="1"/>
                    <line x1="135" y1="110" x2="225" y2="110" stroke="rgba(255,255,255,0.1)" stroke-width="1"/>
                    <line x1="135" y1="125" x2="225" y2="125" stroke="rgba(255,255,255,0.1)" stroke-width="1"/>
                    <line x1="135" y1="140" x2="225" y2="140" stroke="rgba(255,255,255,0.1)" stroke-width="1"/>
                    <line x1="135" y1="155" x2="225" y2="155" stroke="rgba(255,255,255,0.1)" stroke-width="1"/>
                    <line x1="135" y1="170" x2="225" y2="170" stroke="rgba(255,255,255,0.1)" stroke-width="1"/>
                    <!-- Copper Heatpipe Tops -->
                    <circle cx="150" cy="85" r="3.5" fill="#f59e0b" stroke="#78350f" stroke-width="1"/>
                    <circle cx="170" cy="85" r="3.5" fill="#f59e0b" stroke="#78350f" stroke-width="1"/>
                    <circle cx="190" cy="85" r="3.5" fill="#f59e0b" stroke="#78350f" stroke-width="1"/>
                    <circle cx="210" cy="85" r="3.5" fill="#f59e0b" stroke="#78350f" stroke-width="1"/>
                    <!-- Center ARGB Fan Circle -->
                    <circle cx="180" cy="137" r="36" class="rig-fan-ring" />
                    <circle cx="180" cy="137" r="14" fill="#0f111a" stroke="#06b6d4" stroke-width="2"/>
                    <!-- Fan Blades -->
                    <path d="M 180 123 C 185 110 195 110 198 120 C 190 128 185 130 180 123 Z" fill="rgba(6, 182, 212, 0.4)"/>
                    <path d="M 194 137 C 207 142 207 152 197 155 C 189 147 187 142 194 137 Z" fill="rgba(139, 92, 246, 0.4)"/>
                    <path d="M 180 151 C 175 164 165 164 162 154 C 170 146 175 144 180 151 Z" fill="rgba(217, 70, 239, 0.4)"/>
                    <path d="M 166 137 C 153 132 153 122 163 119 C 171 127 173 132 166 137 Z" fill="rgba(6, 182, 212, 0.4)"/>
                </g>

                <!-- 5. SSD M.2 NVMe Slot with Armor Heatsink -->
                <g class="rig-part" id="part-ssd" data-part="ssd">
                    <rect x="115" y="215" width="100" height="24" rx="4" class="rig-ssd-shield" />
                    <!-- Thermal Armor Lines -->
                    <line x1="125" y1="227" x2="195" y2="227" stroke="rgba(6, 182, 212, 0.6)" stroke-width="1.5"/>
                    <circle cx="205" cy="227" r="2.5" fill="#06b6d4" filter="url(#neonGlow)"/>
                    <text x="135" y="224" fill="#94a3b8" font-size="8" font-weight="600" font-family="'Outfit', sans-serif">M.2 NVMe</text>
                </g>

                <!-- 6. GPU (Graphics Card - Beefy Dual Slot) -->
                <g class="rig-part" id="part-gpu" data-part="gpu">
                    <!-- GPU Main Shroud -->
                    <rect x="75" y="250" width="310" height="82" rx="10" fill="url(#gradGpu)" class="rig-gpu-body" />
                    <!-- GPU Backplate Top Line -->
                    <rect x="75" y="248" width="310" height="5" rx="2" fill="#8b5cf6" filter="url(#neonGlow)" />
                    <!-- GPU Fan 1 -->
                    <circle cx="160" cy="292" r="28" class="rig-gpu-fan" />
                    <circle cx="160" cy="292" r="10" fill="#13111c" stroke="#06b6d4" stroke-width="2"/>
                    <!-- GPU Fan 2 -->
                    <circle cx="250" cy="292" r="28" class="rig-gpu-fan" />
                    <circle cx="250" cy="292" r="10" fill="#13111c" stroke="#8b5cf6" stroke-width="2"/>
                    <!-- GPU Fan 3 / Heatsink Vent (if triple fan) -->
                    <rect x="300" y="265" width="65" height="52" rx="6" fill="#13111c" stroke="rgba(255,255,255,0.1)" stroke-width="1"/>
                    <line x1="310" y1="272" x2="355" y2="272" stroke="#475569" stroke-width="1"/>
                    <line x1="310" y1="282" x2="355" y2="282" stroke="#475569" stroke-width="1"/>
                    <line x1="310" y1="292" x2="355" y2="292" stroke="#475569" stroke-width="1"/>
                    <line x1="310" y1="302" x2="355" y2="302" stroke="#475569" stroke-width="1"/>
                    <!-- GPU PCIe Power Cable Routing -->
                    <rect x="330" y="238" width="22" height="12" rx="2" fill="#0f172a" stroke="#06b6d4" stroke-width="1"/>
                    <path d="M 335 238 C 335 220 370 220 370 200" fill="none" stroke="#334155" stroke-width="3"/>
                    <path d="M 345 238 C 345 220 380 220 380 200" fill="none" stroke="#334155" stroke-width="3"/>
                    <!-- GPU Illuminated Logo -->
                    <rect x="90" y="286" width="35" height="12" rx="2" fill="#0f111a"/>
                    <text x="94" y="295" fill="#06b6d4" font-size="8" font-weight="700" font-family="'Outfit', sans-serif">GEFORCE</text>
                </g>

                <!-- 7. PSU & BOTTOM SHROUD (Power Supply Unit) -->
                <g class="rig-part" id="part-psu" data-part="psu">
                    <!-- Lower PSU Chamber Shroud -->
                    <rect x="35" y="415" width="390" height="90" rx="10" class="rig-psu-shroud" />
                    <!-- PSU Cut-out Window showing PSU Label -->
                    <rect x="55" y="430" width="160" height="60" rx="6" class="rig-psu-unit" />
                    <text x="75" y="455" fill="#f8fafc" font-size="12" font-weight="700" font-family="'Outfit', sans-serif" letter-spacing="1">1STPLAYER</text>
                    <text x="75" y="475" fill="#eab308" font-size="10" font-weight="600" font-family="'Outfit', sans-serif">80+ GOLD ATX 3.1</text>
                    <!-- Cable Management Grommets -->
                    <ellipse cx="260" cy="425" rx="25" ry="8" fill="#13111c" stroke="#334155" stroke-width="1.5"/>
                    <ellipse cx="340" cy="425" rx="20" ry="8" fill="#13111c" stroke="#334155" stroke-width="1.5"/>
                    <!-- Fan Grill Pattern (Bottom intake) -->
                    <line x1="280" y1="445" x2="385" y2="445" stroke="#334155" stroke-width="2"/>
                    <line x1="280" y1="460" x2="385" y2="460" stroke="#334155" stroke-width="2"/>
                    <line x1="280" y1="475" x2="385" y2="475" stroke="#334155" stroke-width="2"/>
                </g>

                <!-- 8. CASE FANS (Chassis RGB Fans) -->
                <!-- Front Intake Fans (3x 120mm) -->
                <g class="rig-case-fans" opacity="0.85">
                    <circle cx="410" cy="115" r="26" class="rig-chassis-fan" />
                    <circle cx="410" cy="225" r="26" class="rig-chassis-fan" />
                    <circle cx="410" cy="335" r="26" class="rig-chassis-fan" />
                    <!-- Rear Exhaust Fan -->
                    <circle cx="70" cy="115" r="24" class="rig-chassis-fan" />
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

                const shopBadgeClass = item.shop.includes('Авито') ? 'badge-avito' :
                                      (item.shop.includes('Wildberries') ? 'badge-wb' : 'badge-ot');

                html += `
                    <div class="pc-part-card" id="card-${key}" data-part="${key}">
                        <div class="part-card-left">
                            <span class="part-card-icon">${item.icon || '⚡'}</span>
                            <div class="part-card-details">
                                <div class="part-card-meta">
                                    <span class="part-category-tag">${item.category}</span>
                                    <span class="part-shop-badge ${shopBadgeClass}">${item.shop}</span>
                                </div>
                                <span class="part-card-name" title="${item.name}">${item.name}</span>
                                ${item.tag ? `<span class="part-spec-tag">${item.tag}</span>` : ''}
                            </div>
                        </div>
                        <div class="part-card-right">
                            <span class="part-card-price">${item.price}</span>
                            ${item.url ? `
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
            // Copy Build Spec Button
            const copyBtn = document.getElementById("rig-copy-spec-btn");
            if (copyBtn) {
                copyBtn.addEventListener("click", () => {
                    this.copyBuildToClipboard(copyBtn);
                });
            }
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
                        if (item && item.url) {
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
                        if (item && item.url) {
                            window.open(item.url, "_blank", "noopener,noreferrer");
                        }
                    });
                }
            });
        },

        resetToDefault() {
            localStorage.removeItem("skyrex_active_build");
            this.state = JSON.parse(JSON.stringify(DEFAULT_BUILD));
            this.render();
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

        copyBuildToClipboard(button) {
            const items = this.state.items;
            let text = `🖥️ Игровая сборка SKYREX Computers\n`;
            text += `💰 Итоговая стоимость: ${this.state.total} ₽\n\n`;

            const order = ['cpu', 'mb', 'cooler', 'ram', 'gpu', 'ssd', 'psu', 'case'];
            order.forEach((key, idx) => {
                const itm = items[key];
                if (itm) {
                    text += `${idx + 1}. ${itm.category}: ${itm.name} — ${itm.price} (${itm.shop})\n`;
                    if (itm.url) text += `   Ссылка: ${itm.url}\n`;
                }
            });

            navigator.clipboard.writeText(text).then(() => {
                button.classList.add("copied");
                const span = button.querySelector("span");
                if (span) span.textContent = "Скопировано!";
                setTimeout(() => {
                    button.classList.remove("copied");
                    if (span) span.textContent = "Скопировать";
                }, 2000);
            }).catch(err => {
                console.warn("Clipboard copy failed", err);
            });
        },

        /**
         * Parses LLM response text, updates rig state, and plays visual scan effect
         */
        updateFromAiResponse(responseText) {
            if (!responseText || typeof responseText !== "string") return;

            // Pre-normalize text: ensure numbered items start on fresh line even if glued
            let norm = responseText.replace(/([^\n>])\s*(\b\d+[\.\)]\s*(?:<b>)?[А-ЯA-Z])/g, "$1\n$2");
            norm = norm.replace(/<br\s*\/?>/gi, "\n");

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
                    if (newItems[cat.key]) continue; // already matched

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

            // Extract Total Price if present or calculate
            const mTotal = responseText.match(/(?:суммарная стоимость|итого|стоимость сборки).*?([\d\s\xa0]{4,})\s*(?:руб|₽)/i);
            let total = mTotal ? mTotal[1].replace(/[\s\xa0]/g, '') : null;

            // If at least 3 components were parsed, update the rig!
            if (foundCount >= 3) {
                // Merge with existing state for any unmentioned parts
                Object.keys(newItems).forEach(k => {
                    this.state.items[k] = newItems[k];
                });

                if (total) {
                    this.state.total = total;
                } else {
                    // Recalculate total sum from parts
                    let sum = 0;
                    Object.values(this.state.items).forEach(itm => {
                        if (itm.price) {
                            const digits = itm.price.replace(/\D/g, '');
                            if (digits) sum += parseInt(digits, 10);
                        }
                    });
                    if (sum > 0) this.state.total = String(sum);
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
