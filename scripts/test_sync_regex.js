const sample1 = 'Точная суммарная стоимость: 60 076 руб. (практически впритык к бюджету с учетом мощной видеокарты RTX 4060).';
const sample2 = '<b>Точная суммарная стоимость:</b> 10 800 + 4 104 + 1 223 + 7 000 + 30 000 + 1 700 + 4 550 + 3 750 = 63 153 рубля.<br><br><b>Примечание эксперта:</b>';
const sample3 = 'Итоговая стоимость сборки: 58 400 руб.<br>Отличный выбор!';

const exactNum = 70076;
const formatted = exactNum.toLocaleString('ru-RU') + ' руб.';

const repl = (str) => str.replace(/((?:<b>)?(?:Точная суммарная стоимость|Итого(?:вая)? стоимость|Суммарная стоимость)[^:\n<]*:(?:<\/b>)?\s*)(?:[^\n<]+)/gi, `$1${formatted}`);

console.log('1:', repl(sample1));
console.log('2:', repl(sample2));
console.log('3:', repl(sample3));

