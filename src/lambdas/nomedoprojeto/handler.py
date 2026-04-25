import awswrangler as wr
import json
import pandas as pd
from utils import log, dumps

def lambda_handler(event, context):
    # 1. Tratamento do evento para extrair 'name' (cidade)
    try:
        # Tenta extrair o body caso venha de um API Gateway
        body = event.get('body', {})
        if isinstance(body, str):
            body = json.loads(body)
        
        # Se o body estiver vazio ou não for dict, tenta o evento raiz
        if not isinstance(body, dict) or not body:
            body = event
            
        cidade_param = body.get('name', 'Goiânia')
        log(f"Iniciando busca para a cidade: {cidade_param}", level='INFO')
        
    except Exception as e:
        log(f"Erro ao processar parâmetros de entrada: {e}", level='ERROR')
        cidade_param = 'Goiânia'

    try:
        # 2. Query formatada
        # Nota: Mantive a lógica de REGEXP_REPLACE e concatenação do Athena
        query = f"""
        SELECT 
            d.id,
            dl.mobi_id AS dealerid,
            dl."name" AS loja,
            c."name" AS cidade,
            c.state_id AS uf,
            t."name" AS versao,
            m."name" AS modelo,
            mk."name" AS marca,
            'https://www.primeiramaosaga.com.br/gradedeofertas/' || 
            CAST(mk."name" AS VARCHAR) || '-' || 
            CAST(m."name" AS VARCHAR) || '-' || 
            REGEXP_REPLACE(CAST(t."name" AS VARCHAR), ' ', '-') || 
            '/detalhes/' || 
            CAST(d.id AS VARCHAR) AS url,
            'https://images.primeiramaosaga.com.br/images/api/v1.0/' || 
            CAST(img.min_image_id AS VARCHAR) || 
            '/transform/2Cw_638,q_80' AS url_imagem
        FROM modelled.pm_deal AS d
        LEFT JOIN modelled.pm_trim AS t ON d.trim_id = t.id 
        LEFT JOIN modelled.pm_model AS m ON t.model_id = m.id
        LEFT JOIN modelled.pm_make AS mk ON m.make_id = mk.id
        LEFT JOIN modelled.pm_dealer AS dl ON d.dealer_id = dl.id
        LEFT JOIN modelled.pm_city AS c ON dl.city_id = c.id
        INNER JOIN (
            SELECT deal_id, MIN(image_id) as min_image_id
            FROM modelled.pm_deal_x_image
            GROUP BY deal_id
        ) AS img ON d.id = img.deal_id
        WHERE d.status = 1
            AND c."name" = '{cidade_param}'
        LIMIT 25;
        """

        # 3. Execução no Athena com otimizações
        # ctas_approach=False resolve o erro de GlueEncryption/DeleteTable
        df = wr.athena.read_sql_query(
            sql=query, 
            database="modelled",
            ctas_approach=False,
            athena_cache_settings={"max_cache_age": 60} # Opcional: cache de 60s para velocidade
        )
        
        # Converte o DataFrame para o formato de dicionário
        result = df.to_dict(orient="records")

        return {
            'statusCode': 200,
            'headers': {
                'Content-Type': 'application/json',
                'Access-Control-Allow-Origin': '*'
            },
            'body': dumps(result)
        }

    except Exception as e:
        log(f'Erro ao executar query no Athena: {e}', level='ERROR')
        return {
            'statusCode': 500,
            'body': dumps({
                'error': 'Erro interno ao processar a consulta',
                'details': str(e)
            })
        }