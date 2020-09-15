package ws

import (
	"encoding/json"

	"github.com/gorilla/websocket"
)

// Packet models generic websocket packet
type Packet struct {
	PType string `json:"type"`
	// TODO: Make Data generic: map[string]interface{} for more usecases
	Data string `json:"data"`
}

type Client struct {
	conn *websocket.Conn
}

func NewClient(conn *websocket.Conn) *Client {
	return &Client{
		conn: conn,
	}
}

// Send send websocket message
func (c *Client) Send(packet Packet) error {
	data, err := json.Marshal(packet)
	if err != nil {
		return err
	}

	// TODO: change to byte
	c.conn.WriteMessage(websocket.TextMessage, data)
	return nil
}
