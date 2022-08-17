param ($path,$appfile,$isSandbox,$hostIP,$vcodec)

if ([string]::IsNullOrEmpty($hostIP)) {
    $hostIP = '127.0.0.1';
}
# Split-Path $outputPath -leaf
echo "running $PSScriptRoot/winvm/$path/$appfile"

taskkill /FI "ImageName eq $appfile" /F
taskkill /FI "ImageName eq ffmpeg.exe" /F
taskkill /FI "ImageName eq syncinput.exe" /F
$app = Start-Process "$PSScriptRoot/winvm/$path/$appfile" -PassThru
sleep 2
$title = ((Get-Process -Id $app.id).mainWindowTitle)
sleep 2
# x86_64-w64-mingw32-g++ $PSScriptRoot\winvm\syncinput.cpp -o $PSScriptRoot\winvm\syncinput.exe -lws2_32 -lpthread -static

# ffmpeg setup
    $ffmpegParams = -join @(
        "-f gdigrab -framerate 30 -i title=`"$title`" -pix_fmt yuv420p "
        if ( 'h264' -eq $vcodec )
            { "-c:v libx264 -tune zerolatency " } else
            { "-c:v libvpx -deadline realtime -quality realtime " }
        "-vf scale=1280:-2 "
        "-f rtp rtp://127.0.0.2:5004 "
    )
    echo "encoding params: "$ffmpegParams

if ($isSandbox -eq "sandbox") {
    Start-Process $PSScriptRoot/winvm/pkg/ffmpeg/ffmpeg.exe -PassThru -NoNewWindow -ArgumentList "$ffmpegParams"
    sleep 2
    while ($true) {
        Start-Process -Wait $PSScriptRoot/winvm/syncinput.exe -PassThru -NoNewWindow -ArgumentList "$title", ".", "windows", $hostIP
    }
    # Restart on failure. Using service to restart on failure, not working now
    # $syncinput = New-Service -Name "Syncinput" -BinaryPathName "$PSScriptRoot\winvm\syncinput.exe $title . windows $hostIP"
    # sc failure Syncinput reset= 30 actions= restart/5000
    # $syncinput.Start()
}
else {
    Start-Process ffmpeg -PassThru -ArgumentList "$ffmpegParams"
    sleep 2
    Start-Process -PassThru $PSScriptRoot/winvm/syncinput.exe -ArgumentList "$title", ".", "windows"
}
