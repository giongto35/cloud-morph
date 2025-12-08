/**
 * syncinput.exe - Windows input injection for Wine environment
 * 
 * Connects to TCP server (port 9090) and receives input commands:
 *   - K{keycode},{state}|  - Keyboard input (state: 0=up, 1=down)
 *   - M{left},{state},{x},{y},{w},{h}|  - Mouse input
 * 
 * Compile: x86_64-w64-mingw32-g++ syncinput.cpp -o syncinput.exe -lws2_32 -lpthread -static
 */

#include <iostream>
#include <windows.h>
#include <psapi.h>
#include <tlhelp32.h>
#include <vector>
#include <sstream>
#include <pthread.h>
#include <chrono>

using namespace std;

int screenWidth, screenHeight;
int server;
chrono::_V2::system_clock::time_point last_ping;
bool done;
HWND hwnd;
char *winTitle;
string hardcodeIP;
bool isMac = false;
bool isWindows = false;

const byte MOUSE_MOVE = 0;
const byte MOUSE_DOWN = 1;
const byte MOUSE_UP = 2;
const byte KEY_UP = 0;
const byte KEY_DOWN = 1;

// Connect to TCP server
int clientConnect() {
    WSADATA wsa_data;
    SOCKADDR_IN addr;

    memset(&addr, 0, sizeof(addr));
    WSAStartup(MAKEWORD(2, 0), &wsa_data);
    int server = socket(AF_INET, SOCK_STREAM, 0);

    addr.sin_family = AF_INET;
    addr.sin_port = htons(9090);
    
    if (isMac) {
        char ip[100];
        struct hostent *he;
        struct in_addr **addr_list;
        if ((he = gethostbyname("host.docker.internal")) == NULL) {
            printf("gethostbyname failed: %d", WSAGetLastError());
            return 1;
        }
        addr_list = (struct in_addr **)he->h_addr_list;
        for (int i = 0; addr_list[i] != NULL; i++) {
            strcpy(ip, inet_ntoa(*addr_list[i]));
        }
        addr.sin_addr.s_addr = inet_addr(ip);
    } else if (isWindows) {
        addr.sin_addr.s_addr = inet_addr(hardcodeIP.empty() ? "127.0.0.1" : hardcodeIP.c_str());
    } else {
        addr.sin_addr.s_addr = INADDR_ANY;
    }

    cout << "Connecting to server..." << endl;
    connect(server, reinterpret_cast<SOCKADDR *>(&addr), sizeof(addr));
    cout << "Connected!" << endl;
    return server;
}

void getDesktopResolution(int &width, int &height) {
    RECT desktop;
    const HWND hDesktop = GetDesktopWindow();
    GetWindowRect(hDesktop, &desktop);
    width = desktop.right;
    height = desktop.bottom;
}

// Find process ID by name
DWORD GetProcessIdByName(const char *processName) {
    HANDLE hSnapshot = CreateToolhelp32Snapshot(TH32CS_SNAPPROCESS, 0);
    if (hSnapshot == INVALID_HANDLE_VALUE) return 0;

    PROCESSENTRY32 pe32;
    pe32.dwSize = sizeof(PROCESSENTRY32);

    if (Process32First(hSnapshot, &pe32)) {
        do {
            if (_stricmp(pe32.szExeFile, processName) == 0) {
                DWORD pid = pe32.th32ProcessID;
                CloseHandle(hSnapshot);
                return pid;
            }
        } while (Process32Next(hSnapshot, &pe32));
    }
    CloseHandle(hSnapshot);
    return 0;
}

struct EnumData {
    DWORD targetPID;
    HWND hwnd;
};

BOOL CALLBACK EnumWindowsProc(HWND hwnd, LPARAM lParam) {
    EnumData *data = (EnumData *)lParam;
    DWORD dwPID = 0;
    GetWindowThreadProcessId(hwnd, &dwPID);
    
    if (dwPID == data->targetPID) {
        char title[256] = {0};
        char cls[256] = {0};
        GetWindowText(hwnd, title, 256);
        GetClassName(hwnd, cls, 256);
        
        if (strcmp(cls, "#32769") == 0) return TRUE;  // Skip desktop
        
        data->hwnd = hwnd;
        cout << "Found window PID " << dwPID << ": " << hwnd << " [" << title << "]" << endl;
        return FALSE;
    }
    return TRUE;
}

