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
  const appMeta = document.getElementById("app-meta");
  const appd = document.getElementById("app");
  const chatd = document.getElementById("chat");
  const numplayers = document.getElementById("numplayers");
  const discoverydropdown = document.getElementById("discoverydropdown");
  const discovery = document.getElementById("discovery");
  const appTitle = document.getElementById("app-title");
  const appContainer = document.getElementById("app-container");
  let curAppID = 0;

  var appList = [];

  discoverydropdown.addEventListener("change", () => {
    app = appList[discoverydropdown.selectedIndex];
    curAppID = app.id;
      socket.connect("http", `${app.addr}/wscloudmorph`);
      appContainer.setAttribute("src", `${location.protocol}//${app.addr}/embed`);
    updatePage(app);
  });

  //document.addEventListener(
  //"contextmenu",
  //function (e) {
  //if (isFullscreen) {
  //e.preventDefault();
  //}
  //},
  //false
  //);

  // chatsubmit.addEventListener("click", (e) => {
  //   socket.send({
  //     type: "CHAT",
  //     data: JSON.stringify({
  //       user: username.value,
  //       message: chatmessage.value,
  //     }),
  //   });
  // });

  fullscreen.addEventListener("click", (e) => {
    isFullscreen = !isFullscreen;
    if (isFullscreen) {
      chatd.style.display = "none";
      discovery.style.display = "none";
      appMeta.style.height = 0;
      appBody.style.justifyContent = "center";
      appd.style.display = "flex";
      appd.style.flexDirection = "row";
      appd.style.flexGrow = 0;
      appContainer.style.height = "99vh";
      appContainer.style.width = `${(99.0 * 8) / 6}vh`; // maintain 800x600
      fullscreen.style.position = "absolute";
      fullscreen.style.left = "0px";
      fullscreen.style.top = "0px";
      fullscreen.style.display = "block";
    } else {
      discovery.style.display = "block";
      chatd.style.display = "flex";
      appd.style.display = "block";
      appMeta.style.display = "block";
      appd.style.flexGrow = 1;
      appContainer.style.height = "100%";
      appContainer.style.width = "100%";
      appContainer.style.flexGrow = 1;
      appMeta.style.height = "auto";
      fullscreen.style.left = "auto";
      fullscreen.style.top = "auto";
      fullscreen.style.position = "static";
      fullscreen.style.display = "inline-block";
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
    chatd.style.display = app.has_chat ? "visible" : "hidden";
    appTitle.innerText = app.page_title;
    appContainer.style.height = "85vh";
    appContainer.style.width = `${
      (85 * app.screen_width) / app.screen_height
    }vh`; // maintain 800x600
    numplayers.style.visibility = app.collaborative;
  };

  event.sub(CHAT, (data) => appendChatMessage(data.chatrow));
  event.sub(NUM_PLAYER, ({ data }) => updateNumPlayers(data));
  event.sub(CLIENT_INIT, ({ data }) => {
    initApps(JSON.parse(data));
  });
  event.sub(UPDATE_APP_LIST, ({ data }) => {
    updateAppList(JSON.parse(data));
  });
})(document, event, env, socket);
