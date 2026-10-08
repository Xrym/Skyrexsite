"""
Определения инструментов (Function Calling) для интеграции поиска цен с LLM:
Google Gemini API, OpenAI API и Anthropic Claude.
"""

# 1. Схема для Google Gemini REST API (systemInstruction / tools)
GEMINI_SEARCH_PRICE_TOOL = {
    "functionDeclarations": [
        {
            "name": "search_price",
            "description": "Поиск актуальных цен на новые комплектующие ПК (видеокарты, процессоры, материнские платы, память, SSD, блоки питания) из магазинов ДНС (DNS-Shop) и Ситилинк по локальной базе данных.",
            "parameters": {
                "type": "OBJECT",
                "properties": {
                    "query": {
                        "type": "STRING",
                        "description": "Название модели или ключевые слова для поиска (например: 'RTX 4060', 'Ryzen 5 7500F', 'DDR5 32GB', 'Kingston NV2')"
                    },
                    "category": {
                        "type": "STRING",
                        "enum": ["gpu", "cpu", "motherboard", "ram", "ssd", "psu"],
                        "description": "Опциональная категория: gpu (видеокарты), cpu (процессоры), motherboard (платы), ram (память), ssd (диски), psu (блоки питания)"
                    },
                    "max_price": {
                        "type": "INTEGER",
                        "description": "Опциональный максимальный бюджет в рублях"
                    }
                },
                "required": ["query"]
            }
        }
    ]
}

# 2. Схема для OpenAI / OpenRouter / Groq / Ollama (chat/completions tools)
OPENAI_SEARCH_PRICE_TOOL = {
    "type": "function",
    "function": {
        "name": "search_price",
        "description": "Поиск актуальных цен на новые комплектующие ПК (видеокарты, процессоры, материнские платы, память, SSD, БП) в розничных магазинах ДНС (DNS-Shop) и Ситилинк.",
        "parameters": {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "Название комплектующего или модели (например: 'RTX 4060 Ti', 'i5-12400F', 'Deepcool PK650D')"
                },
                "category": {
                    "type": "string",
                    "enum": ["gpu", "cpu", "motherboard", "ram", "ssd", "psu"],
                    "description": "Опциональная категория комплектующего"
                },
                "max_price": {
                    "type": "integer",
                    "description": "Максимальная цена в рублях"
                }
            },
            "required": ["query"]
        }
    }
}
