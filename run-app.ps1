$path = $args[0]
$appfile = $args[1]
$isSandbox = $args[2]
# Split-Path $outputPath -leaf
echo "running $PSScriptRoot/winvm/$path/$appfile"

taskkill /FI "ImageName eq $appfile" /F
taskkill /FI "ImageName eq ffmpeg.exe" /F
taskkill /FI "ImageName eq syncinput.exe" /F
$app = Start-Process "$PSScriptRoot/winvm/$path/$appfile" -PassThru
sleep 2
$title = ((Get-Process -Id $app.id).mainWindowTitle)
sleep 2
if ($isSandbox -eq "sandbox") {
    $localEthernetIP = (Get-NetIPAddress -AddressFamily IPv4 -InterfaceAlias ethernet).IPAddress
    Start-Process $PSScriptRoot/winvm/pkg/ffmpeg.exe -PassThru -ArgumentList "-f gdigrab -framerate 30 -i title=`"$title`" -pix_fmt yuv420p -vf scale=1280:-2 -c:v libvpx -f rtp rtp://$localEthernetIP`:5004"
}
else {
    Start-Process ffmpeg -PassThru -ArgumentList "-f gdigrab -framerate 30 -i title=`"$title`" -pix_fmt yuv420p -vf scale=1280:-2 -c:v libvpx -f rtp rtp://127.0.0.1:5004"
}
sleep 2
# x86_64-w64-mingw32-g++ $PSScriptRoot\winvm\syncinput.cpp -o $PSScriptRoot\winvm\syncinput.exe -lws2_32 -lpthread -static

Start-Process $PSScriptRoot/winvm/syncinput.exe -PassThru -ArgumentList "$title", ".", "windows"
