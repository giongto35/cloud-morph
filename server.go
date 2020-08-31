package main

import (
	"encoding/base64"
	"encoding/json"
	"fmt"
	"html/template"
	"io/ioutil"
	"log"
	"net/http"
	"time"

	"github.com/giongto35/cloud-morph/core/go/cloudgame"
	"github.com/gofrs/uuid"
	"github.com/gorilla/mux"
	"github.com/gorilla/websocket"
	"github.com/pion/rtp"
	"github.com/pion/webrtc/v2"
	"gopkg.in/yaml.v2"
)

var webrtcconfig = webrtc.Configuration{ICEServers: []webrtc.ICEServer{{URLs: []string{"stun:stun.l.google.com:19302"}}}}

var isStarted bool

var upgrader = websocket.Upgrader{}

const configFilePath = "config.yaml"

var curApp string = "Notepad"

const indexPage string = "web/index.html"
const addr string = ":8080"

// TODO: multiplex clientID
var clientID string
var payloadType uint8

type Server struct {
	httpServer *http.Server
	// browserClients are the map clientID to browser Client
	clients map[string]*Client
	events  chan cloudgame.WSPacket
	cgame   cloudgame.CloudGameClient
}

type Client struct {
	conn     *websocket.Conn
	clientID string

	serverEvents chan cloudgame.WSPacket
	videoStream  chan rtp.Packet
	done         chan struct{}
}

// GetWeb returns web frontend
func (o *Server) GetWeb(w http.ResponseWriter, r *http.Request) {
	tmpl, err := template.ParseFiles(indexPage)
	if err != nil {
		log.Fatal(err)
	}

	tmpl.Execute(w, nil)
}

func NewClient(c *websocket.Conn, clientID string, serverEvents chan cloudgame.WSPacket) *Client {
	return &Client{
		conn:         c,
		clientID:     clientID,
		serverEvents: serverEvents,
		videoStream:  make(chan rtp.Packet, 1),
		done:         make(chan struct{}),
	}
}

func NewServer() *Server {
	server := &Server{
		clients: map[string]*Client{},
		events:  make(chan cloudgame.WSPacket, 1),
	}

	r := mux.NewRouter()
	r.HandleFunc("/ws", server.WS)
	r.PathPrefix("/static/").Handler(http.StripPrefix("/static/", http.FileServer(http.Dir("./web"))))
	r.HandleFunc("/signal", server.Signalling)

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

	// Launch Game VM
	cfg, err := readConfig(configFilePath)
	if err != nil {
		panic(err)
	}

	fmt.Println(cfg)
	server.cgame = cloudgame.NewCloudGameClient(cfg)

	return server
}

func (o *Server) Handle() {
	// Fanin input channel
	go func() {
		for e := range o.events {
			log.Println("event", e)
			o.cgame.SendInput(e)
		}
	}()

	// Fanout output channel
	go func() {
		for p := range o.cgame.VideoStream() {
			for _, client := range o.clients {
				client.videoStream <- p
			}
		}
	}()
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

	// Generate clientID for browserClient
	for {
		clientID = uuid.Must(uuid.NewV4()).String()
		// check duplicate
		if _, ok := o.clients[clientID]; !ok {
			break
		}
	}

	// Create browserClient instance
	o.clients[clientID] = NewClient(c, clientID, o.events)
	// Run browser listener first (to capture ping)
	go func(client *Client) {
		client.Listen()
		delete(o.clients, client.clientID)
	}(o.clients[clientID])
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

func (c *Client) Send(packet cloudgame.WSPacket) {
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

	log.Println("Client listening")
	for {
		_, rawMsg, err := c.conn.ReadMessage()
		fmt.Println("received", rawMsg)
		if err != nil {
			log.Println("[!] read:", err)
			// TODO: Check explicit disconnect error to break
			break
		}
		wspacket := cloudgame.WSPacket{}
		err = json.Unmarshal(rawMsg, &wspacket)

		fmt.Println("send chan", wspacket)
		if err != nil {
			log.Println("error decoding", err)
			continue
		}
		c.serverEvents <- wspacket
	}
}

func readConfig(path string) (cloudgame.Config, error) {
	cfgyml, err := ioutil.ReadFile(path)
	if err != nil {
		return cloudgame.Config{}, err
	}

	cfg := cloudgame.Config{}
	err = yaml.Unmarshal(cfgyml, &cfg)
	return cfg, err
}

func main() {
	// HTTP server
	// TODO: Make the communication over websocket
	http.Handle("/assets/", http.StripPrefix("/assets", http.FileServer(http.Dir("./assets"))))

	server := NewServer()
	server.Handle()
	err := server.ListenAndServe()
	if err != nil {
		log.Fatal(err)
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

	log.Println("SSRC ", ssrc, "payload", webrtc.DefaultPayloadTypeVP8, payloadType)
	// Create a video track, using the same SSRC as the incoming RTP Pack)
	videoTrack, err := conn.NewTrack(payloadType, ssrc, "video", "pion")
	if err != nil {
		panic(err)
	}
	if _, err = conn.AddTrack(videoTrack); err != nil {
		panic(err)
	}
	log.Println("video track", videoTrack)

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

// Signalling is to setup new webRTC connection
// TODO: Change to Socket
func (o *Server) Signalling(w http.ResponseWriter, r *http.Request) {
	log.Println("Signalling")
	RTCConn, err := webrtc.NewPeerConnection(webrtcconfig)
	if err != nil {
		log.Println("error ", err)
	}

	bodyBytes, _ := ioutil.ReadAll(r.Body)
	offerString := string(bodyBytes)

	offer := webrtc.SessionDescription{}
	Decode(offerString, &offer)

	err = RTCConn.SetRemoteDescription(offer)
	if err != nil {
		log.Println("Set remote description from peer failed", err)
		return
	}

	log.Println("Get SSRC", o.cgame.GetSSRC())
	videoTrack := streamRTP(RTCConn, offer, o.cgame.GetSSRC())

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

	// Updatge clientID from connection
	client := o.clients[clientID]

	// Listen from video stream
	go func() {
		for packet := range client.videoStream {
			if writeErr := videoTrack.WriteRTP(&packet); writeErr != nil {
				panic(writeErr)
			}
		}
	}()
}
