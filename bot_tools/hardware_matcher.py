"""
Skyrex Hardware Matcher - Opinion & Expert Assessment Inheritance Engine.
Maps administrator opinions, comments, and 1-10 marks from expert_components
to ALL scraped products (OnlineTrade, Wildberries, Avito) across all brands/editions.
"""

import re
from typing import Dict, Any, List, Optional, Tuple

# Common vendors across computer hardware
VENDORS = [
    'palit', 'msi', 'gigabyte', 'asus', 'asrock', 'colorful', 'inno3d', 'zotac', 'pny', 'gainward', 'kfa2',
    'sapphire', 'powercolor', 'xfx', 'deepcool', 'montech', 'cougar', 'be quiet', 'corsair', 'seasonic',
    'chieftec', 'thermaltake', 'fsp', '1stplayer', 'zalman', 'kingston', 'adata', 'samsung', 'crucial',
    'team group', 'g.skill', 'patriot', 'netac', 'xpg', 'id-cooling', 'thermalright', 'aerocool'
]

# Common submodel editions for GPUs and parts
SUBMODELS = [
    'dual', 'gamingpro', 'gaming oc', 'eagle', 'windforce', 'aero', 'aorus', 'tuf', 'rog strix', 'strix',
    'ventus 2x', 'ventus 3x', 'ventus', 'gaming x', 'suprim', 'mech', 'armor', 'shadow',
    'pulse', 'nitro+', 'nitro', 'pure', 'hellhound', 'red devil', 'fighter', 'merc', 'qick', 'swft',
    'titan gold', 'century', 'gamma ii', 'smart bm', 'toughpower', 'core reactor', 'straight power', 'pure power',
    'pk550d', 'pk650d', 'pk750d', 'pq750m', 'pq850m', 'pq1000m', 'vx plus', 'vx', 'kcas',
    'ak620', 'ak400', 'ag400', 'ag620', 'peerless assassin', 'phantom spirit', 'se-224-xt', 'se-214-xt',
    'fury beast', 'fury renegade', 'lancer', 'gammix s11', 'gammix s60', 'gammix s70', 'blade',
    'kc3000', 'nv2', 'nv3', '980 pro', '990 pro', 'p3 plus', 't500'
]


def normalize_text(text: str) -> str:
    """Cleans up text, lowercase, replaces 'ё' and strips common shop noise."""
    if not text:
        return ""
    t = text.lower().replace("ё", "е")
    # Strip shop noise
    noise_patterns = [
        r'\b(?:видеокарта|процессор|материнская плата|блок питания|накопитель|модуль памяти|корпус|кулер)\b',
        r'\b(?:для пк|компьютера|пк|pci-e\s*\d\.\d|gddr\d[x]?|oem|box|ret|bulk|m\.2|nvme|sata|atx|matx|itx)\b',
        r'[\(\)\[\]\{\},:;\"\'«»]',
    ]
    for p in noise_patterns:
        t = re.sub(p, ' ', t)
    return re.sub(r'\s+', ' ', t).strip()


