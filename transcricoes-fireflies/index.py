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
load_dotenv('config/.env')
bucket_name = os.getenv('BUCKET_S3')
url = os.getenv('URL_TRANSCRIPTIONS')
transcription_api_key = os.getenv('API_KEY_TRANSCRIPTIONS')

# Desabilitar o aviso de requisição insegura
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# Cliente S3
s3 = boto3.client('s3', region_name='sa-east-1')

def lambda_handler(event, context):
    try:
        fetch_transcripts()
        
        # Ler os dados salvos no arquivo JSON
        with open('transcripts.json', 'r') as f:
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
        title_without_specials = re.sub(r'[^A-Za-z0-9]', '', item['title']) or item['id']

        print('title_without_spaces',title_without_specials)
        pdf_filename = f"{formatted_date}-{title_without_specials}.pdf"
        
        # Gerar o PDF com o conteúdo atualizado
        pdf_path = format_pdf(pdf_content, pdf_filename)

        print(f"PDF gerado em handleer depois fformat_pdf: {pdf_path}")
        
        save_pdf_s3(pdf_path, pdf_filename)

def format_pdf(content, filename):
    try:
        pdf = FPDF()
        pdf.add_page()
        pdf.set_auto_page_break(auto=True, margin=15)
        pdf.set_font("Helvetica", size=12)

        # Defina a largura da célula para a largura da página menos as margens
        page_width = pdf.epw  # epw é a largura da área de conteúdo da página

        content = re.sub(r'…', '...', content) 
        # Adiciona o conteúdo diretamente ao PDF
        pdf.multi_cell(page_width, 10, content)

        # Salva o PDF no caminho especificado
        pdf_output = f"/tmp/{filename}"
        pdf.output(pdf_output)
        print('PDF salvo em FORMAT PDF:', pdf_output)
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
        print('transcript', transcript)

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

def fetch_transcripts():
    try:
        # Obter o horário atual
        current_time = datetime.now()
        print('current_time.hour', current_time.hour)
        if current_time.hour == 9:
            # Se for 9h, 15 horas antes pra buscar a partir das 18h do dia anterior
            current_time_adjusted = current_time - timedelta(hours=15)
        else:
            # Caso contrário, 3 horas antes
            current_time_adjusted = current_time - timedelta(hours=3)

        # Adicionar 3 horas ao horário atual
        current_time_plus_3 = current_time_adjusted + timedelta(hours=3)
        # Converter para o formato ISO 8601
        current_time_iso = current_time_plus_3.isoformat()
        current_time_iso = "2024-10-28T15:37:40.695001"
        print(current_time_iso)


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

            # Salvar os dados em um arquivo JSON
            with open('transcripts.json', 'w') as f:
                json.dump(transcripts, f, indent=4)
            print("Ids salvos em 'transcripts.json'.")

        else:
            print('Falha na requisição para o Fireflies.')

    except requests.exceptions.RequestException as e:
        print(f"Erro na requisição: {e}")
    except Exception as e:
        print(f"Erro geral: {e}")
