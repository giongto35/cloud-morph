package textchat

import (
	"encoding/json"
	"fmt"
	"log"

	"github.com/giongto35/cloud-morph/pkg/common/cws"
)

type ChatMessage struct {
	User    string `json:"user"`
	Message string `json:"message"`
}

// TextChat is the service to handle all chat over websocket
type TextChat struct {
	chatMsgs    []ChatMessage
	broadcastCh chan ChatMessage
	clients     map[string]*chatClient
}

type chatClient struct {
	clientID    string
	ws          *cws.Client
	broadcastCh chan ChatMessage
	WSEvents    chan cws.WSPacket
}

// NewTextChat spawns a new text chat
func NewTextChat() *TextChat {
	return &TextChat{
		chatMsgs:    []ChatMessage{},
		clients:     map[string]*chatClient{},
		broadcastCh: make(chan ChatMessage, 1),
	}
}

// broadcast broadcasts a message to all clients
func (t *TextChat) broadcast(e ChatMessage) error {
	data, err := json.Marshal(ChatMessage{
		User:    e.User,
		Message: e.Message,
	})
	if err != nil {
		return err
	}
	for _, client := range t.clients {
		client.ws.Send(cws.WSPacket{
			Type: "CHAT",
			Data: string(data),
		}, nil)
	}
	t.chatMsgs = append(t.chatMsgs, e)

	return nil
}

// Handle is main handler for TextChat
func (t *TextChat) Handle() {
	for e := range t.broadcastCh {
		t.broadcast(e)
	}
}

// NewChatClient returns a new chat client
func NewChatClient(clientID string, ws *cws.Client, broadcastCh chan ChatMessage, wsEvents chan cws.WSPacket) *chatClient {
	return &chatClient{
		broadcastCh: broadcastCh,
		clientID:    clientID,
		ws:          ws,
		WSEvents:    wsEvents,
	}
}

// AddClient add a new chat client to TextChat
func (t *TextChat) AddClient(clientID string, ws *cws.Client) *chatClient {
	client := NewChatClient(clientID, ws, t.broadcastCh, make(chan cws.WSPacket, 1))
	t.clients[clientID] = client
	return client
}

// SendChatHistory sends chat history to all clients
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

		client.ws.Send(cws.WSPacket{
			Type: "CHAT",
			Data: string(data),
		}, nil)
	}
}

func convert(packet cws.WSPacket) ChatMessage {
	chatMsg := ChatMessage{}
	err := json.Unmarshal([]byte(packet.Data), &chatMsg)
	if err != nil {
		panic(err)
	}

	return chatMsg
}

func (c *chatClient) Route() {
	c.ws.Receive("CHAT", func(request cws.WSPacket) (response cws.WSPacket) {
		c.broadcastCh <- convert(request)
		return cws.EmptyPacket
	})
}

func (c *chatClient) Close() {
}
