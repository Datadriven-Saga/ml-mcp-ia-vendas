import asyncio
from services.mobiauto_service import MobiautoService
from database.postgres_client import get_lojas_primeira_mao
from utils.helpers import normalizar_placa
from config import logger

class InventoryAggregator:
    @staticmethod
    def simplificar_veiculo(v, loja_nome):
        try:
            preco = float(v.get("salePrice") or v.get("price") or 0)
        except:
            preco = 0.0

        return {
            "id": v.get("id"),
            "makeName": v.get("makeName"),
            "modelName": v.get("modelName"),
            "trimName": v.get("trimName"),
            "modelYear": v.get("modelYear"),
            "salePrice": preco,
            "km": v.get("km"),
            "colorName": v.get("colorName"),
            "plate": v.get("plate"),
            "images": v.get("images", []),
            "loja_unidade": loja_nome
        }

    @staticmethod
    async def obter_lista_lojas():
        lojas_raw = get_lojas_primeira_mao()
        if not lojas_raw:
            return []
        
        res = []
        for l in lojas_raw:
            codigo = l.get("dealerid") or l.get("nm_codigo_svm")
            nome = l.get("loja_nome") or l.get("vc_empresa") or "Loja Saga"
            if codigo:
                res.append({
                    "nome": nome,
                    "codigo_svm": str(codigo),
                    "cidade": l.get("vc_cidade", "N/A")
                })
        return res

    @staticmethod
    async def buscar_estoque_consolidado():
        lojas = await InventoryAggregator.obter_lista_lojas()
        if not lojas:
            return []

        tarefas = [MobiautoService.buscar_estoque(l['codigo_svm']) for l in lojas]
        resultados = await asyncio.gather(*tarefas, return_exceptions=True)
        
        estoque_global = []
        for i, veiculos in enumerate(resultados):
            nome_loja = lojas[i]['nome']
            if isinstance(veiculos, list):
                for v in veiculos:
                    estoque_global.append(InventoryAggregator.simplificar_veiculo(v, nome_loja))
            else:
                logger.error(f"Erro ao buscar estoque da loja {nome_loja}: {veiculos}")
        return estoque_global

    @staticmethod
    async def buscar_veiculo_especifico(identificador: str):
        estoque = await InventoryAggregator.buscar_estoque_consolidado()
        id_str = str(identificador).strip().upper()
        placa_norm = normalizar_placa(id_str)

        for v in estoque:
            if str(v.get("id")) == id_str or normalizar_placa(str(v.get("plate", ""))) == placa_norm:
                return v
        return None