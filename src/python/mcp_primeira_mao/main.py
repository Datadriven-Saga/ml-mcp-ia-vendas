import asyncio
from fastmcp import FastMCP
from services.mobiauto_service import MobiautoService
from services.fipe_service import FipeService
from services.pricing_service import PricingService # Ajustado para o nome do arquivo na sua pasta
from database.postgres_client import get_lojas_primeira_mao # Ajustado para postgres_client.py
from utils.helpers import formatar_moeda

mcp = FastMCP("PrimeiraMaoSaga")

@mcp.tool()
async def listar_lojas():
    """
    Retorna a lista de todas as lojas 'Primeira Mão' e seus respectivos Dealer IDs.
    Esta é a primeira ferramenta a ser usada para identificar o ID da loja.
    """
    return get_lojas_primeira_mao()

@mcp.tool()
async def consultar_estoque(dealer_id: str):
    """
    Lista todos os veículos disponíveis em uma loja específica.
    Argumento: dealer_id (ID numérico da loja obtido em listar_lojas).
    """
    return await MobiautoService.buscar_estoque(dealer_id)

@mcp.tool()
async def buscar_fipe(placa: str):
    """
    Consulta o valor oficial da Tabela FIPE de um veículo pela placa.
    Use quando o cliente quiser saber o valor de mercado ou antes de avaliar.
    """
    return await FipeService.consultar_por_placa(placa)

@mcp.tool()
async def avaliar_veiculo(
    placa: str,
    valor_fipe: str,
    marca: str,
    modelo: str,
    ano_modelo: str,
    km: str = "0",
    uf: str = "GO"
):
    """
    Calcula o valor de COMPRA do veículo pela loja (Avaliação Interna).
    Use esta ferramenta APÓS obter os dados da FIPE.
    - valor_fipe: Valor retornado pela busca_fipe.
    - km: Quilometragem atual do veículo (Perguntar ao cliente).
    - uf: Estado onde o veículo está (Ex: GO, DF).
    """
    dados = {
        "placa": placa,
        "valor_fipe": formatar_moeda(valor_fipe),
        "marca": marca,
        "modelo": modelo,
        "ano_modelo": ano_modelo,
        "km": km,
        "uf": uf
    }
    return await PricingService.calcular(dados)

if __name__ == "__main__":
    mcp.run()