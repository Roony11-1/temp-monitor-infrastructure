# clonador.ps1
# PSScriptAnalyzer: disable=PSUseApprovedVerbs

param(
    [switch]$DryRun,
    [switch]$SkipClone,
    [string]$BasePath = "",
    [string]$GitOrg = "Roony11-1"
)

if (-not $BasePath) {
    $BasePath = Resolve-Path (Join-Path $PSScriptRoot "..")
}

# ============================================
# CLASES
# ============================================
class RepoInfo {
    [string]$Name
    [string]$Status
    [string]$CurrentBranch
    [string]$LastCommitHash
    [string]$LastAuthor
    [string]$LastDate
    [string]$LastMessage
    [string]$ErrorMessage
    [string]$AheadBehind
    [string[]]$FeatureBranches
    [string]$MainVsDev

    RepoInfo([string]$name) {
        $this.Name = $name
        $this.Status = "PENDING"
    }
    
    [void] SetSuccess([string]$hash, [string]$author, [string]$date, [string]$message) {
        $this.Status = "OK"
        $this.CurrentBranch = "main"
        $this.LastCommitHash = $hash
        $this.LastAuthor = $author
        $this.LastDate = $date
        $this.LastMessage = $message
    }
    
    [void] SetError([string]$errorMsg) {
        $this.Status = "ERROR"
        $this.ErrorMessage = $errorMsg
    }
    
    [void] SetCloned() {
        $this.Status = "CLONED"
    }
    
    [void] SetSkipped() {
        $this.Status = "SKIPPED"
    }
}

# ============================================
# FUNCIONES
# ============================================
function Write-Banner {
    param([string]$Text, [string]$Color = "Cyan")
    
    $line = "=" * 44
    Write-Host $line -ForegroundColor $Color
    Write-Host "  $Text" -ForegroundColor $Color
    Write-Host $line -ForegroundColor $Color
}

function Write-RepoHeader {
    Write-Host ""
    Write-Host "--------------------------------------------" -ForegroundColor DarkGray
}

function Invoke-GitCommand {
    param(
        [string]$Command,
        [string]$ErrorMessage = "Git command failed"
    )
    
    $output = Invoke-Expression "git $Command 2>&1"
    
    if ($LASTEXITCODE -ne 0) {
        throw "$ErrorMessage : $output"
    }
    
    return $output
}

function Write-CommitDetails {
    param(
        [string]$BranchName,
        [string]$Indent = "    "
    )
    
    try {
        $hash = git rev-parse --short $BranchName 2>&1
        if ($LASTEXITCODE -ne 0) { return }
        
        $author = git log -1 $BranchName --pretty=format:"%an" 2>&1
        $date = git log -1 $BranchName --pretty=format:"%ad" --date=short 2>&1
        $message = git log -1 $BranchName --pretty=format:"%s" 2>&1
        
        $aheadBehind = Get-AheadBehindForBranch -BranchName $BranchName
        
        Write-Host "${Indent}Hash   : $($hash.Trim())" -ForegroundColor White
        Write-Host "${Indent}Autor  : $($author.Trim())" -ForegroundColor White
        Write-Host "${Indent}Fecha  : $($date.Trim())" -ForegroundColor White
        Write-Host "${Indent}Mensaje: $($message.Trim())" -ForegroundColor White
        Write-Host "${Indent}Estado : $aheadBehind" -ForegroundColor White
        
        return @{
            Hash    = $hash.Trim()
            Author  = $author.Trim()
            Date    = $date.Trim()
            Message = $message.Trim()
        }
    } catch {
        return $null
    }
}

function Get-AheadBehindForBranch {
    param([string]$BranchName)
    
    try {
        $upstream = git rev-parse --abbrev-ref "$BranchName@{upstream}" 2>&1
        if ($LASTEXITCODE -ne 0) { return "[sin upstream]" }
        
        $ahead = git rev-list --count "$BranchName@{upstream}..$BranchName" 2>&1
        $behind = git rev-list --count "$BranchName..$BranchName@{upstream}" 2>&1
        
        $result = ""
        if ($ahead -gt 0) { $result += "+$ahead" }
        if ($behind -gt 0) { $result += "-$behind" }
        
        if ([string]::IsNullOrEmpty($result)) {
            return "sincronizado"
        }
        
        return $result
    } catch {
        return "[sin upstream]"
    }
}

