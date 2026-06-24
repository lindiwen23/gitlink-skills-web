#!/usr/bin/env python3
"""Deploy GitLink Skills Web Service to Alibaba Cloud."""
import os
import sys
import subprocess

HOST = "121.41.212.97"
PORT = 22
USER = "root"
PASSWORD = "<YOUR_PASSWORD>"
API_KEY = "<YOUR_API_KEY>"

LOCAL_DIR = os.path.dirname(os.path.abspath(__file__))
REMOTE_DIR = "/opt/gitlink-web"

try:
    import paramiko
except ImportError:
    subprocess.check_call([sys.executable, "-m", "pip", "install", "paramiko", "-q"])
    import paramiko

def run_ssh(ssh, cmd):
    _, stdout, stderr = ssh.exec_command(cmd)
    exit_code = stdout.channel.recv_exit_status()
    out = stdout.read().decode().strip()
    err = stderr.read().decode().strip()
    return out, err, exit_code

def main():
    print(f"[1/8] Connecting to {HOST}...")
    ssh = paramiko.SSHClient()
    ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    ssh.connect(HOST, PORT, USER, PASSWORD, timeout=10)
    print("  OK - Connected")

    print("[2/8] Installing system dependencies...")
    run_ssh(ssh, "apt-get update -qq && apt-get install -y -qq python3-pip npm nodejs 2>&1 | tail -3")

    print("[3/8] Installing gitlink-cli...")
    run_ssh(ssh, "npm install -g gitlink-cli 2>&1 | tail -3")
    v, _, _ = run_ssh(ssh, "gitlink-cli version 2>&1 || echo 'not found'")
    print(f"  gitlink-cli: {v}")

    print(f"[4/8] Creating {REMOTE_DIR}...")
    run_ssh(ssh, f"mkdir -p {REMOTE_DIR}/templates {REMOTE_DIR}/skills {REMOTE_DIR}/reports")

    print("[5/8] Uploading files...")
    sftp = ssh.open_sftp()
    for root, dirs, files in os.walk(LOCAL_DIR):
        for fname in files:
            if fname.endswith(('.py', '.txt', '.html')) or fname in ('requirements.txt', 'README.md'):
                local_path = os.path.join(root, fname)
                rel_path = os.path.relpath(local_path, LOCAL_DIR)
                remote_path = f"{REMOTE_DIR}/{rel_path}"
                try:
                    sftp.put(local_path, remote_path)
                    print(f"  -> {rel_path}")
                except Exception as e:
                    print(f"  FAIL {rel_path}: {e}")
    sftp.close()

    print("[6/8] Installing Python dependencies...")
    run_ssh(ssh, f"cd {REMOTE_DIR} && pip3 install -r requirements.txt -q 2>&1 | tail -3")

    print("[7/8] Creating systemd service...")
    service = '\n'.join([
        '[Unit]',
        'Description=GitLink Skills Web Service',
        'After=network.target',
        '',
        '[Service]',
        'Type=simple',
        'User=root',
        f'WorkingDirectory={REMOTE_DIR}',
        f'Environment="API_KEY={API_KEY}"',
        'Environment="API_MODEL=deepseek-chat"',
        f'ExecStart=/usr/bin/python3 {REMOTE_DIR}/app.py --port=80',
        'Restart=always',
        'RestartSec=5',
        '',
        '[Install]',
        'WantedBy=multi-user.target',
    ])
    escaped_service = service.replace('"', '\\"').replace("'", "\\'")
    run_ssh(ssh, f"cat > /etc/systemd/system/gitlink-web.service << 'EOF'\n{service}\nEOF")

    print("[8/8] Starting service...")
    run_ssh(ssh, "systemctl daemon-reload")
    run_ssh(ssh, "systemctl enable gitlink-web")
    _, err, code = run_ssh(ssh, "systemctl start gitlink-web")
    if err and "Unit" not in err:
        print(f"  WARN: {err[:200]}")
    out, _, _ = run_ssh(ssh, "systemctl status gitlink-web --no-pager -l | head -15")
    print(f"\n  {out.replace(chr(10), chr(10)+'  ')}")

    print(f"\nService URLs:")
    print(f"  http://{HOST}/")
    print(f"  http://{HOST}/research")
    print(f"  http://{HOST}/contributor")

    ssh.close()

if __name__ == "__main__":
    main()
