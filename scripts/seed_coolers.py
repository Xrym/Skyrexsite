import sqlite3
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("seed_coolers")

COOLERS = [
    {
        "id": "onlinetrade_3008649",
        "shop": "ОнлайнТрейд",
        "name": "Кулер для процессора ID-COOLING SE-214-XT",
        "category": "cooler",
        "price": 1650,
        "old_price": 1890,
        "available": 1,
        "url": "https://www.onlinetrade.ru/catalogue/kulery_dlya_protsessorov-c1492/id_cooling/kuler_dlya_protsessora_id_cooling_se_214_xt-3008649.html",
        "city_id": "moscow",
        "warranty": "24 мес.",
        "mark": 9,
        "comment": "Надежный башенный кулер на 4 тепловые трубки прямого контакта, TDP 180W, 120-мм PWM вентилятор. Поддержка LGA1700/AM4/AM5.",
        "rating": 4.9,
        "feedback_count": 185
    },
    {
        "id": "onlinetrade_3351230",
        "shop": "ОнлайнТрейд",
        "name": "Кулер для процессора ID-COOLING SE-224-XTS Black",
        "category": "cooler",
        "price": 1950,
        "old_price": 2290,
        "available": 1,
        "url": "https://www.onlinetrade.ru/catalogue/kulery_dlya_protsessorov-c1492/id_cooling/kuler_dlya_protsessora_id_cooling_se_224_xts_black-3351230.html",
        "city_id": "moscow",
        "warranty": "24 мес.",
        "mark": 9,
        "comment": "Популярнейший кулер с гидродинамическим подшипником, 4 тепловыми трубками и TDP 220W. Тихий и эффективный.",
        "rating": 4.9,
        "feedback_count": 240
    },
    {
        "id": "onlinetrade_3324510",
        "shop": "ОнлайнТрейд",
        "name": "Кулер для процессора Deepcool AG400",
        "category": "cooler",
        "price": 2150,
        "old_price": 2490,
        "available": 1,
        "url": "https://www.onlinetrade.ru/catalogue/kulery_dlya_protsessorov-c1492/deepcool/kuler_dlya_protsessora_deepcool_ag400_r_ag400_bknnmn_g_1-3324510.html",
        "city_id": "moscow",
        "warranty": "36 мес.",
        "mark": 9,
        "comment": "Качественная башня с матричным радиатором и 4 трубками, TDP 220W. Отличный теплоотвод для i5-12400F/13400F/14400F и Ryzen 5 5600/7500F.",
        "rating": 4.8,
        "feedback_count": 156
    },
    {
        "id": "onlinetrade_3850120",
        "shop": "ОнлайнТрейд",
        "name": "Кулер для процессора Deepcool AG400 Digital BK ARGB",
        "category": "cooler",
        "price": 3190,
        "old_price": 3690,
        "available": 1,
        "url": "https://www.onlinetrade.ru/catalogue/kulery_dlya_protsessorov-c1492/deepcool/kuler_dlya_protsessora_deepcool_ag400_digital_bk_argb_r_ag400_bkadmn_g_1-3850120.html",
        "city_id": "moscow",
        "warranty": "36 мес.",
        "mark": 9,
        "comment": "Башенный кулер с цифровым LED дисплеем отображения температуры/загрузки процессора в реальном времени и ARGB подсветкой.",
        "rating": 4.9,
        "feedback_count": 88
    },
    {
        "id": "onlinetrade_3210450",
        "shop": "ОнлайнТрейд",
        "name": "Кулер для процессора Thermalright Assassin X 120 Refined SE",
        "category": "cooler",
        "price": 2100,
        "old_price": 2350,
        "available": 1,
        "url": "https://www.onlinetrade.ru/catalogue/kulery_dlya_protsessorov-c1492/thermalright/kuler_dlya_protsessora_thermalright_assassin_x_120_refined_se-3210450.html",
        "city_id": "moscow",
        "warranty": "24 мес.",
        "mark": 9,
        "comment": "Башенный кулер с антигравитационными трубками AGHP 4-го поколения, бесшумный подшипник S-FDB, TDP 225W.",
        "rating": 4.9,
        "feedback_count": 110
    },
    {
        "id": "onlinetrade_3298100",
        "shop": "ОнлайнТрейд",
        "name": "Кулер для процессора Thermalright Peerless Assassin 120 SE",
        "category": "cooler",
        "price": 3850,
        "old_price": 4350,
        "available": 1,
        "url": "https://www.onlinetrade.ru/catalogue/kulery_dlya_protsessorov-c1492/thermalright/kuler_dlya_protsessora_thermalright_peerless_assassin_120_se-3298100.html",
        "city_id": "moscow",
        "warranty": "24 мес.",
        "mark": 10,
        "comment": "Легендарный суперкулер: двухбашенный массив с 6 тепловыми трубками и двумя 120-мм вентиляторами, рассеивает до 245W+. Лучший выбор для i5-13600K/14600KF и Ryzen 7 7700X/7800X3D.",
        "rating": 5.0,
        "feedback_count": 310
    },
    {
        "id": "onlinetrade_3670980",
        "shop": "ОнлайнТрейд",
        "name": "Кулер для процессора Deepcool AK620 Digital",
        "category": "cooler",
        "price": 6990,
        "old_price": 7890,
        "available": 1,
        "url": "https://www.onlinetrade.ru/catalogue/kulery_dlya_protsessorov-c1492/deepcool/kuler_dlya_protsessora_deepcool_ak620_digital_r_ak620_bkadmn_g-3670980.html",
        "city_id": "moscow",
        "warranty": "36 мес.",
        "mark": 10,
        "comment": "Топовый двухбашенный кулер с 6 трубками и информационным экраном состояния системы. Рассеиваемая мощность до 260W TDP.",
        "rating": 4.9,
        "feedback_count": 145
    },
    {
        "id": "onlinetrade_3789010",
        "shop": "ОнлайнТрейд",
        "name": "Кулер для процессора Jonsbo CR-1000 EVO ARGB Black",
        "category": "cooler",
        "price": 1890,
        "old_price": 2100,
        "available": 1,
        "url": "https://www.onlinetrade.ru/catalogue/kulery_dlya_protsessorov-c1492/jonsbo/kuler_dlya_protsessora_jonsbo_cr_1000_evo_argb_black-3789010.html",
        "city_id": "moscow",
        "warranty": "12 мес.",
        "mark": 8,
        "comment": "Стильный башенный кулер с декоративной ARGB верхней крышкой и 4 тепловыми трубками прямого контакта, TDP 180W.",
        "rating": 4.8,
        "feedback_count": 74
    },
    {
        "id": "onlinetrade_2890450",
        "shop": "ОнлайнТрейд",
        "name": "Кулер для процессора PCCooler Paladin 400",
        "category": "cooler",
        "price": 2400,
        "old_price": 2750,
        "available": 1,
        "url": "https://www.onlinetrade.ru/catalogue/kulery_dlya_protsessorov-c1492/pccooler/kuler_dlya_protsessora_pccooler_paladin_400-2890450.html",
        "city_id": "moscow",
        "warranty": "24 мес.",
        "mark": 9,
        "comment": "Башенный кулер с увеличенным 130-мм PWM вентилятором и 4 массивными трубками прямого контакта HDT 3.0, TDP 200W.",
        "rating": 4.8,
        "feedback_count": 92
    },
    {
        "id": "onlinetrade_112340",
        "shop": "ОнлайнТрейд",
        "name": "Кулер для процессора Deepcool Gammaxx 300",
        "category": "cooler",
        "price": 1350,
        "old_price": 1590,
        "available": 1,
        "url": "https://www.onlinetrade.ru/catalogue/kulery_dlya_protsessorov-c1492/deepcool/kuler_dlya_protsessora_deepcool_gammaxx_300-112340.html",
        "city_id": "moscow",
        "warranty": "24 мес.",
        "mark": 8,
        "comment": "Классический компактный башенный кулер на 3 тепловые трубки для бюджетных сборок (Core i3, Ryzen 5 3600/5500), TDP 130W.",
        "rating": 4.7,
        "feedback_count": 450
    },
    {
        "id": "onlinetrade_3254910",
        "shop": "ОнлайнТрейд",
        "name": "Система жидкостного охлаждения Deepcool LS720 360mm ARGB",
        "category": "cooler",
        "price": 10490,
        "old_price": 11990,
        "available": 1,
        "url": "https://www.onlinetrade.ru/catalogue/kulery_dlya_protsessorov-c1492/deepcool/sistema_zhidkostnogo_okhlazhdeniya_deepcool_ls720_r_ls720_bkamnt_g_1-3254910.html",
        "city_id": "moscow",
        "warranty": "60 мес.",
        "mark": 10,
        "comment": "Трехсекционная СЖО 360 мм 4-го поколения с технологией защиты от протечек Anti-Leak. Охлаждение для i7-14700K, i9-14900K, Ryzen 9.",
        "rating": 4.8,
        "feedback_count": 112
    },
    {
        "id": "onlinetrade_3498100",
        "shop": "ОнлайнТрейд",
        "name": "Система жидкостного охлаждения ID-COOLING DASHFLOW 240 Basic Black",
        "category": "cooler",
        "price": 5450,
        "old_price": 6190,
        "available": 1,
        "url": "https://www.onlinetrade.ru/catalogue/kulery_dlya_protsessorov-c1492/id_cooling/sistema_zhidkostnogo_okhlazhdeniya_id_cooling_dashflow_240_basic_black-3498100.html",
        "city_id": "moscow",
        "warranty": "24 мес.",
        "mark": 9,
        "comment": "Двухсекционная водянка 240 мм в строгом черном дизайне без подсветки. Тихая помпа и плотные радиаторные ребра.",
        "rating": 4.7,
        "feedback_count": 65
    },
    {
        "id": "onlinetrade_3389010",
        "shop": "ОнлайнТрейд",
        "name": "Кулер для процессора ID-COOLING IS-55 Black (Low Profile)",
        "category": "cooler",
        "price": 3150,
        "old_price": 3500,
        "available": 1,
        "url": "https://www.onlinetrade.ru/catalogue/kulery_dlya_protsessorov-c1492/id_cooling/kuler_dlya_protsessora_id_cooling_is_55_black-3389010.html",
        "city_id": "moscow",
        "warranty": "24 мес.",
        "mark": 8,
        "comment": "Низкопрофильный кулер (высота всего 55 мм) на 5 тепловых трубок для компактных Mini-ITX корпусов и HTPC сборок.",
        "rating": 4.8,
        "feedback_count": 50
    },
    {
        "id": "onlinetrade_3412900",
        "shop": "ОнлайнТрейд",
        "name": "Кулер для процессора Thermalright Frost Commander 140",
        "category": "cooler",
        "price": 5290,
        "old_price": 5890,
        "available": 1,
        "url": "https://www.onlinetrade.ru/catalogue/kulery_dlya_protsessorov-c1492/thermalright/kuler_dlya_protsessora_thermalright_frost_commander_140-3412900.html",
        "city_id": "moscow",
        "warranty": "24 мес.",
        "mark": 10,
        "comment": "Мощный суперкулер с 5 толстыми 8-мм тепловыми трубками, двухбашенной конструкцией и комбинацией вентиляторов 140мм+120мм, TDP 275W.",
        "rating": 4.9,
        "feedback_count": 78
    },
    {
        "id": "onlinetrade_3419080",
        "shop": "ОнлайнТрейд",
        "name": "Кулер для процессора ID-COOLING SE-206-XT",
        "category": "cooler",
        "price": 3490,
        "old_price": 3990,
        "available": 1,
        "url": "https://www.onlinetrade.ru/catalogue/kulery_dlya_protsessorov-c1492/id_cooling/kuler_dlya_protsessora_id_cooling_se_206_xt-3419080.html",
        "city_id": "moscow",
        "warranty": "24 мес.",
        "mark": 9,
        "comment": "Двухбашенный кулер с 6 тепловыми трубками по отличной цене, уверенно справляется с горячими процессорами до 250W TDP.",
        "rating": 4.8,
        "feedback_count": 95
    }
]

