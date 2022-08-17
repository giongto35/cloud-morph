param ($vcodec)

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
        <Command>C:\\Windows\\System32\\WindowsPowerShell\\v1.0\\powershell.exe -ExecutionPolicy Bypass -F C:\Users\cloud-morph\run-app.ps1 {0} {1} sandbox {3} -vcodec {4}</Command>
    </LogonCommand>
</Configuration>
'@

# To install Virtual Box Image. Copy FFMPEG to VM

# Create Sandbox Config

$localEthernetIP = (Get-NetIPAddress -AddressFamily IPv4 -InterfaceAlias ethernet).IPAddress
# pass variables in orders to template
$template -f $args[0], $args[1], "$PWD", $localEthernetIP, $vcodec | Out-File -FilePath .\run-sandbox.wsb
# x86_64-w64-mingw32-g++ $PSScriptRoot\winvm\syncinput.cpp -o $PSScriptRoot\winvm\syncinput.exe -lws2_32 -lpthread -static

powershell -ExecutionPolicy Bypass -F "setup-sandbox.ps1"
# Run Sandbox
.\run-sandbox.wsb
