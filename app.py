import os
import json
import gspread
import re
import time
from google.oauth2.service_account import Credentials
from flask import Flask, jsonify, request
from flask_cors import CORS
from flask_caching import Cache

app = Flask(__name__)

# Configuração CORS mais específica
cors = CORS(app, resources={
    r"/pecas/*": {
        "origins": ["https://fsaecarcara.com.br", "http://localhost:*", "https://carcara-site.onrender.com"],
        "methods": ["GET", "POST", "PUT", "DELETE", "OPTIONS"],
        "allow_headers": ["Content-Type", "Authorization"]
    }
})

# 1. Obter a credencial compacta da variável de ambiente
creds_json_str = os.getenv('GOOGLE_CREDENTIALS')

if not creds_json_str:
    raise RuntimeError("Variável GOOGLE_CREDENTIALS não definida!")

# 2. Converter string JSON para dicionário
creds_dict = json.loads(creds_json_str)

# 3. Corrigir quebras de linha na chave privada
creds_dict['private_key'] = creds_dict['private_key'].replace('\\n', '\n')

# 4. Configurar credenciais
SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive"
]
CREDS = Credentials.from_service_account_info(creds_dict, scopes=SCOPES)
CLIENT = gspread.authorize(CREDS)

# 5. Obter ID da planilha
SPREADSHEET_ID = os.getenv('SPREADSHEET_ID')

# ID da planilha (encontre na URL: https://docs.google.com/spreadsheets/d/SEU_ID_AQUI/edit)
SPREADSHEET_ID = "1vmIKVDCVs-KbINHRUnVlyyQVE-5JXV4rIme8dJB-keI"

# Configuração de cache (vamos usar um timeout muito curto ou desativar para desenvolvimento)
cache = Cache(config={'CACHE_TYPE': 'SimpleCache', 'CACHE_DEFAULT_TIMEOUT': 5})
cache.init_app(app)

def get_next_id(records):
    """
    Gera o próximo ID baseado nos IDs existentes.
    Para IDs numéricos: incrementa o maior número.
    Para IDs alfanuméricos: gera um novo ID sequencial baseado no padrão.
    """
    if not records:
        return "1"
    
    # Extrai todos os IDs existentes
    existing_ids = []
    for record in records:
        if 'ID' in record and record['ID']:
            existing_ids.append(str(record['ID']))
    
    if not existing_ids:
        return "1"
    
    # Verifica se todos os IDs são numéricos
    all_numeric = all(id.replace('.', '').isdigit() for id in existing_ids if id)
    
    if all_numeric:
        # IDs numéricos - encontra o maior e incrementa
        numeric_ids = [float(id) for id in existing_ids if id.replace('.', '').isdigit()]
        return str(int(max(numeric_ids)) + 1)
    else:
        # IDs alfanuméricos - analisa o padrão para gerar o próximo
        return generate_next_alphanumeric_id(existing_ids)

def generate_next_alphanumeric_id(existing_ids):
    """
    Gera o próximo ID para IDs alfanuméricos.
    Assume que os IDs seguem um padrão como: ABC 123 2024-1 CR-01
    """
    # Encontra o maior ID numérico no final dos IDs
    pattern = r'(\d+)$'
    max_num = 0
    
    for id_str in existing_ids:
        match = re.search(pattern, id_str)
        if match:
            num = int(match.group(1))
            if num > max_num:
                max_num = num
    
    # Se não encontrou números, retorna um padrão básico
    if max_num == 0:
        return "FRS-001"
    
    # Encontra o prefixo do último ID (assumindo que todos têm o mesmo prefixo)
    prefix_pattern = r'^(.+?)(\d+)$'
    prefix = "FRS"
    
    for id_str in existing_ids:
        match = re.match(prefix_pattern, id_str)
        if match:
            prefix = match.group(1)
            break
    
    # Retorna o próximo ID com o número incrementado
    return f"{prefix}{max_num + 1:03d}"

