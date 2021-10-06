//go:build windows
// +build windows

package shim

import (
	"errors"
	"syscall"
	"unsafe"

	"golang.org/x/sys/windows"
)

// KEYBDINPUT
// See: https://docs.microsoft.com/en-us/windows/win32/api/winuser/ns-winuser-keybdinput.
type KEYBDINPUT struct {
	WVk         uint16
	WScan       uint16
	DwFlags     uint32
	Time        uint32
	DwExtraInfo uintptr

	_ [8]byte
}

type KEYBD_INPUT struct {
	Type uint32
	Ki   KEYBDINPUT
}

type MOUSE_INPUT struct {
	Type uint32
	Mi   MOUSEINPUT
}

type MOUSEINPUT struct {
	Dx          int32
	Dy          int32
	MouseData   uint32
	DwFlags     uint32
	Time        uint32
	DwExtraInfo uintptr
}

// INPUT Type
const (
	INPUT_MOUSE    = 0
	INPUT_KEYBOARD = 1
	INPUT_HARDWARE = 2
)

// Virtual key codes
const (
	VK_LEFT  = 37
	VK_UP    = 38
	VK_RIGHT = 39
	VK_DOWN  = 40
)

// KEYBDINPUT DwFlags
const (
	KEYEVENTF_EXTENDEDKEY = 0x0001
	KEYEVENTF_KEYUP       = 0x0002
	KEYEVENTF_SCANCODE    = 0x0008
	KEYEVENTF_UNICODE     = 0x0004
)

// GetSystemMetrics constants
const (
	SM_CXSCREEN = 0
	SM_CYSCREEN = 1
)

// MOUSEINPUT DwFlags
const (
	MOUSEEVENTF_ABSOLUTE        = 0x8000
	MOUSEEVENTF_HWHEEL          = 0x1000
	MOUSEEVENTF_MOVE            = 0x0001
	MOUSEEVENTF_MOVE_NOCOALESCE = 0x2000
	MOUSEEVENTF_LEFTDOWN        = 0x0002
	MOUSEEVENTF_LEFTUP          = 0x0004
	MOUSEEVENTF_RIGHTDOWN       = 0x0008
	MOUSEEVENTF_RIGHTUP         = 0x0010
	MOUSEEVENTF_MIDDLEDOWN      = 0x0020
	MOUSEEVENTF_MIDDLEUP        = 0x0040
	MOUSEEVENTF_VIRTUALDESK     = 0x4000
	MOUSEEVENTF_WHEEL           = 0x0800
	MOUSEEVENTF_XDOWN           = 0x0080
	MOUSEEVENTF_XUP             = 0x0100
)

// The RECT structure defines a rectangle by the coordinates of its upper-left and lower-right corners.
type RECT struct {
	Left, Top, Right, Bottom int32
}

// GetWindowLong
const (
	// GWL_EXSTYLE sets a new extended window style.
	GWL_EXSTYLE = -20
	// GWL_HINSTANCE sets a new application instance handle.
	GWL_HINSTANCE = -6
	// GWL_ID sets a new identifier of the child window.
	// The window cannot be a top-level window.
	GWL_ID = -12
	// GWL_STYLE sets a new window style.
	GWL_STYLE = -16
	// GWL_USERDATA sets the user data associated with the window.
	// This data is intended for use by the application that created the window.
	// Its value is initially zero.
	GWL_USERDATA = -21
	// GWL_WNDPROC sets a new address for the window procedure.
	// You cannot change this attribute if the window does not belong to the same process as the calling thread.
	GWL_WNDPROC = -4
)

// user32.dll
var (
	user32              *windows.LazyDLL
	enumWindows         *windows.LazyProc
	getDesktopWindow    *windows.LazyProc
	getSystemMetrics    *windows.LazyProc
	getWindowText       *windows.LazyProc
	getWindowRect       *windows.LazyProc
	mapVirtualKey       *windows.LazyProc
	sendInput           *windows.LazyProc
	setActiveWindow     *windows.LazyProc
	setForegroundWindow *windows.LazyProc
	setWindowPos        *windows.LazyProc
	setWindowLong       *windows.LazyProc
)

