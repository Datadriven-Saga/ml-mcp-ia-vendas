import os
from fastmcp import FastMCP
from starlette.middleware.cors import CORSMiddleware
import uvicorn
from dotenv import load_dotenv

from saga_api import (
    lista_lojas        as _api_lista_lojas,
    busca_estoque_loja as _api_estoque_loja,
    busca_fipe         as _api_busca_fipe,
    precifica          as _api_precifica,
    busca_veiculo      as _api_busca_veiculo,
)

load_dotenv()

FALLBACK_LOJAS   = os.environ["FALLBACK_LOJAS"]
FALLBACK_ESTOQUE = os.environ["FALLBACK_ESTOQUE"]

mcp = FastMCP(
    name="PrimeiraMaoSaga",
    instructions=(
        "Você é o assistente de vendas da Primeira Mão Saga, "
        "maior rede de seminovos do Brasil. "
        "Ajude o cliente a encontrar veículos, consultar preços, "
        "agendar visitas e solicitar avaliação do carro usado."
    ),
)

# helpers

def _veiculo_para_resultado(v: dict) -> dict:
    preco  = v.get("sellingPrice") or v.get("preco")  or v.get("price") or v.get("valor") or 0
    km     = v.get("odometer")     or v.get("km")     or v.get("quilometragem") or 0
    marca  = v.get("brandName")    or v.get("marca")  or v.get("brand") or ""
    modelo = v.get("modelName")    or v.get("modelo") or v.get("model") or ""
    ano    = v.get("modelYear")    or v.get("ano_modelo") or v.get("ano") or v.get("year") or ""
    cor    = v.get("colorName")    or v.get("cor")    or v.get("color") or ""
    cambio = v.get("gearboxType")  or v.get("cambio") or v.get("transmission") or ""
    comb   = v.get("fuelType")     or v.get("combustivel") or v.get("fuel") or ""
    cidade = v.get("cidade")       or v.get("city")   or v.get("loja") or ""
    vid    = v.get("plate")        or v.get("id")     or v.get("codigo") or v.get("sku") or ""

    try:
        preco_fmt = f"R$ {float(preco):,.0f}"
        km_fmt    = f"{int(km):,} km"
    except (ValueError, TypeError):
        preco_fmt = str(preco)
        km_fmt    = str(km)

    return {
        "id":    str(vid),
        "title": f"{marca} {modelo} {ano}".strip(),
        "text": (
            f"💰 {preco_fmt}  |  🛣️ {km_fmt}  |  🎨 {cor}\n"
            f"⚙️ {cambio}  |  ⛽ {comb}\n"
            f"📍 {cidade}"
        ),
        "url": FALLBACK_ESTOQUE,
        "metadata": {"marca": marca, "modelo": modelo, "ano": ano,
                     "preco": preco, "km": km, "cidade": cidade},
    }

# tools 

@mcp.tool
async def search(query: str) -> dict:
    """
    Busca veículos seminovos no estoque da Primeira Mão Saga.
    Use para encontrar carros por marca, modelo, cidade ou faixa de preço.
    """
    lojas = _api_lista_lojas()
    if not lojas:
        return {"results": [], "fallback_url": FALLBACK_ESTOQUE,
                "message": f"Estoque indisponível. Consulte em: {FALLBACK_ESTOQUE}"}

    todos: list[dict] = []
    for loja in lojas:
        did = str(loja.get("dealerid", ""))
        if did:
            todos.extend(await _api_estoque_loja(did))

    if not todos:
        return {"results": [], "fallback_url": FALLBACK_ESTOQUE,
                "message": f"Estoque indisponível. Consulte em: {FALLBACK_ESTOQUE}"}

    q = query.lower().split()
    resultados = [
        _veiculo_para_resultado(v)
        for v in todos
        if any(p in " ".join(str(x) for x in v.values()).lower() for p in q)
    ]
    return {"results": resultados or [_veiculo_para_resultado(v) for v in todos]}


