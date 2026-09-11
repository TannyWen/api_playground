import requests, json, pathlib
import pandas as pd

BASE_URL = "https://processdetraining-d8a8h6dtdhhvh7e2.westeurope-01.azurewebsites.net"

#DON'T DO THIS IN A REAL-LIFE CONTEXT, USE AN .env FILE INSTEAD - 
#Nevertheless, copy your token from postman into here:
TOKEN = ""

header = {
    'Authorization': f'Bearer {TOKEN}',
    'Content-Type': 'application/json'
}

HERE = pathlib.Path(__file__).resolve().parent
OUT = HERE.parent / "training" / "data" / "my_output" / "pagination_json.json"
out_file = open(OUT, 'a')

cursor = 'init'
i = 0

while cursor:
    if i == 0:
        res = requests.post(
            headers = header,
            json = {
                'page_size': 10
                },
            url = BASE_URL + '/v1/invoices/search'
        )
    else:
        res = requests.post(
            headers=header,
            json = {
                'page_size': 10,
                'cursor': cursor
                },
            url = BASE_URL + '/v1/invoices/search'
        )

    res_dict = res.json()

    cursor = res_dict['page']['next_cursor']

    out_file.write(json.dumps(res_dict, indent=2) + r',\n')

    i += 1