func init() {
	user32 = windows.NewLazySystemDLL("user32.dll")
	enumWindows = user32.NewProc("EnumWindows")
	getDesktopWindow = user32.NewProc("GetDesktopWindow")
	getSystemMetrics = user32.NewProc("GetSystemMetrics")
	getWindowText = user32.NewProc("GetWindowTextW")
	getWindowRect = user32.NewProc("GetWindowRect")
	mapVirtualKey = user32.NewProc("MapVirtualKey")
	sendInput = user32.NewProc("SendInput")
	setActiveWindow = user32.NewProc("SetActiveWindow")
	setForegroundWindow = user32.NewProc("SetForegroundWindow")
	setWindowPos = user32.NewProc("SetWindowPos")
	setWindowLong = user32.NewProc("SetWindowLongW")
}

func FreeLibs() error {
	return syscall.FreeLibrary(syscall.Handle(user32.Handle()))
}

// EnumWindows enumerates all top-level windows on the screen by passing the handle to each window,
// in turn, to an application-defined callback function. EnumWindows continues until the
// last top-level window is enumerated or the callback function returns FALSE.
//
// See: https://docs.microsoft.com/en-us/windows/win32/api/winuser/nf-winuser-enumwindows
func EnumWindows(lpEnumFunc uintptr, lParam uintptr) (err error) {
	r, _, callErr := syscall.Syscall(enumWindows.Addr(), 2, lpEnumFunc, lParam, 0)
	if r == 0 && !errors.Is(callErr, windows.SEVERITY_SUCCESS) {
		err = setErr(callErr)
	}
	return
}

// GetDesktopWindow retrieves a handle to the desktop window.
// The desktop window covers the entire screen.
// The desktop window is the area on top of which other windows are painted.
//
// See: https://docs.microsoft.com/en-us/windows/win32/api/winuser/nf-winuser-getdesktopwindow
func GetDesktopWindow() syscall.Handle {
	r, _, _ := syscall.Syscall(getDesktopWindow.Addr(), 0, 0, 0, 0)
	return syscall.Handle(r)
}

// GetWindowText copies the text of the specified window's title bar (if it has one) into a buffer.
// If the specified window is a control, the text of the control is copied.
// However, GetWindowText cannot retrieve the text of a control in another application.
//
// See: https://docs.microsoft.com/en-us/windows/win32/api/winuser/nf-winuser-getwindowtextw
func GetWindowText(hWnd syscall.Handle, lpString *uint16, nMaxCount int32) (len int32, err error) {
	r, _, callErr := syscall.Syscall(getWindowText.Addr(), 3,
		uintptr(hWnd),
		uintptr(unsafe.Pointer(lpString)),
		uintptr(nMaxCount))
	len = int32(r)
	if len == 0 {
		err = setErr(callErr)
	}
	return
}

// GetWindowRect retrieves the dimensions of the bounding rectangle of the specified window.
// The dimensions are given in screen coordinates that are relative to the upper-left corner of the screen.
//
// See: https://docs.microsoft.com/en-us/windows/win32/api/winuser/nf-winuser-getwindowrect
func GetWindowRect(hWnd syscall.Handle, lpRect *RECT) (err error) {
	r, _, callErr := syscall.Syscall(getWindowRect.Addr(), 2,
		uintptr(hWnd),
		uintptr(unsafe.Pointer(lpRect)),
		0)
	if r == 0 {
		err = setErr(callErr)
	}
	return
}

// MapVirtualKey translates (maps) a virtual-key code into a scan code
// or character value, or translates a scan code into a virtual-key code.
//
// To specify a handle to the keyboard layout to use for translating
// the specified code, use the MapVirtualKeyEx function.
//
// See: https://docs.microsoft.com/en-us/windows/win32/api/winuser/nf-winuser-mapvirtualkeyw
func MapVirtualKey(uCode uint32, uMapType uint32) uint32 {
	r, _, _ := syscall.Syscall(mapVirtualKey.Addr(), 2, uintptr(uCode), uintptr(uMapType), 0)
	return uint32(r)
}

