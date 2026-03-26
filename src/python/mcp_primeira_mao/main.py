import os
import json
from fastmcp import FastMCP
from config import MCP_TRANSPORT, logger
from services.mobiauto_service import MobiautoService
from services.fipe_service import FipeService
from services.pricing_service import PricingService
from services.inventory_aggregator import InventoryAggregator
from database.postgres_client import get_lojas_primeira_mao
from utils.helpers import formatar_moeda, normalizar_placa

mcp = FastMCP("PrimeiraMaoSaga")

@mcp.tool()
async def listar_lojas():
    return await InventoryAggregator.obter_lista_lojas()

@mcp.tool()
async def estoque_total():
    return await InventoryAggregator.buscar_estoque_consolidado()

@mcp.tool()
async def search_veiculos(marca: str = None, modelo: str = None, cidade: str = None, preco_max: float = None):
    estoque = await InventoryAggregator.buscar_estoque_consolidado()
    res = [v for v in estoque if 
        (not marca or marca.lower() in str(v.get('brand', '')).lower()) and
        (not modelo or modelo.lower() in str(v.get('model', '')).lower()) and
        (not cidade or cidade.lower() in str(v.get('city', '')).lower()) and
        (not preco_max or float(v.get('sellingPrice', 0)) <= preco_max)
    ]
    return [{
        "id": str(v.get("id")),
        "veiculo": f"{v.get('brand')} {v.get('model')}",
        "valor": formatar_moeda(v.get("sellingPrice")),
        "loja": v.get("loja_origem")
    } for v in res[:20]]

@mcp.tool()
async def fetch_veiculo_detalhado(identificador: str):
    veiculo = await InventoryAggregator.buscar_veiculo_especifico(identificador)
    return veiculo if veiculo else {"erro": "Nao encontrado"}

@mcp.tool()
async def imagem_veiculo(identificador: str):
    v = await InventoryAggregator.buscar_veiculo_especifico(identificador)
    if not v: return {"erro": "Veiculo nao encontrado"}
    return {
        "modelo": f"{v.get('brand')} {v.get('model')}",
        "cor": v.get("color"),
        "imagens": v.get("photos", [])
    }

@mcp.tool()
async def buscar_fipe(placa: str):
    return await FipeService.consultar_por_placa(normalizar_placa(placa))

@mcp.tool()
async def avaliar_veiculo(placa: str, valor_fipe: str, marca: str, modelo: str, ano_modelo: str, km: str, uf: str):
    dados = {
        "placa": normalizar_placa(placa), "valor_fipe": valor_fipe,
        "marca": marca, "modelo": modelo, "ano_modelo": ano_modelo,
        "km": km, "uf": uf
    }
    resultado = await PricingService.calcular(dados)
    if isinstance(resultado, dict) and "Valor_proposta_compra" in resultado:
        return {
            "Avaliacao": resultado["Valor_proposta_compra"],
            "Resumo": f"Proposta de compra para {marca} {modelo}: {resultado['Valor_proposta_compra']}",
            "Dados_Completos": resultado
        }
    return resultado

if __name__ == "__main__":
    mcp.run(transport="sse" if MCP_TRANSPORT == "sse" else "stdio")