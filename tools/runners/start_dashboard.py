"""
@category: tool
@impact: moderate
@description: Runner unificado para iniciar o Dashboard com verificações de ambiente e conectividade
"""
import os
import sys
import time
import requests
import subprocess
from dotenv import load_dotenv

# Carrega variáveis de ambiente
load_dotenv()

BRIDGE_URL = os.getenv("MT5_BRIDGE_URL", "http://localhost:8000")
DASHBOARD_SCRIPT = "src/visualization/dashboard.py"
MOCK_BRIDGE_SCRIPT = "tools/validation/mock_bridge.py"

def check_bridge_connection(url):
    """Verifica se o Bridge está respondendo"""
    try:
        print(f"[*] Verificando conexão com Bridge em {url}...", end=" ", flush=True)
        resp = requests.get(f"{url}/health", timeout=2)
        if resp.status_code == 200:
            print("✅ ONLINE")
            return True
        else:
            print(f"❌ ERRO (Status {resp.status_code})")
            return False
    except requests.exceptions.ConnectionError:
        print("❌ OFFLINE")
        return False
    except Exception as e:
        print(f"❌ ERRO: {e}")
        return False

def start_mock_bridge():
    """Inicia o Mock Bridge em background"""
    print(f"[*] Iniciando Mock Bridge ({MOCK_BRIDGE_SCRIPT})...", end=" ", flush=True)
    try:
        # Popen sem wait para rodar em background
        proc = subprocess.Popen([sys.executable, MOCK_BRIDGE_SCRIPT], 
                                stdout=subprocess.DEVNULL, 
                                stderr=subprocess.DEVNULL)
        time.sleep(2) # Espera iniciar
        print("✅ INICIADO (PID {})".format(proc.pid))
        return proc
    except Exception as e:
        print(f"❌ FALHA AO INICIAR MOCK: {e}")
        return None

def get_wsl_host_ip():
    """Detecta IP do Host Windows no WSL"""
    try:
        cmd = "ip route show | grep default | awk '{print $3}'"
        return os.popen(cmd).read().strip()
    except:
        return None

def main():
    print("="*60)
    print("🚀 CODING DAY TRADING - DASHBOARD LAUNCHER")
    print("="*60)

    # 1. Tenta Validar Conexão (Inteligente)
    active_url = None
    
    # Check 1: URL do .env
    if check_bridge_connection(BRIDGE_URL):
        active_url = BRIDGE_URL
    else:
        # Check 2: Tenta descobrir IP do Host
        host_ip = get_wsl_host_ip()
        if host_ip and host_ip not in BRIDGE_URL:
            dynamic_url = f"http://{host_ip}:8000"
            print(f"[*] Tentando IP detectado ({dynamic_url})...")
            if check_bridge_connection(dynamic_url):
                print(f"[!] SUCESSO! Bridge encontrada em {dynamic_url} (Atualizando runtime...)")
                active_url = dynamic_url
                os.environ["MT5_BRIDGE_URL"] = active_url

    mock_proc = None
    if not active_url:
        print("\n[!] AVISO: Não foi possível verificar a Bridge automaticamente.")
        print("[*] Dashboard será iniciado mesmo assim (Modo: Launch Anyway).")
        print("[*] Se os dados não carregarem, verifique o 'run_windows_bridge.bat' no Windows.")
    
    # 2. Inicia Dashboard
    print(f"\n[*] Iniciando Dashboard ({DASHBOARD_SCRIPT})...")
    print("="*60)
    
    cmd = [
        "streamlit", "run", DASHBOARD_SCRIPT,
        "--server.headless", "true",
        "--server.address", "0.0.0.0",
        "--server.port", "8501"
    ]
    try:
        # Executa streamlit e bloqueia
        subprocess.run(cmd, check=True)
    except KeyboardInterrupt:
        print("\n[!] Encerrando...")
    finally:
        if mock_proc:
            mock_proc.terminate()

if __name__ == "__main__":
    main()
