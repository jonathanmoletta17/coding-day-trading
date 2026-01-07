"""
@category: experiment
@impact: none
@description: Sistema de backtesting para validação de estratégias usando dados históricos do Yahoo Finance
"""

import pandas as pd
import numpy as np
from datetime import datetime, timedelta
import matplotlib.pyplot as plt
from typing import Dict, List, Tuple
import yfinance as yf

# ============================================================================
# OBTENÇÃO DE DADOS HISTÓRICOS
# ============================================================================

def download_historical_data(symbol: str, start_date: str, end_date: str) -> pd.DataFrame:
    """
    Baixa dados históricos do Yahoo Finance
    
    Args:
        symbol: Código B3 (ex: PETR4.SA)
        start_date: Data inicial (YYYY-MM-DD)
        end_date: Data final (YYYY-MM-DD)
    
    Returns:
        DataFrame com OHLCV
    """
    print(f"📥 Baixando dados históricos de {symbol}...")
    
    # Yahoo Finance adiciona .SA para ações brasileiras
    if not symbol.endswith('.SA'):
        symbol = f"{symbol}.SA"
    
    try:
        df = yf.download(symbol, start=start_date, end=end_date, interval='1d') # Changed to 1d for stability, 5m often requires shorter ranges or different API access
        
        if df.empty:
            print(f"❌ Nenhum dado encontrado para {symbol}")
            return None
        
        print(f"✓ {len(df)} candles baixados")
        return df
        
    except Exception as e:
        print(f"❌ Erro ao baixar dados: {e}")
        return None

def calculate_indicators(df: pd.DataFrame) -> pd.DataFrame:
    """
    Calcula indicadores técnicos
    """
    # Fix for yfinance MultiIndex columns if present
    if isinstance(df.columns, pd.MultiIndex):
        df.columns = df.columns.get_level_values(0)

    # RSI
    delta = df['Close'].diff()
    gain = (delta.where(delta > 0, 0)).rolling(window=14).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(window=14).mean()
    rs = gain / loss
    df['RSI'] = 100 - (100 / (1 + rs))
    
    # MACD
    exp1 = df['Close'].ewm(span=12, adjust=False).mean()
    exp2 = df['Close'].ewm(span=26, adjust=False).mean()
    df['MACD'] = exp1 - exp2
    df['MACD_Signal'] = df['MACD'].ewm(span=9, adjust=False).mean()
    
    # Bollinger Bands
    df['BB_Middle'] = df['Close'].rolling(window=20).mean()
    bb_std = df['Close'].rolling(window=20).std()
    df['BB_Upper'] = df['BB_Middle'] + (bb_std * 2)
    df['BB_Lower'] = df['BB_Middle'] - (bb_std * 2)
    
    # Volume médio
    df['Volume_MA'] = df['Volume'].rolling(window=20).mean()
    
    # Volatilidade
    df['Volatility'] = df['Close'].pct_change().rolling(window=20).std() * np.sqrt(252) * 100
    
    return df

# ============================================================================
# ESTRATÉGIAS DE TRADING
# ============================================================================

class Strategy:
    """Classe base para estratégias"""
    
    def __init__(self, name: str):
        self.name = name
    
    def generate_signals(self, df: pd.DataFrame) -> pd.DataFrame:
        """
        Gera sinais de compra/venda
        
        Returns:
            DataFrame com coluna 'Signal': 1 (buy), -1 (sell), 0 (hold)
        """
        raise NotImplementedError

class RSIStrategy(Strategy):
    """
    Estratégia baseada em RSI
    - Compra quando RSI < 30 (oversold)
    - Vende quando RSI > 70 (overbought)
    """
    
    def __init__(self, oversold=30, overbought=70):
        super().__init__("RSI Strategy")
        self.oversold = oversold
        self.overbought = overbought
    
    def generate_signals(self, df: pd.DataFrame) -> pd.DataFrame:
        df['Signal'] = 0
        df.loc[df['RSI'] < self.oversold, 'Signal'] = 1  # Buy
        df.loc[df['RSI'] > self.overbought, 'Signal'] = -1  # Sell
        return df

