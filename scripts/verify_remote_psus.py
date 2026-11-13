import os
import paramiko
from dotenv import load_dotenv

load_dotenv()

def verify():
    client = paramiko.SSHClient()
    client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    client.connect(os.getenv('DEPLOY_HOST', '87.120.84.33'), username=os.getenv('DEPLOY_USER', 'root'), password=os.getenv('DEPLOY_SSH_PASSWORD'))

    cmd = """/var/www/skyrex/venv/bin/python -c "
import sqlite3
con = sqlite3.connect('/var/www/skyrex/catalog.db')
cur = con.cursor()
psus = cur.execute(\\"SELECT id, shop, name, price FROM products WHERE category = 'psu' ORDER BY price ASC\\").fetchall()
print(f'Total PSUs on server: {len(psus)}')
print('Cheapest 5:')
for p in psus[:5]:
    print(' ', p)
print('Most expensive 5:')
for p in psus[-5:]:
    print(' ', p)
"
"""
    stdin, stdout, stderr = client.exec_command(cmd)
    print(stdout.read().decode('utf-8'))
    err = stderr.read().decode('utf-8')
    if err:
        print("ERR:", err)
    client.close()

if __name__ == '__main__':
    verify()

