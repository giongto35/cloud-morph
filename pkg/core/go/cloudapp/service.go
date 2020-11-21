package cloudapp

import (
	"encoding/base64"
	"encoding/json"
	"log"
	"time"

	"github.com/giongto35/cloud-morph/pkg/addon/textchat"
	"github.com/giongto35/cloud-morph/pkg/common/config"
	"github.com/giongto35/cloud-morph/pkg/core/go/cloudapp/webrtc"
	"github.com/gorilla/websocket"

	"github.com/pion/rtp"
)

const (
	// CollaborativeMode Multiple users share the same app session
	CollaborativeMode = "collaborative"
	// OnDemandMode Multiple users runs on a new available machine
	OnDemandMode = "ondemand"
)

var appEventTypes []string = []string{"OFFER", "ANSWER", "MOUSEDOWN", "MOUSEUP", "MOUSEMOVE", "KEYDOWN", "KEYUP"}

var webrtcconfig = webrtc.Configuration{ICEServers: []webrtc.ICEServer{{URLs: []string{"stun:stun.l.google.com:19302"}}}}
var isStarted bool

type Service struct {
	clients        map[string]*Client
	appModeHandler *appModeHandler
	ccApp          CloudAppClient
	config         config.Config
	chat           *textchat.TextChat
	// communicate with client
	serverEvents chan cws.Packet
	// communicate with cloud app
	appEvents chan cws.Packet
}

type Client struct {
	clientID     string
	ws           *cws.Client
	rtcConn      *webrtc.PeerConnection
	videoStream  chan rtp.Packet
	videoTrack   *webrtc.Track
	serverEvents chan cws.Packet
	WSEvents     chan cws.Packet
	done         chan struct{}
	// TODO: Get rid of ssrc
	ssrc uint32
}

type AppHost struct {
	// Host string `json:"host"`
	Addr    string `json:"addr"`
	AppName string `json:"app_name"`
}

type instance struct {
	addr string
}

type appModeHandler struct {
	appMode            string
	availableInstances []instance
}

func NewAppMode(appMode string) *appModeHandler {
	return &appModeHandler{
		appMode: appMode,
	}
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

func (s *Service) AddClient(clientID string, conn *websocket.Conn) *Client {
	client := NewServiceClient(clientID, conn, s.ccApp.GetSSRC(), s.serverEvents, make(chan cws.Packet, 1))
	s.clients[clientID] = client
	go client.WebsocketListen()
	go client.StreamListen()
	return client
}

func (s *Service) RemoveClient(clientID string) {
	delete(s.clients, clientID)
}

func NewServiceClient(clientID string, conn *websocket.Conn, ssrc uint32, serverEvents chan cws.Packet, wsEvents chan cws.Packet) *Client {
	return &Client{
		clientID:     clientID,
		conn:         conn,
		ssrc:         ssrc,
		WSEvents:     wsEvents,
		serverEvents: serverEvents,
		videoStream:  make(chan rtp.Packet, 1),
		done:         make(chan struct{}),
	}
}

func (c *Client) StreamListen() {
	for packet := range c.videoStream {
		if c.videoTrack == nil {
			continue
		}
		if writeErr := c.videoTrack.WriteRTP(&packet); writeErr != nil {
			log.Println("Error in StreamListen: ", writeErr)
			return
		}
	}
}

func (c *Client) Route() {
	// Listen from video stream
	// WebRTC
	c.ws.Receive("initwebrtc", func(req cws.WSPacket) (resp cws.WSPacket) {
		log.Println("Received a request to createOffer from browser")

		peerconnection := webrtc.NewWebRTC()
		var initPacket struct {
			IsMobile bool `json:"is_mobile"`
		}
		err := json.Unmarshal([]byte(resp.Data), &initPacket)
		if err != nil {
			log.Println("Error: Cannot decode json:", err)
			return cws.EmptyPacket
		}

		localSession, err := peerconnection.StartClient(
			initPacket.IsMobile,
			func(candidate string) {
				// send back candidate string to browser
				c.ws.Send(cws.WSPacket{
					Type:      "candidate",
					Data:      candidate,
					SessionID: req.SessionID,
				}, nil)
			},
		)

		h.sessions[resp.SessionID] = session
		log.Println("Start peerconnection", resp.SessionID)

		if err != nil {
			log.Println("Error: Cannot create new webrtc session", err)
			return cws.EmptyPacket
		}

		return cws.WSPacket{
			Type: "offer",
			Data: localSession,
		}
	})
	for _, event := range appEventTypes {
		c.ws.Receive(event, func(req cws.WSPacket) (resp cws.WSPacket) {
			c.serverEvents <- Convert(wspacket)
		})
	}
}

func (c *Client) Close() {
	if c.rtcConn != nil {
		c.rtcConn.Close()
		c.rtcConn = nil
	}
}

// NewCloudService returns a Cloud Service
func NewCloudService(cfg config.Config) *Service {
	appEvents := make(chan cws.Packet, 1)
	s := &Service{
		clients:        map[string]*Client{},
		appEvents:      appEvents,
		serverEvents:   make(chan cws.Packet, 10),
		appModeHandler: NewAppMode(cfg.AppMode),
		ccApp:          NewCloudAppClient(cfg, appEvents),
		config:         cfg,
	}

	return s
}

func (s *Service) VideoStream() chan rtp.Packet {
	return s.ccApp.VideoStream()
}

func (s *Service) SendInput(packet cws.Packet) {
	s.ccApp.SendInput(packet)
}

func (s *Service) GetSSRC() uint32 {
	return s.ccApp.GetSSRC()
}

func (s *Service) Handle() {
	go func() {
		for p := range s.ccApp.VideoStream() {
			for _, client := range s.clients {
				client.videoStream <- p
			}
		}
	}()

	go func() {
		for e := range s.serverEvents {
			s.appEvents <- e
		}
	}()

	s.ccApp.Handle()
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

	// Create a video track, using the same SSRC as the incoming RTP Pack)
	videoTrack, err := conn.NewTrack(webrtc.DefaultPayloadTypeVP8, ssrc, "video", "pion")
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
