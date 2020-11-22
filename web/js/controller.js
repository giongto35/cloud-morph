/**
 * App controller module.
 * @version 1
 */
(() => {
    const pingIntervalMs = 2000; // 2 secs
    const MOUSE_DOWN = 0;
    const MOUSE_UP = 1;
    const MOUSE_LEFT = 0;
    const MOUSE_RIGHT = 1;
    var isFullscreen = false;

    // TODO: move to chat.js // Non core logic
    const chatoutput = document.getElementById("chatoutput");
    const chatsubmit = document.getElementById("chatsubmit");
    const username = document.getElementById("chatusername");
    const message = document.getElementById("chatmessage");
    const fullscreen = document.getElementById("fullscreen");
    const appd = document.getElementById("app");
    const chatd = document.getElementById("chat");
    const numplayers = document.getElementById("numplayers");
    const discoverydropdown = document.getElementById("discoverydropdown");
    const appTitle = document.getElementById("appTitle");
    const appscreen = document.getElementById("app-screen");

    var offerst;
    // const offer = new RTCSessionDescription(JSON.parse(atob(data)));
    // await pc.setRemoteDescription(offer);
    var appList = [];

    const init = () => {
        connect(location.protocol, location.host);
        const timeoutMs = 1111;
        const address = `apps`;
        ajax.fetch(address, {method: "GET", redirect: "follow"}, timeoutMs)
            .then((data) => {
                data.json().then((body) => {
                    updateAppList(body);
                });
            });
    }

    const onConnectionReady = () => {
        // start
        start();
    };

    const start = () => {
        if (!rtcp.isConnected()) {
            log.error('App cannot load. Please refresh');
            return;
        }

        if (!rtcp.isInputReady()) {
            log.error('App is not ready yet. Please wait');
            return;
        }

        log.info('[control] app start');

        // setState(app.state.game);

        // const promise = gameScreen[0].play();
        // if (promise !== undefined) {
        //     promise.then(() => log.info('Media can autoplay'))
        //         .catch(error => {
        //             // Usually error happens when we autoplay unmuted video, browser requires manual play.
        //             // We already muted video and use separate audio encoding so it's fine now
        //             log.error('Media Failed to autoplay');
        //             log.error(error)
        //             // TODO: Consider workaround
        //         });
        // }

        // TODO get current game from the URL and not from the list?
        // if we are opening a share link it will send the default game name to the server
        // currently it's a game with the index 1
        // on the server this game is ignored and the actual game will be extracted from the share link
        // so there's no point in doing this and this' really confusing
        socket.start(gameList.getCurrentGame(), env.isMobileDevice(), room.getId());

        // // end clear
        // input.poll().enable();

    }

    event.sub(MEDIA_STREAM_INITIALIZED, (data) => {
        rtcp.start(data.stunturn);
    });
    event.sub(MEDIA_STREAM_SDP_AVAILABLE, (data) => rtcp.setRemoteDescription(data.sdp, appscreen));
    event.sub(MEDIA_STREAM_CANDIDATE_ADD, (data) => rtcp.addCandidate(data.candidate));
    event.sub(MEDIA_STREAM_CANDIDATE_FLUSH, () => rtcp.flushCandidate());
    event.sub(MEDIA_STREAM_READY, () => rtcp.start());
    event.sub(CONNECTION_READY, onConnectionReady);
    // event.sub(CONNECTION_CLOSED, () => input.poll().disable());
})($, document, event, env, socket);
