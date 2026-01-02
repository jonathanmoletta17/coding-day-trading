"""
@category: tool
@impact: low
@description: Diagnóstico: Valida orderbook depth
"""

import MetaTrader5 as mt5
import time
import pandas as pd

def check_order_book(symbol="PETR4"):
    print(f"=== VERIFICAÇÃO DE ORDER BOOK (L2): {symbol} ===")
    
    if not mt5.initialize():
        print("❌ Falha ao inicializar MT5")
        return

    if not mt5.symbol_select(symbol, True):
        print(f"❌ Símbolo {symbol} não encontrado.")
        mt5.shutdown()
        return

    # Habilita a assinatura do livro de ofertas
    print(f"1. Assinando livro de ofertas para {symbol}...")
    if mt5.market_book_add(symbol):
        print(f"✅ Assinatura realizada com sucesso para {symbol}")
    else:
        print(f"❌ Falha ao assinar livro (market_book_add). Erro: {mt5.last_error()}")
        print("   Isso pode significar que a corretora não fornece dados L2 via MT5.")
        mt5.shutdown()
        return

    # Aguarda um pouco para receber dados
    time.sleep(2)

    print("\n2. Obtendo snapshot do livro...")
    book = mt5.market_book_get(symbol)
    
    if book:
        print(f"✅ Livro recebido! Profundidade: {len(book)} níveis")
        
        # Converte para DataFrame para visualização bonita
        df = pd.DataFrame(list(book), columns=book[0]._asdict().keys())
        
        # Tipo de ordem: 1=Sell (Ask), 2=Buy (Bid) - *Verificar documentação MQL5, pode variar
        # BOOK_TYPE_SELL = 1
        # BOOK_TYPE_BUY = 2
        
        print("\n--- TOP 5 OFERTAS DE COMPRA (BID) ---")
        # Alguns MT5 não retornam volume_real, apenas volume
        cols = ['price', 'volume']
        if 'volume_real' in df.columns:
            cols.append('volume_real')
            
        bids = df[df['type'] == 2].sort_values('price', ascending=False).head(5)
        print(bids[cols])
        
        print("\n--- TOP 5 OFERTAS DE VENDA (ASK) ---")
        asks = df[df['type'] == 1].sort_values('price', ascending=True).head(5)
        print(asks[cols])
        
        print("\nCONCLUSÃO:")
        if len(df) > 2: # Geralmente Nível 1 tem só 1 bid e 1 ask
            print("🌟 SUCESSO TOTAL: Temos acesso à profundidade do mercado (L2)!")
            print("   Podemos construir o Heatmap.")
        else:
            print("⚠️  AVISO: Recebemos dados do livro, mas parece ser apenas Topo do Livro (Nível 1).")
            print("   Verifique se o mercado está aberto ou se o ativo tem liquidez.")

    else:
        print("❌ market_book_get retornou vazio (None).")
        print(f"   Erro: {mt5.last_error()}")
    
    # Desassina
    mt5.market_book_release(symbol)
    mt5.shutdown()

if __name__ == "__main__":
    symbol_to_test = input("Digite o ativo para testar (padrão PETR4): ").strip()
    if not symbol_to_test:
        symbol_to_test = "PETR4"
    check_order_book(symbol_to_test)
