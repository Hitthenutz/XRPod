# One-time Git setup for Matt's XRPod clone. Run from the repo root:
#   powershell -ExecutionPolicy Bypass -File esp32\scent-node\tools\setup-git.ps1
#
# 1. Commits in this repo are authored as Hitthenutz (GitHub no-reply email).
# 2. Turns on the guard hook: on "scent*" branches, commits can only change
#    esp32/scent-node/ (override once with: git commit --no-verify).
# 3. Creates .github/CODEOWNERS so PRs touching esp32/scent-node/ ask you to review.
# 4. Optionally re-authors the setup commit and force-pushes scent-esp32.

$ErrorActionPreference = 'Continue'
$Name  = 'Hitthenutz'
$Email = '161002723+Hitthenutz@users.noreply.github.com'

$root = (git rev-parse --show-toplevel 2>$null)
if (-not $root) { Write-Host 'Run this from inside the XRPod repo.' -ForegroundColor Red; exit 1 }
Set-Location $root

Write-Host '==> Author identity (this repo only)' -ForegroundColor Cyan
git config user.name  $Name
git config user.email $Email
Write-Host "   $(git config user.name) <$(git config user.email)>"

Write-Host '==> Folder guard hook' -ForegroundColor Cyan
git config core.hooksPath esp32/scent-node/tools/git-hooks
Write-Host "   core.hooksPath = $(git config core.hooksPath)"

Write-Host '==> CODEOWNERS' -ForegroundColor Cyan
$co = Join-Path $root '.github\CODEOWNERS'
if (Test-Path $co) {
  Write-Host '   .github/CODEOWNERS already exists - not touching it.'
} else {
  $text = @(
    '# Code owners: pull requests that change these paths ask the owner for review.',
    '# To make it required, turn on "Require review from Code Owners" in the',
    '# main branch rules (GitHub > Settings > Rules or Branches).',
    '# Add teammates'' folders below as they claim them, e.g.',
    '# /pi-agent/ @their-github-username',
    '',
    '/esp32/scent-node/ @Hitthenutz'
  ) -join "`n"
  [IO.File]::WriteAllText($co, $text + "`n")
  Write-Host '   Created .github/CODEOWNERS (commit it from Source Control).'
}

Write-Host '==> Setup commit author' -ForegroundColor Cyan
$branch = git symbolic-ref --short HEAD
$headEmail = git log -1 --format=%ae
if ($branch -like 'scent*' -and $headEmail -ne $Email) {
  Write-Host "   Last commit on $branch is authored by <$headEmail>."
  git diff --cached --quiet
  if ($LASTEXITCODE -ne 0) {
    Write-Host '   You have staged changes - unstage them first, then re-run to fix the author.' -ForegroundColor Yellow
    exit 0
  }
  $ans = Read-Host '   Re-author it as Hitthenutz and force-push this branch? (y/N)'
  if ($ans -match '^[yY]') {
    git commit --amend --reset-author --no-edit --no-verify
    git push --force-with-lease origin $branch
  }
} else {
  Write-Host '   Nothing to fix.'
}

Write-Host "`nDone." -ForegroundColor Green
