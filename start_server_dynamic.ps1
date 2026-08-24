#Requires -Version 5.1
param([switch]$VerboseOutput)
Write-Warning "start_server_dynamic.ps1 is deprecated; start_server.ps1 now always uses dynamic config mode."
& "$PSScriptRoot\\start_server.ps1" -VerboseOutput:$VerboseOutput
exit $LASTEXITCODE
