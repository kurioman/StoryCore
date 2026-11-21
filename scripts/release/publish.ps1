<#
  Publie une nouvelle version de StoryCore (installateur Windows + mise a jour automatique des testeurs).

  Lance-le avec DEVONLY\Publier une mise a jour.bat (double-clic).
  Avant : change APP_VERSION dans app\backend\story\config.py (ex. 0.6.0 -> 0.6.1) et reconstruis l'interface
  si tu l'as modifiee (npm run build dans app\frontend).

  Ce que fait le script :
    1. lit la version, recupere ton acces GitHub (celui que Git utilise deja), verifie que la version est nouvelle ;
    2. installe les outils la premiere fois, dans _work\tools (SDK .NET + vpk de Velopack), sans rien toucher au PC ;
    3. prepare les fichiers (DEVONLY\make_release.py --folder) et compile StoryCore.exe avec son icone ;
    4. fabrique l'installateur et la mise a jour (vpk pack, avec une mise a jour "delta" depuis la version precedente) ;
    5. publie le tout sur https://github.com/kurioman/StoryCore/releases.

  Option : -NoUpload  fabrique tout dans _work\release\Releases sans rien publier (pour tester l'installateur).
#>
param([switch]$NoUpload)

$ErrorActionPreference = 'Stop'
$ProgressPreference = 'SilentlyContinue'   # sinon les telechargements sont tres lents sous PowerShell 5
[Net.ServicePointManager]::SecurityProtocol = [Net.ServicePointManager]::SecurityProtocol -bor [Net.SecurityProtocolType]::Tls12

$Root     = (Resolve-Path (Join-Path $PSScriptRoot '..\..')).Path
$Work     = Join-Path $Root '_work\release'
$Tools    = Join-Path $Root '_work\tools'
$Stage    = Join-Path $Work 'stage'
$Out      = Join-Path $Work 'Releases'
$Python   = Join-Path $Root 'app\python\python.exe'
$Icon     = Join-Path $PSScriptRoot 'storycore.ico'
$Launcher = Join-Path $PSScriptRoot 'Launcher.cs'
$Owner    = 'kurioman'
$Repo     = 'StoryCore'
$RepoUrl  = "https://github.com/$Owner/$Repo"
$ApiRepo  = "https://api.github.com/repos/$Owner/$Repo"
$PackId   = 'StoryCore'
$VelopackVersion = '1.2.161'   # meme version pour vpk et pour le module Python (app\python\Lib\site-packages\velopack)

function Step([string]$t) { Write-Host ''; Write-Host "== $t" -ForegroundColor Cyan }
function Info([string]$t) { Write-Host "   $t" }
function Fail([string]$t) { Write-Host ''; Write-Host "   ERREUR : $t" -ForegroundColor Red; Write-Host ''; exit 1 }
function Check([string]$what) { if ($LASTEXITCODE -ne 0) { Fail "$what a echoue (code $LASTEXITCODE). Copie les messages ci-dessus et montre-les a Claude." } }

# Le Python embarque ignore les reglages Python du PC (comme Start StoryCore.bat).
Remove-Item Env:PYTHONHOME, Env:PYTHONPATH, Env:PYTHONSTARTUP -ErrorAction SilentlyContinue
$env:PYTHONUTF8 = '1'
$env:PYTHONDONTWRITEBYTECODE = '1'
$env:DOTNET_CLI_TELEMETRY_OPTOUT = '1'
$env:DOTNET_NOLOGO = '1'
$env:DOTNET_ROLL_FORWARD = 'Major'

# --------------------------------------------------------------------------- 1. version et acces GitHub
Step 'Version'
$cfg = Get-Content (Join-Path $Root 'app\backend\story\config.py') -Raw -Encoding UTF8
if ($cfg -notmatch 'APP_VERSION\s*=\s*"([0-9]+\.[0-9]+\.[0-9]+[^"]*)"') { Fail 'APP_VERSION introuvable dans app\backend\story\config.py.' }
$Version = $Matches[1]
Info "StoryCore $Version"
if (-not (Test-Path $Python)) { Fail "Python embarque introuvable : $Python" }

function Get-GitHubToken {
    if ($env:GITHUB_TOKEN) { return $env:GITHUB_TOKEN.Trim() }
    $f = Join-Path $Root '_work\github_token.txt'
    if (Test-Path $f) { return (Get-Content $f -Raw).Trim() }
    if (-not (Get-Command git -ErrorAction SilentlyContinue)) { return $null }
    $ErrorActionPreference = 'Continue'   # PowerShell 5 : une sortie d'erreur redirigee ne doit pas tout arreter
    $env:GIT_TERMINAL_PROMPT = '0'
    $lines = "protocol=https`nhost=github.com`n`n" | git credential fill 2>$null
    foreach ($l in $lines) { if ($l -like 'password=*') { return $l.Substring(9).Trim() } }
    return $null
}

$Token = $null
$Headers = @{ 'User-Agent' = 'StoryCore-publish'; Accept = 'application/vnd.github+json' }
if (-not $NoUpload) {
    Step 'Acces GitHub'
    $Token = Get-GitHubToken
    if (-not $Token) {
        Fail ("Aucun acces GitHub trouve. Lance d'abord DEVONLY\Push vers GitHub.bat (il te connecte a GitHub), " +
              "puis relance ce fichier.")
    }
    $Headers.Authorization = "Bearer $Token"
    try { $info = Invoke-RestMethod "$ApiRepo" -Headers $Headers }
    catch { Fail "GitHub refuse l'acces au depot $Owner/$Repo ($($_.Exception.Message))." }
    if ($info.permissions -and -not $info.permissions.push) { Fail "Ton acces GitHub ne permet pas de publier sur $Owner/$Repo." }
    if ($info.private) {
        Write-Host '   ATTENTION : le depot est prive. Les testeurs ne pourront ni telecharger ni recevoir les mises a jour.' -ForegroundColor Yellow
        Write-Host '   Rends-le public : GitHub > StoryCore > Settings > General > Danger Zone > Change visibility.' -ForegroundColor Yellow
    }
    Info "Depot $Owner/$Repo : OK"
    $exists = $false
    try { Invoke-RestMethod "$ApiRepo/releases/tags/v$Version" -Headers $Headers | Out-Null; $exists = $true }
    catch {
        $code = 0
        if ($_.Exception.Response) { $code = [int]$_.Exception.Response.StatusCode }
        if ($code -ne 404) { Fail "Impossible de lire les versions publiees ($($_.Exception.Message))." }
    }
    if ($exists) {
        Fail ("La version $Version est deja publiee. Change APP_VERSION dans app\backend\story\config.py " +
              "(par exemple $Version -> la version suivante), puis relance.")
    }
}

# --------------------------------------------------------------------------- 2. outils
Step 'Outils (installes une seule fois dans _work\tools)'
New-Item -ItemType Directory -Force $Tools, $Work | Out-Null

# module Python de Velopack dans le Python embarque (il n'est pas dans Git : app\python est ignore)
$SitePackages = Join-Path $Root 'app\python\Lib\site-packages'
if (-not (Test-Path (Join-Path $SitePackages 'velopack\velopack.pyd'))) {
    Info "Ajout du module velopack $VelopackVersion au Python embarque..."
    $meta = Invoke-RestMethod "https://pypi.org/pypi/velopack/$VelopackVersion/json"
    $wheel = $meta.urls | Where-Object { $_.filename -like '*win_amd64.whl' } | Select-Object -First 1
    if (-not $wheel) { Fail "Module velopack $VelopackVersion introuvable sur PyPI." }
    $zip = Join-Path $Work 'velopack-wheel.zip'
    Invoke-WebRequest $wheel.url -OutFile $zip
    Expand-Archive $zip -DestinationPath $SitePackages -Force
    Remove-Item $zip
}
Info 'Module Python velopack : OK'

# SDK .NET (vpk est un outil .NET) : celui du PC s'il existe, sinon une copie locale
$Dotnet = $null
$global = Get-Command dotnet -ErrorAction SilentlyContinue
if ($global) {
    $ErrorActionPreference = 'Continue'
    $sdks = & $global.Source --list-sdks 2>$null
    $ErrorActionPreference = 'Stop'
    if ($sdks) { $Dotnet = $global.Source }
}
if (-not $Dotnet) {
    $Dotnet = Join-Path $Tools 'dotnet\dotnet.exe'
    if (-not (Test-Path $Dotnet)) {
        Info 'Installation du SDK .NET dans _work\tools\dotnet (une seule fois, quelques minutes)...'
        $inst = Join-Path $Tools 'dotnet-install.ps1'
        Invoke-WebRequest 'https://dot.net/v1/dotnet-install.ps1' -OutFile $inst
        & powershell -NoProfile -ExecutionPolicy Bypass -File $inst -Channel LTS -InstallDir (Join-Path $Tools 'dotnet') -NoPath
        Check 'Installation du SDK .NET'
    }
}
$env:DOTNET_ROOT = Split-Path $Dotnet
$env:PATH = "$($env:DOTNET_ROOT);$($env:PATH)"
Info "SDK .NET : $(& $Dotnet --version)"

$VpkDir = Join-Path $Tools 'vpk'
$Vpk = Join-Path $VpkDir 'vpk.exe'
if (-not (Test-Path $Vpk)) {
    Info "Installation de vpk $VelopackVersion..."
    & $Dotnet tool install vpk --version $VelopackVersion --tool-path $VpkDir
    if ($LASTEXITCODE -ne 0) {
        Info 'Version exacte indisponible : installation de la derniere version de vpk.'
        & $Dotnet tool install vpk --tool-path $VpkDir
        Check 'Installation de vpk'
    }
}
Info 'vpk : OK'

$Csc = Join-Path $env:WINDIR 'Microsoft.NET\Framework64\v4.0.30319\csc.exe'
if (-not (Test-Path $Csc)) { $Csc = Join-Path $env:WINDIR 'Microsoft.NET\Framework\v4.0.30319\csc.exe' }
if (-not (Test-Path $Csc)) { Fail 'Compilateur C# de Windows introuvable (.NET Framework 4).' }

# --------------------------------------------------------------------------- 3. fichiers de l'app + StoryCore.exe
Step 'Preparation des fichiers'
& $Python (Join-Path $Root 'DEVONLY\make_release.py') --folder $Stage
Check 'La preparation des fichiers'
& $Csc /nologo /target:exe /optimize+ "/win32icon:$Icon" "/out:$(Join-Path $Stage 'StoryCore.exe')" $Launcher
Check 'La compilation de StoryCore.exe'
Info 'StoryCore.exe : OK'

# notes de version : la section "## ... v0.6" de RELEASE_NOTES.md
$Notes = Join-Path $Work 'release-notes.md'
$mm = ($Version -split '\.')[0..1] -join '.'
$section = @(); $inside = $false
foreach ($l in (Get-Content (Join-Path $Root 'RELEASE_NOTES.md') -Encoding UTF8)) {
    if ($l -match '^## ') {
        if ($inside) { break }
        if ($l -match ("v" + [regex]::Escape($mm) + '(\.|\b)')) { $inside = $true }
    }
    if ($inside) { $section += $l }
}
if (-not $section) { $section = @("## StoryCore $Version") }
$section += ''
$section += 'Installation : telecharge **StoryCore-win-Setup.exe** ci-dessous et lance-le. Les mises a jour se font ensuite toutes seules au demarrage.'
[IO.File]::WriteAllLines($Notes, $section, (New-Object Text.UTF8Encoding($false)))

# --------------------------------------------------------------------------- 4. installateur et mise a jour
Step 'Fabrication de l''installateur'
if (Test-Path $Out) { Remove-Item $Out -Recurse -Force }
New-Item -ItemType Directory -Force $Out | Out-Null
if ($Token) {
    Info 'Recuperation de la version precedente (pour une mise a jour plus legere)...'
    & $Vpk download github --repoUrl $RepoUrl --token $Token -o $Out
    if ($LASTEXITCODE -ne 0) { Info 'Aucune version precedente recuperee : la mise a jour sera complete.' }
}
& $Vpk pack -u $PackId -v $Version -p $Stage -e 'StoryCore.exe' -i $Icon --packTitle 'StoryCore' --packAuthors 'Kurio' `
    --shortcuts 'Desktop,StartMenuRoot' --releaseNotes $Notes --skipVeloAppCheck -o $Out
Check 'vpk pack'

$Setup = Get-ChildItem $Out -Filter '*Setup.exe' | Select-Object -First 1
if ($Setup) {
    New-Item -ItemType Directory -Force (Join-Path $Root '_release') | Out-Null
    Copy-Item $Setup.FullName (Join-Path $Root "_release\StoryCore-Setup-$Version.exe") -Force
    Info "Copie locale : _release\StoryCore-Setup-$Version.exe"
}

if ($NoUpload) {
    Step 'Termine (rien n''a ete publie)'
    Info "Fichiers : $Out"
    exit 0
}

# --------------------------------------------------------------------------- 5. publication
Step 'Publication sur GitHub'
& $Vpk upload github --repoUrl $RepoUrl --token $Token -o $Out --publish --releaseName "StoryCore $Version" --tag "v$Version"
Check 'La publication'

Step 'Termine !'
Info "StoryCore $Version est publie : $RepoUrl/releases/tag/v$Version"
Info 'Lien a donner aux nouveaux testeurs (toujours la derniere version) :'
Write-Host "   $RepoUrl/releases/latest/download/StoryCore-win-Setup.exe" -ForegroundColor Green
Info 'Les testeurs deja installes recevront la mise a jour au prochain lancement de StoryCore.'
