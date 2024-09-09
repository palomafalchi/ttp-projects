import boto3
import requests
from fpdf import FPDF

# Configurações
bucket_name = "transcricoes-fireflies-ttp"
fireflies_api_url = "https://api.fireflies.ai/graphql"
fireflies_api_key = "467f3c6a-e4a7-4910-9500-34c302dfa15c"
transcript_id = "Kkgk2F7dhbU4S3p7"

# Cliente S3
s3 = boto3.client('s3')

def create_pdf(content, filename):
    pdf = FPDF()
    pdf.add_page()
    pdf.set_font("Arial", size=12)
    
    for line in content.split('\n'):
        pdf.cell(200, 10, txt=line, ln=True, align='L')
    
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
        
        # Gerar o conteúdo do PDF
        pdf_content = f"Title: {transcript['title']}\nDate: {transcript['dateString']}\n\n"
        for sentence in transcript['sentences']:
            pdf_content += f"{sentence['index']}. {sentence['speaker_name']}: {sentence['text']}\n"
        
        # Criar o PDF
        pdf_filename = f"fireflies-transcript-{transcript_id}.pdf"
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