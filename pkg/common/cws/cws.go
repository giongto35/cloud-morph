package cws

import (
	"encoding/json"
	"log"
	"sync"
	"time"

	"github.com/gofrs/uuid"
	"github.com/gorilla/websocket"
)

type Client struct {
	id string

	conn *websocket.Conn

	sendLock sync.Mutex
	// sendCallback is callback based on packetID
	sendCallback     map[string]func(req WSPacket)
	sendCallbackLock sync.Mutex
	// recvCallback is callback when receive based on ID of the packet
	recvCallback map[string]func(req WSPacket)

	Done chan struct{}
}

// WSPacket represents a websocket packet
type WSPacket struct {
	Type string `json:"type"`
	// TODO: Make Data generic: map[string]interface{} for more usecases
	Data string `json:"data"`

	PacketID string `json:"packet_id"`
	// Globally ID of a browser session
	SessionID string `json:"session_id"`
}

// EmptyPacket represents an empty packet
var EmptyPacket = WSPacket{}

// NewClient returns a websocket client
func NewClient(conn *websocket.Conn) *Client {
	id := uuid.Must(uuid.NewV4()).String()
	sendCallback := map[string]func(WSPacket){}
	recvCallback := map[string]func(WSPacket){}

	return &Client{
		id:   id,
		conn: conn,

		sendCallback: sendCallback,
		recvCallback: recvCallback,

		Done: make(chan struct{}),
	}
}

// Send sends a packet and trigger callback when the packet comes back
func (c *Client) Send(request WSPacket, callback func(response WSPacket)) {
	request.PacketID = uuid.Must(uuid.NewV4()).String()
	data, err := json.Marshal(request)
	if err != nil {
		return
	}

	// Wrap callback with sessionID and packetID
	if callback != nil {
		wrapperCallback := func(resp WSPacket) {
			defer func() {
				if err := recover(); err != nil {
					log.Println("Recovered from err in client callback ", err)
				}
			}()

			resp.PacketID = request.PacketID
			resp.SessionID = request.SessionID
			callback(resp)
		}
		c.sendCallbackLock.Lock()
		c.sendCallback[request.PacketID] = wrapperCallback
		c.sendCallbackLock.Unlock()
	}

	c.sendLock.Lock()
	c.conn.SetWriteDeadline(time.Now().Add(20 * time.Second))
	c.conn.WriteMessage(websocket.TextMessage, data)
	c.sendLock.Unlock()
}

// Receive receive and response
func (c *Client) Receive(id string, f func(request WSPacket) (response WSPacket)) {
	c.recvCallback[id] = func(request WSPacket) {
		// defer func() {
		// 	if err := recover(); err != nil {
		// 		log.Println("Recovered from err ", err)
		// 		log.Println(debug.Stack())
		// 	}
		// }()

		resp := f(request)
		// Add Meta data
		resp.PacketID = request.PacketID
		resp.SessionID = request.SessionID

		// Skip request if it is EmptyPacket
		if resp == EmptyPacket {
			return
		}
		respText, err := json.Marshal(resp)
		if err != nil {
			log.Println("[!] json marshal error:", err)
		}
		c.sendLock.Lock()
		c.conn.SetWriteDeadline(time.Now().Add(20 * time.Second))
		c.conn.WriteMessage(websocket.TextMessage, respText)
		c.sendLock.Unlock()
	}
}

// SyncSend sends a packet and wait for callback till the packet comes back
func (c *Client) SyncSend(request WSPacket) (response WSPacket) {
	res := make(chan WSPacket)
	f := func(resp WSPacket) {
		res <- resp
	}
	c.Send(request, f)
	return <-res
}

// SendAwait sends some packet while waiting for a tile-limited response
//func (c *Client) SendAwait(packet WSPacket) WSPacket {
//	ch := make(chan WSPacket)
//	defer close(ch)
//	c.Send(packet, func(response WSPacket) { ch <- response })
//
//	for {
//		select {
//		case packet := <-ch:
//			return packet
//		case <-time.After(config.WsIpcTimeout):
//			log.Printf("Packet receive timeout!")
//			return EmptyPacket
//		}
//	}
//}

// Heartbeat maintains connection to server
func (c *Client) Heartbeat() {
	// send heartbeat every 1s
	timer := time.Tick(time.Second)

	for range timer {
		select {
		case <-c.Done:
			log.Println("Close heartbeat")
			return
		default:
		}
		c.Send(WSPacket{Type: "heartbeat"}, nil)
	}
}

// Listen start a client
func (c *Client) Listen() {
	for {
		c.conn.SetReadDeadline(time.Now().Add(20 * time.Second))
		_, rawMsg, err := c.conn.ReadMessage()
		if err != nil {
			log.Println("[!] read:", err)
			// TODO: Check explicit disconnect error to break
			close(c.Done)
			break
		}
		wspacket := WSPacket{}
		err = json.Unmarshal(rawMsg, &wspacket)

		if err != nil {
			log.Println("Warn: error decoding", rawMsg)
			continue
		}

		// Check if some async send is waiting for the response based on packetID
		// TODO: Change to read lock.
		//c.sendCallbackLock.Lock()
		callback, ok := c.sendCallback[wspacket.PacketID]
		//c.sendCallbackLock.Unlock()
		if ok {
			go callback(wspacket)
			//c.sendCallbackLock.Lock()
			delete(c.sendCallback, wspacket.PacketID)
			//c.sendCallbackLock.Unlock()
			// Skip receiveCallback to avoid duplication
			continue
		}
		// Check if some receiver with the ID is registered
		if callback, ok := c.recvCallback[wspacket.Type]; ok {
			go callback(wspacket)
		}
	}
}

func (c *Client) GetID() string {
	return c.id
}

func (c *Client) Close() {
	if c == nil || c.conn == nil {
		return
	}
	c.conn.Close()
}
