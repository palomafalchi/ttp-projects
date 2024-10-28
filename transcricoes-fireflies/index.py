import boto3
import requests
from fpdf import FPDF
from datetime import datetime, timedelta
from dotenv import load_dotenv
import os
import json

# Configurações
load_dotenv('config/.env')
bucket_name = os.getenv('BUCKET_S3')
url = os.getenv('URL_FIREFLIES')
fireflies_api_key = os.getenv('API_KEY_FIREFLIES')

# Cliente S3
s3 = boto3.client('s3', region_name='sa-east-1')

def format_pdf(content, filename):
    try:
        pdf = FPDF()
        pdf.add_page()
        pdf.set_font("Arial", size=12)
        # Defina a largura da célula para a largura da página menos as margens
        page_width = pdf.w - 2 * pdf.l_margin
        previous_speaker = None
        
        for line in content.split('\n'):
            if previous_speaker and line.startswith(previous_speaker):
                # Se a linha começa com o nome do speaker anterior, remova o nome do speaker
                line = line[len(previous_speaker):].strip()
            elif ':' in line:
                # Se a linha contém ':', coloque o nome do speaker em negrito
                speaker, text = line.split(':', 1)
                pdf.set_font("Arial", style='B', size=12)
                pdf.multi_cell(page_width, 10, txt=speaker + ":", align='L')
                pdf.set_font("Arial", size=12)
                line = text.strip()
                previous_speaker = speaker
            pdf.multi_cell(page_width, 10, txt=line, align='L')
        
        pdf_output = f"/tmp/{filename}"
        pdf.output(pdf_output)
        print('pdf_output',pdf_output)    
        return pdf_output
    except Exception as e:
        print(f"Erro ao criar PDF: {e}")
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

def get_transcription_infos(pdf_content, id): 
    print(id)
    payload = f"{{\"query\":\"query Transcript($transcriptId: String!) {{ transcript(id: $transcriptId) {{ title id dateString sentences {{ index speaker_name text }} }} }}\",\"variables\":{{\"transcriptId\":\"{id}\"}}}}"
        
    headers = {
        'Content-Type': 'application/json',
        'Authorization': f"Bearer {fireflies_api_key}"
    }

    response = requests.request("POST", url, headers=headers, data=payload, verify=False)
    # Verificar se a requisição foi bem-sucedida
    if response.status_code == 200:
        data = json.loads(response.text)
        transcript = data['data']["transcript"]
        print('transcript',transcript)
        
        previous_speaker = ""
        for sentence in transcript['sentences']:
            if previous_speaker: 
                if sentence['speaker_name'] == previous_speaker:
                    pdf_content = pdf_content.rstrip('\n') + f" {sentence['text']}\n"
                else:
                    pdf_content += f"{sentence['speaker_name']}: {sentence['text']}\n"
            previous_speaker = sentence['speaker_name']
            
        return pdf_content

def lambda_handler(event, context):

    try:
        # Obter o horário atual
        current_time = datetime.now()
        print('current_time.hour',current_time.hour)
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
        current_time_iso = "2024-10-24T16:19:39.117680"
        print(current_time_iso)

        payload = f"{{\"query\":\"query Transcripts($fromDate: DateTime) {{ transcripts(fromDate: $fromDate) {{ title id dateString }} }}\",\"variables\":{{\"fromDate\":\"{current_time_iso}\"}}}}"
        headers = {
            'Content-Type': 'application/json',
            'Authorization': f"Bearer {fireflies_api_key}"
        }

        response = requests.request("POST", url, headers=headers, data=payload, verify=False)

        # Verificar se a requisição foi bem-sucedida
        if response.status_code == 200:
            data = json.loads(response.text)
            print('data',data)
            transcripts = data['data']["transcripts"]
            
            if len(transcripts) > 0:
                for item in data['data']["transcripts"]:
                    print('item',item)
                    formatted_date = format_date(item['dateString'])

                    # Gerar o conteúdo do PDF
                    pdf_content = f"{item['title']} - {formatted_date}\n\n"
                    pdf_content = get_transcription_infos(pdf_content, item['id']);
    
                    # Criar o PDF
                    pdf_filename = f"{item['id']}.pdf"
                    pdf_path = format_pdf(pdf_content, pdf_filename)
                    print(f"PDF path: {pdf_path}")
                    print('pdf_content',pdf_content)        
                    # Salvar o PDF no S3
                    
                    try:
                        s3.head_bucket(Bucket=bucket_name)
                        print(f"Conexão com o bucket {bucket_name} estabelecida com sucesso.")
                    except Exception as e:
                        print(f"Erro ao conectar ao bucket S3: {e}")
                    
                    try:
                        with open(pdf_path, "rb") as pdf_file:
                            s3.put_object(Bucket=bucket_name, Key=pdf_filename, Body=pdf_file)
                        print(f"PDF salvo no S3: {pdf_filename}")
                    except Exception as e:
                        print(f"Erro ao salvar o PDF no S3: {e}")

        else:
            print('Falha na requisição para o Fireflies.')
    except requests.exceptions.RequestException as e:
        print(f"Erro na requisição: {e}")
    except Exception as e:
        print(f"Erro geral: {e}")