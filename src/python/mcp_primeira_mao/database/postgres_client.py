import psycopg2
from psycopg2.extras import RealDictCursor
from config import DB_CONFIG, logger

def get_lojas_primeira_mao():
    """
    Consulta o banco de dados para buscar lojas que contenham 
    'primeira mão' ou 'sn' no nome.
    """
    query = """
        SELECT loja_nome, dealerid 
        FROM public.loja_ids_mobigestor
        WHERE loja_nome ILIKE ANY (ARRAY['%primeira%', '%mão%', '%mao%', '%sn%']);
    """
    try:
        # O 'with' garante que a conexão feche sozinha após a consulta
        with psycopg2.connect(**DB_CONFIG) as conn:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute(query)
                # O RealDictCursor já retorna algo muito parecido com dict, 
                # mas transformar em lista de dicts garante compatibilidade total com o JSON do MCP
                return list(cur.fetchall())
    except Exception as e:
        logger.error(f"Erro ao consultar Postgres: {e}")
        return []