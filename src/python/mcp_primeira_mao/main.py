import os
import sys
from typing import Optional
from fastmcp import FastMCP
from services.inventory_aggregator import InventoryAggregator
from services.fipe_service import FipeService
from services.pricing_service import PricingService
from utils.helpers import normalizar_placa
from config import logger

mcp = FastMCP("PrimeiraMaoSaga")

@mcp.tool()
async def listar_lojas():
    """Lista as lojas configuradas no banco de dados ou no arquivo de fallback (lojas_mock.csv)."""
    return await InventoryAggregator.obter_lista_lojas()

@mcp.tool()
async def estoque_total():
    """Retorna o estoque completo de todas as unidades mapeadas do Grupo Saga."""
    return await InventoryAggregator.buscar_estoque_consolidado()

@mcp.tool()
async def search_veiculos(
    marca: Optional[str] = None, 
    modelo: Optional[str] = None, 
    preco_max: Optional[float] = None
):
    """
    Busca inteligente no estoque. Todos os campos são opcionais.
    Resolve erros de validação permitindo valores nulos da interface.
    """
    estoque = await InventoryAggregator.buscar_estoque_consolidado()
    
    if marca is None and modelo is None and preco_max is None:
        return estoque[:20]

    res = []
    for v in estoque:
        match_marca = not marca or str(marca).lower() in str(v.get('makeName', '')).lower()
        match_modelo = not modelo or str(modelo).lower() in str(v.get('modelName', '')).lower()
        
        valor_veiculo = float(v.get('salePrice') or v.get('price') or 0)
        match_preco = preco_max is None or valor_veiculo <= preco_max
        
        if match_marca and match_modelo and match_preco:
            res.append(v)
        
    return res[:40]

@mcp.tool()
async def fetch_veiculo_detalhado(identificador: str):
    """
    Retorna o dossiê completo de um veículo (fotos, opcionais e dados técnicos).
    Aceita ID da Mobiauto ou Placa como identificador.
    """
    return await InventoryAggregator.buscar_veiculo_especifico(identificador)

@mcp.tool()
async def buscar_fipe(placa: str):
    """Consulta o valor atualizado da Tabela FIPE e dados técnicos via placa."""
    return await FipeService.consultar_por_placa(normalizar_placa(placa))

@mcp.tool()
async def avaliar_veiculo(
    placa: str, 
    valor_fipe: str, 
    marca: str, 
    modelo: str, 
    ano_modelo: str, 
    km: str, 
    uf: str
):
    """
    Calcula a proposta de avaliação para compra/troca baseada na API de precificação do Grupo Saga.
    """
    dados = {
        "placa": normalizar_placa(placa), 
        "valor_fipe": valor_fipe, 
        "marca": marca, 
        "modelo": modelo, 
        "ano_modelo": ano_modelo, 
        "km": km, 
        "uf": uf
    }
    return await PricingService.calcular_compra(dados)

if __name__ == "__main__":
    sys.path.append(os.path.dirname(os.path.abspath(__file__)))
    
    transport = os.getenv("MCP_TRANSPORT", "stdio").lower()
    
    if transport == "sse":
        port = int(os.getenv("PORT", 8000))
        logger.info(f"Iniciando MCP em modo SSE na porta {port}")
        mcp.run(transport="sse", host="0.0.0.0", port=port)
    else:
        mcp.run(transport="stdio")