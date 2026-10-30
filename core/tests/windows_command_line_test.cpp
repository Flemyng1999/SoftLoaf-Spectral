#include <windows.h>
#include <shellapi.h>
#include "../../desktop/windows/command_line.h"
#include <stdexcept>
#include <vector>
int main() {
    const std::vector<std::wstring> expected={L"service.exe",L"",L"D:\\data folder\\",L"含空格 资料",L"literal\"quote",L"slashes\\\\\"quote",L"plain"};
    std::wstring command;
    for(const auto& argument:expected) {
        if(!command.empty())command+=L' ';
        command+=softloaf::quote_argument(argument);
    }
    int count=0;auto argv=CommandLineToArgvW(command.c_str(),&count);
    if(!argv||count!=static_cast<int>(expected.size()))throw std::runtime_error("argument count changed");
    for(int i=0;i<count;++i)if(argv[i]!=expected[i])throw std::runtime_error("argument content changed");
    LocalFree(argv);
}
