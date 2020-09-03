const pingIntervalMs = 2000; // 2 secs
const MOUSE_DOWN = 0;
const MOUSE_UP = 1;
const MOUSE_LEFT = 0;
const MOUSE_RIGHT = 1;
var isFullscreen = false;

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
      case "NUMPLAYER":
        updateNumPlayers(data);
    }
  };
}

function send(data) {
  conn.send(JSON.stringify(data));
}

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
pc.createOffer().then((offer) => {
  console.log(offer);
  $.post(
    "http://" + location.host + "/signal",
    btoa(JSON.stringify(offer)),
    (data, status) => {
      console.log(`answer ${data} and status is ${status}`);
      pc.setRemoteDescription(
        new RTCSessionDescription(JSON.parse(atob(data)))
      );
    }
  );
  pc.setLocalDescription(offer);
});
// .catch(log);
// }

init();

// document.addEventListener("contextmenu", (event) => event.preventDefault());

const gamescreen = document.getElementById("game-screen");

// log key
document.addEventListener("keydown", logKey);

function logKey(e) {
  console.log(e.keyCode);
  send({
    type: "KEYDOWN",
    data: JSON.stringify({
      keyCode: e.keyCode
    })
  });
}

// Add the event listeners for mousedown, mousemove, and mouseup
gamescreen.addEventListener("mouseup", (e) => {
  x = e.offsetX;
  y = e.offsetY;
  b = e.button;
  boundRect = gamescreen.getBoundingClientRect();
  console.log(e.offsetX, e.offsetY);
  send({
    type: "MOUSE",
    data: JSON.stringify({
      isLeft: e.button == 0 ? 1 : 0, // 1 is right button
      isDown: 0,
      x: e.offsetX,
      y: e.offsetY,
      width: boundRect.width,
      height: boundRect.height,
    }),
  });
});

gamescreen.addEventListener("mousedown", (e) => {
  x = e.offsetX;
  y = e.offsetY;
  boundRect = gamescreen.getBoundingClientRect();
  console.log(e.offsetX, e.offsetY);
  send({
    type: "MOUSE",
    data: JSON.stringify({
      isLeft: e.button == 0 ? 1 : 0, // 1 is right button
      isDown: 1,
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

// TODO: move to chat.js // Non core logic
const chatoutput = document.getElementById("chatoutput");
const chatsubmit = document.getElementById("chatsubmit");
const username = document.getElementById("chatusername");
const message = document.getElementById("chatmessage");
const fullscreen = document.getElementById("fullscreen");
const gamed = document.getElementById("game");
const chatd = document.getElementById("chat");
const numplayers = document.getElementById("numplayers");

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
  if (!isFullscreen) {
    chatd.style.display = "none";
    gamed.style.width = "100%";
    gamed.style.height = "100%";
  } else {
    chatd.style.display = "block";
    gamed.style.width = "800px";
    gamed.style.height = "600px";
  }
  isFullscreen = !isFullscreen
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
}

function updateNumPlayers(data) {
  sNumPlayers = JSON.parse(data.data);
  numplayers.innerText = "Number of players: " + sNumPlayers
}