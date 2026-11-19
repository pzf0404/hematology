# Neo4j 数据目录恢复（校验 SHA256 -> 停容器 -> 备份现目录 -> 解包 -> 启动 -> 计数核验）
# 用法：powershell -ExecutionPolicy Bypass -File scripts\restore_neo4j.ps1 -Archive backups\neo4j-data-YYYYMMDD-HHMMSS.tar.gz
[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)][string]$Archive,
    [string]$Container = 'hematology-neo4j',
    [switch]$SkipChecksum,
    [switch]$RemovePrevious
)

$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent $PSScriptRoot
$dataRoot = Join-Path $root 'neo4j'
$dataDir = Join-Path $dataRoot 'data'
$envFile = Join-Path $root '.env'

if (-not (Test-Path $Archive)) { throw "备份文件不存在：$Archive" }
$Archive = (Resolve-Path $Archive).Path
$envLine = Select-String -Path $envFile -Pattern '^NEO4J_PASSWORD=' | Select-Object -First 1
if (-not $envLine) { throw ".env 缺少 NEO4J_PASSWORD" }
$password = $envLine.Line -replace '^NEO4J_PASSWORD=', ''

if (-not $SkipChecksum) {
    $shaFile = "$Archive.sha256"
    if (-not (Test-Path $shaFile)) { throw "缺少校验文件 $shaFile（可加 -SkipChecksum 跳过）" }
    $expected = ((Get-Content $shaFile -Raw).Trim() -split '\s+')[0].ToUpperInvariant()
    $actual = (Get-FileHash -Algorithm SHA256 -Path $Archive).Hash.ToUpperInvariant()
    if ($expected -ne $actual) { throw "SHA256 校验失败：期望 $expected，实际 $actual" }
    Write-Host "SHA256 校验通过：$actual"
}

$entries = & tar -tzf $Archive
if ($LASTEXITCODE -ne 0) { throw "无法读取备份归档" }
if (-not ($entries | Select-String -Pattern '^data/databases/neo4j/' -Quiet)) {
    throw "归档中未找到 data/databases/neo4j/，可能不是 Neo4j 数据目录备份"
}

function Get-Count([string]$query) {
    $eap = $ErrorActionPreference
    $ErrorActionPreference = 'SilentlyContinue'
    $out = & docker exec $Container cypher-shell -u neo4j -p $password --format plain $query 2>&1
    $code = $LASTEXITCODE
    $ErrorActionPreference = $eap
    if ($code -ne 0) { return $null }
    return (($out | Select-Object -Last 1) | Out-String).Trim()
}

function Wait-Neo4jReady([int]$TimeoutSeconds = 240) {
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

if (((& docker inspect -f '{{.State.Running}}' $Container 2>$null) -eq 'true')) {
    Write-Host "停止容器 $Container ..."
    & docker stop $Container | Out-Null
    if (((& docker inspect -f '{{.State.Running}}' $Container) -eq 'true')) {
        throw "容器未停止，中止恢复"
    }
}

$stamp = Get-Date -Format 'yyyyMMdd-HHmmss'
$previous = Join-Path $dataRoot "data.pre-restore-$stamp"
if (Test-Path $dataDir) {
    Write-Host "保留现有数据目录：$previous"
    Rename-Item -Path $dataDir -NewName (Split-Path -Leaf $previous)
}
New-Item -ItemType Directory -Force -Path $dataDir | Out-Null

Write-Host "解包 $Archive -> $dataRoot ..."
& tar -xzf $Archive -C $dataRoot
if ($LASTEXITCODE -ne 0) { throw "解包失败（退出码 $LASTEXITCODE）；原数据仍在 $previous" }

Write-Host "启动容器 $Container ..."
& docker start $Container | Out-Null
$ready = Wait-Neo4jReady
if (-not $ready) { throw "Neo4j 未在超时内就绪；原数据仍在 $previous，可回滚" }

$nodes = Get-Count "MATCH (n) RETURN count(n);"
$edges = Get-Count "MATCH ()-[r]->() RETURN count(r);"
$constraint = Get-Count "SHOW CONSTRAINTS YIELD name RETURN count(name);"

Write-Host ""
Write-Host "恢复完成："
Write-Host "  nodes: $nodes"
Write-Host "  edges: $edges"
Write-Host "  constraints: $constraint"
Write-Host "  原数据目录：$previous"

if ($RemovePrevious -and (Test-Path $previous)) {
    Remove-Item -Recurse -Force $previous
    Write-Host "  已删除原数据目录（-RemovePrevious）"
}
