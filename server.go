package main

import (
	"bytes"
	"encoding/base64"
	"encoding/json"
	"fmt"
	"html/template"
	"io/ioutil"
	"log"
	"net"
	"net/http"
	"os/exec"
	"syscall"
	"time"

	"github.com/gofrs/uuid"
	"github.com/gorilla/mux"
	"github.com/gorilla/websocket"
	"github.com/pion/rtp"
	"github.com/pion/webrtc/v2"
	"gopkg.in/yaml.v2"
)

var webrtcconfig = webrtc.Configuration{ICEServers: []webrtc.ICEServer{{URLs: []string{"stun:stun.l.google.com:19302"}}}}

var WineConn net.Conn
var isStarted bool

const startRTPPort = 5004

var cuRTPPort = startRTPPort
var videoStream = map[string]chan *rtp.Packet{}
var payloadType uint8
var ssrc uint32
var upgrader = websocket.Upgrader{}

const eventKeyDown = "KEYDOWN"
const eventMouse = "MOUSE"
const configFilePath = "config.yaml"

type WSPacket struct {
	PType string `json:"type"`
	// TODO: Make Data generic: map[string]interface{} for more usecases
	Data string `json:"data"`
}

type appConfig struct {
	Path       string `yaml:"path"`
	AppFile    string `yaml:"appFile"`
	WidowTitle string `yaml:"windowTitle"` // To help WinAPI search the app
}

var curApp string = "Notepad"

const indexPage string = "web/index.html"
const addr string = ":8080"

type Server struct {
	httpServer *http.Server
	// browserClients are the map sessionID to browser Client
	clients map[string]*Client
}

type Client struct {
	conn      *websocket.Conn
	SessionID string

	done chan struct{}
}

// GetWeb returns web frontend
func (o *Server) GetWeb(w http.ResponseWriter, r *http.Request) {
	tmpl, err := template.ParseFiles(indexPage)
	if err != nil {
		log.Fatal(err)
	}

	tmpl.Execute(w, nil)
}

func NewClient(c *websocket.Conn, browserID string) *Client {
	return &Client{
		conn:      c,
		SessionID: browserID,
		done:      make(chan struct{}),
	}
}

func NewServer(cfg appConfig) *Server {
	server := &Server{
		clients: map[string]*Client{},
	}

	r := mux.NewRouter()
	r.HandleFunc("/ws", server.WS)
	r.PathPrefix("/static/").Handler(http.StripPrefix("/static/", http.FileServer(http.Dir("./web"))))
	r.HandleFunc("/signal", Signalling)

	r.PathPrefix("/").HandlerFunc(server.GetWeb)

	svmux := &http.ServeMux{}
	svmux.Handle("/", r)

	httpServer := &http.Server{
		Addr:         addr,
		ReadTimeout:  5 * time.Second,
		WriteTimeout: 5 * time.Second,
		IdleTimeout:  120 * time.Second,
		Handler:      svmux,
	}
	server.httpServer = httpServer
	log.Println("Spawn server")

	return server
}

func (o *Server) ListenAndServe() error {
	log.Println("Server is running at", addr)
	return o.httpServer.ListenAndServe()
}

// WSO handles all connections from user/frontend to coordinator
func (o *Server) WS(w http.ResponseWriter, r *http.Request) {
	log.Println("A user is connecting...")
	defer func() {
		if r := recover(); r != nil {
			log.Println("Warn: Something wrong. Recovered in ", r)
		}
	}()

	// be aware of ReadBufferSize, WriteBufferSize (default 4096)
	// https://pkg.go.dev/github.com/gorilla/websocket?tab=doc#Upgrader
	c, err := upgrader.Upgrade(w, r, nil)
	if err != nil {
		log.Println("Coordinator: [!] WS upgrade:", err)
		return
	}

	// Generate sessionID for browserClient
	var sessionID string
	for {
		sessionID = uuid.Must(uuid.NewV4()).String()
		// check duplicate
		if _, ok := o.clients[sessionID]; !ok {
			break
		}
	}

	// Create browserClient instance
	client := NewClient(c, sessionID)
	// Run browser listener first (to capture ping)
	go func(client *Client) {
		client.Listen()
		delete(o.clients, client.SessionID)
	}(client)
}

