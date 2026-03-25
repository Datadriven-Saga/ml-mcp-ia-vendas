import os
import logging
from datetime import datetime

import httpx
import psycopg2
from psycopg2.extras import RealDictCursor
from dotenv import load_dotenv

load_dotenv()

# Logger
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler(
            f"saga_api_{datetime.now().strftime('%Y%m%d')}.log"
        ),
    ],
)
logger = logging.getLogger(__name__)

# Configurações
DB_CONFIG = {
    "dbname":   os.getenv("DB_NAME"),
    "user":     os.getenv("DB_USER"),
    "password": os.getenv("DB_PASSWORD"),
    "host":     os.getenv("DB_HOST"),
    "port":     os.getenv("DB_PORT"),
}

URL_AWS_TOKEN        = os.getenv("URL_AWS_TOKEN", "")          
MOBI_SECRET          = os.getenv("MOBI_SECRET", "")
MOBI_DEALER_ID       = os.getenv("MOBI_DEALER_ID", "")         
PRECIFICACAO_API_URL = os.getenv("PRECIFICACAO_API_URL", "")   
TIMEOUT              = int(os.getenv("API_TIMEOUT", "10"))

MOBI_INVENTORY_URL = (
    f"https://open-api.mobiauto.com.br/api/dealer/{MOBI_DEALER_ID}/inventory/v1.0"
)

# LISTA LOJAS  

def lista_lojas() -> list[dict]:
    """
    Consulta o Postgres e retorna todas as lojas da Primeira Mão Saga
    com seus respectivos dealerids.
    """
    logger.info("Consultando lojas no banco de dados...")
    query = """
        SELECT loja_nome, dealerid
        FROM public.loja_ids_mobigestor
        WHERE
            loja_nome ILIKE '%primeira%' OR
            loja_nome ILIKE '%mão%'      OR
            loja_nome ILIKE '%mao%'      OR
            loja_nome ILIKE '%sn%';
    """
    try:
        with psycopg2.connect(**DB_CONFIG) as conn:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute(query)
                results = [dict(r) for r in cur.fetchall()]
                logger.info(f"{len(results)} loja(s) encontrada(s).")
                return results
    except Exception as e:
        logger.error(f"Falha ao consultar lojas: {e}")
        return []

# TOKEN MOBIAUTO

async def _get_mobi_token() -> str | None:
    """Obtém o token Bearer dinâmico da Mobiauto via AWS Lambda."""
    url = f"{URL_AWS_TOKEN}{MOBI_SECRET}"
    logger.info("Buscando token Mobiauto...")
    try:
        async with httpx.AsyncClient(timeout=TIMEOUT) as client:
            resp = await client.get(url, follow_redirects=False)
            resp.raise_for_status()
            token = resp.text.strip()
            logger.info("Token Mobiauto obtido com sucesso.")
            return token
    except httpx.HTTPStatusError as e:
        logger.error(f"Erro HTTP ao buscar token Mobiauto: {e.response.status_code}")
    except Exception as e:
        logger.error(f"Erro inesperado ao buscar token Mobiauto: {e}")
    return None


#  BUSCA ESTOQUE POR LOJA  

async def busca_estoque_loja(dealer_id: str) -> list[dict]:
    """
    Retorna o inventário completo de uma loja Mobiauto pelo dealerid.
    A URL do inventário usa o MOBI_DEALER_ID do .env; o dealer_id
    recebido é registrado em log para rastreabilidade.
    """
    logger.info(f"Buscando estoque da loja dealerid={dealer_id}...")
    token = await _get_mobi_token()
    if not token:
        logger.error("Não foi possível obter token Mobiauto — abortando busca de estoque.")
        return []

    try:
        async with httpx.AsyncClient(timeout=TIMEOUT) as client:
            resp = await client.get(
                MOBI_INVENTORY_URL,
                headers={"Authorization": f"Bearer {token}"},
            )
            resp.raise_for_status()
            data = resp.json()
        if isinstance(data, list):
            veiculos = data
        else:
            veiculos = (
                data.get("imagem")
                or data.get("data")
                or data.get("items")
                or data.get("results")
                or []
            )

        logger.info(f"{len(veiculos)} veículo(s) encontrado(s) para dealerid={dealer_id}.")
        return veiculos

    except httpx.HTTPStatusError as e:
        logger.error(f"Erro HTTP ao buscar estoque Mobiauto: {e.response.status_code}")
    except Exception as e:
        logger.error(f"Erro ao buscar estoque: {e}")
    return []

#  BUSCA FIPE  

async def busca_fipe(placa: str) -> list[dict]:
    """
    Consulta a FIPE de um veículo pela placa.
    Retorna lista de dicts com: placa, codigo_fipe, valor_fipe, marca,
    modelo, versao, carroceria, combustivel, ano_modelo.
    """
    placa = placa.upper().strip()
    logger.info(f"Buscando FIPE para placa {placa}...")
    url = f"{PRECIFICACAO_API_URL}/fipe"
    try:
        async with httpx.AsyncClient(timeout=TIMEOUT) as client:
            resp = await client.get(url, params={"placa": placa})
            resp.raise_for_status()
            data = resp.json()
            logger.info(f"FIPE retornada com sucesso para placa {placa}.")
            # Normaliza para sempre retornar lista
            return data if isinstance(data, list) else [data]
    except httpx.HTTPStatusError as e:
        logger.error(f"Erro HTTP ao buscar FIPE ({placa}): {e.response.status_code}")
    except Exception as e:
        logger.error(f"Erro ao buscar FIPE ({placa}): {e}")
    return []

