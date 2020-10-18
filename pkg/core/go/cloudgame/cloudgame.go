// cloudgame package is an individual cloud application
package cloudgame

import (
	"bytes"
	"encoding/json"
	"fmt"
	"log"
	"net"
	"os/exec"
	"syscall"
	"time"

	"github.com/giongto35/cloud-morph/pkg/common/config"
	"github.com/giongto35/cloud-morph/pkg/common/ws"
	"github.com/pion/rtp"
	"github.com/pion/webrtc/v2"
)

// type WSPacket struct {
// 	PType string `json:"type"`
// 	// TODO: Make Data generic: map[string]interface{} for more usecases
// 	Data string `json:"data"`
// }

type InputEvent struct {
	inputType    bool
	inputPayload []byte
}

type CloudGameClient interface {
	VideoStream() chan rtp.Packet
	SendInput(ws.Packet)
	Handle()
	// TODO: Remove it
	GetSSRC() uint32
}

type ccImpl struct {
	isReady     bool
	listener    *net.UDPConn
	videoStream chan rtp.Packet
	gameEvents  chan ws.Packet
	wineConn    *net.TCPConn
	ssrc        uint32
	payloadType uint8
}

const startRTPPort = 5004
const eventKeyDown = "KEYDOWN"
const eventKeyUp = "KEYUP"
const eventMouseMove = "MOUSEMOVE"
const eventMouseDown = "MOUSEDOWN"
const eventMouseUp = "MOUSEUP"

var cuRTPPort = startRTPPort

// NewCloudGameClient returns new cloudgame client
func NewCloudGameClient(cfg config.Config, gameEvents chan ws.Packet) *ccImpl {
	c := &ccImpl{
		videoStream: make(chan rtp.Packet, 1),
		gameEvents:  gameEvents,
	}

	la, err := net.ResolveTCPAddr("tcp4", ":9090")
	if err != nil {
		panic(err)
	}
	log.Println("listening wine at port 9090")
	ln, err := net.ListenTCP("tcp", la)
	if err != nil {
		panic(err)
	}

	c.launchGameVM(cuRTPPort, cfg.Path, cfg.AppFile, cfg.WindowTitle, cfg.HWKey)
	log.Println("Launched application VM")

	// Read video stream from encoded video stream produced by FFMPEG
	listener, listenerssrc := c.newLocalStreamListener(cuRTPPort)
	c.listener = listener
	c.ssrc = listenerssrc

	c.listenVideoStream()
	log.Println("Launched Video stream listener")

	// Maintain input stream from server to Virtual Machine over websocket
	// Why Websocket: because normal IPC cannot communicate cross OS.
	go func() {
		for {
			// Polling Wine socket connection (input stream)
			conn, err := ln.AcceptTCP()
			if err != nil {
				// handle error
			}
			conn.SetKeepAlive(true)
			conn.SetKeepAlivePeriod(10 * time.Second)
			c.wineConn = conn
			// Successfully obtain input stream
			log.Println("Server is successfully lauched!")
			log.Println("Listening at :8080")
			c.isReady = true
			go c.healthCheckVM()
		}
	}()

	return c
}

func Convert(packet ws.Packet) ws.Packet {
	return ws.Packet{
		PType: packet.PType,
		Data:  packet.Data,
	}
}

func (c *ccImpl) GetSSRC() uint32 {
	return c.ssrc
}

