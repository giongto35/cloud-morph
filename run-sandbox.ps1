$template = @'
<Configuration>
    <vGPU>Enable</vGPU>
    <Networking>Default</Networking>
    <MappedFolders>
        <MappedFolder>
            <HostFolder>{2}</HostFolder>
            <SandboxFolder>C:\Users\cloud-morph</SandboxFolder>
        </MappedFolder>
    </MappedFolders>
    <LogonCommand>
        <Command>C:\\Windows\\System32\\WindowsPowerShell\\v1.0\\powershell.exe -ExecutionPolicy Bypass -F C:\Users\cloud-morph\run-app.ps1 {0} {1} sandbox</Command>
    </LogonCommand>
</Configuration>
'@
# Init Sandbox mount dir
# mkdir winvm/pkg
# Invoke-WebRequest -Uri "https://www.gyan.dev/ffmpeg/builds/ffmpeg-git-full.7z" -OutFile winvm/pkg/ffmpeg.7z
# 7z e winvm/pkg/ffmpeg.7z 

# Create Sandbox Config
$template -f $args[0], $args[1], "$PWD"  | Out-File -FilePath .\run-sandbox.wsb
# Run Sandbox
.\run-sandbox.wsb
# <Command>C:\\Windows\\System32\\WindowsPowerShell\\v1.0\\powershell.exe -executionpolicy unrestricted -command "start powershell \"cd C:\Users\cloud-morph; run-app.ps1 {0} {1}\""</Command>
# <Command>powershell -ExecutionPolicy Bypass -F "cd C:\Users\cloud-morph; run-app.ps1 {0} {1}"</Command>