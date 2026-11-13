const testResp = `Привет! На связи цифровой помощник... 
<ul>
<li>1. Процессор (CPU): <a href='https://www.avito.ru/novosibirsk/tovary_dlya_kompyutera/protsessor_amd_ryzen_5_5600_8051486018' target='_blank'>Процессор AMD Ryzen 5 5600 (Б/У)</a> — 10 800 руб.</li>
<li>2. Материнская плата: <a href='https://www.wildberries.ru/catalog/720676360/detail.aspx' target='_blank'>Материнская плата A520M K V2, AM4, DDR4 Gigabyte</a> — 4 104 руб.</li>
<li>3. Кулер для процессора: <a href='https://www.onlinetrade.ru/catalogue/kulery_dlya_protsessorov-c1492/id_cooling/kuler_dlya_protsessora_id_cooling_se_903_xt_frgb-4361685.html' target='_blank'>Кулер для процессора ID-COOLING SE-903-XT FRGB</a> — 1 249 руб.</li>
<li>4. Оперативная память (RAM): <a href='https://www.avito.ru/himki/tovary_dlya_kompyutera/kingston_hyperx_fury_ddr4_16gb_2x8gb_8469978635' target='_blank'>Комплект Kingston HyperX Fury DDR4 16GB (2x8GB) (Б/У)</a> — 7 000 руб.</li>
<li>5. Видеокарта (GPU): <a href='https://www.wildberries.ru/catalog/1344318433/detail.aspx' target='_blank'>Видеокарта RTX 5060 SHADOW 2X OC MAX 8 Гб MSI</a> — 78 045 руб.</li>
<li>6. Накопитель (SSD): <a href='https://www.avito.ru/moskva/tovary_dlya_kompyutera/ssd_256gb_m2_8452074991' target='_blank'>SSD M.2 NVMe 256GB (Б/У)</a> — 1 700 руб.</li>
<li>7. Блок питания (PSU): <a href='https://www.onlinetrade.ru/catalogue/bloki_pitaniya_dlya_kompyutera-c339/deepcool/blok_pitaniya_deepcool_gamerstorm_pf600x_600w_80_bronze_belyy_pf600x_wh-5140742.html' target='_blank'>Блок питания Deepcool GAMERSTORM PF600X, 600W, 80+ Bronze</a> — 4 550 руб.</li>
<li>8. Корпус: <a href='https://www.onlinetrade.ru/catalogue/kompyuternye_korpusa-c1323/1stplayer/korpus_1stplayer_bullet_hunter_h2_chernyy_h2_bk_4f1-4719545.html' target='_blank'>Корпус 1STPLAYER BULLET HUNTER H2, черный</a> — 3 750 руб.</li>
</ul>
<ul>
<li>5. Видеокарта (Альтернатива под бюджет): <a href='https://www.avito.ru/ust-labinsk/tovary_dlya_kompyutera/videokarta_geforce_rtx_4060_ventus_2x_white_8g_oc_8454654880' target='_blank'>Видеокарта GeForce RTX 4060 Ventus 2X 8G OC (Б/У)</a> — 30 000 руб.</li>
</ul>
<b>Точная суммарная стоимость:</b> 63 153 рубля.`;

let norm = testResp.replace(/<\/?(?:ul|ol|li)[^>]*>/gi, '\n');
norm = norm.replace(/<br\s*\/?>/gi, '\n');
norm = norm.replace(/([^\n>])\s*(\b\d+[\.\)]\s*(?:<b>)?[А-ЯA-Z])/g, '$1\n$2');

const lines = norm.split('\n');
const newItems = {};
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
        if (new RegExp(`^\\s*\\d+[\\.\\)]\\s*.*?${cat.regex.source}`, 'i').test(lineClean)) {
            const mPrice = lineClean.match(/(?:—|-)?\s*([\d\s\xa0,.]+)\s*(?:руб|₽)/i);
            const rawP = mPrice ? mPrice[1].replace(/[\s\xa0]/g, '').replace(/,/g, '') : '0';
            newItems[cat.key] = parseInt(rawP, 10);
            break;
        }
    }
}

let sum = 0;
for (const k in newItems) sum += newItems[k];
console.log('Parsed Items:', newItems);
console.log('Total sum:', sum);
