const fs = require('fs');

// Create mock browser environment
const dom = {};
const listeners = {};
global.document = {
    getElementById: (id) => {
        if (!dom[id]) {
            dom[id] = {
                id,
                innerHTML: '',
                style: {},
                classList: {
                    add: (c) => {},
                    remove: (c) => {}
                },
                addEventListener: (evt, fn) => {
                    listeners[evt] = fn;
                }
            };
        }
        return dom[id];
    },
    createElement: (tag) => {
        return {
            tagName: tag,
            style: {},
            classList: { add: () => {}, remove: () => {} }
        };
    },
    body: {
        appendChild: () => {}
    },
    addEventListener: (evt, fn) => {
        if (evt === 'DOMContentLoaded') fn();
    }
};

global.window = {
    document: global.document,
    addEventListener: () => {}
};

global.localStorage = {
    data: {},
    getItem: (k) => global.localStorage.data[k] || null,
    setItem: (k, v) => { global.localStorage.data[k] = v; },
    removeItem: (k) => { delete global.localStorage.data[k]; }
};

// Ensure container exists
global.document.getElementById('skyrex-pc-visualizer');

// Load rig_visualizer.js
const rigJs = fs.readFileSync('rig_visualizer.js', 'utf-8');
eval(rigJs);

console.log('window.SkyrexRig defined:', typeof window.SkyrexRig);
console.log('Initial total:', window.SkyrexRig.state.total);
console.log('Initial isCustomized:', window.SkyrexRig.state.isCustomized);

// Now test calling updateFromAiResponse
const sampleText = `Привет! На связи цифровой помощник и технический эксперт сервиса Skyrex.Отличный бюджет для сборки производительного игрового ПК, который уверенно справится с современными проектами в разрешении 1080p и 1440p на высоких настройках графики. Я подготовил для тебя сбалансированную конфигурацию из надежных комплектующих, которая строго укладывается в рамки твоего бюджета.Вот оптимальная конфигурация игрового ПК за 80 000 рублей:
1. Процессор: [Intel Core i5-13400F OEM (Б/У)](https://www.avito.ru/all?q=Intel%20Core%20i5-13400F%20OEM) — 12 000 руб.
2. Материнская плата: [Материнская плата B760M GAMING X DDR4 GEN5 LGA1700 Intel B76 Gigabyte](https://www.wildberries.ru/catalog/935780314/detail.aspx) — 11 744 руб.
3. Кулер для процессора: [DeepCool AK400](https://www.onlinetrade.ru/catalogue/kulery_dlya_protsessorov-c1492/deepcool/kuler_dlya_protsessora_deepcool_ak400_r_ak400_bknnmn_g_1-3107909.html) — 2 349 руб.
4. Оперативная память: [Оперативная память DDR4 32gb 2x16 XPG Gammix D10 (Б/У)](https://www.avito.ru/all?q=%D0%9E%D0%BF%D0%B5%D1%80%D0%B0%D1%82%D0%B8%D0%B2%D0%BD%D0%B0%D1%8F%20%D0%BF%D0%B0%D0%BC%D1%8F%D1%82%D1%8C%20DDR4%2032gb%202x16%20XPG%20Gammix%20D10) — 21 500 руб.
5. Видеокарта: [RTX 3060 Ti 8GB iGame Ultra W OC (Б/У)](https://www.avito.ru/all?q=RTX%203060%20Ti%208GB%20iGame%20Ultra%20W%20OC) — 30 000 руб.
6. Накопитель: [SSD M.2 NVMe 1TB (Б/У)](https://www.avito.ru/all?q=SSD%20M.2%20NVMe%201TB) — 3 990 руб.
7. Блок питания: [Deepcool GAMERSTORM PF850D V2, 850W, 80+ Silver](https://www.onlinetrade.ru/catalogue/bloki_pitaniya_dlya_kompyutera-c339/deepcool/blok_pitaniya_deepcool_gamerstorm_pf850d_v2_850w_80_silver_atx_3.1-5512353.html) — 5 850 руб.
8. Корпус: Продуваемый корпус с отличной вентиляцией — 3 000 руб.
Точная суммарная стоимость: 90 433 руб. — Стоп, проверяем арифметику! Сумма превышает бюджет в 80 000 руб. Пересчитываем конфигурацию строго под лимит!`;

window.SkyrexRig.updateFromAiResponse(sampleText);

console.log('After update isCustomized:', window.SkyrexRig.state.isCustomized);
console.log('After update total:', window.SkyrexRig.state.total);
console.log('CPU name:', window.SkyrexRig.state.items.cpu.name);
console.log('GPU name:', window.SkyrexRig.state.items.gpu.name);
console.log('RAM name:', window.SkyrexRig.state.items.ram.name);
console.log('Rendered HTML contains CPU name:', dom['skyrex-pc-visualizer'].innerHTML.includes('Intel Core i5-13400F'));
console.log('Rendered HTML contains ? in CPU name:', dom['skyrex-pc-visualizer'].innerHTML.includes('title="?"'));

