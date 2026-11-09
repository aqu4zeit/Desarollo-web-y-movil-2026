# Muestra los correos que "llegaron" a una casilla en la API de mensajeria de prueba
# (codigo de verificacion, boletas). Uso: .\ver-correos.ps1 camila@aroma.cl
param([Parameter(Mandatory = $true)][string]$Correo)

Set-Location $PSScriptRoot
$raiz = (Get-Content .env | Where-Object { $_ -like "VAULT_ROOT_TOKEN=*" }).Split("=")[1]
$secreto = docker compose exec -T -e VAULT_ADDR=http://127.0.0.1:8200 -e "VAULT_TOKEN=$raiz" vault vault kv get -field=secret secret/tramos/laboratorio-mensajeria
$script = "import httpx, sys; r = httpx.get('http://mensajeria:9600/buzon', params={'correo': sys.argv[1]}, headers={'X-Service-Name': 'laboratorio', 'X-Service-Secret': sys.argv[2]}); [print('\n=== ' + m['fecha'] + '  ' + m['asunto'] + '\n' + m['cuerpo']) for m in r.json()] or print('Sin correos para', sys.argv[1])"
docker compose exec -T gateway python -c $script $Correo $secreto
