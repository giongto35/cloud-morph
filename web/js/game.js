const pingIntervalMs = 2000; // 2 secs
const MOUSE_DOWN = 0;
const MOUSE_UP = 1;
const MOUSE_LEFT = 0;
const MOUSE_RIGHT = 1;

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
    const message = data.id;

    if (message !== "heartbeat")
      console.log(`[ws] <- message '${message}' `, data);

    switch (message) {}
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

document.addEventListener("contextmenu", (event) => event.preventDefault());

const myPics = document.getElementById("game-screen");

// Add the event listeners for mousedown, mousemove, and mouseup
myPics.addEventListener("mouseup", (e) => {
  x = e.offsetX;
  y = e.offsetY;
  b = e.button;
  boundRect = myPics.getBoundingClientRect();
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

myPics.addEventListener("mousedown", (e) => {
  x = e.offsetX;
  y = e.offsetY;
  boundRect = myPics.getBoundingClientRect();
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

myPics.addEventListener("click", (e) => {
  e.preventDefault();
  return false;
});