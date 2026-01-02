"""
@category: tool
@impact: low
@description: Script completo de migração estrutural para Fases 4-6
"""
import os
import shutil
import subprocess
from pathlib import Path

MIGRATION_MAP = [
    # TESTES - INTEGRATION
    ("scripts/test_end_to_end.py", "tests/integration/test_end_to_end.py", "test", "moderate", "Teste E2E crítico de toda pipeline"),
    ("scripts/validate_backend.py", "tests/integration/validate_backend.py", "test", "moderate", "Health check de infraestrutura"),
    
    # TESTES - UNIT
    ("scripts/test_dsl_v01_unittest.py", "tests/unit/test_dsl_v01_unittest.py", "test", "moderate", "Unittests do engine DSL v01"),
    ("scripts/test_market_context_exhaustive.py", "tests/unit/test_market_context_exhaustive.py", "test", "critical", "Validação de propriedades do Context Classifier"),

    # TOOLS - RUNNERS
    ("scripts/run_dsl_v01.py", "tools/runners/run_dsl_v01.py", "tool", "low", "CLI runner para processamento DSL"),
    
    # TOOLS - DIAGNOSTICS (MT5 Validation 0-3)
    ("scripts/mt5_validation/0_find_mt5.py", "tools/diagnostics/0_find_mt5.py", "tool", "low", "Diagnóstico: Busca executável MT5"),
    ("scripts/mt5_validation/1_check_connection.py", "tools/diagnostics/1_check_connection.py", "tool", "low", "Diagnóstico: Checa conexão e login"),
    ("scripts/mt5_validation/2_check_tick_data.py", "tools/diagnostics/2_check_tick_data.py", "tool", "low", "Diagnóstico: Valida stream de ticks"),
    ("scripts/mt5_validation/3_check_orderbook.py", "tools/diagnostics/3_check_orderbook.py", "tool", "low", "Diagnóstico: Valida orderbook depth"),

    # TOOLS - VALIDATION
    ("scripts/test_database_strategies.py", "tools/validation/test_database_strategies.py", "tool", "low", "Validação de queries e estratégias SQL"),
    ("scripts/validate_dashboard_playwright.py", "tools/validation/validate_dashboard_playwright.py", "tool", "low", "Teste automatizado da UI do dashboard"),

    # EXPERIMENTS - MT5 EXPLORATION
    ("scripts/explore_mt5_capabilities.py", "experiments/mt5_exploration/explore_capabilities.py", "experiment", "low", "Exploração completa da API MT5"),
    ("scripts/test_mt5_simple.py", "experiments/mt5_exploration/simple_test.py", "experiment", "low", "Teste didático inicial"),
    ("scripts/test_mt5_connection_windows.py", "experiments/mt5_exploration/windows_connection_test.py", "experiment", "low", "Teste legacy de conexão Windows direto"),
    
    # EXPERIMENTS - STRESS & VALIDATION
    ("scripts/mt5_validation/4_stress_test.py", "experiments/stress_tests/mt5_stress_test.py", "experiment", "low", "Teste de carga pontual"),
    ("scripts/mt5_validation/5_data_structure_test.py", "experiments/validation/data_structure_test.py", "experiment", "low", "Validação one-time de schema"),
]

HEADER_TEMPLATE = '''"""
@category: {category}
@impact: {impact}
@description: {description}
"""
'''

def run_git_mv(src, dst):
    # Cria diretório destino se não existir
    Path(dst).parent.mkdir(parents=True, exist_ok=True)
    
    print(f"Moving {src} -> {dst}")
    subprocess.run(["git", "mv", src, dst], check=True)

def prepend_header(file_path, category, impact, description):
    path = Path(file_path)
    if not path.exists():
        print(f"Error: {path} not found")
        return

    content = path.read_text()
    
    # Evita duplicação se rodar 2x
    if "@category:" in content:
        print(f"Header already present in {file_path}")
        return

    header = HEADER_TEMPLATE.format(category=category, impact=impact, description=description)
    new_content = header + "\n" + content
    path.write_text(new_content)
    print(f"Added header to {file_path}")

def main():
    print("Iniciando MIGRATION STRUCTURE FULL...")
    
    for src, dst, cat, imp, desc in MIGRATION_MAP:
        if not os.path.exists(src):
            print(f"Skipping {src} (not found)")
            continue
            
        run_git_mv(src, dst)
        prepend_header(dst, cat, imp, desc)

    # Caso especial: .sh file
    sh_src = "scripts/test_mt5_wsl_helper.sh"
    sh_dst = "experiments/mt5_exploration/wsl_helper.sh"
    if os.path.exists(sh_src):
        run_git_mv(sh_src, sh_dst)
        # Não adiciona header python em .sh
    
    # Limpeza de pastas vazias
    if os.path.exists("scripts/mt5_validation"):
        try:
            os.rmdir("scripts/mt5_validation")
            print("Removed empty scripts/mt5_validation")
        except OSError:
            print("scripts/mt5_validation not empty")

    print("Migração completa.")

if __name__ == "__main__":
    main()
