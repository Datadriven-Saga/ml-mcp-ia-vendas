"""
Serviço de criação de leads (propostas) na API Mobiauto CRM.
Suporta dois tipos: BUY (compra) e SELL (venda de veículo do cliente).

Endpoints:
  POST https://open-api.mobiauto.com.br/api/proposal/v1.0/{dealer_id}
  Auth: Bearer {token Mobiauto} — mesmo token usado para o estoque
"""

import httpx
from config import logger

PROPOSAL_BASE_URL = "https://open-api.mobiauto.com.br/api/proposal/v1.0"
PROPOSAL_TIMEOUT  = 10  # reduzido para caber dentro do timeout do widget (15s)
GROUP_ID          = 948  # int — a API espera número, não string

# Provider para fluxo de COMPRA (cliente quer comprar da Saga)
_PROVIDER_BUY = {
    "id":     11,
    "name":   "Site",
    "origin": "Internet",
    "providerCampaign": [
        {"provider": "Site", "campaign": ""}
    ],
}

# Provider para fluxo de VENDA (cliente quer vender o carro para a Saga)
_PROVIDER_SELL = {
    "id":     245,
    "name":   "Primeira Mão - Avaliação",
    "origin": "Internet",
    "providerCampaign": [
        {"provider": "Primeira Mão - Avaliação", "campaign": ""}
    ],
}