function Compare-Branches {
    param(
        [string]$BranchA = "main",
        [string]$BranchB = "dev"
    )
    
    try {
        # Verificar si ambas ramas existen
        $existsA = git rev-parse --verify $BranchA 2>&1
        $existsB = git rev-parse --verify $BranchB 2>&1
        
        if ($LASTEXITCODE -ne 0) {
            # Si dev no existe, no comparamos
            return ""
        }
        
        # Commits que main tiene y dev no (main ahead de dev)
        $aheadCount = git rev-list --count "$BranchB..$BranchA" 2>&1
        
        # Commits que dev tiene y main no (dev ahead de main)
        $behindCount = git rev-list --count "$BranchA..$BranchB" 2>&1
        
        if ($aheadCount -eq 0 -and $behindCount -eq 0) {
            return "main = dev (identicas)"
        } elseif ($aheadCount -gt 0 -and $behindCount -eq 0) {
            return "main +$aheadCommitCount sobre dev"
        } elseif ($aheadCount -eq 0 -and $behindCount -gt 0) {
            return "dev +$behindCommitCount sobre main"
        } else {
            return "main +$aheadCommitCount | dev +$behindCommitCount (divergidas)"
        }
    } catch {
        return ""
    }
}

function Update-Branch {
    param(
        [string]$BranchName,
        [string[]]$RemoteAliases = @($BranchName)
    )
    
    Write-Host "  Sincronizando ${BranchName}..." -ForegroundColor DarkGray
    
    try {
        Invoke-GitCommand "checkout $BranchName" 2>&1 | Out-Null
        
        if ($LASTEXITCODE -eq 0) {
            Invoke-GitCommand "pull origin $BranchName"
            Write-Host "    OK: ${BranchName} actualizado" -ForegroundColor Green
            Write-Host "    Ultimo commit en ${BranchName}:" -ForegroundColor DarkGray
            Write-CommitDetails -BranchName $BranchName
            return $true
        }
        
        throw "Branch not found locally"
        
    } catch {
        foreach ($remote in $RemoteAliases) {
            try {
                Write-Host "    Probando origin/$remote..." -ForegroundColor DarkGray
                Invoke-GitCommand "checkout -b $BranchName origin/$remote"
                Write-Host "    OK: Creada ${BranchName} desde origin/$remote" -ForegroundColor Green
                Write-Host "    Ultimo commit en ${BranchName}:" -ForegroundColor DarkGray
                Write-CommitDetails -BranchName $BranchName
                return $true
            } catch {
                continue
            }
        }
        
        Write-Host "    WARN: No se encontro '${BranchName}' en remoto" -ForegroundColor Yellow
        return $false
    }
}

function Get-FeatureBranches {
    try {
        $branches = git branch -a 2>&1 | 
            Where-Object { $_ -match 'feature/|fix/|hotfix/' } |
            ForEach-Object { $_.Trim() -replace 'remotes/origin/', '' } |
            Where-Object { -not $_.StartsWith('*') } |
            Select-Object -Unique |
            Sort-Object
        
        return @($branches)
    } catch {
        return @()
    }
}

function Invoke-RepositorySync {
    param(
        [string]$RepoName,
        [string]$OrgName
    )
    
    $info = [RepoInfo]::new($RepoName)
    
    try {
        Write-RepoHeader
        Write-Host "[$RepoName]" -ForegroundColor Yellow
        
        Push-Location $RepoName
        
        # Fetch
        Write-Host "  Fetching..." -ForegroundColor DarkGray
        Invoke-GitCommand "fetch origin --prune"
        
        # Main
        $mainResult = Update-Branch -BranchName "main"
        
        # Dev
        $devResult = Update-Branch -BranchName "dev" -RemoteAliases @("dev", "development")
        
        # Comparar main vs dev
        if ($devResult) {
            $comparison = Compare-Branches -BranchA "main" -BranchB "dev"
            if ($comparison) {
                Write-Host "  Comparacion main vs dev:" -ForegroundColor Cyan
                Write-Host "    $comparison" -ForegroundColor White
                $info.MainVsDev = $comparison
            }
        }
        
        # Buscar ramas feature/fix/hotfix
        $featureBranches = Get-FeatureBranches
        $info.FeatureBranches = $featureBranches
        
        if ($featureBranches.Count -gt 0) {
            Write-Host "  Ramas activas (feature/fix/hotfix):" -ForegroundColor Cyan
            foreach ($branch in $featureBranches) {
                $cleanBranch = $branch -replace '^\*?\s*', ''
                Write-Host "    Ultimo commit en ${cleanBranch}:" -ForegroundColor DarkGray
                Write-CommitDetails -BranchName $cleanBranch -Indent "      "
            }
        }
        
        # Guardar info de main para el resumen
        Invoke-GitCommand "switch main" | Out-Null
        $hash = git rev-parse --short HEAD 2>&1
        $author = git log -1 --pretty=format:"%an" 2>&1
        $date = git log -1 --pretty=format:"%ad" --date=short 2>&1
        $message = git log -1 --pretty=format:"%s" 2>&1
        
        $info.SetSuccess(
            $hash.Trim(),
            $author.Trim(),
            $date.Trim(),
            $message.Trim()
        )
        $info.AheadBehind = Get-AheadBehindForBranch -BranchName "main"
        
        Pop-Location
        
    } catch {
        Write-Host "  ERROR: $_" -ForegroundColor Red
        $info.SetError($_.Exception.Message)
        try { Pop-Location } catch {}
    }
    
    return $info
}