// Heartbeat maintains connection to server
func (c *Client) Heartbeat() {
	// send heartbeat every 1s
	timer := time.Tick(time.Second)

	for range timer {
		select {
		case <-c.done:
			log.Println("Close heartbeat")
			return
		default:
		}
		// c.Send({PType: "heartbeat"})
	}
}

func (c *Client) Send(packet WSPacket) {
	data, err := json.Marshal(packet)
	if err != nil {
		return
	}

	c.conn.WriteMessage(websocket.TextMessage, data)
}

func (c *Client) Listen() {
	defer func() {
		close(c.done)
	}()

	for {
		_, rawMsg, err := c.conn.ReadMessage()
		if err != nil {
			log.Println("[!] read:", err)
			// TODO: Check explicit disconnect error to break
			break
		}
		wspacket := WSPacket{}
		err = json.Unmarshal(rawMsg, &wspacket)

		if err != nil {
			log.Println("error decoding", err)
			continue
		}
		switch wspacket.PType {
		case eventKeyDown:
			simulateKeyDown(wspacket.Data)
		case eventMouse:
			simulateMouseEvent(wspacket.Data)
		}
	}
}

func initConfig() (appConfig, error) {
	cfgyml, err := ioutil.ReadFile(configFilePath)
	if err != nil {
		return appConfig{}, err
	}

	cfg := appConfig{}
	err = yaml.Unmarshal(cfgyml, &cfg)
	return cfg, err
}

func main() {
	// HTTP server
	// TODO: Make the communication over websocket
	http.Handle("/assets/", http.StripPrefix("/assets", http.FileServer(http.Dir("./assets"))))

	cfg, err := initConfig()
	if err != nil {
		log.Fatal(err)
	}
	log.Printf("%v", cfg)

	server := NewServer(cfg)
	launchGameVM(cuRTPPort, cfg.Path, cfg.AppFile, cfg.WidowTitle)
	go WineInteract()
	log.Println("done wine interact")
	err = server.ListenAndServe()
	if err != nil {
		log.Fatal(err)
	}
}

// WineInteract starts Virtual buffer + Controller utitlity
func WineInteract() {
	log.Println("listening wine at port 9090")
	ln, err := net.Listen("tcp", ":9090")
	if err != nil {
		// handle error
	}

	// go startXVFB()

	// Read video stream from encoded video stream produced by FFMPEG
	listener, listenerssrc := newLocalStreamListener(cuRTPPort)
	ssrc = listenerssrc

	// Broadcast video stream
	go func() {
		defer func() {
			listener.Close()
			log.Println("Closing game VM")
			// close(gameVMDone)
		}()

		// Read RTP packets forever and send them to the WebRTC Client
		for {
			// TODO: avoid allocating new inboundRTPPacket
			inboundRTPPacket := make([]byte, 4096) // UDP MTU
			n, _, err := listener.ReadFrom(inboundRTPPacket)
			if err != nil {
				log.Printf("error during read: %s", err)
				panic(err)
			}

			packet := &rtp.Packet{}
			if err := packet.Unmarshal(inboundRTPPacket[:n]); err != nil {
				panic(err)
			}
			if payloadType == 0 {
				continue
			}
			packet.Header.PayloadType = payloadType

			for _, stream := range videoStream {
				stream <- packet
			}
		}
	}()

	// Maintain input stream from server to Virtual Machine over websocket
	// Why Websocket: because normal IPC cannot communicate cross OS.
	for {
		conn, err := ln.Accept()
		if err != nil {
			// handle error
		}
		handleConnection(conn)
	}
}

func handleConnection(conn net.Conn) {
	log.Println("Wine connected")
	WineConn = conn
	go healthCheckVM(conn)
}