#  PRECIFICA  

async def precifica(
    placa: str,
    valor_fipe: str,
    marca: str,
    modelo: str,
    versao: str,               # campo "versão" no n8n — enviado como "versao" na query string
    tipo_combustivel: str,
    ano_modelo: str,
    uf: str,
    tipo: str,
    km: str,
    codigo_fipe: str,
    cor: str,
    existe_zero_km: str,
    tipo_carroceria: str,
) -> dict:
    """
    Consulta a precificação de compra de um veículo seminovo.
    Equivale ao nó 'precifica' do n8n: GET /carro/compra?...
    """
    logger.info(f"Precificando veículo placa={placa}...")
    url = f"{PRECIFICACAO_API_URL}/carro/compra"
    params = {
        "placa":            placa.upper().strip(),
        "valor_fipe":       str(valor_fipe),
        "marca":            marca,
        "modelo":           modelo,
        "versao":           versao,           # a API recebe "versao" sem acento na query string
        "tipo_combustivel": tipo_combustivel,
        "ano_modelo":       str(ano_modelo),
        "uf":               uf.upper(),
        "tipo":             tipo,
        "km":               str(km),
        "codigo_fipe":      codigo_fipe,
        "cor":              cor,
        "existe_zero_km":   existe_zero_km,
        "tipo_carroceria":  tipo_carroceria,
    }
    try:
        async with httpx.AsyncClient(timeout=TIMEOUT) as client:
            resp = await client.get(url, params=params)
            resp.raise_for_status()
            data = resp.json()
            logger.info("Precificação retornada com sucesso.")
            return data if isinstance(data, dict) else {"resultado": data}
    except httpx.HTTPStatusError as e:
        logger.error(f"Erro HTTP ao precificar ({placa}): {e.response.status_code}")
    except Exception as e:
        logger.error(f"Erro ao precificar ({placa}): {e}")
    return {}

# BUSCA VEÍCULO COM IMAGENS  

async def busca_veiculo(placa: str, dealer_id: str) -> dict:
    """
    Busca os dados completos e imagens de um veículo específico.
    Equivale ao fluxo n8n: pega token → busca inventário → filtra pela placa.

    Retorna o objeto do veículo encontrado (com campo 'plate' == placa)
    ou dict vazio se não encontrado.
    """
    placa = placa.upper().strip()
    logger.info(f"Buscando veículo placa={placa} na loja dealerid={dealer_id}...")

    inventario = await busca_estoque_loja(dealer_id)
    if not inventario:
        logger.warning(f"Inventário vazio ou inacessível para dealerid={dealer_id}.")
        return {}

    # O campo de placa na Mobiauto é "plate"
    veiculo = next(
        (v for v in inventario if str(v.get("plate", "")).upper() == placa),
        None,
    )

    if veiculo:
        logger.info(f"Veículo {placa} encontrado.")
    else:
        logger.warning(f"Placa {placa} não encontrada no inventário da loja {dealer_id}.")

    return veiculo or {}


# Teste local

if __name__ == "__main__":
    import asyncio

    async def _smoke_test():
        print("\n=== LISTA LOJAS ===")
        lojas = lista_lojas()
        for l in lojas:
            print(l)

        placa_teste = "QCK3E36"

        print(f"\n=== BUSCA FIPE ({placa_teste}) ===")
        fipe = await busca_fipe(placa_teste)
        print(fipe)

        if fipe:
            f = fipe[0]
            print(f"\n=== PRECIFICA ({placa_teste}) ===")
            resultado = await precifica(
                placa           = f["placa"],
                valor_fipe      = f["valor_fipe"],
                marca           = f["marca"],
                modelo          = f["modelo"],
                versao          = f["versao"],
                tipo_combustivel= f["combustivel"],
                ano_modelo      = f["ano_modelo"],
                uf              = "GO",
                tipo            = "Passeio",
                km              = "15000",
                codigo_fipe     = f["codigo_fipe"],
                cor             = "Preta",
                existe_zero_km  = "Não",
                tipo_carroceria = f["carroceria"],
            )
            print(resultado)

        if lojas:
            dealer_id = str(lojas[0]["dealerid"])
            print(f"\n=== ESTOQUE LOJA ({dealer_id}) ===")
            estoque = await busca_estoque_loja(dealer_id)
            print(f"{len(estoque)} veículos retornados.")

            print(f"\n=== BUSCA VEÍCULO + IMAGENS ({placa_teste}) ===")
            veiculo = await busca_veiculo(placa_teste, dealer_id)
            print(veiculo)

    asyncio.run(_smoke_test())