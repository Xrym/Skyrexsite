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

// Copy exact JS logic from rig_visualizer.js:
let norm = sampleText.replace(/([^\n>])\s*(\b\d+[\.\)]\s*(?:<b>)?[А-ЯA-Z])/g, "$1\n$2");
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

    for (const cat of catPatterns) {
        if (newItems[cat.key]) continue;

        if (new RegExp(`^\\s*\\d+[\\.\\)]\\s*.*?${cat.regex.source}`, 'i').test(lineClean)) {
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

            const mPrice = lineClean.match(/(?:—|-)?\s*([\d\s\xa0,.]+)\s*(?:руб|₽)/i);
            let price = "";
            if (mPrice) {
                const rawP = mPrice[1].replace(/[\s\xa0]/g, '').replace(/,/g, '');
                const numP = parseInt(rawP, 10);
                price = !isNaN(numP) ? numP.toLocaleString('ru-RU') + " ₽" : mPrice[1].trim() + " ₽";
            }

            let shop = "Маркетплейс";
            if (url.includes("avito.ru")) shop = "Авито (Б/У)";
            else if (url.includes("wildberries.ru")) shop = "Wildberries";
            else if (url.includes("onlinetrade.ru")) shop = "ОнлайнТрейд";

            newItems[cat.key] = {
                id: cat.key,
                name: name,
                price: price,
                shop: shop,
                url: url
            };
            foundCount++;
            break;
        }
    }
}

console.log("Found count:", foundCount);
console.log("Keys found:", Object.keys(newItems));
for (const [k, v] of Object.entries(newItems)) {
    console.log(`  ${k}: ${v.name} | ${v.price} | ${v.shop} | ${v.url}`);
}
