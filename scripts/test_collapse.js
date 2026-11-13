const sample = `Приветствую! На связи цифровой помощник сервиса Skyrex.Отличная задача! Бюджет в 40 000 рублей — это разумный порог для сборки.
Вот оптимальная конфигурация ПК ровно под ваш бюджет:
1. Процессор: [Процессор amd Ryzen 5 5600 (Б/У)] — 10 800 руб.
5. Видеокарта: ... — 23 990 руб. — отмечу, что здесь небольшая коррекция ...
Давайте пересоберем с точным математическим балансом:
1. Процессор: [Процессор amd Ryzen 5 5600 (Б/У)] — 10 800 руб.
Точная суммарная стоимость: 47 190 руб. — Ой, секунду! Это превышает лимит. Давайте сделаем правильную компоновку:
1. Процессор: [Процессор Intel Core i3-12100F (Б/У)] — 6 000 руб.
2. Материнская плата: [Asus prime H610M-R D4-SI] — 4 050 руб.
Точная суммарная стоимость: 42 121 руб.
Примечание эксперта: Платформа LGA 1700!`;

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
    return `${intro}\n\nВот оптимальная конфигурация ПК под ваш бюджет:\n${finalBuild}`;
}

console.log('=== JS RESULT ===');
console.log(collapseMultipleBuildDrafts(sample));

