import os
import json
import gspread
from google.oauth2.service_account import Credentials
from flask import Flask, jsonify, request
from flask_cors import CORS
from flask_caching import Cache

app = Flask(__name__)
CORS(app)

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

cache = Cache(config={'CACHE_TYPE': 'SimpleCache'})
cache.init_app(app)

@app.route('/pecas', methods=['GET'])
@cache.cached(timeout=300, query_string=True)
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
