/**
 * RTCP connection module.
 * @version 1
 */
const rtcp = (() => {
    let connection;
    let inputChannel;
    let mediaStream;
    let candidates = Array();
    let isAnswered = false;
    let isFlushing = false;

    let connected = false;
    let inputReady = false;

    const start = (iceservers) => {
        log.info("[rtcp] <- received STUN/TURN config from the worker", iceservers);

        let conf
        if (iceservers !== "") {
            conf = {
                iceservers: {urls: iceservers}
            }
        }

        connection = conf ? new RTCPeerConnection(conf) : new RTCPeerConnection();

        mediaStream = new MediaStream();

        connection.ondatachannel = (e) => {
            log.debug(`[rtcp] ondatachannel: ${e.channel.label}`);
            inputChannel = e.channel;
            inputChannel.onopen = () => {
                log.debug("[rtcp] the input channel has opened");
                inputReady = true;
                event.pub(CONNECTION_READY);
            };
            inputChannel.onclose = () => {
                inputReady = false;
                log.debug("[rtcp] the input channel has closed");
            }
        };

        connection.oniceconnectionstatechange = ice.onIceConnectionStateChange;
        connection.onicegatheringstatechange = ice.onIceStateChange;
        connection.onicecandidate = ice.onIcecandidate;
        connection.ontrack = (event) => {
            mediaStream.addTrack(event.track);
        };

        socket.send({type: "initwebrtc"});
    };

    const ice = (() => {
        let timeForIceGathering;
        const ICE_TIMEOUT = 2000;

        return {
            onIcecandidate: (event) => {
                // this trigger when setRemoteDesc success
                // send any candidate to worker
                if (event.candidate != null) {
                    const candidate = JSON.stringify(event.candidate);
                    log.info('[rtcp] got ice candidate', candidate);
                    socket.send({type: "candidate", data: btoa(candidate)});
                }
            },
            onIceStateChange: (event) => {
                switch (event.target.iceGatheringState) {
                    case "gathering":
                        log.info("[rtcp] ice gathering");
                        timeForIceGathering = setTimeout(() => {
                            log.info(`[rtcp] ice gathering was aborted due to timeout ${ICE_TIMEOUT}ms`);
                        }, ICE_TIMEOUT);
                        break;
                    case "complete":
                        log.info("[rtcp] ice gathering completed");
                        if (timeForIceGathering) {
                            clearTimeout(timeForIceGathering);
                        }
                }
            },
            onIceConnectionStateChange: () => {
                log.info(`[rtcp] <- iceConnectionState: ${connection.iceConnectionState}`);
                switch (connection.iceConnectionState) {
                    case "connected": {
                        log.info("[rtcp] connected...");
                        connected = true;
                        break;
                    }
                    case "disconnected": {
                        log.info("[rtcp] disconnected...");
                        connected = false;
                        event.pub(CONNECTION_CLOSED);
                        break;
                    }
                    case "failed": {
                        log.error("[rtcp] connection failed, retry...");
                        connected = false;
                        connection
                            .createOffer({iceRestart: true})
                            .then((description) =>
                                connection.setLocalDescription(description).catch(log.error)
                            )
                            .catch(log.error);
                        break;
                    }
                }
            },
        };
    })();

    return {
        start: start,
        setRemoteDescription: async (data, media) => {
            const offer = new RTCSessionDescription(JSON.parse(atob(data)));
            await connection.setRemoteDescription(offer);

            const answer = await connection.createAnswer();
            // Chrome bug https://bugs.chromium.org/p/chromium/issues/detail?id=818180 workaround
            // force stereo params for Opus tracks (a=fmtp:111 ...)
            answer.sdp = answer.sdp.replace(/(a=fmtp:111 .*)/g, "$1;stereo=1;sprop-stereo=1");
            await connection.setLocalDescription(answer);

            isAnswered = true;
            event.pub(MEDIA_STREAM_CANDIDATE_FLUSH);

            socket.send({type: "answer", data: btoa(JSON.stringify(answer))});

            media.srcObject = mediaStream;
        },
        addCandidate: (data) => {
            if (data === "") {
                event.pub(MEDIA_STREAM_CANDIDATE_FLUSH);
            } else {
                candidates.push(data);
            }
        },
        flushCandidate: () => {
            if (isFlushing || !isAnswered) return;
            isFlushing = true;
            candidates.forEach((data) => {
                const d = atob(data);
                const candidate = new RTCIceCandidate(JSON.parse(d));
                log.debug("[rtcp] add candidate", d);
                connection.addIceCandidate(candidate).catch(log.error);
            });
            isFlushing = false;
        },
        input: (data) => {
            if (inputChannel) inputChannel.send(data);
        },
        isConnected: () => connected,
        isInputReady: () => inputReady,
    };
})(event, socket, log);