HWND getWindowByTitle(char *pattern) {
    // Try by process ID first
    DWORD pid = GetProcessIdByName("notepad.exe");
    if (pid != 0) {
        EnumData data = {pid, NULL};
        EnumWindows(EnumWindowsProc, (LPARAM)&data);
        if (data.hwnd != NULL) return data.hwnd;
    }

    // Try FindWindow
    HWND hwnd = FindWindow("Notepad", NULL);
    if (hwnd != NULL && IsWindow(hwnd)) return hwnd;

    // Fallback: enumerate windows
    hwnd = NULL;
    do {
        hwnd = FindWindowEx(NULL, hwnd, NULL, NULL);
        if (hwnd == NULL) break;

        char className[256] = {0};
        GetClassName(hwnd, className, 256);
        if (strcmp(className, "#32769") == 0) continue;

        int len = GetWindowTextLength(hwnd) + 1;
        char title[len];
        GetWindowText(hwnd, title, len);

        if (string(title).find(pattern) != string::npos) return hwnd;
        if (string(className).find("Notepad") != string::npos) return hwnd;
    } while (hwnd != 0);

    return NULL;
}

HWND sendIt(int key, bool state, bool isDxGame) {
    HWND targetHwnd = hwnd;
    if (targetHwnd == NULL || !IsWindow(targetHwnd)) {
        targetHwnd = GetForegroundWindow();
        if (targetHwnd == NULL) return 0;
    }
    
    SetActiveWindow(targetHwnd);
    ShowWindow(targetHwnd, SW_RESTORE);
    SetFocus(targetHwnd);
    BringWindowToTop(targetHwnd);

    INPUT ip;
    ZeroMemory(&ip, sizeof(INPUT));
    ip.type = INPUT_KEYBOARD;
    ip.ki.time = 0;
    ip.ki.dwExtraInfo = 0;
    
    if (isDxGame) {
        if (key == VK_UP || key == VK_DOWN || key == VK_LEFT || key == VK_RIGHT) {
            ip.ki.dwFlags = KEYEVENTF_EXTENDEDKEY;
        }
        key = MapVirtualKey(key, 0);
        ip.ki.wScan = key;
        ip.ki.dwFlags |= KEYEVENTF_SCANCODE;
    } else {
        ip.ki.wVk = key;
    }
    
    if (state == KEY_UP) {
        ip.ki.dwFlags |= KEYEVENTF_KEYUP;
    }
    
    SendInput(1, &ip, sizeof(INPUT));
    cout << "Sent key " << key << endl;
    return hwnd;
}

void MouseMove(int x, int y) {
    double fx = x * (65535.0f / (GetSystemMetrics(SM_CXSCREEN) - 1));
    double fy = y * (65535.0f / (GetSystemMetrics(SM_CYSCREEN) - 1));
    INPUT Input = {0};
    Input.type = INPUT_MOUSE;
    Input.mi.dwFlags = MOUSEEVENTF_MOVE | MOUSEEVENTF_ABSOLUTE;
    Input.mi.dx = fx;
    Input.mi.dy = fy;
    SendInput(1, &Input, sizeof(INPUT));
}

void sendMouseDown(bool isLeft, byte state, float x, float y) {
    HWND targetHwnd = hwnd;
    if (targetHwnd == NULL || !IsWindow(targetHwnd)) {
        targetHwnd = GetForegroundWindow();
        if (targetHwnd == NULL) return;
    }
    
    MouseMove(int(x), int(y));

    INPUT Input = {0};
    Input.type = INPUT_MOUSE;
    
    if (isLeft && state == MOUSE_DOWN) Input.mi.dwFlags = MOUSEEVENTF_LEFTDOWN | MOUSEEVENTF_ABSOLUTE;
    else if (isLeft && state == MOUSE_UP) Input.mi.dwFlags = MOUSEEVENTF_LEFTUP | MOUSEEVENTF_ABSOLUTE;
    else if (!isLeft && state == MOUSE_DOWN) Input.mi.dwFlags = MOUSEEVENTF_RIGHTDOWN | MOUSEEVENTF_ABSOLUTE;
    else if (!isLeft && state == MOUSE_UP) Input.mi.dwFlags = MOUSEEVENTF_RIGHTUP | MOUSEEVENTF_ABSOLUTE;

    SendInput(1, &Input, sizeof(INPUT));
}

