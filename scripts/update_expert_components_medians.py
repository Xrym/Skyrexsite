# -*- coding: utf-8 -*-
"""
Skyrex Dynamic Market Medians Updater.
Calculates all reference medians 100% dynamically from real database listings in 'products' table.
ZERO HARDCODED PRICES IN CODE!
"""

import sys
import os

# Add project root to sys.path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from bot_tools.dynamic_medians import sync_all_database_medians

def main():
    db_file = sys.argv[1] if len(sys.argv) > 1 else "catalog.db"
    print("=" * 60)
    print(f"[*] Skyrex Dynamic Medians Calculation for: {db_file}")
    print("[*] Calculating statistical medians directly from database products...")
    print("=" * 60)
    
    res = sync_all_database_medians(db_path=db_file)
    print(f"\n[✓] Successfully updated {res['updated']} reference components dynamically from real database listings!")
    for comp, data in list(res['details'].items())[:15]:
        print(f"  • {comp}: {data['new_price']:,} ₽ (listings: {data['count']}, range: {data['range'][0]:,} – {data['range'][1]:,} ₽)")
    if len(res['details']) > 15:
        print(f"  ... and {len(res['details']) - 15} more components.")
    print("\n[✓] Zero hardcoded prices. Medians are 100% database-driven.")

if __name__ == "__main__":
    main()
