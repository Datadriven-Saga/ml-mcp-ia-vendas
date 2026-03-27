import psycopg2
import pandas as pd
import os
from psycopg2.extras import RealDictCursor
from config import DB_CONFIG, logger

def get_lojas_primeira_mao():
    """
    Consulta o Postgres de forma segura. Se falhar ou vier vazio, busca no lojas_mock.csv.
    """
    query = """
        SELECT loja_nome, dealerid 
        FROM public.loja_ids_mobigestor 
        WHERE loja_nome LIKE %s;
    """
    filtro_seguro = ('%prim%',)

    try:
        with psycopg2.connect(**DB_CONFIG) as conn:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute(query, filtro_seguro)
                res = list(cur.fetchall())
                if res:
                    logger.info(f"Sucesso: {len(res)} lojas encontradas via Postgres.")
                    return res
    except Exception as e:
        logger.error(f"Erro ao consultar Postgres: {e}")

    logger.info("Iniciando fallback: buscando lojas no arquivo lojas_mock.csv...")
    try:
        base_path = os.path.dirname(os.path.abspath(__file__))
        csv_path = os.path.join(base_path, 'lojas_mock.csv')
        
        if not os.path.exists(csv_path):
            csv_path = os.path.join(os.path.dirname(base_path), 'lojas_mock.csv')

        if os.path.exists(csv_path):
            df = pd.read_csv(csv_path)
            return df.to_dict(orient='records')
        else:
            logger.error(f"Arquivo de fallback não encontrado: {csv_path}")
    except Exception as e:
        logger.error(f"Erro ao ler CSV de fallback: {e}")
    
    return []