import os
import json
import gspread
from google.oauth2.service_account import Credentials
from flask import Flask, jsonify, request

app = Flask(__name__)

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

@app.route('/pecas', methods=['GET'])
def get_pecas():
    try:
        pagina = request.args.get('pagina', default='freios')
        
        # Acessa a planilha remota
        spreadsheet = CLIENT.open_by_key(SPREADSHEET_ID)
        worksheet = spreadsheet.worksheet(pagina)
        
        # Obtém todos os dados como lista de dicionários
        dados = worksheet.get_all_records()
        
        return jsonify({
            "pagina": pagina,
            "total": len(dados),
            "dados": dados
        })
    
    except gspread.exceptions.WorksheetNotFound:
        return jsonify({"erro": f"Página '{pagina}' não encontrada"}), 404
    
    except Exception as e:
        return jsonify({"erro": str(e)}), 500
