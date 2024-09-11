import boto3
import requests
from fpdf import FPDF
from datetime import datetime
from dotenv import load_dotenv
import os

# Configurações
load_dotenv('config.env')


# transcript_id = "00v4bEr83aff0uvY"

# Configurações
bucket_name = os.getenv('BUCKET_S3')
fireflies_api_url = os.getenv('URL_FIREFLIES')
fireflies_api_key = os.getenv('API_KEY_FIREFLIES')

# Cliente S3
s3 = boto3.client('s3')

def create_pdf(content, filename):
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

def lambda_handler(event, context):
    # Fazer a requisição para o Fireflies
    query = """
    query Transcript($transcriptId: String!) {
        transcript(id: $transcriptId) {
            title
            dateString
            transcript_url
            audio_url
            video_url
            sentences {
                index
                speaker_name
                text
            }
            summary {
                keywords
                action_items
                outline
                shorthand_bullet
                overview
                bullet_gist
                gist
                short_summary
            }
        }
    }
    """
    variables = {"transcriptId": transcript_id}
    response = requests.post(
        fireflies_api_url,
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {fireflies_api_key}"
        },
        json={"query": query, "variables": variables}
    )
    
    # Verificar se a requisição foi bem-sucedida
    if response.status_code == 200:
        data = response.json()
        transcript = data['data']['transcript']
        
        formatted_date = format_date(transcript['dateString'])
        
        # Gerar o conteúdo do PDF
        pdf_content = f"Título: {transcript['title']}\Data: {formatted_date}\n\n"
        previous_speaker = ""
        for sentence in transcript['sentences']:
            if previous_speaker: 
                if sentence['speaker_name'] == previous_speaker:
                    pdf_content = pdf_content.rstrip('\n') + f" {sentence['text']}\n"
                else:
                    pdf_content += f"{sentence['speaker_name']}: {sentence['text']}\n"
            previous_speaker = sentence['speaker_name']
            
        # Criar o PDF
        pdf_filename = f"{transcript['title']}-{transcript['dateString']}.pdf"
        pdf_path = create_pdf(pdf_content, pdf_filename)
        
        # Salvar o PDF no S3
        with open(pdf_path, "rb") as pdf_file:
            s3.put_object(Bucket=bucket_name, Key=pdf_filename, Body=pdf_file)
        
        return {
            'statusCode': 200,
            'body': 'Requisição para o Fireflies bem-sucedida e resposta salva no S3 como PDF.'
        }
    else:
        return {
            'statusCode': response.status_code,
            'body': 'Falha na requisição para o Fireflies.'
        }
        
def format_date(date_string):
    # Converter a string para um objeto datetime
    date_object = datetime.strptime(date_string, "%Y-%m-%dT%H:%M:%S.%fZ")
    formatted_date = date_object.strftime("%d-%m-%Y")
    
    return formatted_date