// SendInput synthesizes keystrokes, mouse motions, and button clicks.
// pInputs expects a unsafe.Pointer to a slice of MOUSE_INPUT or KEYBD_INPUT or HARDWARE_INPUT structs.
//
// See: https://docs.microsoft.com/en-us/windows/win32/api/winuser/nf-winuser-sendinput
func SendInput(nInputs uint32, pInputs unsafe.Pointer, cbSize int32) uint32 {
	r, _, _ := syscall.Syscall(sendInput.Addr(), 3, uintptr(nInputs), uintptr(pInputs), uintptr(cbSize))
	return uint32(r)
}

// SetActiveWindow activates a window. The window must be attached to the calling thread's
// message queue.
//
// See: https://docs.microsoft.com/en-us/windows/win32/api/winuser/nf-winuser-setactivewindow
func SetActiveWindow(hWnd syscall.Handle) (rez syscall.Handle, err error) {
	r, _, callErr := syscall.Syscall(setActiveWindow.Addr(), 1, uintptr(hWnd), 0, 0)
	rez = syscall.Handle(r)
	if r == 0 && !errors.Is(callErr, windows.DNS_ERROR_RCODE_NO_ERROR) {
		err = setErr(callErr)
	}
	return
}

// SetForegroundWindow brings the thread that created the specified window into the foreground
// and activates the window. Keyboard input is directed to the window, and various visual cues are
// changed for the user. The system assigns a slightly higher priority to the thread that created the
// foreground window than it does to other threads.
//
// See: https://docs.microsoft.com/en-us/windows/win32/api/winuser/nf-winuser-setforegroundwindow
func SetForegroundWindow(hWnd syscall.Handle) bool {
	r, _, _ := syscall.Syscall(setForegroundWindow.Addr(), 1, uintptr(hWnd), 0, 0)
	return r != 0
}

// SetWindowPos changes the size, position, and Z order of a child, pop-up, or top-level window.
// These windows are ordered according to their appearance on the screen.
// The topmost window receives the highest rank and is the first window in the Z order.
//
// See: https://docs.microsoft.com/en-us/windows/win32/api/winuser/nf-winuser-setwindowpos
func SetWindowPos(hWnd syscall.Handle, hWndInsertAfter syscall.Handle, x, y, width, height int32, flags uint32) bool {
	r, _, _ := syscall.Syscall9(setWindowPos.Addr(), 7,
		uintptr(hWnd),
		uintptr(hWndInsertAfter),
		uintptr(x),
		uintptr(y),
		uintptr(width),
		uintptr(height),
		uintptr(flags),
		0,
		0)
	return r != 0
}

// SetWindowLong Changes an attribute of the specified window.
// The function also sets the 32-bit (long) value at the specified offset into the extra window memory.
//
// See: https://docs.microsoft.com/en-us/windows/win32/api/winuser/nf-winuser-setwindowlongw
func SetWindowLong(hWnd syscall.Handle, index, value int32) int32 {
	r, _, _ := syscall.Syscall(setWindowLong.Addr(), 3, uintptr(hWnd), uintptr(index), uintptr(value))
	return int32(r)
}

// GetSystemMetrics retrieves the specified system metric or system configuration setting.
// Note that all dimensions retrieved by GetSystemMetrics are in pixels.
//
// See: https://docs.microsoft.com/en-us/windows/win32/api/winuser/nf-winuser-getsystemmetrics
func GetSystemMetrics(nIndex int32) int32 {
	r, _, _ := syscall.Syscall(getSystemMetrics.Addr(), 1, uintptr(nIndex), 0, 0)
	return int32(r)
}

func setErr(e syscall.Errno) (err error) {
	if e != 0 {
		err = error(e)
	} else {
		err = syscall.EINVAL
	}
	return
}
