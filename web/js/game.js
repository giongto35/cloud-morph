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
const gamed = document.getElementById("game");
const chatd = document.getElementById("chat");
const numplayers = document.getElementById("numplayers");
const discoverydropdown = document.getElementById("discoverydropdown");

var offerst;
// const offer = new RTCSessionDescription(JSON.parse(atob(data)));
// await pc.setRemoteDescription(offer);

function init() {
  const address = `${location.protocol !== "https:" ? "ws" : "wss"}://${
    location.host
  }/ws`;
  console.info(`[ws] connecting to ${address}`);
  conn = new WebSocket(address);

  // Clear old roomID
  conn.onopen = () => {
    console.log("[ws] <- open connection");
    console.log(`[ws] -> setting ping interval to ${pingIntervalMs}ms`);
    // !to add destructor if SPA
    // setInterval(ping, pingIntervalMs);
  };
  conn.onerror = (error) => console.log(`[ws] ${error}`);
  conn.onclose = () => console.log("[ws] closed");
  // Message received from server
  conn.onmessage = (response) => {
    const data = JSON.parse(response.data);
    const ptype = data.type;

    console.log(`[ws] <- message '${data}' `, ptype);
    switch (ptype) {
      case "CHAT":
        appendChatMessage(data);
        break;
      case "NUMPLAYER":
        updateNumPlayers(data);
        break;
      case "ANSWER":
        updateAnswer(data);
        break;
      case "UPDATEGAMELIST":
        updateGameList(data);
        break;
    }
  };
}

function send(data) {
  conn.send(JSON.stringify(data));
}

init();

let pc = new RTCPeerConnection({
  iceServers: [{
    urls: "stun:stun.l.google.com:19302",
  }, ],
});
pc.oniceconnectionstatechange = (e) => console.log(pc.iceConnectionState);
pc.onicecandidate = (event) => {
  console.log(event.candidate);
};

pc.ontrack = function (event) {
  var el = document.getElementById("game-screen");
  el.srcObject = event.streams[0];
};

// start session
// window.startSession = () => {
pc.addTransceiver("video", {
  direction: "recvonly"
});
pc.createOffer().then(async (offer) => {
  while (conn.readyState === WebSocket.CONNECTING) {
    await new Promise(r => setTimeout(r, 1000));
  }

  send({
    type: "OFFER",
    data: btoa(JSON.stringify(offer)),
  })
  pc.setLocalDescription(offer);
});

// document.addEventListener("contextmenu", (event) => event.preventDefault());

const gamescreen = document.getElementById("game-screen");

// log key
document.addEventListener("keydown", (e) => {
  console.log(e.keyCode);
  if (document.activeElement === username || document.activeElement === chatmessage) {
    return;
  }
  send({
    type: "KEYDOWN",
    data: JSON.stringify({
      keyCode: e.keyCode
    })
  });
});

document.addEventListener("keyup", (e) => {
  console.log(e.keyCode);
  if (document.activeElement === username || document.activeElement === chatmessage) {
    return;
  }
  send({
    type: "KEYUP",
    data: JSON.stringify({
      keyCode: e.keyCode
    })
  });
});

// Add the event listeners for mousedown, mousemove, and mouseup
gamescreen.addEventListener("mousedown", (e) => {
  x = e.offsetX;
  y = e.offsetY;
  boundRect = gamescreen.getBoundingClientRect();
  console.log(e.offsetX, e.offsetY);
  send({
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

gamescreen.addEventListener("mouseup", (e) => {
  x = e.offsetX;
  y = e.offsetY;
  boundRect = gamescreen.getBoundingClientRect();
  console.log(e.offsetX, e.offsetY);
  send({
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

gamescreen.addEventListener("mousemove", function (e) {
  x = e.offsetX;
  y = e.offsetY;
  boundRect = gamescreen.getBoundingClientRect();
  console.log(e.offsetX, e.offsetY);
  send({
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

gamescreen.addEventListener("click", (e) => {
  e.preventDefault();
  return false;
});

chatsubmit.addEventListener("click", (e) => {
  send({
    type: "CHAT",
    data: JSON.stringify({
      user: username.value,
      message: chatmessage.value,
    }),
  });
});

fullscreen.addEventListener("click", (e) => {
  isFullscreen = !isFullscreen
  if (isFullscreen) {
    chatd.style.display = "none";
    gamed.style.display = "flex";
    gamed.style.flexDirection = "row";
    gamescreen.style.height = "100vh";
    gamescreen.style.width = "133.33vh"; // maintain 800x600
  } else {
    chatd.style.display = "block";
    gamed.style.display = "block";
    gamescreen.style.height = "85vh";
    gamescreen.style.width = `${85 * 8 / 6}vh`; // maintain 800x600
  }
});

function appendChatMessage(data) {
  chatrow = JSON.parse(data.data)

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
  chatoutput.scrollTop = chatoutput.scrollHeight
}

function updateNumPlayers(data) {
  sNumPlayers = JSON.parse(data.data);
  numplayers.innerText = "Number of players: " + sNumPlayers
}

function updateGameList(data) {
  updatedGameList = JSON.parse(data.data);
  for (game of updatedGameList) {
    gameEntry = document.createElement("option");
    gameEntry.innerText = game
    discoverydropdown.appendChild(gameEntry);
  }
}

function updateAnswer(data) {
  console.log(`answer ${data.data}`);
  pc.setRemoteDescription(
    new RTCSessionDescription(JSON.parse(atob(data.data)))
  );
}