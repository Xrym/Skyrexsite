import os
import paramiko
from dotenv import load_dotenv

load_dotenv()

def verify_remote():
    client = paramiko.SSHClient()
    client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    host = os.getenv("DEPLOY_HOST", "87.120.84.33")
    user = os.getenv("DEPLOY_USER", "root")
    pwd = os.getenv("DEPLOY_SSH_PASSWORD")
    client.connect(host, username=user, password=pwd)

    cmd = """/var/www/skyrex/venv/bin/python -c "
import sqlite3
con = sqlite3.connect('/var/www/skyrex/catalog.db')
cur = con.cursor()
cpus = cur.execute(\\"SELECT id, name, price FROM products WHERE category = 'cpu'\\").fetchall()
print(f'Total CPUs on server: {len(cpus)}')

bundle_keywords = ['комплект', 'komplekt', 'материн', 'плата', 'b450', 'b550', 'b650', 'b760', 'b850', 'с кулером', 'snowman', 'vodyanka', 'сборк', 'игровой пк']
bundles = [c for c in cpus if any(k in c[1].lower() for k in bundle_keywords)]
print(f'Bundles found on server: {len(bundles)}')
for b in bundles:
    print('  BUNDLE:', b)

print('--- Clean CPUs sample ---')
for c in cpus[:8]:
    print(' ', c)

print('--- Expert Components CPUs ---')
exp = cur.execute(\\"SELECT componentname, price, mark FROM expert_components WHERE type = 'cpu' ORDER BY price ASC\\").fetchall()
for e in exp:
    print(' ', e)
"
"""
    stdin, stdout, stderr = client.exec_command(cmd)
    out = stdout.read().decode('utf-8')
    err = stderr.read().decode('utf-8')
    print("OUTPUT:\n", out)
    if err:
        print("ERROR:\n", err)
    client.close()

if __name__ == '__main__':
    verify_remote()