class MACDStrategy(Strategy):
    """
    Estratégia baseada em MACD
    - Compra quando MACD cruza acima do signal
    - Vende quando MACD cruza abaixo do signal
    """
    
    def __init__(self):
        super().__init__("MACD Strategy")
    
    def generate_signals(self, df: pd.DataFrame) -> pd.DataFrame:
        df['Signal'] = 0
        
        # Detecta cruzamentos
        macd_cross = (df['MACD'] > df['MACD_Signal']) & (df['MACD'].shift(1) <= df['MACD_Signal'].shift(1))
        signal_cross = (df['MACD'] < df['MACD_Signal']) & (df['MACD'].shift(1) >= df['MACD_Signal'].shift(1))
        
        df.loc[macd_cross, 'Signal'] = 1  # Buy
        df.loc[signal_cross, 'Signal'] = -1  # Sell
        
        return df

class BollingerStrategy(Strategy):
    """
    Estratégia baseada em Bollinger Bands
    - Compra quando preço toca banda inferior
    - Vende quando preço toca banda superior
    """
    
    def __init__(self):
        super().__init__("Bollinger Bands Strategy")
    
    def generate_signals(self, df: pd.DataFrame) -> pd.DataFrame:
        df['Signal'] = 0
        
        df.loc[df['Close'] <= df['BB_Lower'], 'Signal'] = 1  # Buy
        df.loc[df['Close'] >= df['BB_Upper'], 'Signal'] = -1  # Sell
        
        return df

class CombinedStrategy(Strategy):
    """
    Estratégia combinada (RSI + MACD + Volume)
    Mais conservadora, só opera quando múltiplos sinais concordam
    """
    
    def __init__(self):
        super().__init__("Combined Strategy")
    
    def generate_signals(self, df: pd.DataFrame) -> pd.DataFrame:
        df['Signal'] = 0
        
        # Buy conditions (todos devem ser True)
        buy_rsi = df['RSI'] < 35
        buy_macd = (df['MACD'] > df['MACD_Signal']) & (df['MACD'].shift(1) <= df['MACD_Signal'].shift(1))
        buy_volume = df['Volume'] > df['Volume_MA']
        
        df.loc[buy_rsi & buy_macd & buy_volume, 'Signal'] = 1
        
        # Sell conditions
        sell_rsi = df['RSI'] > 65
        sell_macd = (df['MACD'] < df['MACD_Signal']) & (df['MACD'].shift(1) >= df['MACD_Signal'].shift(1))
        
        df.loc[sell_rsi & sell_macd, 'Signal'] = -1
        
        return df

# ============================================================================
# BACKTESTING ENGINE
# ============================================================================

