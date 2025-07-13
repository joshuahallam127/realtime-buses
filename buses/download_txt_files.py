import zipfile
import os
import requests
from dotenv import load_dotenv
from io import BytesIO

load_dotenv()

os.system('rm -rf *.txt')

url = 'https://api.transport.nsw.gov.au/v1/gtfs/schedule/buses'
headers = { 'Authorization': f'apikey {os.getenv('APIKEY')}' }

response = requests.get(url, headers=headers)

with zipfile.ZipFile(BytesIO(response.content)) as zip_ref:
    zip_ref.extractall('.')