@mcp.tool
async def fetch(document_id: str) -> str:
    """Retorna detalhes completos de um veículo pelo ID/placa."""
    for loja in _api_lista_lojas():
        did = str(loja.get("dealerid", ""))
        if not did:
            continue
        for v in await _api_estoque_loja(did):
            vid = str(v.get("plate") or v.get("id") or v.get("codigo") or "").upper()
            if vid == document_id.upper():
                r = _veiculo_para_resultado(v)
                return (
                    f"# {r['title']}\n\n"
                    f"**Preço:** {r['metadata']['preco']}\n"
                    f"**KM:** {r['metadata']['km']}\n"
                    f"**Localização:** {r['metadata']['cidade']}\n\n"
                    f"**ID:** {vid}\n\n"
                    f"🔗 [Ver ofertas]({FALLBACK_ESTOQUE})\n"
                    f"📞 Entre em contato para agendar um test-drive!"
                )
    return f"Veículo {document_id} não encontrado. Use `search` para ver o estoque."


@mcp.tool
async def listar_lojas(cidade: str = "") -> str:
    """
    Lista as lojas da Primeira Mão Saga com nome e dealerid.
    Filtre por cidade ou deixe em branco para todas.
    """
    lojas = _api_lista_lojas()
    if not lojas:
        return f"Lojas indisponíveis.\n\n🌐 [{FALLBACK_LOJAS}]({FALLBACK_LOJAS})"

    if cidade:
        lojas = [l for l in lojas
                 if cidade.lower() in str(l.get("loja_nome") or "").lower()]

    if not lojas:
        return f"Nenhuma loja em '{cidade}'.\n\n🌐 [{FALLBACK_LOJAS}]({FALLBACK_LOJAS})"

    linhas = ["# Lojas Primeira Mão Saga\n"]
    for l in lojas:
        linhas.append(
            f"## {l.get('loja_nome', '')}\n"
            f"🏷️ Dealer ID: `{l.get('dealerid', '')}`\n"
        )
    linhas.append(f"\n🌐 [Todas as lojas]({FALLBACK_LOJAS})")
    return "\n".join(linhas)


@mcp.tool
async def estoque_por_loja(dealer_id: str) -> dict:
    """
    Busca o estoque de uma loja pelo dealerid (obtido com listar_lojas).
    """
    veiculos = await _api_estoque_loja(dealer_id)
    if not veiculos:
        return {"results": [], "fallback_url": FALLBACK_ESTOQUE,
                "message": f"Estoque da loja '{dealer_id}' indisponível. "
                           f"Consulte em: {FALLBACK_ESTOQUE}"}
    return {"results": [_veiculo_para_resultado(v) for v in veiculos]}


