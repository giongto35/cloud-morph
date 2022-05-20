/**
 * App controller module.
 * @version 1
 */
(() => {
  const pingIntervalMs = 2000; // 2 secs
  var isFullscreen = false;

  // TODO: move to chat.js // Non core logic
  const appBody = document.getElementById("app-body");
  const appd = document.getElementById("app");
  const appTitle = document.getElementById("app-title");
  const appScreen = document.getElementById("app-screen");

  var offerst;

  const onConnectionReady = () => {
    start();
  };

  const start = () => {
    if (!rtcp.isConnected()) {
      log.error("App cannot load. Please refresh");
      return;
    }

    if (!rtcp.isInputReady()) {
      log.error("App is not ready yet. Please wait");
      return;
    }

    log.info("[control] app start");

    // TODO: Remove
    // socket.start(gameList.getCurrentGame(), env.isMobileDevice(), room.getId());

    // // end clear
    // input.poll().enable();
  };

  const onKeyPress = (data) => {
    rtcp.input(
      JSON.stringify({
        type: "KEYDOWN",
        data: JSON.stringify({
          keyCode: data.key,
        }),
      })
    );
  };

  const onKeyRelease = (data) => {
    rtcp.input(
      JSON.stringify({
        type: "KEYUP",
        data: JSON.stringify({
          keyCode: data.key,
        }),
      })
    );
  };

  const onMouseDown = (data) => {
    appScreen.muted = false;
    rtcp.input(
      JSON.stringify({
        type: "MOUSEDOWN",
        data: JSON.stringify(data),
      })
    );
  };

  const onMouseUp = (data) => {
    rtcp.input(
      JSON.stringify({
        type: "MOUSEUP",
        data: JSON.stringify(data),
      })
    );
  };

  const onMouseMove = (data) => {
    rtcp.input(
      JSON.stringify({
        type: "MOUSEMOVE",
        data: JSON.stringify(data),
      })
    );
  };

  document.addEventListener("keydown", (e) => {
    //if (
      //document.activeElement === username ||
      //document.activeElement === chatmessage
    //) {
      //return;
    //}
    event.pub(KEY_PRESSED, { key: e.keyCode });
  });

  document.addEventListener("keyup", (e) => {
    //if (
      //document.activeElement === username ||
      //document.activeElement === chatmessage
    //) {
      //return;
    //}
    event.pub(KEY_RELEASED, { key: e.keyCode });
  });

  appScreen.addEventListener("mousedown", (e) => {
    boundRect = appScreen.getBoundingClientRect();
    event.pub(MOUSE_DOWN, {
      isLeft: e.button == 0 ? 1 : 0, // 1 is right button
      x: e.offsetX,
      y: e.offsetY,
      width: boundRect.width,
      height: boundRect.height,
    });
  });

  appScreen.addEventListener("mouseup", (e) => {
    boundRect = appScreen.getBoundingClientRect();
    event.pub(MOUSE_UP, {
      isLeft: e.button == 0 ? 1 : 0, // 1 is right button
      x: e.offsetX,
      y: e.offsetY,
      width: boundRect.width,
      height: boundRect.height,
    });
  });

  appScreen.addEventListener("mousemove", function (e) {
    boundRect = appScreen.getBoundingClientRect();
    event.pub(MOUSE_MOVE, {
      isLeft: e.button == 0 ? 1 : 0, // 1 is right button
      x: e.clientX - boundRect.left,
      y: e.clientY - boundRect.top,
      width: boundRect.width,
      height: boundRect.height,
    });
  });

  document.addEventListener(
    "contextmenu",
    function (e) {
      if (isFullscreen) {
        e.preventDefault();
      }
    },
    false
  );

  event.sub(MEDIA_STREAM_INITIALIZED, (data) => {
    rtcp.start(data.stunturn);
  });
  event.sub(MEDIA_STREAM_SDP_AVAILABLE, (data) =>
    rtcp.setRemoteDescription(data.sdp, appScreen)
  );
  event.sub(MEDIA_STREAM_CANDIDATE_ADD, (data) =>
    rtcp.addCandidate(data.candidate)
  );
  event.sub(MEDIA_STREAM_CANDIDATE_FLUSH, () => rtcp.flushCandidate());
  event.sub(MEDIA_STREAM_READY, () => rtcp.start());
  event.sub(CONNECTION_READY, onConnectionReady);
  //event.sub(NUM_PLAYER, ({ data }) => updateNumPlayers(data));
  //event.sub(CLIENT_INIT, ({ data }) => {
    //initApps(JSON.parse(data));
  //});
  //event.sub(UPDATE_APP_LIST, ({ data }) => {
    //updateAppList(JSON.parse(data));
  //});
  // event.sub(CONNECTION_CLOSED, () => input.poll().disable());
  event.sub(KEY_PRESSED, onKeyPress);
  event.sub(KEY_RELEASED, onKeyRelease);
  event.sub(MOUSE_MOVE, onMouseMove);
  event.sub(MOUSE_DOWN, onMouseDown);
  event.sub(MOUSE_UP, onMouseUp);
  event.sub(KEY_STATE_UPDATED, (data) => rtcp.input(data));
})(document, event, env);
