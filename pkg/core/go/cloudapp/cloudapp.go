package cloudapp

import (
	"bufio"
	"container/ring"
	"context"
	"encoding/json"
	"fmt"
	"log"
	"net"
	"os"
	"os/exec"
	"runtime"
	"strconv"

	"github.com/giongto35/cloud-morph/pkg/common/config"
	"github.com/giongto35/cloud-morph/pkg/common/cws"
	"github.com/giongto35/cloud-morph/pkg/shim"
	"github.com/pion/rtp"
)

type CloudAppClient interface {
	VideoStream() chan *rtp.Packet
	AudioStream() chan *rtp.Packet
	SendInput(Packet)
	Handle()
	// TODO: Remove it
	GetSSRC() uint32
}

type osTypeEnum int

const (
	Linux osTypeEnum = iota
	Mac
	Windows
)

type ccImpl struct {
	videoListener *net.UDPConn
	audioListener *net.UDPConn
	videoStream   chan *rtp.Packet
	audioStream   chan *rtp.Packet
	appEvents     chan Packet
	osType        osTypeEnum
	screenWidth   float32
	screenHeight  float32
	ssrc          uint32
	shim          shim.Server
}

// Packet represents a packet in cloudapp
type Packet struct {
	Type string `json:"type"`
	Data string `json:"data"`
}

const startVideoRTPPort = 5004
const startAudioRTPPort = 4004
const eventKeyDown = "KEYDOWN"
const eventKeyUp = "KEYUP"
const eventMouseMove = "MOUSEMOVE"
const eventMouseDown = "MOUSEDOWN"
const eventMouseUp = "MOUSEUP"

var curVideoRTPPort = startVideoRTPPort
var curAudioRTPPort = startAudioRTPPort

// NewCloudAppClient returns new cloudapp client
func NewCloudAppClient(cfg config.Config, appEvents chan Packet) *ccImpl {
	c := &ccImpl{
		videoStream: make(chan *rtp.Packet, 1),
		audioStream: make(chan *rtp.Packet, 1),
		appEvents:   appEvents,
	}

	switch runtime.GOOS {
	case "windows":
		c.osType = Windows
	default:
		c.osType = Linux
	}

	fmt.Println(cfg)
	c.launchAppVM(curVideoRTPPort, curAudioRTPPort, cfg)
	log.Println("Launched application VM")

	// Read video stream from encoded video stream produced by FFMPEG
	log.Println("Setup Video Listener")
	videoListener, listenerssrc := c.newLocalStreamListener(curVideoRTPPort)
	c.videoListener = videoListener
	c.ssrc = listenerssrc
	if c.osType != Windows {
		// Don't spawn Audio in Windows
		log.Println("Setup Audio Listener")
		audioListener, audiolistenerssrc := c.newLocalStreamListener(curAudioRTPPort)
		c.audioListener = audioListener
		c.ssrc = audiolistenerssrc
	}
	log.Println("Done Listener")

	c.listenVideoStream()
	log.Println("Launched Video stream listener")
	if c.osType != Windows {
		// Don't spawn Audio in Windows
		c.listenAudioStream()
		log.Println("Launched Audio stream listener")
	}

	c.shim = shim.Server{}
	go c.shim.Start(context.Background())

	return c
}

// convertWSPacket returns cloudapp packet from ws packet
func convertWSPacket(packet cws.WSPacket) Packet {
	return Packet{
		Type: packet.Type,
		Data: packet.Data,
	}
}

func (c *ccImpl) GetSSRC() uint32 {
	return c.ssrc
}

func (c *ccImpl) runApp(params []string) {
	log.Println("params: ", params)

	var cmd *exec.Cmd
	if c.osType == Windows {
		params = append([]string{"-ExecutionPolicy", "Bypass", "-F", "run-app.ps1"}, params...)
		log.Println("You are running on Windows", params)
		cmd = exec.Command("powershell", params...)
	} else {
		log.Println("You are running on Linux")
		cmd = exec.Command("./run-wine.sh", params...)
	}

	cmd.Env = os.Environ()
	stdout, err := cmd.StdoutPipe()
	if err != nil {
		log.Fatal(err)
	}
	go func() {
		scanner := bufio.NewScanner(stdout)
		for scanner.Scan() {
			log.Printf(scanner.Text())
		}
	}()
	stderr, err := cmd.StderrPipe()
	if err != nil {
		log.Fatal(err)
	}
	go func() {
		scanner := bufio.NewScanner(stderr)
		for scanner.Scan() {
			log.Printf(scanner.Text())
		}
	}()
	cmd.Start()
	log.Println("Done running script")
	cmd.Wait()
}

