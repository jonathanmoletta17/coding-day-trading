"""
@category: tool
@impact: low
@description: Script auxiliar para migração estrutural de infraestrutura
"""
import os
import shutil
import subprocess
from pathlib import Path

# Configuração da migração
MIGRATION_MAP = [
    # Infrastructure
    ("scripts/mt5_bridge_service.py", "infrastructure/mt5_bridge_service.py", "infrastructure", "critical", "Serviço de ponte API entre MT5 (Windows) e Linux/WSL"),
    ("src/collectors/mt5_data_collector.py", "infrastructure/mt5_data_collector.py", "infrastructure", "critical", "Serviço de coleta contínua de dados MT5"),
    ("scripts/load_historical_data.py", "infrastructure/load_historical_data.py", "infrastructure", "moderate", "Script ETL para carga inicial de histórico"),
]

HEADER_TEMPLATE = '''"""
@category: {category}
@impact: {impact}
@description: {description}
"""
'''

def run_git_mv(src, dst):
    print(f"Moving {src} -> {dst}")
    subprocess.run(["git", "mv", src, dst], check=True)

def prepend_header(file_path, category, impact, description):
    path = Path(file_path)
    if not path.exists():
        print(f"Error: {path} not found")
        return

    content = path.read_text()
    header = HEADER_TEMPLATE.format(category=category, impact=impact, description=description)
    
    # Se já tiver shebang ou encoding no topo, tenta preservar?
    # Simplesmente prependendo por enquanto, python aceita docstring no topo.
    
    new_content = header + "\n" + content
    path.write_text(new_content)
    print(f"Added header to {file_path}")

def main():
    print("Iniciando migração de INFRAESTRUTURA...")
    
    for src, dst, cat, imp, desc in MIGRATION_MAP:
        if not os.path.exists(src):
            print(f"Skipping {src} (not found)")
            continue
            
        # 1. Git Move
        run_git_mv(src, dst)
        
        # 2. Add Header (necessário para passar no hook)
        prepend_header(dst, cat, imp, desc)

    print("Migração concluída. Pronto para commit.")

if __name__ == "__main__":
    main()
