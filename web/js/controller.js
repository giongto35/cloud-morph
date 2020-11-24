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
    ajax
      .fetch(address, { method: "GET", redirect: "follow" }, timeoutMs)
      .then((data) => {
        data.json().then((body) => {
          updateAppList(body);
        });
      });
  };

  const onConnectionReady = () => {
    // start
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
  };

  document.addEventListener("keydown", (e) => {
    if (
      document.activeElement === username ||
      document.activeElement === chatmessage
    ) {
      return;
    }
    socket.send({
      type: "KEYDOWN",
      data: JSON.stringify({
        keyCode: e.keyCode,
      }),
    });
  });

  document.addEventListener("keyup", (e) => {
    if (
      document.activeElement === username ||
      document.activeElement === chatmessage
    ) {
      return;
    }
    socket.send({
      type: "KEYUP",
      data: JSON.stringify({
        keyCode: e.keyCode,
      }),
    });
  });

  appscreen.addEventListener("mousedown", (e) => {
    x = e.offsetX;
    y = e.offsetY;
    boundRect = appscreen.getBoundingClientRect();
    console.log(e.offsetX, e.offsetY);
    socket.send({
      type: "MOUSEDOWN",
      data: JSON.stringify({
        isLeft: e.button == 0 ? 1 : 0, // 1 is right button
        x: e.offsetX,
        y: e.offsetY,
        width: boundRect.width,
        height: boundRect.height,
      }),
    });
  });

  appscreen.addEventListener("mouseup", (e) => {
    x = e.offsetX;
    y = e.offsetY;
    boundRect = appscreen.getBoundingClientRect();
    console.log(e.offsetX, e.offsetY);
    socket.send({
      type: "MOUSEUP",
      data: JSON.stringify({
        isLeft: e.button == 0 ? 1 : 0, // 1 is right button
        x: e.offsetX,
        y: e.offsetY,
        width: boundRect.width,
        height: boundRect.height,
      }),
    });
  });

  appscreen.addEventListener("mousemove", function (e) {
    x = e.offsetX;
    y = e.offsetY;
    boundRect = appscreen.getBoundingClientRect();
    socket.send({
      type: "MOUSEMOVE",
      data: JSON.stringify({
        isLeft: e.button == 0 ? 1 : 0, // 1 is right button
        x: e.offsetX,
        y: e.offsetY,
        width: boundRect.width,
        height: boundRect.height,
      }),
    });
  });

  appscreen.addEventListener("click", (e) => {
    e.preventDefault();
    return false;
  });

  chatsubmit.addEventListener("click", (e) => {
    socket.send({
      type: "CHAT",
      data: JSON.stringify({
        user: username.value,
        message: chatmessage.value,
      }),
    });
  });

  fullscreen.addEventListener("click", (e) => {
    isFullscreen = !isFullscreen;
    if (isFullscreen) {
      chatd.style.display = "none";
      appd.style.display = "flex";
      appd.style.flexDirection = "row";
      appscreen.style.height = "100vh";
      appscreen.style.width = "133.33vh"; // maintain 800x600
    } else {
      chatd.style.display = "block";
      appd.style.display = "block";
      appscreen.style.height = "85vh";
      appscreen.style.width = `${(85 * 8) / 6}vh`; // maintain 800x600
    }
  });

  const appendChatMessage = (chatrowData) => {
    chatrow = JSON.parse(chatrowData);

    var divNode = document.createElement("div");
    var userSpanNode = document.createElement("span");
    var boldNode = document.createElement("strong");
    var messageSpanNode = document.createElement("span");
    userSpanNode.setAttribute("class", "output-user-label");
    messageSpanNode.setAttribute("class", "output-message-label");
    divNode.setAttribute("class", "output-row");
    var userTextnode = document.createTextNode(chatrow.user);
    var messageTextnode = document.createTextNode(chatrow.message);
    boldNode.appendChild(userTextnode);
    userSpanNode.appendChild(boldNode);
    messageSpanNode.appendChild(messageTextnode);
    divNode.appendChild(userSpanNode);
    divNode.appendChild(messageSpanNode);
    chatoutput.appendChild(divNode);
    chatoutput.scrollTop = chatoutput.scrollHeight;
  };

  const updateNumPlayers = (numplayersData) => {
    sNumPlayers = JSON.parse(numplayersData);
    numplayers.innerText = "Number of players: " + sNumPlayers;
  };

  // function isConnectable(addr) {
  //   const timeoutMs = 1111;
  //   const latency = await ajax.fetch(`${app.addr}/echo`, {method: "GET", redirect: "follow"}, timeoutMs);
  // }

  const updateAppList = (appData) => {
    appList = JSON.parse(appData);
    discoverydropdown.innerHTML = "";
    const timeoutMs = 1111;

    Promise.all(
      appList.map((app) => {
        const start = Date.now();
        return ajax
          .fetch(`echo`, { method: "GET", redirect: "follow" }, timeoutMs)
          .then(() => ({ [app.addr]: Date.now() - start }))
          .catch(() => ({ [app.addr]: 9999 }));
      })
    ).then((servers) => {
      const latencies = Object.assign({}, ...servers);
      console.log("[ping] <->", latencies);

      for (app of appList) {
        appEntry = document.createElement("option");
        appEntry.innerText = app.app_name + "-" + latencies[app.addr] + "ms";
        discoverydropdown.appendChild(appEntry);
      }
    });
  };

  const updatePage = (app) => {
    chatd.style.visibility = app.has_chat;
    appTitle.innerText = app.page_title;
    numplayers.style.visibility = app.collaborative;
  };

  event.sub(MEDIA_STREAM_INITIALIZED, (data) => {
    rtcp.start(data.stunturn);
  });
  event.sub(MEDIA_STREAM_SDP_AVAILABLE, (data) =>
    rtcp.setRemoteDescription(data.sdp, appscreen)
  );
  event.sub(MEDIA_STREAM_CANDIDATE_ADD, (data) =>
    rtcp.addCandidate(data.candidate)
  );
  event.sub(MEDIA_STREAM_CANDIDATE_FLUSH, () => rtcp.flushCandidate());
  event.sub(MEDIA_STREAM_READY, () => rtcp.start());
  event.sub(CONNECTION_READY, onConnectionReady);
  event.sub(CHAT, (data) => appendChatMessage(data.chatrow));
  event.sub(NUM_PLAYER, (data) => updateNumPlayers(data.numplayers));
  event.sub(UPDATE_APP_LIST, (data) => updateAppList(data.appData));
  // event.sub(CONNECTION_CLOSED, () => input.poll().disable());
})($, document, event, env, socket);
