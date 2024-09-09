import boto3
import requests
from fpdf import FPDF
from datetime import datetime
import json


# Configurações
bucket_name = "transcricoes-fireflies-ttp"
url = "https://api.fireflies.ai/graphql"
fireflies_api_key = "467f3c6a-e4a7-4910-9500-34c302dfa15c"

s3 = boto3.client('s3')

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

def lambda_handler(event, context):
    try:
        payload = "{\"query\":\"query Transcripts($fromDate: DateTime) { transcripts(fromDate: $fromDate) { title id dateString sentences { index speaker_name text } } }\",\"variables\":{\"fromDate\":\"2024-09-04T17:13:46.660Z\"}}"
        headers = {
        'Content-Type': 'application/json',
        'Authorization': 'Bearer 467f3c6a-e4a7-4910-9500-34c302dfa15c'
        }

        response = requests.request("POST", url, headers=headers, data=payload)

        # Verificar se a requisição foi bem-sucedida
        if response.status_code == 200:
            data = json.loads(response.text)

            for item in data['data']["transcripts"]:
                formatted_date = format_date(item['dateString'])

                # Gerar o conteúdo do PDF
                pdf_content = f"{item['title']} - {formatted_date}\n\n"
                previous_speaker = ""
                if item['sentences']:
                    for sentence in item['sentences']:
                        if previous_speaker: 
                            if sentence['speaker_name'] == previous_speaker:
                                pdf_content = pdf_content.rstrip('\n') + f" {sentence['text']}\n"
                            else:
                                pdf_content += f"{sentence['speaker_name']}: {sentence['text']}\n"
                        previous_speaker = sentence['speaker_name']
                        
                # Criar o PDF
                pdf_filename = f"{item['id']}.pdf"
                pdf_path = format_pdf(pdf_content, pdf_filename)

                # Salvar o PDF no S3
                with open(pdf_path, "rb") as pdf_file:
                    s3.put_object(Bucket=bucket_name, Key=pdf_filename, Body=pdf_file)

                print('PDF salvo no S3', pdf_filename)
        else:
            print('Falha na requisição para o Fireflies.')

    except requests.exceptions.RequestException as e:
        print(f"Erro na requisição: {e}")
        return {
            'statusCode': 500,
            'body': f"Erro na requisição: {e}"
        }
    except Exception as e:
        print(f"Erro geral: {e}")
        return {
            'statusCode': 500,
            'body': f"Erro geral: {e}"
        }
