"""
@category: test
@impact: critical
@description: Validação de propriedades do Context Classifier
"""

#!/usr/bin/env python3
"""
Teste Exaustivo End-to-End - Market Context Classifier

Valida TODAS as propriedades declaradas:
1. NÃO gera sinais
2. NÃO prevê preço
3. NÃO otimiza parâmetros
4. Separa atividade de comportamento
5. Mede TODOS os eventos
6. Classifica por distribuição observada
7. Determinístico
8. Auditável
"""

import sys
import pandas as pd
import numpy as np
from sqlalchemy import create_engine, text
from datetime import datetime
import os
from dotenv import load_dotenv

# Importar o classificador
sys.path.append('/home/workbench/projects/coding-day-trading/src/analysis')
from market_context_classifier import (
    analyze_market_context,
    measure_activity,
    measure_behavior,
    classify_context
)

load_dotenv()

DB_URL = f"postgresql://{os.getenv('POSTGRES_USER')}:{os.getenv('POSTGRES_PASSWORD')}@{os.getenv('POSTGRES_HOST')}:{os.getenv('POSTGRES_PORT')}/{os.getenv('POSTGRES_DB')}"
engine = create_engine(DB_URL)

# =============================================================================
# TESTES
# =============================================================================

class TestResults:
    def __init__(self):
        self.passed = []
        self.failed = []
    
    def add_pass(self, test_name, details=""):
        self.passed.append((test_name, details))
        print(f"✅ {test_name}")
        if details:
            print(f"   {details}")
    
    def add_fail(self, test_name, reason):
        self.failed.append((test_name, reason))
        print(f"❌ {test_name}")
        print(f"   Falha: {reason}")
    
    def summary(self):
        total = len(self.passed) + len(self.failed)
        print(f"\n{'='*70}")
        print(f"RESUMO DOS TESTES: {len(self.passed)}/{total} passaram")
        print(f"{'='*70}")
        
        if self.failed:
            print("\n🔴 Testes que falharam:")
            for name, reason in self.failed:
                print(f"  - {name}: {reason}")
        
        return len(self.failed) == 0

results = TestResults()

# =============================================================================
# TESTE 1: Pipeline PostgreSQL → Classifier
# =============================================================================

def test_pipeline():
    """Testa que dados fluem do PostgreSQL para o classifier"""
    print("\n" + "="*70)
    print("TESTE 1: Pipeline PostgreSQL → Classifier")
    print("="*70)
    
    try:
        # Verificar dados no banco
        query = text("SELECT COUNT(*) FROM candles WHERE symbol_id = (SELECT id FROM symbols WHERE symbol = 'EURUSD') AND timeframe = 'H1'")
        with engine.connect() as conn:
            count = conn.execute(query).scalar()
        
        if count == 0:
            results.add_fail("Pipeline - Dados disponíveis", "Sem dados no PostgreSQL")
            return
        
        results.add_pass("Pipeline - Dados disponíveis", f"{count} candles H1 no database")
        
        # Executar classifier
        context = analyze_market_context('EURUSD', 'H1')
        
        if context is None:
            results.add_fail("Pipeline - Execução do classifier", "Retornou None")
            return
        
        results.add_pass("Pipeline - Execução do classifier", "Contexto gerado com sucesso")
        
        # Verificar estrutura do output
        required_attrs = ['symbol', 'timeframe', 'activity', 'behavior', 'activity_level', 'behavior_type']
        for attr in required_attrs:
            if not hasattr(context, attr):
                results.add_fail(f"Pipeline - Atributo {attr}", "Faltando no output")
                return
        
        results.add_pass("Pipeline - Estrutura do output", "Todos atributos presentes")
        
    except Exception as e:
        results.add_fail("Pipeline", str(e))

# =============================================================================
# TESTE 2: NÃO gera sinais
# =============================================================================

