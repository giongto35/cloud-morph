package textchat

import (
	"encoding/json"
	"fmt"
	"log"

	"github.com/giongto35/cloud-morph/pkg/common/ws"
	"github.com/gorilla/websocket"
)

type ChatMessage struct {
	User    string `json:"user"`
	Message string `json:"message"`
}

type TextChat struct {
	chatMsgs    []ChatMessage
	broadcastCh chan ChatMessage
	clients     map[string]*chatClient
}

type chatClient struct {
	clientID    string
	conn        *websocket.Conn
	broadcastCh chan ChatMessage
	WSEvents    chan ws.Packet
}

func NewTextChat() *TextChat {
	return &TextChat{
		chatMsgs:    []ChatMessage{},
		clients:     map[string]*chatClient{},
		broadcastCh: make(chan ChatMessage, 1),
	}
}

func Convert(packet ws.Packet) ChatMessage {
	chatMsg := ChatMessage{}
	err := json.Unmarshal([]byte(packet.Data), &chatMsg)
	if err != nil {
		panic(err)
	}

	return chatMsg
}

func (t *TextChat) broadcast(e ChatMessage) error {
	data, err := json.Marshal(ChatMessage{
		User:    e.User,
		Message: e.Message,
	})
	if err != nil {
		return err
	}
	for _, client := range t.clients {
		client.Send(ws.Packet{
			PType: "CHAT",
			Data:  string(data),
		})
	}
	t.chatMsgs = append(t.chatMsgs, e)

	return nil
}

func (t *TextChat) Handle() {
	for e := range t.broadcastCh {
		t.broadcast(e)
	}
}

func NewChatClient(clientID string, conn *websocket.Conn, broadcastCh chan ChatMessage, wsEvents chan ws.Packet) *chatClient {
	return &chatClient{
		broadcastCh: broadcastCh,
		clientID:    clientID,
		conn:        conn,
		WSEvents:    wsEvents,
	}
}

func (c *chatClient) Listen() {
	// defer func() {
	// 	close(c.done)
	// }()

	log.Println("Client listening")
	for wspacket := range c.WSEvents {
		// data := Convert(wspacket)
		// data, err := json.Marshal(Convert(wspacket))
		fmt.Println("wspacket", wspacket)
		c.broadcastCh <- Convert(wspacket)
		// c.Send(ws.Packet{
		// 	PType: "CHAT",
		// 	Data:  string(data),
		// })
	}
}

func (t *TextChat) AddClient(clientID string, conn *websocket.Conn) *chatClient {
	client := NewChatClient(clientID, conn, t.broadcastCh, make(chan ws.Packet, 1))
	go client.Listen()
	t.clients[clientID] = client
	return client
}

func (t *TextChat) SendChatHistory(clientID string) {
	client, ok := t.clients[clientID]
	if !ok {
		fmt.Println("Client not found", clientID)
		return
	}

	for _, msg := range t.chatMsgs {
		data, err := json.Marshal(ChatMessage{
			User:    msg.User,
			Message: msg.Message,
		})
		if err != nil {
			log.Println("Failed to send ", msg)
			continue
		}
		fmt.Println("chat history ", data)

		client.Send(ws.Packet{
			PType: "CHAT",
			Data:  string(data),
		})
	}
}

func (c *chatClient) Send(packet ws.Packet) error {
	data, err := json.Marshal(packet)
	if err != nil {
		return err
	}

	c.conn.WriteMessage(websocket.TextMessage, data)
	return nil
}

func (c *chatClient) Close() {
}