@mcp.tool
async def avaliar_troca(marca: str, modelo: str, ano: int, km: int) -> str:
    """Estimativa rápida do valor de troca do carro do cliente."""
    estimativa = 50000 + max(0, (ano - 2015)) * 5000 - min(km // 10000 * 2000, 30000)
    return (
        f"# Estimativa de Avaliação — {marca} {modelo} {ano}\n\n"
        f"📊 KM informada: {km:,} km\n\n"
        f"💵 **Faixa estimada: R$ {max(estimativa-5000,0):,.0f} – R$ {estimativa+5000:,.0f}**\n\n"
        f"> ⚠️ Valor sujeito à vistoria presencial.\n\n"
        f"1. Acesse [primeiramaosaga.com.br](https://www.primeiramaosaga.com.br)\n"
        f"2. Ou ligue para a loja mais próxima\n\n"
        f"🔄 A Primeira Mão aceita seu usado como entrada!"
    )


@mcp.tool
async def buscar_fipe_por_placa(placa: str) -> str:
    """
    Busca dados FIPE de um veículo pela placa.
    Após retornar os dados, solicita ao cliente: cor, uf, tipo, km e existe_zero_km
    para então chamar buscar_precificacao.
    """
    resultado = await _api_busca_fipe(placa)
    if not resultado:
        return f"Nenhum dado FIPE encontrado para a placa **{placa.upper()}**."

    d = resultado[0]
    try:
        valor_fmt = f"R$ {float(str(d.get('valor_fipe', 0))):,.2f}"
    except (ValueError, TypeError):
        valor_fmt = str(d.get("valor_fipe", ""))

    return (
        f"# Dados FIPE — Placa {placa.upper()}\n\n"
        f"**Marca:** {d.get('marca','')}\n"
        f"**Modelo:** {d.get('modelo','')}\n"
        f"**Versão:** {d.get('versao','')}\n"
        f"**Ano Modelo:** {d.get('ano_modelo','')}\n"
        f"**Código FIPE:** {d.get('codigo_fipe','')}\n"
        f"**Valor FIPE:** {valor_fmt}\n"
        f"**Combustível:** {d.get('combustivel','')}\n"
        f"**Carroceria:** {d.get('carroceria','')}\n\n"
        f"---\n"
        f"Para prosseguir com a precificação, preciso de mais algumas informações:\n\n"
        f"1. 🎨 **Cor** do veículo\n"
        f"2. 📍 **UF** (estado onde o veículo está)\n"
        f"3. 🚗 **Tipo** do veículo (ex: Passeio, Utilitário, SUV)\n"
        f"4. 🛣️ **KM** atual do veículo\n"
        f"5. ✅ **Existe versão zero km?** (Sim ou Não)\n"
    )


@mcp.tool
async def buscar_precificacao(
    placa: str,
    cor: str,
    uf: str,
    tipo: str,
    km: str,
    existe_zero_km: str,
) -> str:
    """
    Busca precificação de mercado de um veículo.
    Chame APÓS buscar_fipe_por_placa — os dados FIPE são recuperados internamente.
    O cliente informa apenas: cor, uf, tipo, km, existe_zero_km.
    """
    fipe_lista = await _api_busca_fipe(placa)
    if not fipe_lista:
        return f"❌ Dados FIPE não encontrados para {placa.upper()}. Verifique a placa."

    f = fipe_lista[0]
    resultado = await _api_precifica(
        placa=placa, valor_fipe=f.get("valor_fipe",""),
        marca=f.get("marca",""), modelo=f.get("modelo",""),
        versao=f.get("versao",""), tipo_combustivel=f.get("combustivel",""),
        ano_modelo=f.get("ano_modelo",""), uf=uf, tipo=tipo, km=km,
        codigo_fipe=f.get("codigo_fipe",""), cor=cor,
        existe_zero_km=existe_zero_km, tipo_carroceria=f.get("carroceria",""),
    )

    if not resultado:
        return "Nenhuma precificação retornada para os dados informados."

    def fmt(val) -> str:
        try:
            return f"R$ {float(str(val).replace(',','.')):,.2f}"
        except (ValueError, TypeError):
            return str(val)

    preco_compra = resultado.get("preco_compra") or resultado.get("valorCompra") or ""
    preco_venda  = resultado.get("preco_venda")  or resultado.get("valorVenda")  or ""
    percentual   = resultado.get("percentual_fipe") or resultado.get("percentual") or ""
    observacoes  = resultado.get("observacoes")  or resultado.get("obs") or ""

    linhas = [
        f"# Precificação — {f.get('marca','')} {f.get('modelo','')} {f.get('ano_modelo','')}",
        "", f"**Placa:** {placa.upper()}", f"**Versão:** {f.get('versao','')}",
        f"**KM:** {int(km):,} km" if km.isdigit() else f"**KM:** {km}",
        f"**Cor:** {cor}", f"**UF:** {uf.upper()}", "",
        "## Valores",
        f"📊 **Valor FIPE:** {fmt(resultado.get('valor_fipe') or f.get('valor_fipe',''))}",
    ]
    if preco_compra:
        linhas.append(f"💰 **Preço Sugerido de Compra:** {fmt(preco_compra)}")
    if preco_venda:
        linhas.append(f"🏷️ **Preço Sugerido de Venda:** {fmt(preco_venda)}")
    if percentual:
        linhas.append(f"📉 **Percentual sobre FIPE:** {percentual}%")
    if observacoes:
        linhas += ["", f"> ℹ️ {observacoes}"]
    linhas += ["", "---",
               "🔄 A **Primeira Mão Saga** aceita seu usado como entrada!",
               "🌐 [primeiramaosaga.com.br](https://www.primeiramaosaga.com.br)"]
    return "\n".join(linhas)


@mcp.tool
async def buscar_veiculo_com_imagens(placa: str, dealer_id: str) -> str:
    """
    Busca dados completos e fotos de um veículo pela placa e dealer ID.
    Use listar_lojas para obter o dealer_id correto.
    """
    data = await _api_busca_veiculo(placa, dealer_id)
    if not data:
        return (
            f"Nenhum veículo com placa **{placa.upper()}** encontrado na loja `{dealer_id}`.\n"
            f"Verifique a placa e o dealer ID com a tool `listar_lojas`."
        )

    marca       = data.get("brandName")    or data.get("marca")      or ""
    modelo      = data.get("modelName")    or data.get("modelo")     or ""
    versao      = data.get("versionName")  or data.get("versao")     or ""
    ano         = data.get("modelYear")    or data.get("ano_modelo") or ""
    cor         = data.get("colorName")    or data.get("cor")        or ""
    cambio      = data.get("gearboxType")  or data.get("cambio")     or ""
    combustivel = data.get("fuelType")     or data.get("combustivel") or ""
    km_raw      = data.get("odometer")     or data.get("km")         or 0
    preco_raw   = data.get("sellingPrice") or data.get("preco")      or 0
    carroceria  = data.get("bodyType")     or data.get("carroceria") or ""
    opcionais   = data.get("optionals")    or data.get("opcionais")  or []

    try:
        preco_fmt = f"R$ {float(preco_raw):,.2f}"
    except (ValueError, TypeError):
        preco_fmt = str(preco_raw)
    try:
        km_fmt = f"{int(km_raw):,} km"
    except (ValueError, TypeError):
        km_fmt = str(km_raw)

    imagens_raw = (
        data.get("images") or data.get("imagens") or
        data.get("fotos")  or data.get("photos")  or []
    )
    urls: list[str] = []
    for img in imagens_raw:
        if isinstance(img, str):
            urls.append(img)
        elif isinstance(img, dict):
            u = img.get("url") or img.get("imageUrl") or img.get("src") or ""
            if u:
                urls.append(u)

    linhas = [
        f"# {marca} {modelo} {ano}", f"**Versão:** {versao}", "",
        f"💰 **Preço:** {preco_fmt}", f"🛣️ **KM:** {km_fmt}",
        f"🎨 **Cor:** {cor}", f"⚙️ **Câmbio:** {cambio}",
        f"⛽ **Combustível:** {combustivel}", f"🚘 **Carroceria:** {carroceria}",
    ]

    if opcionais:
        itens = opcionais if isinstance(opcionais, list) else [str(opcionais)]
        linhas += ["", "## Opcionais", ", ".join(str(o) for o in itens)]

    if urls:
        linhas += ["", f"## Fotos ({len(urls)} imagens)"]
        for i, u in enumerate(urls, 1):
            linhas.append(f"![Foto {i} — {marca} {modelo}]({u})")
    else:
        linhas += ["", "> 📷 Nenhuma imagem disponível para este veículo."]

    linhas += ["", "---",
               f"🔗 [Ver na Grade de Ofertas]({FALLBACK_ESTOQUE})",
               "📞 Entre em contato para agendar um test-drive!"]
    return "\n".join(linhas)


@mcp.tool
def solicitar_contato(nome: str, telefone: str, interesse: str) -> str:
    """
    Registra interesse do cliente e solicita contato de um consultor.
    Use quando o cliente quiser falar com um vendedor ou agendar visita.
    """
    return (
        f"✅ **Solicitação de contato registrada com sucesso!**\n\n"
        f"👤 Nome: {nome}\n"
        f"📱 Telefone: {telefone}\n"
        f"🚗 Interesse: {interesse}\n\n"
        f"Um consultor da **Primeira Mão Saga** entrará em contato em até **2 horas úteis**.\n\n"
        f"🌐 [primeiramaosaga.com.br](https://www.primeiramaosaga.com.br)\n"
        f"📧 filipe.mfonseca@gruposaga.com.br"
    )


#  inicialização 
if __name__ == "__main__":
    app = mcp.http_app(stateless_http=True)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"], allow_credentials=True,
        allow_methods=["*"], allow_headers=["*"],
    )
    uvicorn.run(app, host="0.0.0.0", port=8000)