// healthCheckVM to maintain connection
func healthCheckVM(conn net.Conn) {
	for {
		conn.Write([]byte{0})
		time.Sleep(2 * time.Second)
	}
}

// Encode encodes the input in base64
// It can optionally zip the input before encoding
func Encode(obj interface{}) string {
	b, err := json.Marshal(obj)
	if err != nil {
		panic(err)
	}

	return base64.StdEncoding.EncodeToString(b)
}

// Decode decodes the input from base64
// It can optionally unzip the input after decoding
func Decode(in string, obj interface{}) {
	b, err := base64.StdEncoding.DecodeString(in)
	if err != nil {
		panic(err)
	}

	err = json.Unmarshal(b, obj)
	if err != nil {
		panic(err)
	}
}

// done to forcefully stop all processes
func launchGameVM(rtpPort int, appPath string, appFile string, windowTitle string) chan struct{} {
	var cmd *exec.Cmd
	var streamCmd *exec.Cmd

	var out bytes.Buffer
	var stderr bytes.Buffer

	// go func() {
	// 	log.Println("Reading pipe stderr")
	// 	for {
	// 		log.Println(string(stderr.Bytes()))
	// 		time.Sleep(time.Second)
	// 	}
	// }()
	// go func() {
	// 	log.Println("Reading pipe stdout")
	// 	for {
	// 		log.Println(string(out.Bytes()))
	// 		time.Sleep(time.Second)
	// 	}
	// }()

	gameSpawned := make(chan struct{})
	go func() {
		log.Println("execing run-client.sh")
		// cmd = exec.Command("./run-wine-nodocker.sh", appCfg[appName].path, appCfg[appName].appName, appCfg[appName].windowTitle)
		cmd = exec.Command("./run-wine.sh", appPath, appFile, windowTitle)

		cmd.Stdout = &out
		cmd.Stderr = &stderr
		err := cmd.Run()
		if err != nil {
			panic(err)
		}
		log.Println("execed run-client.sh")
		close(gameSpawned)
	}()

	done := make(chan struct{})
	// clean up func
	go func() {
		<-done
		err := streamCmd.Process.Kill()
		log.Println("Kill streamcmd: ", err)

		err = cmd.Process.Kill()
		log.Println("Kill game: ", err)

		log.Println("killing", streamCmd.Process.Pid)
		syscall.Kill(streamCmd.Process.Pid, syscall.SIGKILL)
	}()

	return done
}

// streapRTP is based on to https://github.com/pion/webrtc/tree/master/examples/rtp-to-webrtc
// It fetches from a RTP stream produced by FFMPEG and broadcast to all webRTC sessions
func streamRTP(conn *webrtc.PeerConnection, offer webrtc.SessionDescription, ssrc uint32) *webrtc.Track {
	// We make our own mediaEngine so we can place the sender's codecs in it.  This because we must use the
	// dynamic media type from the sender in our answer. This is not required if we are the offerer
	mediaEngine := webrtc.MediaEngine{}
	err := mediaEngine.PopulateFromSDP(offer)
	if err != nil {
		panic(err)
	}

	// Search for VP8 Payload type. If the offer doesn't support VP8 exit since
	// since they won't be able to decode anything we send them
	for _, videoCodec := range mediaEngine.GetCodecsByKind(webrtc.RTPCodecTypeVideo) {
		if videoCodec.Name == "VP8" {
			payloadType = videoCodec.PayloadType
			break
		}
	}
	log.Println("Payload type", payloadType)
	if payloadType == 0 {
		panic("Remote peer does not support VP8")
	}

	// Create a video track, using the same SSRC as the incoming RTP Pack)
	videoTrack, err := conn.NewTrack(payloadType, ssrc, "video", "pion")
	if err != nil {
		panic(err)
	}
	if _, err = conn.AddTrack(videoTrack); err != nil {
		panic(err)
	}

	// Set the handler for ICE connection state
	// This will notify you when the peer has connected/disconnected
	conn.OnICEConnectionStateChange(func(connectionState webrtc.ICEConnectionState) {
		log.Printf("Connection State has changed %s \n", connectionState.String())
	})

	// Set the remote SessionDescription
	if err = conn.SetRemoteDescription(offer); err != nil {
		panic(err)
	}
	log.Println("Done creating videotrack")

	return videoTrack
}