@app.route('/pecas', methods=['GET'])
def get_pecas():
    try:
        pagina = request.args.get('pagina', default='freios')
        busca = request.args.get('busca', default='')
        
        # Acessa a planilha remota
        spreadsheet = CLIENT.open_by_key(SPREADSHEET_ID)
        worksheet = spreadsheet.worksheet(pagina)
        
        # Obtém todos os dados como lista de dicionários
        dados = worksheet.get_all_records()

        if busca:
            busca = busca.lower()
            dados_filtrados = []
            for peca in dados:
                # Verifica vários campos para a busca
                if (busca in str(peca.get('ID', '')).lower() or 
                    busca in peca.get('peca', '').lower() or 
                    busca in peca.get('material', '').lower() or 
                    busca in peca.get('descricao', '').lower() or 
                    busca in peca.get('fornecedor', '').lower()):
                    dados_filtrados.append(peca)
            dados = dados_filtrados
        
        return jsonify({
            "pagina": pagina,
            "total": len(dados),
            "dados": dados
        })
    
    except gspread.exceptions.WorksheetNotFound:
        return jsonify({"erro": f"Página '{pagina}' não encontrada"}), 404
    
    except gspread.exceptions.APIError as e:
        app.logger.error(f"Erro na API Google: {e.response.json()}")
        return jsonify({
            "erro": "Problema com o Google Sheets",
            "codigo": e.response.status_code,
            "detalhes": e.response.json().get('error', {}).get('message')
        }), 502
    
    except Exception as e:
        app.logger.exception("Erro interno:")
        return jsonify({"erro": "Erro interno no servidor"}), 500

@app.route('/pecas', methods=['POST'])
def adicionar_peca():
    try:
        data = request.get_json()
        if not data:
            return jsonify({"erro": "Dados JSON necessários"}), 400

        categoria = data.get('categoria')
        if not categoria:
            return jsonify({"erro": "Categoria não fornecida"}), 400

        spreadsheet = CLIENT.open_by_key(SPREADSHEET_ID)
        worksheet = spreadsheet.worksheet(categoria)

        # Obter todos os registros para determinar o próximo ID
        records = worksheet.get_all_records()
        next_id = get_next_id(records)

        # Preparar dados para adicionar
        nova_peca = {
            'ID': next_id,
            'peca': data.get('peca', ''),
            'quantidade': data.get('quantidade', ''),
            'material': data.get('material', ''),
            'massa(g)': data.get('massa(g)', ''),
            'valor($)': data.get('valor($)', ''),
            'descricao': data.get('descricao', ''),
            'fornecedor': data.get('fornecedor', '')
        }

        # Adicionar nova linha
        worksheet.append_row(list(nova_peca.values()))

        # Pequena pausa para garantir que a planilha foi atualizada
        time.sleep(1)

        return jsonify({
            "mensagem": "Peça adicionada com sucesso",
            "id": next_id
        }), 201

    except gspread.exceptions.WorksheetNotFound:
        return jsonify({"erro": f"Página '{categoria}' não encontrada"}), 404
    except gspread.exceptions.APIError as e:
        app.logger.error(f"Erro na API Google: {e.response.json()}")
        return jsonify({
            "erro": "Problema com o Google Sheets",
            "codigo": e.response.status_code,
            "detalhes": e.response.json().get('error', {}).get('message')
        }), 502
    except Exception as e:
        app.logger.exception("Erro interno:")
        return jsonify({"erro": "Erro interno no servidor"}), 500