function Invoke-RepositoryClone {
    param(
        [string]$RepoName,
        [string]$OrgName
    )
    
    $info = [RepoInfo]::new($RepoName)
    $url = "https://github.com/$OrgName/$RepoName.git"
    
    try {
        Write-Host "[$RepoName] No existe localmente" -ForegroundColor Yellow
        
        if ($DryRun) {
            Write-Host "  [DRY RUN] Clonaria: $url" -ForegroundColor DarkGray
            $info.SetSkipped()
        } else {
            Write-Host "  Clonando $url..." -ForegroundColor DarkGray
            git clone $url 2>&1 | Out-Null
            
            if ($LASTEXITCODE -eq 0) {
                Write-Host "  OK: Clonado exitosamente" -ForegroundColor Green
                $info.SetCloned()
            } else {
                throw "Error al clonar"
            }
        }
        
    } catch {
        Write-Host "  ERROR al clonar: $_" -ForegroundColor Red
        $info.SetError($_.Exception.Message)
    }
    
    return $info
}

# ============================================
# SCRIPT PRINCIPAL
# ============================================
Clear-Host
Write-Banner "SINCRONIZANDO MICROSERVICIOS"

Push-Location $BasePath

$repos = @(
    "temp-monitor-api",
    "temp-monitor-frontend"
)

$results = @()
$startTime = Get-Date

foreach ($repo in $repos) {
    if (Test-Path $repo) {
        $result = Invoke-RepositorySync -RepoName $repo -OrgName $GitOrg
        $results += $result
    } elseif (-not $SkipClone) {
        $result = Invoke-RepositoryClone -RepoName $repo -OrgName $GitOrg
        $results += $result
    } else {
        Write-Host "[$repo] No existe (skip por -SkipClone)" -ForegroundColor DarkGray
        $info = [RepoInfo]::new($repo)
        $info.SetSkipped()
        $results += $info
    }
}

$duration = (Get-Date) - $startTime
Pop-Location

# ============================================
# RESUMEN FINAL
# ============================================
Write-Host ""
Write-Banner "RESUMEN"

$results | Select-Object @{N='Repo';E={$_.Name}},
                          @{N='S';E={$_.Status}},
                          @{N='Sync';E={$_.AheadBehind}},
                          @{N='main vs dev';E={$_.MainVsDev}},
                          @{N='Hash';E={$_.LastCommitHash}},
                          @{N='Autor';E={$_.LastAuthor}},
                          @{N='Fecha';E={$_.LastDate}} |
    Format-Table -AutoSize -Wrap

$okCount = ($results | Where-Object Status -eq "OK").Count
$clonedCount = ($results | Where-Object Status -eq "CLONED").Count
$errorCount = ($results | Where-Object Status -eq "ERROR").Count
$skippedCount = ($results | Where-Object Status -eq "SKIPPED").Count

Write-Host "Estadisticas:" -ForegroundColor Cyan
Write-Host "  OK: $okCount" -ForegroundColor Green
if ($clonedCount -gt 0) { Write-Host "  Clonado: $clonedCount" -ForegroundColor Yellow }
if ($errorCount -gt 0) { Write-Host "  ERROR: $errorCount" -ForegroundColor Red }
if ($skippedCount -gt 0) { Write-Host "  Skip: $skippedCount" -ForegroundColor DarkGray }
Write-Host "  Tiempo: $($duration.ToString('hh\:mm\:ss'))" -ForegroundColor Cyan

Write-Banner "PROCESO FINALIZADO" "Green"

if ($Host.Name -eq "ConsoleHost") {
    Read-Host "`nPresiona Enter para salir"
}