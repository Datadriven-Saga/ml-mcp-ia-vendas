"""
Serviço de busca de estoque via Lambda AWS (fonte primária).

A Lambda recebe POST com {"name": "<cidade>"} e retorna lista de veículos
com os campos: id, dealerid, loja, cidade, uf, versao, modelo, marca, url, url_imagem.

O retorno é normalizado para o mesmo formato de simplificar_veiculo do InventoryAggregator,
permitindo uso transparente em toda a pipeline de cards.
"""

import httpx
import json
from config import LAMBDA_ESTOQUE_URL, logger

LAMBDA_TIMEOUT = 12


class LambdaInventoryService:

    @staticmethod
    def _normalizar(v: dict) -> dict:
        """Converte um veículo da Lambda no formato interno usado pelo widget."""
        vid   = str(v.get("id") or "")
        marca = str(v.get("marca")  or "")
        modelo= str(v.get("modelo") or "")
        versao= str(v.get("versao") or "")
        loja  = str(v.get("loja")   or "")
        img   = str(v.get("url_imagem") or "")
        link  = str(v.get("url")        or "")

        return {
            "id":            vid,
            "makeName":      marca,
            "modelName":     modelo,
            "trimName":      versao,
            "modelYear":     str(v.get("ano") or ""),
            "salePrice":     0.0,
            "km":            str(v.get("km") or ""),
            "colorName":     str(v.get("cor") or ""),
            "plate":         "",
            "loja_unidade":  loja,
            "carroceria":    "",
            "transmissao":   "",
            "combustivel":   "",
            "portas":        "",
            "opcionais":     [],
            "url_imagem":    img,
            "imagens_urls":  [img] if img else [],
            "preco_formatado": str(v.get("preco_formatado") or ""),
            "link_ofertas":  link,
            "titulo_card":   f"{marca} {modelo} {versao}".strip(),
        }

    @staticmethod
    async def buscar_por_cidade(cidade: str) -> list:
        """
        Chama a Lambda com {"name": "<cidade>"} e retorna lista normalizada.
        Retorna [] se a Lambda não estiver configurada, falhar ou retornar vazio.
        """
        if not LAMBDA_ESTOQUE_URL:
            logger.debug("[LambdaInventoryService] LAMBDA_ESTOQUE_URL não configurada — pulando")
            return []

        payload = {"name": cidade}
        logger.info(f"[LambdaInventoryService] POST {LAMBDA_ESTOQUE_URL} | payload={payload}")

        try:
            async with httpx.AsyncClient(timeout=LAMBDA_TIMEOUT) as client:
                resp = await client.post(LAMBDA_ESTOQUE_URL, json=payload)
                resp.raise_for_status()
        except Exception as exc:
            logger.error(f"[LambdaInventoryService] Falha na chamada | {type(exc).__name__}: {exc}")
            return []

        # Suporta respostas diretas (lista), {"data": [...]}, e proxy Lambda {"body": "..."}
        try:
            raw = resp.json()
        except Exception:
            logger.error(f"[LambdaInventoryService] Resposta não é JSON | body={resp.text[:200]}")
            return []

        # Lambda proxy format: {"statusCode": 200, "body": "[{...}]"}
        if isinstance(raw, dict) and "body" in raw:
            body = raw["body"]
            if isinstance(body, str):
                try:
                    raw = json.loads(body)
                except Exception:
                    raw = []
            else:
                raw = body

        # {"data": [...]} ou {"items": [...]} ou {"veiculos": [...]}
        if isinstance(raw, dict):
            for key in ("data", "items", "veiculos", "vehicles", "results"):
                if isinstance(raw.get(key), list):
                    raw = raw[key]
                    break

        if not isinstance(raw, list):
            logger.warning(f"[LambdaInventoryService] Formato inesperado: {type(raw)}")
            return []

        veiculos = [LambdaInventoryService._normalizar(v) for v in raw if isinstance(v, dict)]
        logger.info(f"[LambdaInventoryService] {len(veiculos)} veículos recebidos para '{cidade}'")
        return veiculos
