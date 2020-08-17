FROM scottyhardy/docker-wine:latest
RUN apt-get update -y
RUN apt-get install -y mingw-w64
RUN mkdir -p /winevm
WORKDIR /winevm
COPY ./ ./
RUN mkdir -p /home/wineuser/
RUN echo "2"
RUN x86_64-w64-mingw32-g++ ./sendkey.cpp -o /home/wineuser/synckey.exe -lws2_32 -static-libgcc -static-libstdc++
RUN x86_64-w64-mingw32-g++ ./sendkey.cpp -o ./synckey.exe -lws2_32 -static-libgcc -static-libstdc++
ENTRYPOINT ["/winevm/run.sh"]