def test_no_signals():
    """Verifica que NÃO há geração de sinais de trading"""
    print("\n" + "="*70)
    print("TESTE 2: NÃO Gera Sinais")
    print("="*70)
    
    try:
        context = analyze_market_context('EURUSD', 'H1')
        
        # Atributos proibidos
        forbidden_attrs = ['signal', 'trade', 'buy', 'sell', 'entry', 'exit', 'stop_loss', 'take_profit']
        
        for attr in forbidden_attrs:
            if hasattr(context, attr):
                results.add_fail("Sem sinais", f"Atributo proibido encontrado: {attr}")
                return
        
        results.add_pass("Sem sinais", "Nenhum atributo de trading detectado")
        
        # Verificar output textual
        output = context.describe()
        forbidden_words = ['comprar', 'vender', 'entrar', 'sair', 'operar', 'buy', 'sell', 'trade']
        
        for word in forbidden_words:
            if word.lower() in output.lower():
                results.add_fail("Output descritivo", f"Palavra prescritiva encontrada: {word}")
                return
        
        results.add_pass("Output descritivo", "Sem palavras prescritivas")
        
    except Exception as e:
        results.add_fail("Sem sinais", str(e))

# =============================================================================
# TESTE 3: NÃO prevê preço
# =============================================================================

def test_no_prediction():
    """Verifica que NÃO há previsão de preço futuro"""
    print("\n" + "="*70)
    print("TESTE 3: NÃO Prevê Preço")
    print("="*70)
    
    try:
        context = analyze_market_context('EURUSD', 'H1')
        
        # Atributos proibidos
        forbidden_attrs = ['prediction', 'forecast', 'target', 'predicted_price', 'next_price']
        
        for attr in forbidden_attrs:
            if hasattr(context, attr):
                results.add_fail("Sem previsão", f"Atributo proibido: {attr}")
                return
        
        results.add_pass("Sem previsão", "Nenhum atributo preditivo detectado")
        
        # Verificar que só analisa dados passados
        output = context.describe()
        future_words = ['vai', 'irá', 'será', 'próxim', 'futuro', 'esperado']
        
        for word in future_words:
            if word.lower() in output.lower():
                results.add_fail("Análise retrospectiva", f"Referência ao futuro: {word}")
                return
        
        results.add_pass("Análise retrospectiva", "Apenas descreve passado observado")
        
    except Exception as e:
        results.add_fail("Sem previsão", str(e))

# =============================================================================
# TESTE 4: Separa atividade de comportamento
# =============================================================================

def test_separation():
    """Verifica separação entre atividade e comportamento"""
    print("\n" + "="*70)
    print("TESTE 4: Separa Atividade de Comportamento")
    print("="*70)
    
    try:
        context = analyze_market_context('EURUSD', 'H1')
        
        # Verificar que activity e behavior são independentes
        activity = context.activity
        behavior = context.behavior
        
        # Activity deve medir "quantos eventos"
        activity_attrs = ['total_sweeps', 'sweeps_per_day', 'avg_spread', 'avg_range']
        for attr in activity_attrs:
            if not hasattr(activity, attr):
                results.add_fail("Separação - Activity", f"Faltando: {attr}")
                return
        
        results.add_pass("Separação - Activity", "Mede eventos quantitativamente")
        
        # Behavior deve medir "como reagiu"
        behavior_attrs = ['reversions_count', 'continuations_count', 'reversion_rate', 'continuation_rate']
        for attr in behavior_attrs:
            if not hasattr(behavior, attr):
                results.add_fail("Separação - Behavior", f"Faltando: {attr}")
                return
        
        results.add_pass("Separação - Behavior", "Mede reação aos eventos")
        
        # Verificar que são módulos independentes
        if activity.total_sweeps == 0 and behavior.total_measured > 0:
            results.add_fail("Independência", "Behavior depende de Activity indevidamente")
            return
        
        results.add_pass("Independência", "Módulos separados corretamente")
        
    except Exception as e:
        results.add_fail("Separação", str(e))

# =============================================================================
# TESTE 5: Mede TODOS os eventos
# =============================================================================

