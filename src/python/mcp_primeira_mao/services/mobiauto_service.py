import httpx
from config import URL_AWS_TOKEN, MOBI_SECRET, TIMEOUT, logger
from utils.helpers import extrair_lista_veiculos

class MobiautoService:
    @staticmethod
    async def get_token():
        url = f"{URL_AWS_TOKEN}{MOBI_SECRET}"
        try:
            async with httpx.AsyncClient(timeout=TIMEOUT) as client:
                resp = await client.get(url, follow_redirects=False)
                resp.raise_for_status()
                return resp.text.strip()
        except Exception as e:
            logger.error(f"Erro Token Mobiauto: {e}")
            return None

    @staticmethod
    async def buscar_estoque(dealer_id: str):
        """Busca o estoque de uma loja específica via ID."""
        token = await MobiautoService.get_token()
        if not token: return []
        
        url = f"https://open-api.mobiauto.com.br/api/dealer/{dealer_id}/inventory/v1.0"
        try:
            async with httpx.AsyncClient(timeout=TIMEOUT) as client:
                resp = await client.get(url, headers={"Authorization": f"Bearer {token}"})
                resp.raise_for_status()
                return extrair_lista_veiculos(resp.json())
        except Exception as e:
            logger.error(f"Erro Estoque {dealer_id}: {e}")
            return []

    @staticmethod
    async def buscar_veiculo_por_placa(placa: str, dealer_id: str):
        """Filtra um veículo por placa dentro do estoque de um dealer."""
        estoque = await MobiautoService.buscar_estoque(dealer_id)
        placa_up = placa.upper().replace("-", "").strip()
        return next((v for v in estoque if str(v.get("plate", "")).replace("-", "").upper() == placa_up), {})