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

def main():
    print("="*60)
    print("🚀 CODING DAY TRADING - DASHBOARD LAUNCHER")
    print("="*60)

    # 1. Verifica Bridge Real
    bridge_active = check_bridge_connection(BRIDGE_URL)
    mock_proc = None

    if not bridge_active:
        print(f"\n[!] AVISO: MT5 Bridge não encontrado em {BRIDGE_URL}")
        choice = input("[?] Deseja iniciar o MOCK BRIDGE para testes visuais? (S/n): ").strip().lower()
        
        if choice in ('', 's', 'y'):
            # Sobrescreve URL para localhost se usar mock
            os.environ["MT5_BRIDGE_URL"] = "http://localhost:8000"
            mock_proc = start_mock_bridge()
            if not mock_proc:
                print("[!] Abortando devido a falha no Mock.")
                sys.exit(1)
        else:
            print("[!] Prosseguindo sem Bridge (Funcionalidades MT5 podem falhar).")

    # 2. Inicia Dashboard
    print(f"\n[*] Iniciando Dashboard ({DASHBOARD_SCRIPT})...")
    print("="*60)
    
    cmd = ["streamlit", "run", DASHBOARD_SCRIPT]
    try:
        # Executa streamlit e bloqueia
        subprocess.run(cmd, check=True)
    except KeyboardInterrupt:
        print("\n[!] Encerrando...")
    finally:
        if mock_proc:
            print(f"[*] Finalizando Mock Bridge (PID {mock_proc.pid})...")
            mock_proc.terminate()
            mock_proc.wait()

if __name__ == "__main__":
    main()
