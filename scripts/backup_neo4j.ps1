# Neo4j 数据目录一致性备份（停容器 -> tar.gz -> SHA256 -> 重启 -> 计数核验）
# 用法：powershell -ExecutionPolicy Bypass -File scripts\backup_neo4j.ps1
# 备份产物写入 backups\，该目录已被 .gitignore 排除；不要提交到 Git。
[CmdletBinding()]
param(
    [string]$BackupDir = '',
    [string]$Container = 'hematology-neo4j'
)

$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent $PSScriptRoot
if (-not $BackupDir) { $BackupDir = Join-Path $root 'backups' }
$dataRoot = Join-Path $root 'neo4j'
$dataDir = Join-Path $dataRoot 'data'
$envFile = Join-Path $root '.env'

if (-not (Test-Path (Join-Path $dataDir 'databases\neo4j'))) {
    throw "未找到 Neo4j 数据目录：$dataDir"
}
$envLine = Select-String -Path $envFile -Pattern '^NEO4J_PASSWORD=' | Select-Object -First 1
if (-not $envLine) { throw ".env 缺少 NEO4J_PASSWORD" }
$password = $envLine.Line -replace '^NEO4J_PASSWORD=', ''

function Get-Count([string]$query) {
    $eap = $ErrorActionPreference
    $ErrorActionPreference = 'SilentlyContinue'
    $out = & docker exec $Container cypher-shell -u neo4j -p $password --format plain $query 2>&1
    $code = $LASTEXITCODE
    $ErrorActionPreference = $eap
    if ($code -ne 0) { return $null }
    return (($out | Select-Object -Last 1) | Out-String).Trim()
}

function Wait-Neo4jReady([int]$TimeoutSeconds = 180) {
    $deadline = (Get-Date).AddSeconds($TimeoutSeconds)
    while ((Get-Date) -lt $deadline) {
        $eap = $ErrorActionPreference
        $ErrorActionPreference = 'SilentlyContinue'
        $null = & docker exec $Container cypher-shell -u neo4j -p $password "RETURN 1;" 2>&1
        $code = $LASTEXITCODE
        $ErrorActionPreference = $eap
        if ($code -eq 0) { return $true }
        Start-Sleep -Seconds 3
    }
    return $false
}

$wasRunning = ((& docker inspect -f '{{.State.Running}}' $Container 2>$null) -eq 'true')
$beforeNodes = $null
$beforeEdges = $null
if ($wasRunning) {
    $beforeNodes = Get-Count "MATCH (n) RETURN count(n);"
    $beforeEdges = Get-Count "MATCH ()-[r]->() RETURN count(r);"
}

$imageRef = (& docker inspect -f '{{.Config.Image}}' $Container 2>$null)
$imageDigest = (& docker inspect -f '{{.Image}}' $Container 2>$null)

if ($wasRunning) {
    Write-Host "停止容器 $Container ..."
    & docker stop $Container | Out-Null
    if (((& docker inspect -f '{{.State.Running}}' $Container) -eq 'true')) {
        throw "容器未停止，拒绝在运行状态下拷贝数据"
    }
}

New-Item -ItemType Directory -Force -Path $BackupDir | Out-Null
$stamp = Get-Date -Format 'yyyyMMdd-HHmmss'
$archive = Join-Path $BackupDir "neo4j-data-$stamp.tar.gz"

try {
    Write-Host "打包 $dataDir -> $archive ..."
    & tar -czf $archive -C $dataRoot data
    if ($LASTEXITCODE -ne 0) { throw "tar 打包失败（退出码 $LASTEXITCODE）" }
}
finally {
    if ($wasRunning) {
        Write-Host "恢复启动容器 $Container ..."
        & docker start $Container | Out-Null
    }
}

$hash = (Get-FileHash -Algorithm SHA256 -Path $archive).Hash
Set-Content -Path "$archive.sha256" -Value "$hash  $(Split-Path -Leaf $archive)" -Encoding ASCII

$ready = Wait-Neo4jReady
$afterNodes = $null
$afterEdges = $null
if ($ready) {
    $afterNodes = Get-Count "MATCH (n) RETURN count(n);"
    $afterEdges = Get-Count "MATCH ()-[r]->() RETURN count(r);"
}

$meta = [ordered]@{
    created_at     = (Get-Date).ToString('o')
    archive        = $archive
    size_bytes     = (Get-Item $archive).Length
    sha256         = $hash
    container      = $Container
    image_ref      = $imageRef
    image_digest   = $imageDigest
    nodes_before   = $beforeNodes
    edges_before   = $beforeEdges
    nodes_after    = $afterNodes
    edges_after    = $afterEdges
    neo4j_ready    = $ready
    method         = '停容器后对 neo4j/data 做 tar.gz 一致性快照'
}
$metaPath = Join-Path $BackupDir "neo4j-data-$stamp.meta.json"
$meta | ConvertTo-Json | Set-Content -Path $metaPath -Encoding UTF8

Write-Host ""
Write-Host "备份完成：$archive"
Write-Host "  SHA256: $hash"
Write-Host "  大小: $([math]::Round((Get-Item $archive).Length / 1MB, 1)) MB"
Write-Host "  元数据: $metaPath"
Write-Host "  备份前 nodes/edges: $beforeNodes / $beforeEdges"
Write-Host "  恢复后 nodes/edges: $afterNodes / $afterEdges（neo4j_ready=$ready）"

if ($beforeNodes -and $afterNodes -and ($beforeNodes -ne $afterNodes -or $beforeEdges -ne $afterEdges)) {
    Write-Warning "重启前后节点/边计数不一致，请检查 neo4j/logs/neo4j.log"
}
if (-not $ready) { throw "备份已完成，但 Neo4j 在规定时间内未就绪" }
