"""
Serviço de busca de estoque via Lambda AWS (fonte primária).

A Lambda recebe POST com {"name": "<cidade>"} e retorna lista de veículos
com os campos: id, dealerid, loja, cidade, uf, versao, modelo, marca, url, url_imagem.

O retorno é normalizado para o mesmo formato de simplificar_veiculo do InventoryAggregator,
permitindo uso transparente em toda a pipeline de cards.
"""

import httpx
import json
import math
from config import LAMBDA_ESTOQUE_URL, LAMBDA_API_KEY, logger

LAMBDA_TIMEOUT = 30


def _s(val) -> str:
    """Converte para string ignorando None e NaN do pandas."""
    if val is None:
        return ""
    try:
        if isinstance(val, float) and math.isnan(val):
            return ""
    except Exception:
        pass
    return str(val).strip()


def _f(val) -> float:
    """Converte para float ignorando None e NaN."""
    if val is None:
        return 0.0
    try:
        f = float(val)
        return 0.0 if math.isnan(f) else f
    except (TypeError, ValueError):
        return 0.0


class LambdaInventoryService:

    @staticmethod
    def _normalizar(v: dict) -> dict:
        """Converte um veículo da Lambda no formato interno usado pelo widget."""
        vid    = _s(v.get("id"))
        marca  = _s(v.get("marca"))
        modelo = _s(v.get("modelo"))
        versao = _s(v.get("versao_tabela")) or _s(v.get("versao"))
        loja   = _s(v.get("loja"))
        img    = _s(v.get("url_imagem"))
        link   = _s(v.get("url"))
        ano    = _s(v.get("model_year")) or _s(v.get("ano"))
        km     = _s(v.get("km"))
        price  = _f(v.get("price")) or _f(v.get("salePrice"))

        preco_fmt = (
            _s(v.get("preco_formatado"))
            or (
                f"R$ {price:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
                if price > 0 else ""
            )
        )

        return {
            "id":              vid,
            "makeName":        marca,
            "modelName":       modelo,
            "trimName":        versao,
            "versao_direta":   _s(v.get("versao_direta")),
            "modelYear":       ano,
            "salePrice":       price,
            "km":              km,
            "colorName":       _s(v.get("cor")) or _s(v.get("colorName")),
            "plate":           "",
            "loja_unidade":    loja,
            "cidade":          _s(v.get("cidade")),
            "uf":              _s(v.get("uf")),
            "dealerid":        _s(v.get("dealerid")),
            "carroceria":      "",
            "transmissao":     "",
            "combustivel":     "",
            "portas":          "",
            "opcionais":       [],
            "url_imagem":      img,
            "imagens_urls":    [img] if img else [],
            "preco_formatado": preco_fmt,
            "link_ofertas":    link,
            "titulo_card":     f"{marca} {modelo} {versao}".strip(),
        }

    @staticmethod
    async def buscar(cidade: str, filtros: dict | None = None) -> list:
        """
        Chama a Lambda com cidade + filtros opcionais e retorna lista normalizada.
        filtros aceitos: marca, modelo, versao, preco_min, preco_max, km_max, ano_min, ano_max
        Retorna [] se a Lambda não estiver configurada, falhar ou retornar vazio.
        """
        if not LAMBDA_ESTOQUE_URL:
            logger.warning("[LambdaInventoryService] LAMBDA_ESTOQUE_URL não configurada — usando fallback Mobiauto")
            return []

        if "console.aws.amazon.com" in LAMBDA_ESTOQUE_URL:
            logger.error("[LambdaInventoryService] URL INVÁLIDA: use a URL do API Gateway, não do console AWS")
            return []

        params = {"cidade": cidade}
        if filtros:
            params.update({k: v for k, v in filtros.items() if v is not None})

        headers = {"x-api-key": LAMBDA_API_KEY}
        logger.info(f"[LambdaInventoryService] >>> GET {LAMBDA_ESTOQUE_URL} | params={params}")

        try:
            async with httpx.AsyncClient(timeout=LAMBDA_TIMEOUT) as client:
                resp = await client.get(LAMBDA_ESTOQUE_URL, params=params, headers=headers)
                logger.info(f"[LambdaInventoryService] <<< HTTP {resp.status_code}")
                resp.raise_for_status()
        except Exception as exc:
            logger.error(f"[LambdaInventoryService] FALHA | {type(exc).__name__}: {exc} — usando fallback Mobiauto")
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

        if raw:
            logger.info(f"[LambdaInventoryService] RAW[0] keys={list(raw[0].keys())}")
            logger.info(f"[LambdaInventoryService] RAW[0] values={raw[0]}")

        veiculos = [LambdaInventoryService._normalizar(v) for v in raw if isinstance(v, dict)]
        logger.info(f"[LambdaInventoryService] {len(veiculos)} veículos recebidos")
        return veiculos

    @staticmethod
    async def buscar_por_cidade(cidade: str) -> list:
        """Alias retrocompatível — chama buscar() sem filtros extras."""
        return await LambdaInventoryService.buscar(cidade)