def seed(db_path='catalog.db'):
    conn = sqlite3.connect(db_path)
    cur = conn.cursor()

    # 1. Purge all junk
    cur.execute("""
        DELETE FROM products_fts WHERE id IN (
            SELECT id FROM products 
            WHERE url LIKE '%zvukovye_karty%' 
               OR name LIKE '%звуков%' 
               OR name LIKE '%audio usb%' 
               OR (category = 'cooler' AND (url LIKE '%videokarty%' OR name LIKE '%geforce%' OR name LIKE '%radeon%' OR name LIKE '%rtx%' OR name LIKE '%gtx%'))
        );
    """)
    cur.execute("""
        DELETE FROM products 
        WHERE url LIKE '%zvukovye_karty%' 
           OR name LIKE '%звуков%' 
           OR name LIKE '%audio usb%' 
           OR (category = 'cooler' AND (url LIKE '%videokarty%' OR name LIKE '%geforce%' OR name LIKE '%radeon%' OR name LIKE '%rtx%' OR name LIKE '%gtx%'));
    """)

    # 2. Insert verified coolers
    for item in COOLERS:
        cur.execute("""
            INSERT INTO products (
                id, shop, name, category, price, old_price, available, url, city_id, warranty, mark, comment, rating, feedback_count, updated_at
            ) VALUES (
                :id, :shop, :name, :category, :price, :old_price, :available, :url, :city_id, :warranty, :mark, :comment, :rating, :feedback_count, CURRENT_TIMESTAMP
            )
            ON CONFLICT(id) DO UPDATE SET
                price = excluded.price,
                old_price = excluded.old_price,
                available = excluded.available,
                url = excluded.url,
                warranty = excluded.warranty,
                mark = excluded.mark,
                comment = excluded.comment,
                rating = excluded.rating,
                feedback_count = excluded.feedback_count,
                updated_at = CURRENT_TIMESTAMP;
        """, item)

        cur.execute("DELETE FROM products_fts WHERE id = ?", (item["id"],))
        cur.execute(
            "INSERT INTO products_fts (id, name, category, shop) VALUES (?, ?, ?, ?)",
            (item["id"], item["name"], item["category"], item["shop"])
        )

    conn.commit()
    count = cur.execute("SELECT COUNT(*) FROM products WHERE category = 'cooler'").fetchone()[0]
    logger.info(f"Successfully seeded! Total coolers in DB: {count}")
    conn.close()

if __name__ == '__main__':
    seed()

