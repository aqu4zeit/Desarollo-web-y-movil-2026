# Prepara y levanta Aroma & Café en Docker.
#  1. Genera .env (no se sube a GitHub) con el token raiz de Vault y la clave root de Mongo.
#  2. Carga en Vault un secreto distinto por cada tramo entre servicios.
#  3. Crea un usuario de Mongo por servicio, con acceso solo a su base, y guarda su URI en Vault.
#  4. Crea una politica y un token de Vault por servicio (minimo privilegio).
#  5. Levanta los servicios.
# Vault corre en modo dev (en memoria): si el contenedor de Vault se reinicia, ejecutar de nuevo.

# Docker escribe su progreso en stderr; cada comando se revisa con $LASTEXITCODE
$ErrorActionPreference = "Continue"
Set-Location $PSScriptRoot

function Nuevo-Secreto {
    $bytes = New-Object byte[] 24
    [System.Security.Cryptography.RandomNumberGenerator]::Create().GetBytes($bytes)
    ($bytes | ForEach-Object { $_.ToString("x2") }) -join ""
}

# Servicios con token propio y tramos (origen-destino) con secreto propio
$servicios = "gateway", "auth", "inventory", "clients", "mensajeria", "orders", "payments", "despacho", "graphql"
$tramos = @(
    "gateway-auth", "gateway-inventory", "gateway-clients", "gateway-orders", "gateway-payments", "gateway-despacho",
    "gateway-graphql",
    "clients-auth", "clients-mensajeria",
    "graphql-inventory", "graphql-clients", "graphql-orders", "graphql-payments", "graphql-despacho",
    "orders-inventory", "orders-clients", "orders-despacho", "orders-payments",
    "payments-orders", "payments-clients", "payments-mensajeria",
    "despacho-orders",
    "laboratorio-mensajeria"
)
$conBase = "auth", "inventory", "clients", "orders", "payments", "despacho"

# Claves de los usuarios de prueba (solo laboratorio)
$clavesPrueba = [ordered]@{
    clave_admin    = "Admin2026!"
    clave_dueno    = "Dueno2026!"
    clave_cajero   = "Cajero2026!"
    clave_despacho = "Despacho2026!"
    clave_cliente  = "Camila2026!"
}

# 1. .env
$vars = [ordered]@{}
if (Test-Path .env) {
    Get-Content .env | ForEach-Object { if ($_ -match "^([^=]+)=(.*)$") { $vars[$matches[1]] = $matches[2] } }
}
if (-not $vars.VAULT_ROOT_TOKEN) { $vars.VAULT_ROOT_TOKEN = Nuevo-Secreto }
if (-not $vars.MONGO_ROOT_PASSWORD) { $vars.MONGO_ROOT_PASSWORD = Nuevo-Secreto }
# Credenciales del comercio en la plataforma de pago de prueba: las usa el
# proveedor (por .env) y payments (por Vault)
if (-not $vars.PROVEEDOR_API_KEY) { $vars.PROVEEDOR_API_KEY = Nuevo-Secreto }
if (-not $vars.PROVEEDOR_CLAVE_FIRMA) { $vars.PROVEEDOR_CLAVE_FIRMA = Nuevo-Secreto }
foreach ($s in $servicios) {
    $clave = "$($s.ToUpper())_VAULT_TOKEN"
    if (-not $vars[$clave]) { $vars[$clave] = "pendiente" }
}
function Guardar-Env { $vars.GetEnumerator() | ForEach-Object { "$($_.Key)=$($_.Value)" } | Set-Content .env -Encoding ascii }
Guardar-Env

function Vault {
    $salida = docker compose exec -T -e VAULT_ADDR=http://127.0.0.1:8200 -e "VAULT_TOKEN=$($vars.VAULT_ROOT_TOKEN)" vault vault @args
    if ($LASTEXITCODE -ne 0) { throw "Fallo: vault $args" }
    $salida
}

function Mongo($js) {
    $salida = docker compose exec -T mongo mongosh --quiet -u root -p $vars.MONGO_ROOT_PASSWORD --authenticationDatabase admin --eval $js
    if ($LASTEXITCODE -ne 0) { throw "Fallo: mongosh" }
    $salida
}

