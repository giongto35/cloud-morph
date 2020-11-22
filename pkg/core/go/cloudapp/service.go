package cloudapp

import (
	"encoding/base64"
	"encoding/json"
	"log"
	"time"

	"github.com/giongto35/cloud-morph/pkg/addon/textchat"
	"github.com/giongto35/cloud-morph/pkg/common/config"
	"github.com/giongto35/cloud-morph/pkg/common/cws"
	"github.com/giongto35/cloud-morph/pkg/core/go/cloudapp/webrtc"

	"github.com/pion/rtp"
)

const (
	// CollaborativeMode Multiple users share the same app session
	CollaborativeMode = "collaborative"
	// OnDemandMode Multiple users runs on a new available machine
	OnDemandMode = "ondemand"
)

var appEventTypes []string = []string{"OFFER", "ANSWER", "MOUSEDOWN", "MOUSEUP", "MOUSEMOVE", "KEYDOWN", "KEYUP"}

// var webrtcconfig = webrtc.Configuration{ICEServers: []webrtc.ICEServer{{URLs: []string{"stun:stun.l.google.com:19302"}}}}
var isStarted bool

type Service struct {
	clients        map[string]*Client
	appModeHandler *appModeHandler
	ccApp          CloudAppClient
	config         config.Config
	chat           *textchat.TextChat
	// communicate with cloud app
	appEvents chan Packet
}

type Client struct {
	clientID    string
	ws          *cws.Client
	rtcConn     *webrtc.WebRTC
	videoStream chan rtp.Packet
	appEvents   chan Packet
	// videoTrack   *webrtc.Track
	done chan struct{}
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

func (s *Service) AddClient(clientID string, ws *cws.Client) *Client {
	client := NewServiceClient(clientID, ws, s.ccApp.GetSSRC(), s.config.StunTurn)
	s.clients[clientID] = client
	return client
}

func (s *Service) RemoveClient(clientID string) {
	delete(s.clients, clientID)
}

func NewServiceClient(clientID string, ws *cws.Client, ssrc uint32, stunturn string) *Client {
	ws.Send(cws.WSPacket{
		Type: "init",
		Data: stunturn,
	}, nil)

	return &Client{
		clientID:    clientID,
		ws:          ws,
		ssrc:        ssrc,
		videoStream: make(chan rtp.Packet, 1),
		done:        make(chan struct{}),
	}
}

func (c *Client) StreamListen() {
	for packet := range c.videoStream {
		// if c.rtcConn.videoTrack == nil {
		// 	continue
		// }
		// if writeErr := c.videoTrack.WriteRTP(&packet); writeErr != nil {
		// 	log.Println("Error in StreamListen: ", writeErr)
		// 	return
		// }
		c.rtcConn.ImageChannel <- packet
	}
}

func (c *Client) Route(ssrc uint32) {
	// Listen from video stream
	// WebRTC
	c.ws.Receive("initwebrtc", func(req cws.WSPacket) (resp cws.WSPacket) {
		log.Println("Received a request to createOffer from browser", req)

		c.rtcConn = webrtc.NewWebRTC()
		var initPacket struct {
			IsMobile bool `json:"is_mobile"`
		}
		err := json.Unmarshal([]byte(req.Data), &initPacket)
		if err != nil {
			log.Println("Error: Cannot decode json:", err)
			return cws.EmptyPacket
		}

		localSession, err := c.rtcConn.StartClient(
			initPacket.IsMobile,
			func(candidate string) {
				// send back candidate string to browser
				c.ws.Send(cws.WSPacket{
					Type:      "candidate",
					Data:      candidate,
					SessionID: req.SessionID,
				}, nil)
			},
			ssrc,
		)

		if err != nil {
			log.Println("Error: Cannot create new webrtc session", err)
			return cws.EmptyPacket
		}

		return cws.WSPacket{
			Type: "offer",
			Data: localSession,
		}
	})

	c.ws.Receive(
		"answer",
		func(resp cws.WSPacket) (req cws.WSPacket) {
			log.Println("Received answer SDP from browser", resp)
			err := c.rtcConn.SetRemoteSDP(resp.Data)
			if err != nil {
				log.Println("Error: Cannot set RemoteSDP of client: " + resp.SessionID)
			}

			go c.StreamListen()
			return cws.EmptyPacket
		},
	)

	c.ws.Receive(
		"candidate",
		func(resp cws.WSPacket) (req cws.WSPacket) {
			log.Println("Received remote Ice Candidate from browser")

			err := c.rtcConn.AddCandidate(resp.Data)
			if err != nil {
				log.Println("Error: Cannot add IceCandidate of client: " + resp.SessionID)
			}

			return cws.EmptyPacket
		},
	)

	for _, event := range appEventTypes {
		c.ws.Receive(event, func(req cws.WSPacket) (resp cws.WSPacket) {
			c.appEvents <- convertWSPacket(req)
			return cws.EmptyPacket
		})
	}
}

func (c *Client) Close() {
	if c.rtcConn != nil {
		// c.rtcConn.Close()
		c.rtcConn = nil
	}
}

// NewCloudService returns a Cloud Service
func NewCloudService(cfg config.Config) *Service {
	appEvents := make(chan Packet, 1)
	s := &Service{
		clients:        map[string]*Client{},
		appEvents:      appEvents,
		appModeHandler: NewAppMode(cfg.AppMode),
		ccApp:          NewCloudAppClient(cfg, appEvents),
		config:         cfg,
	}

	return s
}

func (s *Service) VideoStream() chan rtp.Packet {
	return s.ccApp.VideoStream()
}

func (s *Service) SendInput(packet Packet) {
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