struct Key { byte key; byte state; };
struct Mouse { byte isLeft; byte state; float x, y, relwidth, relheight; };

Key parseKeyPayload(string s) {
    stringstream ss(s);
    string substr;
    getline(ss, substr, ','); byte key = stof(substr);
    getline(ss, substr, ','); byte state = stof(substr);
    return {key, state};
}

Mouse parseMousePayload(string s) {
    stringstream ss(s);
    string substr;
    getline(ss, substr, ','); bool isLeft = stof(substr);
    getline(ss, substr, ','); byte state = stof(substr);
    getline(ss, substr, ','); float x = stof(substr);
    getline(ss, substr, ','); float y = stof(substr);
    getline(ss, substr, ','); float w = stof(substr);
    getline(ss, substr, ','); float h = stof(substr);
    return {isLeft, state, x, y, w, h};
}

void formatWindow(HWND hwnd) {
    if (hwnd == NULL || !IsWindow(hwnd)) return;
    SetWindowPos(hwnd, NULL, 0, 0, 800, 600, 0);
    cout << "Window formatted: " << hwnd << endl;
}

void *thealthcheck(void *args) {
    while (true) {
        auto cur = chrono::system_clock::now();
        chrono::duration<double> elapsed = cur - last_ping;
        if (elapsed.count() > 10) {
            cout << "Connection timeout" << endl;
            done = true;
            return NULL;
        }
        Sleep(2000);
    }
}

void *thwndupdate(void *args) {
    HWND oldhwnd = 0;
    while (true) {
        hwnd = getWindowByTitle(winTitle);
        if (hwnd == NULL) hwnd = GetForegroundWindow();
        
        if (hwnd != oldhwnd) {
            formatWindow(hwnd);
            oldhwnd = hwnd;
        }
        Sleep(2000);
    }
}

void processEvent(string ev, bool isDxGame) {
    if (ev[0] == 'K') {
        Key key = parseKeyPayload(ev.substr(1));
        cout << "Key: " << (int)key.key << " state: " << (int)key.state << endl;
        sendIt(key.key, key.state, isDxGame);
    } else if (ev[0] == 'M') {
        Mouse mouse = parseMousePayload(ev.substr(1));
        sendMouseDown(mouse.isLeft, mouse.state, mouse.x, mouse.y);
    }
}

int main(int argc, char *argv[]) {
    winTitle = (char *)"Notepad";
    bool isDxGame = false;

    if (argc > 1) winTitle = argv[1];
    if (argc > 2 && strcmp(argv[2], "game") == 0) isDxGame = true;
    if (argc > 3) {
        if (strcmp(argv[3], "host.docker.internal") == 0) isMac = true;
        else if (strcmp(argv[3], "windows") == 0) isWindows = true;
    }
    if (argc > 4) hardcodeIP = argv[4];

    server = clientConnect();
    hwnd = 0;
    
    getDesktopResolution(screenWidth, screenHeight);
    cout << "Screen: " << screenWidth << "x" << screenHeight << endl;

    done = false;
    last_ping = chrono::system_clock::now();
    
    pthread_t th1, th2;
    pthread_create(&th1, NULL, thealthcheck, NULL);
    pthread_create(&th2, NULL, thwndupdate, NULL);

    char buf[2000];
    string ev;

    while (!done) {
        int recv_size = recv(server, buf, 1024, 0);
        if (recv_size == SOCKET_ERROR) {
            Sleep(1000);
            continue;
        }

        last_ping = chrono::system_clock::now();
        
        if (recv_size == 1 && buf[0] == 0) continue;  // Ping

        try {
            stringstream ss(string(buf, recv_size));
            while (getline(ss, ev, '|')) {
                processEvent(ev, isDxGame);
            }
        } catch (const exception &e) {
            cout << "Error: " << e.what() << endl;
        }
    }

    closesocket(server);
    WSACleanup();
    return 0;
}

