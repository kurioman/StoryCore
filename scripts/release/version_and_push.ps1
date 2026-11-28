<#
  Etape 1 de DEVONLY\Publier une mise a jour.bat : choisir le numero de version, l'enregistrer et envoyer le code sur
  GitHub (l'APK Android est fabriquee a partir du code EN LIGNE, il doit donc etre envoye avant de publier).

    1. affiche la version actuelle (APP_VERSION dans app\backend\story\config.py) et propose la suivante ;
    2. ecrit la version choisie dans config.py ;
    3. enregistre (commit) et envoie (push) le tout sur GitHub.

  Option : -PushOnly  saute la version : enregistre et envoie seulement le code (sauvegarde, APK de test).
#>
param([switch]$PushOnly)
$ErrorActionPreference = 'Stop'
$Root = (Resolve-Path (Join-Path $PSScriptRoot '..\..')).Path
$Config = Join-Path $Root 'app\backend\story\config.py'

function Fail([string]$t) { Write-Host ''; Write-Host "   ERREUR : $t" -ForegroundColor Red; Write-Host ''; exit 1 }
function Info([string]$t) { Write-Host "   $t" }

if (-not (Get-Command git -ErrorAction SilentlyContinue)) {
    Fail "Git n'est pas installe sur ce PC. Installe-le depuis https://git-scm.com/download/win puis relance ce fichier."
}

# --------------------------------------------------------------------------- 1. numero de version
if ($PushOnly) { $Version = $null } else {
$text = [IO.File]::ReadAllText($Config)
if ($text -notmatch 'APP_VERSION\s*=\s*"([0-9]+)\.([0-9]+)\.([0-9]+)"') { Fail 'APP_VERSION introuvable dans app\backend\story\config.py.' }
$Current = [version]"$($Matches[1]).$($Matches[2]).$($Matches[3])"
$Suggested = "$($Current.Major).$($Current.Minor).$($Current.Build + 1)"

Write-Host ''
Write-Host "   Version actuelle : $Current" -ForegroundColor Cyan
Write-Host '   Format : trois nombres separes par des points (ex. 0.7.6 ou 0.7.51).'
Write-Host '   Attention : les nombres se comparent en entier, donc 0.7.51 est PLUS RECENT que 0.7.6.'
Write-Host '   Une version plus petite que la precedente ne serait jamais installee par les testeurs.'
while ($true) {
    Write-Host ''
    $answer = (Read-Host "   Nouvelle version (Entree = $Suggested)").Trim()
    if (-not $answer) { $answer = $Suggested }
    if ($answer -notmatch '^[0-9]+\.[0-9]+\.[0-9]+$') {
        Write-Host '   Format invalide : il faut exactement trois nombres, par exemple 0.7.6.' -ForegroundColor Yellow
        continue
    }
    $New = [version]$answer
    if ($New -lt $Current) {
        Write-Host "   $New est plus ancienne que $Current : les applis installees l'ignoreraient." -ForegroundColor Yellow
        continue
    }
    if ($New -eq $Current) {
        $same = (Read-Host "   Garder $Current ? Possible seulement si elle n'a jamais ete publiee (O/N)").Trim()
        if ($same -notmatch '^[oOyY]') { continue }
    }
    break
}
$Version = "$($New.Major).$($New.Minor).$($New.Build)"

# --------------------------------------------------------------------------- 2. ecrire la version
if ($New -ne $Current) {
    $updated = [regex]::Replace($text, 'APP_VERSION\s*=\s*"[^"]*"', "APP_VERSION = `"$Version`"", 1)
    [IO.File]::WriteAllText($Config, $updated, (New-Object Text.UTF8Encoding($false)))
    Info "config.py : APP_VERSION = `"$Version`""
}
}

# --------------------------------------------------------------------------- 3. commit et envoi sur GitHub
$ErrorActionPreference = 'Continue'   # git ecrit ses messages normaux sur la sortie d'erreur
Set-Location $Root
git config --global --add safe.directory ($Root -replace '\\', '/') 2>$null | Out-Null
git remote get-url origin 2>$null | Out-Null
if ($LASTEXITCODE -ne 0) { git remote add origin https://github.com/kurioman/StoryCore.git }

$others = @(git status --porcelain | Where-Object { $_ -and ($PushOnly -or $_ -notmatch 'app/backend/story/config\.py$') })
if ($others.Count -gt 0) {
    Write-Host ''
    Write-Host '   Ces fichiers sont modifies mais pas encore enregistres (commit) :' -ForegroundColor Yellow
    $others | ForEach-Object { Write-Host "     $_" }
    if ($PushOnly) { $all = (Read-Host '   Les enregistrer et les envoyer aussi ? (O/N)').Trim() }
    else { $all = (Read-Host '   Les inclure dans cette version ? (O = oui, N = seulement le numero de version)').Trim() }
    if ($all -match '^[oOyY]') { git add -A } elseif (-not $PushOnly) { git add -- app/backend/story/config.py }
} elseif (-not $PushOnly) {
    git add -- app/backend/story/config.py
}
git diff --cached --quiet
if ($LASTEXITCODE -ne 0) {
    $msg = if ($Version) { "Version $Version" } else { (Read-Host '   Description de ces modifications').Trim() }
    if (-not $msg) { $msg = 'Modifications' }
    git commit -q -m $msg
    if ($LASTEXITCODE -ne 0) { Fail "Le commit a echoue. Copie les messages ci-dessus et montre-les a Claude." }
    Info "Commit : $msg"
}

Write-Host ''
Info 'Envoi sur GitHub... (la premiere fois, une fenetre GitHub s''ouvre pour te connecter)'
git push -u origin main
if ($LASTEXITCODE -ne 0) { Fail "L'envoi sur GitHub a echoue. Copie les messages ci-dessus et montre-les a Claude." }
Info "Code envoye : https://github.com/kurioman/StoryCore"
exit 0