@app.route('/pecas/<peca_id>', methods=['PUT'])
def atualizar_peca(peca_id):
    try:
        data = request.get_json()
        if not data:
            return jsonify({"erro": "Dados JSON necessários"}), 400

        categoria = data.get('categoria')
        if not categoria:
            return jsonify({"erro": "Categoria não fornecida"}), 400

        spreadsheet = CLIENT.open_by_key(SPREADSHEET_ID)
        worksheet = spreadsheet.worksheet(categoria)
        records = worksheet.get_all_records()

        # Encontrar a linha da peça
        linha_index = None
        for i, record in enumerate(records, start=2):  # Começa na linha 2 (após cabeçalho)
            if str(record.get('ID')) == peca_id:
                linha_index = i
                break

        if not linha_index:
            return jsonify({"erro": "Peça não encontrada"}), 404

        # Atualizar os campos
        campos = ['peca', 'quantidade', 'material', 'massa(g)', 'valor($)', 'descricao', 'fornecedor']
        col_indices = {
            'ID': 1,
            'peca': 2,
            'quantidade': 3,
            'material': 4,
            'massa(g)': 5,
            'valor($)': 6,
            'descricao': 7,
            'fornecedor': 8
        }
        
        for campo in campos:
            if campo in data:
                col_index = col_indices.get(campo)
                if col_index:
                    worksheet.update_cell(linha_index, col_index, data[campo])

        # Pequena pausa para garantir que a planilha foi atualizada
        time.sleep(1)

        return jsonify({"mensagem": "Peça atualizada com sucesso"}), 200

    except gspread.exceptions.WorksheetNotFound:
        return jsonify({"erro": f"Página '{categoria}' não encontrada"}), 404
    except gspread.exceptions.APIError as e:
        app.logger.error(f"Erro na API Google: {e.response.json()}")
        return jsonify({
            "erro": "Problema com o Google Sheets",
            "codigo": e.response.status_code,
            "detalhes": e.response.json().get('error', {}).get('message')
        }), 502
    except Exception as e:
        app.logger.exception("Erro interno:")
        return jsonify({"erro": "Erro interno no servidor"}), 500

@app.route('/pecas/<peca_id>', methods=['DELETE'])
def deletar_peca(peca_id):
    try:
        data = request.get_json()
        if not data:
            return jsonify({"erro": "Dados JSON necessários"}), 400

        categoria = data.get('categoria')
        if not categoria:
            return jsonify({"erro": "Categoria não fornecida"}), 400

        spreadsheet = CLIENT.open_by_key(SPREADSHEET_ID)
        worksheet = spreadsheet.worksheet(categoria)
        records = worksheet.get_all_records()

        # Encontrar a linha da peça
        linha_index = None
        for i, record in enumerate(records, start=2):  # Começa na linha 2 (após cabeçalho)
            if str(record.get('ID')) == peca_id:
                linha_index = i
                break

        if not linha_index:
            return jsonify({"erro": "Peça não encontrada"}), 404

        # Deletar a linha
        worksheet.delete_rows(linha_index)

        # Pequena pausa para garantir que a planilha foi atualizada
        time.sleep(1)

        return jsonify({"mensagem": "Peça deletada com sucesso"}), 200

    except gspread.exceptions.WorksheetNotFound:
        return jsonify({"erro": f"Página '{categoria}' não encontrada"}), 404
    except gspread.exceptions.APIError as e:
        app.logger.error(f"Erro na API Google: {e.response.json()}")
        return jsonify({
            "erro": "Problema com o Google Sheets",
            "codigo": e.response.status_code,
            "detalhes": e.response.json().get('error', {}).get('message')
        }), 502
    except Exception as e:
        app.logger.exception("Erro interno:")
        return jsonify({"erro": "Erro interno no servidor"}), 500

# -------------------------------------------------------------------
# NOVA FUNÇÃO SEPARADA (/status) verificada no render
# -------------------------------------------------------------------
@app.route('/status')
def status_check():
    def test_sheets_access():
        """Verifica acesso básico ao Google Sheets"""
        try:
            spreadsheet = CLIENT.open_by_key(SPREADSHEET_ID)
            spreadsheet.worksheets()  # Tenta listar as abas
            return True
        except Exception as e:
            raise ConnectionError(f"Falha no acesso ao Google Sheets: {str(e)}")
    
    try:
        # Verifica o acesso ao Google Sheets
        test_sheets_access()
        
        return jsonify({
            "status": "online",
            "service": "API de Peças",
            "version": "1.0",
            "planilha": SPREADSHEET_ID
        }), 200
    
    except Exception as e:
        return jsonify({
            "status": "degraded",
            "error": str(e),
            "details": "Problema de conexão com o Google Sheets"
        }), 500

if __name__ == '__main__':
    app.run(debug=True)
