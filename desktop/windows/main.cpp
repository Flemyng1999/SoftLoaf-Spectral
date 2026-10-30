// Local development shell. WebView2 hosts the same loopback UI as macOS.
#define WIN32_LEAN_AND_MEAN
#define NOMINMAX
#include <windows.h>
#include <tlhelp32.h>
#include <charconv>
#include "process_tree.h"
#include "dpi_window.h"
#include <ole2.h>
#include <shellapi.h>
#include <WebView2.h>
#include <wrl.h>
#include <filesystem>
#include <fstream>
#include <regex>
#include <string>
#include <vector>

using Microsoft::WRL::Callback;
using Microsoft::WRL::ComPtr;
namespace fs=std::filesystem;
namespace {
struct Application {
    HWND window=nullptr;HANDLE service=nullptr,stop=nullptr;DWORD service_id=0;bool ready=false,closing=false,check=false,english=true;int exit_code=0;
    fs::path directory,source,report,ready_file;std::wstring origin;
    ComPtr<ICoreWebView2Controller> controller;ComPtr<ICoreWebView2> web;
    std::wstring setting(const wchar_t* key,const wchar_t* fallback=L"")const {
        std::vector<wchar_t> value(32768);GetPrivateProfileStringW(L"runtime",key,fallback,value.data(),static_cast<DWORD>(value.size()),(directory/L"runtime.ini").c_str());return value.data();
    }
    void result(bool ok,const char* stage,HRESULT code=S_OK){if(report.empty())return;std::ofstream stream(report);stream<<"{\"ok\":"<<(ok?"true":"false")<<",\"stage\":\""<<stage<<"\",\"window_created\":"<<(window?"true":"false")<<",\"dpi_per_monitor_v2\":"<<(AreDpiAwarenessContextsEqual(GetThreadDpiAwarenessContext(),DPI_AWARENESS_CONTEXT_PER_MONITOR_AWARE_V2)?"true":"false")<<",\"window_dpi\":"<<(window?GetDpiForWindow(window):0)<<",\"native_hresult\":"<<static_cast<unsigned long>(code)<<"}\n";}
    void failure(const wchar_t* message,const char* stage="startup",HRESULT code=S_OK){exit_code=2;result(false,stage,code);CreateWindowW(L"STATIC",message,WS_CHILD|WS_VISIBLE,28,70,1000,180,window,nullptr,nullptr,nullptr);if(check){DestroyWindow(window);PostQuitMessage(2);}}
    void resize(){if(controller){RECT bounds{};GetClientRect(window,&bounds);controller->put_Bounds(bounds);}}
    void start_web(){
        if(check)result(false,"environment-start");
        auto cache=setting(L"browser_cache");
        // Only this fixed, pixel-free smoke page may use the build directory.
        if(check&&cache.empty())cache=(directory/L"shell-check-browser-cache").wstring();
        if(cache.empty()){failure(L"Set the browser profile on the configured external data volume.","runtime-config");return;}fs::create_directories(cache);
        const auto started=CreateCoreWebView2EnvironmentWithOptions(nullptr,cache.c_str(),nullptr,Callback<ICoreWebView2CreateCoreWebView2EnvironmentCompletedHandler>([this](HRESULT error,ICoreWebView2Environment* environment)->HRESULT {
            if(FAILED(error)||!environment){failure(L"Microsoft Edge WebView2 Runtime is unavailable.","environment-failed",error);return S_OK;}
            if(check)result(false,"environment-ready");
            const auto controller_request=environment->CreateCoreWebView2Controller(window,Callback<ICoreWebView2CreateCoreWebView2ControllerCompletedHandler>([this](HRESULT created,ICoreWebView2Controller* value)->HRESULT {
                if(FAILED(created)||!value){failure(L"Could not create the WebView2 window.","controller-failed",created);return S_OK;}
                if(check)result(false,"controller-ready");
                controller=value;controller->get_CoreWebView2(&web);resize();controller->put_IsVisible(TRUE);
                EventRegistrationToken token{};
                web->add_NavigationStarting(Callback<ICoreWebView2NavigationStartingEventHandler>([this](ICoreWebView2*,ICoreWebView2NavigationStartingEventArgs* args)->HRESULT {
                    LPWSTR raw=nullptr;args->get_Uri(&raw);const std::wstring uri=raw?raw:L"";CoTaskMemFree(raw);
                    // Shell-check supplies only our fixed NavigateToString page;
                    // WebView2 may use a synthetic document URI for it.
                    const bool local=check||(!origin.empty()&&(uri.starts_with(origin)||uri.starts_with(L"blob:"+origin)));
                    if(!local){args->put_Cancel(TRUE);BOOL user=FALSE;args->get_IsUserInitiated(&user);if(user&&uri.starts_with(L"https://"))ShellExecuteW(window,L"open",uri.c_str(),nullptr,nullptr,SW_SHOWNORMAL);}
                    return S_OK;
                }).Get(),&token);
                web->add_WebMessageReceived(Callback<ICoreWebView2WebMessageReceivedEventHandler>([this](ICoreWebView2*,ICoreWebView2WebMessageReceivedEventArgs* args)->HRESULT {
                    LPWSTR source_url=nullptr;args->get_Source(&source_url);const std::wstring source=source_url?source_url:L"";CoTaskMemFree(source_url);
                    if(origin.empty()||!source.starts_with(origin))return S_OK;
                    LPWSTR raw=nullptr;args->get_WebMessageAsJson(&raw);const std::wstring value=raw?raw:L"";CoTaskMemFree(raw);
                    if(std::regex_search(value,std::wregex(LR"("kind"\s*:\s*"language")"))){
                        english=std::regex_search(value,std::wregex(LR"("value"\s*:\s*"en")"));
                        SetWindowTextW(window,english?L"SoftLoaf Spectral":L"面包光谱");
                        ModifyMenuW(GetMenu(window),1,MF_BYCOMMAND|MF_STRING,1,english?L"Settings…":L"设置…");
                        ModifyMenuW(GetMenu(window),2,MF_BYCOMMAND|MF_STRING,2,english?L"Exit":L"退出");DrawMenuBar(window);
                    }
                    if(value.find(L"\"quit\"")!=std::wstring::npos){
                        if(std::regex_search(value,std::wregex(LR"("ok"\s*:\s*true)")))DestroyWindow(window);
                        else{closing=false;MessageBoxW(window,L"Apply or save pending edits before closing.",english?L"SoftLoaf Spectral":L"面包光谱",MB_OK);}
                    }
                    return S_OK;
                }).Get(),&token);
                if(check){
                    web->add_NavigationCompleted(Callback<ICoreWebView2NavigationCompletedEventHandler>([this](ICoreWebView2*,ICoreWebView2NavigationCompletedEventArgs* args)->HRESULT {
                        BOOL success=FALSE;args->get_IsSuccess(&success);if(!success){failure(L"WebView2 smoke navigation failed.","navigation-failed");return S_OK;}
                        web->ExecuteScript(L"document.getElementById('shell-check').textContent",Callback<ICoreWebView2ExecuteScriptCompletedHandler>([this](HRESULT error,LPCWSTR text)->HRESULT {
                            const bool ok=SUCCEEDED(error)&&text&&std::wstring(text)==L"\"SoftLoaf Spectral\"";result(ok,"webview2-script");DestroyWindow(window);PostQuitMessage(ok?0:2);return S_OK;
                        }).Get());return S_OK;
                    }).Get(),&token);
                    web->NavigateToString(L"<!doctype html><meta charset='utf-8'><title>SoftLoaf Spectral</title><p id='shell-check'>SoftLoaf Spectral</p>");
                }else web->Navigate(origin.c_str());
                return S_OK;
            }).Get());
            if(FAILED(controller_request))failure(L"WebView2 rejected creation of the desktop controller.","controller-rejected",controller_request);
            return S_OK;
        }).Get());
        if(FAILED(started))failure(L"Could not initialize Microsoft WebView2.","environment-rejected",started);
    }
    void start_service(){
        source=setting(L"source");const auto python=setting(L"python"),core=setting(L"core");
        if(!fs::is_regular_file(python)||!fs::is_regular_file(core)){failure(L"Development Python or C++ runtime is missing. Check runtime.ini.");return;}
        const auto output=source/L"artifacts/application";fs::create_directories(output);
        const auto identity=std::to_wstring(GetCurrentProcessId());ready_file=output/(L"windows-ready-"+identity+L".json");fs::remove(ready_file);
        const auto event_name=L"Local\\SoftLoafSpectralStop-"+identity;stop=CreateEventW(nullptr,TRUE,FALSE,event_name.c_str());
        SECURITY_ATTRIBUTES security{sizeof(SECURITY_ATTRIBUTES),nullptr,TRUE};
        HANDLE log=CreateFileW((output/L"windows-desktop.log").c_str(),GENERIC_WRITE,FILE_SHARE_READ,&security,CREATE_ALWAYS,FILE_ATTRIBUTE_NORMAL,nullptr);
        STARTUPINFOW info{};info.cb=sizeof(info);info.dwFlags=STARTF_USESTDHANDLES;info.hStdOutput=log;info.hStdError=log;info.hStdInput=GetStdHandle(STD_INPUT_HANDLE);
        auto command=L"\""+python+L"\" -X utf8 -m spectral_app --compute auto --core \""+core+L"\" --parent-pid "+identity+L" --stop-event \""+event_name+L"\" --ready-file \""+ready_file.wstring()+L"\"";
        PROCESS_INFORMATION process{};const auto ok=CreateProcessW(python.c_str(),command.data(),nullptr,nullptr,TRUE,CREATE_NO_WINDOW,nullptr,source.c_str(),&info,&process);
        if(log!=INVALID_HANDLE_VALUE)CloseHandle(log);
        if(!ok){failure(L"Could not start the local Python service.");return;}
        service=process.hProcess;service_id=process.dwProcessId;CloseHandle(process.hThread);SetTimer(window,1,200,nullptr);SetTimer(window,2,60000,nullptr);
    }
    bool owns_service(const std::string& value)const {
        DWORD candidate=0;const auto parsed=std::from_chars(value.data(),value.data()+value.size(),candidate);
        if(parsed.ec!=std::errc{}||parsed.ptr!=value.data()+value.size()||!candidate)return false;
        const auto snapshot=CreateToolhelp32Snapshot(TH32CS_SNAPPROCESS,0);
        if(snapshot==INVALID_HANDLE_VALUE)return false;
        std::unordered_map<std::uint32_t,std::uint32_t> parents;PROCESSENTRY32W entry{};entry.dwSize=sizeof(entry);
        if(Process32FirstW(snapshot,&entry))do{parents[entry.th32ProcessID]=entry.th32ParentProcessID;}while(Process32NextW(snapshot,&entry));
        CloseHandle(snapshot);
        return parents.contains(candidate)&&softloaf::belongs_to_launch(candidate,service_id,parents);
    }
    void poll(){
        if(ready_file.empty())return;
        std::ifstream file(ready_file);const std::string text((std::istreambuf_iterator<char>(file)),{});std::smatch match;
        std::smatch owner;
        if(std::regex_search(text,owner,std::regex(R"sl("pid"\s*:\s*([0-9]+))sl"))&&owns_service(owner[1].str())&&std::regex_search(text,match,std::regex(R"sl("url"\s*:\s*"(http://127\.0\.0\.1:[0-9]+/)")sl"))){
            const auto url=match[1].str();origin.assign(url.begin(),url.end());KillTimer(window,1);KillTimer(window,2);ready=true;start_web();return;
        }
        DWORD code=STILL_ACTIVE;GetExitCodeProcess(service,&code);
        if(code!=STILL_ACTIVE){KillTimer(window,1);KillTimer(window,2);failure(L"Required runtime data is unavailable. See artifacts/application/windows-desktop.log.\nNo RAW or hyperspectral sources are bundled in this development build.");}
    }
    void close(){
        if(closing)return;
        if(web&&ready){closing=true;web->ExecuteScript(L"(async()=>{try{const r=await window.softloafFlushSession();chrome.webview.postMessage({kind:'quit',ok:r.ok});}catch(e){chrome.webview.postMessage({kind:'quit',ok:false});}})()",nullptr);}
        else DestroyWindow(window);
    }
    void stop_service(){
        if(stop)SetEvent(stop);
        if(service){if(WaitForSingleObject(service,5000)==WAIT_TIMEOUT)TerminateProcess(service,2);CloseHandle(service);service=nullptr;}
        if(stop){CloseHandle(stop);stop=nullptr;}
        if(controller)controller->Close();web.Reset();controller.Reset();
    }
};
Application* application=nullptr;
LRESULT CALLBACK procedure(HWND window,UINT message,WPARAM w,LPARAM l){
    if(!application)return DefWindowProcW(window,message,w,l);
    switch(message){
        case WM_SIZE:application->resize();return 0;
        case WM_DPICHANGED:{
            const auto* bounds=reinterpret_cast<const RECT*>(l);
            SetWindowPos(window,nullptr,bounds->left,bounds->top,
                bounds->right-bounds->left,bounds->bottom-bounds->top,
                SWP_NOACTIVATE|SWP_NOZORDER);
            application->resize();return 0;
        }
        case WM_TIMER:if(w==1)application->poll();else if(w==2){KillTimer(window,1);KillTimer(window,2);application->failure(L"Local service startup timed out. See the application log.");}return 0;
        case WM_COMMAND:if(LOWORD(w)==1&&application->web)application->web->ExecuteScript(L"window.softloafOpenSettings?.()",nullptr);else if(LOWORD(w)==2)application->close();return 0;
        case WM_CLOSE:application->close();return 0;
        case WM_DESTROY:application->stop_service();PostQuitMessage(0);return 0;
    }
    return DefWindowProcW(window,message,w,l);
}
}
int WINAPI wWinMain(HINSTANCE instance,HINSTANCE,PWSTR,int show){
    const HRESULT com=CoInitializeEx(nullptr,COINIT_APARTMENTTHREADED);if(FAILED(com))return 2;
    Application app;application=&app;wchar_t executable[32768]{};GetModuleFileNameW(nullptr,executable,32768);app.directory=fs::path(executable).parent_path();
    int argc=0;auto** argv=CommandLineToArgvW(GetCommandLineW(),&argc);
    for(int i=1;i<argc;++i){if(std::wstring(argv[i])==L"--shell-check")app.check=true;else if(std::wstring(argv[i])==L"--report"&&i+1<argc)app.report=argv[++i];}LocalFree(argv);
    WNDCLASSW type{};type.lpfnWndProc=procedure;type.hInstance=instance;type.lpszClassName=L"SoftLoafSpectralDevelopment";type.hCursor=LoadCursorW(nullptr,IDC_ARROW);type.hIcon=LoadIconW(instance,MAKEINTRESOURCEW(101));type.hbrBackground=reinterpret_cast<HBRUSH>(COLOR_WINDOW+1);RegisterClassW(&type);
    app.window=CreateWindowW(type.lpszClassName,L"SoftLoaf Spectral",WS_OVERLAPPEDWINDOW,CW_USEDEFAULT,CW_USEDEFAULT,1320,900,nullptr,nullptr,instance,nullptr);
    auto menu=CreateMenu();AppendMenuW(menu,MF_STRING,1,L"Settings…");AppendMenuW(menu,MF_STRING,2,L"Exit");SetMenu(app.window,menu);softloaf::size_initial_window(app.window);ShowWindow(app.window,show);
    if(app.check)app.start_web();else app.start_service();
    MSG message{};while(GetMessageW(&message,nullptr,0,0)>0){TranslateMessage(&message);DispatchMessageW(&message);}
    app.stop_service();application=nullptr;CoUninitialize();return app.exit_code?app.exit_code:static_cast<int>(message.wParam);
}
