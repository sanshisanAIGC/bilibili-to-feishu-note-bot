"""Upload the fixed downloader.py and pipeline.py to server via SFTP."""
from dotenv import load_dotenv; load_dotenv()
import os, paramiko, sys

host = os.getenv('DEPLOY_HOST')
user = os.getenv('DEPLOY_USER', 'root')
pwd = os.getenv('DEPLOY_PASSWORD')

ssh = paramiko.SSHClient()
ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
ssh.connect(host, username=user, password=pwd, timeout=15)
print('Connected')

sftp = ssh.open_sftp()
sftp.put('src/audio/downloader.py', '/opt/bilibili-bot/src/audio/downloader.py')
sftp.put('src/pipeline.py', '/opt/bilibili-bot/src/pipeline.py')
sftp.close()
print('Files uploaded')

stdin, stdout, stderr = ssh.exec_command('systemctl restart bilibili-bot')
print('Restarted')
ssh.close()
print('Done')
