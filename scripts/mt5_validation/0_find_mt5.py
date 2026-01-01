import os
import platform
import winreg

def find_mt5_in_registry():
    print("🔍 Buscando MT5 no Registro do Windows...")
    paths = []
    try:
        # Tenta encontrar na chave de desinstalação (onde muitos programas ficam)
        key_path = r"SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall"
        # Verifica registro 64 bits e 32 bits
        for reg_view in [winreg.KEY_WOW64_64KEY, winreg.KEY_WOW64_32KEY]:
            try:
                with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, key_path, 0, winreg.KEY_READ | reg_view) as key:
                    for i in range(0, winreg.QueryInfoKey(key)[0]):
                        try:
                            sub_key_name = winreg.EnumKey(key, i)
                            with winreg.OpenKey(key, sub_key_name) as sub_key:
                                try:
                                    display_name = winreg.QueryValueEx(sub_key, "DisplayName")[0]
                                    if "MetaTrader 5" in display_name:
                                        install_location = winreg.QueryValueEx(sub_key, "InstallLocation")[0]
                                        exe_path = os.path.join(install_location, "terminal64.exe")
                                        if os.path.exists(exe_path):
                                            paths.append((display_name, exe_path))
                                except FileNotFoundError:
                                    pass
                        except OSError:
                            continue
            except OSError:
                continue
    except Exception as e:
        print(f"Erro ao ler registro: {e}")
    return paths

def find_mt5_on_disk():
    print("🔍 Buscando terminal64.exe no disco (Varrendo todos os drives)...")
    
    # Detecta todos os drives lógicos
    drives = []
    try:
        import string
        from ctypes import windll
        bitmask = windll.kernel32.GetLogicalDrives()
        for letter in string.ascii_uppercase:
            if bitmask & 1:
                drives.append(f"{letter}:\\")
            bitmask >>= 1
    except:
        drives = ["C:\\"] # Fallback

    print(f"   Drives detectados: {drives}")

    # Locais comuns para procurar em cada drive
    common_folders = [
        "Program Files", 
        "Program Files (x86)", 
        "MetaTrader 5", 
        "MT5", 
        "XP MetaTrader 5",
        "Genial MetaTrader 5",
        "Rico MetaTrader 5",
        "BTG Pactual MetaTrader 5",
        "Clear MetaTrader 5",
        "Users" # Para AppData
    ]
    
    found_paths = []
    
    for drive in drives:
        for folder in common_folders:
            root_path = os.path.join(drive, folder)
            if not os.path.exists(root_path): continue
            
            print(f"   Varrendo {root_path}...")
            try:
                # Limita a profundidade para não demorar
                for dirpath, dirnames, filenames in os.walk(root_path):
                    # Calcula profundidade relativa
                    rel_depth = dirpath[len(root_path):].count(os.sep)
                    
                    # Se for Users, precisa ir mais fundo para achar AppData, mas pula outras coisas
                    if "Users" in root_path:
                         if rel_depth > 6: # Users/Name/AppData/Local/Programs/MT5...
                             del dirnames[:]
                             continue
                    elif rel_depth > 3:
                        del dirnames[:]
                        continue
                    
                    if "terminal64.exe" in filenames:
                        full_path = os.path.join(dirpath, "terminal64.exe")
                        print(f"   Found: {full_path}")
                        found_paths.append(full_path)
            except PermissionError:
                pass
            except Exception as e:
                print(f"   Erro ao ler {root_path}: {e}")
            
    return found_paths

def main():
    print("=== DIAGNÓSTICO DE INSTALAÇÃO MT5 ===")
    print(f"Sistema: {platform.system()} {platform.release()} ({platform.architecture()[0]})")
    print(f"Python: {platform.python_version()} ({platform.architecture()[0]})")
    
    # 1. Busca no Registro
    registry_paths = find_mt5_in_registry()
    if registry_paths:
        print("\n✅ Encontrado via Registro:")
        for name, path in registry_paths:
            print(f"   - {name}: {path}")
    else:
        print("\n❌ Não encontrado no Registro (Instalação Portable ou corrompida?)")

    # 2. Busca no Disco (se necessário ou para complementar)
    disk_paths = find_mt5_on_disk()
    if disk_paths:
        print("\n✅ Encontrado via Busca em Disco:")
        for path in disk_paths:
            print(f"   - {path}")
    else:
        print("\n❌ 'terminal64.exe' não encontrado nas pastas padrão.")

    # Conclusão
    all_paths = [p[1] for p in registry_paths] + disk_paths
    unique_paths = list(set(all_paths))
    
    if unique_paths:
        print("\n✨ CONCLUSÃO: Use um dos caminhos acima no seu script de conexão.")
        print("   Vou salvar o primeiro caminho encontrado em 'mt5_path.txt' para uso automático.")
        with open("scripts/mt5_validation/mt5_path.txt", "w") as f:
            f.write(unique_paths[0])
    else:
        print("\n⚠️  CRÍTICO: O MetaTrader 5 NÃO PARECE ESTAR INSTALADO.")
        print("   Se você tem certeza que instalou, ele está em uma pasta fora de 'Arquivos de Programas'?")
        print("   Por favor, digite o caminho completo do 'terminal64.exe' abaixo:")
        user_path = input("   Caminho: ").strip().replace('"', '')
        if os.path.exists(user_path):
             with open("scripts/mt5_validation/mt5_path.txt", "w") as f:
                f.write(user_path)
             print("✅ Caminho salvo!")

if __name__ == "__main__":
    main()
