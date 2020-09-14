package common

// WSPacket models generic websocket packet
type WSPacket struct {
	PType string `json:"type"`
	// TODO: Make Data generic: map[string]interface{} for more usecases
	Data string `json:"data"`
}