def extract_chipset(text: str) -> Optional[str]:
    """
    Extracts canonical hardware chip / series:
    e.g. 'RTX 4070 Ti SUPER', 'RTX 4060', 'RX 7800 XT', 'Ryzen 5 7500F', 'i5 13400', 'B650'
    """
    t = text.lower()

    # 1. NVIDIA GPUs: RTX / GTX
    m = re.search(r'\b(rtx\s*\d{4}(?:\s*(?:ti\s*super|ti|super))?)\b', t)
    if m:
        return re.sub(r'\s+', ' ', m.group(1)).upper()

    m = re.search(r'\b(gtx\s*\d{3,4}(?:\s*(?:ti|super))?)\b', t)
    if m:
        return re.sub(r'\s+', ' ', m.group(1)).upper()

    # 2. AMD GPUs: RX
    m = re.search(r'\b(rx\s*\d{3,4}(?:\s*(?:xtx|xt|gre))?)\b', t)
    if m:
        return re.sub(r'\s+', ' ', m.group(1)).upper()

    # 3. AMD CPUs: Ryzen
    m = re.search(r'\b(ryzen\s*(?:[3579])?\s*\d{4}[a-z0-9]*)\b', t)
    if m:
        val = re.sub(r'\s+', ' ', m.group(1)).upper()
        # Normalization: 'RYZEN 7500F' -> 'RYZEN 5 7500F'
        if re.search(r'RYZEN\s+(?:7500|7600|5600|5500|3600)', val) and not re.search(r'RYZEN\s+5', val):
            val = val.replace("RYZEN ", "RYZEN 5 ")
        elif re.search(r'RYZEN\s+(?:7800|7700|5700|5800|9800|9700)', val) and not re.search(r'RYZEN\s+7', val):
            val = val.replace("RYZEN ", "RYZEN 7 ")
        return val

    # 4. Intel CPUs: Core i3/i5/i7/i9 or Core Ultra
    m = re.search(r'\b(core\s*ultra\s*[579]\s*\d{3}[a-z]*)\b', t)
    if m:
        return re.sub(r'\s+', ' ', m.group(1)).upper()

    m = re.search(r'\b(i[3579]\s*[- ]?\s*\d{4,5}[a-z]*)\b', t)
    if m:
        cleaned = re.sub(r'[\s\-]+', '', m.group(1)).upper()
        return cleaned

    # 5. Motherboards: Chipsets
    m = re.search(r'\b([xzbha]\d{2,3}[a-z]?)\b', t)
    if m:
        chip = m.group(1).upper()
        if chip in ("B650", "B550", "B450", "A620", "A520", "X670", "X870", "B850", "Z790", "B760", "H610", "Z890", "B860", "Z690", "B660"):
            return chip

    # 6. Specific PSU / SSD / Cooler lines (e.g. PK550D, TITAN GOLD, AK620, NV2, KC3000)
    for model in ('pk550d', 'pk650d', 'pk750d', 'pq750m', 'pq850m', 'pq1000m', 'titan gold', 'century', 'gamma ii',
                  'ak620', 'ak400', 'ag400', 'ag620', 'peerless assassin', 'phantom spirit',
                  'kc3000', 'nv2', 'nv3', 'gammix s11', 'gammix s60', 'vx plus', 'kcas'):
        if model in t:
            return model.upper()

    return None


def extract_vendor_and_submodel(text: str) -> Tuple[Optional[str], Optional[str]]:
    """Extracts vendor (e.g. 'palit') and submodel edition (e.g. 'dual', 'ventus')."""
    t = text.lower()
    found_vendor = None
    for v in VENDORS:
        if re.search(rf'\b{re.escape(v)}\b', t):
            found_vendor = v
            break

    found_submodel = None
    for sm in SUBMODELS:
        if sm in t:
            found_submodel = sm
            break

    return found_vendor, found_submodel


