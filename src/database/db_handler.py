import os
import logging
import psycopg2
import json
from datetime import datetime
from queue import Queue, Empty
from threading import Thread
from dotenv import load_dotenv

load_dotenv()

class DatabaseHandler:
    _instance = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super(DatabaseHandler, cls).__new__(cls)
            cls._instance._initialized = False
        return cls._instance

    def __init__(self):
        if self._initialized:
            return
        self._initialized = True
        
        self.db_config = {
            "dbname": os.getenv("POSTGRES_DB"),
            "user": os.getenv("POSTGRES_USER"),
            "password": os.getenv("POSTGRES_PASSWORD"),
            "host": os.getenv("POSTGRES_HOST", "localhost"),
            "port": os.getenv("POSTGRES_PORT", "5432")
        }
        
        self.queue = Queue()
        self.running = True
        self.worker_thread = Thread(target=self._worker, daemon=True)
        self.worker_thread.start()
        
        logging.info("DatabaseHandler inicializado com Worker Thread.")

    def get_connection(self):
        try:
            return psycopg2.connect(**self.db_config)
        except Exception as e:
            logging.error(f"Erro ao conectar ao DB: {e}")
            return None

    def validate_snapshot(self, bids, asks):
        """
        Validação básica de integridade dos dados.
        Retorna True se válido, False caso contrário.
        """
        try:
            # Verifica se são listas ou arrays
            if not isinstance(bids, (list, tuple)) and not hasattr(bids, 'tolist'):
                return False
            if not isinstance(asks, (list, tuple)) and not hasattr(asks, 'tolist'):
                return False
            
            # Se ambos vazios, pode ser válido (mercado sem liquidez), mas suspeito
            if len(bids) == 0 and len(asks) == 0:
                logging.warning("Snapshot vazio recebido.")
                return True # Aceitamos, mas logamos

            # Verifica consistência de preços (Best Ask > Best Bid)
            # Precisamos pegar o primeiro elemento de forma segura
            best_bid = bids[0][0] if len(bids) > 0 else None
            best_ask = asks[0][0] if len(asks) > 0 else None

            if best_bid and best_ask and best_bid >= best_ask:
                logging.warning(f"Crossed Market Detectado: Bid {best_bid} >= Ask {best_ask}")
                # Em HFT real isso acontece (arbitragem), então salvamos mesmo assim, 
                # mas o warning serve para auditoria.
            
            return True
        except Exception as e:
            logging.error(f"Erro na validação de snapshot: {e}")
            return False

    def insert_snapshot(self, symbol, bids, asks, timestamp):
        """
        Enfileira um snapshot para inserção.
        timestamp: float (unix timestamp)
        """
        if not self.validate_snapshot(bids, asks):
            logging.error(f"Snapshot inválido rejeitado para {symbol}")
            return

        data = {
            "type": "snapshot",
            "symbol": symbol,
            "bids": bids.tolist() if hasattr(bids, 'tolist') else bids,
            "asks": asks.tolist() if hasattr(asks, 'tolist') else asks,
            "timestamp": datetime.fromtimestamp(timestamp)
        }
        self.queue.put(data)

    def _worker(self):
        """
        Consome a fila e insere no banco em batches.
        """
        conn = self.get_connection()
        if not conn:
            logging.error("Worker não conseguiu conectar ao DB. Parando persistência.")
            return

        cursor = conn.cursor()
        batch_size = 50
        batch = []
        
        while self.running:
            try:
                # Tenta pegar item com timeout para permitir verificação de self.running
                item = self.queue.get(timeout=1)
                batch.append(item)
                
                if len(batch) >= batch_size:
                    self._flush_batch(conn, cursor, batch)
                    batch = []
                    
            except Empty:
                # Se a fila estiver vazia, flush o que tiver
                if batch:
                    self._flush_batch(conn, cursor, batch)
                    batch = []
            except Exception as e:
                logging.error(f"Erro no Worker DB: {e}")
                # Tenta reconectar
                try:
                    if conn: conn.close()
                except:
                    pass
                conn = self.get_connection()
                if conn:
                    cursor = conn.cursor()
                else:
                    # Wait a bit before retrying
                    import time
                    time.sleep(5)

    def _flush_batch(self, conn, cursor, batch):
        if not batch:
            return
            
        try:
            # Separa por tipos se necessário, por enquanto só temos snapshot
            snapshots = [i for i in batch if i['type'] == 'snapshot']
            
            if snapshots:
                args_list = [
                    (s['timestamp'], s['symbol'], json.dumps(s['bids']), json.dumps(s['asks']))
                    for s in snapshots
                ]
                query = """
                    INSERT INTO orderbook_snapshots (time, symbol, bids, asks)
                    VALUES (%s, %s, %s, %s)
                """
                cursor.executemany(query, args_list)
                conn.commit()
                # logging.info(f"Persistidos {len(snapshots)} snapshots.")
                
        except Exception as e:
            logging.error(f"Erro ao inserir batch: {e}")
            conn.rollback()

    def close(self):
        self.running = False
        if self.worker_thread:
            self.worker_thread.join()
