package shim

import "testing"

func TestGetDesktopSize(t *testing.T) {
	w, h, err := getDesktopSize()

	t.Logf("%vx%v %v", w, h, err)
}

func TestFindWindow(t *testing.T) {
	hwnd, err := FindWindow("Minesweeper")

	t.Logf("%v, %v", hwnd, err)
}

func TestFocusWindow(t *testing.T) {

	hwnd, err := FindWindow("Minesweeper")
	t.Logf("%v, %v", hwnd, err)

	FocusWindow(hwnd)
}
