"use strict";

var pingIntervalMs = 2000; // 2 secs

var MOUSE_DOWN = 0;
var MOUSE_UP = 1;
var MOUSE_LEFT = 0;
var MOUSE_RIGHT = 1; // const offer = new RTCSessionDescription(JSON.parse(atob(data)));
// await pc.setRemoteDescription(offer);

function init() {
  var address = "".concat(location.protocol !== "https:" ? "ws" : "wss", "://").concat(location.host, "/ws");
  console.info("[ws] connecting to ".concat(address));
  conn = new WebSocket(address); // Clear old roomID

  conn.onopen = function () {
    console.log("[ws] <- open connection");
    console.log("[ws] -> setting ping interval to ".concat(pingIntervalMs, "ms")); // !to add destructor if SPA
    // setInterval(ping, pingIntervalMs);
  };

  conn.onerror = function (error) {
    return console.log("[ws] ".concat(error));
  };

  conn.onclose = function () {
    return console.log("[ws] closed");
  }; // Message received from server


  conn.onmessage = function (response) {
    var data = JSON.parse(response.data);
    var message = data.id;
    if (message !== "heartbeat") console.log("[ws] <- message '".concat(message, "' "), data);

    switch (message) {}
  };
}

function send(data) {
  conn.send(JSON.stringify(data));
}

var pc = new RTCPeerConnection({
  iceServers: [{
    urls: "stun:stun.l.google.com:19302"
  }]
});

pc.oniceconnectionstatechange = function (e) {
  return console.log(pc.iceConnectionState);
};

pc.onicecandidate = function (event) {
  console.log(event.candidate);
};

pc.ontrack = function (event) {
  var el = document.getElementById("app-screen");
  el.srcObject = event.streams[0];
}; // start session
// window.startSession = () => {


pc.addTransceiver("video", {
  direction: "recvonly"
});
pc.createOffer().then(function (offer) {
  console.log(offer);
  $.post("http://" + location.host + "/signal", btoa(JSON.stringify(offer)), function (data, status) {
    console.log("answer ".concat(data, " and status is ").concat(status));
    pc.setRemoteDescription(new RTCSessionDescription(JSON.parse(atob(data))));
  });
  pc.setLocalDescription(offer);
}); // .catch(log);
// }

init(); // log key

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

document.addEventListener("contextmenu", function (event) {
  return event.preventDefault();
});
var myPics = document.getElementById("app-screen"); // Add the event listeners for mousedown, mousemove, and mouseup

myPics.addEventListener("mouseup", function (e) {
  x = e.offsetX;
  y = e.offsetY;
  b = e.button;
  boundRect = myPics.getBoundingClientRect();
  console.log(e.offsetX, e.offsetY);
  send({
    type: "MOUSE",
    data: JSON.stringify({
      isLeft: e.button == 0 ? 1 : 0,
      // 1 is right button
      isDown: 0,
      x: e.offsetX,
      y: e.offsetY,
      width: boundRect.width,
      height: boundRect.height
    })
  });
});
myPics.addEventListener("mousedown", function (e) {
  x = e.offsetX;
  y = e.offsetY;
  boundRect = myPics.getBoundingClientRect();
  console.log(e.offsetX, e.offsetY);
  send({
    type: "MOUSE",
    data: JSON.stringify({
      isLeft: e.button == 0 ? 1 : 0,
      // 1 is right button
      isDown: 1,
      x: e.offsetX,
      y: e.offsetY,
      width: boundRect.width,
      height: boundRect.height
    })
  });
});
myPics.addEventListener("click", function (e) {
  e.preventDefault();
  return false;
});