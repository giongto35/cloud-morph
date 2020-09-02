#include <iostream>
#include <windows.h>
// #include <psapi.h>
#include <vector>
#include <sstream>
#include <pthread.h>
#include <ctime>
#include <chrono>
using namespace std;

int screenWidth, screenHeight;
int server; // TODO: Move to local variable
chrono::_V2::system_clock::time_point last_ping;
bool done;

int clientConnect()
{
    WSADATA wsa_data;
    SOCKADDR_IN addr;

    WSAStartup(MAKEWORD(2, 0), &wsa_data);
    int server = socket(AF_INET, SOCK_STREAM, 0);

    //inet_pton(AF_INET, "127.0.0.1", &addr.sin_addr.s_addr);

    addr.sin_family = AF_INET;
    addr.sin_port = htons(9090);
    addr.sin_addr.s_addr = INADDR_ANY;

    connect(server, reinterpret_cast<SOCKADDR *>(&addr), sizeof(addr));
    cout << "Connected to server!" << endl;
    return server;
}

// get the horizontal and vertical screen sizes in pixel
void getDesktopResolution(int &width, int &height)
{
    RECT desktop;
    // Get a handle to the desktop window
    const HWND hDesktop = GetDesktopWindow();
    // Get the size of screen to the variable desktop
    GetWindowRect(hDesktop, &desktop);
    // The top left corner will have coordinates (0,0)
    // and the bottom right corner will have coordinates
    // (width, height)
    width = desktop.right;
    height = desktop.bottom;
}

HWND getWindowByTitle(char *pattern)
{
    HWND hwnd = NULL;

    do
    {
        hwnd = FindWindowEx(NULL, hwnd, NULL, NULL);
        DWORD dwPID = 0;
        GetWindowThreadProcessId(hwnd, &dwPID);
        cout << "Searching" << hwnd << endl;
        int len = GetWindowTextLength(hwnd) + 1;

        char title[len];
        GetWindowText(hwnd, title, len);
        string st(title);
        cout << "len " << len << " Title : " << st << endl;

        if (st.find(pattern) != string::npos)
        {
            cout << "Found " << hwnd << endl;
            return hwnd;
        }
    } while (hwnd != 0);
    cout << "Not found";
    return hwnd; //Ignore that
}

HWND sendIt(HWND hwnd, int key)
{
    INPUT ip;

    // Set up a generic keyboard event.
    ip.type = INPUT_KEYBOARD;
    ip.ki.wScan = 0; // hardware scan code for key
    ip.ki.time = 0;
    ip.ki.dwExtraInfo = 0;
    ip.ki.wVk = key;   // virtual-key code for the "a" key
    ip.ki.dwFlags = 0; // 0 for key press

    cout << "Sending key " << ' ' << key << endl;
    HWND temp = SetActiveWindow(hwnd);
    ShowWindow(hwnd, SW_RESTORE);
    SetFocus(hwnd);
    BringWindowToTop(hwnd);

    //cout << temp << endl;
    SendInput(1, &ip, sizeof(INPUT));

    // PostMessage(hwnd, WM_KEYDOWN, key, 0x001E0001); //send
    // PostMessage(hwnd, WM_KEYUP, key, 0x001E0001);   //send
    cout << "sended key " << ' ' << key << endl;

    return hwnd;
}

int MakeLParam(float x, float y)
{
    return int(y) << 16 | (int(x) & 0xFFFF);
}
// MouseMove function
void MouseMove(int x, int y)
{
    double fScreenWidth = GetSystemMetrics(SM_CXSCREEN) - 1;
    double fScreenHeight = GetSystemMetrics(SM_CYSCREEN) - 1;
    double fx = x * (65535.0f / fScreenWidth);
    double fy = y * (65535.0f / fScreenHeight);
    INPUT Input = {0};
    Input.type = INPUT_MOUSE;
    Input.mi.dwFlags = MOUSEEVENTF_MOVE | MOUSEEVENTF_ABSOLUTE;
    Input.mi.dx = fx;
    Input.mi.dy = fy;
    SendInput(1, &Input, sizeof(INPUT));
}

void sendMouseDown(HWND hwnd, bool isLeft, bool isDown, float x, float y)
{
    cout << x << ' ' << y << endl;
    INPUT Input = {0};
    ZeroMemory(&Input, sizeof(INPUT));

    MouseMove(int(x), int(y));

    if (isLeft && isDown)
    {
        Input.mi.dwFlags = MOUSEEVENTF_LEFTDOWN | MOUSEEVENTF_ABSOLUTE;
    }
    else if (isLeft && !isDown)
    {
        Input.mi.dwFlags = MOUSEEVENTF_LEFTUP | MOUSEEVENTF_ABSOLUTE;
    }
    else if (!isLeft && isDown)
    {
        Input.mi.dwFlags = MOUSEEVENTF_RIGHTDOWN | MOUSEEVENTF_ABSOLUTE;
    }
    else if (!isLeft && !isDown)
    {
        Input.mi.dwFlags = MOUSEEVENTF_RIGHTUP | MOUSEEVENTF_ABSOLUTE;
    }

    // left down
    Input.type = INPUT_MOUSE;
    SendInput(1, &Input, sizeof(INPUT));
}