Write-Host "Levantando Vault y MongoDB..."
docker compose up -d vault mongo
if ($LASTEXITCODE -ne 0) { throw "No fue posible levantar Vault y MongoDB" }

# Espera a que ambos respondan
for ($i = 0; $i -lt 30; $i++) {
    docker compose exec -T -e VAULT_ADDR=http://127.0.0.1:8200 vault vault status 2>&1 | Out-Null
    $vaultOk = $LASTEXITCODE -eq 0
    docker compose exec -T mongo mongosh --quiet -u root -p $vars.MONGO_ROOT_PASSWORD --authenticationDatabase admin --eval "db.runCommand({ping:1}).ok" 2>&1 | Out-Null
    if ($vaultOk -and $LASTEXITCODE -eq 0) { break }
    Start-Sleep -Seconds 2
}

# 2. Secretos por tramo
Write-Host "Cargando secretos por tramo en Vault..."
foreach ($t in $tramos) {
    Vault kv put "secret/tramos/$t" "secret=$(Nuevo-Secreto)" | Out-Null
}

# 3. Usuario de Mongo por servicio y su URI en Vault
Write-Host "Creando usuarios de MongoDB por servicio..."
foreach ($s in $conBase) {
    $clave = Nuevo-Secreto
    $base = "aroma_$s"
    $usuario = "svc_$s"
    Mongo "const d = db.getSiblingDB('$base'); if (d.getUser('$usuario')) { d.updateUser('$usuario', {pwd: '$clave'}) } else { d.createUser({user: '$usuario', pwd: '$clave', roles: [{role: 'readWrite', db: '$base'}]}) }" | Out-Null
    $datos = @("mongodb_uri=mongodb://${usuario}:${clave}@mongo:27017/${base}?authSource=${base}")
    if ($s -eq "auth") { $clavesPrueba.GetEnumerator() | ForEach-Object { $datos += "$($_.Key)=$($_.Value)" } }
    if ($s -eq "payments") {
        $datos += "proveedor_api_key=$($vars.PROVEEDOR_API_KEY)"
        $datos += "proveedor_clave_firma=$($vars.PROVEEDOR_CLAVE_FIRMA)"
    }
    Vault kv put "secret/servicios/$s" @datos | Out-Null
}

# 4. Politica y token por servicio: lee solo sus tramos y su configuracion
Write-Host "Creando politicas y tokens de Vault..."
foreach ($s in $servicios) {
    $hcl = "path `"secret/data/servicios/$s`" { capabilities = [`"read`"] }`n"
    foreach ($t in $tramos) {
        $partes = $t.Split("-")
        if ($partes[0] -eq $s -or $partes[1] -eq $s) {
            $hcl += "path `"secret/data/tramos/$t`" { capabilities = [`"read`"] }`n"
        }
    }
    # Windows PowerShell agrega un BOM al enviar texto por la tuberia: se quita en el contenedor
    $hcl | docker compose exec -T -e VAULT_ADDR=http://127.0.0.1:8200 -e "VAULT_TOKEN=$($vars.VAULT_ROOT_TOKEN)" vault sh -c "tr -d '\357\273\277\r' | vault policy write $s -" | Out-Null
    if ($LASTEXITCODE -ne 0) { throw "No fue posible crear la politica $s" }
    $vars["$($s.ToUpper())_VAULT_TOKEN"] = (Vault token create "-policy=$s" -period=168h -field=token)
}
Guardar-Env

# 5. Servicios
Write-Host "Construyendo y levantando los servicios..."
docker compose up -d --build --force-recreate auth inventory clients mensajeria orders payments despacho graphql proveedor_pago gateway
if ($LASTEXITCODE -ne 0) { throw "No fue posible levantar los servicios" }

Write-Host ""
Write-Host "Listo: http://localhost:8000  (pasarela de pago de prueba: http://localhost:9500)"
Write-Host "Usuarios de prueba:"
Write-Host "  admin@aroma.cl     $($clavesPrueba.clave_admin)"
Write-Host "  dueno@aroma.cl     $($clavesPrueba.clave_dueno)"
Write-Host "  cajero@aroma.cl    $($clavesPrueba.clave_cajero)"
Write-Host "  despacho@aroma.cl  $($clavesPrueba.clave_despacho)"
Write-Host "  camila@aroma.cl    $($clavesPrueba.clave_cliente)"
