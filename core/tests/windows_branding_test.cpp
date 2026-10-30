#define WIN32_LEAN_AND_MEAN
#include <windows.h>
#include <filesystem>
#include <iostream>
#include <set>
#include <vector>

int main(int argc,char** argv) {
    if(argc!=2)return 1;
    const auto path=std::filesystem::path(argv[1]).wstring();
    const auto module=LoadLibraryExW(path.c_str(),nullptr,LOAD_LIBRARY_AS_DATAFILE);
    if(!module)return 2;
    const auto resource=FindResourceW(module,MAKEINTRESOURCEW(101),RT_GROUP_ICON);
    if(!resource){FreeLibrary(module);return 3;}
    const auto data=static_cast<const unsigned char*>(LockResource(LoadResource(module,resource)));
    const auto size=SizeofResource(module,resource);
    const auto count=size>=6?data[4]+256*data[5]:0;
    if(size<6+14*count){FreeLibrary(module);return 4;}
    std::set<int> actual;
    for(int i=0;i<count;++i)actual.insert(data[6+14*i]?data[6+14*i]:256);
    FreeLibrary(module);
    if(actual!=std::set<int>{16,20,24,32,40,48,64,96,128,256})return 5;
    DWORD unused=0;const auto bytes=GetFileVersionInfoSizeW(path.c_str(),&unused);
    if(!bytes)return 6;
    std::vector<unsigned char> info(bytes);
    if(!GetFileVersionInfoW(path.c_str(),0,bytes,info.data()))return 7;
    for(const auto language:{L"0409",L"0804"}){
        const auto key=L"\\StringFileInfo\\"+std::wstring(language)+L"04b0\\ProductName";
        void* value=nullptr;UINT length=0;
        if(!VerQueryValueW(info.data(),key.c_str(),&value,&length))return 8;
        const auto expected=std::wstring(language)==L"0804"?L"面包光谱":L"SoftLoaf Spectral";
        if(std::wstring(static_cast<const wchar_t*>(value))!=expected)return 9;
    }
    std::cout<<"Verified ten embedded icon sizes and both localized product names\n";
}
