const pingIntervalMs = 2000; // 2 secs

var log = (msg) => {
  document.getElementById("logs").innerHTML += msg + "<br>";
};
// const offer = new RTCSessionDescription(JSON.parse(atob(data)));
// await pc.setRemoteDescription(offer);

function init() {
  const address = `${location.protocol !== "https:" ? "ws" : "wss"}://${
    location.host
  }/ws?${params}`;
  console.info(`[ws] connecting to ${address}`);
  conn = new WebSocket(address);

  // Clear old roomID
  conn.onopen = () => {
    log.info("[ws] <- open connection");
    log.info(`[ws] -> setting ping interval to ${pingIntervalMs}ms`);
    // !to add destructor if SPA
    setInterval(ping, pingIntervalMs);
  };
  conn.onerror = (error) => log.error(`[ws] ${error}`);
  conn.onclose = () => log.info("[ws] closed");
  // Message received from server
  conn.onmessage = (response) => {
    const data = JSON.parse(response.data);
    const message = data.id;

    if (message !== "heartbeat")
      log.debug(`[ws] <- message '${message}' `, data);

    switch (message) {
    }
  };
}

function send(data) {
  conn.send(JSON.stringify(data));
}

let pc = new RTCPeerConnection({
  iceServers: [
    {
      urls: "stun:stun.l.google.com:19302",
    },
  ],
});
pc.oniceconnectionstatechange = (e) => log(pc.iceConnectionState);
pc.onicecandidate = (event) => {
  console.log(event.candidate);
  // if (event.candidate === null) {
  //   document.getElementById('localSessionDescription').value = btoa(JSON.stringify(pc.localDescription))
  // }
};

pc.ontrack = function (event) {
  var el = document.getElementById("game-screen");
  el.srcObject = event.streams[0];
};

// start session
// window.startSession = () => {
pc.addTransceiver("video", { direction: "recvonly" });
pc.createOffer()
  .then((offer) => {
    log(offer);
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
  })
  .catch(log);
// }

// log key
document.addEventListener("keydown", logKey);
function logKey(e) {
  console.log(e.keyCode);
  $.post(
    "http://" + location.host + "/key",
    e.keyCode.toString(10),
    (data, status) => {
      console.log(`${data} and status is ${status}`);
    }
  );
}

const myPics = document.getElementById("game-screen");
// Add the event listeners for mousedown, mousemove, and mouseup
myPics.addEventListener("mousedown", (e) => {
  x = e.offsetX;
  y = e.offsetY;
  boundRect = myPics.getBoundingClientRect();
  console.log(e.offsetX, e.offsetY);
  $.post(
    "http://" + location.host + "/mousedown",
    e.offsetX.toString() +
      "," +
      e.offsetY.toString() +
      "," +
      boundRect.width +
      "," +
      boundRect.height,
    (data, status) => {
      console.log(`${data} and status is ${status}`);
    }
  );
});
