package shim

import (
	"log"
	"math"
	"strings"
	"syscall"
	"unsafe"
)

const strBuf int32 = 256

func getDesktopSize() (w int, h int, err error) {
	var rect RECT
	err = GetWindowRect(GetDesktopWindow(), &rect)
	return int(rect.Right), int(rect.Bottom), err
}

func FindWindow(title string) (syscall.Handle, error) {
	var hWnd syscall.Handle
	err := EnumWindows(syscall.NewCallback(func(h syscall.Handle, _ uintptr) uintptr {
		var buf [strBuf]uint16
		if _, err := GetWindowText(h, &buf[0], strBuf); err != nil {
			return 1 // continue
		}
		if strings.Contains(syscall.UTF16ToString(buf[:]), title) {
			hWnd = h
			return 0 // stop
		}
		return 1
	}), 0)
	if err != nil {
		return 0, err
	}
	if hWnd == 0 {
		return 0, syscall.ERROR_NOT_FOUND
	}
	return hWnd, nil
}

func FocusWindow(hWnd syscall.Handle) {
	//_, err := SetActiveWindow(hWnd)
	//if err != nil {
	//	log.Printf("active window fail, %v", err)
	//}
	//win.ShowWindow(win.HWND(hWnd), win.SW_RESTORE)
	//win.SetFocus(win.HWND(hWnd))
	//win.BringWindowToTop(win.HWND(hWnd))
	SetForegroundWindow(hWnd)

	//SendKeyEvent(uintptr(hWnd), KeyPayload{KeyCode: 113}, KeyEventDown, false)
}

func FormatWindow(hWnd syscall.Handle) {
	SetWindowPos(hWnd, 0, 0, 0, 800, 600, 0)
	SetWindowLong(hWnd, GWL_STYLE, 0)
}

func SendKeyEvent(hWnd uintptr, payload KeyPayload, event KeyEvent, isDx bool) {
	log.Printf("Sending key %v", payload)

	FocusWindow(syscall.Handle(hWnd))

	input := KEYBD_INPUT{Type: INPUT_KEYBOARD}

	key := payload.KeyCode

	if isDx {
		if key == VK_UP || key == VK_DOWN || key == VK_LEFT || key == VK_RIGHT {
			input.Ki.DwFlags = KEYEVENTF_EXTENDEDKEY
			log.Printf(" after %v", key)
		}
		key = int(MapVirtualKey(uint32(key), 0))
		input.Ki.WScan = uint16(key) // hardware scan code for key
		input.Ki.DwFlags |= KEYEVENTF_SCANCODE
		log.Printf(" after %v", key)
	} else {
		input.Ki.WVk = uint16(key)
	}
	if event == KeyEventUp {
		input.Ki.DwFlags |= KEYEVENTF_KEYUP
	}
	val := SendInput(1, unsafe.Pointer(&input), int32(unsafe.Sizeof(input)))
	log.Printf("key sent %v - %v", key, val)
}

func SendMouseEvent(payload MousePayload, event MouseEvent) {
	fScreenWidth := GetSystemMetrics(SM_CXSCREEN) - 1
	fScreenHeight := GetSystemMetrics(SM_CYSCREEN) - 1
	fx := payload.X * (float32(math.MaxUint16 / fScreenWidth))
	fy := payload.Y * (float32(math.MaxUint16 / fScreenHeight))

	input := MOUSE_INPUT{
		Type: INPUT_MOUSE,
		Mi: MOUSEINPUT{
			Dx:      int32(fx),
			Dy:      int32(fy),
			DwFlags: MOUSEEVENTF_MOVE | MOUSEEVENTF_ABSOLUTE,
		},
	}
	SendInput(1, unsafe.Pointer(&input), int32(unsafe.Sizeof(input)))

	if payload.IsLeft == 1 && event == MouseEventDown {
		input.Mi.DwFlags = MOUSEEVENTF_LEFTDOWN | MOUSEEVENTF_ABSOLUTE
	} else if payload.IsLeft == 1 && event == MouseEventUp {
		input.Mi.DwFlags = MOUSEEVENTF_LEFTUP | MOUSEEVENTF_ABSOLUTE
	} else if payload.IsLeft == 0 && event == MouseEventDown {
		input.Mi.DwFlags = MOUSEEVENTF_RIGHTDOWN | MOUSEEVENTF_ABSOLUTE
	} else if payload.IsLeft == 0 && event == MouseEventUp {
		input.Mi.DwFlags = MOUSEEVENTF_RIGHTUP | MOUSEEVENTF_ABSOLUTE
	}

	// left down
	SendInput(1, unsafe.Pointer(&input), int32(unsafe.Sizeof(input)))
}
