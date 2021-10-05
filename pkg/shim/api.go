package shim

import (
	"errors"
	"fmt"
	"strconv"
	"strings"
)

type (
	KeyEvent   byte
	MouseEvent int
)

type (
	MousePayload struct {
		IsLeft byte    `json:"isLeft"`
		X      float32 `json:"x"`
		Y      float32 `json:"y"`
		Width  float32 `json:"width"`
		Height float32 `json:"height"`
	}
	KeyPayload struct {
		KeyCode int `json:"keycode"`
	}
)

const (
	KeyEventUp     KeyEvent   = 0
	KeyEventDown   KeyEvent   = 1
	MouseEventMove MouseEvent = 0
	MouseEventDown MouseEvent = 1
	MouseEventUp   MouseEvent = 2
)

// PING is a special packet for
// explicit keepalive/ping procedures.
var PING = []byte{0}

var ErrDeserialize = errors.New("couldn't deserialize")

// ToKey serializes a keypress event.
// The output value should be in the following format:
//   K133,1
// where:
//   K -- event constant prefix
//   133 -- key code
//   1 -- key state: 1 -- pressed, 0 -- released
func ToKey(code int, event KeyEvent) []byte {
	return []byte(fmt.Sprintf("K%d,%b|", code, event))
}

// FromKey extracts data from a serialized keypress value.
// See ToKey for the value format.
func FromKey(data string) (key KeyPayload, event KeyEvent, err error) {
	v := strings.Split(string([]byte(data)[1:]), ",")
	if len(v) < 2 {
		return key, 0, ErrDeserialize
	}
	code_, err := strconv.Atoi(v[0])
	if err != nil {
		return key, 0, err
	}
	event_, err := strconv.Atoi(v[1])
	if err != nil {
		return key, 0, err
	}
	return KeyPayload{KeyCode: code_}, KeyEvent(event_), nil
}

// ToMouse serializes a mouse state.
// The output value should be in the following format:
//   M1,0,429.522430,276.350586,691.000000,801.156250
// where:
//   M -- event constant prefix
//   1 --
//   0 -- mouse state: 0 -- move, 1 -- pressed, 2 -- released
//   429.522430 -- x coordinate of the cursor
//   276.350586 -- y coordinate of the cursor
//   691.000000 -- width of the window
//   801.156250 -- height of the window
func ToMouse(left byte, event MouseEvent, x, y, w, h float32) []byte {
	return []byte(fmt.Sprintf("M%d,%d,%f,%f,%f,%f|", left, event, x, y, w, h))
}

// FromMouse extracts data from a serialized mouse state value.
// See ToMouse for the value format.
func FromMouse(data string) (mouse MousePayload, event MouseEvent, err error) {
	v := strings.Split(string([]byte(data)[1:]), ",")
	if len(v) < 6 {
		return mouse, 0, ErrDeserialize
	}
	left_, err := strconv.Atoi(v[0])
	if err != nil {
		return mouse, 0, err
	}
	event_, err := strconv.Atoi(v[1])
	if err != nil {
		return mouse, 0, err
	}
	x_, err := strconv.ParseFloat(v[2], 32)
	if err != nil {
		return mouse, 0, err
	}
	y_, err := strconv.ParseFloat(v[3], 32)
	if err != nil {
		return mouse, 0, err
	}
	w_, err := strconv.ParseFloat(v[4], 32)
	if err != nil {
		return mouse, 0, err
	}
	h_, err := strconv.ParseFloat(v[5], 32)
	if err != nil {
		return mouse, 0, err
	}
	return MousePayload{
		IsLeft: byte(left_),
		X:      float32(x_),
		Y:      float32(y_),
		Width:  float32(w_),
		Height: float32(h_),
	}, MouseEvent(event_), nil
}
