const fs = require('fs');
const text = fs.readFileSync('C:/Users/user/.gemini/antigravity/brain/bf0f4570-ab64-46b8-8aee-18763b1c4198/.system_generated/tasks/task-2404.log', 'utf8');

let norm = text.replace(/<li[^>]*>/gi, "\n").replace(/<\/li>/gi, "\n");
norm = norm.replace(/<\/?ul[^>]*>/gi, "\n");
norm = norm.replace(/([^\n>])\s*(\b\d+[\.\)]\s*(?:<b>)?[А-ЯA-Z])/g, "$1\n$2");
norm = norm.replace(/<br\s*\/?>/gi, "\n");
const lines = norm.split("\n");
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
console.log('Final parsed items:', newItems);
console.log('Final sum:', sum);

const allTotals = [...text.matchAll(/(?:суммарная стоимость|итого|стоимость сборки).*?([\d\s\xa0]{4,})\s*(?:руб|₽)/gi)];
let total = allTotals.length > 0 ? allTotals[allTotals.length - 1][1].replace(/[\s\xa0]/g, '') : null;
console.log('Final parsed total string:', total);