// done to forcefully stop all processes
func (c *ccImpl) launchAppVM(curVideoRTPPort int, curAudioRTPPort int, cfg config.Config) chan struct{} {
	var cmd *exec.Cmd
	var params []string

	// Setup wine params and run
	log.Println("execing run-wine.sh")
	// TODO: refactor to key value
	params = []string{cfg.Path, cfg.AppFile, cfg.WindowTitle}
	if cfg.HWKey {
		params = append(params, "game")
	} else {
		params = append(params, "")
	}
	params = append(params, []string{strconv.Itoa(cfg.ScreenWidth), strconv.Itoa(cfg.ScreenHeight)}...)
	if *cfg.IsWindowMode {
		params = append(params, "-w")
	} else {
		params = append(params, "")
	}
	if c.osType == Windows {
		params = append(params, "windows")
	} else {
		params = append(params, "")
	}

	c.runApp(params)
	// update flag
	c.screenWidth = float32(cfg.ScreenWidth)
	c.screenHeight = float32(cfg.ScreenHeight)

	done := make(chan struct{})
	// clean up func
	go func() {
		<-done
		err := cmd.Process.Kill()
		cmd.Process.Kill()
		log.Println("Kill app: ", err)
	}()

	return done
}

func (c *ccImpl) Handle() {
	for event := range c.appEvents {
		c.SendInput(event)
	}
}

// newLocalStreamListener returns RTP: listener and SSRC of that listener
func (c *ccImpl) newLocalStreamListener(rtpPort int) (*net.UDPConn, uint32) {
	// Open a UDP Listener for RTP Packets on port 5004
	listener, err := net.ListenUDP("udp", &net.UDPAddr{IP: net.ParseIP("localhost"), Port: rtpPort})
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

func (c *ccImpl) VideoStream() chan *rtp.Packet {
	return c.videoStream
}

func (c *ccImpl) AudioStream() chan *rtp.Packet {
	return c.audioStream
}

// Listen to videostream, output to videoStream channel
func (c *ccImpl) listenAudioStream() {

	// Broadcast video stream
	go func() {
		defer func() {
			c.audioListener.Close()
			log.Println("Closing app VM")
		}()
		r := ring.New(120)

		n := r.Len()
		for i := 0; i < n; i++ {
			// r.Value = make([]byte, 4096)
			r.Value = make([]byte, 1500)
			r = r.Next()
		}

		// TODO: Create a precreated memory, only pop after finish processing
		// Read RTP packets forever and send them to the WebRTC Client
		for {
			inboundRTPPacket := r.Value.([]byte) // UDP MTU
			r = r.Next()
			n, _, err := c.audioListener.ReadFrom(inboundRTPPacket)
			if err != nil {
				log.Printf("error during read: %s", err)
				continue
			}

			// TODOs: Don't assign packet here
			packet := &rtp.Packet{}
			if err := packet.Unmarshal(inboundRTPPacket[:n]); err != nil {
				log.Printf("error during unmarshalling a packet: %s", err)
				continue
			}

			c.audioStream <- packet
		}
	}()

}

// Listen to videostream, output to videoStream channel
func (c *ccImpl) listenVideoStream() {
	// Broadcast video stream
	go func() {
		defer func() {
			c.videoListener.Close()
			log.Println("Closing app VM")
		}()
		r := ring.New(120)

		n := r.Len()
		for i := 0; i < n; i++ {
			// r.Value = make([]byte, 4096)
			r.Value = make([]byte, 1500)
			r = r.Next()
		}

		// TODO: Create a precreated memory, only pop after finish processing
		// Read RTP packets forever and send them to the WebRTC Client
		for {
			inboundRTPPacket := r.Value.([]byte) // UDP MTU
			r = r.Next()
			n, _, err := c.videoListener.ReadFrom(inboundRTPPacket)
			if err != nil {
				log.Printf("error during read: %s", err)
				continue
			}

			// TODOs: Don't assign packet here
			packet := &rtp.Packet{}
			if err := packet.Unmarshal(inboundRTPPacket[:n]); err != nil {
				log.Printf("error during unmarshalling a packet: %s", err)
				continue
			}

			c.videoStream <- packet
		}
	}()
}

func (c *ccImpl) SendInput(packet Packet) {
	if !c.shim.IsReady() {
		return
	}

	switch packet.Type {
	case eventKeyUp:
		c.simulateKey(packet.Data, shim.KeyEventUp)
	case eventKeyDown:
		c.simulateKey(packet.Data, shim.KeyEventDown)
	case eventMouseMove:
		c.simulateMouseEvent(packet.Data, shim.MouseEventMove)
	case eventMouseDown:
		c.simulateMouseEvent(packet.Data, shim.MouseEventDown)
	case eventMouseUp:
		c.simulateMouseEvent(packet.Data, shim.MouseEventUp)
	}
}

func (c *ccImpl) simulateKey(jsonPayload string, event shim.KeyEvent) {
	log.Println("KeyDown event", jsonPayload)

	p := &shim.KeyPayload{}
	json.Unmarshal([]byte(jsonPayload), &p)

	b, err := c.shim.Write(shim.ToKey(p.KeyCode, event))
	log.Println("Key sent: ", b, err)
}

// simulateMouseEvent handles mouse down event and send it to Virtual Machine over TCP port
func (c *ccImpl) simulateMouseEvent(jsonPayload string, event shim.MouseEvent) {
	p := &shim.MousePayload{}
	json.Unmarshal([]byte(jsonPayload), &p)
	p.X = p.X * c.screenWidth / p.Width
	p.Y = p.Y * c.screenHeight / p.Height

	_, err := c.shim.Write(shim.ToMouse(p.IsLeft, event, p.X, p.Y, p.Width, p.Height))
	if err != nil {
		fmt.Println("Err: ", err)
	}
}
