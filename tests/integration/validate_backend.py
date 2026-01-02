"""
@category: test
@impact: moderate
@description: Health check de infraestrutura
"""

import sys
import os
import logging
import psycopg2
from dotenv import load_dotenv

# Adiciona diretório raiz
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
load_dotenv()

# Configuração de Logs
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

def get_db_connection():
    try:
        conn = psycopg2.connect(
            dbname=os.getenv("POSTGRES_DB"),
            user=os.getenv("POSTGRES_USER"),
            password=os.getenv("POSTGRES_PASSWORD"),
            host=os.getenv("POSTGRES_HOST", "localhost"),
            port=os.getenv("POSTGRES_PORT", "5432")
        )
        return conn
    except Exception as e:
        logging.error(f"Erro de conexão: {e}")
        logging.warning("⚠️  A validação do banco de dados será ignorada devido a falha de autenticação. Verifique POSTGRES_PASSWORD no .env.")
        return None

def check_table_exists(cursor, table_name):
    try:
        cursor.execute(f"""
            SELECT EXISTS (
                SELECT FROM information_schema.tables 
                WHERE table_schema = 'public' 
                AND table_name = '{table_name}'
            );
        """)
        exists = cursor.fetchone()[0]
        if exists:
            logging.info(f"✅ Tabela '{table_name}' existe.")
            return True
        else:
            logging.error(f"❌ Tabela '{table_name}' NÃO existe.")
            return False
    except Exception as e:
        logging.error(f"Erro ao checar tabela {table_name}: {e}")
        return False

if __name__ == "__main__":
    logging.info("=== Auditoria de Backend (Consolidação) ===")
    conn = get_db_connection()
    if conn:
        try:
            cursor = conn.cursor()
            tables = ['market_ticks', 'orderbook_snapshots']
            for table in tables:
                check_table_exists(cursor, table)
            cursor.close()
            conn.close()
        except Exception as e:
            logging.error(f"Erro durante auditoria: {e}")
    else:
        logging.info("⏭️  Pulando testes de banco de dados.")
