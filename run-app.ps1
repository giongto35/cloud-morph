# named params
param ($path,$appfile,$tit,$vcodec)

$os = 'windows'

# Split-Path $outputPath -leaf
echo "running winvm/$path/$appfile"

taskkill /FI "ImageName eq $appfile" /F
taskkill /FI "ImageName eq ffmpeg.exe" /F
# taskkill /FI "ImageName eq syncinput.exe" /F
$app = Start-Process "winvm/$path/$appfile" -PassThru
sleep 2
$title = ((Get-Process -Id $app.id).mainWindowTitle)
sleep 2

# ffmpeg setup
$ffmpegParams = -join @(
    "-f gdigrab -framerate 30 -i title=`"$title`" -pix_fmt yuv420p "
    if ( 'h264' -eq $vcodec )
        { "-c:v libx264 -tune zerolatency " } else
        { "-c:v libvpx -deadline realtime -quality realtime " }
    "-vf `"scale=2*trunc(iw/2):-2`" "
    "-f rtp rtp://127.0.0.2:5004 "
)
echo "encoding params: "$ffmpegParams

Start-Process ffmpeg -PassThru -ArgumentList "$ffmpegParams"
sleep 2

# shim build/running
$env:CGO_ENABLED = 0
go build -o ./ ./cmd/shim/shim.go
sleep 2

# Start-Process ffmpeg -PassThru -ArgumentList "-f gdigrab -framerate 30 -i title=`"$title`" -pix_fmt yuv420p -vf scale=1280:-2 -c:v libvpx -f rtp rtp://127.0.0.2:5004"
# sleep 2
# x86_64-w64-mingw32-g++ .\winvm\syncinput.cpp -o .\winvm\syncinput.exe -lws2_32 -lpthread -static

Start-Process ./shim.exe -PassThru -ArgumentList "$title", ".", "$os"
