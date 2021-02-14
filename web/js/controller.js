/**
 * App controller module.
 * @version 1
 */
(() => {
  const pingIntervalMs = 2000; // 2 secs
  var isFullscreen = false;

  // TODO: move to chat.js // Non core logic
  const chatoutput = document.getElementById("chatoutput");
  const chatsubmit = document.getElementById("chatsubmit");
  const username = document.getElementById("chatusername");
  const message = document.getElementById("chatmessage");
  const fullscreen = document.getElementById("fullscreen");
  const appBody = document.getElementById("app-body");
  const appd = document.getElementById("app");
  const chatd = document.getElementById("chat");
  const numplayers = document.getElementById("numplayers");
  const discoverydropdown = document.getElementById("discoverydropdown");
  const discovery = document.getElementById("discovery");
  const appTitle = document.getElementById("app-title");
  const appScreen = document.getElementById("app-screen");
  let curAppID = 0;

  var offerst;
  var appList = [];

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
    if (
      document.activeElement === username ||
      document.activeElement === chatmessage
    ) {
      return;
    }
    event.pub(KEY_PRESSED, { key: e.keyCode });
  });

  document.addEventListener("keyup", (e) => {
    if (
      document.activeElement === username ||
      document.activeElement === chatmessage
    ) {
      return;
    }
    event.pub(KEY_RELEASED, { key: e.keyCode });
  });

  discoverydropdown.addEventListener("change", () => {
    app = appList[discoverydropdown.selectedIndex];
    curAppID = app.id;
    socket.connect("http", app.addr);
    updatePage(app);
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

  document.addEventListener("mousemove", function (e) {
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
      discovery.style.display = "none";
      appBody.style.justifyContent = "center";
      appd.style.display = "flex";
      appd.style.flexDirection = "row";
      appd.style.flexGrow = 0;
      appScreen.style.height = "99vh";
      appScreen.style.width = `${(99.0 * 8) / 6}vh`; // maintain 800x600
    } else {
      discovery.style.display = "block";
      chatd.style.display = "flex";
      appd.style.display = "block";
      appScreen.style.height = "85vh";
      appScreen.style.width = `${(85 * 8) / 6}vh`; // maintain 800x600
      appScreen.style.flexGrow = 1;
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

  // TODO: Update this check before joining a room
  // function isConnectable(addr) {
  //   const timeoutMs = 1111;
  //   const latency = await ajax.fetch(`${app.addr}/echo`, {method: "GET", redirect: "follow"}, timeoutMs);
  // }

  const initApps = ({ cur_app_id, cur_app, apps }) => {
    curAppID = cur_app_id;
    updateAppList(apps);
    updatePage(cur_app);
  };

  const updateAppList = (apps) => {
    appList = apps;
    discoverydropdown.innerHTML = "";
    const timeoutMs = 1111;

    Promise.all(
      appList.map((app) => {
        const start = Date.now();
        return ajax
          .fetch(
            `http://${app.addr}/echo?_=${start}`,
            { method: "GET", redirect: "follow" },
            timeoutMs
          )
          .then(() => ({ [app.addr]: Date.now() - start }))
          .catch(() => ({ [app.addr]: 9999 }));
      })
    ).then((servers) => {
      const latencies = Object.assign({}, ...servers);
      console.log("[ping] <->", latencies);

      for (const idx of appList.keys()) {
        const app = appList[idx];
        appEntry = document.createElement("option");
        appEntry.innerText = app.app_name + "-" + latencies[app.addr] + "ms";
        discoverydropdown.appendChild(appEntry);
        if (app.id == curAppID) {
          discoverydropdown.selectedIndex = idx;
        }
      }
    });
  };

  function vh(v) {
    var h = Math.max(
      document.documentElement.clientHeight,
      window.innerHeight || 0
    );
    return (v * h) / 100;
  }

  function vw(v) {
    var w = Math.max(
      document.documentElement.clientWidth,
      window.innerWidth || 0
    );
    return (v * w) / 100;
  }

  const updatePage = (app) => {
    chatd.style.visibility = app.has_chat;
    appTitle.innerText = app.page_title;
    appScreen.style.height = "85vh";
    appScreen.style.width = `${(85 * app.screen_width) / app.screen_height}vh`; // maintain 800x600
    numplayers.style.visibility = app.collaborative;
  };

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
  event.sub(CHAT, (data) => appendChatMessage(data.chatrow));
  event.sub(NUM_PLAYER, ({ data }) => updateNumPlayers(data));
  event.sub(CLIENT_INIT, ({ data }) => {
    initApps(JSON.parse(data));
  });
  event.sub(UPDATE_APP_LIST, ({ data }) => {
    updateAppList(JSON.parse(data));
  });
  // event.sub(CONNECTION_CLOSED, () => input.poll().disable());
  event.sub(KEY_PRESSED, onKeyPress);
  event.sub(KEY_RELEASED, onKeyRelease);
  event.sub(MOUSE_MOVE, onMouseMove);
  event.sub(MOUSE_DOWN, onMouseDown);
  event.sub(MOUSE_UP, onMouseUp);
  event.sub(KEY_STATE_UPDATED, (data) => rtcp.input(data));
})($, document, event, env, socket);