class Backtester:
    """
    Motor de backtesting
    Simula trades baseado em sinais da estratégia
    """
    
    def __init__(self, initial_capital: float = 10000):
        self.initial_capital = initial_capital
        self.capital = initial_capital
        self.position = 0  # Quantidade de ações
        self.entry_price = 0
        self.trades = []
        
        # Custos
        self.commission = 0.0005  # 0.05% por operação
        self.slippage = 0.0010  # 0.1% de slippage
        
        # Gestão de risco
        self.stop_loss_pct = 0.02  # 2% stop loss
        self.take_profit_pct = 0.04  # 4% take profit
    
    def run(self, df: pd.DataFrame, strategy: Strategy) -> Dict:
        """
        Executa backtest completo
        
        Returns:
            Dicionário com métricas de performance
        """
        # print(f"\n{'='*80}")
        # print(f"🔄 EXECUTANDO BACKTEST: {strategy.name}")
        # print(f"{'='*80}")
        # print(f"Período: {df.index[0]} até {df.index[-1]}")
        # print(f"Capital Inicial: R$ {self.initial_capital:,.2f}")
        # print()
        
        # Gera sinais
        df = strategy.generate_signals(df)
        
        # Simula trades
        for i in range(len(df)):
            row = df.iloc[i]
            
            # Se tem posição aberta, verifica stop/take
            if self.position != 0:
                self._check_exit(row)
            
            # Verifica novos sinais
            if row['Signal'] == 1 and self.position == 0:
                self._open_long(row)
            elif row['Signal'] == -1 and self.position > 0:
                self._close_position(row)
        
        # Fecha posição final se houver
        if self.position > 0:
            last_row = df.iloc[-1]
            self._close_position(last_row)
        
        # Calcula métricas
        metrics = self._calculate_metrics()
        
        # Mostra resultados
        # self._print_results(metrics)
        
        return metrics
    
    def _open_long(self, row):
        """Abre posição de compra"""
        # Preço com slippage
        price = row['Close'] * (1 + self.slippage)
        
        # Quantidade baseada em capital disponível
        max_value = self.capital * 0.95  # Usa 95% do capital
        quantity = int(max_value / price)
        quantity = (quantity // 100) * 100  # Lote de 100
        
        if quantity < 100:
            return  # Capital insuficiente
        
        # Custo da operação
        cost = quantity * price
        commission = cost * self.commission
        total_cost = cost + commission
        
        if total_cost > self.capital:
            return
        
        # Executa
        self.position = quantity
        self.entry_price = price
        self.capital -= total_cost
        
        self.trades.append({
            'type': 'ENTRY',
            'date': row.name,
            'price': price,
            'quantity': quantity,
            'value': cost,
            'commission': commission
        })
    
    def _close_position(self, row):
        """Fecha posição"""
        if self.position == 0:
            return
        
        # Preço de saída com slippage
        exit_price = row['Close'] * (1 - self.slippage)
        
        # Valor da venda
        value = self.position * exit_price
        commission = value * self.commission
        net_value = value - commission
        
        # Lucro/prejuízo
        profit = net_value - (self.position * self.entry_price)
        profit_pct = (exit_price / self.entry_price - 1) * 100
        
        # Atualiza capital
        self.capital += net_value
        
        self.trades.append({
            'type': 'EXIT',
            'date': row.name,
            'price': exit_price,
            'quantity': self.position,
            'value': value,
            'commission': commission,
            'profit': profit,
            'profit_pct': profit_pct
        })
        
        # Zera posição
        self.position = 0
        self.entry_price = 0
    
    def _check_exit(self, row):
        """Verifica stop loss e take profit"""
        if self.position == 0:
            return
        
        current_price = row['Close']
        change = (current_price / self.entry_price - 1)
        
        # Stop loss
        if change <= -self.stop_loss_pct:
            self._close_position(row)
            return
        
        # Take profit
        if change >= self.take_profit_pct:
            self._close_position(row)
            return
    
    def _calculate_metrics(self) -> Dict:
        """Calcula métricas de performance"""
        exits = [t for t in self.trades if t['type'] == 'EXIT']
        
        if not exits:
            return {
                'final_capital': self.capital,
                'total_return': 0,
                'num_trades': 0,
                'win_rate': 0,
                'avg_profit': 0,
                'sharpe_ratio': 0,
                'max_drawdown': 0,
                'profit_factor': 0,
                'winning_trades': 0,
                'losing_trades': 0,
                'avg_win': 0,
                'avg_loss': 0
            }
        
        # Trades vencedores e perdedores
        winning_trades = [t for t in exits if t['profit'] > 0]
        losing_trades = [t for t in exits if t['profit'] <= 0]
        
        # Retornos
        returns = [t['profit_pct'] for t in exits]
        
        # Métricas
        total_return = (self.capital / self.initial_capital - 1) * 100
        win_rate = len(winning_trades) / len(exits) * 100 if exits else 0
        avg_profit = np.mean([t['profit'] for t in exits]) if exits else 0
        
        # Sharpe ratio
        if len(returns) > 1:
            sharpe_ratio = np.mean(returns) / np.std(returns) * np.sqrt(252)
        else:
            sharpe_ratio = 0
        
        # Max drawdown
        capital_curve = [self.initial_capital]
        current_capital = self.initial_capital
        
        for trade in self.trades:
            if trade['type'] == 'ENTRY':
                current_capital -= (trade['value'] + trade['commission'])
            elif trade['type'] == 'EXIT':
                current_capital += (trade['value'] - trade['commission'])
            capital_curve.append(current_capital)
        
        peak = capital_curve[0]
        max_dd = 0
        for value in capital_curve:
            if value > peak:
                peak = value
            dd = (peak - value) / peak
            if dd > max_dd:
                max_dd = dd
        
        return {
            'final_capital': self.capital,
            'total_return': total_return,
            'num_trades': len(exits),
            'winning_trades': len(winning_trades),
            'losing_trades': len(losing_trades),
            'win_rate': win_rate,
            'avg_profit': avg_profit,
            'avg_win': np.mean([t['profit'] for t in winning_trades]) if winning_trades else 0,
            'avg_loss': np.mean([t['profit'] for t in losing_trades]) if losing_trades else 0,
            'sharpe_ratio': sharpe_ratio,
            'max_drawdown': max_dd * 100,
            'profit_factor': abs(sum(t['profit'] for t in winning_trades) / sum(t['profit'] for t in losing_trades)) if losing_trades and sum(t['profit'] for t in losing_trades) != 0 else float('inf')
        }
    
    def _print_results(self, metrics: Dict):
        """Imprime resultados do backtest"""
        print(f"\n{'='*80}")
        print("📊 RESULTADOS DO BACKTEST")
        print(f"{'='*80}")
        print(f"Capital Final: R$ {metrics['final_capital']:,.2f}")
        print(f"Retorno Total: {metrics['total_return']:+.2f}%")
        print(f"Número de Trades: {metrics['num_trades']}")
        print(f"Trades Vencedores: {metrics['winning_trades']}")
        print(f"Trades Perdedores: {metrics['losing_trades']}")
        print(f"Taxa de Acerto: {metrics['win_rate']:.1f}%")
        print(f"Lucro Médio: R$ {metrics['avg_profit']:.2f}")
        print(f"Ganho Médio: R$ {metrics['avg_win']:.2f}")
        print(f"Perda Média: R$ {metrics['avg_loss']:.2f}")
        print(f"Profit Factor: {metrics['profit_factor']:.2f}")
        print(f"Sharpe Ratio: {metrics['sharpe_ratio']:.2f}")
        print(f"Max Drawdown: {metrics['max_drawdown']:.2f}%")
        print(f"{'='*80}\n")

# ============================================================================
# EXECUÇÃO PRINCIPAL
# ============================================================================


def run_comprehensive_analysis():
    """
    Executa análise abrangente de múltiplos ativos e períodos.
    """
    print("""
╔══════════════════════════════════════════════════════════════════════════════╗
║             🚀 ANÁLISE ABRANGENTE DE POTENCIAL DE TRADING                    ║
╚══════════════════════════════════════════════════════════════════════════════╝
    """)
    
    # Configuração do Teste
    assets = ['PETR4', 'VALE3', 'ITUB4', 'BBDC4', 'WEGE3']
    initial_capital = 10000
    
    # Definição de Cenários (Periodo, Intervalo)
    scenarios = [
        {"name": "Curto Prazo (1 Mês)", "days": 30, "interval": "1h"},
        {"name": "Médio Prazo (6 Meses)", "days": 180, "interval": "1d"},
        {"name": "Longo Prazo (1 Ano)", "days": 365, "interval": "1d"},
        {"name": "Histórico (5 Anos)", "days": 365*5, "interval": "1d"},
    ]
    
    # Estratégias a testar
    strategies = [
        MACDStrategy(),
        RSIStrategy(),
        CombinedStrategy() # Adicionado para ver se performa melhor no longo prazo
    ]
    
    results_summary = []

    for asset in assets:
        print(f"\n📦 ATIVO: {asset}")
        
        for scenario in scenarios:
            print(f"  📅 Cenário: {scenario['name']}")
            
            end_date = datetime.now()
            start_date = end_date - timedelta(days=scenario['days'])
            
            # Formato strings
            s_date = start_date.strftime('%Y-%m-%d')
            e_date = end_date.strftime('%Y-%m-%d')
            
            # Baixa dados
            try:
                # Ajuste de intervalo para yfinance
                # 1h só tem dados recentes (730 dias max)
                interval = scenario['interval']
                if interval == '1h' and scenario['days'] > 700:
                    interval = '1d' # Fallback
                
                df = yf.download(f"{asset}.SA", start=s_date, end=e_date, interval=interval, progress=False)
                
                if df.empty or len(df) < 50:
                    print(f"     ⚠️ Dados insuficientes para {asset} no período.")
                    continue
                
                # Prepara dados
                if isinstance(df.columns, pd.MultiIndex):
                    df.columns = df.columns.get_level_values(0)
                
                df = calculate_indicators(df)
                df = df.dropna()
                
                # Roda estratégias
                best_return = -999
                best_strat = ""
                
                for strategy in strategies:
                    backtester = Backtester(initial_capital=initial_capital)
                    
                    # Silencia output detalhado do run para não poluir o console nesse loop massivo
                    # (Poderíamos modificar a classe Backtester para ter um modo 'quiet', mas vamos capturar apenas o resultado)
                    # O print dentro do run vai sair, mas ok.
                    
                    metrics = backtester.run(df, strategy)
                    
                    if metrics['total_return'] > best_return:
                        best_return = metrics['total_return']
                        best_strat = strategy.name
                    
                    results_summary.append({
                        "asset": asset,
                        "scenario": scenario['name'],
                        "strategy": strategy.name,
                        "return": metrics['total_return'],
                        "profit_factor": metrics['profit_factor'],
                        "trades": metrics['num_trades'],
                        "win_rate": metrics['win_rate'],
                        "max_dd": metrics['max_drawdown']
                    })
                
                print(f"     🏆 Melhor no período: {best_strat} ({best_return:+.2f}%)")
                
            except Exception as e:
                print(f"     ❌ Erro: {e}")

    # ==========================
    # GERA RELATÓRIO FINAL
    # ==========================
    print("\n" + "="*80)
    print("📋 RELATÓRIO CONSOLIDADO DE POTENCIAL")
    print("="*80)
    
    # Converte para DataFrame para facilitar análise
    df_res = pd.DataFrame(results_summary)
    
    if df_res.empty:
        print("Nenhum resultado gerado.")
        return

    # Agrupa por Cenário
    print("\n--- MÉDIA DE RETORNO POR CENÁRIO (Todas Estratégias) ---")
    print(df_res.groupby("scenario")["return"].mean())
    
    print("\n--- MELHOR ESTRATÉGIA GERAL (Média de Retorno) ---")
    print(df_res.groupby("strategy")["return"].mean().sort_values(ascending=False))
    
    print("\n--- ATIVO MAIS LUCRATIVO (Média) ---")
    print(df_res.groupby("asset")["return"].mean().sort_values(ascending=False))
    
    # Projeção Financeira Simples
    avg_monthly_return = df_res[df_res['scenario'] == "Curto Prazo (1 Mês)"]['return'].mean()
    if pd.isna(avg_monthly_return): avg_monthly_return = 0
    
    print("\n💰 PROJEÇÃO FINANCEIRA SIMPLIFICADA (Baseado na média mensal de curto prazo)")
    print(f"Média Mensal Estimada: {avg_monthly_return:.2f}%")
    
    capital = initial_capital
    print(f"\nEvolução Teórica de R$ {capital:,.2f} (sem reinvestimento, juros compostos):")
    for m in [1, 3, 6, 12]:
        proj = capital * (1 + (avg_monthly_return/100) * m)
        print(f"  {m} Meses: R$ {proj:,.2f} (Lucro: R$ {proj-capital:,.2f})")

    print("\n⚠️ NOTA: Resultados passados não garantem lucros futuros. O backtest utiliza dados históricos.")


if __name__ == "__main__":
    run_comprehensive_analysis()