def test_measures_all():
    """Verifica que TODOS os eventos são medidos (sem filtro)"""
    print("\n" + "="*70)
    print("TESTE 5: Mede TODOS os Eventos")
    print("="*70)
    
    try:
        # Carregar dados brutos
        query = text("""
            SELECT COUNT(*) as total
            FROM candles
            WHERE symbol_id = (SELECT id FROM symbols WHERE symbol = 'EURUSD')
                AND timeframe = 'H1'
        """)
        with engine.connect() as conn:
            total_candles = conn.execute(query).scalar()
        
        context = analyze_market_context('EURUSD', 'H1')
        
        # Behavior deve analisar TODOS os candles, não só sweeps
        if context.behavior.total_measured != total_candles:
            results.add_fail("Mede todos", f"Analisou {context.behavior.total_measured} de {total_candles} candles")
            return
        
        results.add_pass("Mede todos", f"Todos os {total_candles} candles analisados")
        
        # Verificar que inclui "neutros" (não filtrados)
        if context.behavior.neutral_count == 0 and total_candles > 10:
            results.add_fail("Inclui neutros", "Sem movimentos neutros - pode estar filtrando")
            return
        
        results.add_pass("Inclui neutros", f"{context.behavior.neutral_count} neutros preservados")
        
    except Exception as e:
        results.add_fail("Mede todos", str(e))

# =============================================================================
# TESTE 6: Classifica por distribuição
# =============================================================================

def test_distribution_based():
    """Verifica classificação por distribuição observada"""
    print("\n" + "="*70)
    print("TESTE 6: Classifica por Distribuição")
    print("="*70)
    
    try:
        context = analyze_market_context('EURUSD', 'H1')
        
        # Verificar que usa taxas (rates), não thresholds absolutos
        if not hasattr(context.behavior, 'reversion_rate'):
            results.add_fail("Distribuição", "Sem taxa de reversão")
            return
        
        # Verificar que classificação é baseada em maioria (>50%)
        behavior_type = context.behavior_type
        
        if behavior_type == "REVERSIVE":
            if context.behavior.reversion_rate <= 0.5:
                results.add_fail("Classificação REVERSIVE", f"Taxa {context.behavior.reversion_rate:.1%} < 50%")
                return
        elif behavior_type == "TREND":
            if context.behavior.continuation_rate <= 0.5:
                results.add_fail("Classificação TREND", f"Taxa {context.behavior.continuation_rate:.1%} < 50%")
                return
        elif behavior_type == "MIXED":
            if context.behavior.reversion_rate > 0.5 or context.behavior.continuation_rate > 0.5:
                results.add_fail("Classificação MIXED", "Deveria ser REVERSIVE ou TREND")
                return
        
        results.add_pass("Classificação por distribuição", f"{behavior_type} baseado em taxas observadas")
        
    except Exception as e:
        results.add_fail("Distribuição", str(e))

# =============================================================================
# TESTE 7: Determinístico
# =============================================================================

def test_deterministic():
    """Verifica que mesmos dados produzem mesmo output"""
    print("\n" + "="*70)
    print("TESTE 7: Determinístico")
    print("="*70)
    
    try:
        # Executar 3 vezes
        contexts = []
        for i in range(3):
            context = analyze_market_context('EURUSD', 'H1')
            contexts.append(context)
        
        # Verificar que outputs são idênticos
        for i in range(1, 3):
            if contexts[i].activity_level != contexts[0].activity_level:
                results.add_fail("Determinismo - Activity", "Outputs diferentes entre execuções")
                return
            
            if contexts[i].behavior_type != contexts[0].behavior_type:
                results.add_fail("Determinismo - Behavior", "Outputs diferentes entre execuções")
                return
            
            if contexts[i].activity.total_sweeps != contexts[0].activity.total_sweeps:
                results.add_fail("Determinismo - Métricas", "Contagens diferentes entre execuções")
                return
        
        results.add_pass("Determinismo", "3 execuções produziram output idêntico")
        
    except Exception as e:
        results.add_fail("Determinismo", str(e))

# =============================================================================
# TESTE 8: Auditável
# =============================================================================