// done to forcefully stop all processes
func (c *ccImpl) launchGameVM(rtpPort int, appPath string, appFile string, windowTitle string, hwKey bool) chan struct{} {
	var cmd *exec.Cmd
	var streamCmd *exec.Cmd

	var out bytes.Buffer
	var stderr bytes.Buffer
	var params []string

	log.Println("execing run-client.sh")
	// cmd = exec.Command("./run-wine-nodocker.sh", appPath, appFile, windowTitle, hwKey)
	params = []string{appPath, appFile, windowTitle}
	if hwKey {
		params = append(params, "game")
	}
	cmd = exec.Command("./run-wine.sh", params...)

	cmd.Stdout = &out
	cmd.Stderr = &stderr
	err := cmd.Run()
	if err != nil {
		panic(err)
	}
	log.Println("execed run-client.sh")

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

// healthCheckVM to maintain connection
func (c *ccImpl) healthCheckVM() {
	for {
		c.wineConn.Write([]byte{0})
		time.Sleep(2 * time.Second)
	}
}

func (c *ccImpl) Handle() {
	for event := range c.gameEvents {
		c.SendInput(event)
	}
}

// newLocalStreamListener returns RTP: listener and SSRC of that listener
func (c *ccImpl) newLocalStreamListener(rtpPort int) (*net.UDPConn, uint32) {
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

func (c *ccImpl) VideoStream() chan rtp.Packet {
	return c.videoStream
}

// Listen to videostream, output to videoStream channel
func (c *ccImpl) listenVideoStream() {
	// Broadcast video stream
	go func() {
		defer func() {
			c.listener.Close()
			log.Println("Closing game VM")
			// close(gameVMDone)
		}()

		// Read RTP packets forever and send them to the WebRTC Client
		for {
			inboundRTPPacket := make([]byte, 4096) // UDP MTU
			n, _, err := c.listener.ReadFrom(inboundRTPPacket)
			if err != nil {
				log.Printf("error during read: %s", err)
				continue
			}

			packet := rtp.Packet{}
			if err := packet.Unmarshal(inboundRTPPacket[:n]); err != nil {
				log.Printf("error during unmarshalling a packet: %s", err)
				continue
			}
			packet.Header.PayloadType = webrtc.DefaultPayloadTypeVP8

			c.videoStream <- packet
		}
	}()

}

func (c *ccImpl) SendInput(packet ws.Packet) {
	switch packet.PType {
	case eventKeyUp:
		c.simulateKey(packet.Data, 0)
	case eventKeyDown:
		c.simulateKey(packet.Data, 1)
	case eventMouseMove:
		c.simulateMouseEvent(packet.Data, 0)
	case eventMouseDown:
		c.simulateMouseEvent(packet.Data, 1)
	case eventMouseUp:
		c.simulateMouseEvent(packet.Data, 2)
	}
}

func (c *ccImpl) simulateKey(jsonPayload string, keyState byte) {
	if !c.isReady {
		return
	}

	log.Println("KeyDown event", jsonPayload)
	type keydownPayload struct {
		KeyCode int `json:keycode`
	}
	p := &keydownPayload{}
	json.Unmarshal([]byte(jsonPayload), &p)

	vmKeyMsg := fmt.Sprintf("K%d,%b|", p.KeyCode, keyState)
	b, err := c.wineConn.Write([]byte(vmKeyMsg))
	log.Printf("%+v\n", c.wineConn)
	log.Println("Sended key: ", b, err)
}

// simulateMouseEvent handles mouse down event and send it to Virtual Machine over TCP port
func (c *ccImpl) simulateMouseEvent(jsonPayload string, mouseState int) {
	if !c.isReady {
		return
	}

	type mousePayload struct {
		IsLeft byte    `json:isLeft`
		X      float32 `json:x`
		Y      float32 `json:y`
		Width  float32 `json:width`
		Height float32 `json:height`
	}
	p := &mousePayload{}
	json.Unmarshal([]byte(jsonPayload), &p)

	// Mouse is in format of comma separated "12.4,52.3"
	vmMouseMsg := fmt.Sprintf("M%d,%d,%f,%f,%f,%f|", p.IsLeft, mouseState, p.X, p.Y, p.Width, p.Height)
	_, err := c.wineConn.Write([]byte(vmMouseMsg))
	if err != nil {
		fmt.Println("Err: ", err)
	}
}