struct Mouse
{
    byte isLeft;
    byte isDown;
    float x;
    float y;
    float relwidth;
    float relheight;
};

// TODO: Use some proper serialization
Mouse parseMousePos(string stPos)
{
    stringstream ss(stPos);

    string substr;
    getline(ss, substr, ',');
    bool isLeft = stof(substr);

    getline(ss, substr, ',');
    bool isDown = stof(substr);

    getline(ss, substr, ',');
    float x = stof(substr);

    getline(ss, substr, ',');
    float y = stof(substr);

    getline(ss, substr, ',');
    float w = stof(substr);

    getline(ss, substr, ',');
    float h = stof(substr);

    return Mouse{isLeft, isDown, x, y, w, h};
}

void formatWindow(HWND hwnd)
{
    SetWindowPos(hwnd, NULL, 0, 0, 800, 600, 0);
    SetWindowLong(hwnd, GWL_STYLE, 0);
    cout << "Window formated" << endl;
}

void *healthcheck(void *args)
{
    while (true)
    {
        cout << "Health check pipe" << endl;
        auto cur = chrono::system_clock::now();
        chrono::duration<double> elapsed_seconds = cur - last_ping;
        cout << elapsed_seconds.count() << endl;
        if (elapsed_seconds.count() > 5)
        {
            // socket is died
            cout << "Broken pipe" << endl;
            done = true;
            return NULL;
        }
        Sleep(3000);
    }
}

int main(int argc, char *argv[])
{
    server = clientConnect();

    char *winTitle = (char *)"Notepad";
    if (argc > 1)
    {
        winTitle = argv[1];
    }
    cout << "Finding title " << winTitle << endl;
    HWND hwnd = 0;
    hwnd = getWindowByTitle(winTitle);
    while (hwnd == 0)
    {
        hwnd = getWindowByTitle(winTitle);
        Sleep(3000);
    }

    cout << "HWND: " << hwnd << endl;
    cout << "Connected " << server << endl;
    getDesktopResolution(screenWidth, screenHeight);
    cout << "width " << screenWidth << " "
         << "height " << screenHeight << endl;

    formatWindow(hwnd);

    // setup socket watcher. TODO: How to check if a socket pipe is broken?
    done = false;
    last_ping = chrono::system_clock::now();
    pthread_t th;
    int t = pthread_create(&th, NULL, healthcheck, NULL);

    do
    {
        int recv_size;
        char buf[2000];
        if (done)
        {
            exit(1);
        }
        //Receive a reply from the server
        if ((recv_size = recv(server, buf, 1024, 0)) == SOCKET_ERROR)
        {
            puts("recv failed");
            continue;
        }
        if (recv_size == 0)
        {
            //cout << "Rejected: " << buffer << ' ' << strlen(buffer) << endl;
            continue;
        }
        try
        {
            cout << recv_size << endl;
            char *buffer = new char[recv_size];
            memcpy(buffer, buf, recv_size);
            cout << "Got: " << buf << " Parsed: " << buffer << "recv size " << recv_size << " len " << strlen(buffer) << endl;
            if (recv_size == 1)
            {
                if (buffer[0] == 0)
                {
                    // Received ping
                    last_ping = chrono::system_clock::now();
                    continue;
                };
                // use key
                sendIt(hwnd, buffer[0]); //notepad ID
                cout << '\n'
                     << "Press a key to continue...";
            }
            else if (recv_size > 1)
            {
                string st(buffer);
                cout << "Mouse: " << st << endl;
                Mouse pos = parseMousePos(st);
                float x = pos.x * screenWidth / pos.relwidth;
                float y = pos.y * screenHeight / pos.relheight;
                cout << "pos: " << x << ' ' << y << ' ' << screenWidth << ' '
                     << screenHeight << ' ' << pos.relwidth << ' ' << pos.relheight << endl;
                sendMouseDown(hwnd, pos.isLeft, pos.isDown, x, y);
            }
        }
        catch (const std::exception &e)
        {
            cout << "exception" << e.what() << endl;
        }
    } while (true);
    closesocket(server);
    cout << "Socket closed." << endl
         << endl;

    WSACleanup();

    return 0;
}
