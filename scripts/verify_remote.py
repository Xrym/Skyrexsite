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

cmd = """python3 -c "
import sqlite3
con = sqlite3.connect('/var/www/skyrex/catalog.db')
cur = con.cursor()
print('Total products on server:', cur.execute('SELECT COUNT(*) FROM products').fetchone()[0])
print('By shop:', cur.execute('SELECT shop, COUNT(*) FROM products GROUP BY shop').fetchall())
print('Total reference components:', cur.execute('SELECT COUNT(*) FROM expert_components').fetchone()[0])
print('Sample reference components:')
for r in cur.execute('SELECT componentname, price, mark, comment FROM expert_components LIMIT 5'):
    print('  ', r)
print('Rule 4:')
r4 = cur.execute('SELECT id, title, rule_text FROM ai_rules WHERE id = 4').fetchone()
print('  Rule #4:', r4[1], '->', r4[2][:90])
" """

stdin, stdout, stderr = client.exec_command(cmd)
print(stdout.read().decode('utf-8', errors='replace').strip())
err = stderr.read().decode('utf-8', errors='replace').strip()
if err:
    print('Error:', err)
client.close()