// newLocalStreamListener returns RTP: listener and SSRC of that listener
func newLocalStreamListener(rtpPort int) (*net.UDPConn, uint32) {
	// Open a UDP Listener for RTP Packets on port 5004
	listener, err := net.ListenUDP("udp", &net.UDPAddr{IP: net.ParseIP("127.0.0.1"), Port: rtpPort})
	if err != nil {
		panic(err)
	}

	// Listen for a single RTP Packet, we need this to determine the SSRC
	inboundRTPPacket := make([]byte, 4096) // UDP MTU
	n, _, err := listener.ReadFromUDP(inboundRTPPacket)
	if err != nil {
		panic(err)
	}

	// Unmarshal the incoming packet
	packet := &rtp.Packet{}
	if err = packet.Unmarshal(inboundRTPPacket[:n]); err != nil {
		panic(err)
	}

	return listener, packet.SSRC
}

// Signalling is to setup new webRTC connection
// TODO: Change to Socket
func Signalling(w http.ResponseWriter, r *http.Request) {
	id := uuid.Must(uuid.NewV4()).String()
	videoStream[id] = make(chan *rtp.Packet)

	log.Println("Signalling")

	RTCConn, err := webrtc.NewPeerConnection(webrtcconfig)
	if err != nil {
		log.Println("error ", err)
	}

	bodyBytes, _ := ioutil.ReadAll(r.Body)
	offerString := string(bodyBytes)
	log.Println("Got Offer: ", offerString)

	offer := webrtc.SessionDescription{}
	Decode(offerString, &offer)

	err = RTCConn.SetRemoteDescription(offer)
	if err != nil {
		log.Println("Set remote description from peer failed", err)
		return
	}

	videoTrack := streamRTP(RTCConn, offer, ssrc)

	var answer webrtc.SessionDescription
	answer, err = RTCConn.CreateAnswer(nil)
	if err != nil {
		log.Println("Create Answer Failed", err)
		return
	}

	err = RTCConn.SetLocalDescription(answer)
	if err != nil {
		log.Println("Set Local Description Failed", err)
		return
	}

	isStarted = true
	w.Write([]byte(Encode(answer)))

	go func() {
		for packet := range videoStream[id] {
			if writeErr := videoTrack.WriteRTP(packet); writeErr != nil {
				panic(writeErr)
			}
		}
	}()
}

func simulateKeyDown(jsonPayload string) {
	if isStarted == false {
		return
	}
	if WineConn == nil {
		return
	}

	log.Println("KeyDown event", jsonPayload)
	type keydownPayload struct {
		KeyCode int `json:keycode`
	}
	p := &keydownPayload{}
	json.Unmarshal([]byte(jsonPayload), &p)

	WineConn.Write([]byte{byte(p.KeyCode)})
}

// simulateMouseEvent handles mouse down event and send it to Virtual Machine over TCP port
func simulateMouseEvent(jsonPayload string) {
	if isStarted == false {
		return
	}
	if WineConn == nil {
		return
	}

	log.Println("MouseDown event", jsonPayload)
	type mousedownPayload struct {
		IsLeft byte    `json:isLeft`
		IsDown byte    `json:isDown`
		X      float32 `json:x`
		Y      float32 `json:y`
		Width  float32 `json:width`
		Height float32 `json:height`
	}
	p := &mousedownPayload{}
	json.Unmarshal([]byte(jsonPayload), &p)

	// Mouse is in format of comma separated "12.4,52.3"
	mousePayload := fmt.Sprintf("%d,%d,%f,%f,%f,%f", p.IsLeft, p.IsDown, p.X, p.Y, p.Width, p.Height)
	WineConn.Write([]byte(mousePayload))
}
