"""
@category: experiment
@impact: low
@description: Validação one-time de schema
"""

import time
import numpy as np
import pandas as pd

def test_data_structure_performance():
    print("=== TESTE DE ESTRUTURA DE DADOS (HEATMAP) ===")
    print("Simulando carga de 1 hora de pregão em memória...")

    # Parâmetros do Heatmap
    price_levels = 100 # 100 níveis de preço monitorados
    time_steps = 3600  # 1 hora (1 snapshot por segundo)
    
    print(f"Criando matriz {price_levels} x {time_steps}...")
    
    start_alloc = time.time()
    
    # Opção A: Lista de Listas (Péssimo, mas teste base)
    # heatmap_list = [[0.0] * time_steps for _ in range(price_levels)]
    
    # Opção B: NumPy Array (Ideal)
    # Inicializa com Zeros
    heatmap_matrix = np.zeros((price_levels, time_steps), dtype=np.float32)
    
    end_alloc = time.time()
    print(f"✅ Alocação inicial: {end_alloc - start_alloc:.4f}s")
    
    print("\nSimulando Updates em Tempo Real (100ms loop)...")
    
    # Simulando um "Sliding Window" (Janela Deslizante)
    # O heatmap visualiza os últimos N segundos. Quando chega dado novo, tudo shift para esquerda.
    
    window_width = 600 # Visualiza 10 minutos na tela
    display_buffer = np.zeros((price_levels, window_width), dtype=np.float32)
    
    update_times = []
    
    for i in range(100): # Simula 100 updates
        t_start = time.time()
        
        # 1. Chega nova coluna de dados (Snapshot do Book)
        new_column = np.random.rand(price_levels, 1).astype(np.float32) * 100
        
        # 2. Shift do Buffer (Custoso?)
        # Move tudo uma casa para esquerda
        display_buffer = np.roll(display_buffer, -1, axis=1)
        # Insere na última coluna
        display_buffer[:, -1] = new_column.flatten()
        
        t_end = time.time()
        update_times.append((t_end - t_start) * 1000) # ms
        
    avg_update = np.mean(update_times)
    max_update = np.max(update_times)
    
    print(f"⚡ Tempo médio de update da matriz: {avg_update:.3f}ms")
    print(f"⚡ Pior caso: {max_update:.3f}ms")
    
    print("\n=== CONCLUSÃO DE PERFORMANCE ===")
    if max_update < 16: # 16ms = 60 FPS
        print("✅ A estrutura aguenta 60 FPS tranquilamente.")
        print("   Podemos usar NumPy para armazenar o histórico do Heatmap.")
    else:
        print("⚠️ Cuidado! O update da matriz é lento. Precisamos otimizar ou reduzir resolução.")

if __name__ == "__main__":
    test_data_structure_performance()