class MobiautoProposalService:

    # ── Lookup de dealer_id ────────────────────────────────────────────

    @staticmethod
    def _dealer_por_nome(loja_nome: str, lojas: list) -> str | None:
        """Depara nome da loja → dealerid (codigo_svm). Tenta exato, depois parcial."""
        if not loja_nome or not lojas:
            return None
        busca = loja_nome.lower().strip()
        for loja in lojas:
            if loja["nome"].lower().strip() == busca:
                return loja["codigo_svm"]
        # Parcial (ex: "SN GO BURITI" contido em "SN GO BURITI PREMIUM")
        for loja in lojas:
            if busca in loja["nome"].lower():
                return loja["codigo_svm"]
        return None

    @staticmethod
    def _dealer_por_uf(uf: str, lojas: list) -> str | None:
        """Retorna o primeiro dealerid de lojas com a UF informada."""
        if not uf or not lojas:
            return None
        uf_up = uf.upper().strip()
        for loja in lojas:
            if loja.get("uf", "").upper() == uf_up:
                return loja["codigo_svm"]
        return None

    # ── Criação de lead ────────────────────────────────────────────────

    @staticmethod
    async def criar_lead(
        intention_type: str,
        nome: str,
        telefone: str,
        email: str = "",
        loja_nome: str = None,
        uf_fallback: str = None,
        mensagem: str = "",
    ) -> dict:
        """
        Cria um lead na API Mobiauto.

        Parâmetros:
          intention_type : "BUY"  → cliente quer comprar um veículo da Saga
                           "SELL" → cliente quer vender o veículo para a Saga
          nome           : Nome do cliente
          telefone       : Telefone do cliente
          email          : E-mail (opcional; usa espaço se vazio pois a API exige o campo)
          loja_nome      : Nome da loja (usado para BUY — obtém dealer_id pelo nome)
          uf_fallback    : UF do cliente (fallback para SELL sem loja específica)
          mensagem       : Mensagem interna opcional (placa, km, etc.)

        Retorna dict com:
          success: bool
          dealer_id: str  (se success)
          error: str      (se não success)
        """
        # Importações locais para evitar circular import
        from services.inventory_aggregator import InventoryAggregator
        from services.mobiauto_service import MobiautoService

        # 1. Token
        token = await MobiautoService.get_token()
        if not token:
            logger.error("[MobiautoProposalService] Sem token Mobiauto — abortando")
            return {"success": False, "error": "Sem token de autenticação Mobiauto"}

        # 2. Lista de lojas para depara
        lojas = await InventoryAggregator.obter_lista_lojas()

        # 3. Resolve dealer_id com prioridade: nome → uf → primeira loja disponível
        dealer_id = None
        dealer_origem = ""

        if loja_nome:
            dealer_id = MobiautoProposalService._dealer_por_nome(loja_nome, lojas)
            if dealer_id:
                dealer_origem = f"loja_nome='{loja_nome}'"

        if not dealer_id and uf_fallback:
            dealer_id = MobiautoProposalService._dealer_por_uf(uf_fallback, lojas)
            if dealer_id:
                dealer_origem = f"uf_fallback='{uf_fallback}'"

        if not dealer_id and lojas:
            dealer_id = lojas[0]["codigo_svm"]
            dealer_origem = f"primeira_loja='{lojas[0]['nome']}'"

        if not dealer_id:
            logger.error("[MobiautoProposalService] Nenhum dealer_id disponível — sem lojas carregadas")
            return {"success": False, "error": "Nenhum dealer_id disponível"}

        # 4. Normaliza telefone — remove tudo que não for dígito
        #    O widget envia com máscara "(62) 99399-4629"; a API espera só dígitos.
        telefone_digits = "".join(c for c in telefone if c.isdigit())

        logger.info(
            f"[MobiautoProposalService] dealer_id={dealer_id} | origem={dealer_origem} | "
            f"type={intention_type} | cliente='{nome}' | tel='{telefone}' | tel_digits='{telefone_digits}'"
        )

        # Monta body — tipos corretos: groupId e departmentId são inteiros
        provider = _PROVIDER_BUY if intention_type == "BUY" else _PROVIDER_SELL
        body = {
            "callcenter":    True,
            "intentionType": intention_type,
            "user": {
                "email":        email or "",
                "dealerId":     dealer_id,
                "name":         nome,
                "phone":        telefone_digits,
                "departmentId": 0,
            },
            "message":  (mensagem or "")[:500],
            "origin":   1,
            "whatsapp": False,
            "provider": provider,
            "status":   "NEW",
            "groupId":  GROUP_ID,
        }

        # 5. POST na API com estratégia de fallback progressiva
        url = f"{PROPOSAL_BASE_URL}/{dealer_id}"
        logger.info(f"[MobiautoProposalService] POST {url} | type={intention_type}")

        # Token atual (pode ser renovado abaixo se receber 401)
        _current_token = token

        async def _post(payload: dict, tok: str):
            try:
                async with httpx.AsyncClient(timeout=PROPOSAL_TIMEOUT) as client:
                    return await client.post(
                        url,
                        json=payload,
                        headers={"Authorization": f"Bearer {tok}"},
                    )
            except httpx.ReadTimeout:
                return None
            except Exception as exc:
                logger.error(f"[MobiautoProposalService] _post exception | {type(exc).__name__}: {exc}")
                return None

        try:
            resp = await _post(body, _current_token)

            if resp is None:
                logger.error(f"[MobiautoProposalService] Timeout ({PROPOSAL_TIMEOUT}s) | dealer_id={dealer_id}")
                return {"success": False, "error": f"Timeout após {PROPOSAL_TIMEOUT}s"}

            # 401 → renova token e tenta uma vez mais
            if resp.status_code == 401:
                logger.warning(f"[MobiautoProposalService] 401 — token expirado, renovando...")
                MobiautoService._token_cache = None
                _current_token = await MobiautoService.get_token(force_refresh=True)
                if _current_token:
                    resp = await _post(body, _current_token)
                    if resp is None:
                        return {"success": False, "error": f"Timeout após {PROPOSAL_TIMEOUT}s"}

            # SELL falhou com 4xx → tenta com provider BUY
            if resp and not resp.is_success and 400 <= resp.status_code < 500 and intention_type == "SELL":
                logger.warning(
                    f"[MobiautoProposalService] SELL provider falhou HTTP {resp.status_code} | "
                    f"body={resp.text[:300]} — tentando provider BUY"
                )
                body_sell_fallback = dict(body)
                body_sell_fallback["provider"] = _PROVIDER_BUY
                resp = await _post(body_sell_fallback, _current_token)
                if resp is None:
                    return {"success": False, "error": f"Timeout após {PROPOSAL_TIMEOUT}s"}

            # BUY ou SELL (após fallbacks) ainda falhou com 4xx → tenta sem provider
            if resp and not resp.is_success and 400 <= resp.status_code < 500:
                logger.warning(
                    f"[MobiautoProposalService] HTTP {resp.status_code} com provider | "
                    f"body={resp.text[:300]} — tentando sem provider"
                )
                body_no_provider = {k: v for k, v in body.items() if k != "provider"}
                resp = await _post(body_no_provider, _current_token)
                if resp is None:
                    return {"success": False, "error": f"Timeout após {PROPOSAL_TIMEOUT}s"}

            if resp and resp.is_success:
                try:
                    resp_body = resp.json()
                except Exception:
                    resp_body = resp.text
                logger.info(
                    f"[MobiautoProposalService] Lead criado | status={resp.status_code} | "
                    f"dealer_id={dealer_id} | type={intention_type} | response={resp_body}"
                )
                return {"success": True, "status_code": resp.status_code, "dealer_id": dealer_id, "response": resp_body}

            status  = resp.status_code if resp else "N/A"
            detalhe = resp.text[:600] if resp else "sem resposta"
            logger.error(
                f"[MobiautoProposalService] Falha final | HTTP {status} | dealer_id={dealer_id} | "
                f"type={intention_type} | body={detalhe}"
            )
            return {
                "success":   False,
                "error":     f"HTTP {status}",
                "detalhe":   detalhe,
                "dealer_id": dealer_id,
            }

        except Exception as exc:
            logger.exception(f"[MobiautoProposalService] Erro inesperado | {type(exc).__name__}: {exc}")
            return {"success": False, "error": f"{type(exc).__name__}: {exc}"}
