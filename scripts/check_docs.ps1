# Requires PowerShell 7. Checks documentation only; does not validate mathematics.
# Exit code 1 means a missing document, invalid UTF-8, conflict, or local link error.
#requires -Version 7.0
Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

$repoRoot = Split-Path -Parent $PSScriptRoot
$rootPrefix = $repoRoot + [IO.Path]::DirectorySeparatorChar
$pathComparison = if ($IsWindows) { [StringComparison]::OrdinalIgnoreCase } else { [StringComparison]::Ordinal }
$required = @(
    'AGENTS.md', 'README.md', 'HOMOLOGY_OPERATOR_ROADMAP.md',
    'docs/README.md', 'docs/ARCHITECTURE.md', 'docs/INTERFACE.md',
    'docs/RESULT_MODEL.md', 'docs/SOLVER_CONTRACT.md', 'docs/VALIDATION.md',
    'docs/冷启动.md'
)
$problems = [Collections.Generic.List[string]]::new()
foreach ($relativePath in $required) {
    if (-not (Test-Path -LiteralPath (Join-Path $repoRoot $relativePath) -PathType Leaf)) {
        $problems.Add("Missing required document: $relativePath")
    }
}

$documents = @(Get-ChildItem -LiteralPath $repoRoot -File -Filter '*.md')
$docsRoot = Join-Path $repoRoot 'docs'
if (Test-Path -LiteralPath $docsRoot -PathType Container) {
    $documents += @(Get-ChildItem -LiteralPath $docsRoot -Recurse -File -Filter '*.md')
}
$utf8 = [Text.UTF8Encoding]::new($false, $true)
$localLinks = 0
foreach ($document in $documents) {
    $relativePath = [IO.Path]::GetRelativePath($repoRoot, $document.FullName)
    try {
        $content = $utf8.GetString([IO.File]::ReadAllBytes($document.FullName)).TrimStart([char]0xFEFF)
    } catch {
        $problems.Add("${relativePath}: cannot read as UTF-8: $($_.Exception.Message)")
        continue
    }
    if ($content -match '(?m)^(?:<{7}|={7}|>{7})(?: |\r?$)') {
        $problems.Add("${relativePath}: unresolved merge conflict marker")
    }
    # Ignore fenced examples. This intentionally checks inline file links only.
    $prose = [regex]::Replace($content, '(?ms)^```[^\r\n]*\r?\n.*?^```[ \t]*\r?$', '')
    foreach ($match in [regex]::Matches($prose, '\[[^\]\r\n]*\]\(([^)\r\n]+)\)')) {
        $target = $match.Groups[1].Value.Trim()
        if ($target -match '^(?:[a-zA-Z][a-zA-Z0-9+.-]*:|#|//)') {
            continue
        }
        $localLinks++
        $target = [Uri]::UnescapeDataString(($target -split '[#?]', 2)[0].Trim('<', '>'))
        try {
            $basePath = $document.DirectoryName
            if ($target.StartsWith('/')) {
                $basePath = $repoRoot
                $target = $target.TrimStart('/')
            }
            $resolved = [IO.Path]::GetFullPath((Join-Path $basePath $target))
            if (-not ($resolved.Equals($repoRoot, $pathComparison) -or $resolved.StartsWith($rootPrefix, $pathComparison))) {
                $problems.Add("${relativePath}: link leaves repository: $target")
            } elseif (-not (Test-Path -LiteralPath $resolved)) {
                $problems.Add("${relativePath}: missing local link target: $target")
            }
        } catch {
            $problems.Add("${relativePath}: invalid local link: $target")
        }
    }
}

if ($problems.Count -gt 0) {
    foreach ($problem in $problems) {
        [Console]::Error.WriteLine($problem)
    }
    exit 1
}
Write-Output "Documentation checks passed: $($documents.Count) Markdown files, $localLinks local file links."