def match_expert_assessment(
    product_name: str,
    category: str = "",
    expert_components: List[Dict[str, Any]] = None
) -> Optional[Dict[str, Any]]:
    """
    Matches a product from online shops against the expert opinion knowledge base.

    Hierarchy & Inheritance:
    1. Exact Edition Match (Specificity = 300):
       Expert specified both chip and edition (e.g. 'RTX 4060 MSI Ventus 2X')
       -> Matches only MSI Ventus products.
    2. General Family / Chip Match (Specificity = 200):
       Expert specified chip family (e.g. 'RTX 4060' or 'Ryzen 5 7500F')
       -> APPLIES TO ALL EDITIONS (Palit, MSI, Gigabyte, Asus, etc.)!
    3. Series Model Match (Specificity = 250):
       Expert specified line (e.g. 'Deepcool PK550D' or 'Kingston NV2')
    4. Text Containment (Specificity = 150):
       All significant words of expert name are inside product name.

    Returns the highest-scoring expert assessment or None if no opinion exists.
    """
    if not product_name or not expert_components:
        return None

    prod_norm = normalize_text(product_name)
    prod_chip = extract_chipset(product_name)
    prod_vendor, prod_submodel = extract_vendor_and_submodel(product_name)

    best_match = None
    highest_specificity = 0

    cat_norm = category.strip().lower() if category else ""

    for exp in expert_components:
        exp_type = exp.get("type", "other").strip().lower()
        if cat_norm and exp_type != "other" and cat_norm != exp_type:
            continue

        exp_name = exp.get("componentname", "")
        exp_norm = normalize_text(exp_name)
        exp_chip = extract_chipset(exp_name)
        exp_vendor, exp_submodel = extract_vendor_and_submodel(exp_name)

        specificity = 0

        # Case 1: Chipset Match (GPUs, CPUs, Motherboards)
        if prod_chip and exp_chip and prod_chip == exp_chip:
            # Did expert specify a particular edition or vendor?
            if exp_vendor or exp_submodel:
                vendor_matches = (not exp_vendor) or (exp_vendor == prod_vendor)
                submodel_matches = (not exp_submodel) or (exp_submodel and prod_submodel and (exp_submodel in prod_submodel or prod_submodel in exp_submodel))

                if vendor_matches and submodel_matches:
                    specificity = 300  # Exact Edition Match (e.g. RTX 4060 MSI Ventus)
                else:
                    # Specified for another vendor/submodel -> skip this product
                    continue
            else:
                # Expert commented on the entire family (e.g. "RTX 4060" with no vendor)
                # Inherited by ALL editions (Palit, MSI, Gigabyte, Asus, etc.)!
                specificity = 200

        # Case 2: Specific model series (PSU / SSD / Cooler / Motherboard line)
        if specificity == 0 and not prod_chip and not exp_chip:
            p_model = extract_chipset(product_name)
            e_model = extract_chipset(exp_name)
            if p_model and e_model and p_model == e_model:
                specificity = 250

        # Case 3: Fuzzy word inclusion
        if specificity == 0 and len(exp_norm) >= 3:
            exp_words = [w for w in exp_norm.split() if len(w) >= 2]
            if exp_words and all(w in prod_norm for w in exp_words):
                specificity = 150

        if specificity > highest_specificity:
            highest_specificity = specificity
            best_match = {
                "mark": exp.get("mark", 8),
                "comment": (exp.get("comment") or "").strip(),
                "expert_name": exp_name,
                "analogue": exp.get("analogue") or "",
                "match_type": "edition" if specificity >= 300 else ("family" if specificity >= 200 else "partial"),
                "specificity": specificity
            }

    return best_match


def enrich_and_rank_products(
    products: List[Dict[str, Any]],
    expert_components: List[Dict[str, Any]],
    limit: Optional[int] = None
) -> List[Dict[str, Any]]:
    """
    Enriches scraped products with expert marks & comments, and sorts them:
    1. Highest expert mark first (10 -> 8 -> 7...)
    2. Sub-sorted by price within budget
    3. Items with mark <= 5 are placed at the end or filtered for recommendations.
    """
    enriched = []
    for p in products:
        item = dict(p)
        assessment = match_expert_assessment(item["name"], item.get("category", ""), expert_components)
        if assessment:
            item["expert_mark"] = assessment["mark"]
            item["expert_comment"] = assessment["comment"]
            item["expert_name"] = assessment["expert_name"]
            item["expert_match"] = assessment["match_type"]
        else:
            # Default fallback neutral score
            item["expert_mark"] = item.get("mark") if item.get("mark") is not None else 7
            item["expert_comment"] = item.get("comment") or ""
            item["expert_name"] = None
            item["expert_match"] = None
        enriched.append(item)

    # Separate recommended / acceptable (mark >= 6) from rejected/criticized (mark <= 5)
    recommended = [p for p in enriched if p["expert_mark"] >= 6]
    # Primary sort: highest mark first, then highest price (for budget tier utilization)
    recommended.sort(key=lambda x: (x["expert_mark"], x.get("price", 0)), reverse=True)

    rejected = [p for p in enriched if p["expert_mark"] <= 5]
    rejected.sort(key=lambda x: (x["expert_mark"], x.get("price", 0)), reverse=True)

    result = recommended
    if limit is not None:
        result = recommended[:limit]
        if len(result) < limit and rejected:
            result.extend(rejected[:limit - len(result)])
    else:
        result.extend(rejected)

    return result
