import sys

ES_URL = "https://localhost:9200/photos"

try:
    with open("expt/es_auth.txt", "r") as file:
        lines = file.readlines()
        for i, line in enumerate(lines):
            if i == 0:
                ES_USERNAME = line.strip()
            if i == 1:
                ES_PASSWORD = line.strip()
except FileNotFoundError:
    print("Error: file 'es_auth.txt' was not found under directory 'expt'.")
    print("Create the file with username in 1st line and password in 2nd line.")
    sys.exit(1)
except Exception as e:
    print(e)

CERT_PATH = "./elasticsearch-9.2.1/config/certs/http_ca.crt"

VECTOR_SEARCH_TOP_K = 60
