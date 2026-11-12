import socket, paramiko, os, dotenv
dotenv.load_dotenv(os.path.join(os.getcwd(), '.env'))

host = os.getenv('DEPLOY_HOST', '87.120.84.33')
user = os.getenv('DEPLOY_USER', 'root')
pwd = os.getenv('DEPLOY_SSH_PASSWORD')

sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
sock.settimeout(10)
sock.connect((host, 22))

client = paramiko.SSHClient()
client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
client.connect(host, 22, user, password=pwd, sock=sock, banner_timeout=30)

cmd = '''/var/www/skyrex/venv/bin/python -c "
import sqlite3
con = sqlite3.connect('/var/www/skyrex/catalog.db')
cur = con.cursor()

print('=== REMOTE SOUND CARDS / JUNK IN PRODUCTS ===')
cur.execute(\\\"\\\"\\\"
    SELECT id, shop, category, name, price, url 
    FROM products 
    WHERE url LIKE '%zvukovye_karty%' 
       OR name LIKE '%звуков%'
       OR name LIKE '%audio usb%'
       OR name LIKE '%звук%'
\\\"\\\"\\\")
rows = cur.fetchall()
print(f'Total sound cards on server: {len(rows)}')
for r in rows[:10]:
    print(f'#{r[0]} [{r[1]}] [{r[2]}] {r[3][:60]} - {r[4]} руб')

print('=== ALL PRODUCTS IN COOLER ON SERVER ===')
cur.execute(\\\"\\\"\\\"
    SELECT id, shop, name, price, url 
    FROM products 
    WHERE category = 'cooler'
\\\"\\\"\\\")
coolers = cur.fetchall()
print(f'Total items in cooler on server: {len(coolers)}')
for r in coolers[:15]:
    print(f'#{r[0]} [{r[1]}] {r[2][:60]} - {r[3]} руб')
" '''

stdin, stdout, stderr = client.exec_command(cmd)
print(stdout.read().decode('utf-8', errors='replace').strip())
err = stderr.read().decode('utf-8', errors='replace').strip()
if err:
    print('Stderr:', err)
client.close()
