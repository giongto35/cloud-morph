package cloudgame

import (
	"bytes"
	"encoding/base64"
	"encoding/json"
	"log"
	"net/http"
	"time"

	"github.com/giongto35/cloud-morph/pkg/addon/textchat"

	"github.com/giongto35/cloud-morph/pkg/common/config"
	"github.com/giongto35/cloud-morph/pkg/common/ws"
	"github.com/gorilla/websocket"
	"github.com/pion/webrtc/v2"

	"github.com/pion/rtp"
)

const (
	// CollaborativeMode Multiple users share the same app session
	CollaborativeMode = "collaborative"
	// OnDemandMode Multiple users runs on a new available machine
	OnDemandMode = "ondemand"
)

var webrtcconfig = webrtc.Configuration{ICEServers: []webrtc.ICEServer{{URLs: []string{"stun:stun.l.google.com:19302"}}}}
var isStarted bool

type Service struct {
	clients          map[string]*Client
	appModeHandler   *appModeHandler
	discoveryHandler *discoveryHandler
	ccApp            CloudGameClient
	config           config.Config
	chat             *textchat.TextChat
	// communicate with client
	serverEvents chan ws.Packet
	// communicate with cloud app
	appEvents chan ws.Packet
}

type Client struct {
	clientID     string
	conn         *websocket.Conn
	rtcConn      *webrtc.PeerConnection
	videoStream  chan rtp.Packet
	videoTrack   *webrtc.Track
	serverEvents chan ws.Packet
	WSEvents     chan ws.Packet
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

type discoveryHandler struct {
	httpClient    *http.Client
	discoveryHost string
	curAppHosts   []AppHost
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
	client := NewServiceClient(clientID, conn, s.ccApp.GetSSRC(), s.serverEvents, make(chan ws.Packet, 1))
	s.clients[clientID] = client
	go client.WebsocketListen()
	go client.StreamListen()
	return client
}

func NewServiceClient(clientID string, conn *websocket.Conn, ssrc uint32, serverEvents chan ws.Packet, wsEvents chan ws.Packet) *Client {
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
			log.Println(writeErr)
			return
		}
	}
}

func (c *Client) WebsocketListen() {
	// Listen from video stream
	for wspacket := range c.WSEvents {
		if wspacket.PType == "OFFER" {
			c.signal(wspacket.Data)
			continue
		}

		c.serverEvents <- Convert(wspacket)
	}
}

func (c *Client) Send(packet ws.Packet) {
	data, err := json.Marshal(packet)
	if err != nil {
		return
	}

	c.conn.WriteMessage(websocket.TextMessage, data)
}

func (c *Client) Close() {
	if c.rtcConn != nil {
		c.rtcConn.Close()
		c.rtcConn = nil
	}
}

func (c *Client) signal(offerString string) {
	log.Println("Signalling")
	RTCConn, err := webrtc.NewPeerConnection(webrtcconfig)
	if err != nil {
		log.Println("error ", err)
	}
	c.rtcConn = RTCConn

	offer := webrtc.SessionDescription{}
	Decode(offerString, &offer)

	err = RTCConn.SetRemoteDescription(offer)
	if err != nil {
		log.Println("Set remote description from peer failed", err)
		return
	}

	log.Println("Get SSRC", c.ssrc)
	videoTrack := streamRTP(RTCConn, offer, c.ssrc)

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
	log.Println("Sending answer", answer)
	c.Send(ws.Packet{
		PType: "ANSWER",
		Data:  Encode(answer),
	})
	c.videoTrack = videoTrack
}

func (d *discoveryHandler) GetAppHosts() []AppHost {
	type GetAppHostsResponse struct {
		AppHosts []AppHost `json:"apps"`
	}
	var resp GetAppHostsResponse

	rawResp, err := d.httpClient.Get(d.discoveryHost + "/get-apps")
	if err != nil {
		log.Println(err)
		return []AppHost{}
	}

	defer rawResp.Body.Close()
	json.NewDecoder(rawResp.Body).Decode(&resp)

	return resp.AppHosts
}

func (d *discoveryHandler) isNeedAppListUpdate(appHosts []AppHost) bool {
	if len(appHosts) != len(d.curAppHosts) {
		return true
	}

	for i, app := range appHosts {
		if app != d.curAppHosts[i] {
			return true
		}
	}

	return false
}

func (d *discoveryHandler) AppListUpdate() chan []AppHost {
	updatedApps := make(chan []AppHost, 1)
	go func() {
		// TODO: Change to subscription based
		for range time.Tick(5 * time.Second) {
			appHosts := d.GetAppHosts()
			if d.isNeedAppListUpdate(appHosts) {
				log.Println("Update AppHosts: ", appHosts)
				updatedApps <- appHosts
				d.curAppHosts = make([]AppHost, len(appHosts))
				copy(d.curAppHosts, appHosts)
			}
		}
	}()

	return updatedApps
}

func (d *discoveryHandler) Register(addr string, appName string) error {
	type RegisterAppRequest struct {
		Addr    string `json:"addr"`
		AppName string `json:"app_name"`
	}
	req := RegisterAppRequest{
		Addr:    addr,
		AppName: appName,
	}

	reqBytes, err := json.Marshal(req)
	if err != nil {
		return nil
	}

	_, err = d.httpClient.Post(d.discoveryHost+"/register", "application/json", bytes.NewBuffer(reqBytes))
	if err != nil {
		return nil
	}

	return err
}

func NewDiscovery(discoveryHost string) *discoveryHandler {
	return &discoveryHandler{
		httpClient: &http.Client{
			Timeout: time.Second * 10,
		},
		discoveryHost: discoveryHost,
	}
}

func (s *Service) GetAppHosts() []AppHost {
	return s.discoveryHandler.GetAppHosts()
}

func (s *Service) Register(addr string) error {
	return s.discoveryHandler.Register(addr, s.config.AppName)
}

func (s *Service) AppListUpdate() chan []AppHost {
	return s.discoveryHandler.AppListUpdate()
}

// func NewCloudGameClient(cfg Config, gameEvents chan WSPacket) *ccImpl {
func NewCloudService(cfg config.Config) *Service {
	appEvents := make(chan ws.Packet, 1)
	s := &Service{
		clients:          map[string]*Client{},
		appEvents:        appEvents,
		serverEvents:     make(chan ws.Packet, 10),
		appModeHandler:   NewAppMode(cfg.AppMode),
		discoveryHandler: NewDiscovery(cfg.DiscoveryHost),
		ccApp:            NewCloudGameClient(cfg, appEvents),
		config:           cfg,
	}

	return s
}

func (s *Service) VideoStream() chan rtp.Packet {
	return s.ccApp.VideoStream()
}

func (s *Service) SendInput(packet ws.Packet) {
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