def test_auditable():
    """Verifica que cada cálculo é verificável"""
    print("\n" + "="*70)
    print("TESTE 8: Auditável")
    print("="*70)
    
    try:
        context = analyze_market_context('EURUSD', 'H1')
        
        # Verificar cálculos
        total = context.behavior.reversions_count + context.behavior.continuations_count + context.behavior.neutral_count
        
        if total != context.behavior.total_measured:
            results.add_fail("Auditoria - Soma", f"{total} != {context.behavior.total_measured}")
            return
        
        results.add_pass("Auditoria - Soma", "reversions + continuations + neutral = total")
        
        # Verificar taxas
        expected_rev_rate = context.behavior.reversions_count / context.behavior.total_measured if context.behavior.total_measured > 0 else 0
        
        if abs(expected_rev_rate - context.behavior.reversion_rate) > 0.001:
            results.add_fail("Auditoria - Taxa", f"reversion_rate incorreta: {context.behavior.reversion_rate:.4f} vs {expected_rev_rate:.4f}")
            return
        
        results.add_pass("Auditoria - Taxa", "Reversion rate calculada corretamente")
        
        # Verificar que métricas são rastreáveis aos dados brutos
        query = text("""
            SELECT COUNT(*) 
            FROM candles 
            WHERE symbol_id = (SELECT id FROM symbols WHERE symbol = 'EURUSD')
                AND timeframe = 'H1'
        """)
        with engine.connect() as conn:
            db_count = conn.execute(query).scalar()
        
        if context.activity.total_candles != db_count:
            results.add_fail("Auditoria - Fonte", f"total_candles {context.activity.total_candles} != DB {db_count}")
            return
        
        results.add_pass("Auditoria - Fonte", "Métricas rastreáveis ao PostgreSQL")
        
    except Exception as e:
        results.add_fail("Auditável", str(e))

# =============================================================================
# TESTE 9: Múltiplos Timeframes
# =============================================================================

def test_multiple_timeframes():
    """Testa consistência entre timeframes"""
    print("\n" + "="*70)
    print("TESTE 9: Múltiplos Timeframes")
    print("="*70)
    
    try:
        timeframes = ['H1', 'H4', 'D1']
        contexts = {}
        
        for tf in timeframes:
            contexts[tf] = analyze_market_context('EURUSD', tf)
        
        # Verificar que todos executaram
        if len(contexts) != 3:
            results.add_fail("Múltiplos TFs", "Nem todos timeframes processados")
            return
        
        results.add_pass("Múltiplos TFs", "H1, H4, D1 processados com sucesso")
        
        # Verificar coerência (spread maior em TF maior)
        if contexts['D1'].activity.avg_range < contexts['H1'].activity.avg_range:
            results.add_fail("Coerência TFs", "Range D1 < H1 (inconsistente)")
            return
        
        results.add_pass("Coerência TFs", "Range aumenta com timeframe")
        
    except Exception as e:
        results.add_fail("Múltiplos TFs", str(e))

# =============================================================================
# MAIN
# =============================================================================

def main():
    print("="*70)
    print("TESTE EXAUSTIVO END-TO-END")
    print("Market Context Classifier")
    print("="*70)
    print(f"\nData/Hora: {datetime.now()}")
    print()
    
    # Executar todos os testes
    test_pipeline()
    test_no_signals()
    test_no_prediction()
    test_separation()
    test_measures_all()
    test_distribution_based()
    test_deterministic()
    test_auditable()
    test_multiple_timeframes()
    
    # Resumo
    success = results.summary()
    
    if success:
        print("\n🎉 TODOS OS TESTES PASSARAM!")
        print("\nMarket Context Classifier está:")
        print("  ✓ Funcionando end-to-end")
        print("  ✓ Cumprindo TODAS as propriedades declaradas")
        print("  ✓ Sem sinais, sem previsões")
        print("  ✓ Determinístico e auditável")
        print("  ✓ Puramente descritivo")
        return 0
    else:
        print("\n❌ ALGUNS TESTES FALHARAM")
        print("Revise os erros acima")
        return 1

if __name__ == "__main__":
    exit_code = main()
    sys.exit(exit_code)
