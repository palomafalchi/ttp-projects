import boto3
import requests
from fpdf import FPDF
import urllib3
import json
import os
from datetime import datetime, timedelta
from dotenv import load_dotenv
import json
import re

# Configurações
load_dotenv('/package/config/.env')
bucket_name = os.getenv('BUCKET_S3')
url = os.getenv('URL_TRANSCRIPTIONS')
transcription_api_key = os.getenv('API_KEY_TRANSCRIPTIONS')

# Desabilitar o aviso de requisição insegura
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# Cliente S3
s3 = boto3.client('s3', region_name='sa-east-1')

# Dicionário de mapeamento para caracteres especiais
translation_table = str.maketrans({
    'á': 'a', 'ã': 'a', 'â': 'a',
    'é': 'e', 'ê': 'e',
    'í': 'i',
    'ó': 'o', 'õ': 'o', 'ô': 'o',
    'ú': 'u',
    'ç': 'c'
})

def lambda_handler(event, context):
    try:
        # Verifica se está rodando no Lambda
        if os.environ.get('AWS_EXECUTION_ENV'):
            file_path = '/tmp/transcripts.json'  # para Lambda
            print('Ambiente da lambda')
        else:
            file_path = 'transcripts.json'  # para execução local

        fetch_transcripts(file_path)
        
        # Ler os dados salvos no arquivo JSON
        with open(file_path, 'r') as f:
            transcripts = json.load(f)
            
    except Exception as e:
        return {
            'statusCode': 500,
            'body': f"Erro ao processar: {str(e)}"
        }

    # Processar cada transcrição e gerar o PDF
    for item in transcripts:
        print('item', item)

        formatted_date = format_date(item['dateString'])
        pdf_content = f"{item['title']} - {formatted_date}\n\n"
        
        # Atualizar o pdf_content com as informações da transcrição
        pdf_content = get_sentences(pdf_content, item['id'])
        
        # Remove caracteres especiais e traduz caracteres acentuados
        title_without_specials = item['title'].translate(translation_table)
        title_without_specials = re.sub(r'[^A-Za-z0-9]', '', title_without_specials)  # Remove outros caracteres não alfanuméricos
        
        # Se o resultado estiver vazio, use item['id']
        title_without_specials = title_without_specials if title_without_specials else item['id']

        print('title_without_spaces',title_without_specials)

        pdf_filename = f"{formatted_date}-{title_without_specials}-{item['id']}.pdf"
        
        # Gerar o PDF com o conteúdo atualizado
        pdf_path = format_pdf(pdf_content, pdf_filename)

        print(f"PDF gerado em handler: {pdf_path}")
        
        save_pdf_s3(pdf_path, pdf_filename)

def format_pdf(content, filename):
    try:
        pdf = FPDF()
        pdf.add_page()
        pdf.set_auto_page_break(auto=True, margin=15)
        pdf.set_font("Helvetica", size=12)

        # Calcular a largura efetiva
        page_width = pdf.w - 2*pdf.l_margin  # largura total menos as margens

        content = re.sub(r'…', '...', content) 
        # Adiciona o conteúdo diretamente ao PDF
        pdf.multi_cell(page_width, 10, content)

        # Salva o PDF no caminho especificado
        pdf_output = f"/tmp/{filename}"
        pdf.output(pdf_output)
        return pdf_output
    except Exception as e:
        print(f"Erro ao gerar PDF: {e}")
        raise
  
def format_date(date_string):
    try:
        # Converter a string para um objeto datetime
        date_object = datetime.strptime(date_string, "%Y-%m-%dT%H:%M:%S.%fZ")
        formatted_date = date_object.strftime("%d-%m-%Y")
        return formatted_date
    except Exception as e:
        print(f"Erro ao formatar data: {e}")
        raise

def get_sentences(pdf_content, id): 
    print(id)
    payload = f"{{\"query\":\"query Transcript($transcriptId: String!) {{ transcript(id: $transcriptId) {{ title id dateString sentences {{ index speaker_name text }} }} }}\",\"variables\":{{\"transcriptId\":\"{id}\"}}}}"
        
    headers = {
        'Content-Type': 'application/json',
        'Authorization': f"Bearer {transcription_api_key}"
    }

    response = requests.request("POST", url, headers=headers, data=payload, verify=False)
    # Verificar se a requisição foi bem-sucedida
    if response.status_code == 200:
        data = json.loads(response.text)
        transcript = data['data']["transcript"]
        print('numero de transcrições', len(transcript))

        previous_speaker = ""
        for sentence in transcript['sentences']:
            if previous_speaker:
                if sentence['speaker_name'] == previous_speaker:
                    pdf_content = pdf_content.rstrip('\n\n') + f" {sentence['text']}\n\n"
                else:
                    pdf_content += f"{sentence['speaker_name']}: {sentence['text']}\n\n"
            previous_speaker = sentence['speaker_name']
        
        return pdf_content
    else:
        print(f"Erro na requisição: {response.status_code}")
        return pdf_content  # Retornar o conteúdo original se a requisição falhar

def save_pdf_s3(pdf_path, pdf_filename):
            # Salvar o PDF no S3
        s3 = boto3.client('s3', region_name='sa-east-1')
        bucket_name = os.getenv('BUCKET_S3')
        try:
            with open(pdf_path, "rb") as pdf_file:
                s3.put_object(Bucket=bucket_name, Key=pdf_filename, Body=pdf_file)
            print(f"PDF salvo no S3: {pdf_filename}")
        except Exception as e:
            print(f"Erro ao salvar o PDF no S3: {e}")

def fetch_transcripts(file_path):
    try:
        # Obter o horário atual
        current_time = datetime.now()
        print('current_time',current_time)
            # Se for 12h (9h horário brasília), pesquisar 16h antes pra buscar a partir das 17h do dia anterior
        if current_time.hour == 12:
            current_time_adjusted = current_time - timedelta(hours=16)
        else:
            # Caso contrário, buscar 1h e meia antes
            current_time_adjusted = current_time - timedelta(minutes=90)

        print('current_time_adjusted',current_time_adjusted)

        current_time_iso = current_time_adjusted

        payload = f"{{\"query\":\"query Transcripts($fromDate: DateTime) {{ transcripts(fromDate: $fromDate) {{ title id dateString }} }}\",\"variables\":{{\"fromDate\":\"{current_time_iso}\"}}}}"
        headers = {
            'Content-Type': 'application/json',
            'Authorization': f"Bearer {transcription_api_key}"
        }

        response = requests.post(os.getenv('URL_TRANSCRIPTIONS'), headers=headers, data=payload, verify=False)

        if response.status_code == 200:
            data = response.json()
            print('data',data)
            transcripts = data['data']["transcripts"]
            print('trancrições encontradas', len(transcripts))
            
            # Salvar os dados em um arquivo JSON
            with open(file_path, 'w') as f:
                json.dump(transcripts, f, indent=4)
            print("Ids salvos em ", file_path)

        else:
            print('Falha na requisição para o Fireflies.')

    except requests.exceptions.RequestException as e:
        print(f"Erro na requisição: {e}")
    except Exception as e:
        print(f"Erro geral: {e}")
